"""Report delivery — email via AWS SES, Slack webhook, or terminal print."""

import json
import os

import boto3
import requests


def _render_html(report: dict) -> str:
    """Convert final report dict to an HTML email body."""
    lines = [
        "<html><body>",
        f"<h1>Stock Intelligence Report — {report.get('generated_at', '')[:10]}</h1>",
        f"<p><b>Run ID:</b> {report.get('run_id', '')}</p>",
        f"<p><b>Market Regime:</b> {report.get('market_regime', {}).get('label', 'N/A')}</p>",
        f"<p><b>Causal Summary:</b> {report.get('causal_summary', '')}</p>",
        "<hr/>",
    ]

    for horizon_data in report.get("horizons", []):
        horizon = horizon_data.get("horizon", "")
        lines.append(f"<h2>{horizon.replace('_', ' ').title()} Picks</h2>")

        lines.append("<h3>Buys</h3><ul>")
        for pick in horizon_data.get("picks", []):
            lines.append(
                f"<li><b>{pick['ticker']}</b> — {pick['signal']} "
                f"({pick['confidence']}% confidence)<br/>"
                f"{pick.get('thesis', '')}</li>"
            )
        lines.append("</ul>")

        if horizon_data.get("contrarian_picks"):
            lines.append("<h3>Contrarian</h3><ul>")
            for pick in horizon_data["contrarian_picks"]:
                lines.append(f"<li><b>{pick['ticker']}</b> — {pick.get('thesis', '')}</li>")
            lines.append("</ul>")

        if horizon_data.get("avoid"):
            lines.append("<h3>Avoid</h3><ul>")
            for pick in horizon_data["avoid"]:
                lines.append(f"<li><b>{pick['ticker']}</b> — {pick.get('thesis', '')}</li>")
            lines.append("</ul>")

    lines.append(f"<hr/><p><i>{report.get('analyst_note', '')}</i></p>")
    lines.append("</body></html>")
    return "\n".join(lines)


def _deliver_email(report: dict) -> None:
    sender = os.environ["SES_SENDER_EMAIL"]
    recipient = os.environ["SES_RECIPIENT_EMAIL"]
    run_date = report.get("generated_at", "")[:10]

    ses = boto3.client("ses", region_name=os.environ.get("AWS_REGION", "us-east-1"))
    ses.send_email(
        Source=sender,
        Destination={"ToAddresses": [recipient]},
        Message={
            "Subject": {"Data": f"Stock Intelligence Report — {run_date}"},
            "Body": {
                "Html": {"Data": _render_html(report)},
                "Text": {"Data": json.dumps(report, indent=2)},
            },
        },
    )
    print(f"[delivery] Email sent to {recipient}")


def _deliver_slack(report: dict) -> None:
    webhook = os.environ.get("SLACK_WEBHOOK_URL", "")
    if not webhook:
        raise ValueError("SLACK_WEBHOOK_URL not set")

    run_date = report.get("generated_at", "")[:10]
    text = f"*Stock Intelligence Report — {run_date}*\n"

    for h in report.get("horizons", []):
        picks = h.get("picks", [])
        if picks:
            tickers = ", ".join(p["ticker"] for p in picks)
            text += f"\n*{h['horizon']}*: {tickers}"

    resp = requests.post(webhook, json={"text": text}, timeout=10)
    resp.raise_for_status()
    print("[delivery] Slack message sent")


def _deliver_terminal(report: dict) -> None:
    print("\n" + "=" * 70)
    print("STOCK INTELLIGENCE REPORT")
    print("=" * 70)
    print(json.dumps(report, indent=2))


def deliver_report(report: dict, method: str | None = None) -> None:
    """Dispatch report via configured delivery method."""
    if method is None:
        import yaml
        cfg_path = os.path.join(os.path.dirname(__file__), "..", "config.yaml")
        with open(cfg_path) as f:
            cfg = yaml.safe_load(f)
        method = cfg.get("delivery", {}).get("method", "terminal")

    if method == "email":
        _deliver_email(report)
    elif method == "slack":
        _deliver_slack(report)
    else:
        _deliver_terminal(report)
