"""Fill the department's project-poster template (A0 portrait) in place: header, logo, coloured strip,
section bars and footer are the template's own; everything else is added on top in the same style.

    python scripts/poster_charts.py   # the four charts (measured values only)
    python scripts/build_poster.py    # -> docs/Review-III/QueryGenie_Poster.pptx

Layout follows the department's examples: title + icon strip, Abstract / Objectives / Key innovations /
the app / References on the left, architecture / datasets / results / conclusion / team on the right.
"""
import os

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE = os.path.join(ROOT, "docs", "Templates", "project-poster-tempalte.pptx")
OUT = os.path.join(ROOT, "docs", "Review-III", "QueryGenie_Poster.pptx")
ASSETS = os.path.join(ROOT, "docs", "Review-III", "poster_assets")
ICON = lambda name, colour="blue": os.path.join(ASSETS, "icons", f"{name}_{colour}.png")
FIG = os.path.join(ROOT, "docs", "report-latex", "images", "figures")
BRAND = os.path.join(ROOT, "desktop", "ui", "brand", "mark.png")

# the template's palette
RED, NAVY, BLUE, YELLOW, GREEN = "C00000", "002060", "0070C0", "FFC000", "92D050"
INK, MUTED, LINE, CARD = "1F2937", "4B5563", "D6DCE5", "FFFFFF"
SERIF = "Times New Roman"            # the template's body and heading font

prs = Presentation(TEMPLATE)
s = prs.slides[0]
P = {p.placeholder_format.idx: p for p in s.placeholders}
rgb = lambda h: RGBColor.from_string(h)


def place(shape, x, y, w, h):
    shape.left, shape.top, shape.width, shape.height = Inches(x), Inches(y), Inches(w), Inches(h)


def run(p, text, size, bold=False, colour=INK, italic=False, font=SERIF):
    r = p.add_run()
    r.text = text
    r.font.size, r.font.bold, r.font.italic, r.font.name = Pt(size), bold, italic, font
    r.font.color.rgb = rgb(colour)
    return r


def text(x, y, w, h, paras, size=26, colour=INK, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, shape=None, spacing=0.25):
    """paras: list of str or (str, {bold, size, colour, italic}) or [(str, fmt), ...] (runs)."""
    tb = shape or s.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    if shape is not None:
        place(shape, x, y, w, h)
    tf = tb.text_frame
    tf.clear()
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = Inches(0.08)
    tf.margin_top = tf.margin_bottom = Inches(0.03)
    for k, para in enumerate(paras):
        p = tf.paragraphs[0] if k == 0 else tf.add_paragraph()
        p.alignment = align
        p.space_after = Pt(size * spacing)
        p.space_before = Pt(0)          # the master adds 33 pt above every paragraph
        runs = para if isinstance(para, list) else [para]
        for rn in runs:
            t, f = (rn, {}) if isinstance(rn, str) else rn
            run(p, t, f.get("size", size), f.get("bold", False), f.get("colour", colour), f.get("italic", False))
    return tb


def bar(x, y, w, title):
    """A section bar in the template's style (red, white bold underlined serif)."""
    b = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(0.8))
    b.fill.solid(); b.fill.fore_color.rgb = rgb(RED); b.line.fill.background(); b.shadow.inherit = False
    tf = b.text_frame
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]; p.alignment = PP_ALIGN.CENTER
    r = run(p, title, 39, True, "FFFFFF"); r.font.underline = True
    return b


def header(idx, x, y, w=15.6):
    """Move one of the template's own section bars."""
    place(P[idx], x, y, w, 0.8)


def card(x, y, w, h, fill=CARD, line=LINE, radius=0.06):
    c = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    c.adjustments[0] = radius
    c.fill.solid(); c.fill.fore_color.rgb = rgb(fill)
    c.line.color.rgb = rgb(line); c.line.width = Pt(1.5); c.shadow.inherit = False
    return c


