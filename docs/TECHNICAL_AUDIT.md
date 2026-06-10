# Technical Audit — worldcup-pool-optimizer

> Analysis-only audit (no code modified). All claims verified against files at commit `18ddb22`.

## Context

The owner requested a principal-level technical audit of this repository: an honest, evidence-based assessment with file:line citations, followed by a prioritized improvement plan. The repo is a private, single-admin web app that recommends World Cup score predictions by fitting probability models to bookmaker odds. The audit's purpose is to find what's actually broken, what's risky, and what's worth fixing given the project's maturity (personal tool, deployed to a VPS, World Cup starts June 2026 — the clock matters).

---

## Executive Summary

**Overall health: C-.** The mathematical core (Dixon-Coles + entropy calibration in `backend/app/services/score_model.py`) is genuinely well-engineered and well-tested, but the integration layer around it has rotted: **two entire UI features (Settings, Exports) call backend endpoints that do not exist**, the documented seed script **crashes on import**, and the default "Run Optimizer" flow **mixes stale odds from every historical refresh** into its consensus probabilities — silently corrupting the model inputs the whole app exists to compute. There is no CI, no lockfile-based backend install, no frontend lint/test tooling, and the README contradicts the code in at least three places.

**Top 3 risks:** (1) the stale-odds consensus bug degrades recommendation quality invisibly as refreshes accumulate; (2) frontend/backend contract drift with zero integration tests means features break silently on every refactor — it has already happened twice; (3) the synchronous optimizer run blocks the single-process event loop for minutes on a full 104-match schedule, which will time out at the nginx proxy and fail container health checks during the tournament, exactly when the app is needed.

**Top 3 opportunities:** (1) a half-day of contract fixes restores Settings + Exports and the seed script; (2) a minimal GitHub Actions pipeline (pytest + tsc + eslint) would have caught every broken feature found in this audit; (3) deleting ~5 dead modules and the legacy Poisson path removes the main source of confusion for future work.

---

## Repo Map

**Purpose:** Private web app for one admin user. Fetches bookmaker odds (The Odds API), fits a per-match score-probability model, and recommends the score predictions maximizing expected points under configurable pool scoring rules. Exports to CSV/Excel.

**Maturity:** Functional MVP / personal tool, deployed via Docker Compose to a Coolify VPS (`pool.joseathie.com` hardcoded in `docker-compose.yml:76-88`).

**Stack:** Python 3.12, FastAPI (async), SQLAlchemy 2 async + asyncpg-style psycopg, Alembic, PostgreSQL 16, NumPy/SciPy; React 18 + TypeScript (strict) + Vite + TanStack Query/Table + Tailwind; nginx serves the SPA and reverse-proxies `/api`.

**Architecture / data flow:**
```
The Odds API ──> api/odds.py (_do_odds_refresh) ──> OddsSnapshot/OddsEvent/BookmakerMarket/MarketOutcome (Postgres)
                                                          │
POST /api/model-runs (api/model_runs.py) ────────────────┤
  └─ per match: compute_consensus (odds_normalization.py) → fit_score_model (score_model.py: DC prior + entropy calibration)
     → compute_expected_points (optimizer.py × scoring.py) → MatchModelFit + ScoreRecommendation rows
                                                          │
GET recommendations / diagnostics ──> React pages         └─> export_service.py → CSV/Excel files on volume
```

**Key directories:**
| Path | Role |
|---|---|
| `backend/app/api/` | FastAPI routers (auth, matches, odds, pool_configs, model_runs, exports, health) |
| `backend/app/services/` | Business logic; `score_model.py` is the production model, `poisson_model.py` is the legacy one |
| `backend/app/db/` | SQLAlchemy models (11 tables) + async session |
| `backend/app/core/` | Settings (pydantic-settings), session-cookie auth, structlog, default scoring rules |
| `backend/alembic/` | 4 migrations; 0001 builds schema from live ORM metadata |
| `backend/tests/` | 1,484 lines of pytest (math core well covered; API thinly) |
| `frontend/src/pages/` | 9 pages; `api/` typed fetch client; no state library beyond TanStack Query |

