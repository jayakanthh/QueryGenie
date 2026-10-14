"""
LEGACY — superseded by research/reproduction/colab_eval_tier2.py (kept because it produced logged run
T2-001; see results/harness_audit.md). Do not use for new results.

Tier-2 reproduction: Execution Accuracy of CodeS on the Spider development set.

This is an inference-only reproduction (no training), so it does not need the
authors' CUDA-only libraries. It loads a released CodeS checkpoint, generates SQL
for each Spider dev question, executes both the predicted and the gold query
against the real Spider SQLite database, and marks the prediction correct when the
two result sets match (Execution Accuracy, EX).

Documented deviations from the paper's exact protocol (see the reproducibility
report): (1) the prompt is the schema + foreign keys, not the authors' full
database prompt with the learned schema filter and BM25-matched values; (2) EX is
computed by result-set comparison here rather than the official test-suite script.
Both are expected to lower EX relative to the reported 77.9%; the gap is the finding.

Usage:
    python research/reproduction/eval_spider_v1.py --model seeklhy/codes-1b-spider --limit 50
    python research/reproduction/eval_spider_v1.py --model seeklhy/codes-1b-spider           # full 1034
"""

from __future__ import annotations

import argparse, csv, datetime, json, os, sqlite3, sys, time

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "legacy"))
from database import build_schema_string  # noqa: E402
SPIDER = os.path.join(REPO, "data", "spider_full", "spider_data")
DEV = os.path.join(SPIDER, "dev.json")
DBDIR = os.path.join(SPIDER, "database")
LOG = os.path.join(REPO, "results", "reproduction_log.csv")


def db_path(db_id: str) -> str:
    return os.path.join(DBDIR, db_id, f"{db_id}.sqlite")


def run_sql(path: str, sql: str):
    """Execute a query; return (ok, sorted_rows_or_None, error)."""
    try:
        con = sqlite3.connect(path)
        con.text_factory = lambda b: b.decode(errors="ignore")
        cur = con.execute(sql)
        rows = cur.fetchall()
        con.close()
        return True, sorted([tuple(str(c) for c in r) for r in rows]), ""
    except Exception as e:  # noqa: BLE001
        return False, None, f"{type(e).__name__}: {e}"


def clean_sql(text: str) -> str:
    text = text.strip().replace("```sql", "").replace("```", "").strip()
    return text.split(";")[0].strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="seeklhy/codes-1b-spider")
    ap.add_argument("--limit", type=int, default=0, help="0 = all dev examples")
    ap.add_argument("--beams", type=int, default=4)
    ap.add_argument("--run-id", default="T2-001")
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

    # Cache one schema string per database.
    schema_cache: dict[str, str] = {}
    def schema_for(db_id):
        if db_id not in schema_cache:
            con = sqlite3.connect(db_path(db_id))
            schema_cache[db_id] = build_schema_string(con)
            con.close()
        return schema_cache[db_id]

    correct = pred_exec_ok = 0
    t0 = time.time()
    for i, ex in enumerate(dev):
        db_id, question, gold = ex["db_id"], ex["question"], ex["query"]
        prompt = f"{schema_for(db_id)}\n{question}\n"
        inp = tok(prompt, return_tensors="pt", truncation=True, max_length=1536).to(device)
        with torch.no_grad():
            out = model.generate(**inp, max_new_tokens=256, num_beams=args.beams,
                                 num_return_sequences=1, pad_token_id=tok.eos_token_id)
        pred = clean_sql(tok.decode(out[0][inp["input_ids"].shape[1]:], skip_special_tokens=True))

        p_ok, p_rows, _ = run_sql(db_path(db_id), pred)
        g_ok, g_rows, _ = run_sql(db_path(db_id), gold)
        pred_exec_ok += p_ok
        is_ex = p_ok and g_ok and p_rows == g_rows
        correct += is_ex
        if (i + 1) % 20 == 0 or i + 1 == len(dev):
            print(f"[{i+1}/{len(dev)}] EX={correct/(i+1):.4f} (exec-ok {pred_exec_ok/(i+1):.2f}) "
                  f"{(time.time()-t0)/(i+1):.1f}s/ex")

    n = len(dev)
    ex_acc = correct / n
    runtime = round(time.time() - t0, 1)
    print(f"\n=== Execution Accuracy on Spider dev ({n} ex): {ex_acc:.4f} "
          f"({correct}/{n}) | predicted-executes {pred_exec_ok/n:.3f} | {runtime}s ===")

    # Append to the reproduction log.
    import transformers
    fields = ["run_id","timestamp","tier","model","dataset","seed","metric_name",
              "metric_value","runtime_s","gpu","torch_version","transformers_version","notes"]
    row = {
        "run_id": args.run_id,
        "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
        "tier": "Tier 2 - Spider dev EX (inference-only)",
        "model": args.model,
        "dataset": f"Spider dev ({n} examples)",
        "seed": args.seed,
        "metric_name": "execution_accuracy_spider_dev",
        "metric_value": round(ex_acc, 4),
        "runtime_s": runtime,
        "gpu": device,
        "torch_version": torch.__version__,
        "transformers_version": transformers.__version__,
        "notes": (f"beams={args.beams}; schema+FK prompt (not full CodeS DB prompt); "
                  f"EX by result-set match. Target 77.9%. predicted-executes {pred_exec_ok/n:.3f}."),
    }
    new = not os.path.exists(LOG)
    with open(LOG, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        if new:
            w.writeheader()
        w.writerow(row)
    print("logged", args.run_id, "->", os.path.relpath(LOG, REPO))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
