from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"  # app/templates


def generate_report_pdf(case_id: str, report_data: Dict[str, Any], output_path: str) -> None:
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))
    template = env.get_template("report.html")

    html = template.render(case_id=case_id, data=report_data)

    HTML(string=html, base_url=str(TEMPLATES_DIR)).write_pdf(str(out))