**Surprises found during mapping:**
- `services/jobs.py` imports a module (`jobs_impl`) that doesn't exist anywhere in the repo.
- The README documents a bcrypt `ADMIN_PASSWORD_HASH` setup that was removed in commit `a836cc6` ("simplify auth: plain-text ADMIN_PASSWORD, drop bcrypt entirely").
- The frontend has a Settings page and an Exports list page whose backend endpoints were never built (or were removed).
- No CI of any kind (`.github/` does not exist), no `CONTRIBUTING`, no ADRs.

---

## Audit Report

Legend: **[F]** = verified fact, **[J]** = judgment call.

### Correctness & Architecture

**A1 — CRITICAL [F]: Settings page calls endpoints that don't exist.**
`frontend/src/pages/SettingsPage.tsx:26-48` issues `GET /api/settings` and `PUT /api/settings`. The backend registers no settings router — `backend/app/main.py:38-44` includes only health, auth, pool-configs, matches, odds, model-runs, exports. The page silently renders hardcoded defaults (form pre-seeded at `SettingsPage.tsx:31-45`) and every Save fails. Users believe they're configuring sport key/regions/bookmakers; they aren't — those only come from env vars (`backend/app/core/config.py:26-31`).

**A2 — CRITICAL [F]: Exports feature is broken end-to-end in the UI.**
`frontend/src/api/exports.ts:11-13` calls `GET /api/exports` (list) and `POST /api/exports` with `{format, model_run_id, pool_config_id}`. The backend router (`backend/app/api/exports.py`) exposes only `POST /csv`, `POST /excel`, and `GET /{export_id}/download`, expecting `{model_run_id, top_n}` (`backend/app/schemas/exports.py:18-20`). Both the Dashboard "Export Excel" button (`DashboardPage.tsx:66-72`) and the entire Exports page (`ExportsPage.tsx:27,42`) 404. The backend export code itself (`export_service.py`) is complete and tested (`tests/test_exports.py`) — it's purely a contract mismatch.

**A3 — CRITICAL [F]: Stale-odds consensus — the default optimizer flow averages odds from every snapshot ever fetched.**
`backend/app/api/model_runs.py:48-53`: when `odds_snapshot_id` is `None`, the query takes **all** `OddsEvent` rows for the match (the `order_by(created_at.desc())` has no limiting effect; `.all()` at line 55). All of their bookmaker markets are fed to `compute_consensus` (`odds_normalization.py:41-107`), which is a flat average. The Dashboard "Run Optimizer" button — the documented primary flow — passes no snapshot id (`frontend/src/pages/DashboardPage.tsx:53-57`). Consequence: after N odds refreshes, the model is fit to the average of N days of prices, not current prices. Recommendations drift toward stale market views with every refresh, with no error or warning.

**A4 — HIGH [F]: Seed script crashes on import.**
`backend/app/seed.py:13` — `from .core.security import hash_password` — but `core/security.py` (19 lines) defines only `create_session_token`/`verify_session_token`. `hash_password` was deleted in commit `a836cc6`. `python -m app.seed` (README Quick Start step 4 and Coolify deploy step 10) raises `ImportError` immediately. Also `seed.py:82` writes to the dead `users` table.

**A5 — HIGH [F]: Optimizer run blocks the event loop for the whole fit.**
`backend/app/api/model_runs.py:99-233` runs synchronously inside the request: per match, `fit_score_model` (`score_model.py:410` — 7-start L-BFGS-B at line 202-211 plus a 36-parameter entropy calibration at line 279-282 with numerically estimated gradients) and `compute_expected_points` (`optimizer.py:42-105` — 36 candidates × 36 outcomes × ~10 rules in pure Python, with `score_points` re-evaluated inside the breakdown loop at lines 79-87). At World Cup scale (104 matches) this is minutes of CPU inside a single uvicorn worker (`entrypoint.sh:15` — one process). During that time every other request — including `/health`, which the compose healthcheck probes with a 3s timeout (`docker-compose.yml:42-48`) — is starved, and nginx's default 60s `proxy_read_timeout` (`frontend/nginx.conf:9-13` sets none) will return 504 to the user while the run continues blind. **[J]** This will first hurt in production the week the tournament starts, when all 104 matches are flagged complete.

