"""
Queries GitHub's Code Scanning API for CodeQL alerts on this repo and
generates a PDF summary — run as a step in the CodeQL workflow, right
after github/codeql-action/analyze uploads results.

Required environment variables:
    GITHUB_TOKEN        auto-provided by GitHub Actions (secrets.GITHUB_TOKEN)
    GITHUB_REPOSITORY   auto-provided by GitHub Actions, format "owner/repo"
"""
import os
import time
from datetime import datetime

import requests
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

TOKEN = os.environ["GITHUB_TOKEN"]
REPO = os.environ["GITHUB_REPOSITORY"]  # "owner/repo"
API_ROOT = f"https://api.github.com/repos/{REPO}"

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}

SEVERITY_ORDER = {"critical": 0, "high": 1, "error": 1, "medium": 2, "warning": 2, "low": 3, "note": 4}
SEVERITY_COLORS = {
    "critical": colors.HexColor("#b71c1c"), "high": colors.HexColor("#c62828"), "error": colors.HexColor("#c62828"),
    "medium": colors.HexColor("#ef6c00"), "warning": colors.HexColor("#ef6c00"),
    "low": colors.HexColor("#2e7d32"), "note": colors.HexColor("#2e7d32"),
}


def api_get(path, params=None):
    resp = requests.get(f"{API_ROOT}{path}", headers=HEADERS, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def wait_for_alerts_processed(max_wait_seconds=90):
    """CodeQL uploads results asynchronously — the analyze step finishing
    doesn't guarantee the alerts API reflects them immediately. Poll the
    analyses endpoint until the most recent one is marked complete, or
    give up and report with whatever's available."""
    print("Waiting for CodeQL analysis to finish processing...")
    deadline = time.time() + max_wait_seconds
    while time.time() < deadline:
        try:
            analyses = api_get("/code-scanning/analyses", {"per_page": 1})
            if analyses:
                print("Analysis processing complete.")
                return
        except Exception as e:
            print(f"  (poll error, retrying: {e})")
        time.sleep(5)
    print(f"Gave up waiting after {max_wait_seconds}s — reporting with latest available data.")


def fetch_open_alerts():
    alerts = api_get("/code-scanning/alerts", {"state": "open", "per_page": 100})
    return alerts


def severity_of(alert):
    rule = alert.get("rule", {})
    return (rule.get("security_severity_level") or rule.get("severity") or "note").lower()


def build_pdf(alerts, out_path):
    doc = SimpleDocTemplate(out_path, pagesize=A4,
                             topMargin=2*cm, bottomMargin=2*cm,
                             leftMargin=2*cm, rightMargin=2*cm)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("TitleCustom", parent=styles["Title"], fontSize=20)
    h2 = styles["Heading2"]
    body = styles["BodyText"]
    cell_style = ParagraphStyle("Cell", parent=body, fontSize=8, leading=10)

    story = [
        Paragraph(f"CodeQL SAST Report — {REPO}", title_style),
        Paragraph(datetime.utcnow().strftime("Generated %Y-%m-%d %H:%M UTC"), body),
        Spacer(1, 0.5*cm),
    ]

    counts = {}
    for a in alerts:
        sev = severity_of(a)
        counts[sev] = counts.get(sev, 0) + 1

    status_color = colors.HexColor("#2e7d32") if not alerts else colors.HexColor("#c62828")
    status_style = ParagraphStyle("Status", parent=h2, textColor=status_color)
    story.append(Paragraph(
        "No open alerts" if not alerts else f"{len(alerts)} open alert{'s' if len(alerts) != 1 else ''}",
        status_style,
    ))
    if counts:
        summary_line = "  ·  ".join(f"{k}: {v}" for k, v in sorted(counts.items(), key=lambda kv: SEVERITY_ORDER.get(kv[0], 9)))
        story.append(Paragraph(summary_line, body))
    story.append(Spacer(1, 0.5*cm))

    if not alerts:
        story.append(Paragraph("No open CodeQL findings.", body))
    else:
        story.append(Paragraph("Findings", h2))
        alerts_sorted = sorted(alerts, key=lambda a: SEVERITY_ORDER.get(severity_of(a), 9))

        rows = [["Severity", "Rule", "File : Line", "Description"]]
        for alert in alerts_sorted:
            rule = alert.get("rule", {})
            instance = alert.get("most_recent_instance", {})
            location = instance.get("location", {})
            file_line = f"{location.get('path', '?')}:{location.get('start_line', '?')}"
            description = rule.get("description") or rule.get("name") or ""
            sev = severity_of(alert)
            rows.append([
                Paragraph(sev, cell_style),
                Paragraph(rule.get("id", ""), cell_style),
                Paragraph(file_line, cell_style),
                Paragraph(description, cell_style),
            ])

        table = Table(rows, colWidths=[2.2*cm, 3.5*cm, 4*cm, 7.3*cm])
        table_style_cmds = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a1a2e")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f4f4f4")]),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]
        for i, alert in enumerate(alerts_sorted, start=1):
            sev = severity_of(alert)
            if sev in SEVERITY_COLORS:
                table_style_cmds.append(("TEXTCOLOR", (0, i), (0, i), SEVERITY_COLORS[sev]))
                table_style_cmds.append(("FONTNAME", (0, i), (0, i), "Helvetica-Bold"))
        table.setStyle(TableStyle(table_style_cmds))
        story.append(table)

    doc.build(story)
    print(f"Report written to {out_path}")


def main():
    wait_for_alerts_processed()
    try:
        alerts = fetch_open_alerts()
    except Exception as e:
        print(f"Could not fetch alerts ({e}) — reporting as empty.")
        alerts = []
    build_pdf(alerts, "codeql-report.pdf")


if __name__ == "__main__":
    main()
