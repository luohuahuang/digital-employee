"""
Tool: Create a real Jira issue via the REST API v2.

Risk Level: L2 (requires Mentor approval before execution)
Auth: Jira Data Center / Server — Personal Access Token (Bearer)
     Jira Cloud — Basic Auth (email + API token)
API: Jira REST API v2  POST /rest/api/2/issue

Typical use cases:
  - QA agent discovers a defect during testing → creates issue directly in Jira
  - Create subtasks or related issues for defect tracking
  - Log test failures with structured steps and results

Prerequisites: Configure JIRA_BASE_URL, JIRA_API_TOKEN in .env
"""
import base64
import requests

from config import (
    JIRA_AUTH_TYPE,
    JIRA_BASE_URL,
    JIRA_USERNAME,
    JIRA_API_TOKEN,
    DEFAULT_JIRA_PROJECT,
)
from tools.audit_logger import log_tool_call

_CREATE_ENDPOINT = "/rest/api/2/issue"

# Valid Jira field values
_VALID_ISSUE_TYPES = {"Bug", "Task", "Story", "Improvement"}
_VALID_PRIORITIES = {"Blocker", "Critical", "Major", "Medium", "Minor"}


def create_jira_issue(
    summary: str,
    description: str,
    issue_type: str = "Bug",
    priority: str = "Medium",
    project_key: str = "",
    labels: list[str] = None,
    components: list[str] = None,
    affected_version: str = "",
    steps_to_reproduce: str = "",
    expected_result: str = "",
    actual_result: str = "",
    agent_id: str = None,
    conversation_id: str = None,
    agent_name: str = "",
    trace_id: str = None,
    node_name: str = "",
) -> str:
    """
    Create a real Jira issue via the REST API v2.

    Args:
        summary:           Issue title (required)
        description:       Issue description (required)
        issue_type:        Bug | Task | Story | Improvement (default: Bug)
        priority:          Blocker | Critical | Major | Medium | Minor (default: Medium)
        project_key:       Jira project key, e.g. "SHOP", "QA" (falls back to DEFAULT_JIRA_PROJECT)
        labels:            List of labels to attach, e.g. ["regression", "payment"]
        components:        List of component names, e.g. ["Checkout", "Payment"]
        affected_version:  Version string affected by this bug, e.g. "2.3.0"
        steps_to_reproduce: Detailed steps to reproduce the issue
        expected_result:   What should happen (for bugs)
        actual_result:     What actually happened (for bugs)
        agent_id:          ID of the agent creating the issue (for audit)
        conversation_id:   ID of the current conversation (for audit)
        agent_name:        Display name of the agent (for audit and Jira description)
        trace_id:          Trace ID for observability
        node_name:         LangGraph node name

    Returns:
        Success message with issue key and URL, or error message.
    """
    if not _check_config():
        return (
            "[Jira Not Configured] Please set the following variables in .env:\n"
            "  JIRA_BASE_URL=https://jira.yourcompany.com\n"
            "  JIRA_API_TOKEN=your_api_token\n"
            "  JIRA_AUTH_TYPE=pat (or basic for Jira Cloud)\n"
            "  DEFAULT_JIRA_PROJECT=SHOP (or your project key)"
        )

    # Validate inputs
    if not summary or not summary.strip():
        return "[Error] 'summary' is required and cannot be empty."
    if not description or not description.strip():
        return "[Error] 'description' is required and cannot be empty."
    if issue_type not in _VALID_ISSUE_TYPES:
        return f"[Error] Invalid issue_type '{issue_type}'. Valid values: {', '.join(_VALID_ISSUE_TYPES)}"
    if priority not in _VALID_PRIORITIES:
        return f"[Error] Invalid priority '{priority}'. Valid values: {', '.join(_VALID_PRIORITIES)}"

    # Resolve project key
    final_project_key = project_key.strip() if project_key else DEFAULT_JIRA_PROJECT
    if not final_project_key:
        return (
            "[Error] No project_key provided and DEFAULT_JIRA_PROJECT not configured. "
            "Set project_key parameter or DEFAULT_JIRA_PROJECT in .env"
        )

    # Build the issue payload in Jira v2 format
    payload = _build_jira_payload(
        summary=summary,
        description=description,
        issue_type=issue_type,
        priority=priority,
        project_key=final_project_key,
        labels=labels,
        components=components,
        affected_version=affected_version,
        steps_to_reproduce=steps_to_reproduce,
        expected_result=expected_result,
        actual_result=actual_result,
        agent_name=agent_name,
    )

    url = f"{JIRA_BASE_URL.rstrip('/')}{_CREATE_ENDPOINT}"

    try:
        response = requests.post(
            url, json=payload, timeout=15, **_auth_kwargs()
        )
        response.raise_for_status()
    except requests.exceptions.ConnectionError:
        return f"[Error] Cannot connect to Jira: {JIRA_BASE_URL}. Check network or URL."
    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response else "?"
        resp_text = ""
        try:
            error_data = e.response.json() if e.response else {}
            resp_text = error_data.get("errorMessages", [])
            if isinstance(resp_text, list):
                resp_text = "; ".join(resp_text)
        except Exception:
            resp_text = e.response.text if e.response else ""

        if status == 400:
            return (
                f"[Error] Invalid request (400). Check field names and values.\n"
                f"Details: {resp_text}"
            )
        if status == 401:
            return (
                "[Error] Jira authentication failed (401). "
                "Please verify JIRA_API_TOKEN and JIRA_AUTH_TYPE are correct."
            )
        if status == 403:
            return (
                "[Error] No permission to create issues in project {final_project_key} (403). "
                "Contact your Jira admin."
            )
        if status == 404:
            return (
                f"[Error] Project '{final_project_key}' not found (404). "
                "Check the project key."
            )
        if status == 422:
            return (
                f"[Error] Unprocessable request (422). "
                f"This often means required fields are missing or invalid.\n"
                f"Details: {resp_text}"
            )
        return f"[Error] Jira API returned HTTP {status}: {resp_text or str(e)}"
    except requests.exceptions.Timeout:
        return "[Error] Jira request timed out (15s). Check your network connection."
    except Exception as e:
        return f"[Error] Jira issue creation failed: {e}"

    # Success: extract issue key and build response
    try:
        data = response.json()
        issue_key = data.get("key", "")
        issue_id = data.get("id", "")

        if not issue_key:
            return "[Error] Jira returned success but no issue key. Response: " + str(data)

        base_url = JIRA_BASE_URL.rstrip("/")
        issue_url = f"{base_url}/browse/{issue_key}"

        success_msg = (
            f"[Jira Issue Created]\n"
            f"  Key: {issue_key}\n"
            f"  Type: {issue_type}\n"
            f"  Priority: {priority}\n"
            f"  Project: {final_project_key}\n"
            f"  Link: {issue_url}"
        )

        return success_msg
    except Exception as e:
        return (
            f"[Warning] Issue may have been created, but response parsing failed: {e}\n"
            f"Response: {response.text[:200]}"
        )