def circle(x, y, d, colour, label):
    c = s.shapes.add_shape(MSO_SHAPE.OVAL, Inches(x), Inches(y), Inches(d), Inches(d))
    c.fill.solid(); c.fill.fore_color.rgb = rgb(colour); c.line.fill.background(); c.shadow.inherit = False
    tf = c.text_frame; tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    p = tf.paragraphs[0]; p.alignment = PP_ALIGN.CENTER
    run(p, label, 28, True, "FFFFFF")


def pic(path, x, y, w=None, h=None):
    return s.shapes.add_picture(path, Inches(x), Inches(y), Inches(w) if w else None, Inches(h) if h else None)


# ------------------------------------------------------------------ title (top right: the app's own logo)
text(6.6, 1.1, 21.4, 3.4, [("QueryGenie", {"size": 100, "bold": True, "colour": NAVY}),
                           ("A Self-Correcting, Confidence-Aware Natural Language to SQL Interface", {"size": 40, "colour": NAVY}),
                           ("Ask a database in plain English — and get told when the answer can't be trusted", {"size": 28, "colour": MUTED, "italic": True})],
     align=PP_ALIGN.CENTER, shape=P[153], spacing=0.05)
pic(BRAND, 29.0, 1.25, h=3.0)

# ------------------------------------------------------------------ the strip under STUDENTS / INNOVATION / RESEARCH / IMPACT
CHIPS = [[("graduation-cap", "B.Tech CSIT"), ("users", "Team 18")],
         [("shield-check", "Confidence-aware abstention"), ("refresh-cw", "Self-correction")],
         [("book-open", "CodeS · SIGMOD 2024"), ("database", "Spider benchmark")],
         [("monitor-smartphone", "Desktop app"), ("lock-keyhole", "Runs locally")]]
zone_w, gap = 7.75, 0.2
for z, chips in enumerate(CHIPS):
    zx = 0.7 + z * (zone_w + 0.233)
    cw = (zone_w - gap) / 2
    for k, (ic, label) in enumerate(chips):
        cx = zx + k * (cw + gap)
        card(cx, 5.9, cw, 1.25, radius=0.18)
        pic(ICON(ic, "navy"), cx + 0.15, 6.2, w=0.65)
        text(cx + 0.85, 5.9, cw - 0.95, 1.25, [(label, {"size": 21, "bold": True, "colour": NAVY})], anchor=MSO_ANCHOR.MIDDLE)

# ------------------------------------------------------------------ left column
L, W = 0.7, 15.6
header(11, L, 7.5)
text(L, 8.45, W, 5.3, [
    [("Text-to-SQL models let people who do not know SQL ask a database questions in plain English, but they answer "
      "every question with the same confidence, so a wrong answer looks exactly like a right one. ", {}),
     ("QueryGenie", {"bold": True}),
     (" reproduces CodeS (SIGMOD 2024, arXiv:2402.16347), an open-source text-to-SQL model, and makes it say when it is unsure. "
      "We reproduce CodeS-1B to 77.8% execution accuracy on Spider (paper: 77.9%) and 69.5% on Spider-Realistic (paper: 70.9%). "
      "Our enhancement, confidence-aware abstention, runs the candidate queries the model already generates and checks "
      "whether they agree: when they don't, it asks the user instead of guessing. It answers 90.4% of questions and is "
      "right on 83.3% of them, with a third fewer wrong answers — a statistically significant gain. Everything runs "
      "locally in a desktop app, on open weights.", {})]], size=29, shape=P[10])

header(20, L, 13.95)
OBJ = ["Reproduce CodeS-1B on Spider within the ±5–10% tolerance, logging every run.",
       "Ablate the CodeS pipeline to find which components matter.",
       "Make the system say when it is unsure: confidence-aware abstention, tested statistically.",
       "Measure the benchmark-to-reality gap on realistically worded questions.",
       "Deliver a working desktop application that runs fully locally."]
