# shortlist-extractor

Internship postings bury facts people care about inside walls of text. This service reads a posting and returns those facts as structured fields. Each extracted value comes with a confidence score, and low scores are flagged for further verification.

It also compares three ways of doing the extraction:

| Backend | What it is | Cost to run |
| --- | --- | --- |
| `rules` | regex and keyword rules | Free, instant |
| `teacher` | A large hosted LLM (Claude Sonnet 4.6) | Paid per posting |
| `student` | A small open model fine-tuned with LoRA on the teacher's labels, running on CPU | Free after training |

We want to see how close a free local student model get to the paid teacher model, and if either are better than regex.

This also servers as the extraction service for a larger project *Shortlist*, a Django app that tracks internship applications. The app calls this service over HTTP through the small client in [`client/`](client/).

## Results

> **Status: in progress.** The rules backend and the evaluation harness are built. Scores will be filled in once the 127 gold labels (93 test, 34 calibration) are finished. The teacher and student rows come in Stages 5 and 6.

Scores on the held-out **test split**: 93 labeled postings from 51 organizations that appear nowhere in training, at most 3 per organization. Brackets are 95% bootstrap intervals.

| Metric | Rules | Teacher | Student |
| --- | --- | --- | --- |
| Citizenship macro-F1 | — | — | — |
| Clearance macro-F1 | — | — | — |
| Work mode macro-F1 | — | — | — |
| Deadline exact match | — | — | — |
| Pay period accuracy | — | — | — |
| Skills set F1 | — | — | — |
| Cost per 1,000 postings | $0 | — | $0 |
| Latency p50 / p95 | — | — | — |
| Auto-accept rate | — | — | — |

Every run of the harness appends a full per-field table to [`eval/results.md`](eval/results.md).

## Running it

