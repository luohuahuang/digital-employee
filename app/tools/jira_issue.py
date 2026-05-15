"""
Tool: Fetch full details of a Jira issue by key.

Risk Level: L1 (self-execution, read-only)
Auth: Jira Data Center / Server — Personal Access Token (Bearer)
API: Jira REST API v2  GET /rest/api/2/issue/{issueKey}

Use when:
  - User mentions a specific issue key (e.g. QA-1234, SHOP-5678)
  - Need full description / acceptance criteria before writing test cases
  - Want to read comments for context on a known defect

Prerequisites: Configure JIRA_BASE_URL / JIRA_API_TOKEN in .env
"""
import requests

from config import JIRA_API_TOKEN, JIRA_AUTH_TYPE, JIRA_BASE_URL, JIRA_USERNAME

_ISSUE_ENDPOINT  = "/rest/api/2/issue/{issue_key}"
_MAX_COMMENTS    = 5      # Latest N comments to surface
_DESC_TRUNCATE   = 2000   # chars — keep response readable


def get_jira_issue(issue_key: str) -> str:
    """
    Retrieve the full detail of a Jira issue.

    Args:
        issue_key: Jira issue key, e.g. "QA-1234" or "SHOP-5678"

    Returns:
        Formatted issue detail: type, status, priority, description, latest comments.
    """
    if not _check_config():
        return (
            "[Jira Not Configured] Please set the following variables in .env:\n"
            "  JIRA_BASE_URL=https://jira.yourcompany.com\n"
            "  JIRA_API_TOKEN=your_personal_access_token"
        )

    issue_key = issue_key.strip().upper()
    url = f"{JIRA_BASE_URL.rstrip('/')}{_ISSUE_ENDPOINT.format(issue_key=issue_key)}"
    params = {
        "fields": (
            "summary,issuetype,status,priority,assignee,reporter,"
            "description,comment,labels,components,fixVersions,"
            "created,updated,environment"
        )
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
        if status == 404:
            return (
                f"[Error] Issue '{issue_key}' not found. "
                "Please check the issue key or your access permission."
            )
        if status == 401:
            return "[Error] Jira authentication failed (401). Check JIRA_API_TOKEN."
        return f"[Error] Jira API returned HTTP {status}: {e}"
    except requests.exceptions.Timeout:
        return "[Error] Jira request timed out (15s)."
    except Exception as e:
        return f"[Error] Failed to fetch Jira issue: {e}"

    data   = response.json()
    fields = data.get("fields", {})

    summary   = fields.get("summary", "")
    itype     = fields.get("issuetype", {}).get("name", "")
    status    = fields.get("status", {}).get("name", "")
    priority  = (fields.get("priority") or {}).get("name", "")
    assignee  = (fields.get("assignee") or {}).get("displayName", "Unassigned")
    reporter  = (fields.get("reporter") or {}).get("displayName", "")
    created   = (fields.get("created") or "")[:10]
    updated   = (fields.get("updated") or "")[:10]
    labels    = ", ".join(fields.get("labels") or [])
    components = ", ".join(
        c.get("name", "") for c in (fields.get("components") or [])
    )
    fix_versions = ", ".join(
        v.get("name", "") for v in (fields.get("fixVersions") or [])
    )
    environment = fields.get("environment") or ""
    description = _jira_text(fields.get("description") or "")
    if len(description) > _DESC_TRUNCATE:
        description = description[:_DESC_TRUNCATE] + "\n… (truncated)"

    base_url = JIRA_BASE_URL.rstrip("/")
    link     = f"{base_url}/browse/{issue_key}"

    lines = [
        f"【Jira Issue: {issue_key}】",
        f"  Summary    : {summary}",
        f"  Type       : {itype}",
        f"  Status     : {status}",
        f"  Priority   : {priority}",
        f"  Assignee   : {assignee}",
        f"  Reporter   : {reporter}",
        f"  Created    : {created}   Updated: {updated}",
    ]
    if labels:
        lines.append(f"  Labels     : {labels}")
    if components:
        lines.append(f"  Components : {components}")
    if fix_versions:
        lines.append(f"  Fix Version: {fix_versions}")
    if environment:
        lines.append(f"  Environment: {_jira_text(environment)[:200]}")
    lines.append(f"  Link       : {link}")

    lines.append("\n── Description ──")
    lines.append(description if description.strip() else "(No description)")

    # ── Latest comments ───────────────────────────────────────────────────────
    comment_data = fields.get("comment", {})
    comments     = comment_data.get("comments", [])
    total_comments = comment_data.get("total", 0)

    if comments:
        recent = comments[-_MAX_COMMENTS:]
        lines.append(
            f"\n── Comments (latest {len(recent)} of {total_comments}) ──"
        )
        for c in recent:
            author = (c.get("author") or {}).get("displayName", "Unknown")
            date   = (c.get("updated") or c.get("created") or "")[:10]
            body   = _jira_text(c.get("body") or "")[:500]
            lines.append(f"  [{date}] {author}:\n  {body}\n")
    else:
        lines.append("\n── Comments ──\n  (No comments)")

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


def _jira_text(value) -> str:
    """
    Best-effort conversion of a Jira field value to readable plain text.
    Handles: plain string, Jira Document Format (ADF dict), legacy wiki markup.
    """
    if not value:
        return ""
    # ADF (Atlassian Document Format) — common in Jira Cloud and newer DC
    if isinstance(value, dict):
        return _adf_to_text(value)
    text = str(value)
    # Strip common Jira wiki markup: {code}, {panel}, ||, *bold*, _italic_
    import re
    text = re.sub(r"\{[^}]+\}", "", text)          # macros like {code}, {panel}
    text = re.sub(r"\|\|[^|]+", "", text)          # table headers
    text = re.sub(r"[*_]([^*_]+)[*_]", r"\1", text)  # bold/italic
    text = re.sub(r"h[1-6]\. ", "", text)          # headings
    text = re.sub(r"\r\n|\r", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _adf_to_text(node: dict, depth: int = 0) -> str:
    """Recursively extract plain text from an ADF (Atlassian Document Format) node."""
    node_type = node.get("type", "")
    content   = node.get("content", [])
    text_val  = node.get("text", "")

    if node_type == "text":
        return text_val
    if node_type in ("hardBreak", "rule"):
        return "\n"
    if node_type in ("paragraph", "heading", "blockquote"):
        inner = "".join(_adf_to_text(c, depth) for c in content)
        return inner + "\n"
    if node_type in ("bulletList", "orderedList"):
        items = []
        for c in content:
            item_text = "".join(_adf_to_text(cc, depth + 1) for cc in c.get("content", []))
            items.append(f"  {'- ' if node_type == 'bulletList' else '• '}{item_text.strip()}")
        return "\n".join(items) + "\n"
    if node_type == "codeBlock":
        inner = "".join(_adf_to_text(c, depth) for c in content)
        return f"\n```\n{inner}\n```\n"
    # Generic: recurse into content
    return "".join(_adf_to_text(c, depth) for c in content)
