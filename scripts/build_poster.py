"""Fill the department's project-poster template in place (header, logo, footer and theme kept).

    python scripts/build_poster.py
"""
import os

from pptx import Presentation
from pptx.util import Inches, Pt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE = os.path.join(ROOT, "docs", "Templates", "project-poster-tempalte.pptx")
OUT = os.path.join(ROOT, "docs", "Review-III", "QueryGenie_Poster.pptx")
FIG = os.path.join(ROOT, "docs", "report-latex", "images", "figures")
REALITY = None      # [Spider-Realistic EX, BIRD EX] once RL-001 / BD-001 finish

prs = Presentation(TEMPLATE)
s = prs.slides[0]
P = {p.placeholder_format.idx: p for p in s.placeholders}


def fill(idx, items, size=28, top=None, height=None, sub=None):
    shp = P[idx]
    left, width, cur_top, cur_h = shp.left, shp.width, shp.top, shp.height    # inherited from the layout
    if top is not None or height is not None:
        # set all four: a placeholder that overrides only some of them loses the rest
        shp.left, shp.width = left, width
        shp.top = Inches(top) if top is not None else cur_top
        shp.height = Inches(height) if height is not None else cur_h
    tf = shp.text_frame
    tf.clear()
    tf.word_wrap = True
    for k, it in enumerate(items):
        text, lvl = (it, 0) if isinstance(it, str) else it
        p = tf.paragraphs[0] if k == 0 else tf.add_paragraph()
        p.level = lvl
        fs = Pt(size if lvl == 0 else (sub or size - 4))
        if text.startswith("**") and "**" in text[2:]:
            head, rest = text[2:].split("**", 1)
            r = p.add_run(); r.text = head; r.font.bold = True; r.font.size = fs
            r = p.add_run(); r.text = rest; r.font.size = fs
        else:
            r = p.add_run(); r.text = text; r.font.size = fs
        p.space_after = Pt(size * 0.35)


def table(rows, left, top, width, col_w, size=22):
    t = s.shapes.add_table(len(rows), len(rows[0]), Inches(left), Inches(top), Inches(width), Inches(0.6 * len(rows))).table
    for j, w in enumerate(col_w):
        t.columns[j].width = Inches(w)
    for i, r in enumerate(rows):
        for j, v in enumerate(r):
            c = t.cell(i, j)
            c.text = v
            for p in c.text_frame.paragraphs:
                for run in p.runs:
                    run.font.size = Pt(size)
                    run.font.bold = i == 0 or r[0].startswith("Enhanced")


# ---- title
P[153].text_frame.text = "QueryGenie: A Self-Correcting Natural Language to SQL Interface"
for p in P[153].text_frame.paragraphs:
    for r in p.runs:
        r.font.size = Pt(66)
        r.font.bold = True

# ---- left column
fill(10, [
    "Text-to-SQL models let people who don't know SQL ask a database questions in plain English — but they answer "
    "every question with the same confidence, so a wrong answer looks exactly like a right one.",
    "We reproduced CodeS (SIGMOD 2024), an open-source text-to-SQL model: 77.8% Execution Accuracy on the Spider "
    "development set against 77.9% in the paper.",
    "Our enhancement, confidence-aware abstention, runs the four candidate queries CodeS already generates and counts how "
    "many agree. When they disagree, QueryGenie asks the user instead of guessing: it is then correct on 83.3% of the "
    "questions it answers (90.4% of all), wrong answers fall by 32%, and the gain is statistically significant.",
    "Everything runs locally on open weights in a desktop app.",
], size=34, top=8.4, height=11.6)

fill(96, [
    "**1. Reproduce **CodeS-1B on Spider within ±5–10% of the published result.",
    "**2. Ablate **the CodeS pipeline to find which parts matter.",
    "**3. Enhance **it with confidence-aware abstention and test it statistically.",
    "**4. Measure **the benchmark-to-reality gap on realistic questions and real databases.",
    "**5. Deliver **a working desktop application, not a notebook.",
], size=30, top=21.2, height=5.2)
pic = s.shapes.add_picture(os.path.join(FIG, "app_not_sure.png"), Inches(2.7), Inches(26.5), width=Inches(11.6))
cap = s.shapes.add_textbox(Inches(0.7), Inches(26.5 + 11.6 * 1600 / 2560 + 0.1), Inches(15.6), Inches(0.6))
cap.text_frame.text = "QueryGenie asking which reading was meant when its four queries disagree."
cap.text_frame.paragraphs[0].runs[0].font.size = Pt(20)
cap.text_frame.paragraphs[0].runs[0].font.italic = True