**A6 — MEDIUM [F]: Dual schema management (create_all + Alembic).**
`backend/app/main.py:18-24` runs `Base.metadata.create_all` on every startup as a fallback; `entrypoint.sh:11` runs `alembic upgrade head`; migration `0001_initial_schema.py:28-32` creates tables from *live ORM metadata* with `checkfirst=True`. This works today because every later migration re-checks columns (`0002_pool_config_scoring_mode.py:38-39`), but it means revision 0001 produces different schemas depending on when it runs, and any future migration that forgets the inspector guard will break on databases bootstrapped via `create_all`. **[J]** Fragile convention that relies on every future author knowing the trick.

**A7 — MEDIUM [F]: Legacy model pipeline still live in the seed path.**
Two parallel `fit_poisson` implementations exist: the legacy independent-Poisson `backend/app/services/poisson_model.py:109-281` and the production shim `score_model.py:570-572`. `seed.py:15,386` uses the **legacy** one, so seeded recommendations come from a different model than UI-triggered runs. Tests in `tests/test_poisson.py` and `tests/test_optimizer.py:5` also exercise the legacy module.

### Dead code **[F]**

| What | Where | Note |
|---|---|---|
| `jobs.py` imports nonexistent `.jobs_impl` | `backend/app/services/jobs.py:15,27` | Would crash if ever called; nothing calls it |
| `apscheduler` dependency | `backend/pyproject.toml:24` | No scheduler exists (README confirms manual-only refresh) |
| `diagnostics.py` (`compute_diagnostics`) | `backend/app/services/diagnostics.py` | Zero call sites; `model_runs.py:340` has its own implementation |
| `schedule_service.py` | `backend/app/services/schedule_service.py` | Zero call sites |
| `User` and `JobRun` tables | `backend/app/db/models.py:19-26, 288-297` | Auth is env-var based; no job runner |

### Security

**S1 — MEDIUM [F]: Login is plain-text comparison with no rate limiting.**
`backend/app/api/auth.py:21` — `if body.password != settings.ADMIN_PASSWORD` — non-constant-time compare of a plaintext env password, on an internet-exposed endpoint with no throttling or lockout. **[J]** For a single-admin hobby app this is tolerable, but `secrets.compare_digest` plus a simple per-IP delay is ~10 lines. Sessions are 7-day signed cookies (`core/security.py:5-9`) with no revocation — logout only deletes the cookie (`api/auth.py:37-40`).

**S2 — MEDIUM [F]: Random fallback `SESSION_SECRET`.**
`backend/app/core/config.py:12,15-20` falls back to `secrets.token_hex(32)` when unset. Every restart/redeploy silently invalidates all sessions, and multiple workers would mint mutually-invalid cookies. Misconfiguration is masked instead of surfaced (contrast with the explicit `ADMIN_PASSWORD` check at `api/auth.py:18-19`).

**S3 — LOW [F]: No security headers on the SPA.** `frontend/nginx.conf` sets no `X-Frame-Options`/`X-Content-Type-Options`/CSP. TLS is terminated by Coolify/Traefik (`docker-compose.yml:76-88`), so this is hardening, not a hole. Hardcoded `worldcup:worldcup` Postgres creds (`docker-compose.yml:5-8,30`) are confined to the internal compose network — acceptable at this maturity **[J]**.

**S4 — LOW [F]: Unbounded schedule upload.** `backend/app/api/matches.py:281` reads the whole upload into memory with no size cap (nginx default 1 MB `client_max_body_size` is the only backstop, and only in the Docker path).

