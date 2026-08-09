"""
WAIFINDERS Plain Language Capabilities PDF
For Nations, funders, and partners — no jargon, no formulas.
Output: materials/waifinders_plain_language_capabilities.pdf
"""
from pathlib import Path
from datetime import datetime, timezone

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER

try:
    import blake3
    def b3(d): return blake3.blake3(d).hexdigest()
except ImportError:
    import hashlib
    def b3(d): return hashlib.sha256(d).hexdigest()

OUT = Path(__file__).parent.parent / "materials"
OUT.mkdir(parents=True, exist_ok=True)
PDF = OUT / "waifinders_plain_language_capabilities.pdf"

FOREST   = colors.HexColor("#1A4D2E")
GOLD     = colors.HexColor("#C8922A")
EARTH    = colors.HexColor("#5C4033")
SKY      = colors.HexColor("#1B6CA8")
CREAM    = colors.HexColor("#FAF7F2")
LIGHT    = colors.HexColor("#EEF4FA")
MID      = colors.HexColor("#555555")
DARK     = colors.HexColor("#222222")
WHITE    = colors.white
WARN_RED = colors.HexColor("#C0392B")
WARN_ORG = colors.HexColor("#E67E22")
WARN_YEL = colors.HexColor("#B8860B")
WARN_GRN = colors.HexColor("#1A7A3C")

W = letter[0] - 1.2*inch

def styles():
    b = getSampleStyleSheet()
    return {
        "cover_h": ParagraphStyle("ch", parent=b["Title"],
            fontSize=30, textColor=WHITE, alignment=TA_CENTER,
            fontName="Helvetica-Bold", spaceAfter=6),
        "cover_s": ParagraphStyle("cs", parent=b["Normal"],
            fontSize=13, textColor=colors.HexColor("#D4E8C2"),
            alignment=TA_CENTER, spaceAfter=4),
        "cover_d": ParagraphStyle("cd", parent=b["Normal"],
            fontSize=9.5, textColor=colors.HexColor("#8BAF7A"),
            alignment=TA_CENTER),
        "section": ParagraphStyle("sc", parent=b["Heading1"],
            fontSize=14, textColor=WHITE, fontName="Helvetica-Bold",
            spaceAfter=4, spaceBefore=10, backColor=FOREST,
            leftIndent=-4, rightIndent=-4, borderPad=6),
        "question": ParagraphStyle("qu", parent=b["Heading2"],
            fontSize=11, textColor=FOREST, fontName="Helvetica-Bold",
            spaceAfter=2, spaceBefore=6),
        "body": ParagraphStyle("bo", parent=b["Normal"],
            fontSize=9.5, textColor=DARK, spaceAfter=4, leading=14),
        "answer": ParagraphStyle("an", parent=b["Normal"],
            fontSize=9.5, textColor=colors.HexColor("#1A3A1A"),
            spaceAfter=4, leading=14, leftIndent=14,
            backColor=colors.HexColor("#F0F8F0"), borderPad=4),
        "bullet": ParagraphStyle("bu", parent=b["Normal"],
            fontSize=9.5, textColor=DARK, spaceAfter=3, leading=13, leftIndent=16),
        "callout": ParagraphStyle("ca", parent=b["Normal"],
            fontSize=9, textColor=colors.HexColor("#7A3A00"),
            spaceAfter=4, leading=13, backColor=colors.HexColor("#FFF5E6"),
            leftIndent=10, rightIndent=10, borderPad=5),
        "small": ParagraphStyle("sm", parent=b["Normal"],
            fontSize=7.5, textColor=colors.HexColor("#777"), spaceAfter=2),
        "footer": ParagraphStyle("fo", parent=b["Normal"],
            fontSize=7, textColor=colors.HexColor("#999"), alignment=TA_CENTER),
        "big": ParagraphStyle("bi", parent=b["Normal"],
            fontSize=15, textColor=FOREST, fontName="Helvetica-Bold",
            alignment=TA_CENTER, spaceAfter=2),
        "big_lbl": ParagraphStyle("bl", parent=b["Normal"],
            fontSize=8, textColor=MID, alignment=TA_CENTER, spaceAfter=6),
    }

