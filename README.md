<p align="center">
  <img src="frontend/public/logo-1024.png" alt="World Cup Pool Optimizer" width="220" />
</p>

# World Cup Pool Optimizer

A private web app that recommends score predictions for a 2026 FIFA World Cup pool. Fetches bookmaker odds daily, fits a Poisson model per match using 1X2 and Over/Under markets, and outputs the predicted score(s) that maximize expected pool points under a configurable scoring system.

## Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12, FastAPI, SQLAlchemy 2.x, Alembic, PostgreSQL 16 |
| Math | NumPy, SciPy (L-BFGS-B optimizer), Pandas |
| Export | openpyxl (Excel), csv (CSV) |
| Frontend | React 18, TypeScript, Vite, TanStack Query, TanStack Table, Recharts, Tailwind CSS |
| Deployment | Docker Compose (local + Coolify/VPS) |

## Quick Start (Local)

### 1. Prerequisites

- Docker and Docker Compose v2
- A free API key from [The Odds API](https://the-odds-api.com)

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env`:

```env
ODDS_API_KEY=your_odds_api_key_here
ADMIN_PASSWORD=your-chosen-password
SESSION_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
```

> **Note:** `ADMIN_PASSWORD` is the plain-text password you will type on the login screen.
> `SESSION_SECRET` should be a random hex string — generate one with the command above, or with:
> ```bash
> docker compose exec backend python -c "import secrets; print(secrets.token_hex(32))"
> ```

### 3. Build and start

```bash
docker compose up --build
```

### 4. Run migrations and seed data

```bash
docker compose exec backend alembic upgrade head
docker compose exec backend python -m app.seed
```

### 5. Access the app

- **Frontend:** http://localhost:3000
- **Backend API docs:** http://localhost:8000/docs
- **Health check:** http://localhost:8000/health

Log in with the password you set in step 2.

## Using the App

Once logged in, the typical first-time setup is:

### 1. Import the match schedule

Go to **Matches → Import Schedule**. You have two options:

- **Option A — From The Odds API:** pulls the official fixtures directly from your
  configured odds provider and links each match to its odds event (so odds refreshes
  work automatically afterwards). Requires `ODDS_API_KEY` to be set.
- **Option B — Upload a CSV/JSON file:** upload your own schedule. Click **Download
  template** for a ready-to-fill CSV. Required columns are `stage`, `home_team`,
  `away_team`; teams are created automatically. Re-importing updates existing matches
  (matched by `match_number` or `provider_event_id`) instead of duplicating them.

### 2. Set up scoring rules

Go to **Scoring Rules**. If no pool configuration exists yet, click **Create default
configuration** — it is created pre-loaded with the standard World Cup scoring rules.
Toggle rules on/off, edit point values (changes are queued; click **Save Changes** to
apply), or use **Reset to Defaults** at any time.

**Presets.** Each scoring system is a named *preset*. Instead of overwriting the one
you are editing, use **Save as new preset** to keep the current rules and settings as a
separate copy. Switch between presets with the dropdown, mark one **Set Active** (the
active preset is the one the optimizer uses), or **Delete** ones you no longer need.

**Scoring mode.** A preset can use one of two modes:

- **Standard** — the highest-value applicable rule from the table is awarded per match.
- **Binary** — a prediction earns *result points* for a correct outcome (home win, draw
  or away win) **plus** *total-goals points* for the correct total goals (home + away),
  awarded independently (so 0, 1 or 2 categories per match). Both point values default to
  1 and are editable. The rule table is ignored in binary mode.

### 3. Refresh odds (manual)

Odds are **only ever fetched manually** — there is no background scheduler. Click
**Refresh Odds** on the Dashboard whenever you want fresh prices. If `ODDS_API_KEY`
is missing the app tells you so explicitly instead of failing silently.

### 4. Run the optimizer

Click **Run Optimizer** on the Dashboard to fit each match and generate score
recommendations, then view them on the **Optimizer** page or **Export** them.

## Development (without Docker)

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

# Set env vars (or create backend/.env)
export DATABASE_URL=postgresql+psycopg://worldcup:worldcup@localhost:5432/worldcup
export ADMIN_PASSWORD=admin123
export SESSION_SECRET=dev-secret

alembic upgrade head
python -m app.seed
uvicorn app.main:app --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev    # Vite dev server at http://localhost:5173, proxies /api to :8000
```

### Run backend tests

```bash
cd backend
pytest tests/ -v
```

## Project Structure

```
worldcup-pool-optimizer/
├── backend/
│   ├── app/
│   │   ├── api/          # FastAPI route handlers
│   │   ├── core/         # Config, security, logging
│   │   ├── db/           # SQLAlchemy models + session
│   │   ├── schemas/      # Pydantic v2 request/response schemas
│   │   ├── services/     # Business logic
│   │   │   ├── scoring.py              # Pool scoring engine
│   │   │   ├── poisson_model.py        # Poisson fitting (L-BFGS-B)
│   │   │   ├── optimizer.py            # Expected-points optimizer
│   │   │   ├── odds_normalization.py   # Margin removal + consensus
│   │   │   ├── odds_provider_base.py   # Abstract provider interface
│   │   │   ├── odds_provider_the_odds_api.py
│   │   │   ├── diagnostics.py          # Market vs model diagnostics
│   │   │   ├── export_service.py       # CSV + Excel exports
│   │   │   └── jobs.py                 # Daily refresh scheduler
│   │   ├── main.py
│   │   └── seed.py
│   ├── alembic/          # DB migrations
│   └── tests/
├── frontend/
│   └── src/
│       ├── api/          # Typed API client functions
│       ├── components/   # Reusable UI components
│       ├── hooks/        # useAuth, useToast
│       ├── pages/        # 8 app pages
│       ├── styles/       # Design tokens + global CSS
│       └── types/        # TypeScript interfaces
├── docker-compose.yml
├── .env.example
└── README.md
```

## API Overview

All routes require session authentication except `/health` and `/api/auth/login`.

| Method | Path | Description |
|---|---|---|
| POST | `/api/auth/login` | Login with admin password |
| POST | `/api/auth/logout` | Clear session |
| GET | `/api/auth/me` | Auth status |
| GET | `/health` | Health + DB check |
| GET | `/api/pool-configs` | List pool configurations |
| POST | `/api/pool-configs` | Create a config (seeded with default scoring rules) |
| POST | `/api/pool-configs/{id}/duplicate` | Save a config's rules/settings as a new named preset |
| DELETE | `/api/pool-configs/{id}` | Delete a config and its scoring rules |
| POST | `/api/pool-configs/{id}/activate` | Make a config the active one |
| GET | `/api/pool-configs/{id}/scoring-rules` | List scoring rules (seeds defaults if empty) |
| PATCH | `/api/pool-configs/{id}/scoring-rules/{ruleId}` | Update one rule's points/enabled |
| POST | `/api/pool-configs/{id}/scoring-rules/reset` | Reset rules to defaults |
| PUT | `/api/pool-configs/{id}/scoring-rules` | Bulk upsert scoring rules |
| GET | `/api/matches` | List matches (paginated) with filters |
| POST | `/api/matches/import` | Import schedule from CSV/JSON upload |
| POST | `/api/matches/import-provider-schedule` | Import fixtures from the odds provider |
| GET | `/api/dashboard/stats` | Dashboard summary metrics |
| POST | `/api/odds/refresh` | Trigger manual odds refresh (body optional) |
| GET | `/api/matches/{id}/odds` | Match odds + overrides |
| PUT | `/api/matches/{id}/odds-overrides` | Set raw odds overrides |
| POST | `/api/model-runs` | Run optimizer |
| GET | `/api/model-runs/{id}/recommendations` | Get recommendations |
| GET | `/api/matches/{id}/diagnostics` | Model vs market diagnostics |
| POST | `/api/exports/csv` | Export CSV |
| POST | `/api/exports/excel` | Export Excel workbook |
| GET | `/api/exports/{id}/download` | Download export file |

## Mathematical Model

Each match fits a Dixon-Coles correlated score model:

- **Prior fit:** two independent Poisson parameters `(λ_home, λ_away)` plus a Dixon-Coles correlation parameter `ρ` are fitted to 1X2 market targets via L-BFGS-B
- **Entropy-regularized calibration:** the DC prior matrix is further calibrated against O/U market targets using an entropy-regularized softmax (36 parameters, 6×6 score grid), minimizing KL divergence from the DC prior while matching market totals probabilities
- **1X2 targets:** home win, draw, away win
- **O/U targets:** over/under 1.5, 2.5, 3.5 (when available)
- **Fitting grid:** 6×6 final score matrix (0–5 goals per team)
- **Candidate predictions:** 0–5 goals per team (36 candidates)
- **Expected points:** integrated over the full 6×6 grid

## Scoring Rules (Configurable)

| Code | Default Points | Description |
|---|---:|---|
| `exact_score` | 10 | Both goals match exactly |
| `correct_winner_goal_difference` | 6 | Same winner + same goal difference |
| `correct_winner_winner_goals` | 5 | Same winner + winning team's goals match |
| `correct_winner_any_team_goals` | 4 | Same winner + any team's goals match (winner or loser) |
| `correct_winner_only` | 3 | Same winner but wrong goals for both teams (neither team's goals match) |
| `correct_winner_basic_a` | 3 | Same winner, different goal difference |
| `correct_winner_basic_b` | 3 | Same winner, different winning-team goals |
| `correct_draw` | 4 | Both predict draw, not exact score |
| `wrong_result_team_goal` | 1 | Wrong result but one team's goals match |
| `wrong_result` | 0 | Catch-all |

Rules can be enabled/disabled and point values are editable in the UI.

### Binary scoring mode

As an alternative to the rule table above, a preset can be switched to **binary** mode,
which scores each match in two independent parts:

| Component | Default Points | Awarded when |
|---|---:|---|
| Correct result | 1 | Predicted outcome (home win / draw / away win) matches |
| Correct total goals | 1 | Predicted total goals (home + away) match |

The two components are independent, so a match scores 0, 1 or 2 (with the default point
values). Both point values are configurable per preset.

## Deployment on Coolify / VPS

1. Push this repo to GitHub/GitLab.
2. In Coolify, create a new **Docker Compose** deployment pointing to this repo
   (Docker Compose Location: `/docker-compose.yml`).
3. Set the environment variables from `.env.example` in Coolify's environment tab.
4. **Set the domain on the `frontend` service** (e.g. `https://pool.yourdomain.com`
   under "Domains for frontend"). The `frontend` container serves the SPA *and*
   reverse-proxies `/api` and `/health` to the backend, so the backend does **not**
   need its own public domain.
5. The compose file declares `SERVICE_FQDN_FRONTEND_80` on the `frontend` service.
   This is required: it tells Coolify/Traefik to route the domain to the
   container's internal port `80`. Without an explicit port, Coolify cannot
   reliably auto-detect it from `expose`, and the proxy returns a
   `404 page not found`.
6. Persistent volumes (`postgres_data`, `export_files`) are defined in the compose
   file and managed automatically by Coolify.
7. HTTPS is handled automatically by Coolify's built-in reverse proxy for the
   configured domain.
8. **Redeploy** after setting the domain so the proxy labels are regenerated.
9. **Database migrations run automatically** on every deploy — the backend
   container's entrypoint runs `alembic upgrade head` before starting the
   server, so schema changes ship without any manual step.
10. *(Optional, first deploy only)* To load the demo teams / sample matches and
    odds, run the seed once. Skip this if you import your own data through the UI:
    ```bash
    docker compose exec backend python -m app.seed
    ```

> **Troubleshooting `404 page not found`:** That plaintext response comes from the
> Traefik proxy, not the app — it means no router is forwarding your domain to the
> frontend container. Confirm the domain is set on the **frontend** service and that
> `SERVICE_FQDN_FRONTEND_80` is present, then redeploy.

> **Troubleshooting login `500` errors:** In Coolify, `ADMIN_PASSWORD` must be set
> to the plain-text password you type on the login screen. Make sure the variable is
> named `ADMIN_PASSWORD` (not `ADMIN_PASSWORD_HASH`) and contains your chosen
> password, then redeploy.
>
> **Troubleshooting browser `Not secure` warnings:** If the Cloudflare DNS record is
> **DNS only** (gray cloud), browsers connect directly to the Coolify server, so
> Coolify/Traefik must serve a publicly trusted certificate for
> `pool.joseathie.com`. Confirm ports `80` and `443` are open to the VPS, the
> frontend domain is configured as `https://pool.joseathie.com`, and redeploy so
> Let's Encrypt can issue the certificate. If you enable Cloudflare proxying
> instead (orange cloud), use Cloudflare SSL/TLS **Full (strict)** and keep a valid
> certificate on the origin.

## Known Limitations

- Dixon-Coles model uses a 6×6 score grid; very high-scoring matches (6+ goals per team) fall outside the fitting grid.
- Standard 1X2 odds reflect 90-minute outcomes; knockout scoring basis may differ.
- Optimizes each match independently — does not account for other participants' likely picks.
- Candidate scores capped at 0–5 per team.
- Score tracking and leaderboard are future-phase features (not MVP).
