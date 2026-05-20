from __future__ import annotations

from jinja2 import Environment, StrictUndefined  # noqa: I001

# PROMPT-ONLY: autoescape intentionally disabled — do NOT reuse for HTML rendering.
_ENV = Environment(undefined=StrictUndefined, autoescape=False)


def render_template(template: str, inputs: dict) -> str:
    """
    Render a Jinja2 template string with the given inputs.

    Raises jinja2.UndefinedError for any variable referenced in the
    template that is not present in inputs (StrictUndefined).
    """
    tmpl = _ENV.from_string(template)
    return tmpl.render(**inputs)
