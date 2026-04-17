# AI Investment Backend

Backend foundation for an AI-powered investment app that ingests multi-source market data, stores normalized records locally, calculates risk metrics, runs forecast and simulation workflows, and maintains separate immutable and learnable knowledge bases.

Important deployment note:

- GitHub is the right place to store and version the code.
- GitHub is not the runtime for this Python backend.
- To make the backend available when your Mac is off, deploy this repo from GitHub to a cloud host and point the iPhone app to that public API URL.
- This repository now includes a Docker image, a `fly.toml`, and a GitHub Actions workflow for Fly.io so the backend can run continuously outside your local network.

## What This Includes

- Multi-source ingestion modules for:
  - Alpha Vantage daily and intraday equity prices
  - Financial Modeling Prep daily and intraday equity prices
  - FRED macroeconomic indicators
  - FMP and EODHD commodity history
  - Polymarket Gamma prediction-market odds
- Raw payload archiving under `data/raw/`
- Normalized SQLite persistence under `db/`
- Risk engine in `analytics/risk.py`
- Forecasting wrappers for ARIMA/SARIMA, GARCH, and Prophet
- Portfolio simulations and forecast-vs-actual tracking
- Separate `truth.db` and `working.db` knowledge bases with version history
- APScheduler entrypoint for recurring ETL, audit, and simulation jobs
- Local JSON API for the native iOS client
- Native SwiftUI iPhone app under `ui/ios/`
- Unit tests for risk, database initialization, and forecasting utilities

## Environment Variables

Set API keys in your shell or `.env` loading flow before running scripts:

```bash
export ALPHAVANTAGE_API_KEY="your_alpha_vantage_key"
export FMP_API_KEY="your_fmp_key"
export EODHD_API_KEY="your_eodhd_key"
export FRED_API_KEY="your_fred_key"
export OPENAI_API_KEY="your_openai_key"
export OPENAI_MODEL="gpt-5-mini"
export GEOPOLITICAL_RISK_FRED_SERIES_ID="optional_fred_series_id"
export GEOPOLITICAL_RISK_SERIES_NAME="Geopolitical Risk Index"
export APP_STORAGE_ROOT="/data"
export PORT="8080"
export RUN_SCHEDULER="true"
```

An example file is provided at [config/env.example](/Users/daniellobo/Documents/Playground/ai_investment_backend/config/env.example).

No API keys are hard-coded anywhere in the codebase.

Optional geopolitical configuration notes:

- `GEOPOLITICAL_RISK_FRED_SERIES_ID` lets you ingest a dedicated geopolitical-risk series through FRED in addition to Polymarket odds.
- `GEOPOLITICAL_RISK_SERIES_NAME` controls how that series is labeled in the local database and API responses.
- `OPENAI_API_KEY` enables model-backed chat responses in the assistant while still keeping all market data access routed through backend functions.
- `OPENAI_MODEL` selects the OpenAI model used by the chat layer.
- `APP_STORAGE_ROOT` lets cloud deployments store databases, raw payloads, and logs on a mounted persistent volume instead of inside the app source directory.
- `PORT` is used by hosted platforms that inject a runtime port.
- `RUN_SCHEDULER` controls whether the API container also starts the recurring APScheduler jobs.

## Install

Core runtime:

```bash
cd /Users/daniellobo/Documents/Playground/ai_investment_backend
python3 -m pip install -r requirements.txt
```

Notes:

- `requests` is required for ingestion.
- `APScheduler` is required for `scripts/run_scheduler.py`.
- `statsmodels`, `arch`, `pandas`, and `prophet` are only needed when you actually run those forecasting models.
- The code uses lazy imports for optional forecasting libraries, so the rest of the backend can still run if those packages are not installed yet.

## Initialize Databases

Create the primary market database plus the immutable and working knowledge bases:

```bash
python3 scripts/init_db.py
```

This creates:

- `db/market_data.sqlite3`
- `db/truth.db`
- `db/working.db`

## Run Ingestion

Run the full ETL pipeline:

```bash
python3 scripts/run_ingestion.py
```

