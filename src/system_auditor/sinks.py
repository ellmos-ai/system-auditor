"""Where a finding goes -- ticket system optional, never required.

The auditor knows exactly one outbound interface.  It does not know ticket
formats, lifecycle folders, categories or model routing: that is the ticket
system's business, and keeping it there means the two can be improved
independently.

If no ticket system is installed -- or its probe fails -- findings are written
as files.  Nothing is lost, only the routing.
"""

from __future__ import annotations

import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path

KIND_FILE = "file"
KIND_COMMAND = "command"


@dataclass
class Sink:
    kind: str = KIND_FILE
    target: str = ""
    enabled_probe: str = ""


@dataclass
class EmitResult:
    ok: bool
    ref: str
    kind: str
    detail: str = ""
    fell_back: bool = False


def _probe(command: str, timeout: int = 20) -> bool:
    if not command:
        return True
    try:
        completed = subprocess.run(
            command, shell=True, capture_output=True, timeout=timeout, check=False
        )
        return completed.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _slug(text: str) -> str:
    keep = [char if char.isalnum() or char in "-_" else "-" for char in text.strip()]
    return "".join(keep).strip("-").lower()[:60] or "finding"


def emit_file(title: str, body: str, directory: Path, run_id: str = "") -> EmitResult:
    target_dir = Path(directory) / (run_id or "unsorted")
    target_dir.mkdir(parents=True, exist_ok=True)
    index = len(list(target_dir.glob("FINDING-*.md"))) + 1
    target = target_dir / f"FINDING-{index:02d}-{_slug(title)}.md"
    target.write_text(f"# {title}\n\n{body.rstrip()}\n", encoding="utf-8")
    return EmitResult(True, str(target), KIND_FILE)


def emit_command(title: str, body: str, command: str, timeout: int = 120) -> EmitResult:
    """Hand the finding to an external intake command.

    The command's stdout is treated as an opaque reference (an id or a path):
    the auditor deliberately does not parse the ticket system's output format.
    """
    argv = shlex.split(command) + ["--title", title, "--body", body]
    try:
        completed = subprocess.run(
            argv, capture_output=True, text=True, timeout=timeout, check=False
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return EmitResult(False, "", KIND_COMMAND, detail=str(exc))
    if completed.returncode != 0:
        return EmitResult(
            False, "", KIND_COMMAND, detail=(completed.stderr or "").strip()[:400]
        )
    ref = (completed.stdout or "").strip().splitlines()
    return EmitResult(True, ref[-1] if ref else "", KIND_COMMAND)


def emit(
    title: str,
    body: str,
    sink: Sink,
    fallback_dir: Path,
    run_id: str = "",
    probe_runner=None,
) -> EmitResult:
    """Emit one finding, degrading to the file sink rather than failing."""
    if sink.kind == KIND_COMMAND and sink.target:
        runner = probe_runner or _probe
        if runner(sink.enabled_probe):
            result = emit_command(title, body, sink.target)
            if result.ok:
                return result
            fallback = emit_file(title, body, fallback_dir, run_id)
            fallback.fell_back = True
            fallback.detail = f"command sink failed: {result.detail}"
            return fallback
        fallback = emit_file(title, body, fallback_dir, run_id)
        fallback.fell_back = True
        fallback.detail = "command sink not available (probe failed)"
        return fallback
    return emit_file(title, body, fallback_dir, run_id)
