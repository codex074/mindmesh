# Merge TradingAgents into MindMesh2.0, then prep for VPS deployment

## Deliverable

Write this plan as `MindMesh2.0/plan.md` — a checklist-style document meant to be handed to another coding agent (referred to by the user as "Qwen"/"claude-9arm") to execute **incrementally, one checklist item at a time**, not all at once. Each step below is written so it can be picked up, done, and checked off independently, with enough context inline that the executing agent doesn't need this conversation's history.

## Context

The user has two independent, unrelated Python projects sitting side by side in a plain (non-git) folder `MindMesh2.0/`:

- **`TradingAgents/`** — a CLI/library multi-agent LLM trading-analysis framework (own git repo, remote `TauricResearch/TradingAgents.git`, ~10 local commits ahead of upstream). No web server, no multi-user support, no auth.
- **`OpenBB/`** — an unmodified fork of `OpenBB-finance/OpenBB` (own git repo), a finance-data platform with a Python SDK.

`MindMesh2.0/` also contains a fully fleshed-out, decision-locked planning doc, **`PRODUCT_PLAN.md`**, for a not-yet-built FastAPI web app (`apps/lean_web/`) that wraps the OpenBB SDK with a BYOK (bring-your-own-key) AI analysis feature, designed from day one for Docker+Caddy VPS deployment. It never mentions TradingAgents.

The user wants to know if TradingAgents can be merged into this parent project and eventually deployed on a VPS for remote multi-user access. They confirmed: (1) plan the **merge into MindMesh2.0 first**, VPS deployment is a later follow-on step; (2) they don't yet know how many users / what usage pattern the eventual deployment needs — so this plan should solve correctness at small scale without building premature multi-tenant infrastructure.

Investigation (two Explore passes + code verification) established that TradingAgents' only real blocker for shared/web use is a **module-level global mutable `_config` dict** (`tradingagents/dataflows/config.py`) read mid-graph by multiple call sites — concurrent runs in one process would clobber each other's provider/model/language settings. Three other suspected blockers turned out to be non-issues on closer reading: `memory_log_path` and `data_cache_dir` are already env-overridable (`default_config.py`), and `checkpoint_enabled` already defaults to `False` (verified directly in `tradingagents/default_config.py:105`), so per-ticker SQLite checkpoint collisions never occur unless checkpointing is explicitly turned on.

There is also a live-looking `DEEPSEEK_API_KEY` sitting in `TradingAgents/.env` (confirmed genuinely untracked — in `.gitignore`, not in `git ls-files`, and covered by `.dockerignore`) that needs rotating/clearing as hygiene before this becomes part of any shared or deployed artifact.

## Recommended approach

**Don't touch TradingAgents' source or vendor it into a monorepo.** Fix the one real concurrency issue by **process isolation** (run each analysis as its own OS subprocess) rather than refactoring the global config — this fully sidesteps the config, memory-log, and cache-dir concerns at once, requires zero upstream changes, and preserves the ability to `git pull` future upstream fixes into both `OpenBB/` and `TradingAgents/`.

**Build the merge as a new top-level app** (`MindMesh2.0/apps/lean_web/`) that consumes both `OpenBB` and `tradingagents` as installed Python packages (editable/local in dev, pinned git ref in Docker builds) — reusing the architecture and locked decisions already written in `PRODUCT_PLAN.md` (FastAPI + Jinja2, `stream_analysis()` interface, BYOK secret handling, no DB in MVP, Docker+Caddy for VPS) rather than inventing a competing design. TradingAgents' multi-agent debate becomes a **second adapter** ("deep" mode) behind the same `stream_analysis()` seam already planned for the simpler single-model "quick" BYOK mode.

### Named decisions