Run with intraday prices:

```bash
python3 scripts/run_ingestion.py --include-intraday
```

Limit to specific symbols:

```bash
python3 scripts/run_ingestion.py --stocks AAPL MSFT SPY --commodities GCUSD CLUSD
```

Skip Polymarket:

```bash
python3 scripts/run_ingestion.py --skip-polymarket
```

Behavior notes:

- Raw JSON payloads are saved under `data/raw/<provider>/YYYY/MM/DD/`.
- Alpha Vantage requests are spaced to respect roughly 5 calls per minute.
- FMP calls are tracked with a persistent daily limiter aimed at the Basic-tier quota.
- Missing keys cause provider-specific ingestion to be skipped and logged rather than hard-crashing the whole batch.
- Missing or holiday data is tolerated; the pipeline writes whatever valid observations were returned.

## Run Daily Risk Calculations

```bash
python3 scripts/run_risk.py --lookback 252
```

This recalculates risk metrics from stored prices and writes snapshots into `risk_metrics_history`.

Implemented risk metrics:

- Volatility
- Covariance
- Correlation
- Sharpe ratio
- Sortino ratio
- Beta
- Parametric VaR
- Historical VaR
- Monte Carlo VaR
- CVaR / Expected Shortfall
- Maximum drawdown

Formulas embedded in the code and `truth.db` include:

- `Sharpe = (mu - R_f) / sigma`
- `Sortino = (mu - R_f) / downside_deviation`
- `Beta = Cov(R_i, R_m) / Var(R_m)`
- `VaR_alpha = -(mu + z_alpha * sigma)`
- `MDD = min((price - cummax(price)) / cummax(price))`

## Run Forecast Simulations

Example:

```bash
python3 scripts/run_forecasts.py \
  --name "Tech Basket" \
  --positions AAPL:0.5 MSFT:0.5 \
  --start-date 2024-01-01 \
  --end-date 2026-04-14 \
  --initial-capital 10000 \
  --model arima \
  --horizon 1 \
  --horizon-unit daily
```

This:

- loads stored historical prices
- backtests the selected model against the holdout horizon
- stores forecasts in `forecasts`
- stores simulation summaries in `simulations`
- writes portfolio-level evaluation rows in `simulation_results`
- updates `working.db` with the observed prediction outcomes

## Run The Local API For iOS

Start the lightweight JSON API that powers the SwiftUI app:

```bash
python3 scripts/run_local_api.py --host 127.0.0.1 --port 8000
```

## Deploy For Real iPhone Use

If you want the app to work when your Mac is asleep or off-network, deploy the backend from GitHub to a cloud host.

This repo is now prepared for that workflow with:

- `Dockerfile`
- `fly.toml`
- `.github/workflows/deploy-fly.yml`
- `scripts/run_cloud_service.py`

### Recommended Setup

Use:

- GitHub for source control, secrets management, and deployment automation
- Fly.io for the always-on backend runtime
- A persistent Fly volume mounted at `/data` for SQLite, raw payloads, and logs

This works well with the current codebase because the backend still uses local SQLite files and APScheduler.

### No-Fly Alternative: Render

If you do not want to use Fly.io, the cleanest alternative for this repository is Render.

Why Render fits this codebase well:

- it can deploy directly from your linked GitHub repository
- it supports Docker-based services, which matches this repo's `Dockerfile`
- it supports persistent disks for stateful services
- it does not require a Fly API token

This repository now includes [render.yaml](/Users/daniellobo/Documents/Playground/GreenVest/render.yaml) so you can create a Render Blueprint from GitHub.

#### Render Setup Steps

1. Sign in to Render and connect your GitHub account to the `DanielTNL/GreenVest` repository.
2. Create a new Blueprint or Web Service from this repository.
3. Use the root `render.yaml` file.
4. In the Render dashboard, set the secret environment variables:
   - `ALPHAVANTAGE_API_KEY`
   - `FMP_API_KEY`
   - `EODHD_API_KEY`
   - `FRED_API_KEY`
   - `OPENAI_API_KEY`
   - optionally `OPENAI_MODEL`
   - optionally `GEOPOLITICAL_RISK_FRED_SERIES_ID`
   - optionally `GEOPOLITICAL_RISK_SERIES_NAME`
