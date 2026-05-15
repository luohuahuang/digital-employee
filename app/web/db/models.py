"""SQLAlchemy ORM models for Digital Employee web platform."""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Text, Boolean, DateTime, Integer, Float, ForeignKey
from web.db.database import Base


def _uuid():
    return str(uuid.uuid4())


class Agent(Base):
    __tablename__ = "agents"

    id              = Column(String, primary_key=True, default=_uuid)
    name            = Column(String, nullable=False)
    product_line    = Column(String, nullable=False)   # e.g. "promotion", "checkout"
    avatar_emoji    = Column(String, default="🤖")
    description     = Column(Text, default="")
    specialization  = Column(Text, default="")         # Domain-specific prompt injection
    default_jira_project = Column(String, default="")
    confluence_spaces    = Column(Text, default="[]")  # JSON array of space keys
    ranking         = Column(String, default="Intern")  # Intern | Junior | Senior | Lead
    role            = Column(String, default="QA")      # QA | Dev | PM | SRE | PJ
    created_at      = Column(DateTime, default=datetime.utcnow)
    is_active       = Column(Boolean, default=True)
    offboarded_at   = Column(DateTime, nullable=True)   # set when offboarded, null = active


class Conversation(Base):
    __tablename__ = "conversations"

    id         = Column(String, primary_key=True, default=_uuid)
    agent_id   = Column(String, ForeignKey("agents.id"), nullable=False)
    title      = Column(String, default="New Conversation")
    created_at = Column(DateTime, default=datetime.utcnow)


class Message(Base):
    __tablename__ = "messages"

    id              = Column(String, primary_key=True, default=_uuid)
    conversation_id = Column(String, ForeignKey("conversations.id"), nullable=False)
    role            = Column(String, nullable=False)  # user | assistant | tool
    content         = Column(Text, default="")
    tool_calls_json = Column(Text, default="")        # JSON: list of {name, args, result}
    created_at      = Column(DateTime, default=datetime.utcnow)


class ExamRun(Base):
    """
    One row per exam execution.  Auto-scoring is written on completion;
    mentor_score / total_score are updated when the Mentor submits scores.
    """
    __tablename__ = "exam_runs"

    id              = Column(String, primary_key=True, default=_uuid)
    agent_id        = Column(String, ForeignKey("agents.id"), nullable=False)
    agent_name      = Column(String, nullable=False)
    exam_file       = Column(String, nullable=False)     # e.g. "tc_design_001.yaml"
    exam_id         = Column(String, nullable=True)      # id field inside the YAML
    skill           = Column(String, nullable=True)
    difficulty      = Column(String, nullable=True)
    status          = Column(String, default="running")  # running | done | error
    auto_score      = Column(Float, nullable=True)       # 0–100, auto keyword hit score
    auto_weight     = Column(Float, nullable=True)       # weight from YAML
    mentor_score    = Column(Float, nullable=True)       # 0–100, null until Mentor submits
    mentor_weight   = Column(Float, nullable=True)
    total_score     = Column(Float, nullable=True)       # weighted sum; partial until mentor fills in
    threshold       = Column(Integer, nullable=True)
    passed          = Column(Boolean, nullable=True)     # null = pending mentor scoring
    missed_keywords_json  = Column(Text, nullable=True)  # JSON list of missed keywords
    mentor_criteria_json  = Column(Text, nullable=True)  # JSON list of criterion strings
    mentor_scores_json    = Column(Text, nullable=True)  # JSON dict {criterion: 0.0–1.0}
    output              = Column(Text, nullable=True)        # agent's full response text
    elapsed_sec         = Column(Float, nullable=True)
    error_msg           = Column(Text, nullable=True)
    prompt_version_id   = Column(String, nullable=True)   # which prompt version was active
    prompt_version_num  = Column(Integer, nullable=True)  # version number (for display)
    judge_results_json  = Column(Text, nullable=True)     # JSON: {criterion: {score:0-3, evidence, reasoning}}
    rules_result_json   = Column(Text, nullable=True)     # JSON: [{rule, passed, message}]
    created_at          = Column(DateTime, default=datetime.utcnow)