### Performance

**P1 — HIGH [F]:** Same as A5 (event-loop blocking) — listed once.

**P2 — MEDIUM [F]: Full raw provider response stored per refresh.**
`backend/app/api/odds.py:73` saves the entire Odds API JSON payload into `OddsSnapshot.raw_response` (JSONB, `db/models.py:131`) on every refresh, alongside the fully normalized rows. Unbounded growth with no pruning; also re-sent nowhere. Same endpoint flushes per bookmaker-market row (`odds.py:104`), making refresh latency proportional to row count.

**P3 — MEDIUM [F]: 2 queries per match inside the model-run loop.**
`_build_market_probs` (`model_runs.py:32-96`) executes two queries per match (events + overrides) inside the `for match in matches` loop at line 163 — ~208 queries for a full schedule — and the overrides relationship was already eagerly loaded at line 145 and is ignored.

**P4 — LOW [F]: Match list loads every odds event to compute a boolean.**
`matches.py:56` evaluates `len(match.odds_events) > 0` on a fully loaded `selectinload` collection (`matches.py:231`); as snapshots accumulate this loads thousands of rows per page render to derive `has_odds`.

**P5 — LOW [F]: No DB indexes beyond PKs/uniques.** E.g. `Match.provider_event_id` (`db/models.py:49`) is queried per event during refresh (`odds.py:79-81`) and import (`matches.py:181-187`); `OddsEvent.match_id` is filtered in every model run. Data volumes are small; only matters if snapshots accumulate **[J]**.

### Testing

**T1 — HIGH [F]: Zero tests or static checks on the integration seam — where every real bug in this audit lives.**
Frontend has no test runner, no ESLint config, no `lint`/`test` script (`frontend/package.json:5-9`). Backend API tests cover auth and a few 401 paths (`tests/test_api_matches.py`, `tests/test_api_auth.py`) but never touch a real or fake DB (`tests/conftest.py:25-29` ships a client with no DB override), so `model-runs`, exports, pool-configs, and odds endpoints have no endpoint-level tests. Nothing validates that frontend API calls match backend routes — which is precisely how A1, A2, and A4 shipped.

**T2 — MEDIUM [F]: A third of backend test code targets the legacy model.**
`tests/test_poisson.py` (151 lines) and `tests/test_optimizer.py` (imports at line 5) test `poisson_model.py`, which production no longer uses; `test_score_model.py` (355 lines) covers the real pipeline. Green tests on dead code create false confidence.

**Strength:** the math/scoring tests that do exist are good — they assert behavior (probability identities, rule-boundary cases like `tests/test_scoring.py:60-80`, convergence tolerances), not just execution.

### Dependencies & DevEx

**D1 — HIGH [F]: No CI.** `.github/` doesn't exist. Nothing runs pytest, `tsc`, or builds images before merge — and the repo's history is merge-PR-driven (`git log`), so there is a place to hook it.

**D2 — MEDIUM [F]: Non-reproducible builds on both sides.**
Backend has no lockfile; `pyproject.toml:8-26` uses floor pins (`>=`) and the Docker image installs straight from it (`backend/Dockerfile:5-6`), including dev/test deps in production, as root, with `COPY . .` before install (no layer caching). Frontend has a `package-lock.json` but the Dockerfile ignores it — `frontend/Dockerfile:5-6` copies only `package.json` and runs `npm install`, not `npm ci`.

**D3 — LOW [F]: `datetime.utcnow()` (deprecated, naive) used throughout** — e.g. `model_runs.py:134,224`, `odds.py:46`, `exports.py:60` — alongside timezone-aware columns (`DateTime(timezone=True)`); psycopg/SQLAlchemy currently papers over it.

### Documentation

