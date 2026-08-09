"""Build Sentinel multi-hazard demo HTML from real output JSON files."""
import json
from pathlib import Path

OUT  = Path("outputs/disaster_demo")
HTML = Path("materials/sentinel_multihazard_demo.html")

eq   = json.loads((OUT / "warn_earthquake_events.json").read_text())
ts   = json.loads((OUT / "warn_tsunami_events.json").read_text())
fl   = json.loads((OUT / "warn_flood_surge_events.json").read_text())
pu   = json.loads((OUT / "pulse_disaster_exposure.json").read_text())
wi   = json.loads((OUT / "wise_multihazard_decision.json").read_text())

eq_top  = sorted(eq["events"], key=lambda e: -float(e.get("warn_score",0)))[:8]
ts_top  = sorted(ts["events"], key=lambda e: -float(str(e.get("warn_score","0")) or 0))[:8]
ts_top  = [e for e in ts_top if float(str(e.get("warn_score","0")) or 0) > 0]

TIER_COLOR = {
    "EMERGENCY_RESPONSE":  "#e53e3e",
    "MITIGATION_REQUIRED": "#ed8936",
    "MONITOR":             "#ecc94b",
    "NORMAL_OPERATION":    "#48bb78",
}
TIER_LABEL = {
    "EMERGENCY_RESPONSE":  "EMERGENCY",
    "MITIGATION_REQUIRED": "MITIGATE",
    "MONITOR":             "MONITOR",
    "NORMAL_OPERATION":    "NORMAL",
}

def tier_badge(tier, small=False):
    c = TIER_COLOR.get(tier, "#999")
    l = TIER_LABEL.get(tier, tier)
    fs = "10px" if small else "12px"
    return f'<span style="background:{c};color:#000;padding:2px 7px;border-radius:3px;font-weight:700;font-size:{fs};letter-spacing:0.04em">{l}</span>'

def score_bar(score, tier):
    c = TIER_COLOR.get(tier, "#999")
    pct = int(float(score)*100)
    return f'<div style="background:#333;border-radius:3px;height:6px;width:100%"><div style="background:{c};width:{pct}%;height:6px;border-radius:3px"></div></div>'

wise_color = TIER_COLOR.get(wi["wise_decision"], "#999")
wise_label = TIER_LABEL.get(wi["wise_decision"], wi["wise_decision"])

# earthquake rows
eq_rows = ""
for e in eq_top:
    s = float(e.get("warn_score", 0))
    tier = e.get("warn_tier", "NORMAL_OPERATION")
    eq_rows += f"""<tr>
      <td style="padding:6px 8px;font-size:12px;color:#ccc">{str(e.get("time_utc",""))[:10]}</td>
      <td style="padding:6px 8px;font-size:12px;color:#eee">{e.get("place","")[:45]}</td>
      <td style="padding:6px 8px;font-size:13px;font-weight:700;color:#fff">{e.get("magnitude","")}</td>
      <td style="padding:6px 8px;font-size:12px;color:#ccc">{e.get("depth_km",""):.0f} km</td>
      <td style="padding:6px 8px">{score_bar(s,tier)}<span style="font-size:11px;color:#aaa">{s:.3f}</span></td>
      <td style="padding:6px 8px">{tier_badge(tier, small=True)}</td>
    </tr>"""

# 1700 analogue row
eq_rows += f"""<tr style="border-top:1px solid #555">
  <td style="padding:6px 8px;font-size:12px;color:#888">1700-01-26</td>
  <td style="padding:6px 8px;font-size:12px;color:#ffd700">&#9733; Cascadia 1700 (M9.0 analogue)</td>
  <td style="padding:6px 8px;font-size:13px;font-weight:700;color:#ffd700">9.0</td>
  <td style="padding:6px 8px;font-size:12px;color:#ccc">20 km</td>
  <td style="padding:6px 8px">{score_bar(0.748,"EMERGENCY_RESPONSE")}<span style="font-size:11px;color:#aaa">0.748</span></td>
  <td style="padding:6px 8px">{tier_badge("EMERGENCY_RESPONSE", small=True)}</td>
</tr>"""