class GroupChat(Base):
    """A group chat session with multiple QA agents."""
    __tablename__ = "group_chats"

    id         = Column(String, primary_key=True, default=_uuid)
    title      = Column(String, default="New Group Chat")
    created_at = Column(DateTime, default=datetime.utcnow)


class GroupMembership(Base):
    """Many-to-many: which agents are in which group chat."""
    __tablename__ = "group_memberships"

    id         = Column(String, primary_key=True, default=_uuid)
    group_id   = Column(String, ForeignKey("group_chats.id"), nullable=False)
    agent_id   = Column(String, ForeignKey("agents.id"), nullable=False)
    joined_at  = Column(DateTime, default=datetime.utcnow)


class GroupMessage(Base):
    """A message in a group chat (user or agent)."""
    __tablename__ = "group_messages"

    id            = Column(String, primary_key=True, default=_uuid)
    group_id      = Column(String, ForeignKey("group_chats.id"), nullable=False)
    speaker_type  = Column(String, nullable=False)   # "user" | "agent"
    speaker_id    = Column(String, nullable=True)    # agent_id for agent messages
    speaker_name  = Column(String, nullable=True)
    speaker_emoji = Column(String, nullable=True)
    content       = Column(Text, nullable=False, default="")
    is_pass       = Column(Boolean, default=False)
    created_at    = Column(DateTime, default=datetime.utcnow)


class PromptVersion(Base):
    """
    Versioned system prompt per Agent.
    Each save creates a new row; only one row per agent has is_active=True.
    """
    __tablename__ = "prompt_versions"

    id         = Column(String, primary_key=True, default=_uuid)
    agent_id   = Column(String, ForeignKey("agents.id"), nullable=False)
    type       = Column(String, default="base")    # "base" | "specialization"
    version    = Column(Integer, nullable=False)   # 1, 2, 3 … auto-incremented per agent+type
    content    = Column(Text, nullable=False)       # full prompt text
    note       = Column(String, default="")        # optional change description
    is_active  = Column(Boolean, default=False)    # only one active per agent+type
    created_at = Column(DateTime, default=datetime.utcnow)


class PromptSuggestion(Base):
    """
    Prompt improvement suggestion derived from a failed exam run.
    Generated by eval/suggester.py; Mentor reviews and can apply with one click.
    """
    __tablename__ = "prompt_suggestions"

    id                 = Column(String, primary_key=True, default=_uuid)
    run_id             = Column(String, ForeignKey("exam_runs.id"), nullable=False)
    agent_id           = Column(String, nullable=False)
    prompt_version_id  = Column(String, nullable=True)   # version that was analyzed
    diagnosis          = Column(Text, default="")
    suggestions_json   = Column(Text, default="[]")      # [{id, point, rationale, patch}]
    patched_prompt     = Column(Text, default="")        # full revised prompt text
    applied            = Column(Boolean, default=False)
    applied_version_id = Column(String, nullable=True)   # PromptVersion.id created on apply
    created_at         = Column(DateTime, default=datetime.utcnow)


class ToolRiskConfig(Base):
    """Configurable tool risk levels (L1/L2/L3), overrides hardcoded TOOL_RISK_LEVEL."""
    __tablename__ = "tool_risk_config"

    tool_name  = Column(String, primary_key=True)
    risk_level = Column(String, nullable=False, default="L1")  # L1 | L2 | L3
    updated_at = Column(DateTime, default=datetime.utcnow)


class RankingCeilingConfig(Base):
    """Configurable permission ceilings per ranking, overrides hardcoded _RANKING_CEILING."""
    __tablename__ = "ranking_ceiling_config"

    ranking    = Column(String, primary_key=True)  # Intern | Junior | Senior | Lead
    ceiling    = Column(String, nullable=False, default="L1")  # L1 | L2 | L3
    updated_at = Column(DateTime, default=datetime.utcnow)


