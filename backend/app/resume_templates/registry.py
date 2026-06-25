"""Template registry: all available resume templates with metadata."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TemplateInfo:
    id: str
    name: str
    description: str
    thumbnail_url: str


TEMPLATES: list[TemplateInfo] = [
    TemplateInfo(
        id="standard",
        name="Standard Format",
        description="Our most popular reverse-chronological resume template. Designed for maximum readability — the safest choice for corporate, government, and traditional sectors.",
        thumbnail_url="/resume-templates/resume_standard.png",
    ),
    TemplateInfo(
        id="compact",
        name="Compact Format",
        description="A high-density layout designed to maximize page real estate. Ideal for seasoned professionals with long work histories.",
        thumbnail_url="/resume-templates/resume_compact.png",
    ),
    TemplateInfo(
        id="modern",
        name="Modern Template",
        description="A sleek design optimized for the tech industry with distinct sections for technical skills and languages.",
        thumbnail_url="/resume-templates/resume_modern.png",
    ),
    TemplateInfo(
        id="harvard",
        name="Harvard Format",
        description="The definitive Harvard resume format. Clean, education-first layout ideal for students and recent graduates targeting finance, consulting, and academia.",
        thumbnail_url="/resume-templates/resume_harvard.png",
    ),
    TemplateInfo(
        id="jake",
        name="Jake's Resume",
        description="Our adaptation of Jake's Resume from Overleaf. High-density, single-column layout standard for software engineers and developers.",
        thumbnail_url="/resume-templates/resume_jake.png",
    ),
    TemplateInfo(
        id="bold",
        name="Bold Format",
        description="A high-impact creative resume template that commands attention. Designed for marketers, designers, and innovators.",
        thumbnail_url="/resume-templates/resume_bold.png",
    ),
    TemplateInfo(
        id="alternative",
        name="Alternative Format",
        description="A high-density two-column layout with subtle color accents. Ideal for creative professionals looking to maximize space while standing out.",
        thumbnail_url="/resume-templates/resume_alternative.png",
    ),
    TemplateInfo(
        id="highlight",
        name="Highlight Format",
        description="A professional modern template with subtle color accents. Perfect for tech startups and creative professionals maintaining strict ATS compatibility.",
        thumbnail_url="/resume-templates/resume_highlight.png",
    ),
    TemplateInfo(
        id="highlight_compact",
        name="Highlight Compact Format",
        description="A high-density ATS-compatible template with color accents. Maximizes page real estate for seasoned professionals.",
        thumbnail_url="/resume-templates/resume_highlight_compact.png",
    ),
    TemplateInfo(
        id="dev",
        name="Rezi Dev",
        description="The Rezi Dev template — designed to help you create a professional and impactful resume that stands out to recruiters and hiring managers.",
        thumbnail_url="/resume-templates/resume_dev.png",
    ),
    TemplateInfo(
        id="dev_compact",
        name="Rezi Dev Compact",
        description="The Rezi Dev Compact template — a denser version designed for developers with extensive experience.",
        thumbnail_url="/resume-templates/resume_dev_compact.png",
    ),
]

_BY_ID: dict[str, TemplateInfo] = {t.id: t for t in TEMPLATES}


def get_template(template_id: str) -> TemplateInfo | None:
    return _BY_ID.get(template_id)


def list_templates() -> list[TemplateInfo]:
    return list(TEMPLATES)
