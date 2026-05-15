"""
Tool for saving test suites (with test cases) to the database.

Used by QA agents to persist structured test suites created from MR analysis,
Jira tickets, or manual creation.
"""
import json
import uuid
from datetime import datetime
from web.db.database import SessionLocal
from web.db.models import TestSuite, TestCase


def save_test_suite(
    name: str,
    description: str,
    test_cases: list[dict] = None,
    component: str = "",
    source_type: str = "manual",
    source_ref: str = "",
    jira_key: str = "",
    agent_id: str = None,
    conversation_id: str = None,
    agent_name: str = "",
    trace_id: str = None,
    node_name: str = "",
) -> str:
    """
    Save a test suite with its test cases to the database.

    Args:
        name: Suite name (e.g. "Checkout Flow Tests")
        description: Suite description
        test_cases: List of test case dicts with keys:
                   {title, category, preconditions, steps: list[str], expected, priority}
        source_type: "manual" | "mr" | "jira"
        source_ref: MR URL, MR number, or reference (e.g. "https://gitlab.com/.../-/merge_requests/123")
        jira_key: JIRA ticket key (e.g. "SHOP-1234")
        agent_id: ID of agent creating the suite
        conversation_id: Optional conversation context
        agent_name: Name of agent (for denormalization)
        trace_id: Observability trace ID
        node_name: LangGraph node name

    Returns:
        Success message with suite ID and case count
    """
    if not test_cases:
        return (
            "[Error] test_cases is required and must be a non-empty list. "
            "Please structure all test cases first, then call save_test_suite with the complete list."
        )

    db = SessionLocal()
    try:
        # Create suite
        suite_id = str(uuid.uuid4())
        suite = TestSuite(
            id=suite_id,
            agent_id=agent_id or "",
            agent_name=agent_name or "",
            name=name,
            description=description,
            component=component,
            source_type=source_type,
            source_ref=source_ref,
            jira_key=jira_key,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(suite)
        db.flush()

        # Create test cases
        case_count = 0
        for i, tc_data in enumerate(test_cases):
            case_id = str(uuid.uuid4())

            # Convert steps list to JSON if needed
            steps_json = tc_data.get("steps", [])
            if isinstance(steps_json, list):
                steps_json = json.dumps(steps_json, ensure_ascii=False)

            case = TestCase(
                id=case_id,
                suite_id=suite_id,
                title=tc_data.get("title", "Untitled"),
                category=tc_data.get("category", ""),
                preconditions=tc_data.get("preconditions", ""),
                steps=steps_json,
                expected=tc_data.get("expected", ""),
                priority=tc_data.get("priority", "P1"),
                order_index=i,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            db.add(case)
            case_count += 1

        db.commit()
        return f"Test suite '{name}' saved (ID: {suite_id[:8]}…) with {case_count} test case{'s' if case_count != 1 else ''}"

    except Exception as e:
        db.rollback()
        return f"Error saving test suite: {str(e)[:200]}"
    finally:
        db.close()