ST = styles()

def p(text, s="body"): return Paragraph(text, ST[s])
def sp(h=6): return Spacer(1, h)
def hr(): return HRFlowable(width="100%", thickness=0.5, color=GOLD, spaceAfter=5, spaceBefore=3)
def section(t): return [sp(8), Paragraph(f"  {t}", ST["section"]), sp(4)]
def q(text): return Paragraph(text, ST["question"])
def a(text): return Paragraph(text, ST["answer"])
def b_(text): return Paragraph(f"  •  {text}", ST["bullet"])

def cover_row(text, s):
    t = Table([[Paragraph(text, ST[s])]], colWidths=[W])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0),(-1,-1), FOREST),
        ("LEFTPADDING", (0,0),(-1,-1), 18),
        ("TOPPADDING", (0,0),(-1,-1), 8),
        ("BOTTOMPADDING", (0,0),(-1,-1), 8),
    ]))
    return t

def metric_row(pairs):
    cells = [[
        Table([[Paragraph(v, ST["big"]), Paragraph(l, ST["big_lbl"])]],
              colWidths=[W/len(pairs) - 4])
        for v, l in pairs
    ]]
    t = Table(cells, colWidths=[W/len(pairs)]*len(pairs))
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0),(-1,-1), CREAM),
        ("BOX", (0,0),(-1,-1), 0.5, GOLD),
        ("INNERGRID", (0,0),(-1,-1), 0.25, colors.HexColor("#DDDDDD")),
        ("VALIGN", (0,0),(-1,-1), "MIDDLE"),
        ("TOPPADDING", (0,0),(-1,-1), 10),
        ("BOTTOMPADDING", (0,0),(-1,-1), 10),
    ]))
    return t

def tier_box(tier, colour, meaning):
    t = Table([[Paragraph(f"<b>{tier}</b>", ParagraphStyle("tl",
        fontSize=9, textColor=WHITE, fontName="Helvetica-Bold")),
        Paragraph(meaning, ParagraphStyle("tm", fontSize=8.5, textColor=WHITE, leading=12))]],
        colWidths=[1.1*inch, W - 1.1*inch])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0),(-1,-1), colour),
        ("LEFTPADDING", (0,0),(-1,-1), 8),
        ("TOPPADDING", (0,0),(-1,-1), 5),
        ("BOTTOMPADDING", (0,0),(-1,-1), 5),
        ("VALIGN", (0,0),(-1,-1), "MIDDLE"),
    ]))
    return t

story = []
doc = SimpleDocTemplate(str(PDF), pagesize=letter,
    leftMargin=0.6*inch, rightMargin=0.6*inch,
    topMargin=0.6*inch, bottomMargin=0.6*inch)

# ══ COVER ════════════════════════════════════════════════════════════════════
story.append(cover_row("WAIFINDERS", "cover_h"))
story.append(cover_row("What It Does — In Plain Language", "cover_s"))
story.append(cover_row("For First Nations, Funders, and Partners  ·  August 2026", "cover_d"))
story.append(sp(14))
story.append(metric_row([
    ("8", "Hazard types\nmonitored"),
    ("58", "BC First Nations\nscored"),
    ("67", "Nuclear plants\ntracked"),
    ("2,000", "Bridges assessed\n(New York)"),
]))
story.append(sp(6))
story.append(metric_row([
    ("0.8818", "Accuracy score\nwildfire detection"),
    ("7.15x", "Better than random\nat finding high-risk fires"),
    ("10 yr", "Readiness projection\nfor Nations (SPARK7)"),
    ("260", "Tests passed\nall modules"),
]))
story.append(sp(14))
story.append(p(
    "WAIFINDERS is a decision-support platform that watches multiple hazards at once — "
    "wildfires, earthquakes, floods, hurricanes, tsunamis, and nuclear facilities — "
    "and tells you which ones need attention right now. It is built for Nations, "
    "infrastructure managers, and emergency planners who need to see the whole picture "
    "without waiting for separate reports from separate agencies.",
    "body"))