**DOC1 — HIGH [F]: README setup instructions are wrong in three load-bearing places.**
(1) The entire env setup and two troubleshooting sections instruct generating `ADMIN_PASSWORD_HASH` with passlib/bcrypt — neither the variable, nor passlib, nor bcrypt exist anymore (`core/config.py:11` wants plain `ADMIN_PASSWORD`; `.env.example:7-8` is correct). Following the README yields an unbootable login. (2) README says the compose file declares `SERVICE_FQDN_FRONTEND_80` — it doesn't; `docker-compose.yml` uses raw Traefik labels with a hardcoded domain. (3) The "Mathematical Model" section describes the legacy independent-Poisson fit, not the Dixon-Coles + entropy-calibration pipeline that actually runs (`score_model.py:1-11`).

### Strengths (preserve these)

- **`score_model.py` is the best file in the repo:** layered fallbacks (entropy-calibrated DC → DC prior → independent Poisson → incomplete, lines 410-465), explicit fit-status classification, rich diagnostics persisted to JSONB, boundary detection on ρ. Trustworthy numerical engineering.
- **Scoring engine is clean and exhaustively unit-tested** (`scoring.py` + 328-line test file); rule semantics are documented in `core/defaults.py` with a single source of truth shared by seed, create, and reset paths.
- **Row-isolated imports done right:** per-row savepoints with cache reset on rollback (`matches.py:317-328`) — a subtle async-SQLAlchemy pattern handled correctly.
- **Frontend fundamentals are sound:** strict TS, httpOnly-cookie auth (no localStorage tokens), centralized typed API client with decent error normalization (`client.ts:10-31`), consistent TanStack Query usage, no console.log/TODO litter.
- **Pragmatic ops for the scale:** auto-migrations on deploy, container healthchecks, single-domain reverse proxy so the backend needs no public exposure.

---

## Improvement Strategy

### Theme 1 — The frontend/backend contract is unenforced (explains A1, A2, A4, T1, D1)
**Target state:** every API route the frontend calls exists and is exercised by at least one test; CI fails otherwise.
**Principle:** in a two-language repo with one developer, the seam *is* the product; type-safety inside each half is already strong, so all defect pressure concentrates at the boundary.
**Done when:** GitHub Actions runs backend pytest (with a DB-backed smoke suite hitting every router) + `tsc` + eslint on every PR, and Settings/Exports/seed work end-to-end.

### Theme 2 — Odds → model data lineage is leaky (explains A3, P2, P3)
**Target state:** a model run is always pinned to exactly one snapshot (defaulting to the latest successful one), recorded on the run; raw provider payloads are optional/pruned.
**Principle:** the app's entire value is "fit current market prices"; snapshot scoping is a correctness invariant, not an optimization.
**Done when:** `create_model_run` resolves and stores a concrete `odds_snapshot_id` 100% of the time, and a regression test proves two snapshots don't blend.

### Theme 3 — The optimizer run outgrew a request handler (explains A5/P1)
**Target state:** the run executes off the event loop (thread/process executor) with status polling — the `ModelRun.status` field and frontend invalidation pattern already anticipate this.
**Principle:** never hold an HTTP request hostage to minutes of CPU; the DB schema was designed for async status, so finish the thought.
**Done when:** a 104-match run completes with `/health` responsive throughout and no proxy 504.

### Theme 4 — Two of everything (explains A7, T2, dead-code table, A6)
**Target state:** one model pipeline, one schema-management story, zero modules with no call sites.
**Principle:** dead paths in a solo project aren't harmless — they're future debugging time and false test confidence.
**Done when:** `poisson_model.py` survives only as `MarketProbabilities` (or is folded into `score_model.py`), seed uses the production pipeline, and grep finds no orphan modules.

