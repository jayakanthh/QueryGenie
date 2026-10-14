"""
Local (Apple Silicon / CPU) variant of the Tier-2 Spider evaluation.

Runs the evaluated CodeS pipeline (querygenie/pipeline.py: full CodeS database prompt,
4 beams, authors' first-executable selection) and scores with the *simple* sorted-rows
metric only. The reported numbers (T2-005, T2-006, AB-10x) come from the Colab harness,
research/reproduction/colab_eval_tier2.py, which also runs the official Spider evaluator and records
all candidates — use that for anything that goes in a report.

Usage:
    python research/reproduction/eval_spider_full.py --limit 50 --run-id local-smoke
"""
from __future__ import annotations
import argparse, csv, datetime, json, os, sqlite3, sys, time

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)
from querygenie.pipeline import (build_prefix, check_sql_executability, clean_sql, encode,  # noqa: E402
                          get_db_schema, load_db_comments, post_process)

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

    db_comments = load_db_comments(os.path.join(SPIDER, "tables.json"))
    schema_cache = {}
    def schema_for(db_id):
        if db_id not in schema_cache:
            schema_cache[db_id] = get_db_schema(db_path(db_id), db_comments, db_id)
        return schema_cache[db_id]

    correct = pexec = 0
    t0 = time.time()
    for i, ex in enumerate(dev):
        db_id, question, gold = ex["db_id"], ex["question"].replace("\n", " "), ex["query"]
        sch = schema_for(db_id)
        _, prefix = build_prefix(db_path(db_id), question, schema=sch)
        ids = encode(tok, prefix)
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
