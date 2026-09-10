# Leads prospecting pipeline

Standalone ETL that builds sector-specific lead lists for a wealth and retirement advisory use case. The first live segment is Alberta medical and dental practice owners, for outreach about group RRSPs and group health and dental plans.

This document is the design contract. Implementation should follow it; deviations belong here first.

---

## 1. Purpose

Produce a Postgres-backed list of **practice organizations** and **decision-maker contacts** that an advisor can filter, sort, and export.

The pipeline does three things:

1. Extract licensed practitioners and their practice locations from provincial college registries.
2. Normalize those records into a stable schema and score how well each practice fits the group-benefits / group-RRSP pitch.
3. Load scored rows into Postgres, tagged by the named segment that produced them.

It does **not** send email, enrich contacts, or live inside HeadStart. Presentation for the pilot is a BI tool on Postgres.

---

## 2. Scope

### In scope (current build)

- Named segments: `alberta-medical-benefits`, `alberta-dental-benefits`
- Sources: CPSA physician directory; CDSA / Alberta Dental Association dentist directories
- Target: practice owners and equivalent decision makers, roughly 5–50 employees
- Titles to isolate when present: Owner, Practice Owner, Founder, Managing Partner, combined with Physician, MD, Dentist, DDS, DMD
- Industries: Medical Practices, Dentists, Hospital and Health Care
- Fit scoring from signals that actually exist in the landed data
- Postgres tables for organizations, contacts, and segment membership
- Local or GitHub Actions extraction against a free-tier managed Postgres

### Explicitly out of scope until unblocked

| Item | Why it is parked |
| --- | --- |
| Apollo.io API (batch or on-demand) | API ToS: internal use only; no embedding into a distributed product without a Data Reseller Partner agreement |
| Contact enrichment (email, phone, verification) | Same Apollo blocker; enrichment is a write-path action, not part of batch ETL |
| Scraping any registry | Each registry's terms of use must be checked before automated or bulk querying |
| Other verticals without a clean registry (succession, exec equity, job-changers) | No equivalent public source; Apollo would be the likely path and is blocked |
| Adjacent regulated practices (chiro, physio, optometry, vet) | Same profile, later segments, not the first extract |
| Custom advisor app / HeadStart embedding | Metabase or Retool is the placeholder |
| Production AWS (Fargate, RDS, Secrets Manager) | After the scoping pipeline is producing usable lists |

### Open compliance (not resolved by this design)

- Registry terms of use, per source
- CASL consent basis for any later outreach
- Advisor life/health licensing, and investment registration if group RRSP advice is in scope

The pipeline may land **prospect lists**. It does not authorize outreach.

---

## 3. Design principles

1. **One job per named segment.** `alberta-medical-benefits` and `alberta-dental-benefits` are independently runnable. A failed dental run must not block medical.
2. **Raw first.** Extract writes source payloads as-is. Transform never requires a re-hit of the source to change scoring or schema mapping.
3. **Scoring is real.** Transform computes a fit score from available signals. It is not a pass-through cleanup step.
4. **Enrichment is not ETL.** Opening a lead in a dashboard may later trigger a write. That path is separate, gated, and unused until Apollo reseller authorization exists.
5. **Two filter layers.** Extraction decides what exists. Presentation decides what is shown. Do not conflate them.
6. **Canadian data stays in Canada** for production. Prefer `ca-central-1`.
7. **No secrets in the job image or repo.** Even the scoping run reads database URLs from environment or Actions secrets.

---

## 4. Architecture

