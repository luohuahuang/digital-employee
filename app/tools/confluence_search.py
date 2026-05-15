"""
Tool: Search for relevant pages in Confluence (online retrieval).

Risk Level: L1 (self-execution, read-only)
Authentication: HTTP Basic Auth (username + API Token)
API Documentation: https://developer.atlassian.com/cloud/confluence/rest/v1/api-group-content/

Search Syntax (CQL) Examples:
  text~"discount coupon stacking"     # Full-text search
  text~"idempotent" AND space="QA"    # Limit to space
  title="Add to Cart Test Spec"       # Exact title search
  ancestor="12345"                    # Child pages of a page

Prerequisites: Configure CONFLUENCE_BASE_URL / CONFLUENCE_USERNAME / CONFLUENCE_API_TOKEN in .env
"""
import re

import requests

from config import (
    CONFLUENCE_API_TOKEN,
    CONFLUENCE_AUTH_TYPE,
    CONFLUENCE_BASE_URL,
    CONFLUENCE_USERNAME,
)

# Confluence REST API v1 search endpoint
_SEARCH_ENDPOINT = "/rest/api/content/search"

# Returned body expansion fields: view is rendered HTML (for excerpt display)
_EXPAND = "body.view,space,version"

# Maximum number of results per request
_DEFAULT_LIMIT = 5

# Number of characters to extract for excerpt (from cleaned plain text)
_EXCERPT_LEN = 300


def search_confluence(query: str, space_key: str = "", limit: int = _DEFAULT_LIMIT) -> str:
    """
    Search for relevant pages in Confluence using CQL.

    Args:
        query:     Search keywords, supports natural language or CQL syntax
                   Example: "discount coupon stacking rules" or text~"idempotent" AND space="QA"
        space_key: Optional, limit search scope to specified Space (e.g. "QA", "ARCH")
        limit:     Maximum number of results to return, default 5

    Returns:
        Formatted search results, each containing: title, Space, excerpt, page link, page_id (for later saving)
    """
    if not _check_config():
        return (
            "[Confluence Not Configured] Please set the following variables in .env:\n"
            "  CONFLUENCE_BASE_URL=https://yourcompany.atlassian.net\n"
            "  CONFLUENCE_USERNAME=your@email.com\n"
            "  CONFLUENCE_API_TOKEN=your_api_token"
        )

    # ── Build CQL Statement ────────────────────────────────────────────────────────
    # If query already contains CQL operators (AND/OR/~/"), use directly; otherwise wrap as full-text search
    if _is_cql(query):
        cql = query
    else:
        # Escape quotes to prevent CQL injection
        safe_query = query.replace('"', '\\"')
        cql = f'text~"{safe_query}"'

    if space_key:
        cql = f'{cql} AND space="{space_key}"'

    cql += " ORDER BY lastmodified DESC"

    # ── Make Request ─────────────────────────────────────────────────────────────
    url = f"{CONFLUENCE_BASE_URL.rstrip('/')}{_SEARCH_ENDPOINT}"
    params = {
        "cql":    cql,
        "limit":  min(limit, 20),
        "expand": _EXPAND,
    }

    try:
        response = requests.get(
            url,
            params=params,
            timeout=15,
            **_auth_kwargs(),
        )
        response.raise_for_status()
    except requests.exceptions.ConnectionError:
        return f"[Error] Cannot connect to Confluence: {CONFLUENCE_BASE_URL}, please check network or URL configuration."
    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response else "?"
        if status == 401:
            auth_hint = (
                "PAT mode: Please confirm CONFLUENCE_API_TOKEN is a Personal Access Token (not username/password)"
                if CONFLUENCE_AUTH_TYPE == "pat"
                else "Basic mode: Please confirm CONFLUENCE_USERNAME (email) and CONFLUENCE_API_TOKEN are correct"
            )
            return f"[Error] Confluence authentication failed (401). {auth_hint}"
        if status == 403:
            return "[Error] No permission to access this Confluence Space, please contact administrator."
        return f"[Error] Confluence API returned HTTP {status}: {e}"
    except requests.exceptions.Timeout:
        return "[Error] Confluence request timeout (15s), please check network connection."
    except Exception as e:
        return f"[Error] Confluence search failed: {e}"

    data = response.json()
    results = data.get("results", [])

    if not results:
        return f"[Confluence] No pages found related to '{query}'."

    # ── Format Output ────────────────────────────────────────────────────────────
    base_url = CONFLUENCE_BASE_URL.rstrip("/")
    lines = [f"【Confluence Search Results: {query}】(Total {len(results)} items)\n"]

    for i, item in enumerate(results, 1):
        page_id   = item.get("id", "")
        title     = item.get("title", "(No Title)")
        space     = item.get("space", {}).get("name", "")
        web_link  = base_url + item.get("_links", {}).get("webui", "")

        # Extract plain text excerpt from rendered HTML
        html_body = item.get("body", {}).get("view", {}).get("value", "")
        excerpt   = _html_to_text(html_body)[:_EXCERPT_LEN].strip()
        if len(_html_to_text(html_body)) > _EXCERPT_LEN:
            excerpt += "…"

        lines.append(
            f"── Result {i} ──\n"
            f"  Title: {title}\n"
            f"  Space: {space}\n"
            f"  Excerpt: {excerpt}\n"
            f"  Link: {web_link}\n"
            f"  page_id: {page_id} (can use save_confluence_page to cache to local knowledge base)\n"
        )

    lines.append(
        "💡 Tip: To save a page to local knowledge base for quick retrieval later, "
        "use save_confluence_page(page_id=...) (requires Mentor confirmation)."
    )
    return "\n".join(lines)


# ── Internal Helper Functions ──────────────────────────────────────────────────────────────

def _check_config() -> bool:
    """Check if necessary Confluence configuration exists."""
    if not CONFLUENCE_BASE_URL or not CONFLUENCE_API_TOKEN:
        return False
    # PAT mode doesn't need USERNAME; Basic mode does
    if CONFLUENCE_AUTH_TYPE != "pat" and not CONFLUENCE_USERNAME:
        return False
    return True


def _auth_kwargs() -> dict:
    """
    Return corresponding requests authentication parameters based on CONFLUENCE_AUTH_TYPE.

    pat   → Confluence Server/Data Center Personal Access Token
            Header: Authorization: Bearer <token>
    basic → Atlassian Cloud / older Server
            HTTP Basic Auth: username + api_token
    """
    if CONFLUENCE_AUTH_TYPE == "pat":
        return {"headers": {"Authorization": f"Bearer {CONFLUENCE_API_TOKEN}"}}
    else:
        return {"auth": (CONFLUENCE_USERNAME, CONFLUENCE_API_TOKEN)}


def _is_cql(query: str) -> bool:
    """Roughly determine if query is already a CQL statement (contains operators or field references)."""
    cql_keywords = [" AND ", " OR ", " NOT ", "~", "space=", "title=", "ancestor="]
    return any(kw in query for kw in cql_keywords)


def _html_to_text(html: str) -> str:
    """
    Simple HTML to plain text conversion:
    1. Remove all HTML tags
    2. Compress excess whitespace/line breaks to single space
    """
    if not html:
        return ""
    # Remove tags
    text = re.sub(r"<[^>]+>", " ", html)
    # Decode common HTML entities
    text = (text
            .replace("&amp;",  "&")
            .replace("&lt;",   "<")
            .replace("&gt;",   ">")
            .replace("&nbsp;", " ")
            .replace("&#39;",  "'")
            .replace("&quot;", '"'))
    # Compress whitespace
    text = re.sub(r"\s+", " ", text)
    return text.strip()
