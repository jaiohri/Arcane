# Arcane

Standalone ETL that builds Alberta medical and dental practice lead lists. Design contract: [`docs/pipeline.md`](docs/pipeline.md).

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

Set `DATABASE_URL` in `.env` for the load phase (local Postgres, Neon, or Supabase). Extract and transform do not need a database.

## Run

Live registry extract is gated until each source `tos_status` is `allowed`. Until then, use fixtures:

```bash
python -m pipeline.cli run --segment alberta-medical-benefits --phase extract,transform --allow-fixtures
python -m pipeline.cli run --segment alberta-dental-benefits --phase full --allow-fixtures
```

```bash
pytest
```