```
                    ┌─────────────────────────────────────┐
                    │  segment config (YAML)             │
                    │  e.g. alberta-medical-benefits       │
                    └─────────────────┬───────────────────┘
                                      │
                                      ▼
                    ┌─────────────────────────────────────┐
   legal gate ───►  │  EXTRACT  (one job per segment)     │
                    │  registry adapter, rate-limited    │
                    └─────────────────┬───────────────────┘
                                      │ as-is payloads
                                      ▼
                    ┌─────────────────────────────────────┐
                    │  RAW LANDING                         │
                    │  data/raw/{segment}/{run_id}/       │
                    └─────────────────┬───────────────────┘
                                      │
                                      ▼
                    ┌─────────────────────────────────────┐
                    │  TRANSFORM                           │
                    │  identity, normalize, fit score    │
                    └─────────────────┬───────────────────┘
                                      │
                                      ▼
                    ┌─────────────────────────────────────┐
                    │  LOAD                                │
                    │  upsert practitioners, orgs,         │
                    │  contacts, memberships               │
                    └─────────────────┬───────────────────┘
                                      │
                                      ▼
                    ┌─────────────────────────────────────┐
                    │  POSTGRES                            │
                    │  practitioners, organizations,      │
                    │  contacts, segments,                │
                    │  segment_members, runs              │
                    └─────────────────┬───────────────────┘
                                      │ read only
                                      ▼
                    ┌─────────────────────────────────────┐
                    │  PRESENTATION                         │
                    │  Metabase / Retool                   │
                    └─────────────────┬───────────────────┘
                                      │ later, gated
                                      ▼
                    ┌─────────────────────────────────────┐
                    │  ENRICHMENT (on demand, not ETL)    │
                    │  blocked until Apollo reseller       │
                    └─────────────────────────────────────┘
```

Filtering:

| Layer | When | What it decides | How you change it |
| --- | --- | --- | --- |
| Backend / extract | Job run | Which named segments exist in Postgres at all | Edit segment config, re-run that job |
| Frontend / presentation | Query time | Score threshold, city, sector, title | SQL / BI filter; no re-extract |

---

## 5. Named segments

A **segment** is a versioned search definition, not a SQL view. It is the unit of extraction.

| `segment_id` | Province | Profession | Source adapter | Pitch |
| --- | --- | --- | --- | --- |
| `alberta-medical-benefits` | AB | Physician / MD | `cpsa` | Group RRSP + group health/dental |
| `alberta-dental-benefits` | AB | Dentist / DDS / DMD | `cdsa` (and ADA find-a-dentist if needed) | Same |

Later candidates (config only, do not extract until scoped):

- `alberta-chiro-benefits`, `alberta-physio-benefits`, `alberta-optometry-benefits`, `alberta-vet-benefits`
- Other provinces: one segment per province × profession, because every college is a different HTML tool and ToS.

### Config shape

Stored as YAML under `pipeline/configs/segments/`. One file per segment.

```yaml
segment_id: alberta-medical-benefits
display_name: Alberta medical practice owners (group benefits)
province: AB
country: CA
profession: physician
industries:
  - Medical Practices
  - Hospital and Health Care
source:
  adapter: cpsa
  tos_status: unchecked   # unchecked | allowed | prohibited
  tos_notes: ""
target:
  headcount_min: 5
  headcount_max: 50
  decision_maker_titles:
    - Owner
    - Practice Owner
    - Founder
    - Managing Partner
  credential_tokens:
    - Physician
    - MD
extract:
  enabled: false           # stay false until tos_status is allowed
  rate_limit_rps: 0.2
score:
  version: 1
```

`tos_status: allowed` and `extract.enabled: true` are both required for a live extract. The runner must refuse to hit the network otherwise. Transform and load may still run against already-landed raw files.

---

## 6. Data sources

### 6.1 Primary: provincial college registries

| Adapter | Registry | What it gives | What it does not give |
| --- | --- | --- | --- |
| `cpsa` | CPSA Medical Directory PDFs (six listings, updated daily) | Licensed physician name, city, often specialty / status; address on some listings; professional corporation names | Headcount, revenue, owner tenure, founded year; registration number is often absent from the PDFs; email |
| `cdsa` | CDSA Dentist Directory / Alberta Dental Association Find a Dentist | Licensed dentist name, practice location | Same gaps; no bulk PDF. Fixture-mode is empty until a later task |

CPSA does not offer an API or bulk database export. The live adapter downloads text-based PDFs with `pdfplumber` (no OCR) from predictable URLs under `https://cpsa.ca/MedicalDirectory/`:

