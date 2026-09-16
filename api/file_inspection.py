from pathlib import Path

# Applies everywhere a file's worth of text gets shown to the user:
# stdout, scheduler output, options, "Show inputs and outputs" > "View",
# and the program-files panel's read-only preview, so none of them can
# ship an arbitrarily large response to the browser.
MAX_INSPECT_LINES = 10_000


def looks_binary(path: Path, sample_size: int = 8192) -> bool:
    """
    Sniffs the first chunk of a file the same way `file`/git do: a NUL
    byte, or a decode failure, means it isn't text worth dumping into a
    preview.
    """
    try:
        with path.open("rb") as f:
            chunk = f.read(sample_size)
    except OSError:
        return False

    if b"\x00" in chunk:
        return True

    try:
        chunk.decode("utf-8")
    except UnicodeDecodeError:
        return True

    return False


def read_text_capped(path: Path, max_lines: int = MAX_INSPECT_LINES) -> str:
    """
    Reads at most `max_lines` lines, without loading a much larger file
    into memory first just to find out it's too big.
    """
    lines: list[str] = []
    truncated = False

    with path.open("r", errors="replace") as f:
        for i, line in enumerate(f):
            if i >= max_lines:
                truncated = True
                break
            lines.append(line)

    content = "".join(lines)
    if truncated:
        content = (
            f"Warning: file has more than {max_lines} lines, "
            f"showing only the first {max_lines}.\n\n"
        ) + content

    return content