# tsunami rows
ts_rows = ""
for e in ts_top:
    s = float(str(e.get("warn_score","0")) or 0)
    tier = e.get("warn_tier","NORMAL_OPERATION")
    wh = e.get("max_wave_height_m","")
    mag = e.get("source_mag","")
    ts_rows += f"""<tr>
      <td style="padding:6px 8px;font-size:12px;color:#ccc">{e.get("year","")}</td>
      <td style="padding:6px 8px;font-size:12px;color:#eee">{e.get("location","")[:30]}</td>
      <td style="padding:6px 8px;font-size:12px;color:#ccc">{e.get("country","")[:12]}</td>
      <td style="padding:6px 8px;font-size:13px;font-weight:700;color:#fff">{wh} m</td>
      <td style="padding:6px 8px;font-size:12px;color:#ccc">{mag}</td>
      <td style="padding:6px 8px">{score_bar(s,tier)}<span style="font-size:11px;color:#aaa">{s:.3f}</span></td>
      <td style="padding:6px 8px">{tier_badge(tier, small=True)}</td>
    </tr>"""

# flood rows
fl_rows = ""
for e in fl["events"]:
    s = float(e.get("warn_score",0))
    tier = e.get("warn_tier","NORMAL_OPERATION")
    fl_rows += f"""<tr>
      <td style="padding:6px 8px;font-size:12px;color:#eee">{e.get("name","")}</td>
      <td style="padding:6px 8px;font-size:12px;color:#ccc">{e.get("label","")}</td>
      <td style="padding:6px 8px;font-size:13px;font-weight:700;color:#fff">{e.get("peak_water_level_m_above_mhhw","")} m</td>
      <td style="padding:6px 8px">{score_bar(s,tier)}<span style="font-size:11px;color:#aaa">{s:.3f}</span></td>
      <td style="padding:6px 8px">{tier_badge(tier, small=True)}</td>
      <td style="padding:6px 8px;font-size:10px;color:#888">{e.get("fetch_status","")}</td>
    </tr>"""

# PULSE summary
pu_summary = pu.get("risk_summary", {})
total_bridges = sum(pu_summary.values()) or 1
pri_bridges = pu.get("priority_bridges", [])

pulse_bars = ""
for band, color in [("RED","#e53e3e"),("AMBER","#ed8936"),("YELLOW","#ecc94b"),("GREEN","#48bb78")]:
    n = pu_summary.get(band, 0)
    pct = n / total_bridges * 100
    pulse_bars += f"""<div style="display:flex;align-items:center;gap:10px;margin:4px 0">
      <span style="width:60px;font-size:12px;font-weight:700;color:{color}">{band}</span>
      <div style="flex:1;background:#333;border-radius:3px;height:10px">
        <div style="background:{color};width:{pct:.1f}%;height:10px;border-radius:3px"></div>
      </div>
      <span style="font-size:12px;color:#aaa;width:60px">{n} ({pct:.1f}%)</span>
    </div>"""

# Priority bridge rows
pri_rows = ""
for b in pri_bridges[:10]:
    band = b.get("risk_band","")
    c = TIER_COLOR.get({"RED":"EMERGENCY_RESPONSE","AMBER":"MITIGATION_REQUIRED","YELLOW":"MONITOR","GREEN":"NORMAL_OPERATION"}.get(band,""), "#999")
    pri_rows += f"""<tr>
      <td style="padding:5px 8px;font-size:11px;color:#ccc">{b.get("bin","")}</td>
      <td style="padding:5px 8px;font-size:11px;color:#eee">{b.get("county","")}</td>
      <td style="padding:5px 8px;font-size:11px;color:#aaa">{b.get("seismic_zone","")}</td>
      <td style="padding:5px 8px;font-size:11px;color:#aaa">{"Yes" if b.get("tsunami_zone") else "No"}</td>
      <td style="padding:5px 8px;font-size:12px;font-weight:700;color:{c}">{band}</td>
      <td style="padding:5px 8px;font-size:11px;color:#aaa">{float(b.get("compound_score",0)):.3f}</td>
    </tr>"""

# WISE actions
action_items = ""
for a in wi.get("recommended_actions", []):
    action_items += f'<li style="margin:5px 0;font-size:13px;color:#e2e8f0">{a}</li>'

