# Week-4 Red-Flag Gate — Evidence (Tier 1 smoke test)

**Status:** ✅ CLEARED
**Date:** 2026-08-14
**Where it ran:** Google Colab, Tesla T4 GPU (14.6 GB), Python 3.12.13
**Anchor model:** `seeklhy/codes-1b` (CodeS-1B, StarCoderBase-1B base, Apache-2.0)

## What the gate requires
"The original code runs once to verify it works" — load the released CodeS model,
generate SQL from a schema + question, and confirm the SQL executes.

## What happened

1. **Model loaded.** `AutoModelForCausalLM.from_pretrained("seeklhy/codes-1b")` loaded
   successfully (1.14 B parameters, ~150 s including the 4.55 GB weight download).
   Environment: torch 2.11.0+cu128, transformers 5.15.0, CUDA available (Tesla T4).

2. **SQL generated.** Prompt = toy student/result schema + the question
   *"Which students failed more than two subjects? A subject is failed if marks are below 40."*
   Beam search (4 beams, 256 max new tokens) produced, in 61.86 s:

   ```sql
   SELECT name FROM student
   WHERE student_id IN (
       SELECT student_id FROM result
       WHERE marks < 40
       GROUP BY student_id
       HAVING COUNT(subject) > 2
   );
   ```

3. **SQL executed.** Run against an in-memory SQLite database built from the toy schema:
   - `EXEC_OK = True`
   - Returned rows: `[('Meera',)]` — which is the **correct** answer
     (Meera has 3 failed subjects; the only student with more than two).

## Logged
Run `T1-001` recorded in [`results/reproduction_log.csv`](reproduction_log.csv).

## Important caveats (this is a liveness check, not a reproduction)
- Prompt format is a simplified hand-written version, **not** the CodeS repo's faithful
  schema-filtered / BM25 prompt. The faithful format is Tier 2.
- transformers 5.15.0 is far newer than the repo's pinned 4.28.1; the authors warn that
  version drift shifts inference slightly. This is a documented, expected deviation.
- `torch_dtype=` triggered a deprecation warning in transformers 5.x (`use dtype instead`) —
  harmless; the model still loaded and generated correctly.
- Not evaluated on Spider. Graded Execution/Exact-Match numbers come from Tier 2, which
  still needs a CUDA machine and the authors' pinned environment.

## How it was driven
Run through the Colab notebook **"Capstone project.ipynb"**
(https://colab.research.google.com/drive/1OooLxrtUlCXpuvIC-uvrubzyRlD70ZcL).
The Tier 1 logic from `notebooks/01_week4_gate_codes_setup.ipynb` was executed as a single
consolidated cell (browser automation cannot type multi-line Python into Colab without its
auto-indent corrupting the code; a consolidated payload sidesteps that). The notebook's own
Tier 1 cells are correct and unchanged.
