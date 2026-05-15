"""
Global configuration loaded from environment variables.
Copy .env.example to .env and fill in API keys as needed.

To switch LLM providers, just modify LLM_PROVIDER in .env:
  LLM_PROVIDER=anthropic  →  Use Claude (default)
  LLM_PROVIDER=openai     →  Use GPT-4
"""
# ChromaDB requires SQLite >= 3.35.0.
# On older Linux distros (e.g. Alibaba Cloud Linux 3 / CentOS 8 which ship
# with SQLite 3.26), we override the built-in sqlite3 module with
# pysqlite3-binary which bundles a modern SQLite.
try:
    import pysqlite3 as _pysqlite3  # noqa: F401
    import sys as _sys
    _sys.modules["sqlite3"] = _sys.modules.pop("pysqlite3")
except ImportError:
    pass  # pysqlite3-binary not installed — system sqlite3 will be used

import os
from dotenv import load_dotenv

load_dotenv()

# ── LLM Provider ───────────────────────────────────────────────────────────
# Supports "anthropic" (default) or "openai"
LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "anthropic").lower()

# Anthropic
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")

# OpenAI
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL: str = os.getenv("OPENAI_BASE_URL", "")  # Optional, for proxy or Azure

# Model name: each provider has default values, can also override in .env
_DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-4-6",
    "openai":    "gpt-4o",
}
MODEL_NAME: str = os.getenv("MODEL_NAME", _DEFAULT_MODELS.get(LLM_PROVIDER, "gpt-4o"))

# ── Knowledge Base ────────────────────────────────────────────────────────
KNOWLEDGE_DIR: str = os.path.join(os.path.dirname(__file__), "knowledge")
CHROMA_DB_PATH: str = os.path.join(KNOWLEDGE_DIR, ".chroma")
MAIN_KB_COLLECTION: str = "de_knowledge_main"
MEMORY_FILE:   str = os.path.join(os.path.dirname(__file__), "memory", "agent_memory.json")
# Embedding always uses OpenAI text-embedding-3-small (ChromaDB OpenAIEmbeddingFunction),
# independent of LLM_PROVIDER.  EMBEDDING_API_KEY is the dedicated key for this;
# it falls back to OPENAI_API_KEY so a single key covers both when using OpenAI for LLM.
EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
EMBEDDING_API_KEY: str = os.getenv("EMBEDDING_API_KEY", "") or OPENAI_API_KEY
KNOWLEDGE_TOP_K: int = 3                      # Number of chunks returned per retrieval

# ── Confluence Integration ─────────────────────────────────────────────────
# If not set, Confluence tools will return a notice without error; system still works
#
# CONFLUENCE_AUTH_TYPE explanation:
#   pat   → Confluence Server / Data Center (self-hosted)
#           Use Personal Access Token, auth header: Authorization: Bearer <token>
#           CONFLUENCE_USERNAME can be omitted
#   basic → Atlassian Cloud (confluence.atlassian.net)
#           Use HTTP Basic Auth: email + API Token
#           CONFLUENCE_USERNAME required
CONFLUENCE_AUTH_TYPE: str = os.getenv("CONFLUENCE_AUTH_TYPE", "pat").lower()
CONFLUENCE_BASE_URL:  str = os.getenv("CONFLUENCE_BASE_URL", "")
CONFLUENCE_USERNAME:  str = os.getenv("CONFLUENCE_USERNAME", "")
CONFLUENCE_API_TOKEN: str = os.getenv("CONFLUENCE_API_TOKEN", "")

# ── Jira Integration ──────────────────────────────────────────────────────
# If not set, Jira tools will return a notice; system still works without them.
#
# Jira Data Center / Server (self-hosted) → Personal Access Token (PAT)
#   Go to Jira → top-right avatar → Profile → Personal Access Tokens → Create token
#   Leave JIRA_USERNAME blank; auth uses "Authorization: Bearer <token>"
#
# Jira Cloud (xxx.atlassian.net) → Basic Auth
#   Token: https://id.atlassian.com/manage-profile/security/api-tokens
#   Set JIRA_USERNAME to your login email
JIRA_AUTH_TYPE: str = os.getenv("JIRA_AUTH_TYPE", "pat").lower()  # pat | basic
JIRA_BASE_URL:  str = os.getenv("JIRA_BASE_URL", "")
JIRA_USERNAME:  str = os.getenv("JIRA_USERNAME", "")
JIRA_API_TOKEN: str = os.getenv("JIRA_API_TOKEN", "")
DEFAULT_JIRA_PROJECT: str = os.getenv("DEFAULT_JIRA_PROJECT", "")

# ── GitLab Integration ────────────────────────────────────────────────────
# Used for reading MR diffs to recommend regression test scope.
# If not set, get_gitlab_mr_diff will return a notice; system still works.
#
# GITLAB_API_TOKEN: GitLab → top-right avatar → Preferences → Access Tokens
#   Required scopes: read_api (read MR diffs)
GITLAB_BASE_URL:  str = os.getenv("GITLAB_BASE_URL", "")
GITLAB_API_TOKEN: str = os.getenv("GITLAB_API_TOKEN", "")

# ── Digital Worker Metadata ────────────────────────────────────────────────
AGENT_ID: str = "de-001"
AGENT_NAME: str = "Digital Employee · v1"
AGENT_VERSION: str = "1.0.0"

# ── Permission Hierarchy (per design doc §5.3) ─────────────────────────────
# L1: Execute autonomously; L2: Requires Mentor approval before execution; L3: No execution, output plan only
TOOL_RISK_LEVEL: dict[str, str] = {
    "read_requirement_doc":   "L1",
    "search_knowledge_base":  "L1",
    "write_output_file":      "L1",   # Only writes to output/ directory, safe
    "search_confluence":      "L1",   # Read-only Confluence, no writes
    "search_jira":            "L1",   # Read-only Jira JQL search
    "get_jira_issue":         "L1",   # Read-only Jira issue detail
    "get_gitlab_mr_diff":     "L1",   # Read-only GitLab MR diff
    "save_to_memory":         "L1",   # Write to local memory file only
    "save_test_suite":        "L1",   # Write test suite to local DB only
    "propose_exam_case":      "L1",   # Write exam draft to exams/drafts/ only, safe
    "create_defect_mock":     "L2",   # Create defect (sandbox mock)
    "create_jira_issue":      "L2",   # Create real Jira issue, requires Mentor approval
    "save_confluence_page":   "L2",   # Write to local vector store, requires Mentor approval
    "merge_branch_to_main":   "L2",   # Merge branch KB to main, requires approval
}

# ── Context Window Management ─────────────────────────────────────────────
# When a conversation exceeds this many messages, the oldest messages are
# summarised into a single HumanMessage before being sent to the LLM.
# Only affects the in-flight LangGraph state — the full history is kept in DB.
CONTEXT_COMPRESS_THRESHOLD: int = int(os.getenv("CONTEXT_COMPRESS_THRESHOLD", "40"))
CONTEXT_KEEP_RECENT: int = int(os.getenv("CONTEXT_KEEP_RECENT", "10"))

# ── Web Server ─────────────────────────────────────────────────────────────
WEB_HOST: str = os.getenv("WEB_HOST", "0.0.0.0")
WEB_PORT: int = int(os.getenv("WEB_PORT", "8000"))
WEB_DB_PATH: str = os.path.join(os.path.dirname(__file__), "web", "de_team.db")
WEB_STATIC_DIR: str = os.path.join(os.path.dirname(__file__), "web", "frontend", "dist")
DOCS_DIR: str       = os.path.join(os.path.dirname(__file__), "..", "docs")