# ── Internal helpers ───────────────────────────────────────────────────────────

def _check_config() -> bool:
    return bool(JIRA_BASE_URL and JIRA_API_TOKEN)


def _auth_kwargs() -> dict:
    """
    Return appropriate auth kwargs based on JIRA_AUTH_TYPE.

    pat   → Jira Data Center / Server: Authorization: Bearer <token>
    basic → Jira Cloud: HTTP Basic (username:token base64 encoded)
    """
    if JIRA_AUTH_TYPE == "basic":
        return {"auth": (JIRA_USERNAME, JIRA_API_TOKEN)}
    # Default: PAT (Personal Access Token)
    return {"headers": {"Authorization": f"Bearer {JIRA_API_TOKEN}"}}


def _build_jira_payload(
    summary: str,
    description: str,
    issue_type: str,
    priority: str,
    project_key: str,
    labels: list[str],
    components: list[str],
    affected_version: str,
    steps_to_reproduce: str,
    expected_result: str,
    actual_result: str,
    agent_name: str,
) -> dict:
    """
    Build a Jira v2 issue creation payload.
    Description uses Jira wiki markup format.
    """
    # Format description with wiki markup
    desc_parts = [description]

    if steps_to_reproduce and steps_to_reproduce.strip():
        desc_parts.append("\nh3. Steps to Reproduce\n")
        steps_lines = steps_to_reproduce.strip().split("\n")
        for i, step in enumerate(steps_lines, 1):
            desc_parts.append(f"# {step}\n")

    if expected_result and expected_result.strip():
        desc_parts.append("\nh3. Expected Result\n")
        desc_parts.append(expected_result.strip() + "\n")

    if actual_result and actual_result.strip():
        desc_parts.append("\nh3. Actual Result\n")
        desc_parts.append(actual_result.strip() + "\n")

    if agent_name:
        desc_parts.append(f"\n_Created by Digital QA Employee: {agent_name}_\n")

    full_description = "".join(desc_parts)

    # Build fields object
    fields = {
        "project": {"key": project_key},
        "summary": summary,
        "description": full_description,
        "issuetype": {"name": issue_type},
        "priority": {"name": priority},
    }

    # Add optional fields
    if labels:
        fields["labels"] = [l.strip() for l in labels if l.strip()]

    if components:
        fields["components"] = [{"name": c.strip()} for c in components if c.strip()]

    if affected_version and affected_version.strip():
        fields["affectedVersions"] = [{"name": affected_version.strip()}]

    return {"fields": fields}
