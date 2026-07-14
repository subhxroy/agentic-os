"""Marketplace — package publishing, versions, reviews, search, pricing, revenue."""

import uuid
import hashlib
import json
from datetime import datetime, timedelta
from database import pg_query, pg_execute


# ============================================================
# Packages
# ============================================================
def create_package(publisher_id: str, name: str, display_name: str,
                   description: str = None, long_description: str = None,
                   category: str = "general", tags: list = None,
                   icon_url: str = None, license: str = "MIT") -> dict:
    pkg_id = str(uuid.uuid4())
    pg_execute(
        """INSERT INTO marketplace_packages
           (id, publisher_id, name, display_name, description, long_description,
            category, tags, icon_url, license)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (pkg_id, publisher_id, name, display_name, description, long_description,
         category, tags or [], icon_url, license)
    )
    return get_package(pkg_id)


def get_package(pkg_id: str) -> dict:
    rows = pg_query("SELECT * FROM marketplace_packages WHERE id = %s", (pkg_id,))
    return rows[0] if rows else None


def get_package_by_name(name: str) -> dict:
    rows = pg_query("SELECT * FROM marketplace_packages WHERE name = %s", (name,))
    return rows[0] if rows else None


def update_package(pkg_id: str, **kwargs) -> dict:
    allowed = {"display_name", "description", "long_description", "category", "tags",
               "icon_url", "screenshot_urls", "license", "status", "review_notes",
               "reviewed_by", "reviewed_at", "featured"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return get_package(pkg_id)
    set_parts = []
    values = []
    for k, v in updates.items():
        if k in ("tags", "screenshot_urls"):
            set_parts.append(f"{k} = %s")
            values.append(v)
        elif k in ("reviewed_by", "reviewed_at"):
            set_parts.append(f"{k} = %s")
            values.append(v)
        else:
            set_parts.append(f"{k} = %s")
            values.append(v)
    pg_execute(f"UPDATE marketplace_packages SET {', '.join(set_parts)}, updated_at = NOW() WHERE id = %s",
               values + [pkg_id])
    return get_package(pkg_id)


def search_packages(query: str = None, category: str = None, tags: list = None,
                    status: str = "published", sort: str = "rating",
                    limit: int = 50, offset: int = 0) -> list:
    where = []
    params = []

    if status:
        where.append("mp.status = %s")
        params.append(status)

    if query:
        where.append("(mp.name ILIKE %s OR mp.display_name ILIKE %s OR mp.description ILIKE %s)")
        q = f"%{query}%"
        params.extend([q, q, q])

    if category:
        where.append("mp.category = %s")
        params.append(category)

    if tags:
        # SQLite: check if any of the search tags appear in the JSON tags array
        for tag in tags:
            where.append("mp.tags LIKE ?")
            params.append(f"%{tag}%")

    order = {
        "rating": "mp.rating_avg DESC, mp.rating_count DESC",
        "installs": "mp.installs_count DESC",
        "newest": "mp.created_at DESC",
        "downloads": "mp.downloads_total DESC",
    }.get(sort, "mp.rating_avg DESC")

    where_clause = f"WHERE {' AND '.join(where)}" if where else ""
    sql = f"""SELECT mp.*, u.email as publisher_email
              FROM marketplace_packages mp
              LEFT JOIN users u ON mp.publisher_id = u.id
              {where_clause}
              ORDER BY {order}
              LIMIT %s OFFSET %s"""
    params.extend([limit, offset])
    return pg_query(sql, params)


def list_publisher_packages(publisher_id: str) -> list:
    return pg_query(
        """SELECT * FROM marketplace_packages WHERE publisher_id = %s
           ORDER BY created_at DESC""",
        (publisher_id,)
    )


def submit_for_review(pkg_id: str) -> dict:
    return update_package(pkg_id, status="pending_review")


def approve_package(pkg_id: str, reviewer_id: str, notes: str = None) -> dict:
    return update_package(pkg_id, status="published", reviewed_by=reviewer_id,
                          reviewed_at=datetime.utcnow(), review_notes=notes)


def reject_package(pkg_id: str, reviewer_id: str, notes: str = None) -> dict:
    return update_package(pkg_id, status="suspended", reviewed_by=reviewer_id,
                          reviewed_at=datetime.utcnow(), review_notes=notes)


# ============================================================
# Versions
# ============================================================
def create_version(package_id: str, version: str, manifest: dict = None,
                   changelog: str = None, code_path: str = None,
                   file_size_bytes: int = 0, checksum: str = None) -> dict:
    vid = str(uuid.uuid4())
    pg_execute(
        """INSERT INTO package_versions
           (id, package_id, version, manifest, code_path, changelog, file_size_bytes, checksum)
           VALUES (%s, %s, %s, %s::jsonb, %s, %s, %s, %s)""",
        (vid, package_id, version, json.dumps(manifest or {}), code_path,
         changelog, file_size_bytes, checksum)
    )
    return get_version(vid)


def get_version(version_id: str) -> dict:
    rows = pg_query("SELECT * FROM package_versions WHERE id = %s", (version_id,))
    return rows[0] if rows else None


def list_versions(package_id: str) -> list:
    return pg_query(
        """SELECT * FROM package_versions WHERE package_id = %s
           ORDER BY created_at DESC""",
        (package_id,)
    )


def get_latest_version(package_id: str) -> dict:
    rows = pg_query(
        """SELECT * FROM package_versions WHERE package_id = %s AND status = 'published'
           ORDER BY created_at DESC LIMIT 1""",
        (package_id,)
    )
    return rows[0] if rows else None


def publish_version(version_id: str) -> dict:
    pg_execute("UPDATE package_versions SET status = 'published', reviewed_at = NOW() WHERE id = %s", (version_id,))
    return get_version(version_id)


# ============================================================
# Reviews
# ============================================================
def create_review(package_id: str, user_id: str, rating: int,
                  title: str = None, content: str = None) -> dict:
    review_id = str(uuid.uuid4())
    pg_execute(
        """INSERT INTO package_reviews (id, package_id, user_id, rating, title, content)
           VALUES (%s, %s, %s, %s, %s, %s)
           ON CONFLICT (package_id, user_id) DO UPDATE SET
              rating = EXCLUDED.rating, title = EXCLUDED.title,
              content = EXCLUDED.content, updated_at = NOW()""",
        (review_id, package_id, user_id, rating, title, content)
    )
    _update_package_rating(package_id)
    # Fetch the review (may have been upserted with different id)
    rows = pg_query(
        "SELECT * FROM package_reviews WHERE package_id = %s AND user_id = %s",
        (package_id, user_id)
    )
    return rows[0] if rows else {"id": review_id, "rating": rating}


def get_review(review_id: str) -> dict:
    rows = pg_query(
        """SELECT pr.*, u.email as user_email FROM package_reviews pr
           LEFT JOIN users u ON pr.user_id = u.id WHERE pr.id = %s""",
        (review_id,)
    )
    return rows[0] if rows else None


def list_reviews(package_id: str, limit: int = 50) -> list:
    return pg_query(
        """SELECT pr.*, u.email as user_email FROM package_reviews pr
           LEFT JOIN users u ON pr.user_id = u.id
           WHERE pr.package_id = %s ORDER BY pr.created_at DESC LIMIT %s""",
        (package_id, limit)
    )


def _update_package_rating(package_id: str):
    stats = pg_query(
        "SELECT AVG(rating) as avg, COUNT(*) as cnt FROM package_reviews WHERE package_id = %s",
        (package_id,)
    )
    if stats and stats[0]["avg"] is not None:
        pg_execute(
            "UPDATE marketplace_packages SET rating_avg = %s, rating_count = %s WHERE id = %s",
            (round(float(stats[0]["avg"]), 2), stats[0]["cnt"], package_id)
        )


# ============================================================
# Downloads & Analytics
# ============================================================
def record_download(package_id: str, user_id: str = None, org_id: str = None,
                    version_id: str = None, ip_address: str = None) -> None:
    pg_execute(
        """INSERT INTO package_downloads (id, package_id, version_id, user_id, org_id, ip_address)
           VALUES (%s, %s, %s, %s, %s, %s)""",
        (str(uuid.uuid4()), package_id, version_id, user_id, org_id, ip_address)
    )
    pg_execute(
        "UPDATE marketplace_packages SET installs_count = installs_count + 1, downloads_total = downloads_total + 1 WHERE id = %s",
        (package_id,)
    )


def get_download_analytics(package_id: str, days: int = 30) -> dict:
    cutoff = datetime.utcnow() - timedelta(days=days)
    total = pg_query(
        "SELECT COUNT(*) as count FROM package_downloads WHERE package_id = %s AND created_at > %s",
        (package_id, cutoff)
    )
    by_day = pg_query(
        """SELECT DATE(created_at) as day, COUNT(*) as count
           FROM package_downloads WHERE package_id = %s AND created_at > %s
           GROUP BY DATE(created_at) ORDER BY day""",
        (package_id, cutoff)
    )
    return {
        "total_downloads": total[0]["count"] if total else 0,
        "by_day": by_day,
        "period_days": days,
    }


def get_marketplace_stats() -> dict:
    total = pg_query("SELECT COUNT(*) as c FROM marketplace_packages WHERE status = 'published'")
    categories = pg_query(
        """SELECT category, COUNT(*) as count FROM marketplace_packages
           WHERE status = 'published' GROUP BY category ORDER BY count DESC"""
    )
    top_rated = pg_query(
        """SELECT id, name, display_name, rating_avg, rating_count, installs_count
           FROM marketplace_packages WHERE status = 'published'
           ORDER BY rating_avg DESC, rating_count DESC LIMIT 10"""
    )
    most_installed = pg_query(
        """SELECT id, name, display_name, installs_count, rating_avg
           FROM marketplace_packages WHERE status = 'published'
           ORDER BY installs_count DESC LIMIT 10"""
    )
    return {
        "total_packages": total[0]["c"] if total else 0,
        "categories": categories,
        "top_rated": top_rated,
        "most_installed": most_installed,
    }


# ============================================================
# Pricing
# ============================================================
def set_pricing(package_id: str, price_type: str = "free",
                price_cents: int = 0, currency: str = "USD",
                trial_days: int = 0, subscription_interval: str = None) -> dict:
    pricing_id = str(uuid.uuid4())
    pg_execute(
        """INSERT INTO package_pricing (id, package_id, price_type, price_cents, currency, trial_days, subscription_interval)
           VALUES (%s, %s, %s, %s, %s, %s, %s)
           ON CONFLICT (package_id) DO UPDATE SET
              price_type = EXCLUDED.price_type, price_cents = EXCLUDED.price_cents,
              currency = EXCLUDED.currency, trial_days = EXCLUDED.trial_days,
              subscription_interval = EXCLUDED.subscription_interval, updated_at = NOW()""",
        (pricing_id, package_id, price_type, price_cents, currency, trial_days, subscription_interval)
    )
    # Add unique constraint if not exists
    return get_pricing(package_id)


def get_pricing(package_id: str) -> dict:
    rows = pg_query("SELECT * FROM package_pricing WHERE package_id = %s", (package_id,))
    return rows[0] if rows else None


# ============================================================
# Revenue & Payouts
DEVELOPER_SPLIT = 0.70  # 70% to developer
PLATFORM_SPLIT = 0.30   # 30% to platform
# ============================================================
def record_revenue(package_id: str, user_id: str, amount_cents: int,
                   transaction_type: str = "purchase") -> dict:
    dev_share = int(amount_cents * DEVELOPER_SPLIT)
    plat_share = amount_cents - dev_share
    txn_id = str(uuid.uuid4())
    pg_execute(
        """INSERT INTO revenue_transactions
           (id, package_id, user_id, amount_cents, developer_share_cents, platform_share_cents, transaction_type)
           VALUES (%s, %s, %s, %s, %s, %s, %s)""",
        (txn_id, package_id, user_id, amount_cents, dev_share, plat_share, transaction_type)
    )
    return {"id": txn_id, "amount_cents": amount_cents,
            "developer_share": dev_share, "platform_share": plat_share}


def get_developer_revenue(user_id: str, days: int = 30) -> dict:
    cutoff = datetime.utcnow() - timedelta(days=days)
    total = pg_query(
        """SELECT SUM(developer_share_cents) as total, COUNT(*) as transactions
           FROM revenue_transactions WHERE user_id = %s AND created_at > %s""",
        (user_id, cutoff)
    )
    by_package = pg_query(
        """SELECT mp.name, SUM(rt.developer_share_cents) as revenue, COUNT(*) as sales
           FROM revenue_transactions rt JOIN marketplace_packages mp ON rt.package_id = mp.id
           WHERE rt.user_id = %s AND rt.created_at > %s
           GROUP BY mp.name ORDER BY revenue DESC""",
        (user_id, cutoff)
    )
    return {
        "total_revenue_cents": total[0]["total"] or 0 if total else 0,
        "total_transactions": total[0]["transactions"] or 0 if total else 0,
        "by_package": by_package,
        "period_days": days,
    }


def request_payout(user_id: str, amount_cents: int, period_days: int = 30) -> dict:
    period_end = datetime.utcnow()
    period_start = period_end - timedelta(days=period_days)
    payout_id = str(uuid.uuid4())
    pg_execute(
        """INSERT INTO developer_payouts (id, user_id, amount_cents, period_start, period_end)
           VALUES (%s, %s, %s, %s, %s)""",
        (payout_id, user_id, amount_cents, period_start, period_end)
    )
    return {"id": payout_id, "amount_cents": amount_cents, "status": "pending"}


def list_payouts(user_id: str) -> list:
    return pg_query(
        "SELECT * FROM developer_payouts WHERE user_id = %s ORDER BY created_at DESC",
        (user_id,)
    )


# ============================================================
# Security Scans
# ============================================================
def create_scan(package_id: str, scan_type: str, version_id: str = None) -> dict:
    scan_id = str(uuid.uuid4())
    pg_execute(
        """INSERT INTO package_scans (id, package_id, version_id, scan_type)
           VALUES (%s, %s, %s, %s)""",
        (scan_id, package_id, version_id, scan_type)
    )
    return {"id": scan_id, "status": "pending", "scan_type": scan_type}


def complete_scan(scan_id: str, status: str, findings: list = None) -> dict:
    pg_execute(
        """UPDATE package_scans SET status = %s, findings = %s::jsonb, scanned_at = NOW() WHERE id = %s""",
        (status, json.dumps(findings or []), scan_id)
    )
    return get_scan(scan_id)


def get_scan(scan_id: str) -> dict:
    rows = pg_query("SELECT * FROM package_scans WHERE id = %s", (scan_id,))
    return rows[0] if rows else None


def list_scans(package_id: str) -> list:
    return pg_query(
        "SELECT * FROM package_scans WHERE package_id = %s ORDER BY created_at DESC",
        (package_id,)
    )
