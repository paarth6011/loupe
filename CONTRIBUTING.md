# Contributing

Thanks for your interest in improving this project! It's MIT-licensed and
contributions are welcome.

## Development setup

Everything runs locally via Docker Compose — no cloud account needed.

```bash
cp .env.example .env
docker compose up --build      # db + redis + backend + frontend (empty instance)
# add canned demo data with the optional prober: docker compose --profile demo up -d
```

Open http://localhost:5173 (login `admin` / `admin`) and the API docs at
http://localhost:8000/docs.

## Running tests

```bash
# Backend (pytest, uses in-memory SQLite — no services required)
docker compose exec backend python -m pytest -q
# or locally:
cd backend && pip install -r requirements.txt && python -m pytest -q

# Frontend (Vitest + a production typecheck/build)
cd frontend && npm ci && npm test && npm run build
```

CI runs the same checks on every pull request — please make sure they pass.

## Linting & formatting

```bash
# Backend (ruff)
cd backend && ruff check app tests && ruff format app tests
# Frontend (prettier)
cd frontend && npm run format
```

CI fails on lint or formatting issues (`ruff check`, `ruff format --check`,
`npm run format:check`), so run these before pushing.

## Conventions

- **Backend:** Python 3.12, type hints throughout; pydantic schemas kept separate
  from ORM models; one router module per resource; config via env vars
  (pydantic-settings). Schema changes go through Alembic migrations — never
  auto-create tables.
- **Frontend:** typed API client in `src/api`; components are presentational and
  pages own data fetching.
- **Each backend feature** lands with pytest coverage (happy path + one failure).
- **Commits:** Conventional Commits (`feat:`, `fix:`, `docs:`, `test:`, …).

## Pull requests

1. Branch from `main`.
2. Keep changes focused; update docs/tests alongside code.
3. Ensure tests pass locally and describe what you changed and why.

See [ROADMAP.md](ROADMAP.md) for where the project is headed and good first areas
to help with.