story.append(sp(4))
story.append(p(
    "Everything WAIFINDERS does is based on official public data. It does not make up "
    "numbers, predict the future, or replace your own judgment. It is a tool — "
    "the decision always stays with you.",
    "callout"))

# ══ SECTION 1: THE CORE QUESTION ════════════════════════════════════════════
story += section("THE CORE QUESTION WAIFINDERS ANSWERS")
story.append(q("What is threatening us right now, and how serious is it?"))
story.append(a(
    "WAIFINDERS watches eight types of hazards simultaneously and gives each one a score "
    "from 0 to 1 — where 0 means calm and 1 means the worst conditions on record. "
    "It then combines all those scores into a single decision: what level of response "
    "does today's situation actually require?"
))
story.append(sp(5))
story.append(p("The four response levels, in plain language:", "body"))
story.append(sp(3))
story.append(tier_box("NORMAL OPERATION", WARN_GRN,
    "Everything looks routine. Continue normal monitoring and planning."))
story.append(sp(2))
story.append(tier_box("MONITOR", WARN_YEL,
    "One or more hazards are elevated. Watch more closely. No immediate action required yet."))
story.append(sp(2))
story.append(tier_box("MITIGATION REQUIRED", WARN_ORG,
    "Significant hazard exposure. Take protective action now — check resources, "
    "review evacuation plans, alert key contacts."))
story.append(sp(2))
story.append(tier_box("EMERGENCY RESPONSE", WARN_RED,
    "Critical conditions or multiple hazards hitting at once. Full emergency response. "
    "This is when everything else stops."))
story.append(sp(8))

story.append(q("What triggers an upgrade from MONITOR to EMERGENCY?"))
story.append(a(
    "When two or more hazards reach the MONITOR level at the same time, "
    "WAIFINDERS automatically escalates the overall status by one level. "
    "A flood and a hurricane arriving together is more dangerous than either alone — "
    "and the platform recognises that. This is called a compound event."
))

# ══ SECTION 2: WHAT WAIFINDERS WATCHES ══════════════════════════════════════
story += section("WHAT WAIFINDERS WATCHES")
story.append(p(
    "Each hazard domain uses official public data and a transparent scoring formula. "
    "No scores are invented or estimated without a data source.", "body"))
story.append(sp(5))

hazards = [
    ("Wildfire — Alberta",
     "Forest fire danger across Alberta",
     "Fire Weather Index (FWI), fire spread rate, community exposure, firefighting resources",
     "Official Alberta fire records 2006–2025",
     "Accuracy: 0.8818 out of 1.0. Finds real large fires 7× better than chance."),
    ("Wildfire — BC First Nations",
     "Fire danger near First Nation territories in BC",
     "Fire danger index, proximity to active fires, fire size, fire spread speed",
     "BC Wildfire Service public records; BC Data Catalogue territory locations",
     "58 Nations scored. Kwadacha Nation highest (44 km from Donnie Creek 2023 fire)."),
    ("Earthquake",
     "Ground shaking from earthquakes",
     "Earthquake magnitude, depth, and nearby population",
     "USGS ShakeMap — the US Geological Survey's official earthquake maps",
     "A full Cascadia megaquake (M9.0) scores MITIGATION REQUIRED."),
    ("Tsunami",
     "Ocean waves from underwater earthquakes",
     "Wave height, earthquake size, how far inland the wave could reach",
     "NOAA DART buoy network — ocean sensors across the Pacific",
     "The 2011 Japan tsunami scores 0.970 — near the top of the scale."),
    ("Flood",
     "River and coastal flooding",
     "Water surge height, rainfall",
     "USGS water gauge network; NOAA tide gauge readings",
     "Hurricane Sandy's flood surge (2.74 m) scores MITIGATION REQUIRED."),
    ("Hurricane",
     "Tropical storm and hurricane winds",
     "Wind speed, storm surge, distance to coastline",
     "NOAA's 170-year Atlantic hurricane database (1851–2023)",
     "Hurricane Andrew 1992 scores 0.814 — EMERGENCY RESPONSE."),
    ("Nuclear",
     "Nuclear plant risk based on size, nearby population, and current power output",
     "Plant capacity, population in the emergency zone, current reactor power",
     "US Nuclear Regulatory Commission daily power status report",
     "67 US plants scored. High-density plants in the Northeast score highest."),
]

