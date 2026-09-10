# Arcane

Standalone ETL that builds Alberta medical and dental practice lead lists. Design contract: [`docs/pipeline.md`](docs/pipeline.md). Keep that file in lockstep with the code.

CPSA Medical Directory PDFs are the live source for `alberta-medical-benefits`. Owner is inferred (specialist street address + unique ProfCorp name match), not a college field. Dental ingest is still gated.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

Set `DATABASE_URL` in `.env` for load. This repo’s local Postgres:

```bash
npx supabase start
```

Default URL is `postgresql://postgres:postgres@127.0.0.1:54322/postgres`. Studio: http://127.0.0.1:54323

## Run

Live CPSA extract downloads the six listings from cpsa.ca (rate-limited). Transform can re-parse an existing landing without downloading again:

```bash
python -m pipeline.cli run --segment alberta-medical-benefits --phase extract,transform
python -m pipeline.cli run --segment alberta-medical-benefits --phase transform,load
```

Omit `--run-id` to use the newest directory under `data/raw/alberta-medical-benefits/`. Pass `--run-id` to pin a landing.

`--allow-fixtures` lands the checked-in synthetic slices instead of hitting the network.

Dental is `tos_status: unchecked`. `--allow-fixtures` on `alberta-dental-benefits` is expected to fail until that task.

```bash
pytest
```
