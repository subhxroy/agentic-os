"""Custom LLM Provider Configuration Wizard for Agentic OS.

Allows adding any custom LLM provider (OpenAI-compatible / Custom API endpoint)
with options for API key and authentication header format:
- Bearer token (Authorization: Bearer <key>)
- x-api-key (x-api-key: <key>)
- Custom Header Name (e.g. X-API-Token, api-key, etc.)
"""

from __future__ import annotations

import os
import sys
import uuid
from typing import Any, Dict, Optional

def add_custom_provider(
    name: str,
    base_url: str,
    api_key: str = "",
    auth_header: str = "bearer",
    header_name: Optional[str] = None,
    model_name: Optional[str] = None,
    set_as_default: bool = True,
) -> Dict[str, Any]:
    """Programmatically add or update a custom LLM provider configuration."""
    from agentic_os_cli.config import load_config, save_config, get_config_path
    from agentic_os_cli.providers import custom_provider_slug
    from agent.credential_pool import PooledCredential, load_pool, AUTH_TYPE_API_KEY, SOURCE_MANUAL

    slug = custom_provider_slug(name)
    auth_header_lower = (auth_header or "bearer").strip().lower()
    
    if auth_header_lower == "x-api-key":
        final_header_name = "x-api-key"
    elif auth_header_lower == "custom" and header_name:
        final_header_name = header_name.strip()
    else:
        auth_header_lower = "bearer"
        final_header_name = "Authorization"

    # 1. Load config.yaml
    cfg = load_config() or {}
    custom_list = cfg.get("custom_providers") or []
    if not isinstance(custom_list, list):
        custom_list = []

    # Update existing entry or append
    found = False
    new_entry = {
        "name": name.strip(),
        "base_url": base_url.strip(),
        "api_key": api_key.strip(),
        "auth_header": auth_header_lower,
        "header_name": final_header_name,
    }
    if model_name and model_name.strip():
        new_entry["models"] = [model_name.strip()]

    for i, entry in enumerate(custom_list):
        if isinstance(entry, dict) and entry.get("name", "").strip().lower() == name.strip().lower():
            custom_list[i] = {**entry, **new_entry}
            found = True
            break
    
    if not found:
        custom_list.append(new_entry)

    cfg["custom_providers"] = custom_list

    # If requested, set as default active model & provider
    if set_as_default:
        model_cfg = cfg.get("model") or {}
        if not isinstance(model_cfg, dict):
            model_cfg = {}
        model_cfg["provider"] = slug
        if model_name and model_name.strip():
            model_cfg["name"] = model_name.strip()
        cfg["model"] = model_cfg

    save_config(cfg)

    # 2. Add credential to pool if API key provided
    if api_key and api_key.strip():
        pool = load_pool(slug)
        entry_id = uuid.uuid4().hex[:6]
        pool.add_entry(PooledCredential(
            provider=slug,
            id=entry_id,
            label=f"{name} API Key",
            auth_type=AUTH_TYPE_API_KEY,
            priority=0,
            source=SOURCE_MANUAL,
            access_token=api_key.strip(),
            base_url=base_url.strip(),
            extra={
                "auth_header": auth_header_lower,
                "header_name": final_header_name,
            }
        ))

    return {
        "slug": slug,
        "name": name,
        "base_url": base_url,
        "auth_header": auth_header_lower,
        "header_name": final_header_name,
        "model": model_name,
    }


def run_custom_provider_wizard() -> None:
    """Interactive terminal wizard for configuring custom providers."""
    print("\n\033[36m===================================================\033[0m")
    print("\033[36m  Agentic OS — Add Custom Provider & API Key\033[0m")
    print("\033[36m===================================================\033[0m\n")

    try:
        name = input("  1. Provider Name / ID (e.g. Groq, Together, vLLM, Ollama, My-API): ").strip()
        while not name:
            name = input("     Provider name cannot be empty. Try again: ").strip()

        base_url = input("  2. Base URL (e.g. https://api.groq.com/openai/v1, http://localhost:8000/v1): ").strip()
        while not base_url:
            base_url = input("     Base URL cannot be empty. Try again: ").strip()

        api_key = input("  3. API Key (optional, press Enter if no auth needed): ").strip()

        print("\n  4. Choose Auth Header Format:")
        print("     [1] Bearer Token  (Authorization: Bearer <API_KEY>)")
        print("     [2] x-api-key     (x-api-key: <API_KEY>)")
        print("     [3] Custom Header (e.g. X-API-Token, api-key, etc.)")
        
        choice = input("\n     Select option [1-3] (default: 1): ").strip() or "1"
        
        auth_header = "bearer"
        header_name = "Authorization"
        
        if choice == "2":
            auth_header = "x-api-key"
            header_name = "x-api-key"
        elif choice == "3":
            auth_header = "custom"
            header_name = input("     Enter Custom Header Name (e.g. X-API-Token): ").strip() or "X-API-Key"

        model_name = input("\n  5. Default Model Name (e.g. llama-3.3-70b, gpt-4o, custom-model): ").strip()

        res = add_custom_provider(
            name=name,
            base_url=base_url,
            api_key=api_key,
            auth_header=auth_header,
            header_name=header_name,
            model_name=model_name,
            set_as_default=True,
        )

        print("\n\033[32m===================================================\033[0m")
        print(f"  \033[32mSUCCESS! Custom Provider '{res['name']}' Configured!\033[0m")
        print(f"  Provider ID:  {res['slug']}")
        print(f"  Base URL:     {res['base_url']}")
        print(f"  Auth Header:  {res['header_name']} ({'Bearer <token>' if res['auth_header'] == 'bearer' else '<token>'})")
        if res['model']:
            print(f"  Active Model: {res['model']}")
        print("\033[32m===================================================\033[0m\n")

    except KeyboardInterrupt:
        print("\n  Setup cancelled.")
        sys.exit(0)