for name, what, how, source, result in hazards:
    story.append(KeepTogether([
        p(f"<b>{name}</b>"),
        p(f"<i>What it watches:</i> {what}", "body"),
        p(f"<i>How it scores:</i> {how}", "body"),
        p(f"<i>Data source:</i> {source}", "body"),
        p(f"<i>What the numbers mean:</i> {result}", "body"),
        sp(6),
    ]))

# ══ SECTION 3: BC FIRST NATIONS ════════════════════════════════════════════
story += section("BC FIRST NATIONS — WHAT WAIFINDERS PROVIDES")
story.append(q("What does a Nation actually see?"))
story.append(a(
    "Each Nation gets a current fire threat score (WARN) and a 10-year readiness "
    "projection (SPARK7). The WARN score reflects how close the fires are today, "
    "how fast they are moving, and how large they are. The SPARK7 projection looks "
    "further — it asks: given all the pressures this community faces (heat, drought, "
    "storms, wildfire, sea level), how does their readiness look in 10 years?"
))
story.append(sp(5))
story.append(q("What is SPARK7?"))
story.append(a(
    "SPARK7 is a readiness model originally built for Indigenous communities worldwide. "
    "WAIFINDERS has now connected it to live BC fire data. A community with a readiness "
    "score above 55 is GREEN (resilient). Between 40–55 is ORANGE (watch). "
    "Below 40 is RED (priority). All 58 BC Nations currently score ORANGE — "
    "meaning fire pressure is already affecting their readiness outlook."
))
story.append(sp(5))
story.append(q("How does WAIFINDERS handle Nation data?"))
story.append(a(
    "WAIFINDERS uses only public data: BC Wildfire Service fire records and "
    "approximate territory locations from the public BC Data Catalogue. "
    "No cultural data, sacred site information, governance data, or Nation-specific "
    "information is collected or used. Territory coordinates are approximate."
))
story.append(sp(4))
story.append(p(
    "OCAP principles (Ownership, Control, Access, Possession) are built into "
    "every part of the BC module. The Nation owns its data. WAIFINDERS does not "
    "claim to represent any Nation's view of their situation, and no Nation has "
    "endorsed this platform. A formal data agreement with the Nation is required "
    "before territory-specific data can be used.",
    "callout"))
story.append(sp(5))

story.append(q("What would change with a Nation data agreement?"))
story.append(p("With a formal agreement, WAIFINDERS could:", "body"))
for item in [
    "Use the Nation's own territory boundary maps instead of public approximations",
    "Score specific community infrastructure (roads, water systems, health centres)",
    "Track evacuation route risk under active fire conditions",
    "Provide the Nation with their own data — stored and controlled by them",
    "Integrate traditional ecological knowledge and seasonal fire patterns if the Nation chooses",
]:
    story.append(b_(item))

# ══ SECTION 4: INFRASTRUCTURE ═══════════════════════════════════════════════
story += section("INFRASTRUCTURE — WHAT IS AT RISK WHEN A HAZARD HITS")
story.append(q("What does PULSE do?"))
story.append(a(
    "PULSE scores infrastructure — bridges, roads, water mains, rail — on how stressed "
    "they are likely to be under current hazard conditions. A bridge that is already in "
    "poor condition AND sits in an earthquake zone AND a flood plain gets a much higher "
    "risk score than a newer bridge in a low-hazard area. PULSE shows you which assets "
    "need attention before the hazard arrives."
))
story.append(sp(5))
story.append(p("Current results — 2,000 bridges in New York State:", "body"))
story.append(sp(3))