| `listing_type` | File | Grain | Default `licence_status` |
| --- | --- | --- | --- |
| `alphabetical` | `Alphabetical Listing.pdf` | Person (name, city, phone, specialty) | `active` |
| `specialists` | `Specialty Listing.pdf` | Person (name, address, city, postal, specialty section) | `active` |
| `non_specialists` | `Non Specialty Listing.pdf` | Person at an address when present | `active` |
| `retired` | `Retired Listing.pdf` | Person | `retired` |
| `obituaries` | `Obituaries Listing.pdf` | Person | `deceased` |
| `professional_corporations` | `ProfCorp Listing.pdf` | Organization (corporation legal name only) | n/a |

A symbols-and-abbreviations key is parsed once and hardcoded in the repo. It is not re-fetched on each run.

Phone numbers that appear in the PDFs stay in the raw text landing. They are **not** copied onto `contacts.phone`.

Properties of these sources:

- Public, free; CPSA listings page states they are updated daily
- CPSA bulk path is PDFs, not the HTML Physician Directory search UI
- Identity gold field: **license / registration number** when present; otherwise `(listing_type, normalized name, city)` for people and normalized corporation name for ProfCorp
- CDSA still has no equivalent bulk file; do not scrape its search tool in this build
- Every province (and most other regulated professions) has an analogue. Check that before assuming Apollo is required for a new vertical

**Legal gate:** treat each registry as a separate ToS review. Do not hit the network against a source whose `tos_status` is `unchecked` or `prohibited`.

Until that review is done, extract has two allowed modes:

1. **Fixture mode** — load checked-in sample files under `pipeline/fixtures/` so transform, scoring, and load can be built and tested.
2. **Manual drop mode** — an operator places exported files into `data/raw/{segment}/{run_id}/` and the job starts at transform.

### 6.2 Secondary: Apollo.io (blocked)

Would supply headcount, firmographics, verified contact points, job-change and funding signals.

Do not:

- Call the Apollo API
- Store Apollo API keys in this repo or its Actions
- Design transform as if Apollo fields are required for a valid score

When (if) a reseller agreement exists, enrichment is a separate module. It writes onto existing `contacts` / `organizations` rows. It does not become a new extract adapter for the medical/dental scope.

---

## 7. Entity model

College rows are **people at places**, except CPSA Professional Corporations, which are legal entities. The buyer for group benefits is the **practice**, not the individual license.

| Entity | Grain | Example |
| --- | --- | --- |
| Practitioner | One person as they appear in one CPSA listing (staging) | "Hilary Aadland" from `alphabetical` |
| Organization | A practice location, or a CPSA professional corporation | "A. Ahmed Professional Corporation" |
| Contact | A licensed practitioner | "Hilary Aadland, MD" |
| Segment member | Contact at an organization, produced by a named segment | Only when a real practice org exists |

CPSA promotion rules (do not fuzzy-match ProfCorp names to people in this version):

| Listing | `practitioners` | `contacts` | `organizations` | `segment_members` |
| --- | --- | --- | --- | --- |
| Alphabetical / Specialists | yes, status `active` | yes | no (city is not a practice) | no |
| Non-Specialists | yes | yes | yes only if a practice/address is present | only with that org |
| Retired / Obituaries | yes, status `retired` / `deceased` | yes | no | no |
| ProfCorp | no person row | no | yes, corp name as org | no |

### Identity

**Practitioner key** (in order):

1. Registration / license number, if the listing provides one
2. `(listing_type, normalized full_name, city)`

**Organization key** (in order):

1. Source-provided clinic / facility id, if any
2. Normalized `(practice_name, address_line, city, province, postal_code)`

**Contact key** (in order):

1. `(college, license_number)` — stable across runs
2. Normalized `(full_name, college, organization_key)` when an org exists
3. Normalized `(full_name, college, city)` when the person has no practice org

