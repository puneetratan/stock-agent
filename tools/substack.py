"""
Substack-ready HTML report formatter.

Generates a clean, readable HTML post that can be:
  1. Copy-pasted directly into Substack's HTML editor
  2. Saved as a .html file and opened in browser
  3. Sent as a rich email via SES

Substack strips most CSS, so we use only inline styles and
standard HTML elements that survive the paste.
"""

import os
from datetime import datetime, timezone


def _signal_emoji(signal: str) -> str:
    return {"BUY": "🟢", "AVOID": "🔴", "HOLD": "🟡", "SELL": "🔴"}.get(signal.upper(), "⚪")


def _horizon_label(horizon: str) -> str:
    return {
        "quarter":   "Q2 2026 — Short Term",
        "one_year":  "1 Year — Medium Term",
        "two_year":  "2 Years — Position Build",
        "five_year": "5 Years — Structural",
        "ten_year":  "10 Years — Generational",
    }.get(horizon, horizon.replace("_", " ").title())


def _confidence_bar(confidence: int) -> str:
    filled = round(confidence / 10)
    empty  = 10 - filled
    return "█" * filled + "░" * empty + f" {confidence}%"


def render_substack_html(report: dict) -> str:
    """Convert a FinalReport dict into Substack-ready HTML."""

    run_date   = report.get("generated_at", "")[:10]
    regime     = report.get("market_regime") or {}
    causal     = report.get("causal_summary", "")
    note       = report.get("analyst_note", "")
    horizons   = report.get("horizons", [])
    screened   = report.get("stocks_screened", 0)
    analysed   = report.get("stocks_deep_analysed", 0)

    lines = []

    # ── Header ──────────────────────────────────────────────────────────
    lines.append(f"""
<h1 style="font-size:28px;font-weight:700;margin-bottom:4px;">
  Stock Intelligence Report
</h1>
<p style="color:#666;font-size:14px;margin-top:0;">{run_date} &nbsp;·&nbsp;
  {screened} stocks screened &nbsp;·&nbsp; {analysed} deep analysed
</p>
<hr style="border:none;border-top:2px solid #000;margin:24px 0;">
""")

    # ── Market Regime ────────────────────────────────────────────────────
    if regime:
        lines.append(f"""
<h2 style="font-size:20px;font-weight:700;">📊 Market Regime: {regime.get('label','')}</h2>
<p style="font-size:15px;line-height:1.6;">{regime.get('description','')}</p>
<p style="background:#f5f5f5;padding:12px 16px;border-left:4px solid #000;
          font-size:14px;margin:0;">
  <strong>Posture:</strong> {regime.get('recommended_posture','')}
</p>
<br>
""")

    # ── Causal Summary ───────────────────────────────────────────────────
    if causal:
        lines.append(f"""
<h2 style="font-size:20px;font-weight:700;">🌍 What's Driving Markets</h2>
<p style="font-size:15px;line-height:1.7;">{causal}</p>
<hr style="border:none;border-top:1px solid #ddd;margin:24px 0;">
""")

    # ── Picks per Horizon ────────────────────────────────────────────────
    for horizon_data in horizons:
        horizon  = horizon_data.get("horizon", "")
        picks    = horizon_data.get("picks", [])
        avoid    = horizon_data.get("avoid", [])
        contrary = horizon_data.get("contrarian_picks", [])

        if not picks and not contrary and not avoid:
            continue

        lines.append(f"""
<h2 style="font-size:20px;font-weight:700;margin-bottom:4px;">
  ⏱ {_horizon_label(horizon)}
</h2>
""")

        # BUY picks
        if picks:
            lines.append("<h3 style='font-size:16px;font-weight:600;color:#1a7f37;'>Buys</h3>")
            for pick in picks:
                ticker     = pick.get("ticker", "")
                confidence = pick.get("confidence", 0)
                thesis     = pick.get("thesis", "")
                risks      = pick.get("risks", [])
                themes     = pick.get("theme_ids", [])

                lines.append(f"""
<div style="border:1px solid #e0e0e0;border-radius:6px;padding:16px;
            margin-bottom:12px;background:#fafffe;">
  <div style="display:flex;justify-content:space-between;align-items:center;">
    <span style="font-size:22px;font-weight:700;">{ticker}</span>
    <span style="font-size:13px;color:#555;font-family:monospace;">
      {_confidence_bar(confidence)}
    </span>
  </div>
  <p style="font-size:14px;line-height:1.6;margin:8px 0 4px;">{thesis}</p>
  {"<p style='font-size:12px;color:#888;margin:4px 0;'>Themes: " + ", ".join(themes) + "</p>" if themes else ""}
  {"<p style='font-size:12px;color:#c0392b;margin:4px 0;'>⚠ " + " · ".join(risks) + "</p>" if risks else ""}
</div>
""")

        # Contrarian picks
        if contrary:
            lines.append("<h3 style='font-size:16px;font-weight:600;color:#7d3c98;'>Contrarian</h3>")
            for pick in contrary:
                ticker = pick.get("ticker", "")
                thesis = pick.get("thesis", "")
                conf   = pick.get("confidence", 0)
                lines.append(f"""
<div style="border:1px solid #d2b4de;border-radius:6px;padding:16px;
            margin-bottom:12px;background:#fdf9ff;">
  <span style="font-size:20px;font-weight:700;">🔀 {ticker}</span>
  <span style="font-size:13px;color:#555;font-family:monospace;margin-left:12px;">
    {_confidence_bar(conf)}
  </span>
  <p style="font-size:14px;line-height:1.6;margin:8px 0 0;">{thesis}</p>
</div>
""")

        # Avoid
        if avoid:
            lines.append("<h3 style='font-size:16px;font-weight:600;color:#c0392b;'>Avoid</h3>")
            for pick in avoid:
                ticker = pick.get("ticker", "")
                thesis = pick.get("thesis", "")
                lines.append(f"""
<div style="border:1px solid #f5c6cb;border-radius:6px;padding:12px 16px;
            margin-bottom:8px;background:#fff8f8;">
  <span style="font-size:18px;font-weight:700;">🚫 {ticker}</span>
  <p style="font-size:14px;line-height:1.6;margin:6px 0 0;">{thesis}</p>
</div>
""")

        lines.append("<hr style='border:none;border-top:1px solid #ddd;margin:24px 0;'>")

    # ── Analyst Note ─────────────────────────────────────────────────────
    if note:
        lines.append(f"""
<h2 style="font-size:20px;font-weight:700;">📝 Analyst Note</h2>
<p style="font-size:15px;line-height:1.7;font-style:italic;
          background:#fffbf0;padding:16px;border-left:4px solid #f39c12;">
  {note}
</p>
""")

    # ── Footer ───────────────────────────────────────────────────────────
    lines.append(f"""
<hr style="border:none;border-top:1px solid #ddd;margin:32px 0 16px;">
<p style="font-size:12px;color:#999;line-height:1.6;">
  Generated by Stock Intelligence Agent on {run_date}.<br>
  This is not financial advice. Do your own research before investing.
  Past signals are not indicative of future performance.
</p>
""")

    return "\n".join(lines)


def save_substack_post(report: dict, output_dir: str = ".") -> str:
    """
    Save the report as a standalone HTML file.
    Returns the file path.
    """
    run_date = report.get("generated_at", "")[:10]
    html_body = render_substack_html(report)

    full_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Stock Intelligence Report — {run_date}</title>
  <style>
    body {{ max-width: 680px; margin: 40px auto; padding: 0 20px;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            color: #1a1a1a; line-height: 1.5; }}
  </style>
</head>
<body>
{html_body}
</body>
</html>"""

    filename = os.path.join(output_dir, f"report_{run_date}.html")
    with open(filename, "w") as f:
        f.write(full_html)

    return filename
