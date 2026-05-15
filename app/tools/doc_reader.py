"""
Tool: Read requirement documents.

Risk Level: L1 (self-execution, no approval required)
Permission Constraints: Only allow reading files in knowledge/ and exams/ directories,
                        prevent digital employee from being induced to read system files (path traversal attacks).
"""
import os

# Whitelist of allowed directories to read (relative to project root)
_ALLOWED_DIRS = [
    os.path.join(os.path.dirname(__file__), "..", "knowledge"),
    os.path.join(os.path.dirname(__file__), "..", "exams"),
    os.path.join(os.path.dirname(__file__), "..", "sample_requirements"),
]
_MAX_CHARS = 8000  # Limit single read to avoid exceeding context window


def read_requirement_doc(file_path: str) -> str:
    """
    Read requirement document content.

    Args:
        file_path: Document path (supports relative paths, relative to project root)

    Returns:
        Document content string, or error message.
    """
    # Parse absolute path
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    abs_path = os.path.normpath(os.path.join(project_root, file_path))

    # ── Security Check: Path must be in whitelisted directories ────────────────────────────────────
    allowed = [os.path.normpath(d) for d in _ALLOWED_DIRS]
    if not any(abs_path.startswith(d) for d in allowed):
        return (
            f"[Denied] Path '{file_path}' is not in the allowed directory range. "
            f"Allowed directories: knowledge/, exams/, sample_requirements/."
        )

    if not os.path.exists(abs_path):
        return f"[Error] File does not exist: {file_path}"

    if not os.path.isfile(abs_path):
        return f"[Error] Path is not a file: {file_path}"

    try:
        with open(abs_path, "r", encoding="utf-8") as f:
            content = f.read(_MAX_CHARS)

        if len(content) == _MAX_CHARS:
            content += f"\n\n[Tip] Document truncated (exceeds {_MAX_CHARS} character limit)"

        return content

    except UnicodeDecodeError:
        return f"[Error] File encoding not supported (requires UTF-8): {file_path}"
    except OSError as e:
        return f"[Error] Read failed: {e}"