infra = Table([
    ["Colour", "Count", "What it means"],
    ["RED",    "200",   "Highest combined risk — poor condition in a high-hazard zone. Immediate priority."],
    ["AMBER",  "340",   "Elevated exposure. Monitor closely and prioritise inspection."],
    ["YELLOW", "1,141", "Moderate exposure. Schedule inspection in next cycle."],
    ["GREEN",  "319",   "Low combined risk. Routine maintenance cycle."],
], colWidths=[0.75*inch, 0.6*inch, W - 1.35*inch])
infra.setStyle(TableStyle([
    ("BACKGROUND", (0,0),(-1,0), FOREST),
    ("TEXTCOLOR",  (0,0),(-1,0), WHITE),
    ("FONTNAME",   (0,0),(-1,0), "Helvetica-Bold"),
    ("FONTSIZE",   (0,0),(-1,-1), 8.5),
    ("ROWBACKGROUNDS", (0,1),(-1,-1), [colors.HexColor("#FDE8E8"), colors.HexColor("#FEF3DC"),
                                        colors.HexColor("#FFFDE8"), colors.HexColor("#E8F8EE")]),
    ("GRID", (0,0),(-1,-1), 0.25, colors.HexColor("#CCCCCC")),
    ("VALIGN", (0,0),(-1,-1), "MIDDLE"),
    ("TOPPADDING", (0,0),(-1,-1), 4),
    ("BOTTOMPADDING", (0,0),(-1,-1), 4),
    ("LEFTPADDING", (0,0),(-1,-1), 6),
]))
story.append(infra)
story.append(sp(5))
story.append(p(
    "Hazard zone sources: earthquake risk from the US Geological Survey 2014 national map; "
    "tsunami exposure from NOAA coastal gauges; flood risk from FEMA flood maps.",
    "small"))
story.append(sp(5))
story.append(q("Has this been tested on real infrastructure?"))
story.append(a(
    "Yes. PULSE was validated against real open-data records in Toronto (4,248 assets, "
    "accuracy 0.74) and Calgary (4,748 assets, accuracy 0.66). Both cities confirmed "
    "their open data can be used. The next step is working with a city or utility to "
    "use their live operational data instead of open data."
))

# ══ SECTION 5: WHAT WAIFINDERS DOES NOT DO ══════════════════════════════════
story += section("WHAT WAIFINDERS DOES NOT DO")
story.append(p(
    "Being clear about limits is as important as describing capabilities. "
    "The following are hard rules — not disclaimers.", "body"))
story.append(sp(4))
for item in [
    ("Does not predict hazards",
     "WAIFINDERS does not predict when or where a fire, earthquake, or flood will occur. "
     "It scores the severity of hazards that are already happening or already recorded."),
    ("Does not replace human judgment",
     "Every score is a decision-support input. A person — a Nation leader, an emergency "
     "manager, an engineer — always makes the final call. WAIFINDERS does not direct action."),
    ("Does not use Nation data without consent",
     "No cultural, spiritual, traditional territory, or governance data is collected "
     "from any Nation without a formal written agreement following OCAP principles."),
    ("Does not claim government endorsement",
     "No BC Wildfire Service, NRC, USGS, NOAA, FEMA, or government body has endorsed "
     "WAIFINDERS. Data sources are cited; endorsement is not claimed."),
    ("Does not fabricate numbers",
     "Every score comes from a named official data source. If a data source is unavailable, "
     "WAIFINDERS says so explicitly — it does not substitute made-up values."),
    ("Is not a production emergency system",
     "WAIFINDERS is pilot-ready. It is built to the standard required for production, "
     "but it has not completed external peer review or received an official data agreement. "
     "Those steps are in progress."),
]:
    name, desc = item
    story.append(KeepTogether([
        p(f"<b>{name}</b>"),
        p(desc, "body"),
        sp(4),
    ]))