COL = [BLUE, "2E7D32", YELLOW, RED, "7030A0"]
for k, o in enumerate(OBJ):
    y = 15.0 + k * 1.02
    circle(L + 0.15, y, 0.78, COL[k], str(k + 1))
    text(L + 1.15, y - 0.08, W - 1.25, 0.95, [o], size=27, anchor=MSO_ANCHOR.MIDDLE)
P[96].text_frame.clear(); place(P[96], L, 15.0, 0.1, 0.1)       # template's objectives body: unused (drawn above)

bar(L, 20.3, W, "Key Innovations & Contributions")
INNOV = [("shield-check", "Confidence-aware abstention",
          "Runs every candidate query, counts how many agree, and asks “Did you mean…?” when they don't."),
         ("badge-check", "Faithful, audited reproduction",
          "77.8% vs 77.9% with the official evaluator, after an audit that fixed our own scoring and a value-retriever bug."),
         ("refresh-cw", "Execution-guided self-correction",
          "Failed queries go back to the model with the database error; measured honestly (77.76 → 77.85%)."),
         ("monitor-smartphone", "Local desktop application",
          "Chats, schema map, charts, SQLite / PostgreSQL / MySQL — schema and data never leave the computer.")]
for k, (ic, title, desc) in enumerate(INNOV):
    y = 21.35 + k * 1.75
    pic(ICON(ic, "blue"), L + 0.2, y + 0.15, w=0.95)
    text(L + 1.4, y, W - 1.5, 1.7, [(title, {"bold": True, "size": 28, "colour": NAVY}), (desc, {"size": 25, "colour": INK})], spacing=0.05)

bar(L, 28.5, W, "The Application")
shot_w = 11.6
pic(os.path.join(FIG, "app_answer.png"), L + (W - shot_w) / 2, 29.5, w=shot_w)
text(L, 29.5 + shot_w * 1600 / 2560 + 0.1, W, 0.6,
     [("A confident answer: all four candidate queries agree, so QueryGenie shows the table and a chart.", {"italic": True, "size": 21, "colour": MUTED})],
     align=PP_ALIGN.CENTER)

header(27, L, 37.75)
REFS = [
    "Li, H., et al. (2024). CodeS: Towards building open-source language models for text-to-SQL. arXiv:2402.16347.",
    "Yu, T., et al. (2018). Spider: A large-scale human-labeled dataset for complex and cross-domain semantic parsing and text-to-SQL task. arXiv:1809.08887.",
    "Deng, X., Awadallah, A. H., Meek, C., Polozov, O., Sun, H., & Richardson, M. (2020). Structure-grounded pretraining for text-to-SQL. arXiv:2010.12773.",
    "Li, J., et al. (2023). Can LLM already serve as a database interface? A big bench for large-scale database grounded text-to-SQLs. arXiv:2305.03111.",
    "Pourreza, M., & Rafiei, D. (2023). DIN-SQL: Decomposed in-context learning of text-to-SQL with self-correction. arXiv:2304.11015.",
    "Wang, X., et al. (2022). Self-consistency improves chain of thought reasoning in language models. arXiv:2203.11171.",
    "Geifman, Y., & El-Yaniv, R. (2017). Selective classification for deep neural networks. arXiv:1705.08500.",
    "Zhong, R., Yu, T., & Klein, D. (2020). Semantic evaluation for text-to-SQL with distilled test suites. arXiv:2010.02840.",
]
text(L, 38.7, W, 7.0, [[(f"[{k + 1}] ", {"bold": True}), (r, {})] for k, r in enumerate(REFS)], size=22, shape=P[28], spacing=0.3)

# ------------------------------------------------------------------ right column
R = 16.8
P[25].text_frame.text = "Proposed Methodology / System Architecture"
for p_ in P[25].text_frame.paragraphs:
    for r_ in p_.runs:
        r_.font.size = Pt(39); r_.font.bold = True; r_.font.underline = True; r_.font.color.rgb = rgb("FFFFFF")
header(25, R, 7.5)
fig_h = W * 1376 / 2560
pic(os.path.join(FIG, "final_pipeline.png"), R, 8.45, w=W)
P[26].text_frame.clear(); place(P[26], R, 8.45, 0.1, 0.1)       # body replaced by the diagram