### Explicitly NOT recommending
- **No background scheduler / job queue (Celery, etc.)** — manual refresh is a stated product decision (README); a thread executor suffices for the optimizer.
- **No HTTPS/secret-management overhaul** — Traefik/Coolify already terminate TLS; plaintext `ADMIN_PASSWORD` in env is acceptable for one user, just harden the comparison and add throttling.
- **No frontend test suite beyond lint + typecheck + one smoke test** — 9 pages, one user; the ROI ceiling is low. Contract enforcement comes from backend integration tests instead.
- **No DB index work or odds-table partitioning now** — data volume is tiny; revisit only if refresh history is kept long-term (P2 pruning reduces the need).
- **No model changes** — the DC + entropy calibration core is the strongest part; leave it alone.

---

## Task Plan

### Milestone 0 — Safety net (do first; ~1 day total)

| # | Task | Files | Acceptance criteria | Effort | Risk | Deps |
|---|---|---|---|---|---|---|
| 0.1 | **CI pipeline**: GitHub Actions — backend `pytest` (Postgres service container), `tsc --noEmit`, frontend build | `.github/workflows/ci.yml` | Red PR on any test/type failure; runs on the repo's existing PR flow | S | None | — |
| 0.2 | **DB-backed API smoke tests**: conftest fixture overriding `get_db` with a test database; one happy-path test per router (matches, pool-configs, odds-overrides, model-runs, exports) | `backend/tests/conftest.py`, new `test_api_smoke.py` | Every registered route returns non-5xx with valid auth; exports round-trip creates a file | M | Low | 0.1 |
| 0.3 | **Frontend ESLint + lint script** (flat config, TS + react-hooks plugins), wire into CI | `frontend/.eslintrc`→`eslint.config.js`, `package.json` | `npm run lint` exists and passes in CI | S | Low | 0.1 |

### Milestone 1 — Critical correctness (the broken stuff)

