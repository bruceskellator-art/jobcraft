"""Resume template renderer: Jinja2 → HTML, weasyprint → PDF."""

from __future__ import annotations

import importlib.resources
import logging
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.generator.types import ResumeData
from app.resume_templates.registry import get_template

logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).parent / "templates"
_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=select_autoescape(["html"]),
    trim_blocks=True,
    lstrip_blocks=True,
)


def render_to_html(template_id: str, data: ResumeData) -> str:
    """Render ResumeData into the named HTML template.

    Falls back to 'standard' if the requested template is not found.
    """
    info = get_template(template_id)
    if info is None:
        logger.warning("render_to_html: unknown template %r, falling back to standard", template_id)
        template_id = "standard"

    template = _env.get_template(f"{template_id}.html.j2")
    return template.render(data=data)


def render_to_pdf(template_id: str, data: ResumeData) -> bytes:
    """Render ResumeData → HTML → PDF bytes via weasyprint.

    Raises ImportError if weasyprint is not installed.
    Raises RuntimeError on render failure.
    """
    try:
        from weasyprint import HTML as WeasyprintHTML  # type: ignore[import]
    except ImportError as exc:
        raise ImportError(
            "weasyprint is not installed. Run: pip install weasyprint\n"
            "macOS system deps: brew install cairo pango gdk-pixbuf libffi"
        ) from exc

    html_str = render_to_html(template_id, data)
    try:
        return WeasyprintHTML(string=html_str).write_pdf()
    except Exception as exc:
        raise RuntimeError(f"weasyprint PDF render failed: {exc}") from exc
