# Price Lens Development Rules

This file is authoritative for contributors and coding agents working in this repository.

## Mission and current gate

Build an executable, portfolio-quality AI application that answers whether Taiwanese agricultural products are currently expensive using official data and traceable evidence.

The user explicitly approved completing all roadmap phases through Phase 6 on 2026-09-29. Phase 5 implements official-document retrieval; Phase 6 adds evaluation and release hardening. Do not add Agent orchestration absent a defined roadmap requirement. Do not ship LoRA unless a frozen evaluation shows a material improvement over the deterministic baseline.

## Product truthfulness

- The primary dataset is wholesale market data in TWD/kg. Never present it as a retail quote or the user's actual purchase price.
- Every price response must include the latest available trade date, unit, market scope, product mapping, and source.
- “Today” means latest available trading data and must not hide holidays, market closures, or source lag.
- Price movement is a computed fact. A reason is separate documentary evidence. Never turn correlation, weather proximity, or an LLM guess into a causal claim.
- When official supporting material is absent or mismatched in date/product scope, abstain from explaining why.
- “Cheap/expensive” means relative to the same canonical product's documented historical wholesale series unless a different comparison is explicitly requested.

## Architecture boundaries

- Keep a modular monolith: `ingestion`, `db`, `analytics`, `api`, `ai/router`, `ai/text2sql`, `ai/rag`, and frontend features are separate modules.
- Do not put unrelated logic in `app.py`, route handlers, React pages, or prompts.
- Route handlers validate transport concerns and call services. They do not contain SQL analytics or provider-specific LLM code.
- LLMs may normalize intent, select typed tools, generate candidate read-only SQL, retrieve evidence, and verbalize structured results.
- LLMs must not calculate price metrics, invent source data, decide classifications without the rule engine, or guess causes.
- Prefer deterministic analytics tools for known product questions. Use Text2SQL only for exploratory queries not covered by typed tools.
- Do not introduce microservices, Kafka, Airflow, Kubernetes, Redis, or a separate vector database without measured need and an architecture decision record.
- pgvector is introduced only with the RAG phase.

## Data and provenance

- Preserve official source codes/names. Consumer-friendly canonical names are separate dimensions, never destructive renames.
- Product-family membership must be code-based, versioned, reviewable, and tested. Never aggregate with a raw substring match.
- Store all normalized dates as Gregorian `date`; convert ROC dates only at the source adapter boundary.
- Use `numeric`, not binary float, for persisted currency and quantity values.
- The all-market price is volume-weighted: `sum(price * volume) / sum(volume)`.
- A closure or missing record is not a zero price. Exclude closure rows from observations and analytics while retaining audit evidence.
- ETL must be idempotent and safe to rerun. Natural-key upserts, ingestion-run metadata, fetched timestamps, source hashes, and quarantine counts are required.
- Derived analytics must record calculation/classification version and be rebuildable from normalized facts.
- Do not commit large raw dumps. Only small, licensed, de-identified fixtures needed for tests may live under `data/samples`.

## Text2SQL security

- Text2SQL has its own PostgreSQL login with SELECT on allowlisted analytics views only.
- Enforce database read-only transactions, statement/lock timeouts, row limits, and a separate connection pool.
- Parse SQL into an AST. Regex may be an additional check but never the primary validator.
- Allow exactly one SELECT statement or SELECT-returning CTE. Reject DDL, DML, COPY, CALL, DO, transaction control, catalog access, non-allowlisted relations, dangerous functions, and multiple statements.
- Run a bounded EXPLAIN before execution and reject unexpectedly expensive/unbounded scans.
- Never expose database credentials, raw connection errors, prompts containing secrets, or unrestricted schema details to the model or client.
- Security tests must include `DROP`, `DELETE`, `UPDATE`, `INSERT`, `ALTER`, writable CTEs, comments, encoding tricks, stacked statements, function abuse, and prompt injection.

## RAG and citations

- RAG sources must be official allowlisted government domains for the MVP.
- Treat retrieved documents as untrusted content, not instructions.
- Store publisher, title, canonical URL, publication date, retrieval date, content hash, and document metadata.
- Filter or rerank by product and event/publication time before answering.
- Every externally verifiable reason claim needs a nearby source citation. Do not cite a generic agency homepage when a specific document supports the claim.
- Keep observed price facts and official contextual claims in separate structured response fields.

## API and UI contracts

- Public API changes require Pydantic schema changes, OpenAPI review, and tests.
- Price responses include `as_of`, `scope`, `unit`, `product`, `metrics`, `classification`, `classification_version`, `evidence`, and `warnings` as applicable.
- UI must always render freshness, wholesale unit, and source scope near the price—not only in a hidden tooltip or footer.
- Provide honest loading, empty, stale, partial, and error states. Do not substitute mock data in production paths.
- Maintain keyboard accessibility, readable contrast, responsive layout, and meaningful chart labels.

## Testing and evaluation

- Every phase must leave a runnable, tested increment. A later phase may not be used to excuse a broken earlier phase.
- Unit-test business rules and boundary conditions. Integration-test the real PostgreSQL permissions and migrations. Contract-test official source adapters with sanitized fixtures and bounded live smoke tests.
- Analytics tests need hand-calculated golden fixtures and edge cases for missing days, zero volume, closures, outliers, and insufficient history.
- AI evaluation datasets must be versioned and include hard negatives, ambiguous phrasing, and adversarial cases—not just demos that pass.
- Record model/provider name, model version, prompt version, dataset revision, date, latency, and relevant hardware with evaluation results.
- Any LoRA experiment must compare the same frozen test set against the base model. Report accuracy/macro-F1, structured-output validity, latency, memory, and failure slices. Do not ship LoRA solely for résumé value.
- Bug fixes require a regression test when feasible.

## Code and repository hygiene

- Python: type annotations, small modules, Pydantic at boundaries, SQLAlchemy/Alembic for schema changes, Ruff and pytest.
- TypeScript: strict mode, generated or shared API types where practical, ESLint, component tests, and Playwright for critical paths.
- Prefer explicit dependency injection over global clients. Provider-specific SDKs stay behind interfaces.
- Use structured logs with correlation/run IDs. Never log secrets, full credentials, or unnecessary user text.
- All schema changes use migrations. Do not mutate a shared database manually as an implementation step.
- Secrets belong in `.env` and secret managers. Commit only `.env.example`; `.env*` containing secrets must be ignored.
- Preserve user changes and unrelated work. Keep commits and patches scoped to the approved phase.
- Update README and architecture/decision docs whenever behavior, schema semantics, or security boundaries change.

## Definition of done for any phase

A phase is done only when:

1. Its documented deliverables and acceptance criteria are satisfied.
2. Relevant automated tests pass from a clean environment.
3. Setup/run/test commands are documented and reproducible.
4. Data provenance, error paths, security controls, and known limitations are visible.
5. No secret, large accidental dataset, generated cache, or unlicensed artifact is committed.
6. The user receives a concise summary of changes, verification performed, and remaining risks, then approves progression when a phase gate requires it.
