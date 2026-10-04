"""Server-rendered local dashboard routes."""

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from ...models import (
    BenchmarkRun as BenchmarkRunModel,
    BenchmarkTask as BenchmarkTaskModel,
    Experiment as ExperimentModel,
)
from ...services.experiment import ExperimentNotFoundError, ExperimentService
from ..context import get_db, templates


router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def root(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "title": "AgentBench Local"},
    )


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(
    request: Request,
    db: Session = Depends(get_db),
    limit: int = 20,
    offset: int = 0,
):
    runs = (
        db.query(BenchmarkRunModel)
        .order_by(BenchmarkRunModel.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    total = db.query(BenchmarkRunModel).count()
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "title": "Dashboard",
            "runs": runs,
            "total": total,
            "limit": limit,
            "offset": offset,
        },
    )


@router.get("/experiments", response_class=HTMLResponse)
def experiments_page(
    request: Request,
    db: Session = Depends(get_db),
    limit: int = 20,
    offset: int = 0,
):
    experiments = (
        db.query(ExperimentModel)
        .order_by(ExperimentModel.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    total = db.query(ExperimentModel).count()
    return templates.TemplateResponse(
        "experiments.html",
        {
            "request": request,
            "title": "Experiments",
            "experiments": experiments,
            "total": total,
            "limit": limit,
            "offset": offset,
        },
    )


@router.get("/experiments/{experiment_id}", response_class=HTMLResponse)
def experiment_detail_page(
    request: Request,
    experiment_id: int,
    db: Session = Depends(get_db),
):
    service = ExperimentService(db)
    try:
        experiment = service.get_experiment(experiment_id)
        summary = service.aggregate_experiment(experiment_id)
    except ExperimentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return templates.TemplateResponse(
        "experiment_detail.html",
        {
            "request": request,
            "title": f"Experiment #{experiment_id}",
            "experiment": experiment,
            "summary": summary,
            "ranking": (summary.get("ranking") or {}).get("entries", []),
            "pairwise": summary.get("pairwise_task_comparison", []),
        },
    )


@router.get("/runs/{run_id}", response_class=HTMLResponse)
def run_detail(request: Request, run_id: int, db: Session = Depends(get_db)):
    run = db.query(BenchmarkRunModel).filter(BenchmarkRunModel.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    task = (
        db.query(BenchmarkTaskModel)
        .filter(BenchmarkTaskModel.id == run.task_id)
        .first()
    )
    return templates.TemplateResponse(
        "run_detail.html",
        {
            "request": request,
            "title": f"Run #{run_id}",
            "run": run,
            "task": task,
        },
    )