5. Keep the persistent disk mounted at `/data`.
6. After Render gives you a public URL such as `https://<your-service>.onrender.com`, update:
   - [ui/ios/backend-config.json](/Users/daniellobo/Documents/Playground/GreenVest/ui/ios/backend-config.json)
   Set `public_api_base_url` to:
   - `https://<your-service>.onrender.com/api`
7. Reopen the iPhone app or tap `Sync Backend From GitHub` in Settings.

At that point, the app will stop relying on your Mac and will use the public Render backend instead.

### First-Time Cloud Deploy Steps

1. Push `/Users/daniellobo/Documents/Playground/ai_investment_backend` to a GitHub repository.
2. Create a Fly.io app and change `app = "greenvest-api-replace-me"` in [fly.toml](/Users/daniellobo/Documents/Playground/ai_investment_backend/fly.toml) to your real Fly app name.
3. Create a persistent Fly volume named `greenvest_data` mounted at `/data`.
4. In the GitHub repository, add these Actions secrets:
   - `FLY_API_TOKEN`
   - `ALPHAVANTAGE_API_KEY`
   - `FMP_API_KEY`
   - `EODHD_API_KEY`
   - `FRED_API_KEY`
   - `OPENAI_API_KEY`
   - optionally `OPENAI_MODEL`
   - optionally `GEOPOLITICAL_RISK_FRED_SERIES_ID`
   - optionally `GEOPOLITICAL_RISK_SERIES_NAME`
5. In the GitHub repository, add this Actions variable:
   - `FLY_APP_NAME`
6. Push to `main` or run the `Deploy Backend` workflow manually.
   The workflow now syncs the GitHub secrets into Fly.io and then deploys the backend.
7. In the iPhone app, set the Cloud Backend URL to:
   - `https://<your-fly-app-name>.fly.dev/api`

### GitHub Role Versus Runtime Role

Use GitHub as the control plane:

- store code
- store deployment workflow
- store provider secrets in GitHub Actions
- audit changes through commits and pull requests

Use Fly.io as the runtime plane:

- run the Python API
- run the scheduler
- persist market data, simulation history, and working model state

This is the cleanest architecture for the current app. GitHub is excellent for code, secrets, and automation, but it should not be used as the live operational database for forecasts and simulations.

### Why GitHub Alone Is Not Enough

GitHub stores code and can run CI/CD workflows, but it is not a persistent backend host for this app.
GitHub-hosted Actions jobs have a maximum execution time of 6 hours, so they cannot serve as your always-on API and scheduler runtime.
That runtime must live on a real host such as Fly.io, Render, Railway, or another always-on service.

### Important Caveat

The current production path keeps SQLite as the live database on a persistent disk.
That is acceptable for a single-machine MVP, but the long-term production-grade upgrade is:

- move market data and knowledge-base storage to Postgres
- split scheduler and API into separate deployable services
- add proper auth and observability

Primary routes include:

- `/api/stocks`
- `/api/stocks/<symbol>`
- `/api/baskets`
- `/api/simulation-options`
- `/api/simulations/run`
- `/api/metrics`
- `/api/macro`
- `/api/alerts`
- `/api/diagnostics`
- `/api/chat`

## Run Diagnostics

Before attempting a full ingest or iOS run, check backend readiness:

```bash
python3 scripts/run_diagnostics.py
```

This reports:

- provider API key presence
- installed optional dependencies
- risk-engine and forecast-model readiness
- database and working-version status
- geopolitical-data configuration and ingestion state

## Knowledge Bases

### `truth.db`

Immutable, authoritative definitions:

- risk metric formulas
- econometric model descriptions
- assumptions and explanatory metadata

This database is seeded once and should not be overwritten by model-learning routines.

### `working.db`

Learnable, versioned state:

