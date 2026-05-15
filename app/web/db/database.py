"""SQLite database connection and session management."""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from config import WEB_DB_PATH

os.makedirs(os.path.dirname(WEB_DB_PATH), exist_ok=True)

engine = create_engine(f"sqlite:///{WEB_DB_PATH}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class Base(DeclarativeBase):
    pass

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    from web.db import models  # noqa: ensure models are registered
    Base.metadata.create_all(bind=engine)
    _migrate()


def _migrate():
    """Add new columns to existing tables without dropping data."""
    from sqlalchemy import text, inspect
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    # Rename qa_agents → agents (one-time migration for platform rename)
    if "qa_agents" in existing_tables and "agents" not in existing_tables:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE qa_agents RENAME TO agents"))
        # Refresh table list after rename
        existing_tables = set(inspect(engine).get_table_names())

    # Create role_prompt_templates table if it doesn't exist yet
    if "role_prompt_templates" not in existing_tables:
        with engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE role_prompt_templates (
                    role       TEXT PRIMARY KEY,
                    content    TEXT NOT NULL DEFAULT '',
                    updated_at TEXT
                )
            """))

    def _add_cols(table: str, cols: list[tuple[str, str]]):
        existing = {c["name"] for c in inspector.get_columns(table)}
        with engine.begin() as conn:
            for col, typ in cols:
                if col not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {typ}"))

    _add_cols("test_runs", [
        ("platform",         "TEXT NOT NULL DEFAULT 'web'"),
        ("suite_name",       "TEXT DEFAULT ''"),
        ("env_skill_id",     "TEXT"),
        ("extra_skill_ids",  "TEXT DEFAULT '[]'"),
    ])
    _add_cols("audit_logs", [
        ("input_tokens",   "INTEGER"),
        ("output_tokens",  "INTEGER"),
        ("trace_id",       "TEXT"),
        ("node_name",      "TEXT"),
        ("extra_data_json","TEXT"),
    ])
    _add_cols("exam_runs", [
        ("prompt_version_id",  "TEXT"),
        ("prompt_version_num", "INTEGER"),
        ("judge_results_json", "TEXT"),
        ("rules_result_json",  "TEXT"),
    ])
    _add_cols("prompt_versions", [
        ("type", "TEXT DEFAULT 'base'"),
    ])
    _add_cols("agents", [
        ("role", "TEXT DEFAULT 'QA'"),
    ])

    # Create prompt_suggestions table if it doesn't exist yet
    if "prompt_suggestions" not in existing_tables:
        with engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE prompt_suggestions (
                    id                 TEXT PRIMARY KEY,
                    run_id             TEXT NOT NULL REFERENCES exam_runs(id),
                    agent_id           TEXT NOT NULL,
                    prompt_version_id  TEXT,
                    diagnosis          TEXT DEFAULT '',
                    suggestions_json   TEXT DEFAULT '[]',
                    patched_prompt     TEXT DEFAULT '',
                    applied            INTEGER DEFAULT 0,
                    applied_version_id TEXT,
                    created_at         TEXT
                )
            """))

    # Create test_suites and test_cases tables if they don't exist yet
    if "test_suites" not in existing_tables:
        with engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE test_suites (
                    id           TEXT PRIMARY KEY,
                    agent_id     TEXT NOT NULL REFERENCES agents(id),
                    agent_name   TEXT DEFAULT '',
                    name         TEXT NOT NULL,
                    description  TEXT DEFAULT '',
                    source_type  TEXT DEFAULT 'manual',
                    source_ref   TEXT DEFAULT '',
                    jira_key     TEXT DEFAULT '',
                    created_at   TEXT,
                    updated_at   TEXT
                )
            """))

    # Migrate: add component column to existing test_suites table
    with engine.begin() as conn:
        try:
            conn.execute(text("ALTER TABLE test_suites ADD COLUMN component TEXT DEFAULT ''"))
        except Exception:
            pass  # column already exists

    if "test_cases" not in existing_tables:
        with engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE test_cases (
                    id            TEXT PRIMARY KEY,
                    suite_id      TEXT NOT NULL REFERENCES test_suites(id),
                    title         TEXT NOT NULL,
                    category      TEXT DEFAULT '',
                    preconditions TEXT DEFAULT '',
                    steps         TEXT DEFAULT '',
                    expected      TEXT DEFAULT '',
                    priority      TEXT DEFAULT 'P1',
                    order_index   INTEGER DEFAULT 0,
                    created_at    TEXT,
                    updated_at    TEXT
                )
            """))

    # Create tool_risk_config table if it doesn't exist yet
    if "tool_risk_config" not in existing_tables:
        with engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE tool_risk_config (
                    tool_name  TEXT PRIMARY KEY,
                    risk_level TEXT NOT NULL DEFAULT 'L1',
                    updated_at TEXT
                )
            """))
            from config import TOOL_RISK_LEVEL
            for tool, level in TOOL_RISK_LEVEL.items():
                conn.execute(
                    text("INSERT INTO tool_risk_config (tool_name, risk_level) VALUES (:t, :l)"),
                    {"t": tool, "l": level},
                )

    # Create test_runs table if it doesn't exist yet
    if "test_runs" not in existing_tables:
        with engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE test_runs (
                    id               TEXT PRIMARY KEY,
                    name             TEXT NOT NULL,
                    suite_id         TEXT NOT NULL,
                    base_url         TEXT NOT NULL DEFAULT '',
                    env_skill_id     TEXT,
                    extra_skill_ids  TEXT DEFAULT '[]',
                    platform         TEXT NOT NULL DEFAULT 'web',
                    status           TEXT NOT NULL DEFAULT 'pending',
                    total_cases      INTEGER DEFAULT 0,
                    passed           INTEGER DEFAULT 0,
                    failed           INTEGER DEFAULT 0,
                    created_at       TEXT,
                    started_at       TEXT,
                    completed_at     TEXT
                )
            """))

    # Create test_run_cases table if it doesn't exist yet
    if "test_run_cases" not in existing_tables:
        with engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE test_run_cases (
                    id               TEXT PRIMARY KEY,
                    run_id           TEXT NOT NULL,
                    case_id          TEXT NOT NULL,
                    case_title       TEXT,
                    status           TEXT NOT NULL DEFAULT 'pending',
                    failure_step     INTEGER,
                    actual_result    TEXT,
                    steps_json       TEXT,
                    screenshots_json TEXT,
                    executed_at      TEXT
                )
            """))

    # Create browser_skills table if it doesn't exist yet
    if "browser_skills" not in existing_tables:
        with engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE browser_skills (
                    id         TEXT PRIMARY KEY,
                    name       TEXT NOT NULL,
                    skill_type TEXT NOT NULL DEFAULT 'extra',
                    content    TEXT NOT NULL DEFAULT '',
                    created_at TEXT,
                    updated_at TEXT
                )
            """))
            # Seed a starter environment skill so the UI isn't empty
            import uuid as _uuid
            from datetime import datetime as _dt, timezone as _tz
            _now = _dt.now(_tz.utc).isoformat()
            conn.execute(text("""
                INSERT INTO browser_skills (id, name, skill_type, content, created_at, updated_at)
                VALUES (:id, :name, :type, :content, :now, :now)
            """), {
                "id": str(_uuid.uuid4()),
                "name": "Example Staging Environment",
                "type": "environment",
                "content": (
                    "# Environment: Example Staging\n\n"
                    "base_url: https://staging.example.com\n\n"
                    "credentials:\n"
                    "  username: testuser@example.com\n"
                    "  password: Test1234\n\n"
                    "test_data:\n"
                    "  product_id: '12345'\n"
                    "  voucher_code: 'SAVE10'\n\n"
                    "notes:\n"
                    "  - CAPTCHA is disabled in staging\n"
                    "  - Payment gateway is mocked\n"
                ),
                "now": _now,
            })
            conn.execute(text("""
                INSERT INTO browser_skills (id, name, skill_type, content, created_at, updated_at)
                VALUES (:id, :name, :type, :content, :now, :now)
            """), {
                "id": str(_uuid.uuid4()),
                "name": "Login Flow",
                "type": "extra",
                "content": (
                    "# Skill: Login Flow\n\n"
                    "When a test step requires logging in:\n"
                    "1. Navigate to /login if not already there\n"
                    "2. Enter credentials from the environment skill\n"
                    "3. Click the login/submit button\n"
                    "4. Wait for the redirect to complete before proceeding\n"
                    "5. If a 'Stay signed in' dialog appears, dismiss it\n"
                ),
                "now": _now,
            })

    # Create test_plans table if it doesn't exist yet
    if "test_plans" not in existing_tables:
        with engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE test_plans (
                    id              TEXT PRIMARY KEY,
                    name            TEXT NOT NULL DEFAULT '',
                    description     TEXT DEFAULT '',
                    suite_ids       TEXT DEFAULT '[]',
                    env_skill_id    TEXT DEFAULT '',
                    extra_skill_ids TEXT DEFAULT '[]',
                    platform        TEXT DEFAULT 'web',
                    created_at      TEXT,
                    updated_at      TEXT
                )
            """))

    # Create ranking_ceiling_config table if it doesn't exist yet
    if "ranking_ceiling_config" not in existing_tables:
        with engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE ranking_ceiling_config (
                    ranking    TEXT PRIMARY KEY,
                    ceiling    TEXT NOT NULL DEFAULT 'L1',
                    updated_at TEXT
                )
            """))
            _CEILING_DEFAULTS = {"Intern": "L1", "Junior": "L1", "Senior": "L2", "Lead": "L3"}
            for ranking, ceiling in _CEILING_DEFAULTS.items():
                conn.execute(
                    text("INSERT INTO ranking_ceiling_config (ranking, ceiling) VALUES (:r, :c)"),
                    {"r": ranking, "c": ceiling},
                )
