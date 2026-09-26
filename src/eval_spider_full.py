"""
Tier-2 reproduction, faithful-prompt variant: Spider-dev Execution Accuracy using
the *full* CodeS database prompt the SFT model was trained on.

Prompt = schema_sequence + "\n" + content_sequence + "\n" + question + "\n", with a
BOS token prepended — replicating utils/load_sft_dataset.prepare_text2sql_prefix_sequence.
  - schema_sequence:  authors' get_db_schema_sequence (types, PK, representative
    values via SELECT DISTINCT ... LIMIT 2, foreign keys).
  - content_sequence: "matched contents" — cell values matched to the question by
    the authors' get_matched_entries (difflib + fuzzy, score >= 0.9), replacing the
    Lucene BM25 coarse step with a direct distinct-value scan (fine for small Spider DBs).

Vendored authors' code lives in src/vendor/ (Apache-2.0). Compared with the
schema+FK prompt in eval_spider.py (which gave EX 64.8%), this should recover most
of the gap to the reported 77.9%.

Usage:
    python src/eval_spider_full.py --limit 50 --run-id T2-full-smoke
    python src/eval_spider_full.py --run-id T2-002            # full 1034
"""
from __future__ import annotations
import argparse, csv, datetime, json, os, sqlite3, sys, time

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "src", "vendor"))
from codes_db_utils import (get_db_schema, get_db_schema_sequence, get_matched_content_sequence,
                            check_sql_executability, detect_special_char)
from codes_bridge import get_matched_entries, get_column_picklist

SPIDER = os.path.join(REPO, "data", "spider_full", "spider_data")
DEV = os.path.join(SPIDER, "dev.json")
DBDIR = os.path.join(SPIDER, "database")
LOG = os.path.join(REPO, "results", "reproduction_log.csv")


def db_path(db_id):
    return os.path.join(DBDIR, db_id, f"{db_id}.sqlite")


def run_sql(path, sql):
    try:
        con = sqlite3.connect(path)
        con.text_factory = lambda b: b.decode(errors="ignore")
        rows = con.execute(sql).fetchall()
        con.close()
        return True, sorted([tuple(str(c) for c in r) for r in rows])
    except Exception:
        return False, None


def clean_sql(text):
    text = text.strip().replace("```sql", "").replace("```", "").strip()
    return text.split(";")[0].strip()


def post_process(sql, schema_items):
    """Authors' text2sql_zero_shot.post_process: backtick-quote special column names."""
    sql = sql.replace("\n", " ")
    for table in schema_items:
        for cn in table["column_names"]:
            if detect_special_char(cn) and cn in sql:
                sql = sql.replace(cn, "`" + cn + "`")
    while "``" in sql:
        sql = sql.replace("``", "`")
    return sql


def matched_contents_for(path, schema, question):
    """Replicate prepare_sft's fine matching over a full distinct-value scan."""
    fine = {}
    for table in schema["schema_items"]:
        tname = table["table_name"]
        for cname in table["column_names"]:
            try:
                picklist = get_column_picklist(tname, cname, path)
            except Exception:
                continue
            # Authors' index = str(value) for every column, numbers included, 0 < len <= 25.
            vals = []
            for v in picklist:
                if v is None:
                    continue
                if isinstance(v, bytes):
                    try:
                        v = v.decode("utf-8")
                    except UnicodeDecodeError:
                        v = v.decode("latin-1")
                v = str(v).strip()
                if 0 < len(v) <= 25 and v not in vals:
                    vals.append(v)
            picklist = sorted(vals)
            if not picklist:
                continue
            fm = get_matched_entries(question, picklist)
            if not fm:
                continue
            tc = f"{tname}.{cname}"
            for _m, (field_value, _s, match_score, _sm, _sz) in fm:
                if match_score < 0.9:
                    continue
                fv = field_value.strip()
                if tc not in fine:
                    fine[tc] = []
                if len(fine[tc]) < 25 and fv not in fine[tc]:
                    fine[tc].append(fv)
    return fine


