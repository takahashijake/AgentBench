"""FastAPI application for AgentBench."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..models import (
    AgentConfig as AgentConfigModel,
    BenchmarkRun as BenchmarkRunModel,
    BenchmarkTask as BenchmarkTaskModel,
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
)
from ..services.benchmark import BenchmarkService

PROJECT_ROOT = Path(__file__).resolve().parents[3]
STATIC_DIR = PROJECT_ROOT / "static"
TEMPLATES_DIR = PROJECT_ROOT / "templates"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="AgentBench Local",
    description="A local-first benchmarking platform for coding agents",
    version="0.2.0",
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
def run_detail(
    request: Request,
    run_id: int,
    db: Session = Depends(get_db),
):
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
def create_agent(
    agent: AgentConfigCreate,
    db: Session = Depends(get_db),
):
    db_agent = AgentConfigModel(**agent.model_dump())
    db.add(db_agent)
    db.commit()
    db.refresh(db_agent)
    return db_agent


@app.get("/api/tasks", response_model=list[BenchmarkTaskSchema])
def list_tasks(
    db: Session = Depends(get_db),
    limit: int = 100,
    offset: int = 0,
):
    return db.query(BenchmarkTaskModel).offset(offset).limit(limit).all()


@app.post("/api/tasks", response_model=BenchmarkTaskSchema, status_code=201)
def create_task(
    task: BenchmarkTaskCreate,
    db: Session = Depends(get_db),
):
    db_task = BenchmarkTaskModel(**task.model_dump())
    db.add(db_task)
    db.commit()
    db.refresh(db_task)
    return db_task


@app.get("/api/runs", response_model=BenchmarkRunList)
def list_runs(
    db: Session = Depends(get_db),
    limit: int = 20,
    offset: int = 0,
):
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
def create_run(
    run: BenchmarkRunCreate,
    db: Session = Depends(get_db),
):
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
