"""
Digital Employee · Entry Script

Three usage modes:

  1. Interactive mode (chat with Digital Employee)
     python main.py

  2. Exam mode (run a specific test case)
     python main.py --exam exams/tc_design_001.yaml

  3. Full exam suite (run all test cases)
     python main.py --exam-all
"""
import argparse
import os
import sys

from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.text import Text

console = Console()


def check_env():
    """Check required environment variables and dependencies."""
    from config import ANTHROPIC_API_KEY, CHROMA_DB_PATH

    if not ANTHROPIC_API_KEY:
        console.print(
            "[red][Error] ANTHROPIC_API_KEY not set.\n"
            "Please copy .env.example to .env, fill in your API Key, and retry.[/red]"
        )
        sys.exit(1)

    kb_ready = os.path.exists(CHROMA_DB_PATH)
    if not kb_ready:
        console.print(
            "[yellow][Notice] Knowledge base not yet initialized.\n"
            "Recommended to run first: python knowledge/setup_kb.py\n"
            "The digital worker can still function, but cannot retrieve knowledge base content.[/yellow]\n"
        )


def interactive_mode():
    """
    Interactive mode: real-time chat with Digital Employee.
    Supports Human-in-the-loop: when Agent triggers L2 tools, it pauses and waits for Mentor approval.
    """
    from langchain_core.messages import HumanMessage
    from agent.agent import build_agent
    from config import AGENT_NAME, AGENT_VERSION
    from tools.memory_manager import load_memory_context

    # Show memory status in welcome panel
    memory_context = load_memory_context()
    memory_hint = "🧠 Memory loaded from previous sessions" if memory_context else "🆕 No previous memory (first session)"

    console.print(Panel(
        f"[bold green]{AGENT_NAME} · {AGENT_VERSION}[/bold green]\n"
        f"{memory_hint}\n"
        f"Type [bold]exit[/bold] to quit, [bold]exam[/bold] to enter exam mode",
        title="🤖 Digital Employee Ready",
        border_style="green",
    ))

    app = build_agent()
    thread_id = "interactive-session"
    config = {"configurable": {"thread_id": thread_id}}

    # Initialize state
    state = {
        "messages": [],
        "task_id": thread_id,
        "task_description": "",
        "pending_approval": False,
        "escalated": False,
        "escalation_reason": "",
    }

    while True:
        try:
            user_input = console.input("\n[bold blue]You[/bold blue]: ").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Goodbye![/dim]")
            break

        if user_input.lower() in ("exit", "quit"):
            console.print("[dim]Goodbye![/dim]")
            break

        if user_input.lower() == "exam":
            console.print("[dim]Switching to exam mode, please restart with --exam parameter.[/dim]")
            break

        if not user_input:
            continue

        state["messages"] = state.get("messages", []) + [
            HumanMessage(content=user_input)
        ]

        console.print()  # Blank line separator
        # Stream Agent execution, display progress in real-time
        result = _stream_with_progress(app, state, config)

        # Check if interrupted (waiting for Mentor approval)
        current_tasks = app.get_state(config).next
        if current_tasks and "human_review" in current_tasks:
            console.print(
                "\n[bold yellow]⚠️  Mentor Approval Required[/bold yellow]\n"
                "Digital Employee requests to execute an operation requiring approval (L2 tool)."
            )
            last_msg = result["messages"][-1]
            for tc in last_msg.tool_calls:
                console.print(f"  [dim]Tool:[/dim] {tc['name']}")
                console.print(f"  [dim]Args:[/dim] {_fmt_args(tc['args'])}")

            approval = console.input("\n[bold]Approve? (y/n):[/bold] ").strip().lower()
            if approval == "y":
                result = _stream_with_progress(app, None, config)
            else:
                console.print("[dim]Rejected, operation cancelled.[/dim]")
                app.update_state(config, {"messages": [], "pending_approval": False})
                continue

        # Output final response
        state = result
        last_msg = result["messages"][-1]
        output = last_msg.content if hasattr(last_msg, "content") else str(last_msg)

        console.print(f"\n[bold green]Digital Employee[/bold green]: {output}")

        # Escalation notice
        if result.get("escalated"):
            console.print(
                f"\n[yellow]📢 Escalated to Mentor: {result.get('escalation_reason', '')}[/yellow]"
            )


