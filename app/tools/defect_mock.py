"""
Tool: Sandbox Defect Management System Mock (L2, requires Mentor approval).

This is a pure Mock implementation that writes defects to a local JSON file,
simulating the API behavior of a real defect management system (like Jira).
When replacing with production scenario, only need to modify implementation in this file, interface definition unchanged.
"""
import json
import os
import uuid
from datetime import datetime

_MOCK_DB_PATH = os.path.join(
    os.path.dirname(__file__), "..", "eval", "mock_defects.json"
)


def _load_db() -> list[dict]:
    if not os.path.exists(_MOCK_DB_PATH):
        return []
    with open(_MOCK_DB_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_db(records: list[dict]) -> None:
    os.makedirs(os.path.dirname(_MOCK_DB_PATH), exist_ok=True)
    with open(_MOCK_DB_PATH, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)


def create_defect_mock(
    title: str,
    description: str,
    severity: str,
    module: str = "Unspecified",
) -> str:
    """
    Create a defect record in the sandbox defect system (Mock).

    Args:
        title:       Defect title
        description: Defect description
        severity:    Severity level (P0/P1/P2/P3)
        module:      Module name

    Returns:
        Creation result, containing defect ID.
    """
    defect_id = f"MOCK-{uuid.uuid4().hex[:6].upper()}"
    record = {
        "id":          defect_id,
        "title":       title,
        "description": description,
        "severity":    severity,
        "module":      module,
        "status":      "Pending Confirmation",
        "created_by":  "de-qa-001",
        "created_at":  datetime.now().isoformat(),
    }

    records = _load_db()
    records.append(record)
    _save_db(records)

    return (
        f"[Sandbox Defect System] Defect created\n"
        f"  ID: {defect_id}\n"
        f"  Title: {title}\n"
        f"  Severity: {severity}\n"
        f"  Status: Pending Confirmation (requires human QA review)"
    )


def list_defects_mock() -> list[dict]:
    """Return all Mock defect records (for eval script viewing)."""
    return _load_db()