Unique practitioners are `(source, listing_type, practitioner_key)`, so the same physician may appear once per listing. Re-runs upsert; they must not duplicate because of PDF row order.

A practitioner at two clinics becomes **one contact, two memberships** (or two org links). Do not duplicate the person. A clinic with several dentists is **one organization, many contacts**. Prefer ranking the owner / managing partner as the primary contact for the list; keep other practitioners as secondary members so the org is not lost if title is missing.

Hospital departments: keep them as organizations, but score them down. The owner is rarely the personal buyer above ~50 staff, and a hospital is the wrong buyer for this pitch.

### Registry-only limitation (accepted)

CPSA/CDSA will usually **not** give title = Owner, headcount, or founded year. The pipeline must still produce a useful list:

- Default title to the credential (`Physician`, `Dentist`) when the source has no owner flag
- Use **co-located licensee count** at the same organization key as a headcount proxy
- Do not invent emails or phones; leave them null until enrichment exists. CPSA PDF phone columns stay in raw text only.

Presentation can still filter on city, specialty, and score. Backend extract does not pretend to know employee_count.

---

## 8. Postgres schema

Relational on purpose: the pilot need is tabular filter/sort/export, not document flexibility.

### 8.1 `practitioners`

CPSA landing / staging grain. One row per person × listing. ProfCorp does not write here.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid pk | Internal |
| `practitioner_key` | text | Deterministic identity within a listing |
| `source` | text | `cpsa` |
| `listing_type` | text | One of the six PDF ids |
| `full_name` | text | |
| `profession` | text | `physician` for all CPSA rows |
| `licence_status` | text | `active` \| `retired` \| `deceased` \| listing codes |
| `practice_name` | text null | When the listing provides one |
| `practice_address` | text null | Unstructured address when present |
| `source_reference` | text null | Registration number if present |
| `collection_method` | text | `bulk_pdf` |
| `collected_at` | timestamptz | Producing run |
| `created_at` / `updated_at` | timestamptz | |

Unique `(source, listing_type, practitioner_key)`.

### 8.2 `organizations`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid pk | Internal |
| `org_key` | text unique | Deterministic identity key |
| `name` | text | Practice name |
| `industry` | text | Medical Practices / Dentists / Hospital and Health Care |
| `sector` | text | `medical` \| `dental` |
| `address_line1` | text | |
| `city` | text | Presentation filter |
| `province` | text | `AB` |
| `postal_code` | text | |
| `country` | text | `CA` |
| `employee_count_estimate` | int null | Null until a lawful source exists; may be filled by licensee-count proxy in a separate column |
| `licensee_count` | int null | Count of distinct practitioners resolved to this org in the current transform |
| `practice_type` | text null | `solo` \| `group` \| `hospital` \| `unknown` |
| `founded_year` | int null | Null from registries |
| `source_system` | text | `cpsa` \| `cdsa` |
| `source_org_id` | text null | If the registry exposes one |
| `created_at` / `updated_at` | timestamptz | |

### 8.3 `contacts`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid pk | |
| `contact_key` | text unique | Deterministic identity key |
| `organization_id` | uuid fk null | Primary / current practice for display when one exists; null for people-only listings |
| `first_name` | text | |
| `last_name` | text | |
| `full_name` | text | |
| `title` | text null | Owner / Managing Partner if known; else credential |
| `credentials` | text null | MD, DDS, DMD |
| `specialty` | text null | If the registry provides it |
| `license_number` | text null | |
| `license_college` | text | `CPSA` \| `CDSA` |
| `email` | text null | Always null in v1 |
| `phone` | text null | Always null in v1 |
| `enriched_at` | timestamptz null | |
| `enrichment_status` | text | `none` \| `blocked` \| `ok` \| `failed` — v1 is `blocked` |
| `created_at` / `updated_at` | timestamptz | |

Email and phone stay null by design until enrichment is authorized.

### 8.4 `segments`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | text pk | Matches `segment_id` in YAML |
| `display_name` | text | |
| `province` | text | |
| `profession` | text | |
| `config_hash` | text | Hash of the YAML used for the last successful load |
| `created_at` / `updated_at` | timestamptz | |

