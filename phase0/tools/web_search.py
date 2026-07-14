import requests
import json
from tools.registry import tool

@tool(
    name="web_search",
    description="Search the web for information. Returns top results.",
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query",
            },
            "max_results": {
                "type": "integer",
                "description": "Number of results to return (default: 5)",
            },
        },
        "required": ["query"],
    },
)
def web_search(query: str, max_results: int = 5) -> str:
    url = f"https://html.duckduckgo.com/html/?q={requests.utils.quote(query)}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    resp = requests.get(url, headers=headers, timeout=10)
    import re
    results = re.findall(
        r'<a rel="nofollow" class="result__a" href="([^"]+)".*?class="result__snippet">(.*?)</a>',
        resp.text, re.DOTALL
    )
    out = []
    for i, (link, snippet) in enumerate(results[:max_results]):
        clean = re.sub(r'<[^>]+>', '', snippet).strip()
        out.append(f"{i+1}. {link}\n   {clean[:200]}")
    return "\n\n".join(out) if out else "No results found."