- **D1 — New `apps/` dir, outside both existing repos.** Neither `OpenBB/` nor `TradingAgents/` is touched/vendored.
- **D2 — `MindMesh2.0/` becomes its own git repo**, with `/OpenBB/` and `/TradingAgents/` `.gitignore`d (not submodules — both already track real upstream remotes independently; submodules would add detached-HEAD friction for no benefit here). A checked-in `scripts/bootstrap.sh` clones both into place from pinned remote+ref, making today's implicit "two folders sitting here" setup reproducible.
- **D3 — Consumed as installed dependencies, not copied code.** `pip install -e ../../TradingAgents` in dev; `pip install git+<fork-url>@<pinned-sha>` in the Docker image (never `COPY` the source tree — also keeps the `.env` secret out of any build context by construction).
- **D4 — Deep-mode jobs run one-per-subprocess via a small bounded pool** (e.g. `APP_DEEP_MAX_CONCURRENT_JOBS=3`), not asyncio/threads in-process. Each subprocess: builds a **full** config via `deepcopy(DEFAULT_CONFIG)` + overrides (a partial dict will `KeyError`), receives only the one needed provider API key via its own minimal `env=` (never the parent's full environment) — this is a clean, free implementation of the BYOK "ephemeral secret, never logged/stored" requirement already locked in the lean_web plan — and streams NDJSON events on stdout that the parent re-emits as `AnalysisEvent`s through the existing streaming route. On client cancel, the subprocess is killed.
- **D5 — Memory-log namespaced per authenticated identity** (the proxy-auth user from Caddy, matching the already-locked `APP_AUTH_MODE=proxy`), not per-job (would silently make the reflection feature dead — always an empty log) and not global (cross-user leakage of reasoning into one file). Concurrency-safety is a scheduling rule, not new code: cap concurrent deep jobs **per namespace to 1** (a semaphore keyed by user) so the log's existing atomic tmp+`os.replace()` writes never race; different users still run in true parallel.
- **D6 — Checkpointing stays off** (`checkpoint_enabled=False`, already the default) for the web integration — no resumable-run feature needed yet, and turning it on is what would reintroduce per-ticker SQLite collisions.
- **D7 — Data cache dir stays shared** (same-day OHLCV cache) — safe since checkpointing is off; writers use plain `to_csv()` not atomic replace, so a low-severity "reader sees a partial write" risk exists under concurrent writes to the same cache key — note it, don't build locking for it now.
- **D8 — Deploy pinning.** Before any VPS deploy: push the local ~10-commits-ahead `TradingAgents` branch to a personal fork remote and pin the Docker build to that fork+SHA (a VPS `git clone` of upstream `TauricResearch` would silently deploy a different, older app).
- **D9 — Secret hygiene**, in order: rotate the `DEEPSEEK_API_KEY` on the DeepSeek account; clear/delete the working-tree `TradingAgents/.env`; going forward the deployed app never puts a provider key in its own `.env` — BYOK keys come from end users per-request only (already locked in the lean_web plan).

### Extension point (explicitly deferred, not built now)

Swap D4's local subprocess pool for a real task queue (RQ/Celery/arq) when actual multi-user load justifies it — `redis` is already a `TradingAgents` dependency, so no new infra decision is needed that day, just a `pool.py` implementation swap behind the same interface. Per-user accounts/quotas beyond the proxy-auth identity, and horizontal scaling, are likewise deferred — matches the user's "not sure about scale yet" answer.

## Target folder structure

```
MindMesh2.0/                          # new git repo (D2)
├── .gitignore                        # excludes /OpenBB/, /TradingAgents/, .env, __pycache__
├── PRODUCT_PLAN.md              # single canonical copy (dedupe the OpenBB-nested untracked one)
├── VPS_BYOK_INTEGRATION_PLAN.md      # unrelated product plan, kept as-is
├── scripts/bootstrap.sh              # clones OpenBB + TradingAgents (pinned) into place
├── apps/
│   └── lean_web/
│       ├── app/
│       │   ├── main.py, config.py
│       │   ├── web/                  # routes.py, templates/, static/ — per PRODUCT_PLAN.md §11 unchanged
│       │   ├── market/                # unchanged from existing plan
│       │   ├── analysis/
│       │   │   ├── models.py         # AnalysisRequest + new analysis_mode: "quick" | "deep"
│       │   │   ├── module.py         # stream_analysis() dispatches by analysis_mode
│       │   │   └── adapters/
│       │   │       ├── openai_compatible.py / anthropic.py / gemini.py   # existing "quick" mode
│       │   │       └── deep_debate.py                                    # NEW — TradingAgents adapter
│       │   ├── deep/                 # NEW seam
│       │   │   ├── runner.py         # subprocess entrypoint: builds config, calls graph.stream(), emits NDJSON
│       │   │   ├── pool.py           # bounded process pool + per-namespace concurrency cap
│       │   │   └── namespace.py      # proxy-auth identity -> memory_log_path
│       │   └── security/secrets.py, outbound_url.py
│       ├── tests/ (incl. new test_deep_analysis_concurrency.py)
│       ├── Dockerfile, compose.yaml, Caddyfile, pyproject.toml, .env.example
├── OpenBB/                            # gitignored, untouched
└── TradingAgents/                     # gitignored, untouched
```

## Integration approach (deep-mode adapter)

`app/analysis/module.py`'s `stream_analysis()` stays the single locked interface from `PRODUCT_PLAN.md` §6.2, now dispatching on the new `analysis_mode` field:

```python
async def stream_analysis(request: AnalysisRequest) -> AsyncIterator[AnalysisEvent]:
    adapter = ADAPTERS[request.analysis_mode]   # "quick" -> existing adapter, "deep" -> deep_debate
    async for event in adapter.stream(request):
        yield event
```

`deep_debate.py` acquires a pool slot + per-namespace semaphore, builds the full `TradingAgentsGraph` config (mapping `ai.provider`/`ai.model` onto `llm_provider`/`deep_think_llm`/`quick_think_llm`), spawns `runner.py` with a minimal explicit `env=`, and streams its NDJSON stdout back as `AnalysisEvent`s — reusing the chunk-to-status logic already in `tradingagents/graph/analyst_execution.py` (`sync_analyst_tracker_from_chunk`) rather than reimplementing it. The UI's existing AI drawer (§8.2) gains one dropdown: "Quick (single model)" vs "Deep (multi-agent debate)".

## Checklist — execute top to bottom, one item at a time

### Phase A — Secret hygiene and repo groundwork (do first, blocks everything downstream)

- [ ] **A1. Rotate the leaked-looking DeepSeek key.** `TradingAgents/.env` currently contains a live-looking `DEEPSEEK_API_KEY`. Treat it as compromised (it sat in a plaintext file long enough to be flagged) — rotate it on the DeepSeek account. This is an out-of-repo action on the account, not a code change.
- [ ] **A2. Clear the local `.env`.** After rotating, delete or blank the values in `TradingAgents/.env` (keep `.env.example` as the template). Confirm it stays untracked: `git -C TradingAgents status --short` should not list `.env`, and `git -C TradingAgents check-ignore .env` should succeed.
- [ ] **A3. Push local `TradingAgents` commits to a durable fork remote.** The working tree is ~10 commits ahead of `origin` (`TauricResearch/TradingAgents.git`) and those commits aren't reachable from any remote yet. Add a personal fork remote (`git -C TradingAgents remote add fork <your-fork-url>`), push the current branch (`git -C TradingAgents push fork HEAD:main`), and record the exact commit SHA pushed — later steps pin to it.
- [ ] **A4. `git init` at `MindMesh2.0/`.** It is currently a plain folder, not a repo. Run `git init` at the `MindMesh2.0/` root.
- [ ] **A5. Add `MindMesh2.0/.gitignore`** excluding `/OpenBB/`, `/TradingAgents/`, `.env`, `__pycache__/`, `*.pyc`, `.venv/`. Both subfolders are independently version-controlled clones — they must not become part of this new repo's history.
- [ ] **A6. Dedupe the plan docs.** `PRODUCT_PLAN.md` currently exists both at `MindMesh2.0/PRODUCT_PLAN.md` and (untracked) `MindMesh2.0/OpenBB/PRODUCT_PLAN.md`. Keep one canonical copy at the `MindMesh2.0/` root, delete the copy inside `OpenBB/`.
- [ ] **A7. Commit the groundwork.** Commit `.gitignore`, `PRODUCT_PLAN.md`, `VPS_BYOK_INTEGRATION_PLAN.md`, and this `plan.md` itself to the new `MindMesh2.0` repo.
- [ ] **A8. Write `scripts/bootstrap.sh`.** A script that clones `OpenBB` (from its existing upstream fork, tracking as today) and `TradingAgents` (pinned to the fork+SHA from A3) into place if the folders don't already exist. Purpose: make today's implicit "two folders sitting here" setup reproducible on a fresh machine or the eventual VPS.

### Phase B — Scaffold the web app (no TradingAgents involvement yet)

- [ ] **B1. Scaffold `apps/lean_web/`** per `PRODUCT_PLAN.md` §11/§15 Phase 0: FastAPI app skeleton, Jinja2 templates dir, static assets dir, `/health/live` + `/health/ready` endpoints, `Dockerfile`, `compose.yaml`, `Caddyfile`, `pyproject.toml`, `.env.example`. Pass criterion (from the existing plan): a placeholder page deploys on local Docker.
- [ ] **B2. Market Data module (Phase 1 of the existing plan).** Implement `get_market_snapshot(query: MarketQuery) -> MarketSnapshot` backed by the OpenBB SDK + yfinance, per `PRODUCT_PLAN.md` §6.1/§7. Include summary cards, chart, table, CSV export, and the loading/error/empty states listed in §8.1.
- [ ] **B3. "Quick" AI analysis mode (Phase 2 of the existing plan).** Implement the `stream_analysis(request: AnalysisRequest) -> AsyncIterator[AnalysisEvent]` interface (§6.2) with the `openai_compatible` adapter first, the BYOK modal (§8.2), the `ephemeral_secret()` secret-handling module (§6.4), and secret-redaction tests. This establishes the streaming seam that the deep-mode adapter will plug into next.

### Phase C — Wire in TradingAgents as a second ("deep") analysis mode

- [ ] **C1. Local editable install.** Add `TradingAgents` as a dependency of `apps/lean_web` via `pip install -e ../../TradingAgents` (matches its existing `pyproject.toml` packaging). Do not copy any of its source into `apps/lean_web`.
- [ ] **C2. Extend `AnalysisRequest`** with `analysis_mode: Literal["quick", "deep"]` (default `"quick"`), and add the mode dropdown to the existing AI drawer UI from §8.2.
- [ ] **C3. Write `app/deep/runner.py`.** A subprocess entrypoint that: builds a full config via `deepcopy(DEFAULT_CONFIG)` from the installed `tradingagents` package plus request overrides (never a partial dict — `TradingAgentsGraph.__init__` indexes config keys directly and will `KeyError` on a partial one); sets `checkpoint_enabled=False` (keep the existing default — do not enable checkpointing, it would reintroduce per-ticker SQLite collisions under concurrent same-ticker runs); constructs `TradingAgentsGraph(config=...)` and calls `.stream()`; emits one NDJSON line per event to stdout, reusing the chunk-to-status mapping already in `tradingagents/graph/analyst_execution.py::sync_analyst_tracker_from_chunk` rather than reimplementing it; reads its one required LLM provider API key only from its own process env (never argv, never a file).
- [ ] **C4. Write `app/deep/namespace.py`.** Resolve the proxy-auth identity (Caddy basic auth, `APP_AUTH_MODE=proxy` already locked in §12) to a per-user `memory_log_path` (e.g. `<data_dir>/memory/<user>.md`). Do not use one shared global log (cross-user leakage) or a fresh path per job (silently makes the reflection/self-improvement feature dead — always reads an empty log). Leave `data_cache_dir` shared/unnamespaced — it's a same-day price cache, safe to share since checkpointing is off.
- [ ] **C5. Write `app/deep/pool.py`.** A bounded subprocess pool (e.g. `APP_DEEP_MAX_CONCURRENT_JOBS=3`, via `ProcessPoolExecutor` or `asyncio.create_subprocess_exec`) plus a semaphore keyed per-namespace (from C4) capping **concurrent deep jobs per user to 1** — this is what makes the memory-log's existing atomic tmp+`os.replace()` writes race-free without any new locking code. Different users still run in true parallel up to the pool's total size. On client disconnect/cancel, kill the subprocess.
- [ ] **C6. Write `app/analysis/adapters/deep_debate.py`.** Implements the same `stream()` shape as the quick-mode adapter: acquire a pool slot via C5, spawn `runner.py` (C3) with an explicit minimal `env={<one provider key env var>: request.ai.api_key}` — never `os.environ.copy()` — read its NDJSON stdout, yield `AnalysisEvent`s.
- [ ] **C7. Wire the dispatcher.** In `app/analysis/module.py`, `stream_analysis()` picks the adapter by `request.analysis_mode`: `"quick"` → existing adapter, `"deep"` → `deep_debate.py`. No other route/UI code needs to know which mode is subprocess-backed.
- [ ] **C8. Write `tests/test_deep_analysis_concurrency.py`.** The one test that actually exercises the global-`_config` fix in `TradingAgents/tradingagents/dataflows/config.py`: launch two deep-mode jobs simultaneously with **different** `output_language` and different `llm_provider`/model, assert each returned report reflects its own requested language/model (a same-config concurrency test would pass even if cross-contamination existed). Also test: same-namespace concurrent requests serialize; different-namespace concurrent requests run in parallel with separate log files.

### Phase D — Local verification (before touching Docker or a VPS at all)

- [ ] **D1.** Unit: `TradingAgentsGraph(config=deepcopy(DEFAULT_CONFIG) + partial overrides)` still constructs without `KeyError`.
- [ ] **D2.** Unit: `runner.py` run standalone for a known ticker/date emits valid NDJSON lines, ending in a `final_decision` event.
- [ ] **D3.** Unit: a fake deep adapter (`tests/fakes/`) satisfies the same `stream_analysis()` contract as the real one.
- [ ] **D4.** Security: confirm the BYOK API key never appears in the `runner.py` subprocess's argv (check via `ps`), stdout, or any log line.
- [ ] **D5.** Run the concurrency test from C8 and confirm it passes.
- [ ] **D6.** `docker compose up --build` locally; confirm `/health/ready` reports both market-data and deep-analysis-pool readiness.
- [ ] **D7.** End-to-end: open the dashboard, run a "quick" analysis on a ticker, then a "deep" analysis on the same ticker; confirm both stream to completion and the deep report shows bull/bear/risk debate structure (not a single-model summary).

### Phase E — Rest of the existing lean_web plan (unchanged, deep mode rides along)

- [ ] **E1.** Phase 3 from `PRODUCT_PLAN.md` — Anthropic + Gemini adapters for quick mode, provider-specific validation.
- [ ] **E2.** Phase 4 — SSRF protection on custom base URLs, reverse-proxy auth, rate limits, secure headers, non-root/read-only container, deployment smoke test.
- [ ] **E3.** Phase 5 — responsive/mobile layout, accessibility, chart interactions, copy/export, Thai/English locale files.

### Phase F — Explicitly deferred (do not build yet)

- [ ] **F1 (future, not now).** Swap Phase C's local subprocess pool for a real task queue (RQ/Celery/arq) once actual multi-user load justifies it. `redis` is already a `TradingAgents` dependency, so no new infra decision is needed that day — only `pool.py`'s implementation changes behind the same interface.
- [ ] **F2 (future, not now).** Per-user accounts/quotas beyond the proxy-auth identity, horizontal scaling, multi-worker deployment. Revisit once real usage numbers exist — the user has not yet decided expected scale.
- [ ] **F3 (future, separate plan).** VPS deployment itself — steps already outlined in `PRODUCT_PLAN.md` §13, plus pinning the Docker build to the A3 fork+SHA (a plain `git clone` of TradingAgents' upstream would silently deploy a different, older tree than what was tested here). Start this only after Phase D passes locally in full.
  - **HARD CONSTRAINT — do not overwrite `pharmshift`.** The target VPS already hosts another live service/app called `pharmshift`. This deployment (lean_web + TradingAgents) must be installed alongside it without disturbing it in any way: use a separate directory (not `pharmshift`'s existing path), separate Docker Compose project name (`docker compose -p lean_web ...`, not the default which is derived from the current directory name — verify it doesn't collide), separate host ports (check what `pharmshift` already binds before choosing `APP_PORT`), and a separate Caddy site block/domain (append to the existing Caddyfile rather than replacing it, or use Caddy's `import` for multiple sites) — never run a deploy step that could stop, remove, or rebuild `pharmshift`'s containers, volumes, or reverse-proxy config. Before the first real deploy: SSH in and inventory what's already running (`docker ps -a`, existing Caddyfile/nginx config, listening ports via `ss -tlnp`) and write that inventory down before touching anything.

## Verification plan

- Unit: `TradingAgentsGraph(config=deepcopy(DEFAULT_CONFIG) + partial overrides)` still constructs without `KeyError`; `runner.py` run standalone emits valid NDJSON ending in a `final_decision` event; fake deep adapter satisfies the same `stream_analysis()` contract as the real one; BYOK key never appears in subprocess argv/stdout/logs.
- **Key concurrency test** (the one that actually exercises the global-`_config` fix): launch two deep-mode jobs simultaneously with **different** `output_language` and different `llm_provider`/model, assert each report reflects its own requested language/model — same-config concurrency tests would pass even with the bug present.
- Same-namespace concurrent requests serialize (second job's memory-log read reflects the first's completed write); different-namespace requests run in true parallel with separate log files.
- `docker compose up --build` locally; `/health/ready` reports both market-data and deep-analysis-pool readiness.
- End-to-end: run "quick" analysis on a ticker (existing flow), then "deep" analysis on the same ticker, confirm both stream to completion and the deep report shows bull/bear/risk debate structure.

Only after all of the above pass locally does D8's fork-pinning and the VPS deploy steps already described in `PRODUCT_PLAN.md` §13 apply — this plan stops at "mergeable and deployable," with VPS rollout as a separate follow-on plan once the app works end-to-end locally.