- active daily, weekly, and monthly working versions
- prediction outcomes
- aggregated model-error rollups
- learned parameter summaries
- merged higher-level insights from daily to weekly and monthly views

The update flow is:

1. Forecast or simulation completes.
2. Predicted vs actual values are recorded.
3. A new working version is created for that cadence.
4. Summary statistics are written instead of blindly overwriting prior state.
5. Lower-frequency rollups are derived from recent lower-level outcomes.

## Scheduling

Start the APScheduler loop:

```bash
python3 scripts/run_scheduler.py
```

Configured jobs:

- Intraday ETL every 15 minutes on weekdays
- Daily ETL shortly after midnight
- Daily audit and risk calculations
- Daily forecast simulations for configured baskets
- Weekly forecast simulations on Mondays
- Monthly forecast simulations on day 1

Scheduled simulations use saved baskets from `baskets` and `basket_constituents`. If no baskets exist yet, the scheduler logs a skip instead of failing.

## Project Structure

```text
ai_investment_backend/
  data/
    raw/
    processed/
  db/
    market_data.sqlite3
    truth.db
    working.db
    connection.py
    knowledge.py
    repositories.py
    schema.py
  analytics/
    risk.py
    forecasting.py
    backtesting.py
  forecasting/
    arima.py
    garch.py
    prophet_model.py
  simulations/
    simulator.py
  assistant/
    function_router.py
    nlu_parser.py
    chat.py
  api/
    service.py
    server.py
  audits/
    daily_audit.py
  config/
    settings.py
    env.example
  scripts/
    init_db.py
    run_ingestion.py
    run_risk.py
    run_forecasts.py
    run_scheduler.py
  tests/
    test_risk.py
    test_database.py
    test_forecasting.py
  ui/
    ios/
```

## Testing

Run the unit tests:

```bash
python3 -m unittest discover -s tests
```

### iOS App

The native SwiftUI client lives in [ui/ios](/Users/daniellobo/Documents/Playground/ai_investment_backend/ui/ios) and targets iOS 17 on iPhone 15 or later.

Generate the Xcode project with XcodeGen:

```bash
cd /Users/daniellobo/Documents/Playground/ai_investment_backend/ui/ios
xcodegen generate
```

Run the backend API first:

```bash
cd /Users/daniellobo/Documents/Playground/ai_investment_backend
python3 scripts/run_local_api.py
```

Then build the iOS app:

```bash
cd /Users/daniellobo/Documents/Playground/ai_investment_backend/ui/ios
xcodegen generate
xcodebuild \
  -project GreenVest.xcodeproj \
  -scheme GreenVest \
  -destination 'platform=iOS Simulator,name=iPhone 15' \
  build
```

Simulator default backend URL:

- `http://127.0.0.1:8000/api`

For a physical iPhone on the same network, update the app’s backend URL in Settings to your Mac’s LAN IP, for example:

- `http://192.168.1.20:8000/api`

The iOS app stores API key entries in the Keychain, but the current backend still expects provider keys through environment variables:

- `ALPHAVANTAGE_API_KEY`
- `FMP_API_KEY`
- `EODHD_API_KEY`
- `FRED_API_KEY`

iOS tests:

```bash
cd /Users/daniellobo/Documents/Playground/ai_investment_backend/ui/ios
xcodegen generate
xcodebuild \
  test \
  -project GreenVest.xcodeproj \
  -scheme GreenVest \
  -destination 'platform=iOS Simulator,name=iPhone 15'
```

## Important Implementation Notes

- All timestamps are normalized to UTC before persistence.
- Raw and normalized layers are kept separate for reproducibility.
- SQLite WAL mode is enabled for safer local write concurrency.
- The schema intentionally extends the architecture sketch where needed, especially to support intraday timestamps and forecast/simulation provenance.
- Forecasting model wrappers use lazy imports so the backend remains usable even when optional model packages are not yet installed.

## Next Likely Extensions

- richer basket CRUD and benchmark management
- more explicit exogenous feature alignment in forecasting pipelines
- model-parameter persistence straight from fitted model objects
- a Streamlit UI layered onto this backend
- Docker and CI setup