def _stream_with_progress(app, state, config) -> dict:
    """
    Use LangGraph stream instead of invoke to display Agent's thinking process in real-time:
      - Show rotating spinner "🤔 Thinking..." for each LLM inference round
      - Display intermediate reasoning text in dim italics (before tool calls)
      - Show tool names and key parameters when calling tools
      - Brief summary of results when tools return
    """
    # _TOOL_LABEL: tool name → display label + key field from args
    _TOOL_LABEL = {
        "search_knowledge_base": ("📚 Search Local KB",      "query"),
        "search_confluence":     ("🔍 Search Confluence",    "query"),
        "save_confluence_page":  ("💾 Cache Page",           "page_id"),
        "read_requirement_doc":  ("📄 Read Requirement Doc", "file_path"),
        "write_output_file":     ("💾 Save File",            "filename"),
        "create_defect_mock":    ("🐛 Create Defect",        "title"),
        "search_jira":           ("🎫 Search Jira",          "query"),
        "get_jira_issue":        ("🎫 Get Jira Issue",       "issue_key"),
        "get_gitlab_mr_diff":    ("🔀 Fetch MR Diff",        "mr_url"),
        "save_to_memory":        ("🧠 Save to Memory",        "key"),
    }

    merged_state = state or {}
    round_num = 0

    with console.status("[bold yellow]🤔 Thinking...[/bold yellow]", spinner="dots") as status:
        for event in app.stream(state, config=config, stream_mode="updates"):
            node_name = list(event.keys())[0]
            node_output = event[node_name]

            # ── __interrupt__: emitted when LangGraph pauses for L2 tool, value is tuple, skip merge ──
            if node_name == "__interrupt__" or not isinstance(node_output, dict):
                break  # After interrupt, no more events in stream, exit directly

            if node_name == "agent":
                round_num += 1
                last_msg = node_output.get("messages", [None])[-1]

                # If LLM outputs thinking text before tool call, display in dim
                if last_msg and getattr(last_msg, "content", ""):
                    thinking = last_msg.content.strip()
                    if thinking and getattr(last_msg, "tool_calls", None):
                        preview = thinking[:300] + ("…" if len(thinking) > 300 else "")
                        console.print(f"[dim italic]  💭 {preview}[/dim italic]")

                # Show tools about to be called
                tool_calls = getattr(last_msg, "tool_calls", None) or []
                for tc in tool_calls:
                    label, key_arg = _TOOL_LABEL.get(tc["name"], (f"🔧 {tc['name']}", None))
                    arg_hint = f": {str(tc['args'].get(key_arg, ''))[:60]}" if key_arg and tc["args"].get(key_arg) else ""
                    console.print(f"  [cyan]{label}[/cyan][dim]{arg_hint}[/dim]")

                if tool_calls:
                    status.update("[bold yellow]⚙️  Executing tools...[/bold yellow]")
                else:
                    status.update("")  # About to finish, clear spinner

                merged_state = {**merged_state, **node_output}

            elif node_name == "tools":
                # Show summary of each tool's return (first 120 chars)
                for msg in node_output.get("messages", []):
                    result_text = str(getattr(msg, "content", "")).strip()
                    if result_text:
                        preview = result_text[:120] + ("…" if len(result_text) > 120 else "")
                        console.print(f"  [dim]↳ {preview}[/dim]")

                status.update("[bold yellow]🤔 Organizing results, continuing to think...[/bold yellow]")
                merged_state = {**merged_state, **node_output}

            else:
                # Other nodes like human_review (normal dict, safe merge)
                merged_state = {**merged_state, **node_output}

            # Refresh spinner before each inference round (next agent iteration)
            if node_name == "tools":
                status.update("[bold yellow]🤔 Thinking...[/bold yellow]")

    return merged_state


def _fmt_args(args: dict, max_len: int = 80) -> str:
    """Format tool arguments as short string for approval prompt display."""
    import json
    try:
        s = json.dumps(args, ensure_ascii=False)
    except Exception:
        s = str(args)
    return s[:max_len] + ("…" if len(s) > max_len else "")


def exam_mode(exam_file: str):
    """Run a single test case."""
    from eval.evaluator import run_exam
    run_exam(exam_file)


def exam_all_mode():
    """Run all test cases."""
    from eval.evaluator import run_all_exams
    run_all_exams()


def main():
    parser = argparse.ArgumentParser(description="Digital Employee")
    parser.add_argument("--exam", type=str, help="Run specific test case (YAML file path)")
    parser.add_argument("--exam-all", action="store_true", help="Run all test cases")
    args = parser.parse_args()

    check_env()

    if args.exam_all:
        exam_all_mode()
    elif args.exam:
        exam_mode(args.exam)
    else:
        interactive_mode()


if __name__ == "__main__":
    main()
