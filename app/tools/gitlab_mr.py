"""
Tool: Fetch GitLab Merge Request diff and recommend regression test scope.

Risk Level: L1 (self-execution, read-only)
Auth: GitLab Private Token  (Header: PRIVATE-TOKEN: <token>)
API:  GitLab REST API v4
  GET /api/v4/projects/:encoded_path/merge_requests/:iid/changes
  (uses /changes instead of /diffs — works on all GitLab versions including older self-hosted)

Typical workflow:
  1. QA calls get_jira_issue(ticket_key) to read Jira ticket
  2. Agent extracts GitLab MR URL(s) from description / comments
  3. Agent calls get_gitlab_mr_diff(mr_url) for each URL
  4. Agent synthesizes changed modules → regression scope recommendation

Prerequisites: Configure GITLAB_BASE_URL / GITLAB_API_TOKEN in .env
"""
import re
import urllib.parse

import requests

from config import GITLAB_API_TOKEN, GITLAB_BASE_URL

# Maximum number of diff lines to include per file (keeps LLM context manageable)
_MAX_DIFF_LINES_PER_FILE = 60
# Maximum number of files to show full diff for (rest get stat-only)
_MAX_FILES_WITH_DIFF     = 10
# Maximum total files to list
_MAX_FILES_TOTAL         = 80

# ── File-path → module / test-area heuristics ────────────────────────────────
# Each entry: (regex pattern, module label, suggested test types)
_MODULE_HINTS = [
    # Infrastructure / config
    (r"\.(ya?ml|toml|ini|cfg|env)$",         "Config / Infrastructure",  ["Config change regression", "Environment smoke test"]),
    (r"(docker|k8s|helm|terraform|deploy)",   "Deployment / Infra",       ["Deployment smoke test"]),
    # Database
    (r"(migration|schema|flyway|liquibase)",  "Database Migration",       ["DB migration test", "Data integrity check"]),
    (r"\.(sql)$",                             "Database",                 ["DB query regression"]),
    # API / backend
    (r"(controller|router|handler|api|rest)", "API Layer",                ["API integration test", "Contract test"]),
    (r"(service|usecase|domain|business)",    "Business Logic",           ["Unit test", "Integration test"]),
    (r"(repository|dao|mapper|store)",        "Data Access Layer",        ["Repository unit test", "DB integration test"]),
    (r"(middleware|interceptor|filter)",      "Middleware",               ["Middleware regression", "Auth/permission test"]),
    # Messaging / async
    (r"(consumer|producer|kafka|mq|event)",  "Messaging / Event",        ["Message queue integration test", "Async flow test"]),
    # Frontend
    (r"\.(jsx?|tsx?|vue|html|css|scss)$",    "Frontend",                 ["UI regression test", "E2E test"]),
    # Tests themselves
    (r"(test|spec|mock|fixture|stub)",        "Test Code",                ["Review test coverage"]),
]


def get_gitlab_mr_diff(mr_url: str) -> str:
    """
    Fetch the diff of a GitLab Merge Request and return a structured
    summary of changed files with regression scope recommendations.

    Args:
        mr_url: Full GitLab MR URL.
                Example: https://gitlab.yourcompany.com/group/project/-/merge_requests/42

    Returns:
        MR metadata + changed file list grouped by module + regression recommendations.
    """
    if not _check_config():
        return (
            "[GitLab Not Configured] Please set the following variables in .env:\n"
            "  GITLAB_BASE_URL=https://gitlab.yourcompany.com\n"
            "  GITLAB_API_TOKEN=your_private_token"
        )

    # ── Parse URL ─────────────────────────────────────────────────────────────
    parsed = _parse_mr_url(mr_url)
    if parsed is None:
        return (
            f"[Error] Cannot parse GitLab MR URL: {mr_url}\n"
            "Expected format: https://gitlab.company.com/group/project/-/merge_requests/123"
        )
    base_url, project_path, mr_iid = parsed
    encoded_path = urllib.parse.quote(project_path, safe="")

    # ── Fetch MR metadata + diffs in one call ────────────────────────────────
    # Use /changes endpoint (available on all GitLab versions, incl. self-hosted).
    # /diffs was introduced in GitLab 15.7 and may 404 on older instances.
    mr_data = _api_get(
        base_url,
        f"/api/v4/projects/{encoded_path}/merge_requests/{mr_iid}/changes",
    )
    if isinstance(mr_data, str):   # error string returned by _api_get
        return mr_data

    title       = mr_data.get("title", "")
    state       = mr_data.get("state", "")
    author      = (mr_data.get("author") or {}).get("name", "")
    source_br   = mr_data.get("source_branch", "")
    target_br   = mr_data.get("target_branch", "")
    mr_link     = mr_data.get("web_url", mr_url)
    description = (mr_data.get("description") or "").strip()[:500]
    file_diffs  = mr_data.get("changes", [])
    total_files = len(file_diffs)

    # ── Build output ──────────────────────────────────────────────────────────
    lines = [
        f"【GitLab MR Diff: {project_path}!{mr_iid}】",
        f"  Title   : {title}",
        f"  State   : {state}",
        f"  Author  : {author}",
        f"  Branch  : {source_br} → {target_br}",
        f"  Link    : {mr_link}",
    ]
    if description:
        lines.append(f"  Desc    : {description[:300]}{'…' if len(description) > 300 else ''}")
    lines.append(f"\n── Changed Files ({total_files} total) ──")

    # Group files by detected module
    module_map: dict[str, list[dict]] = {}   # module_label → list of file info
    for fd in file_diffs[:_MAX_FILES_TOTAL]:
        path       = fd.get("new_path") or fd.get("old_path", "unknown")
        is_new     = fd.get("new_file", False)
        is_deleted = fd.get("deleted_file", False)
        is_renamed = fd.get("renamed_file", False)
        diff_text  = fd.get("diff", "")

        if is_new:
            change_type = "ADDED"
        elif is_deleted:
            change_type = "DELETED"
        elif is_renamed:
            old_path = fd.get("old_path", "")
            change_type = f"RENAMED from {old_path}"
        else:
            change_type = "MODIFIED"

        # Count diff stats
        added_lines   = diff_text.count("\n+") if diff_text else 0
        removed_lines = diff_text.count("\n-") if diff_text else 0

        label = _detect_module(path)
        module_map.setdefault(label, []).append({
            "path":    path,
            "type":    change_type,
            "added":   added_lines,
            "removed": removed_lines,
            "diff":    diff_text,
        })

    # Print files grouped by module
    diff_count = 0
    for module_label, files in sorted(module_map.items()):
        lines.append(f"\n  📁 {module_label}")
        for f in files:
            stat = f"+{f['added']} -{f['removed']}"
            lines.append(f"    [{f['type']}] {f['path']}  ({stat})")
            # Show diff excerpt for first N files
            if diff_count < _MAX_FILES_WITH_DIFF and f["diff"]:
                excerpt = _trim_diff(f["diff"])
                if excerpt:
                    lines.append(f"    ```diff\n{excerpt}\n    ```")
                diff_count += 1

    # ── Regression scope recommendations ─────────────────────────────────────
    lines.append("\n── Regression Scope Recommendations ──")
    recommendations: dict[str, set] = {}   # module → test types

    for module_label, files in module_map.items():
        test_types = _test_types_for_module(module_label, [f["path"] for f in files])
        if test_types:
            recommendations[module_label] = test_types

    if recommendations:
        for module_label, test_types in sorted(recommendations.items()):
            lines.append(f"  • {module_label}:")
            for t in sorted(test_types):
                lines.append(f"      - {t}")
    else:
        lines.append("  (Unable to infer test scope from file paths alone — manual review recommended)")

    lines.append(
        "\n💡 Tip: Review the changed files above and cross-reference with your existing "
        "test cases to finalize the regression run list."
    )

    return "\n".join(lines)