### 8.5 `segment_members`

The list the advisor actually uses. One row per contact × organization × segment.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid pk | |
| `segment_id` | text fk | |
| `organization_id` | uuid fk | |
| `contact_id` | uuid fk | |
| `is_primary_contact` | bool | Best guess at decision maker |
| `fit_score` | numeric | 0–100 |
| `score_version` | int | Matches `score.version` in config |
| `score_breakdown` | jsonb | Per-signal contributions, for debug and later UI |
| `run_id` | uuid fk | Producing run |
| `first_seen_at` | timestamptz | |
| `last_seen_at` | timestamptz | |

Unique `(segment_id, organization_id, contact_id)`.

### 8.6 `etl_runs`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid pk | Also the raw landing `run_id` |
| `segment_id` | text | |
| `phase` | text | `extract` \| `transform` \| `load` \| `full` |
| `status` | text | `started` \| `succeeded` \| `failed` \| `skipped_legal_gate` |
| `started_at` / `finished_at` | timestamptz | |
| `row_counts` | jsonb | `{raw, practitioners, orgs, contacts, members}` |
| `git_sha` | text null | |
| `error` | text null | |

### 8.7 What is not a table in v1

- No `enrichment_jobs` queue until Apollo is authorized
- No outreach / CASL consent tables
- No Mongo, no document dump of Apollo payloads

---

## 9. Transform and fit score

Transform is the only place business logic lives. Extract does not score. Load does not reinterpret.

Pipeline:

1. Read raw files for `run_id` (CPSA: `{listing}.txt`, or `{listing}.pdf` if text is missing)
2. Parse each listing with its own layout parser; a failure on one listing must not block the others
3. Map to `practitioners` plus interned people / ProfCorp orgs
4. Resolve identity (upsert keys)
5. Compute `licensee_count` and `practice_type` per organization that exists
6. Score each candidate membership (only contact × org pairs)
7. Mark `is_primary_contact`
8. Emit load batches

### 9.1 Score version 1 (registry-only)

Score is 0–100. Missing Apollo firmographics are **not** treated as zeros that fail the lead; they are omitted signals. The score answers: *how well does this practice look like a 5–50 person medical/dental office where the practitioner is still the buyer?*

| Signal | Weight | How it is computed from registry data |
| --- | --- | --- |
| Province / market | 15 | `AB` and in-province address = full points; else 0 (should not appear in these segments) |
| Practice vs hospital | 25 | Named clinic / office > hospital / health-authority / academic title |
| Size proxy (licensee count at org) | 30 | See bands below |
| Decision-maker title | 20 | Owner / Practice Owner / Founder / Managing Partner = full; credential-only = partial; associate / resident / student = 0 |
| Credential match | 10 | MD / physician for medical segment; DDS / DMD / dentist for dental |

**Size proxy bands** (stands in for 5–50 employees, which registries do not provide):

| Licensees at organization | Interpretation | Points (of 30) |
| --- | --- | --- |
| 1 | Likely solo; may still have staff, weaker group-size fit | 12 |
| 2–3 | Small group; near carrier minimums | 22 |
| 4–8 | Best proxy for 5–50 staff including non-licensed employees | 30 |
| 9–15 | Still plausible owner-operated | 22 |
| 16+ | Likely past personal-owner decision | 8 |

Hospitals ignore the band and take the practice-type penalty instead.

**Primary contact:** among members of an organization in a segment, the highest title rank wins; tie-break license status (active over former), then name. The advisor list default view is `is_primary_contact = true`. Other members remain in the table for transparency.

### 9.2 Score breakdown

Always persist the math, for example:

```json
{
  "version": 1,
  "total": 88,
  "signals": {
    "market": 15,
    "practice_type": 25,
    "size_proxy": 30,
    "title": 8,
    "credential": 10
  },
  "inputs": {
    "practice_type": "group",
    "licensee_count": 5,
    "title": null,
    "title_rank": "credential_only"
  }
}
```