# Hazard signal rows
signal_rows = ""
sigs = wi.get("hazard_signals", {})
for hazard, data in [
    ("Wildfire", sigs.get("wildfire",{})),
    ("Earthquake", sigs.get("earthquake",{})),
    ("Tsunami", sigs.get("tsunami",{})),
    ("Flood Surge", sigs.get("flood_surge",{})),
    ("Hurricane", sigs.get("hurricane",{})),
    ("Nuclear Baseline", sigs.get("nuclear",{})),
]:
    s = float(data.get("score", 0))
    tier = data.get("tier","NORMAL_OPERATION")
    signal_rows += f"""<tr>
      <td style="padding:8px;font-size:13px;color:#ddd">{hazard}{' <span style="font-size:10px;color:#718096">(planning)</span>' if data.get('decision_inclusion') is False else ''}</td>
      <td style="padding:8px">{score_bar(s,tier)}<span style="font-size:11px;color:#aaa">{s:.3f}</span></td>
      <td style="padding:8px">{tier_badge(tier, small=True)}</td>
    </tr>"""

# Pulse WISE row
pu_tier = wi.get("pulse_state",{}).get("tier","NORMAL_OPERATION")
signal_rows += f"""<tr>
  <td style="padding:8px;font-size:13px;color:#ddd">PULSE Infra</td>
  <td style="padding:8px">{score_bar(pu_summary.get("RED",0)/total_bridges, pu_tier)}<span style="font-size:11px;color:#aaa">{pu_summary.get("RED",0)} RED of {total_bridges}</span></td>
  <td style="padding:8px">{tier_badge(pu_tier, small=True)}</td>
</tr>"""

compound_note = ""
if wi.get("compound_event"):
    elevated = ", ".join(wi.get("elevated_hazards",[]))
    compound_note = f'<div style="background:#2d3748;border-left:3px solid #ed8936;padding:10px 14px;margin:12px 0;font-size:13px;color:#fed7aa">⚠ Compound event: <strong>{elevated}</strong> — decision escalated one level above worst individual hazard</div>'