y0 = 8.45 + fig_h + 0.25
text(R, y0, W, 0.6, [("Datasets — all from Hugging Face (approved source; no Kaggle)", {"bold": True, "size": 25, "colour": NAVY})])
tbl = s.shapes.add_table(4, 3, Inches(R), Inches(y0 + 0.65), Inches(W), Inches(2.4)).table
for j, wdt in enumerate([5.4, 3.4, 6.8]):
    tbl.columns[j].width = Inches(wdt)
ROWS = [("Set", "Questions", "Used for"), ("Spider dev", "1,034 · 20 databases", "Reproduction, ablation, enhancement"),
        ("Spider-Realistic", "508", "Realistic wording (no column names)"), ("BIRD Mini-Dev", "500 · 11 databases", "Real-world databases (set up; future work)")]
for i, row in enumerate(ROWS):
    for j, v in enumerate(row):
        c = tbl.cell(i, j)
        c.text = v
        c.fill.solid(); c.fill.fore_color.rgb = rgb(NAVY if i == 0 else ("EEF3F9" if i % 2 else CARD))
        for p_ in c.text_frame.paragraphs:
            for r_ in p_.runs:
                r_.font.size = Pt(21); r_.font.name = SERIF; r_.font.bold = i == 0
                r_.font.color.rgb = rgb("FFFFFF" if i == 0 else INK)

header(154, R, 21.3)
cw, ch = 7.7, 7.7 * 4.8 / 7.6
for k, name in enumerate(["chart_reproduction", "chart_enhancement", "chart_wrong", "chart_calibration"]):
    pic(os.path.join(ASSETS, name + ".png"), R + (k % 2) * (cw + 0.2), 22.25 + (k // 2) * (ch + 0.15), w=cw)
ky = 22.25 + 2 * (ch + 0.15) + 0.1
card(R, ky, W, 4.2, fill="FFF7E6", line=YELLOW)
text(R + 0.25, ky + 0.1, W - 0.5, 4.1, [
    ("Key results", {"bold": True, "size": 28, "colour": NAVY}),
    [("Reproduced: ", {"bold": True}), ("77.8% EX on Spider (paper 77.9%), 69.5% on Spider-Realistic (paper 70.9%) — within tolerance.", {})],
    [("Enhanced: ", {"bold": True}), ("answers 90.4% of questions, correct on 83.3% (vs 77.8%); wrong answers 230 → 156.", {})],
    [("Significant: ", {"bold": True}), ("paired t-test p = 7.7×10⁻¹⁰, Wilcoxon p = 9.8×10⁻⁴, bootstrap 95% CI +4.5 to +6.7 pts.", {})],
    [("Robust: ", {"bold": True}), ("counting each different query once, it still reaches 83.5% at 90% coverage.", {})],
], size=27, spacing=0.12)
P[155].text_frame.clear(); place(P[155], R, 21.3, 0.1, 0.1)

bar(R, ky + 4.45, W, "Conclusion & Future Work")
text(R, ky + 5.4, W, 3.4, [
    "CodeS reproduced within 0.1 points; abstention makes its answers more trustworthy, running locally.",
    [("Next: ", {"bold": True}), ("CodeS-3B and more, more diverse candidate queries; then a platform that plugs into any "
                                  "database (Spark, Snowflake, NoSQL via a SQL gateway) with access control.", {})]], size=27, spacing=0.15)

header(29, R, 41.05)
text(R, 41.95, W, 3.7, [
    [("Supervisor: ", {"bold": True}), ("M Parameswar, Associate Professor", {})],
    ("Team 18", {"bold": True, "colour": NAVY}),
    "2320090050 – N V V S S Jayakanth Kamisetti",
    "2320090009 – Boddupally Narendar",
    "2320090018 – M Praneeth Reddy"], size=27, shape=P[30], spacing=0.25)

prs.save(OUT)
print("saved", OUT)