Changing weights means bumping `score.version` and re-running **transform + load** on existing raw data. Do not re-extract.

### 9.3 Signals reserved for later (do not code against them)

- Employee headcount range (Apollo or another licensed firmographic source)
- Founded year
- Owner tenure in title
- Revenue band
- Funding / acquisition / IPO
- Job-change recency

When those sources exist, they get a new `score.version`, not a silent overwrite of v1 meaning.

---

## 10. Extract, transform, load jobs

### 10.1 CLI

One entrypoint, phase flags, required segment:

```text
python -m pipeline.cli run --segment alberta-medical-benefits --phase full
python -m pipeline.cli run --segment alberta-dental-benefits --phase transform,load --run-id <uuid>
```

Phases: `extract` | `transform` | `load` | `full`.

`full` = extract (if legally enabled) then transform then load. If extract is gated, `full` on an empty raw dir fails with `skipped_legal_gate` unless `--allow-fixtures` or a manual raw drop is present.

### 10.2 Raw landing layout

```text
data/raw/{segment_id}/{run_id}/
  manifest.json
  pages/{listing_type}.pdf
  pages/{listing_type}.txt    # pdfplumber extract; inspectable after transform
  responses/...               # unused for CPSA PDFs
```

`manifest.json` records segment_id, adapter, started_at, tos_status, file list, per-listing success/failure, and whether the run used fixtures. Raw files are not committed except `pipeline/fixtures/`.

`data/` is gitignored. Fixtures are small, redacted, and sufficient to unit-test parse/score/load.

### 10.3 Source adapters

Each adapter implements:

```text
name: str
tos_status from segment config
iter_records(config, run_dir) -> iterator of raw payloads written to disk
parse(raw_payload) -> source-native dict
```

No shared HTML scraper framework that is then pointed at a new college by URL only. Every college is a named adapter with its own ToS field.

### 10.4 Load semantics

- Upsert `practitioners` on `(source, listing_type, practitioner_key)`
- Upsert organizations on `org_key`
- Upsert contacts on `contact_key`
- Upsert `segment_members` on `(segment_id, organization_id, contact_id)` only when both sides exist
- Refresh `fit_score`, `score_breakdown`, `last_seen_at` on each successful transform
- Do not delete members that disappeared from a run in v1; keep `last_seen_at` so a later job can mark inactive. Hard delete is a later policy.

### 10.5 Idempotency

Re-running transform+load for the same segment with new scores must be safe. `etl_runs` is append-only. Members are upserted, not duplicated.

---

## 11. Enrichment (not in batch ETL)

Trigger: a person opens a specific lead (future UI or a BI “enrich” action).

Behavior: a **write**. It may update `contacts.email`, `contacts.phone`, `organizations.employee_count_estimate`, and `enrichment_status`.

Until Apollo reseller authorization:

- Module may exist as a stub that returns `blocked`
- No network calls
- Presentation remains read-only

Do not schedule enrichment. Do not enrich the whole table.

---

## 12. Presentation (pilot)

Not a custom app.

Connect Metabase or Retool (or equivalent) to Postgres with a read-only role.

Default saved question / app:

- From `segment_members` where `is_primary_contact`
- Join organization and contact
- Columns: name, credentials, practice, city, licensee_count, practice_type, fit_score, specialty, segment
- Filters: `segment_id`, `city`, `sector`, `fit_score >= n`, `practice_type`
- Sort: `fit_score` desc
- Export: CSV

That is the advisor-facing lead list for the scoping phase.

---

## 13. Repository layout

