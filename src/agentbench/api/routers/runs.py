"""Canonical benchmark-run HTTP routes."""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ...models import (
    BenchmarkRun as BenchmarkRunModel,
    BenchmarkTask as BenchmarkTaskModel,
)
from ...schemas import BenchmarkRun as BenchmarkRunSchema
from ...schemas import BenchmarkRunCreate, BenchmarkRunList
from ...services.benchmark import BenchmarkService
from ..context import get_db


router = APIRouter()


@router.get("/api/runs", response_model=BenchmarkRunList)
def list_runs(db: Session = Depends(get_db), limit: int = 20, offset: int = 0):
    total = db.query(BenchmarkRunModel).count()
    runs = (
        db.query(BenchmarkRunModel)
        .order_by(BenchmarkRunModel.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return BenchmarkRunList(total=total, limit=limit, offset=offset, items=runs)


@router.post("/api/runs", response_model=BenchmarkRunSchema, status_code=201)
def create_run(run: BenchmarkRunCreate, db: Session = Depends(get_db)):
    task = (
        db.query(BenchmarkTaskModel)
        .filter(BenchmarkTaskModel.id == run.task_id)
        .first()
    )
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    service = BenchmarkService(db)
    try:
        return service.execute_benchmark(
            task,
            agent_config_id=run.agent_config_id,
            agent_name=run.agent_name,
            model_name=run.model_name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/api/runs/{run_id}", response_model=BenchmarkRunSchema)
def get_run(run_id: int, db: Session = Depends(get_db)):
    run = db.query(BenchmarkRunModel).filter(BenchmarkRunModel.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


def _read_run_log(run_id: int, field: str, db: Session) -> dict[str, str]:
    run = db.query(BenchmarkRunModel).filter(BenchmarkRunModel.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    raw_path = getattr(run, field)
    if not raw_path:
        label = "Stdout" if field == "stdout_path" else "Stderr"
        raise HTTPException(status_code=404, detail=f"{label} not available")
    try:
        return {"content": Path(raw_path).read_text(encoding="utf-8")}
    except FileNotFoundError as exc:
        label = "Stdout" if field == "stdout_path" else "Stderr"
        raise HTTPException(status_code=404, detail=f"{label} file not found") from exc


@router.get("/api/runs/{run_id}/stdout")
def get_run_stdout(run_id: int, db: Session = Depends(get_db)):
    return _read_run_log(run_id, "stdout_path", db)


@router.get("/api/runs/{run_id}/stderr")
def get_run_stderr(run_id: int, db: Session = Depends(get_db)):
    return _read_run_log(run_id, "stderr_path", db)
