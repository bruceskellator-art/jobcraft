"""PDF rendering for generated artifacts.

PDF output is best-effort: artifact.content always stays as Markdown.
Rendering to PDF requires the ``typst`` binary to be installed separately.
NullPdfRenderer is the default in tests and environments without typst.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Protocol

logger = logging.getLogger(__name__)


class PdfRenderError(Exception):
    """Raised when PDF rendering fails."""


class PdfRenderer(Protocol):
    """Protocol for PDF renderers."""

    def render(self, markdown: str) -> bytes:
        """Render markdown to PDF bytes."""
        ...


class NullPdfRenderer:
    """No-op renderer for tests and environments without typst.

    Returns empty bytes so callers can treat PDF as optional without
    requiring the typst binary to be present.
    """

    def render(self, markdown: str) -> bytes:
        return b""


def _markdown_to_typst(markdown: str) -> str:
    """Minimal markdown-to-typst conversion for basic resume content."""
    lines = markdown.splitlines()
    out: list[str] = [
        "#set page(margin: 1in)",
        '#set text(font: "Linux Libertine", size: 11pt)',
        "",
    ]

    for line in lines:
        # H1
        if line.startswith("# "):
            out.append(f"= {line[2:]}")
        # H2
        elif line.startswith("## "):
            out.append(f"== {line[3:]}")
        # H3
        elif line.startswith("### "):
            out.append(f"=== {line[4:]}")
        # Bullet
        elif line.startswith("- ") or line.startswith("* "):
            content = line[2:]
            # Bold
            content = re.sub(r"\*\*(.+?)\*\*", r"*\1*", content)
            out.append(f"- {content}")
        # Horizontal rule
        elif line.strip() in ("---", "***", "___"):
            out.append("#line(length: 100%)")
        else:
            # Inline bold
            converted = re.sub(r"\*\*(.+?)\*\*", r"*\1*", line)
            out.append(converted)

    return "\n".join(out)


class TypstRenderer:
    """Renders markdown to PDF via the typst CLI.

    Raises PdfRenderError if the typst binary is missing or if rendering fails.
    """

    def __init__(self, typst_bin: str = "typst") -> None:
        self._bin = typst_bin

    def render(self, markdown: str) -> bytes:
        if shutil.which(self._bin) is None:
            raise PdfRenderError(
                f"typst binary '{self._bin}' not found. "
                "Install typst (https://typst.app) or use NullPdfRenderer."
            )

        typst_source = _markdown_to_typst(markdown)

        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "doc.typ"
            out = Path(tmp) / "doc.pdf"
            src.write_text(typst_source, encoding="utf-8")

            result = subprocess.run(
                [self._bin, "compile", str(src), str(out)],
                capture_output=True,
                timeout=30,
            )
            if result.returncode != 0:
                stderr = result.stderr.decode(errors="replace")
                raise PdfRenderError(f"typst compile failed: {stderr}")

            return out.read_bytes()