REFS = [
    "Li, H., et al. (2024). CodeS: Towards building open-source language models for text-to-SQL. arXiv:2402.16347.",
    "Yu, T., et al. (2018). Spider: A large-scale human-labeled dataset for complex and cross-domain semantic parsing and text-to-SQL task. arXiv:1809.08887.",
    "Li, J., et al. (2023). Can LLM already serve as a database interface? A big bench for large-scale database grounded text-to-SQLs. arXiv:2305.03111.",
    "Deng, X., Awadallah, A. H., Meek, C., Polozov, O., Sun, H., & Richardson, M. (2020). Structure-grounded pretraining for text-to-SQL. arXiv:2010.12773.",
    "Pourreza, M., & Rafiei, D. (2023). DIN-SQL: Decomposed in-context learning of text-to-SQL with self-correction. arXiv:2304.11015.",
    "Wang, X., et al. (2022). Self-consistency improves chain of thought reasoning in language models. arXiv:2203.11171.",
    "Geifman, Y., & El-Yaniv, R. (2017). Selective classification for deep neural networks. arXiv:1705.08500.",
    "Zhong, R., Yu, T., & Klein, D. (2020). Semantic evaluation for text-to-SQL with distilled test suites. arXiv:2010.02840.",
    "Li, H., et al. (2023). RESDSQL: Decoupling schema linking and skeleton parsing for text-to-SQL. arXiv:2302.05965.",
    "Lin, X. V., Socher, R., & Xiong, C. (2020). Bridging textual and tabular data for cross-domain text-to-SQL semantic parsing. arXiv:2012.12627.",
]
fill(28, REFS, size=22, top=35.7, height=9.8)

# ---- right column
s.shapes.add_picture(os.path.join(FIG, "final_pipeline.png"), Inches(16.8), Inches(8.5), width=Inches(15.6))
fill(26, [
    "**Data **(Hugging Face, approved source): Spider dev — 1,034 questions, 20 unseen databases; Spider-Realistic — "
    "508 questions without column names; BIRD Mini-Dev — 500 questions on 11 real-world databases.",
    "**CodeS pipeline (reproduced): **database prompt (schema, keys, sample values, matched values) → 4 candidate "
    "queries by beam search → first query that runs.",
    "**Enhancement: **execute all 4 candidates and count how many return the same result. Agreement below the "
    "threshold (τ = 0.2526, calibrated on held-out halves) → abstain and show the readings to choose from.",
    "**Evaluation: **official Spider evaluator; 10 calibration/test splits, paired t-test and Wilcoxon, bootstrap over questions.",
], size=30, top=8.5 + 15.6 * 1376 / 2560 + 0.3, height=9.6)

table([["System (Spider dev)", "Answered", "Correct", "Wrong"],
       ["CodeS-1B, paper", "100%", "77.9%", "—"],
       ["Our reproduction", "100%", "77.8%", "230"],
       ["Enhanced (tested)", "90.4%", "83.3%", "156"],
       ["All 4 must agree", "39.8%", "88.3%", "48"]], 16.8, 28.2, 8.4, [3.6, 1.6, 1.6, 1.6], size=20)
s.shapes.add_picture(os.path.join(FIG, "accuracy_coverage_T2-006.png"), Inches(25.4), Inches(28.2), width=Inches(7.0))
ra = REALITY or ["TBD", "TBD"]
fill(155, [
    "**Reproduction: **77.8% vs 77.9% (−0.1 pts) on a free Colab T4.",
    "**Enhancement: **+5.5 pts accuracy on answered questions; t-test p = 7.7×10⁻¹⁰, Wilcoxon p = 9.8×10⁻⁴, 95% CI +4.5 to +6.7.",
    f"**Beyond Spider: **Spider-Realistic EX {ra[0]}; BIRD Mini-Dev EX {ra[1]}.",
    "**Next: **a platform companies plug into any database (Spark, Snowflake, NoSQL via a SQL gateway), with access control and per-database adaptation.",
], size=30, top=32.6, height=7.2)

# ---- team
fill(30, [
    "M Parameswar, Designation",
    "2320090050 – N V V S S Jayakanth Kamisetti",
    "2320090009 – Boddupally Narendar",
    "2320090018 – M Praneeth Reddy",
], size=28)

os.makedirs(os.path.dirname(OUT), exist_ok=True)
prs.save(OUT)
print("saved", OUT)