You need [uv](https://docs.astral.sh/uv/) or Docker.

### With Docker (what the team app uses)

```bash
docker run -p 8001:8001 ghcr.io/liamreeves34/shortlist-extractor:latest
```

Then open http://localhost:8001/docs to try every endpoint in the browser.

The image starts with canned answers and never touches the network. Use environment variables to switch it to real work:

```bash
docker run -p 8001:8001 \
  -e EXTRACTOR_BACKEND=rules \
  -e CONNECTOR_MODE=live \
  ghcr.io/liamreeves34/shortlist-extractor:latest
```

### From source

```bash
uv sync
uv run uvicorn service.main:app --reload --port 8001
```

Settings come from environment variables, then a `.env` file in the project root, then the defaults. Copy [`.env.example`](.env.example) to `.env` to start. Never commit `.env`; it holds the API key once the teacher backend exists.

| Variable | Values | Default | Controls |
| --- | --- | --- | --- |
| `EXTRACTOR_BACKEND` | `stub`, `rules`, `teacher`, `student` | `stub` | Who answers `/v1/extract` |
| `CONNECTOR_MODE` | `stub`, `live` | `stub` | Whether `/v1/sources/fetch` calls the real job boards |
| `CONNECTOR_USER_AGENT` | any string | `Shortlist Extractor Service` | The User-Agent sent to the job boards |

### Tests and checks

```bash
uv run ruff format . ; uv run ruff check . ; uv run pytest
```

The tests never touch the network: the job boards are replaced with fake ones that answer from fixture files. CI runs the same three commands on every pull request.

## The API

| Endpoint | Does |
| --- | --- |
| `GET /healthz` | Reports which backend and connector mode are active |
| `POST /v1/extract` | Takes `{"text": ...}` or `{"url": ...}` (exactly one), plus an optional `fields` list, and returns the fields |
| `POST /v1/sources/fetch` | Takes `{"provider": "greenhouse" \| "lever" \| "ashby", "token": ...}` and returns that employer's current internship postings |

Every extracted field comes back in the same shape:

```json
"citizenship": {
  "value": "US_CITIZEN",
  "confidence": 0.9,
  "needs_review": false,
  "evidence": "Must be a U.S. citizen.",
  "source": "rules"
}
```

The 12 fields are `title`, `organization`, `location`, `start_term`, `deadline`, `deadline_type`, `degree_levels`, `citizenship`, `clearance`, `work_mode`, `pay`, and `skills`. Their allowed values and definitions are in the [labeling guide](docs/labeling_guide.md).

The contract is published as JSON Schema in [`contract/`](contract/). The files are generated from [`service/schemas.py`](service/schemas.py) by `uv run python -m scripts.export_schema`, and a test fails if they drift from the code.

`url` only accepts Greenhouse, Lever, and Ashby job pages, so the service can't be pointed at arbitrary addresses.

## Method

### 1. Collecting postings

[`sources.yaml`](sources.yaml) lists 1,008 employer job boards (472 Greenhouse, 392 Ashby, 144 Lever). They were seeded from the links in a public community internship list ([`scripts/seed_sources.py`](scripts/seed_sources.py)), and only boards that answered were kept.

[`pipeline/collect.py`](pipeline/collect.py) fetches every board through the same connectors the service uses and saves each posting **once**, under its content hash. Duplicates collapse automatically, and a posting whose text changes gets a new file instead of overwriting the old one. Collection pauses one second between boards.

Raw posting text is employer content, so it is **not committed**. Only the manifests are committed, and they hold hashes and IDs only.

### 2. Splitting by organization

[`pipeline/build_dataset.py`](pipeline/build_dataset.py) splits the 2,802 collected postings **by organization**, not by posting: every company lands entirely in one split. Companies reuse posting templates, so a random split would put near-copies of the same posting in both training and test and inflate every score.

| Split | Postings | Organizations | Used for |
| --- | --- | --- | --- |
| `train_pool` | 2,627 | 534 | Teacher labels, then student training |
| `calibration` | 50 | 17 | Fitting confidence calibration (Stage 7); 34 hand-labeled |
| `test` | 125 | 51 | Final scores only; never trained or tuned on; 93 hand-labeled |

Details:
- **Fixed seed (42)**, recorded with the counts in [`data/manifests/split.json`](data/manifests/split.json), so the split is reproducible.
- **Only organizations with at most 10 postings go into calibration or test.** Otherwise a single big employer could fill half the test set.
- **Aliases merge name variants** of the same company (for example two spellings on two job boards) before splitting, so one company can't land on both sides.

The split manifests are in [`data/manifests/`](data/manifests/).

### 3. Gold labels

Calibration and test postings are labeled by hand with [`pipeline/label_gold.py`](pipeline/label_gold.py), following the rules in [`docs/labeling_guide.md`](docs/labeling_guide.md).

**At most 3 postings per organization are labeled** in each split: 93 of the 125 test postings and 34 of the 50 calibration postings, covering every organization. One test posting is skipped because the job board returned no description text. An employer's postings share most of their text, so a 4th posting from the same employer adds little information and would make the intervals look tighter than they are. Within an organization, the postings labeled are the first ones in manifest order; one test organization has 4, because they were labeled before the cap. Labels are written to `data/labels/gold.jsonl` along with the guide version they followed. The labeling script resumes where it left off.

### 4. Backends

- **Rules** ([`service/backends/rules.py`](service/backends/rules.py)): one small function per field. Category fields check patterns from most to least restrictive (for example, U.S. citizen before U.S. person before work-authorized). A match gets confidence 0.9 and the sentence it matched as evidence. No match falls back to a default with confidence 0.3 and `needs_review: true`.
- **Teacher** (Stage 5): Claude Sonnet 4.6 with structured outputs, labeling the training pool once.
- **Student** (Stage 6): a small open instruct model (Qwen3, under 2B parameters) fine-tuned with LoRA on the teacher's labels. It runs on CPU, so serving it needs no GPU.

All backends implement the same interface ([`service/backends/base.py`](service/backends/base.py)), so the endpoint and the evaluation code don't change when the backend does.

### 5. Evaluation

[`eval/run.py`](eval/run.py) scores any backend against the gold labels:

```bash
uv run python -m eval.run --backend rules --split test
```

| Field type | Fields | Metric |
| --- | --- | --- |
| Category | citizenship, clearance, work mode, deadline type | Accuracy and macro-F1 |
| Date | deadline | Exact match (a correct "no deadline" counts) |
| Set | degree levels, skills | Precision, recall, F1 |
| Pay | pay | Min, max, and period each exact |
| Short text | title, organization, location, start term | Exact after lowercasing and trimming |

Macro-F1 is reported alongside accuracy because most postings say nothing about citizenship or clearance. A backend that always answers "none mentioned" gets high accuracy and a poor macro-F1.

The 95% intervals come from 1,000 bootstrap resamples of the test postings with a fixed seed. With 93 postings they are wide, so two backends whose intervals overlap aren't shown to differ.

## Repository layout

```
service/      the FastAPI service (runs in the container)
  backends/   who answers /v1/extract: stub, rules, teacher, student
  connectors/ who answers /v1/sources/fetch: Greenhouse, Lever, Ashby
client/       the HTTP client the team app copies in
contract/     JSON Schemas generated from service/schemas.py
pipeline/     offline data work: collect, split, label
eval/         metrics, harness, and results
scripts/      schema export and source seeding
docs/         the labeling guide
training/     LoRA fine-tuning (Stage 6)
data/         manifests and labels committed; raw postings local only
```

## Limitations

- **Small test set.** 93 labeled postings from 51 organizations (at most 3 per organization) gives wide confidence intervals. The results support large differences, not small ones.
- **One labeler.** The gold labels are a single person's judgment, guided by a written rubric. There is no inter-annotator agreement score.
- **Snapshot in time.** Postings were collected in fall 2026 for summer 2027 roles. Wording conventions drift.
- **Few deadlines.** Most collected postings give no application deadline, so deadline scores rest on very few positive examples.
- **The student learns from the teacher.** Its ceiling is the teacher's accuracy. Teacher mistakes on the training pool are learned as if they were correct.
- **Only three job boards.** Postings from Workday, iCIMS, and company career sites aren't collected. Pasted text still works through `/v1/extract`.
- **U.S.-centric fields.** Citizenship and clearance categories follow U.S. rules.

## License

MIT. See [LICENSE](LICENSE).
