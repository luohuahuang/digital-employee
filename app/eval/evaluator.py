"""
Exam Evaluator.

Responsibilities:
  1. Load test cases from YAML
  2. Call Agent to execute test cases
  3. Auto-score (keyword hits)
  4. Display results, prompt Mentor for manual scoring

Corresponds to design doc: §7 Training System, §7.1 Exam Library Structure, §3.5 Test Cases as Exams.
"""
import os
import yaml
from datetime import datetime
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

console = Console()


def load_exam(exam_file: str) -> dict:
    """Load test case definition from YAML file."""
    with open(exam_file, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def auto_score(output: str, expected_keywords: list[str]) -> tuple[float, list[str]]:
    """
    Auto-score based on keyword hits.

    Returns:
        (score_0_to_100, missed_keywords)
    """
    if not expected_keywords:
        return 100.0, []

    hits = [kw for kw in expected_keywords if kw in output]
    missed = [kw for kw in expected_keywords if kw not in output]
    score = (len(hits) / len(expected_keywords)) * 100
    return round(score, 1), missed


def run_exam(
    exam_file: str,
    mentor_scores: Optional[dict[str, float]] = None,
    verbose: bool = True,
) -> dict:
    """
    Execute single test case, output scoring results.

    Args:
        exam_file:      Test case YAML file path
        mentor_scores:  Mentor's scores for each criterion {criterion: score 0-1}
                        None means interactive mode, input from terminal
        verbose:        Whether to print detailed output

    Returns:
        Result dict containing auto_score, mentor_score, total_score, passed, etc.
    """
    # Deferred import to avoid loading model at startup
    from agent import run_agent

    exam = load_exam(exam_file)
    exam_id = exam["id"]
    user_message = exam["input"]["message"]
    expected_kws = exam.get("expected_keywords", [])
    mentor_criteria = exam.get("mentor_criteria", [])
    auto_weight = exam.get("auto_score_weight", 0.6)
    mentor_weight = exam.get("mentor_score_weight", 0.4)
    threshold = exam.get("pass_threshold", 75)

    if verbose:
        console.print(Panel(
            f"[bold cyan]Test Case ID: {exam_id}[/bold cyan]\n"
            f"Skill: {exam.get('skill', 'N/A')}  Difficulty: {exam.get('difficulty', 'N/A')}\n"
            f"Scenario: {exam.get('scenario', 'N/A')}",
            title="📋 Starting Exam",
            border_style="cyan",
        ))
        console.print(f"\n[bold]Task Input:[/bold]\n{user_message}\n")

    # ── Execute Agent ──────────────────────────────────────────────────────
    start_time = datetime.now()
    output = run_agent(user_message, thread_id=exam_id)
    elapsed = (datetime.now() - start_time).total_seconds()

    if verbose:
        console.print(Panel(output, title="🤖 Digital QA Engineer Output", border_style="green"))

    # ── Auto-scoring ────────────────────────────────────────────────────────
    a_score, missed_kws = auto_score(output, expected_kws)

    if verbose:
        kw_table = Table(box=box.SIMPLE, show_header=True)
        kw_table.add_column("Keyword", style="white")
        kw_table.add_column("Hit", justify="center")
        for kw in expected_kws:
            hit = kw in output
            kw_table.add_row(kw, "✅" if hit else "❌")
        console.print(f"\n[bold]Auto-Score (Keyword Hits): {a_score}/100[/bold]")
        console.print(kw_table)

    # ── Mentor Scoring ─────────────────────────────────────────────────────
    if mentor_weight > 0 and mentor_criteria:
        if mentor_scores is None:
            # Interactive mode: terminal input
            console.print("\n[bold yellow]── Mentor Scoring ──[/bold yellow]")
            console.print("[dim]Please score each criterion (0.0 ~ 1.0, 1.0=fully satisfied)[/dim]\n")
            mentor_scores = {}
            for criterion in mentor_criteria:
                while True:
                    try:
                        score_str = console.input(f"  {criterion}\n  Score (0-1): ")
                        score_val = float(score_str)
                        if 0 <= score_val <= 1:
                            mentor_scores[criterion] = score_val
                            break
                        console.print("  [red]Please enter a number between 0 and 1[/red]")
                    except ValueError:
                        console.print("  [red]Please enter a number[/red]")

        m_score = (sum(mentor_scores.values()) / len(mentor_criteria)) * 100
    else:
        m_score = 0.0
        mentor_scores = {}

    # ── Combined Score ─────────────────────────────────────────────────────
    total = round(a_score * auto_weight + m_score * mentor_weight, 1)
    passed = total >= threshold

    result = {
        "exam_id":       exam_id,
        "skill":         exam.get("skill"),
        "auto_score":    a_score,
        "mentor_score":  m_score,
        "total_score":   total,
        "threshold":     threshold,
        "passed":        passed,
        "missed_keywords": missed_kws,
        "elapsed_sec":   round(elapsed, 2),
        "output":        output,
        "timestamp":     datetime.now().isoformat(),
    }

    if verbose:
        status = "[bold green]✅ Passed[/bold green]" if passed else "[bold red]❌ Failed[/bold red]"
        console.print(Panel(
            f"Auto-Score: {a_score}/100  ×  {int(auto_weight * 100)}%\n"
            f"Mentor Score: {m_score}/100  ×  {int(mentor_weight * 100)}%\n"
            f"[bold]Combined Score: {total}/100[/bold] (Threshold: {threshold})\n"
            f"Result: {status}",
            title="📊 Scoring Results",
            border_style="green" if passed else "red",
        ))

        if not passed and missed_kws:
            console.print(f"\n[yellow]Missing Keywords (improvement hints): {', '.join(missed_kws)}[/yellow]")
            console.print("[dim]→ Consider adding related knowledge base content or adjusting System Prompt[/dim]")

    return result


def run_all_exams(exams_dir: str = None) -> list[dict]:
    """
    Run all test cases in exams/ directory, output summary report.
    Useful for full regression before version release.
    """
    if exams_dir is None:
        exams_dir = os.path.join(os.path.dirname(__file__), "..", "exams")

    exam_files = sorted(
        f for f in os.listdir(exams_dir) if f.endswith(".yaml")
    )

    if not exam_files:
        console.print("[yellow]No test case files in exams/ directory.[/yellow]")
        return []

    console.print(f"\n[bold]Starting full exam suite, {len(exam_files)} test cases total[/bold]\n")
    results = []

    for filename in exam_files:
        filepath = os.path.join(exams_dir, filename)
        result = run_exam(filepath, mentor_scores=None, verbose=True)
        results.append(result)
        console.rule()

    # Summary
    passed = sum(1 for r in results if r["passed"])
    avg_score = sum(r["total_score"] for r in results) / len(results)

    summary = Table(title="Exam Summary", box=box.ROUNDED)
    summary.add_column("Test Case ID", style="cyan")
    summary.add_column("Score", justify="right")
    summary.add_column("Threshold", justify="right")
    summary.add_column("Result", justify="center")

    for r in results:
        status = "✅" if r["passed"] else "❌"
        summary.add_row(r["exam_id"], str(r["total_score"]), str(r["threshold"]), status)

    console.print(summary)
    console.print(
        f"\n[bold]Pass Rate: {passed}/{len(results)}  Average Score: {avg_score:.1f}[/bold]"
    )

    return results
