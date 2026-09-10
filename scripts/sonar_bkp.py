"""
Generates a PDF summary of a SonarQube/SonarCloud analysis by querying the
Web API directly — this exists because PDF export is a paid SonarQube
feature (Developer Edition+ / SonarCloud paid tiers); this is the free
equivalent, run as a GitHub Actions step right after the scan.

Usage:
    python scripts/generate_sonar_report.py

Required environment variables:
    SONAR_HOST_URL   e.g. https://sonarcloud.io
    SONAR_TOKEN      same token used for the scan itself
    SONAR_PROJECT_KEY  from sonar-project.properties (sonar.projectKey)
    SONAR_ORGANIZATION  only needed for SonarCloud, omit for self-hosted
"""
import os
import sys
import time
from datetime import datetime

import requests
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak,
)

HOST = os.environ["SONAR_HOST_URL"].rstrip("/")
TOKEN = os.environ["SONAR_TOKEN"]
PROJECT_KEY = os.environ["SONAR_PROJECT_KEY"]
ORGANIZATION = os.environ.get("SONAR_ORGANIZATION", "")

AUTH = (TOKEN, "")  # SonarQube Web API uses basic auth with the token as username

METRIC_KEYS = [
    "bugs", "vulnerabilities", "code_smells", "security_hotspots",
    "coverage", "duplicated_lines_density", "ncloc",
    "reliability_rating", "security_rating", "sqale_rating",
]
RATING_LABELS = {"1.0": "A", "2.0": "B", "3.0": "C", "4.0": "D", "5.0": "E"}


def api_get(path, params=None):
    params = dict(params or {})
    if ORGANIZATION:
        params.setdefault("organization", ORGANIZATION)
    resp = requests.get(f"{HOST}{path}", params=params, auth=AUTH, timeout=30)
    resp.raise_for_status()
    return resp.json()


def wait_for_analysis(max_wait_seconds=120):
    """SonarQube processes an upload asynchronously — poll until the
    project's last analysis timestamp is recent, or give up after
    max_wait_seconds and report with whatever's there."""
    print("Waiting for SonarQube to finish processing the analysis...")
    deadline = time.time() + max_wait_seconds
    last_status = None
    while time.time() < deadline:
        try:
            data = api_get("/api/ce/component", {"component": PROJECT_KEY})
            queue = data.get("queue", [])
            if not queue:
                print("Analysis processing complete.")
                return
            last_status = queue[0].get("status")
        except Exception as e:
            print(f"  (poll error, retrying: {e})")
        time.sleep(5)
    print(f"Gave up waiting after {max_wait_seconds}s (last status: {last_status}) — reporting with latest available data.")


def fetch_quality_gate():
    data = api_get("/api/qualitygates/project_status", {"projectKey": PROJECT_KEY})
    return data["projectStatus"]


def fetch_measures():
    data = api_get("/api/measures/component", {
        "component": PROJECT_KEY,
        "metricKeys": ",".join(METRIC_KEYS),
    })
    measures = {m["metric"]: m.get("value", "—") for m in data["component"]["measures"]}
    return measures


def fetch_top_issues(limit=25):
    data = api_get("/api/issues/search", {
        "componentKeys": PROJECT_KEY,
        "resolved": "false",
        "severities": "BLOCKER,CRITICAL,MAJOR",
        "ps": limit,
    })
    return data.get("issues", []), data.get("total", 0)


def rating_label(value):
    return RATING_LABELS.get(value, value)


def build_pdf(measures, quality_gate, issues, total_issues, out_path):
    doc = SimpleDocTemplate(out_path, pagesize=A4,
                             topMargin=2*cm, bottomMargin=2*cm,
                             leftMargin=2*cm, rightMargin=2*cm)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("TitleCustom", parent=styles["Title"], fontSize=20)
    h2 = styles["Heading2"]
    body = styles["BodyText"]

    story = []
    story.append(Paragraph(f"SonarQube Analysis Report — {PROJECT_KEY}", title_style))
    story.append(Paragraph(datetime.utcnow().strftime("Generated %Y-%m-%d %H:%M UTC"), body))
    story.append(Spacer(1, 0.5*cm))

    # quality gate banner
    gate_status = quality_gate.get("status", "UNKNOWN")
    gate_color = colors.HexColor("#2e7d32") if gate_status == "OK" else colors.HexColor("#c62828")
    gate_style = ParagraphStyle("Gate", parent=h2, textColor=gate_color)
    story.append(Paragraph(f"Quality Gate: {'PASSED' if gate_status == 'OK' else 'FAILED'}", gate_style))
    story.append(Spacer(1, 0.3*cm))

    # metrics table
    story.append(Paragraph("Key Metrics", h2))
    metric_rows = [
        ["Metric", "Value"],
        ["Bugs", measures.get("bugs", "—")],
        ["Vulnerabilities", measures.get("vulnerabilities", "—")],
        ["Code Smells", measures.get("code_smells", "—")],
        ["Security Hotspots", measures.get("security_hotspots", "—")],
        ["Coverage", f"{measures.get('coverage', '—')}%"],
        ["Duplicated Lines", f"{measures.get('duplicated_lines_density', '—')}%"],
        ["Lines of Code", measures.get("ncloc", "—")],
        ["Reliability Rating", rating_label(measures.get("reliability_rating", "—"))],
        ["Security Rating", rating_label(measures.get("security_rating", "—"))],
        ["Maintainability Rating", rating_label(measures.get("sqale_rating", "—"))],
    ]
    metric_table = Table(metric_rows, colWidths=[8*cm, 6*cm])
    metric_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a1a2e")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f4f4f4")]),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(metric_table)
    story.append(Spacer(1, 0.6*cm))

    # top issues
    story.append(Paragraph(f"Top Issues (showing {len(issues)} of {total_issues} open)", h2))
    if not issues:
        story.append(Paragraph("No open Blocker/Critical/Major issues. 🎉", body))
    else:
        cell_style = ParagraphStyle("Cell", parent=body, fontSize=8, leading=10)
        issue_rows = [["Severity", "Type", "File", "Message"]]
        for issue in issues:
            component = issue.get("component", "").split(":")[-1]
            issue_rows.append([
                Paragraph(issue.get("severity", ""), cell_style),
                Paragraph(issue.get("type", ""), cell_style),
                Paragraph(component, cell_style),
                Paragraph(issue.get("message", ""), cell_style),
            ])
        issue_table = Table(issue_rows, colWidths=[2.3*cm, 2.5*cm, 4*cm, 7*cm])
        issue_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a1a2e")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f4f4f4")]),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(issue_table)

    doc.build(story)
    print(f"Report written to {out_path}")


def main():
    wait_for_analysis()
    try:
        quality_gate = fetch_quality_gate()
    except Exception as e:
        print(f"Could not fetch quality gate status ({e}) — continuing with UNKNOWN.")
        quality_gate = {"status": "UNKNOWN"}
    measures = fetch_measures()
    issues, total_issues = fetch_top_issues()

    out_path = "sonarqube-report.pdf"
    build_pdf(measures, quality_gate, issues, total_issues, out_path)


if __name__ == "__main__":
    main()