| # | Task | Files | Acceptance criteria | Effort | Risk | Deps |
|---|---|---|---|---|---|---|
| 1.1 | **Pin model runs to one snapshot** (fix A3): resolve latest successful snapshot when none given; store it on the run; filter events by it | `backend/app/api/model_runs.py:32-96,128-165` | New test: two snapshots in DB → consensus uses only the latest; `ModelRun.odds_snapshot_id` always set | S | Low — query change, behavior is strictly more correct | 0.2 |
| 1.2 | **Fix Exports contract** (A2): add `GET /api/exports` (list) and either `POST /api/exports` dispatching on `format` or change frontend to call `/csv`//`excel` with `{model_run_id, top_n}` | `backend/app/api/exports.py`, `frontend/src/api/exports.ts:11-13`, `DashboardPage.tsx:66-72`, `ExportsPage.tsx` | Export create + list + download work from both Dashboard and Exports page; smoke test covers list/create | M | Low | 0.2 |
| 1.3 | **Settings page** (A1): decide (see Open Questions) — either build `GET/PUT /api/settings` backed by a small `app_settings` table that `refresh_odds` reads, or delete the page and surface env-var values read-only | `backend/app/api/settings.py` (new) or `frontend/src/pages/SettingsPage.tsx`, `SidebarNav.tsx` | No UI element calls a nonexistent endpoint; saved settings actually affect odds refresh (if kept) | M | Medium if persisted settings override env — document precedence | 0.2 |
| 1.4 | **Fix seed script** (A4): drop `hash_password` import and the `users` insert; switch seed to `score_model.fit_score_model` (also closes A7's seed half) | `backend/app/seed.py:13,82,386` | `python -m app.seed` completes on a fresh DB; seeded recommendations match production pipeline | S | Low | — |
| 1.5 | **Login hardening** (S1, S2): `secrets.compare_digest`, naive per-IP attempt delay/lockout, fail-fast at startup when `SESSION_SECRET` unset in production | `backend/app/api/auth.py:21`, `backend/app/core/config.py:15-20` | Wrong-password floods are throttled; prod boot without `SESSION_SECRET` exits with a clear message | S | Low | — |

### Milestone 2 — High-leverage improvements

| # | Task | Files | Acceptance criteria | Effort | Risk | Deps |
|---|---|---|---|---|---|---|
| 2.1 | **Move optimizer run off the event loop** (A5): run fit loop in `anyio.to_thread`/`run_in_executor` (sync DB session inside, or pre-load inputs then fit), return `202` with run id immediately; frontend polls run status (list invalidation already exists) | `backend/app/api/model_runs.py:99-233`, `OptimizerPage.tsx`, `DashboardPage.tsx:53-64` | Full-schedule run: `/health` p99 < 1s during run; UI shows running→completed without 504 | L | Medium — session/threading semantics; gate with test 0.2 | 0.2, 1.1 |
| 2.2 | **Delete dead code** (Theme 4): `services/jobs.py`, `diagnostics.py`, `schedule_service.py`, `User`+`JobRun` models (+ drop-table migration), `apscheduler` dep; retire `tests/test_poisson.py` or repoint to `score_model` | listed files, `pyproject.toml:24`, new migration | Grep finds no orphan modules; tests green; image builds | S | Low | 1.4 |
| 2.3 | **Reproducible builds** (D2): backend `requirements.txt`/`uv.lock` consumed by Dockerfile, split runtime vs dev deps, copy manifest before source for caching; frontend `COPY package*.json` + `npm ci` | `backend/Dockerfile`, `backend/pyproject.toml`, `frontend/Dockerfile:5-6` | Two consecutive image builds produce identical dependency sets; prod image has no pytest | M | Low | 0.1 |
| 2.4 | **README rewrite of setup + model sections** (DOC1): plain `ADMIN_PASSWORD` flow, correct Coolify notes vs actual compose labels, describe DC+entropy model, document the create_all/Alembic convention (A6) | `README.md` | A fresh clone following only the README reaches a working login and seeded data | S | None | 1.4 |
| 2.5 | **Stop persisting full raw odds payloads by default** (P2): store compact metadata (counts, quota headers) or prune `raw_response` older than N snapshots | `backend/app/api/odds.py:73`, optionally a cleanup on refresh | DB growth per refresh is O(normalized rows), not O(raw payload); existing rows pruned | S | Low | — |

### Milestone 3 — Quality & polish

| # | Task | Files | Acceptance | Effort | Risk |
|---|---|---|---|---|---|
| 3.1 | Batch `_build_market_probs` queries (P3) — load all events/overrides for the match set up front | `model_runs.py:32-96` | ≤3 queries regardless of match count | S | Low |
| 3.2 | `has_odds` via `EXISTS` subquery instead of loading collections (P4) | `matches.py:56,231` | Match list does not load odds_events rows | S | Low |
| 3.3 | Replace `datetime.utcnow()` with `datetime.now(timezone.utc)` repo-wide (D3) | ~8 call sites | No naive datetimes written | S | Low |
| 3.4 | Frontend 401 handling: distinguish expired session vs bad password; redirect to login on session expiry | `client.ts:41-43`, `useAuth.ts` | Expired session shows "session expired", not "Invalid password" | S | Low |
| 3.5 | nginx hardening: security headers, `client_max_body_size`, proxy timeouts aligned with 2.1 | `frontend/nginx.conf` | Headers present; uploads >1 MB give a clear error | S | Low |
| 3.6 | Upload size cap + content-type check on schedule import (S4) | `matches.py:266-307` | >5 MB upload rejected with 413-style message | S | Low |

### Quick wins (S effort, do immediately, no dependencies)
- **1.4** fix seed import — unblocks documented onboarding (15 min).
- **1.1** snapshot pinning — one query change kills the worst correctness bug.
- **1.5** `compare_digest` + startup secret check.
- **2.2** delete `jobs.py`/`diagnostics.py`/`schedule_service.py` + `apscheduler`.
- **2.4** README password-setup fix (users are being told to set a variable that doesn't exist).
- Frontend Dockerfile `npm ci` one-liner (part of 2.3).

### Implementation sketches — top 3

**1.1 Snapshot pinning (`model_runs.py`)**
In `create_model_run`, before the match loop: if `body.odds_snapshot_id` is None, `SELECT id FROM odds_snapshots WHERE status='success' ORDER BY fetched_at DESC LIMIT 1`; 404/400 with a clear message if none exists ("Refresh odds first"). Pass the resolved id into `_build_market_probs` unconditionally and set it on the `ModelRun` row (line 128-135). Delete the now-dead `else: order_by` branch (lines 50-52). Gotcha: `OddsEvent.match_id` can be NULL for unmatched events — current `.where(match_id == match.id)` already handles it. Regression test: seed two snapshots with different prices for one match; assert fitted `market_home_win_prob` equals the newer snapshot's consensus.

**1.2 Exports contract**
Smallest-diff option: change the frontend. `exports.ts`: `create` → `api.post(format === 'csv' ? '/exports/csv' : '/exports/excel', { model_run_id, top_n })`; add backend `GET ""` route returning recent `Export` rows (10 lines, mirror `list_snapshots` in `api/odds.py:160-170`). Fix `DashboardPage.tsx:66-72` to pass `model_run_id` (it already has `stats.latest_model_run.id`; disable the button when absent). Gotcha: `ExportRecord` type in `frontend/src/types` must match `ExportOut` — check field names before assuming.

**0.1/0.2 CI + smoke tests**
Workflow: two jobs. Backend: `services: postgres:16-alpine`, `pip install -e ".[dev]"`, `alembic upgrade head`, `pytest`. Frontend: `npm ci`, `tsc --noEmit`, `npm run build`. For 0.2, add a `db_session` fixture creating tables against `TEST_DATABASE_URL` and override `app.dependency_overrides[get_db]`; mint an auth cookie via `create_session_token("admin")` (pattern already exists at `tests/test_api_matches.py:10-13`). Gotcha: `app/core/config.py` reads env at import time — set test env vars in `conftest.py` before importing `app.main`; also the lifespan's `create_all_tables` (`main.py:18-24`) will run against the test DB — harmless, but use a dedicated test database, never the dev one.

---

## Open Questions (need owner decisions)

1. **Settings page (task 1.3):** Was a persisted-settings backend ever intended, or should sport key/regions/bookmakers stay env-only? Build (M effort) vs delete the page (S effort)? This decides the only Medium-risk task in Milestone 1.
2. **Odds history:** Is per-snapshot history (raw payloads + all normalized rows) needed after a model run, or can old snapshots be pruned aggressively? Affects 2.5 and whether P5 indexes ever matter.
3. **Legacy `poisson_model.py`:** Comfortable deleting it outright (keeping only `MarketProbabilities`), or do you want the independent-Poisson model kept as a user-selectable fallback? Affects scope of 2.2.
4. **Hardcoded `pool.joseathie.com`** in `docker-compose.yml:76-88` and as `APP_BASE_URL` default: intentional (this repo serves exactly one deployment) or should it be parameterized for portability?
5. **Performance target for a full run (2.1):** Is "completes in ~5 min in the background with a progress status" acceptable, or do you want per-match incremental persistence so partial results are visible during the run?
6. **Are knockout-stage scoring bases** (90-min vs incl. extra time — flagged in README Known Limitations and `scoring_basis` field on Match, which nothing currently reads — `db/models.py:62`, no consumer found **[F]**) in scope before June 2026? The field exists but is dead today.

---

## Verification of the audit's executable claims (post-approval, if fixes proceed)

- `docker compose up --build` then `docker compose exec backend python -m app.seed` → reproduces A4 ImportError.
- Logged-in browser → Settings page → Save → network tab shows 404 on `PUT /api/settings` (A1); Exports page shows failed `GET /api/exports` (A2).
- Two `POST /api/odds/refresh` calls with changed override prices, then Dashboard "Run Optimizer" → inspect `match_model_fits.market_home_win_prob` blends both (A3).
- `cd backend && pytest tests/ -v` → confirms existing suite is green before any change (baseline).