# ══ SECTION 6: WHAT IS READY TO DEPLOY ══════════════════════════════════════
story += section("WHAT IS READY TODAY")
story.append(tbl := Table([
    ["Capability", "Ready for pilot?", "What is still needed for production"],
    ["Wildfire WARN — Alberta",
     "YES",
     "External peer review; official Alberta fire data agreement"],
    ["Wildfire WARN — BC First Nations",
     "YES",
     "BC official fire data agreement; Nation data agreements"],
    ["SPARK7 — Nation 10-year readiness",
     "YES (BC connected)",
     "Nation-validated baselines; formal data governance"],
    ["Earthquake / Tsunami / Flood / Hurricane",
     "YES",
     "Regional calibration; external review"],
    ["Nuclear plant tracking",
     "YES",
     "Scope agreement; utility partner"],
    ["Infrastructure PULSE",
     "YES",
     "Production operational data partnership (city or utility)"],
    ["WISE decision engine",
     "YES",
     "Pilot integration; knowledge corpus; external review"],
    ["Audit trail (SENTINEL / S.A.F.E.)",
     "YES",
     "Federal partner engagement (underway)"],
    ["Live Nation dashboard",
     "YES",
     "Nation data agreement; formal engagement"],
], colWidths=[2.1*inch, 0.9*inch, 3.3*inch]))
tbl.setStyle(TableStyle([
    ("BACKGROUND", (0,0),(-1,0), FOREST),
    ("TEXTCOLOR",  (0,0),(-1,0), WHITE),
    ("FONTNAME",   (0,0),(-1,0), "Helvetica-Bold"),
    ("FONTSIZE",   (0,0),(-1,-1), 8),
    ("ROWBACKGROUNDS", (0,1),(-1,-1), [WHITE, CREAM]),
    ("GRID", (0,0),(-1,-1), 0.25, colors.HexColor("#CCCCCC")),
    ("VALIGN", (0,0),(-1,-1), "TOP"),
    ("TOPPADDING", (0,0),(-1,-1), 4),
    ("BOTTOMPADDING", (0,0),(-1,-1), 4),
    ("LEFTPADDING", (0,0),(-1,-1), 5),
]))
story.append(sp(8))

# ══ SECTION 7: HOW TO ENGAGE ════════════════════════════════════════════════
story += section("HOW TO ENGAGE")
story.append(q("For First Nations"))
for item in [
    "Request a demonstration of the BC wildfire dashboard for your territory",
    "Begin a Nation-to-Nation conversation about a data agreement (OCAP framework)",
    "Identify a data steward within the Nation to oversee any future data sharing",
    "Define what questions the Nation wants WAIFINDERS to help answer",
]:
    story.append(b_(item))
story.append(sp(5))
story.append(q("For funders and government partners"))
for item in [
    "Review the full technical build metrics (separate PDF — see enclosed)",
    "Request the SENTINEL federal engagement package",
    "Identify a pilot context: wildfire season, infrastructure assessment, emergency planning",
    "Commission an independent external review of the WARN model",
]:
    story.append(b_(item))
story.append(sp(5))
story.append(q("For infrastructure and utility partners"))
for item in [
    "Share a sample of operational asset data (pipe condition, bridge inspection) for a pilot PULSE run",
    "Define the infrastructure question: what assets are you most worried about?",
    "Review the Toronto and Calgary validation results",
]:
    story.append(b_(item))

# ══ FOOTER ═══════════════════════════════════════════════════════════════════
story.append(sp(10))
story.append(HRFlowable(width="100%", thickness=0.5, color=GOLD, spaceAfter=5))
story.append(p(
    "WAIFINDERS is a decision-support platform — not a forecasting system, not an emergency "
    "directive system, and not a government-endorsed product. All wildfire performance figures "
    "are from a real replay of Alberta fire records (Open Alberta OGL-A licence, 2006–2025). "
    "Alberta scope only — performance does not transfer to BC or Ontario without a separate study. "
    "OCAP principles govern all engagement with Nations.",
    "small"))
story.append(sp(4))
story.append(Paragraph(
    f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}  ·  "
    f"WAIFINDERS Platform  ·  Plain Language Edition v1",
    ST["footer"]))

doc.build(story)
raw = PDF.read_bytes()
print(f"Output: {PDF}")
print(f"Size:   {PDF.stat().st_size:,} bytes")
print(f"BLAKE3: {b3(raw)[:16]}...")
