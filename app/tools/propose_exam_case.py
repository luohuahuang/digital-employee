"""
Tool: Propose an exam case as a structured YAML draft.

Risk Level: L1 (self-execution; writes only to drafts/ subdirectory)

Used when an agent analyzes a production failure or test scenario and wants to
propose it as an exam case for the digital employee platform.

The tool:
1. Validates input (criteria weights, difficulty level, etc.)
2. Serializes the exam case as YAML
3. Saves to exams/drafts/{exam_id}.yaml
4. Returns the YAML content with a DRAFT_ID marker for frontend detection
"""
import os
import yaml
from pathlib import Path


def propose_exam_case(
    exam_id: str,
    skill: str,
    scenario: str,
    difficulty: str,
    input_message: str,
    expected_keywords: list = None,
    criteria: list = None,
    mentor_criteria: list = None,
    auto_score_weight: float = 0.40,
    mentor_score_weight: float = 0.60,
    pass_threshold: int = 75,
    origin: str = "production_failure",
    tags: list = None,
    role: str = "QA",
    agent_id: str = None,
    conversation_id: str = None,
    agent_name: str = "",
    trace_id: str = None,
    node_name: str = "",
) -> str:
    """
    Propose an exam case and save as a draft.

    Args:
        exam_id:               Unique exam identifier (e.g. "qa-checkout-refund-edge-001")
        skill:                 Skill being tested (e.g. "defect_analysis", "test_case_design")
        scenario:              One-sentence scenario description
        difficulty:            L1 | L2 | L3
        input_message:         The prompt/question for the exam
        expected_keywords:     List of keywords for auto-scoring
        criteria:              List of rubric criteria dicts with id, description, weight, rubric
        mentor_criteria:       List of human judgment checklist items
        auto_score_weight:     Weight for keyword matching (0.0-1.0)
        mentor_score_weight:   Weight for mentor scoring (0.0-1.0)
        pass_threshold:        Pass score threshold (0-100)
        origin:                "production_failure" | "designed"
        tags:                  Optional tags for categorization
        role:                  QA | Dev | PM | SRE | PJ
        agent_id:              (Metadata) ID of agent proposing
        conversation_id:       (Metadata) ID of conversation
        agent_name:            (Metadata) Name of agent proposing
        trace_id:              (Metadata) Trace ID for audit
        node_name:             (Metadata) Node name for audit

    Returns:
        String with YAML content and DRAFT_ID marker
    """
    # Defaults
    if expected_keywords is None:
        expected_keywords = []
    if mentor_criteria is None:
        mentor_criteria = []
    if criteria is None:
        criteria = []
    if tags is None:
        tags = []

    # Validation
    errors = []

    if not exam_id or not isinstance(exam_id, str):
        errors.append("exam_id must be a non-empty string")

    if difficulty not in ("L1", "L2", "L3"):
        errors.append(f"difficulty must be L1, L2, or L3 (got {difficulty})")

    if not skill or not isinstance(skill, str):
        errors.append("skill must be a non-empty string")

    if not scenario or not isinstance(scenario, str):
        errors.append("scenario must be a non-empty string")

    if not input_message or not isinstance(input_message, str):
        errors.append("input_message must be a non-empty string")

    # Validate weights
    weight_sum = auto_score_weight + mentor_score_weight
    if not (0.99 <= weight_sum <= 1.01):
        errors.append(
            f"auto_score_weight + mentor_score_weight must sum to 1.0 (got {weight_sum:.2f})"
        )

    if auto_score_weight < 0 or auto_score_weight > 1:
        errors.append("auto_score_weight must be between 0.0 and 1.0")

    if mentor_score_weight < 0 or mentor_score_weight > 1:
        errors.append("mentor_score_weight must be between 0.0 and 1.0")

    if pass_threshold < 0 or pass_threshold > 100:
        errors.append("pass_threshold must be between 0 and 100")

    # Validate criteria weights sum to 1.0 if provided
    if criteria:
        crit_weight_sum = sum(c.get("weight", 0) for c in criteria)
        if not (0.99 <= crit_weight_sum <= 1.01):
            errors.append(
                f"criteria weights must sum to 1.0 (got {crit_weight_sum:.2f})"
            )

    if origin not in ("production_failure", "designed"):
        errors.append("origin must be 'production_failure' or 'designed'")

    if role not in ("QA", "Dev", "PM", "SRE", "PJ"):
        errors.append("role must be one of: QA, Dev, PM, SRE, PJ")

    if errors:
        return f"[Error] Validation failed:\n" + "\n".join(f"  - {e}" for e in errors)

    # Build YAML content
    data = {
        "id": exam_id,
        "role": role,
        "skill": skill,
        "scenario": scenario,
        "difficulty": difficulty,
        "origin": origin,
    }

    if tags:
        data["tags"] = tags

    data["input"] = {"message": input_message}

    if expected_keywords:
        data["expected_keywords"] = expected_keywords

    if criteria:
        data["criteria"] = criteria

    if mentor_criteria:
        data["mentor_criteria"] = mentor_criteria

    data["auto_score_weight"] = auto_score_weight
    data["mentor_score_weight"] = mentor_score_weight
    data["pass_threshold"] = pass_threshold

    yaml_content = yaml.dump(
        data,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
    )

    # Ensure drafts/ directory exists
    app_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    drafts_dir = os.path.join(app_root, "exams", "drafts")
    os.makedirs(drafts_dir, exist_ok=True)

    # Save draft
    draft_path = os.path.join(drafts_dir, f"{exam_id}.yaml")
    try:
        with open(draft_path, "w", encoding="utf-8") as f:
            f.write(yaml_content)
    except Exception as e:
        return f"[Error] Failed to save draft: {e}"

    # Return formatted output with DRAFT_ID marker for frontend detection
    output = f"""✅ Exam case draft saved: {exam_id}

--- EXAM CASE DRAFT ---
{yaml_content}--- END DRAFT ---

DRAFT_ID:{exam_id}"""

    return output
