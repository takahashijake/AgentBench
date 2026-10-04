"""Experiment planning, execution, analysis, and bundle HTTP routes."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ...result_bundles import ResultBundleService
from ...schemas import (
    ExperimentCreate,
    ExperimentDetail,
    ExperimentList,
    ExperimentResults,
)
from ...models import Experiment as ExperimentModel
from ...services.experiment import (
    ExperimentBusyError,
    ExperimentNotFoundError,
    ExperimentService,
)
from ..context import get_db


router = APIRouter()


@router.get("/api/experiments", response_model=ExperimentList)
def list_experiments(
    db: Session = Depends(get_db),
    limit: int = 20,
    offset: int = 0,
):
    total = db.query(ExperimentModel).count()
    experiments = (
        db.query(ExperimentModel)
        .order_by(ExperimentModel.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return ExperimentList(
        total=total,
        limit=limit,
        offset=offset,
        items=experiments,
    )


@router.post("/api/experiments", response_model=ExperimentDetail, status_code=201)
def create_experiment(
    request: ExperimentCreate,
    db: Session = Depends(get_db),
):
    service = ExperimentService(db)
    try:
        return service.create_experiment(**request.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/experiments/{experiment_id}", response_model=ExperimentDetail)
def get_experiment(experiment_id: int, db: Session = Depends(get_db)):
    service = ExperimentService(db)
    try:
        return service.get_experiment(experiment_id)
    except ExperimentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/api/experiments/{experiment_id}/run",
    response_model=ExperimentResults,
)
def run_experiment(experiment_id: int, db: Session = Depends(get_db)):
    service = ExperimentService(db)
    try:
        experiment = service.execute_experiment(experiment_id)
        return ExperimentResults(
            experiment=experiment,
            summary=service.aggregate_experiment(experiment_id),
        )
    except ExperimentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ExperimentBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/api/experiments/{experiment_id}/leaderboard")
def get_experiment_leaderboard(
    experiment_id: int,
    db: Session = Depends(get_db),
):
    service = ExperimentService(db)
    try:
        experiment = service.get_experiment(experiment_id)
        summary = service.aggregate_experiment(experiment_id)
        return {
            "analysis_schema_version": summary.get("analysis_schema_version", 3),
            "experiment_id": experiment.id,
            "experiment_name": experiment.name,
            "ranking": summary.get("ranking"),
            "pairwise_task_comparison": summary.get(
                "pairwise_task_comparison",
                [],
            ),
        }
    except ExperimentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/api/experiments/{experiment_id}/results",
    response_model=ExperimentResults,
)
def get_experiment_results(experiment_id: int, db: Session = Depends(get_db)):
    service = ExperimentService(db)
    try:
        experiment = service.get_experiment(experiment_id)
        return ExperimentResults(
            experiment=experiment,
            summary=service.aggregate_experiment(experiment_id),
        )
    except ExperimentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/api/experiments/{experiment_id}/bundle")
def describe_experiment_bundle(
    experiment_id: int,
    db: Session = Depends(get_db),
):
    """Advertise the CLI export path without streaming arbitrary local artifacts."""
    service = ExperimentService(db)
    try:
        experiment = service.get_experiment(experiment_id)
    except ExperimentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "experiment_id": experiment.id,
        "experiment_name": experiment.name,
        "command": f"agentbench bundle export {experiment.id} -o experiment-{experiment.id}.zip",
        "bundle_service": ResultBundleService.__name__,
    }
