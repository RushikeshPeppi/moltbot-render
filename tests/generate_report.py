"""
Moltbot HTML Report Generator — Creates a self-contained HTML test report.
Usage: python generate_report.py
"""

import json
from pathlib import Path
from datetime import datetime

RESULTS_FILE = Path(__file__).parent / "results" / "test_results.json"
REPORT_FILE = Path(__file__).parent / "results" / "test_report.html"


def load_results():
    with open(RESULTS_FILE) as f:
        return json.load(f)


def escape(s):
    if not s:
        return ""
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def generate_html(data):
    results = data.get("results", [])
    meta = data.get("meta", {})

    # Stats
    total = len(results)
    passed = sum(1 for r in results if r.get("result") == "pass")
    failed = sum(1 for r in results if r.get("result") == "fail")
    warned = sum(1 for r in results if r.get("result") == "warn")

    # Group by category
    categories = {}
    for r in results:
        cat = r.get("category", "Unknown")
        categories.setdefault(cat, []).append(r)

    # Build rows
    rows_html = ""
    for r in results:
        sid = escape(r.get("scenario_id", ""))
        name = escape(r.get("scenario_name", ""))
        cat = escape(r.get("category", ""))
        msg = escape(r.get("message", ""))
        reply = escape(r.get("agent_reply", ""))
        result = r.get("result", "unknown")
        code = r.get("status_code", "")
        elapsed = r.get("elapsed_seconds", "")
        tz = escape(r.get("timezone", ""))
        img_urls = r.get("image_urls") or []
        verification = r.get("verification") or {}
        v_method = escape(verification.get("method", ""))
        v_verified = verification.get("verified", False)
        v_details = escape(verification.get("details", ""))
        failure = escape(r.get("failure_reason", ""))
        full_resp = escape(json.dumps(r.get("api_response", {}), indent=2, default=str))

        badge_cls = {"pass": "badge-pass", "fail": "badge-fail", "warn": "badge-warn"}.get(result, "badge-warn")
        badge_txt = {"pass": "✅ PASS", "fail": "❌ FAIL", "warn": "⚠️ WARN"}.get(result, "?")
        v_badge = "✅" if v_verified else ("⚠️" if v_method else "—")

        img_html = ""
        if img_urls:
            for u in img_urls:
                img_html += f'<img src="{escape(u)}" class="img-preview" loading="lazy"/>'

        rows_html += f"""
        <tr class="row-{result}" data-cat="{cat}" data-result="{result}">
          <td class="id-col">{sid}</td>
          <td>{name}</td>
          <td class="cat-col">{cat}</td>
          <td class="msg-col">{msg[:80]}{'...' if len(msg)>80 else ''}</td>
          <td class="tz-col">{tz}</td>
          <td><span class="{badge_cls}">{badge_txt}</span></td>
          <td>{code}</td>
          <td>{elapsed}s</td>
          <td class="reply-col">{reply[:150]}{'...' if len(reply)>150 else ''}</td>
          <td>{v_badge} {v_method}</td>
          <td>
            {img_html}
            <details><summary>Full Response</summary><pre class="json-pre">{full_resp}</pre></details>
            {'<div class="v-details">' + v_details[:200] + '</div>' if v_details else ''}
            {'<div class="fail-reason">❌ ' + failure + '</div>' if failure else ''}
          </td>
        </tr>"""

    # Category summary cards
    cat_cards = ""
    for cat, items in categories.items():
        cp = sum(1 for i in items if i.get("result") == "pass")
        ct = len(items)
        pct = round(cp / ct * 100) if ct else 0
        color = "#22c55e" if pct == 100 else "#ef4444" if pct < 50 else "#f59e0b"
        cat_cards += f'<div class="cat-card"><div class="cat-name">{escape(cat)}</div><div class="cat-score" style="color:{color}">{cp}/{ct}</div><div class="cat-pct">{pct}%</div></div>'

    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    pct_total = round(passed / total * 100) if total else 0

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Moltbot Test Report</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:'Inter','Segoe UI',system-ui,sans-serif;background:#0f0f13;color:#e4e4e7;line-height:1.5}}
.container{{max-width:1600px;margin:0 auto;padding:24px}}
h1{{font-size:28px;font-weight:700;background:linear-gradient(135deg,#818cf8,#6366f1);-webkit-background-clip:text;-webkit-text-fill-color:transparent;margin-bottom:4px}}
.subtitle{{color:#71717a;font-size:14px;margin-bottom:24px}}
.stats{{display:flex;gap:16px;margin-bottom:24px;flex-wrap:wrap}}
.stat{{background:#18181b;border:1px solid #27272a;border-radius:12px;padding:16px 24px;min-width:120px}}
.stat-val{{font-size:32px;font-weight:700}}
.stat-label{{font-size:12px;color:#71717a;text-transform:uppercase;letter-spacing:1px}}
.stat-pass .stat-val{{color:#22c55e}} .stat-fail .stat-val{{color:#ef4444}} .stat-warn .stat-val{{color:#f59e0b}} .stat-total .stat-val{{color:#818cf8}}
.cat-grid{{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:24px}}
.cat-card{{background:#18181b;border:1px solid #27272a;border-radius:8px;padding:12px 16px;min-width:130px;text-align:center}}
.cat-name{{font-size:11px;color:#a1a1aa;margin-bottom:4px}} .cat-score{{font-size:20px;font-weight:700}} .cat-pct{{font-size:11px;color:#71717a}}
.filters{{margin-bottom:16px;display:flex;gap:8px;flex-wrap:wrap}}
.filters button{{background:#27272a;border:1px solid #3f3f46;color:#d4d4d8;padding:6px 14px;border-radius:6px;cursor:pointer;font-size:13px}}
.filters button:hover,.filters button.active{{background:#4f46e5;border-color:#6366f1;color:#fff}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
th{{background:#18181b;color:#a1a1aa;padding:10px 8px;text-align:left;border-bottom:2px solid #27272a;position:sticky;top:0;font-weight:600;font-size:11px;text-transform:uppercase;letter-spacing:.5px}}
td{{padding:8px;border-bottom:1px solid #1e1e24;vertical-align:top}}
tr:hover{{background:#1a1a22}}
.row-fail{{background:#1c0f0f}} .row-warn{{background:#1c1a0f}}
.badge-pass{{background:#052e16;color:#22c55e;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600}}
.badge-fail{{background:#2a0a0a;color:#ef4444;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600}}
.badge-warn{{background:#2a1f0a;color:#f59e0b;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600}}
.id-col{{font-weight:700;color:#818cf8;white-space:nowrap}} .cat-col{{color:#a1a1aa;font-size:11px}} .tz-col{{font-size:11px;color:#71717a}}
.msg-col{{max-width:200px}} .reply-col{{max-width:300px;color:#a1a1aa}}
.img-preview{{width:60px;height:60px;object-fit:cover;border-radius:4px;margin:2px;cursor:pointer;border:1px solid #3f3f46}}
.img-preview:hover{{transform:scale(3);position:relative;z-index:10;border-color:#6366f1}}
details summary{{cursor:pointer;color:#6366f1;font-size:11px}} .json-pre{{background:#0a0a0f;padding:8px;border-radius:4px;font-size:10px;max-height:200px;overflow:auto;color:#71717a;white-space:pre-wrap;word-break:break-all}}
.v-details{{font-size:11px;color:#71717a;margin-top:4px}} .fail-reason{{font-size:11px;color:#ef4444;margin-top:4px}}
</style>
</head>
<body>
<div class="container">
<h1>🤖 Moltbot Agent Test Report</h1>
<div class="subtitle">Generated {now} • {total} scenarios • User: {escape(meta.get('user_id', 'usr_84e773f8'))}</div>

<div class="stats">
  <div class="stat stat-total"><div class="stat-val">{total}</div><div class="stat-label">Total</div></div>
  <div class="stat stat-pass"><div class="stat-val">{passed}</div><div class="stat-label">Passed</div></div>
  <div class="stat stat-fail"><div class="stat-val">{failed}</div><div class="stat-label">Failed</div></div>
  <div class="stat stat-warn"><div class="stat-val">{warned}</div><div class="stat-label">Warned</div></div>
  <div class="stat"><div class="stat-val" style="color:{'#22c55e' if pct_total>=90 else '#f59e0b' if pct_total>=70 else '#ef4444'}">{pct_total}%</div><div class="stat-label">Pass Rate</div></div>
</div>

<div class="cat-grid">{cat_cards}</div>

<div class="filters">
  <button class="active" onclick="filterRows('all',this)">All</button>
  <button onclick="filterRows('pass',this)">✅ Passed</button>
  <button onclick="filterRows('fail',this)">❌ Failed</button>
  <button onclick="filterRows('warn',this)">⚠️ Warned</button>
</div>

<table>
<thead><tr>
  <th>ID</th><th>Scenario</th><th>Category</th><th>Message</th><th>TZ</th><th>Result</th><th>Code</th><th>Time</th><th>Agent Reply</th><th>Verified</th><th>Details</th>
</tr></thead>
<tbody>{rows_html}</tbody>
</table>
</div>

<script>
function filterRows(type, btn) {{
  document.querySelectorAll('.filters button').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  document.querySelectorAll('tbody tr').forEach(tr => {{
    tr.style.display = (type === 'all' || tr.dataset.result === type) ? '' : 'none';
  }});
}}
</script>
</body></html>"""
    return html


def main():
    if not RESULTS_FILE.exists():
        print(f"❌ No results file found at {RESULTS_FILE}")
        print("   Run tests first: python run_tests.py")
        return

    data = load_results()
    html = generate_html(data)

    with open(REPORT_FILE, "w") as f:
        f.write(html)

    print(f"✅ Report generated: {REPORT_FILE}")
    print(f"   Open in browser: open {REPORT_FILE}")


if __name__ == "__main__":
    main()
