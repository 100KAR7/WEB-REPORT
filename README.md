# AI Web Tester

## Highlights

- Crawl a site and measure page response times
- Detect broken links with source-page tracking
- Audit on-page SEO issues and sitewide duplicate metadata
- Generate a richer HTML and JSON report with health scoring, recommendations, and page rankings
- Optionally add AI-written content and UX insights

## Project Structure

## Features

- Crawl pages from a target domain
- Detect broken links
- Measure page performance
- Run SEO checks
- Generate HTML/JSON reports
- Add AI insights through Anthropic or Ollama

## Quick Start

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
python main.py --url https://example.com --format html
```

## Environment

Copy `.env.example` to `.env`:

```bash
ANTHROPIC_API_KEY=
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=llama3
AI_TIMEOUT_SECONDS=240
```

## CLI Usage

```bash
python main.py --url https://example.com --max-pages 10 --format both
python main.py --url https://example.com --no-ai --no-seo
```

## API Service (Phase 2)

Start API server:

```bash
python run_api.py
```

Or:

```bash
uvicorn main_api:app --host 0.0.0.0 --port 8000
```

Endpoints:

- `GET /health` - liveness
- `GET /ready` - readiness
- `POST /v1/runs` - submit audit job (async)
- `GET /v1/runs` - list recent jobs
- `GET /v1/runs/{run_id}` - run status and result

Example run submission:

```bash
export ANTHROPIC_API_KEY="your_api_key_here"   # Linux / Mac
set ANTHROPIC_API_KEY=your_api_key_here        # Windows
curl -X POST "http://localhost:8000/v1/runs" ^
  -H "Content-Type: application/json" ^
  -d "{\"url\":\"https://example.com\",\"max_pages\":5,\"format\":\"json\"}"
```

Run history is persisted in SQLite at `data/app.db`.

## Web MVP (Dashboard)

Once API is running, open:

- [http://localhost:8000/](http://localhost:8000/)

The dashboard lets you:

- Start audit jobs from a web form
- View live run status (queued/running/completed/failed)
- Inspect run JSON details
- Open generated report artifacts directly

## Quality Gates

- Lint: `ruff check .`
- Tests: `python -m pytest`
- CI: GitHub Actions workflow at `.github/workflows/ci.yml`

## Docker

Build image:

```bash
docker build -t ai-web-tester .
```

Run:

```bash
docker run --rm ai-web-tester --url https://example.com --no-ai
```

Run API in Docker:

```bash
docker run --rm -p 8000:8000 ai-web-tester python run_api.py
```

## Release Readiness Checklist

- Set production `.env` secrets
- Validate target-specific crawl limits
- Configure artifact retention for `output/` reports
- Monitor runtime logs for failed pages and AI backend availability
