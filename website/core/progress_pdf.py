"""A branded, printable PDF of one learner's progress report, for parents and schools.
It leaves out the private parts of the admin page (contact details and staff notes)."""

import io
from xml.sax.saxutils import escape

from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

SKY = colors.HexColor("#1CA7EC")
NAVY = colors.HexColor("#0B2545")
GREEN = colors.HexColor("#2FBF71")
CORAL = colors.HexColor("#E8743B")
SOFT = colors.HexColor("#EEF6FC")
LINE = colors.HexColor("#D8E3EC")
QUIET = colors.HexColor("#5B6B7A")

_base = getSampleStyleSheet()
BODY = ParagraphStyle("c4k-body", parent=_base["BodyText"], fontName="Helvetica", fontSize=9.5, leading=13, textColor=NAVY)
SMALL = ParagraphStyle("c4k-small", parent=BODY, fontSize=8, leading=10.5, textColor=QUIET)
H2 = ParagraphStyle("c4k-h2", parent=BODY, fontName="Helvetica-Bold", fontSize=12.5, leading=16, spaceBefore=10, spaceAfter=5, textColor=NAVY)
NUM = ParagraphStyle("c4k-num", parent=BODY, fontName="Helvetica-Bold", fontSize=17, leading=20, textColor=SKY, alignment=TA_LEFT)
CELL = ParagraphStyle("c4k-cell", parent=BODY, fontSize=8.5, leading=11)
CELL_HEAD = ParagraphStyle("c4k-cell-head", parent=CELL, fontName="Helvetica-Bold", textColor=colors.white)


def _p(text, style=BODY):
    return Paragraph(escape(str(text)), style)


def _table(head, rows, widths):
    data = [[_p(h, CELL_HEAD) for h in head]] + [[_p(c, CELL) for c in row] for row in rows]
    t = Table(data, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, SOFT]),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


def _tiles(items):
    """A row of number tiles: [(value, label), ...]."""
    cells = [[Paragraph(f"{escape(str(v))}<br/><font size=8 color='#5B6B7A'>{escape(label)}</font>", NUM) for v, label in items]]
    t = Table(cells, colWidths=[(180 * mm) / len(items)] * len(items))
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), SOFT), ("BOX", (0, 0), (-1, -1), 0.4, LINE), ("INNERGRID", (0, 0), (-1, -1), 2, colors.white),
        ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7), ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    return t


def _bar_chart(points, color=SKY):
    d = Drawing(180 * mm, 42 * mm)
    chart = VerticalBarChart()
    chart.x, chart.y, chart.width, chart.height = 8 * mm, 7 * mm, 168 * mm, 32 * mm
    values = [p["value"] for p in points] or [0]
    chart.data = [values]
    chart.categoryAxis.categoryNames = [p["label"] if i % 5 == 0 else "" for i, p in enumerate(points)]
    chart.categoryAxis.labels.fontSize = 6.5
    chart.categoryAxis.labels.fillColor = QUIET
    chart.valueAxis.valueMin = 0
    chart.valueAxis.valueMax = max(max(values), 1)
    chart.valueAxis.valueStep = max(1, round(chart.valueAxis.valueMax / 4))
    chart.valueAxis.labels.fontSize = 6.5
    chart.valueAxis.labels.fillColor = QUIET
    chart.valueAxis.strokeColor = LINE
    chart.categoryAxis.strokeColor = LINE
    chart.bars[0].fillColor = color
    chart.bars[0].strokeColor = None
    chart.barSpacing = 1
    d.add(chart)
    return d


def _header_footer(name, generated):
    def draw(canvas, doc):
        w, h = A4
        canvas.saveState()
        canvas.setFillColor(NAVY)
        canvas.rect(0, h - 30 * mm, w, 30 * mm, stroke=0, fill=1)
        canvas.setFillColor(SKY)
        canvas.rect(0, h - 31.5 * mm, w, 1.5 * mm, stroke=0, fill=1)
        canvas.setFillColor(colors.white)
        canvas.circle(20 * mm, h - 15 * mm, 6.5 * mm, stroke=0, fill=1)
        canvas.setFillColor(SKY)
        canvas.setFont("Helvetica-Bold", 10)
        canvas.drawCentredString(20 * mm, h - 16.5 * mm, "C4K")
        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica-Bold", 17)
        canvas.drawString(31 * mm, h - 14 * mm, "Cloud for Kids")
        canvas.setFont("Helvetica", 9.5)
        canvas.drawString(31 * mm, h - 20 * mm, "Learner progress report")
        canvas.setFont("Helvetica-Bold", 11)
        canvas.drawRightString(w - 15 * mm, h - 14 * mm, name[:48])
        canvas.setFont("Helvetica", 8.5)
        canvas.drawRightString(w - 15 * mm, h - 20 * mm, f"Prepared {generated:%d %B %Y}")
        canvas.setStrokeColor(LINE)
        canvas.line(15 * mm, 14 * mm, w - 15 * mm, 14 * mm)
        canvas.setFillColor(QUIET)
        canvas.setFont("Helvetica", 7.5)
        canvas.drawString(15 * mm, 9 * mm, "Cloud for Kids  |  cloudforkids.co.ke  |  Confidential: for the learner, their family and their school")
        canvas.drawRightString(w - 15 * mm, 9 * mm, f"Page {doc.page}")
        canvas.restoreState()

    return draw


