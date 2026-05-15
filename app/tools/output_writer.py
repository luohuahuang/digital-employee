"""
Tool: Write content to local files (supports .md / .txt / .csv).

Risk Level: L1 (self-execution)
Write Scope: Only allow writing to output/ directory under project root, prevent path traversal.

CSV Writing Method:
  Pass content directly as CSV format text (first row is column headers, subsequent rows are records separated by commas).
  Tool re-parses and writes using csv module, automatically handles quote escaping, no Chinese encoding issues (utf-8-sig).

  Example:
    Case ID,Title,Scenario Type,Precondition,Steps,Expected Result,Risk Notes
    TC-001,Normal Add to Cart,Normal Flow,User Logged In,Click Add to Cart,Quantity +1 and success message,None
    TC-002,Zero Stock,Boundary Case,Product Stock is 0,Click Add to Cart,Show Out of Stock,None
"""
import csv
import io
import os
from datetime import datetime

_OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output")


def write_output_file(
    content: str,
    filename: str = "",
    file_type: str = "md",
) -> str:
    """
    Save content to a file in the output/ directory.

    Args:
        content:   Text content. For csv, it's CSV format text (first row headers, comma-separated)
        filename:  Filename (without extension). If not provided, auto-generates timestamp filename
        file_type: "md" (default) / "txt" / "csv"

    Returns:
        Confirmation message with saved file path, or error message.
    """
    os.makedirs(_OUTPUT_DIR, exist_ok=True)

    if not filename:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"output_{timestamp}"

    safe_name = "".join(c for c in filename if c.isalnum() or c in "-_")
    ext = file_type.lower() if file_type.lower() in ("md", "txt", "csv") else "md"
    filepath = os.path.join(_OUTPUT_DIR, f"{safe_name}.{ext}")

    if ext == "csv":
        _write_csv(filepath, content)
    else:
        with open(filepath, "w", encoding="utf-8-sig") as f:
            f.write(content)

    rel_path = f"output/{safe_name}.{ext}"
    return f"✅ Saved to: {rel_path}"


def _write_csv(filepath: str, content: str) -> None:
    """
    Re-parse CSV format text and write to file.
    Use csv module for reading/writing, automatically handle quote escaping for cells with commas/line breaks.
    Output utf-8-sig (with BOM), Excel opens Chinese without encoding issues.
    """
    reader = csv.reader(io.StringIO(content.strip()))
    rows = list(reader)

    if not rows:
        raise ValueError("CSV content is empty")

    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f, quoting=csv.QUOTE_MINIMAL)
        writer.writerows(rows)