html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>WAIFINDERS Sentinel — Multi-Hazard Demo</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#1a202c;color:#e2e8f0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;padding:20px}}
h1{{font-size:22px;font-weight:700;letter-spacing:0.05em;color:#fff}}
h2{{font-size:14px;font-weight:600;letter-spacing:0.08em;color:#90cdf4;text-transform:uppercase;margin-bottom:10px}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:16px}}
.grid3{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:16px;margin-top:16px}}
.card{{background:#2d3748;border-radius:8px;padding:16px}}
.card-full{{background:#2d3748;border-radius:8px;padding:16px;grid-column:1/-1}}
table{{width:100%;border-collapse:collapse}}
th{{font-size:11px;color:#718096;text-align:left;padding:5px 8px;border-bottom:1px solid #4a5568;letter-spacing:0.05em}}
tr:hover td{{background:#374151}}
.disclaimer{{background:#1a202c;border:1px solid #4a5568;border-radius:6px;padding:12px;margin-top:20px;font-size:11px;color:#718096;line-height:1.6}}
.wise-box{{border:2px solid {wise_color};border-radius:8px;padding:20px;background:#2d3748}}
.wise-label{{font-size:32px;font-weight:900;color:{wise_color};letter-spacing:0.05em}}
.data-badge{{display:inline-block;background:#2d3748;border:1px solid #4a5568;border-radius:4px;padding:2px 8px;font-size:10px;color:#718096;margin-top:4px}}
</style>
</head>
<body>

<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:20px">
  <div>
    <h1>WAIFINDERS Sentinel</h1>
    <div style="font-size:12px;color:#718096;margin-top:4px">Multi-Hazard Operational Intelligence Demo &nbsp;·&nbsp; {wi.get("generated_utc","")[:19]} UTC</div>
    <div class="data-badge">Real data: USGS · NOAA NCEI · NOAA CO-OPS · NY State DOT</div>
  </div>
  <div style="text-align:right">
    <div style="font-size:11px;color:#718096;margin-bottom:4px">WISE HISTORICAL PEAK</div>
    <div class="wise-label">{wise_label}</div>
    <div style="font-size:11px;color:#718096;margin-top:4px">Historical catalogue · not a live alert</div>
  </div>
</div>

<div class="grid">

<!-- WISE Engine -->
<div class="wise-box">
  <h2>WISE — Historical Scenario Engine</h2>
  {compound_note}
  <table>
    <thead><tr><th>HAZARD</th><th style="width:55%">WARN SCORE</th><th>TIER</th></tr></thead>
    <tbody>{signal_rows}</tbody>
  </table>
  <div style="margin-top:14px">
    <div style="font-size:11px;color:#718096;margin-bottom:6px">RECOMMENDED ACTIONS</div>
    <ul style="padding-left:18px">{action_items}</ul>
  </div>
  <div style="margin-top:10px;font-size:10px;color:#4a5568">Cost: {wi.get("cost_estimate_illustrative",{}).get("label","")} — ILLUSTRATIVE. {wi.get("cost_estimate_illustrative",{}).get("note","")}</div>
</div>

<!-- PULSE -->
<div class="card">
  <h2>PULSE — Infrastructure Risk</h2>
  <div style="font-size:12px;color:#718096;margin-bottom:10px">NY State Bridges (n={total_bridges}) · Source: NY DOT data.ny.gov · Real poor_status + age scoring</div>
  {pulse_bars}
  <div style="margin-top:14px">
    <div style="font-size:11px;color:#718096;margin-bottom:6px">TOP PRIORITY — RED BAND IN HAZARD ZONE</div>
    <table>
      <thead><tr><th>BIN</th><th>COUNTY</th><th>SEISMIC</th><th>TSUNAMI</th><th>BAND</th><th>SCORE</th></tr></thead>
      <tbody>{pri_rows}</tbody>
    </table>
  </div>
  <div style="margin-top:10px;font-size:10px;color:#4a5568">Hazard zones: simplified proximity proxies — not authoritative FEMA/USGS boundaries</div>
</div>

</div><!-- /grid -->

<div class="grid3" style="margin-top:16px">

<!-- Earthquake WARN -->
<div class="card">
  <h2>WARN — Earthquake</h2>
  <div style="font-size:11px;color:#718096;margin-bottom:8px">USGS FDSN Event API · Cascadia M6.0+ 2000-2024 · {eq.get("event_count",0)} events</div>
  <table>
    <thead><tr><th>DATE</th><th>LOCATION</th><th>MAG</th><th>DEPTH</th><th style="width:30%">SCORE</th><th>TIER</th></tr></thead>
    <tbody>{eq_rows}</tbody>
  </table>
  <div style="margin-top:8px;font-size:10px;color:#4a5568">Formula: 0.55×mag_norm + 0.25×shallowness + 0.20×pop_exposure</div>
</div>

<!-- Tsunami WARN -->
<div class="card">
  <h2>WARN — Tsunami</h2>
  <div style="font-size:11px;color:#718096;margin-bottom:8px">NOAA NCEI Global Tsunami DB · {ts.get("event_count",0)} events · 1900-2024</div>
  <table>
    <thead><tr><th>YEAR</th><th>LOCATION</th><th>COUNTRY</th><th>WAVE</th><th>SRC MAG</th><th style="width:25%">SCORE</th><th>TIER</th></tr></thead>
    <tbody>{ts_rows}</tbody>
  </table>
  <div style="margin-top:8px;font-size:10px;color:#4a5568">Formula: 0.50×wave_norm + 0.30×mag_norm + 0.20×reach_norm</div>
</div>

<!-- Flood Surge WARN -->
<div class="card">
  <h2>WARN — Flood Surge</h2>
  <div style="font-size:11px;color:#718096;margin-bottom:8px">NOAA CO-OPS Tide Gauges · 4 real storm events · datum: MHHW</div>
  <table>
    <thead><tr><th>STORM</th><th>STATION</th><th>SURGE</th><th style="width:28%">SCORE</th><th>TIER</th><th>DATA</th></tr></thead>
    <tbody>{fl_rows}</tbody>
  </table>
  <div style="margin-top:8px;font-size:10px;color:#4a5568">Harvey gauge went offline at peak — observed 0.57m vs 3.96m documented surge (real data artifact)</div>
</div>

</div><!-- /grid3 -->

<!-- System mechanism diagram -->
<div class="card-full" style="margin-top:16px;background:#2d3748">
  <h2>How the Engines Connect</h2>
  <div style="display:flex;align-items:center;gap:6px;margin-top:10px;flex-wrap:wrap">
    <div style="background:#1a365d;border:1px solid #2b6cb0;border-radius:6px;padding:10px 14px;font-size:12px">
      <div style="font-weight:700;color:#90cdf4">WARN</div>
      <div style="color:#a0aec0;font-size:11px;margin-top:3px">Earthquake · Tsunami<br>Flood Surge · Wildfire</div>
      <div style="color:#718096;font-size:10px;margin-top:3px">External conditions</div>
    </div>
    <div style="font-size:20px;color:#4a5568">→</div>
    <div style="background:#1c4532;border:1px solid #276749;border-radius:6px;padding:10px 14px;font-size:12px">
      <div style="font-weight:700;color:#9ae6b4">PULSE</div>
      <div style="color:#a0aec0;font-size:11px;margin-top:3px">Bridges · Rail · Roads<br>Water Mains · Sewer</div>
      <div style="color:#718096;font-size:10px;margin-top:3px">Infrastructure stress</div>
    </div>
    <div style="font-size:20px;color:#4a5568">→</div>
    <div style="background:#322659;border:1px solid #553c9a;border-radius:6px;padding:10px 14px;font-size:12px">
      <div style="font-weight:700;color:#d6bcfa">WISE</div>
      <div style="color:#a0aec0;font-size:11px;margin-top:3px">Decision state<br>Compound escalation<br>Cost estimate</div>
      <div style="color:#718096;font-size:10px;margin-top:3px">Signal synthesis</div>
    </div>
    <div style="font-size:20px;color:#4a5568">→</div>
    <div style="background:#2d3748;border:1px solid #718096;border-radius:6px;padding:10px 14px;font-size:12px">
      <div style="font-weight:700;color:#e2e8f0">SENTINEL</div>
      <div style="color:#a0aec0;font-size:11px;margin-top:3px">This view<br>Visual + audit layer<br>Cascading risk map</div>
      <div style="color:#718096;font-size:10px;margin-top:3px">Render + evidence</div>
    </div>
    <div style="margin-left:auto;background:#744210;border:1px solid #c05621;border-radius:6px;padding:10px 14px;font-size:12px">
      <div style="font-weight:700;color:#fbd38d">WISE Compound Rule</div>
      <div style="color:#a0aec0;font-size:11px;margin-top:3px">If 2+ hazards ≥ MONITOR:<br>final tier = max + 1 level</div>
    </div>
  </div>
  <div style="margin-top:10px;font-size:10px;color:#4a5568">
    WARN cross-references PULSE: hazard zone (seismic/tsunami/flood) × PULSE infrastructure risk score = compound exposure priority list
  </div>
</div>

<div class="disclaimer">
  <strong>RESEARCH PROTOTYPE — NOT FOR OPERATIONAL USE</strong><br>
  All WARN, PULSE, WISE, and Sentinel outputs are experimental. WARN catalogues shown here contain historical or baseline records and are not a live alert feed. No component has been validated for emergency management, evacuation, public-health, or infrastructure decision use.
  Hazard zones (seismic, tsunami, flood) are simplified geographic proxies — not authoritative FEMA/USGS/NRCan boundaries.
  PULSE bridge scoring uses publicly available poor_status and year_built fields — no structural engineering assessment.
  Cost estimates are illustrative only; no real repair-cost, traffic, or ridership data is embedded.
  Data sources: USGS FDSN Event API (public domain) · NOAA NCEI Tsunami Database (public domain) · NOAA CO-OPS Tides &amp; Currents (public domain) · NY State DOT Bridge Conditions (data.ny.gov, public domain).
  External peer review not complete. No production claim is approved.
</div>

</body>
</html>"""

HTML.write_text(html)
print(f"Written: {HTML}")
print(f"Size: {HTML.stat().st_size:,} bytes")
