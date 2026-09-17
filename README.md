# Arcane

Standalone ETL that builds Alberta medical and dental practice lead lists. Design contract: [`docs/pipeline.md`](docs/pipeline.md). Keep that file in lockstep with the code.

CPSA Medical Directory PDFs are the live source for `alberta-medical-benefits`. Owner is inferred (specialist street address + unique ProfCorp name match), not a college field. Dental ingest is still gated.

## Setup

Each person runs this on their own machine. Downloaded PDFs (`data/`) and loaded tables are not in git.

You need **Python 3.11+**, **Node** (`npx`), **git**, and **Docker Desktop running**. Local Postgres is Docker via the Supabase CLI, not a hosted supabase.com project.

```bash
git clone git@github.com:jaiohri/Arcane.git
cd Arcane
# check out the branch you are reviewing, then:

python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

`.env.example` already has `DATABASE_URL` for local Postgres. Then:

```bash
npx supabase start
```

The first start pulls Docker images and can take a few minutes. After that:

- Postgres: `postgresql://postgres:postgres@127.0.0.1:54322/postgres`
- Studio (table browser): http://127.0.0.1:54323

Studio is empty until you run **load**. `npx supabase stop` shuts the containers down.

`pytest` does not need Docker. Load does.

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
