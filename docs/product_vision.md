# QueryGenie — Product Vision (future direction)

> Captured 2026-08-15 from Jaikanth's idea. This is a **forward-looking product vision**, not a
> Phase-I deliverable. Phase-I stays focused on reproducing CodeS and the three planned
> contributions; this document records where the project could go as a real product afterward.

## The idea, in Jaikanth's words (paraphrased)

Turn QueryGenie from a demo into an **app / platform that companies integrate into their
workflow**. Specifically:

1. **Multi-database compatibility** — work with **Apache Spark and other databases** (Postgres,
   MySQL, SQL Server, etc.), with the user choosing which connector to use.
2. **Access levels based on users** — role-based permissions so different users see/query only
   what they're allowed to.
3. **Database visualization & selection** — browse the databases available to you, see and
   select them, and run natural-language queries against the selected database(s).
4. **Per-database model adaptation** — optionally **adapt/train the model on a specific database
   (one-time)** so it fetches and queries that database more accurately.

## My honest feasibility read

Overall: **the idea is sound and mostly buildable with standard engineering** — and, importantly,
the most interesting part (per-database adaptation) is *directly supported by the anchor paper*.
The main risk is scope: this is a real product, not a semester's work, so it belongs as **roadmap
/ future work**, with a thin slice demoable for the capstone.

| Piece | Feasible? | Notes |
|---|---|---|
| Multi-DB connectors (Spark, Postgres, MySQL…) | ✅ Yes | Use SQLAlchemy / JDBC / Spark SQL. **Catch:** SQL *dialects differ* (Spark SQL vs ANSI vs Postgres). The model must generate the right dialect → needs dialect-aware prompting + a validation/repair step per engine. Standard but real work. |
| Role-based access levels (RBAC) | ✅ Yes | Standard app auth (users, roles, table/row/column permissions). Enterprise-critical. Adds meaningful scope (auth, multi-tenant). Best as roadmap, not Phase-I. |
| Database visualization / schema browser | ✅ Yes | Introspect schema → show tables/columns/ERD, let the user pick which DB/tables to query. Good UX; also improves accuracy by scoping the schema the model sees. |
| Per-DB model adaptation ("train once on the DB") | ✅ Yes — and paper-backed | **This is literally CodeS Section 7 (bi-directional data augmentation):** generate synthetic (question, SQL) pairs for the new schema, then fine-tune once. Two flavours: **(a) fine-tune per DB** (best accuracy, GPU + time per DB), or **(b) no training — schema filter + BM25 value indexing at query time** (cheaper, already how CodeS handles new DBs). A middle path (few-shot + indexing) is the pragmatic default. |

### Why this fits QueryGenie specifically
- The **local / private** angle is a genuine differentiator for enterprises: schema and data never
  leave the company's machine (no sending your DB to OpenAI). That's the trust story.
- Per-DB adaptation is exactly the **benchmark-to-reality gap** (contribution #3): models score
  85%+ on Spider but collapse on real enterprise schemas. "Adapt once per customer DB" is the
  practical fix — and a real product wedge.
- The **confidence-aware abstention** (contribution #2) matters even more in a company setting:
  a wrong SQL on a production DB is worse than "I'm not sure — did you mean X?".

### Honest cautions
- **Scope creep is the enemy.** RBAC + multi-tenant + Spark + per-DB training is a startup, not a
  Phase-I project. For the capstone, keep the graded work on reproduction + the 3 contributions,
  and demo *one* thin vertical slice of this vision (e.g. connect to one extra DB type + schema
  browser).
- **Dialect correctness** is the sleeper difficulty — generating valid Spark SQL vs Postgres is
  not free; the self-correction loop helps but isn't a full fix.
- **Per-DB fine-tuning cost**: fine-tuning a model for every customer DB is expensive to operate.
  The retrieval/indexing path (no training) is the cheaper MVP; offer training as a premium tier.

## Serving optimizations (future, for the platform — not the capstone demo)

- **TurboQuant (Google Research, 2026)** — compresses the **KV cache** to ~3 bits with no
  training and near-lossless accuracy (~8× faster attention). Note: it compresses the KV cache,
  **not the model weights**, so it helps the *enterprise-serving* case (many concurrent users,
  long enterprise schemas → large KV cache on GPU servers), letting us serve far more queries per
  GPU. It does **not** help the local 16 GB Mac demo (bottleneck there is weight size, and
  sequences are short); it's also Triton/vLLM (CUDA) today, not Apple MPS.
  Ref: https://research.google/blog/turboquant-redefining-ai-efficiency-with-extreme-compression/
- **Weight quantization (MLX / GGUF 4-bit)** — the right lever for running larger CodeS sizes on
  constrained local hardware (e.g. 7B on a 16 GB Mac). Slight accuracy cost, so keep the graded
  Tier-2 reproduction unquantized.

## Suggested phasing (if pursued after Phase-I)
1. **MVP**: schema browser + connect to 2–3 DB engines (SQLite, Postgres, Spark) via a connector
   abstraction; dialect-aware prompting; existing self-correction. No training, no auth.
2. **Adaptation**: per-DB schema/value indexing (CodeS schema filter + BM25) → measurable accuracy
   lift on a real schema. Optional one-time fine-tuning as a premium path.
3. **Enterprise**: RBAC, multi-tenant, audit logging, deployment packaging.

## Status
Idea recorded. Not started — revisit after the Phase-I reproduction and enhancements are done.
See also `README.md` (contributions) and `CLAUDE.md` (project constraints).