# ── Internal helpers ───────────────────────────────────────────────────────────

def _check_config() -> bool:
    return bool(GITLAB_BASE_URL and GITLAB_API_TOKEN)


def _parse_mr_url(url: str):
    """
    Parse a GitLab MR URL into (base_url, project_path, mr_iid).
    Supports:
      https://gitlab.company.com/group/project/-/merge_requests/42
      https://gitlab.company.com/group/sub/project/-/merge_requests/42
    Returns None if pattern does not match.
    """
    # Normalize: remove trailing slash
    url = url.strip().rstrip("/")
    match = re.match(
        r"(https?://[^/]+)/(.+?)/-/merge_requests/(\d+)",
        url,
    )
    if not match:
        return None
    base_url     = match.group(1)
    project_path = match.group(2)
    mr_iid       = int(match.group(3))
    return base_url, project_path, mr_iid


def _api_get(base_url: str, path: str, params: dict = None):
    """Make an authenticated GET request to the GitLab API. Returns parsed JSON or error string."""
    url = f"{base_url.rstrip('/')}{path}"
    headers = {"PRIVATE-TOKEN": GITLAB_API_TOKEN}
    try:
        resp = requests.get(url, headers=headers, params=params or {}, timeout=20)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.ConnectionError:
        return f"[Error] Cannot connect to GitLab: {base_url}. Check GITLAB_BASE_URL."
    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response else "?"
        if status == 401:
            return "[Error] GitLab authentication failed (401). Check GITLAB_API_TOKEN."
        if status == 403:
            return "[Error] No permission to access this GitLab project (403)."
        if status == 404:
            return f"[Error] MR or project not found (404). Check the URL: {url}"
        return f"[Error] GitLab API returned HTTP {status}: {e}"
    except requests.exceptions.Timeout:
        return "[Error] GitLab request timed out (20s)."
    except Exception as e:
        return f"[Error] GitLab API call failed: {e}"


def _detect_module(file_path: str) -> str:
    """Map a file path to a human-readable module label using heuristics."""
    path_lower = file_path.lower()
    for pattern, label, _ in _MODULE_HINTS:
        if re.search(pattern, path_lower):
            return label
    # Fall back to top-level directory
    parts = file_path.split("/")
    if len(parts) > 1:
        return f"Module: {parts[0]}"
    return "Other"


def _test_types_for_module(module_label: str, file_paths: list[str]) -> set[str]:
    """Return a set of recommended test types for the given module."""
    result = set()
    for path in file_paths:
        path_lower = path.lower()
        for pattern, label, test_types in _MODULE_HINTS:
            if label == module_label and re.search(pattern, path_lower):
                result.update(test_types)
    return result


def _trim_diff(diff_text: str) -> str:
    """Trim diff to a readable excerpt, keeping the first N meaningful lines."""
    lines = diff_text.split("\n")
    # Skip binary diffs
    if any("Binary files" in l for l in lines[:5]):
        return "  (binary file, diff not shown)"
    kept = []
    for line in lines[:_MAX_DIFF_LINES_PER_FILE]:
        kept.append("    " + line)
    if len(lines) > _MAX_DIFF_LINES_PER_FILE:
        kept.append(f"    … ({len(lines) - _MAX_DIFF_LINES_PER_FILE} more lines)")
    return "\n".join(kept)
