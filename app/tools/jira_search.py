"""
Tool: Search Jira issues via JQL.

Risk Level: L1 (self-execution, read-only)
Auth: Jira Data Center / Server — Personal Access Token (Bearer)
API: Jira REST API v2  GET /rest/api/2/search

Typical use cases:
  - Find bugs related to a feature before designing test cases
  - Look up recently fixed issues to determine regression scope
  - Search for known issues in a specific component or sprint

Prerequisites: Configure JIRA_BASE_URL / JIRA_API_TOKEN in .env
"""
import re

import requests

from config import JIRA_API_TOKEN, JIRA_AUTH_TYPE, JIRA_BASE_URL, JIRA_USERNAME

_SEARCH_ENDPOINT = "/rest/api/2/search"

# Fields to fetch for each issue (keep payload small)
_FIELDS = [
    "summary", "issuetype", "status", "priority",
    "assignee", "reporter", "labels", "components",
    "fixVersions", "updated", "created",
]

_DEFAULT_MAX_RESULTS = 10
_SUMMARY_TRUNCATE    = 120   # chars


def search_jira(query: str, max_results: int = _DEFAULT_MAX_RESULTS) -> str:
    """
    Search Jira issues using JQL (Jira Query Language).

    Args:
        query:       JQL expression or natural-language keywords.
                     Natural-language example: "add to cart payment timeout"
                       → auto-wrapped as: text ~ "add to cart payment timeout" ORDER BY updated DESC
                     JQL example: 'project=QA AND status="In Progress" AND priority=High'
        max_results: Maximum number of results to return (default 10, max 50).

    Returns:
        Formatted list of matching issues: key, type, status, priority, summary, link.
    """
    if not _check_config():
        return (
            "[Jira Not Configured] Please set the following variables in .env:\n"
            "  JIRA_BASE_URL=https://jira.yourcompany.com\n"
            "  JIRA_API_TOKEN=your_personal_access_token\n"
            "  # JIRA_USERNAME is not required for Data Center PAT auth"
        )

    jql = _build_jql(query)
    url = f"{JIRA_BASE_URL.rstrip('/')}{_SEARCH_ENDPOINT}"
    params = {
        "jql":        jql,
        "maxResults": min(max_results, 50),
        "fields":     ",".join(_FIELDS),
    }

    try:
        response = requests.get(
            url, params=params, timeout=15, **_auth_kwargs()
        )
        response.raise_for_status()
    except requests.exceptions.ConnectionError:
        return f"[Error] Cannot connect to Jira: {JIRA_BASE_URL}. Check network or URL."
    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response else "?"
        if status == 400:
            return (
                f"[Error] JQL syntax error (400). JQL used: {jql}\n"
                f"Tip: Check field names, quote strings, or try a simpler keyword query."
            )
        if status == 401:
            return (
                "[Error] Jira authentication failed (401). "
                "Please confirm JIRA_API_TOKEN is a valid Personal Access Token."
            )
        if status == 403:
            return "[Error] No permission to access this Jira project. Contact your Jira admin."
        return f"[Error] Jira API returned HTTP {status}: {e}"
    except requests.exceptions.Timeout:
        return "[Error] Jira request timed out (15s). Check your network connection."
    except Exception as e:
        return f"[Error] Jira search failed: {e}"

    data   = response.json()
    issues = data.get("issues", [])
    total  = data.get("total", 0)

    if not issues:
        return f"[Jira] No issues found for query: '{query}'."

    base_url = JIRA_BASE_URL.rstrip("/")
    lines = [
        f"【Jira Search Results: {query}】"
        f"(Showing {len(issues)} of {total} total)\n"
    ]

    for issue in issues:
        key     = issue.get("key", "")
        fields  = issue.get("fields", {})
        summary = (fields.get("summary") or "")[:_SUMMARY_TRUNCATE]
        itype   = fields.get("issuetype", {}).get("name", "")
        status  = fields.get("status", {}).get("name", "")
        priority = fields.get("priority", {}).get("name", "") if fields.get("priority") else ""
        assignee = (fields.get("assignee") or {}).get("displayName", "Unassigned")
        updated  = (fields.get("updated") or "")[:10]   # YYYY-MM-DD
        labels   = ", ".join(fields.get("labels") or [])
        components = ", ".join(
            c.get("name", "") for c in (fields.get("components") or [])
        )
        link = f"{base_url}/browse/{key}"

        meta_parts = [f"Type: {itype}", f"Status: {status}"]
        if priority:
            meta_parts.append(f"Priority: {priority}")
        if assignee:
            meta_parts.append(f"Assignee: {assignee}")
        if updated:
            meta_parts.append(f"Updated: {updated}")
        if labels:
            meta_parts.append(f"Labels: {labels}")
        if components:
            meta_parts.append(f"Components: {components}")

        lines.append(
            f"── {key} ──\n"
            f"  Summary : {summary}\n"
            f"  {' | '.join(meta_parts)}\n"
            f"  Link    : {link}\n"
            f"  (Use get_jira_issue('{key}') to view full description and comments)\n"
        )

    return "\n".join(lines)


# ── Internal helpers ───────────────────────────────────────────────────────────

def _check_config() -> bool:
    return bool(JIRA_BASE_URL and JIRA_API_TOKEN)


def _auth_kwargs() -> dict:
    """
    pat   → Jira Data Center / Server: Authorization: Bearer <token>
    basic → Jira Cloud / Basic Auth: HTTP Basic (username + token)
    Controlled by JIRA_AUTH_TYPE env var (default: pat).
    """
    if JIRA_AUTH_TYPE == "basic":
        return {"auth": (JIRA_USERNAME, JIRA_API_TOKEN)}
    return {"headers": {"Authorization": f"Bearer {JIRA_API_TOKEN}"}}


def _build_jql(query: str) -> str:
    """
    If the query looks like JQL already (contains operators / field refs),
    use it verbatim. Otherwise wrap it as a full-text search.
    """
    jql_markers = [" AND ", " OR ", " NOT ", "project=", "status=",
                   "priority=", "assignee=", "issuetype=", "text~",
                   "labels=", "component=", "sprint=", "fixVersion="]
    if any(m.lower() in query.lower() for m in jql_markers):
        return query
    safe = query.replace('"', '\\"')
    return f'text ~ "{safe}" ORDER BY updated DESC'
