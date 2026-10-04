"""FastAPI application for AgentBench."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from .. import __version__

from ..models import (
    AgentConfig as AgentConfigModel,
    BenchmarkRun as BenchmarkRunModel,
    BenchmarkTask as BenchmarkTaskModel,
    Experiment as ExperimentModel,
    get_session,
    init_db,
)
from ..schemas import (
    AgentConfig as AgentConfigSchema,
    AgentConfigCreate,
    BenchmarkRun as BenchmarkRunSchema,
    BenchmarkRunCreate,
    BenchmarkRunList,
    BenchmarkTask as BenchmarkTaskSchema,
    BenchmarkTaskCreate,
    ExperimentCreate,
    ExperimentDetail,
    ExperimentList,
    ExperimentResults,
)
from ..services.benchmark import BenchmarkService
from ..services.experiment import (
    ExperimentBusyError,
    ExperimentNotFoundError,
    ExperimentService,
)

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = PACKAGE_ROOT / "static"
TEMPLATES_DIR = PACKAGE_ROOT / "templates"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="AgentBench Local",
    description="A local-first benchmarking platform for coding agents",
    version=__version__,
    lifespan=lifespan,
)

if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def get_db():
    db = get_session()
    try:
        yield db
    finally:
        db.close()


@app.get("/", response_class=HTMLResponse)
def root(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "title": "AgentBench Local"},
    )


@app.get("/dashboard", response_class=HTMLResponse)
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


@app.get("/runs/{run_id}", response_class=HTMLResponse)
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


@app.get("/api/agents", response_model=list[AgentConfigSchema])
def list_agents(db: Session = Depends(get_db)):
    return db.query(AgentConfigModel).all()


@app.post("/api/agents", response_model=AgentConfigSchema, status_code=201)
def create_agent(agent: AgentConfigCreate, db: Session = Depends(get_db)):
    db_agent = AgentConfigModel(**agent.model_dump())
    db.add(db_agent)
    db.commit()
    db.refresh(db_agent)
    return db_agent


@app.get("/api/tasks", response_model=list[BenchmarkTaskSchema])
def list_tasks(db: Session = Depends(get_db), limit: int = 100, offset: int = 0):
    return db.query(BenchmarkTaskModel).offset(offset).limit(limit).all()


@app.post("/api/tasks", response_model=BenchmarkTaskSchema, status_code=201)
def create_task(task: BenchmarkTaskCreate, db: Session = Depends(get_db)):
    db_task = BenchmarkTaskModel(**task.model_dump())
    db.add(db_task)
    db.commit()
    db.refresh(db_task)
    return db_task


@app.get("/api/runs", response_model=BenchmarkRunList)
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


@app.post("/api/runs", response_model=BenchmarkRunSchema, status_code=201)
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


@app.get("/api/runs/{run_id}", response_model=BenchmarkRunSchema)
def get_run(run_id: int, db: Session = Depends(get_db)):
    run = db.query(BenchmarkRunModel).filter(BenchmarkRunModel.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@app.get("/api/runs/{run_id}/stdout")
def get_run_stdout(run_id: int, db: Session = Depends(get_db)):
    run = db.query(BenchmarkRunModel).filter(BenchmarkRunModel.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    if not run.stdout_path:
        raise HTTPException(status_code=404, detail="Stdout not available")
    try:
        return {"content": Path(run.stdout_path).read_text(encoding="utf-8")}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Stdout file not found") from exc


@app.get("/api/runs/{run_id}/stderr")
def get_run_stderr(run_id: int, db: Session = Depends(get_db)):
    run = db.query(BenchmarkRunModel).filter(BenchmarkRunModel.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    if not run.stderr_path:
        raise HTTPException(status_code=404, detail="Stderr not available")
    try:
        return {"content": Path(run.stderr_path).read_text(encoding="utf-8")}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Stderr file not found") from exc


@app.get("/api/experiments", response_model=ExperimentList)
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


@app.post("/api/experiments", response_model=ExperimentDetail, status_code=201)
def create_experiment(
    request: ExperimentCreate,
    db: Session = Depends(get_db),
):
    service = ExperimentService(db)
    try:
        return service.create_experiment(**request.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/experiments/{experiment_id}", response_model=ExperimentDetail)
def get_experiment(experiment_id: int, db: Session = Depends(get_db)):
    service = ExperimentService(db)
    try:
        return service.get_experiment(experiment_id)
    except ExperimentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post(
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


@app.get(
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
