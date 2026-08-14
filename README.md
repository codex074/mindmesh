# MindMesh

FastAPI web app that wraps market data (OpenBB/yfinance) with a Bring-Your-Own-Key
(BYOK) AI analysis feature, in two modes:

- **Quick** — a single model streams a summary (OpenAI-compatible / OpenAI / DeepSeek / Anthropic / Gemini).
- **Deep** — the [TradingAgents](https://github.com/TauricResearch/TradingAgents)
  multi-agent debate framework runs in a **separate OS subprocess**, returning a
  bull/bear/risk-structured report.

See `docs/PRODUCT_PLAN.md` for the full product plan and `docs/EXECUTION_PLAN.md` for the
TradingAgents merge + VPS-deployment plan this repo implements.

## Local development

Requires Python ≥ 3.11 (TradingAgents needs ≥ 3.10, but the app targets 3.11).

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e . ".[dev]"

# Deep mode needs TradingAgents installed editable from its neighbouring repo:
pip install -e ./TradingAgents

uvicorn app.main:app --reload
```

Open http://localhost:8000. Market data works with no key; AI modes prompt for an
ephemeral key on every request.

## Run tests

```bash
source .venv/bin/activate
pytest
```

## Docker

```bash
cp .env.example .env
docker compose up --build
```

The app listens on `127.0.0.1:8080` on the host — loopback only, so it is never
reachable from the public interface even if the VPS firewall is misconfigured.
Visit `http://localhost:8080` for local testing. In production, Caddy reaches
the container over the Docker network by its service name (`mindmesh_app:8000`,
see `Caddyfile`) — it does not go through the published host port at all, so
that port only exists for local dev convenience and must stay loopback-bound.

TradingAgents is installed inside the image from a **pinned git SHA**
(`pyproject.toml` → `.[deep]`), never copied from disk, so a local key can
never enter the build context.

## VPS / pharmshift co-existence (HARD CONSTRAINT)

The target VPS already runs a service called **pharmshift**. This app must be
installed alongside it without disturbing it:

- Separate directory (not pharmshift's path).
- `compose.yaml` sets `name: mindmesh` explicitly — never the folder-derived default.
- Bind a host port not used by pharmshift (check `ss -tlnp` / `docker ps` first;
  default here is 8080, changeable).
- Append this app's Caddy site block to the existing Caddyfile rather than
  replacing it, and use a separate domain.
- Before the first deploy, SSH in and record an inventory: `docker ps -a`,
  existing Caddyfile/nginx config, and listening ports. Never run a deploy step
  that could stop, remove, or rebuild pharmshift's containers, volumes, or proxy
  config.

## Security notes

- BYOK keys are request-scoped and never stored, logged, or echoed back.
- Deep mode passes the key only through the runner subprocess's minimal env
  (never argv/stdin), keyed to the provider's own env var.
- Custom base URLs (OpenAI-compatible) are SSRF-guarded (`app/security/outbound_url.py`).