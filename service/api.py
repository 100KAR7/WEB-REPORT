"""Production API service for AI Web Tester."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, HttpUrl

from service.jobs import JobManager
from service.storage import RunStore


class RunRequest(BaseModel):
    url: HttpUrl
    max_pages: int = Field(default=10, ge=1, le=500)
    format: str = Field(default="html", pattern="^(html|json|both)$")
    no_ai: bool = False
    no_seo: bool = False
    no_perf: bool = False


class RunCreated(BaseModel):
    run_id: int
    status: str


app = FastAPI(title="AI Web Tester API", version="0.3.0")
store = RunStore()
jobs = JobManager(store=store)
output_dir = Path("output")
web_dir = Path("web")

output_dir.mkdir(parents=True, exist_ok=True)
web_dir.mkdir(parents=True, exist_ok=True)
app.mount("/artifacts", StaticFiles(directory=str(output_dir), html=False), name="artifacts")


def _artifact_url(path_value: str) -> str | None:
    if not path_value:
        return None
    artifact_path = Path(path_value)
    name = artifact_path.name
    if not name:
        return None
    return f"/artifacts/{name}"


def _public_run_payload(run: dict) -> dict:
    payload = dict(run)
    result = payload.get("result") or {}
    report_path = result.get("report_path", "")
    payload["report_url"] = _artifact_url(report_path)
    payload["report_path"] = report_path
    return payload


@app.get("/")
def web_home() -> FileResponse:
    index_path = web_dir / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=500, detail="web UI not found")
    return FileResponse(index_path)


@app.get("/web/{asset_name}")
def web_asset(asset_name: str) -> FileResponse:
    asset_path = web_dir / asset_name
    if not asset_path.exists() or not asset_path.is_file():
        raise HTTPException(status_code=404, detail="asset not found")
    return FileResponse(asset_path)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready")
def ready() -> dict[str, str]:
    # DB initialization already happens in RunStore constructor.
    return {"status": "ready"}


@app.post("/v1/runs", response_model=RunCreated, status_code=202)
def create_run(request: RunRequest) -> RunCreated:
    run_id = jobs.submit_run(
        {
            "url": str(request.url),
            "max_pages": request.max_pages,
            "format": request.format,
            "no_ai": request.no_ai,
            "no_seo": request.no_seo,
            "no_perf": request.no_perf,
        }
    )
    return RunCreated(run_id=run_id, status="queued")


@app.get("/v1/runs")
def list_runs(limit: int = 20) -> dict:
    if limit < 1 or limit > 200:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 200")
    runs = store.list_runs(limit=limit)
    return {"items": [_public_run_payload(run) for run in runs]}


@app.get("/v1/runs/{run_id}")
def get_run(run_id: int) -> dict:
    run = store.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="run not found")
    return _public_run_payload(run)