def learner_pdf(r):
    """PDF bytes for a report from core.progress.build_learner_report."""
    user, profile = r["user"], r["profile"]
    name = user.get_full_name() or user.username
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=38 * mm, bottomMargin=20 * mm,
                            title=f"{name}: progress report", author="Cloud for Kids")
    story = []

    details = [f"Username: {user.username}"]
    if profile:
        details += [x for x in (profile.grade, profile.school_name, profile.county) if x]
        details.append(f"Tier: {profile.tier.name}" if profile.tier_id else "Tier: not chosen")
    details.append(f"Joined {user.date_joined:%d %b %Y}")
    details.append(f"Last active {r['last_seen']:%d %b %Y}" if r["last_seen"] else "Not active yet")
    story += [Paragraph(f"<b>{escape(name)}</b>", ParagraphStyle("n", parent=BODY, fontSize=15, leading=19)), _p("  ·  ".join(details), SMALL),
              Spacer(1, 6)]

    quiz = f"{r['quiz_avg']}%" if r["quiz_avg"] is not None else "-"
    story.append(_tiles([(f"{r['percent']}%", "of enrolled lessons"), (r["lessons_done"], "lessons finished"), (quiz, "quiz average"),
                         (r["active_days"], "days learned")]))
    story.append(Spacer(1, 4))
    story.append(_tiles([(r["courses_finished"], "courses finished"), (f"{r['time']['minutes']}", "minutes learning"),
                         (r["labs_done"], "practice labs"), (len(r["badges"]), "badges")]))

    if r["insights"]:
        story.append(_p("Summary", H2))
        story += [Paragraph(f"• {escape(line)}", BODY) for line in r["insights"][:7]]

    story.append(_p("Learning activity, last 30 days", H2))
    story.append(_bar_chart(r["chart"]))

    if r["courses"]:
        rows = []
        for c in r["courses"]:
            status = "Completed" if c["complete"] else (f"Next: {c['next'].title}" if c["next"] else "In progress")
            rows.append([c["course"].title, c["course"].tier.name, f"{c['done']} of {c['total']}", f"{c['percent']}%", status])
        story.append(KeepTogether([_p("Where they are in each course", H2), _table(["Course", "Tier", "Lessons", "Progress", "Status"], rows,
                                                                                    [55 * mm, 26 * mm, 22 * mm, 20 * mm, 57 * mm])]))

    strong = [[q.lesson.title, q.lesson.course.title, f"{q.score_percent}%"] for q in r["strong"]]
    weak = [[q.lesson.title, q.lesson.course.title, f"{q.score_percent}%" + ("" if q.passed else " (not passed)")] for q in r["weak"]]
    if strong:
        story.append(KeepTogether([_p("Strong areas", H2), _table(["Lesson", "Course", "Score"], strong, [80 * mm, 70 * mm, 30 * mm])]))
    if weak:
        story.append(KeepTogether([_p("Areas to practise", H2), _table(["Lesson", "Course", "Score"], weak, [80 * mm, 70 * mm, 30 * mm])]))
    if r["tries"]["missed"]:
        missed = [[m["text"][:140], m["lesson"].title, str(m["times"])] for m in r["tries"]["missed"][:5]]
        story.append(KeepTogether([_p("Questions answered wrongly most often", H2),
                                   _table(["Question", "Lesson", "Times wrong"], missed, [100 * mm, 55 * mm, 25 * mm])]))

    if r["compare"]:
        rows = [[row["label"], f"{row['mine']}{row['unit']}", f"{row['avg']}{row['unit']}",
                 ("+" if row["diff"] > 0 else "") + f"{row['diff']}{row['unit']}"] for row in r["compare"]["rows"]]
        story.append(KeepTogether([_p(f"Compared with other {r['compare']['tier'].name} learners ({r['compare']['n']})", H2),
                                   _table(["", name.split(" ")[0], "Tier average", "Difference"], rows, [60 * mm, 40 * mm, 40 * mm, 40 * mm])]))

    if r["next_steps"]:
        story.append(_p("Recommended next steps", H2))
        story += [Paragraph(f"{i}. {escape(step['text'])}", BODY) for i, step in enumerate(r["next_steps"], start=1)]

    if r["badges"]:
        story.append(_p("Badges earned", H2))
        story.append(_p(", ".join(f"{b.badge.name} ({b.earned_at:%d %b %Y})" for b in r["badges"]), BODY))

    sign = Table([[_p("Teacher / coordinator", SMALL), "", _p("Signature", SMALL), "", _p("Date", SMALL)]],
                 colWidths=[45 * mm, 10 * mm, 60 * mm, 10 * mm, 55 * mm], rowHeights=[16 * mm])
    sign.setStyle(TableStyle([("LINEABOVE", (0, 0), (0, 0), 0.6, NAVY), ("LINEABOVE", (2, 0), (2, 0), 0.6, NAVY),
                              ("LINEABOVE", (4, 0), (4, 0), 0.6, NAVY), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story += [Spacer(1, 22), KeepTogether([sign])]

    page = _header_footer(name, r["generated"])
    doc.build(story, onFirstPage=page, onLaterPages=page)
    return buf.getvalue()