def load_db_comments():
    """Column/table comments from tables.json, as prepare_sft_datasets.py builds them."""
    def rsc(names, comments):
        return ["" if n.replace("_", "").replace(" ", "") == c.replace("_", "").replace(" ", "") else c
                for n, c in zip(names, comments)]
    out = {}
    for d in json.load(open(os.path.join(SPIDER, "tables.json"))):
        cn = [c.lower() for _, c in d["column_names_original"]]
        ti = [t for t, _ in d["column_names_original"]]
        cc = rsc(cn, [c.lower() for _, c in d["column_names"]])
        tn = [t.lower() for t in d["table_names_original"]]
        tc = rsc(tn, [t.lower() for t in d["table_names"]])
        out[d["db_id"]] = {t: {"table_comment": tcm,
                               "column_comments": {c: m for tix, c, m in zip(ti, cn, cc) if tix == k}}
                           for k, (t, tcm) in enumerate(zip(tn, tc))}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="seeklhy/codes-1b-spider")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--beams", type=int, default=4)
    ap.add_argument("--candidates", type=int, default=4,
                    help="beams returned; first executable one is kept (authors use 4)")
    ap.add_argument("--run-id", default="T2-003")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    torch.manual_seed(args.seed)
    dev = json.load(open(DEV))
    if args.limit:
        dev = dev[: args.limit]

    device = "mps" if torch.backends.mps.is_available() else ("cuda" if torch.cuda.is_available() else "cpu")
    dtype = torch.bfloat16 if device in ("mps", "cuda") else torch.float32
    print(f"loading {args.model} on {device} ...")
    tok = AutoTokenizer.from_pretrained(args.model)
    model = AutoModelForCausalLM.from_pretrained(args.model, dtype=dtype).to(device).eval()

    db_comments = load_db_comments()
    schema_cache = {}
    def schema_for(db_id):
        if db_id not in schema_cache:
            sch = get_db_schema(db_path(db_id), db_comments, db_id)
            schema_cache[db_id] = (sch, get_db_schema_sequence(sch))
        return schema_cache[db_id]

    correct = pexec = 0
    t0 = time.time()
    for i, ex in enumerate(dev):
        db_id, question, gold = ex["db_id"], ex["question"].replace("\n", " "), ex["query"]
        sch, schema_seq = schema_for(db_id)
        matched = matched_contents_for(db_path(db_id), sch, question)
        content_seq = get_matched_content_sequence(matched)
        prefix = schema_seq + "\n" + content_seq + "\n" + question + "\n"

        ids = [tok.bos_token_id] + tok(prefix, truncation=False)["input_ids"]
        if len(ids) > 4096 - 256:  # authors keep the END of the prompt (the question)
            ids = [tok.bos_token_id] + ids[-(4096 - 256 - 1):]
        input_ids = torch.tensor([ids], device=device)
        attn = torch.ones_like(input_ids)
        with torch.no_grad():
            out = model.generate(input_ids=input_ids, attention_mask=attn, max_new_tokens=256,
                                 num_beams=args.beams, num_return_sequences=args.candidates,
                                 pad_token_id=tok.eos_token_id)
        # Authors' selection rule: return all beams, keep the first that passes
        # EXPLAIN QUERY PLAN, else fall back to beam 0 (text2sql_zero_shot.py).
        cands = [clean_sql(post_process(c, sch["schema_items"])) for c in
                 tok.batch_decode(out[:, input_ids.shape[1]:], skip_special_tokens=True,
                                  clean_up_tokenization_spaces=False)]
        pred = next((c for c in cands if check_sql_executability(c, db_path(db_id)) is None),
                    cands[0] if cands[0].strip() else "SQL placeholder")
        p_ok, p_rows = run_sql(db_path(db_id), pred)
        g_ok, g_rows = run_sql(db_path(db_id), gold)
        pexec += p_ok
        correct += (p_ok and g_ok and p_rows == g_rows)
        if (i + 1) % 20 == 0 or i + 1 == len(dev):
            print(f"[{i+1}/{len(dev)}] EX={correct/(i+1):.4f} (exec {pexec/(i+1):.2f}) "
                  f"{(time.time()-t0)/(i+1):.1f}s/ex")

    n = len(dev); ex_acc = correct / n; runtime = round(time.time() - t0, 1)
    print(f"\n=== Execution Accuracy (full CodeS prompt) on Spider dev ({n}): {ex_acc:.4f} "
          f"({correct}/{n}) | executes {pexec/n:.3f} | {runtime}s ===")

    import transformers
    fields = ["run_id","timestamp","tier","model","dataset","seed","metric_name",
              "metric_value","runtime_s","gpu","torch_version","transformers_version","notes"]
    row = {"run_id": args.run_id, "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
           "tier": "Tier 2 - Spider dev EX (full CodeS prompt)", "model": args.model,
           "dataset": f"Spider dev ({n} examples)", "seed": args.seed,
           "metric_name": "execution_accuracy_spider_dev", "metric_value": round(ex_acc, 4),
           "runtime_s": runtime, "gpu": device, "torch_version": torch.__version__,
           "transformers_version": transformers.__version__,
           "notes": (f"beams={args.beams}; candidates={args.candidates} (first executable kept); FULL CodeS prompt (schema+values+matched contents, "
                     f"BOS-prepended); EX by result-set match; distinct-scan value retriever "
                     f"(no Lucene). Target 77.9%. executes {pexec/n:.3f}.")}
    new = not os.path.exists(LOG)
    with open(LOG, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        if new: w.writeheader()
        w.writerow(row)
    print("logged", args.run_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