```text
docs/pipeline.md                 # this file
pipeline/
  cli.py
  configs/segments/
    alberta-medical-benefits.yaml
    alberta-dental-benefits.yaml
  extract/
    runner.py
    adapters/
      base.py
      cpsa.py                    # live PDF download when segment extract is allowed
      cdsa.py                    # gated stub; no fixtures yet
    cpsa_listings.py
    cpsa_symbols.py
  transform/
    parse.py
    cpsa.py                      # per-listing PDF/text parsers
    identity.py
    score.py
    normalize.py
  load/
    schema.sql
    upsert.py
  enrichment/
    stub.py                      # always blocked in v1
  fixtures/
    cpsa/listings/               # synthetic text/PDF slices, all six listings
    cdsa/                        # empty until a later dentist task
tests/
  test_identity.py
  test_score.py
  test_load.py
  test_cpsa_parse.py
data/                            # gitignored raw landing
```

Python package, Postgres schema in SQL, segment definitions in YAML. No application UI in this repo for v1.

---

## 14. Infrastructure

### Now (scoping)

| Piece | Choice |
| --- | --- |
| Compute | Local machine, or a scheduled GitHub Action (free) |
| Database | Free-tier managed Postgres (Neon or Supabase) |
| Secrets | GitHub Actions secrets / local `.env` (not committed) |
| Schedule | Manual, then daily/weekly Action once extract is legally enabled |
| Region | Neon/Supabase project in a Canadian region if offered; otherwise accept scoping exception and move at production |

### Later (ongoing pipeline)

| Piece | Choice |
| --- | --- |
| Compute | Containerized Python job on ECS Fargate |
| Trigger | EventBridge schedule, one rule per segment or a single runner with segment list |
| Database | RDS Postgres, `ca-central-1` |
| Secrets | Secrets Manager; never baked into the image |
| Raw landing | S3 in `ca-central-1` replacing local `data/raw` |
| Presentation | Still Metabase/Retool until product placement (HeadStart vs standalone) is decided |

Production region is **Montreal (`ca-central-1`)**, not `us-east-1`. This is Canadian personal and business contact data in a Canadian insurance/financial context.

---

## 15. Compliance gates in the runner

The runner enforces:

1. If `source.tos_status != allowed` → skip network extract, status `skipped_legal_gate`
2. If `extract.enabled != true` → same
3. Apollo / enrichment code paths are unreachable in v1 (stub only)
4. No CASL send path exists in this pipeline; do not add mailers “for testing”

Human work that the runner cannot do, but the project must not skip:

- Read CPSA, CDSA, and ADA terms before flipping `tos_status`
- Confirm the pilot advisor’s licensing before lists become a pitch
- Define CASL consent before any message is sent from these lists

---

## 16. Implementation order

Build in this order so scoring and schema are real before any network adapter exists.

1. Postgres schema + local/Neon connection
2. Segment YAML for the two Alberta segments, extract disabled
3. Fixtures (small, synthetic CPSA PDF/text slices for all six listings)
4. Transform: per-listing parse, practitioners staging, identity, licensee_count, score v1
5. Load upserts + `etl_runs`
6. Metabase/Retool read-only view on `segment_members`
7. Tests for identity collisions, size bands, hospital penalty, gated extract, listing isolation
8. **CPSA ToS review** — still required before `extract.enabled: true`
9. GitHub Action schedule (optional); CDSA still gated
10. Apollo / enrichment: only after a reseller agreement, as a separate change

---

## 17. Open decisions

Resolved by this document unless explicitly revisited:

- Postgres not Mongo
- Segment = extract unit, not a presentation filter
- Org = practice location or CPSA professional corporation; contact = licensee; list = primary `segment_members`
- CPSA ProfCorp is an organization listing; it is not fuzzy-matched to physicians in this version
- CPSA `practitioners` is staging; city-only listings do not become organizations
- Score v1 uses licensee count as size proxy; does not require Apollo
- Enrichment is on-demand and blocked
- Pilot UI is BI, not a custom app

Still open:

- Which dentist directory is canonical (CDSA vs Alberta Dental Association), after ToS review
- Whether hospital-employed physicians are excluded at extract time or only down-scored
- Neon vs Supabase for scoping
- Whether `licensee_count` 1 (true solo) is kept in the loaded set or dropped in the medical/dental segments (presentation can hide them either way; dropping is an extract-policy change)
- Product home (HeadStart vs standalone) after the pilot