class RolePromptTemplate(Base):
    """
    One row per role (QA/Dev/PM/SRE/PJ).
    Stores the editable base prompt template used to seed new agents of that role.
    """
    __tablename__ = "role_prompt_templates"

    role       = Column(String, primary_key=True)   # QA | Dev | PM | SRE | PJ
    content    = Column(Text, nullable=False, default="")
    updated_at = Column(DateTime, default=datetime.utcnow)


class AuditLog(Base):
    """
    Immutable audit trail of every tool call and L2 decision made by any Agent.
    Used for QA Lead review and ROI reporting.
    Full retention (no automatic pruning).

    Observability fields (added in V2):
      trace_id       — groups all log entries from a single chat turn (P0 chain tracing)
      node_name      — which LangGraph node emitted this entry (P0)
      extra_data_json — structured extra metrics, e.g. KB retrieval stats (P3) or quality score (P2)
    """
    __tablename__ = "audit_logs"

    id              = Column(String, primary_key=True, default=_uuid)
    agent_id        = Column(String, nullable=False)    # which agent
    agent_name      = Column(String, nullable=False)    # denormalised for fast queries
    conversation_id = Column(String, nullable=True)     # null when called from terminal
    event_type      = Column(String, nullable=False)    # "tool_call" | "l2_decision" | "llm_call" | "quality_score"
    tool_name       = Column(String, nullable=True)
    tool_args_json  = Column(Text, nullable=True)       # full args as JSON
    result_preview  = Column(Text, nullable=True)       # first 300 chars of result
    duration_ms     = Column(Integer, nullable=True)    # wall-clock time in ms
    success         = Column(Boolean, default=True)
    error_msg       = Column(Text, nullable=True)
    l2_approved     = Column(Boolean, nullable=True)    # only for l2_decision events
    input_tokens    = Column(Integer, nullable=True)    # LLM input token count
    output_tokens   = Column(Integer, nullable=True)    # LLM output token count
    # ── V2 observability columns ───────────────────────────────────────────────
    trace_id        = Column(String, nullable=True)     # groups entries in one chat turn
    node_name       = Column(String, nullable=True)     # LangGraph node: "agent"|"tools"|"human_review"
    extra_data_json = Column(Text, nullable=True)       # JSON: KB stats, quality score, etc.
    created_at      = Column(DateTime, default=datetime.utcnow)


class TestSuite(Base):
    """Test suite created by QA agent from MR analysis or manual creation."""
    __tablename__ = "test_suites"

    id           = Column(String, primary_key=True, default=_uuid)
    agent_id     = Column(String, ForeignKey("agents.id"), nullable=False)
    agent_name   = Column(String, default="")
    name         = Column(String, nullable=False)
    description  = Column(Text, default="")
    source_type  = Column(String, default="manual")  # manual | mr | jira
    source_ref   = Column(String, default="")        # MR URL or MR number
    jira_key     = Column(String, default="")        # e.g. "SHOP-1234"
    component    = Column(String, default="")        # business component, e.g. "Promotion", "Checkout"
    created_at   = Column(DateTime, default=datetime.utcnow)
    updated_at   = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TestCase(Base):
    """Individual test case within a test suite."""
    __tablename__ = "test_cases"

    id            = Column(String, primary_key=True, default=_uuid)
    suite_id      = Column(String, ForeignKey("test_suites.id"), nullable=False)
    title         = Column(String, nullable=False)
    category      = Column(String, default="")       # e.g. "Happy Path", "Edge Case"
    preconditions = Column(Text, default="")
    steps         = Column(Text, default="")         # JSON array of step strings
    expected      = Column(Text, default="")
    priority      = Column(String, default="P1")     # P0|P1|P2|P3
    order_index   = Column(Integer, default=0)
    created_at    = Column(DateTime, default=datetime.utcnow)
    updated_at    = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
