"""Render the live incident and asset-exposure audit view for Sentinel."""
import html
import json
from pathlib import Path

ROOT = Path(__file__).parent.parent
INPUT = ROOT / "outputs" / "disaster_demo" / "live_incident_exposure.json"
OUTPUT = ROOT / "materials" / "sentinel_live_operations.html"

data = json.loads(INPUT.read_text())
sources = "".join(f"<li><strong>{html.escape(item['source'])}</strong>: {html.escape(item['status'])} ({item.get('records', 0)} locatable records{'; ' + str(item['notifications_fetched']) + ' notifications ingested' if item.get('notifications_fetched') is not None else ''}){' - ' + html.escape(item['note']) if item.get('note') else ''}</li>" for item in data["source_refreshes"])
rows = ""
for action in data["actions"][:50]:
    priority = float(action["priority_score"])
    colour = "#e53e3e" if priority >= .75 else "#ed8936" if priority >= .55 else "#ecc94b" if priority >= .35 else "#48bb78"
    status = action["approval_status"]
    status_class = "approved" if status == "APPROVED" else "rejected" if status == "REJECTED" else "pending"
    review = action.get("human_review", {})
    review_text = f"<br><small>Reviewed by {html.escape(review.get('reviewer',''))}: {html.escape(review.get('note',''))}</small>" if review else ""
    rows += f"<tr><td>{html.escape(action['asset']['name'])}<br><small>{html.escape(action['asset']['asset_type'])} - {html.escape(action['asset']['criticality'])}</small></td><td>{html.escape(action['event']['title'])}<br><small>{html.escape(action['event']['source'])}</small></td><td>{action['distance_km']:.1f} km</td><td><b style='color:{colour}'>{priority:.3f}</b><br><small>confidence {action['confidence']:.2f}</small></td><td><span class='{status_class}'>{html.escape(status.replace('_',' '))}</span><br><small>{html.escape(action['suggested_action'])}</small>{review_text}</td><td><a href='{html.escape(action['event']['source_url'])}'>Source</a></td></tr>"
if not rows:
    rows = "<tr><td colspan='6'>No asset matches yet. Upload inputs/assets.csv with asset_id, name, asset_type, lat, lon, criticality, population_served, and optional flood_gauge_id.</td></tr>"

OUTPUT.write_text(f"""<!doctype html><html><head><meta charset='utf-8'><title>WAIFINDERS Sentinel - Live Operations</title><style>body{{margin:0;background:#111827;color:#e5e7eb;font:14px -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}}main{{max-width:1400px;margin:auto;padding:28px}}h1{{margin:0;color:#fff}}.subtitle,small{{color:#9ca3af}}.grid{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin:22px 0}}.card{{background:#1f2937;border-radius:10px;padding:18px}}table{{width:100%;border-collapse:collapse;background:#1f2937;border-radius:10px;overflow:hidden}}th{{background:#0f3460;text-align:left}}th,td{{padding:12px;border-bottom:1px solid #374151;vertical-align:top}}a{{color:#93c5fd}}.pending,.approved,.rejected{{display:inline-block;color:#111827;font-weight:800;padding:3px 6px;border-radius:4px;font-size:11px}}.pending{{background:#f59e0b}}.approved{{background:#34d399}}.rejected{{background:#f87171}}.notice{{border-left:4px solid #f59e0b;padding:12px;background:#292524;line-height:1.5}}</style></head><body><main><h1>WAIFINDERS Sentinel</h1><div class='subtitle'>Live Incident & Asset Exposure - refreshed {html.escape(data['generated_utc'])}</div><div class='notice'><strong>Decision support only.</strong> These are exposure matches, not official warnings. Every action is pending trained human approval; verify the linked authoritative source before acting.</div><div class='grid'><section class='card'><h2>Operational snapshot</h2><p><b>{data['live_event_count']}</b> live events ingested<br><b>{data['asset_input']['asset_count']}</b> customer assets loaded<br><b>{data['action_count']}</b> exposure actions ranked</p><p class='subtitle'>Asset file: {html.escape(data['asset_input']['status'])}</p></section><section class='card'><h2>Source refresh health</h2><ul>{sources}</ul></section></div><h2>Prioritized human-review queue</h2><table><thead><tr><th>Asset</th><th>Live event</th><th>Distance</th><th>Priority</th><th>Human decision and next step</th><th>Evidence</th></tr></thead><tbody>{rows}</tbody></table></main></body></html>""")
print(f"Written: {OUTPUT}")
