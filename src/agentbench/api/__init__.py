"""FastAPI application for AgentBench."""

from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from .models import get_session, AgentConfig, BenchmarkTask, BenchmarkRun
from .schemas import (
    AgentConfigCreate,
    AgentConfig,
    BenchmarkTaskCreate,
    BenchmarkTask,
    BenchmarkRunCreate,
    BenchmarkRun,
    BenchmarkRunList,
)
from .services.benchmark import BenchmarkService

app = FastAPI(
    title="AgentBench Local",
    description="A local-first benchmarking platform for coding agents",
    version="0.1.0",
)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Templates
templates = Jinja2Templates(directory="templates")


# Dependency for database session
def get_db():
    """Get database session dependency."""
    db = get_session()
    try:
        yield db
    finally:
        db.close()


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """Root endpoint redirecting to dashboard."""
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "title": "AgentBench Local"}
    )


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    db: Session = Depends(get_db),
    limit: int = 20,
    offset: int = 0
):
    """Dashboard showing recent benchmark runs."""
    runs = db.query(BenchmarkRun).order_by(
        BenchmarkRun.created_at.desc()
    ).offset(offset).limit(limit).all()
    
    total = db.query(BenchmarkRun).count()
    
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "title": "Dashboard",
            "runs": runs,
            "total": total,
            "limit": limit,
            "offset": offset,
        }
    )


@app.get("/runs/{run_id}", response_class=HTMLResponse)
async def run_detail(
    request: Request,
    run_id: int,
    db: Session = Depends(get_db)
):
    """Detail page for a benchmark run."""
    run = db.query(BenchmarkRun).filter(BenchmarkRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    
    task = db.query(BenchmarkTask).filter(BenchmarkTask.id == run.task_id).first()
    
    return templates.TemplateResponse(
        "run_detail.html",
        {
            "request": request,
            "title": f"Run #{run_id}",
            "run": run,
            "task": task,
        }
    )


# API endpoints
@app.get("/api/agents", response_model=list[AgentConfig])
async def list_agents(db: Session = Depends(get_db)):
    """List all agent configurations."""
    return db.query(AgentConfig).all()


@app.post("/api/agents", response_model=AgentConfig, status_code=201)
async def create_agent(
    agent: AgentConfigCreate,
    db: Session = Depends(get_db)
):
    """Create a new agent configuration."""
    db_agent = AgentConfig(**agent.model_dump())
    db.add(db_agent)
    db.commit()
    db.refresh(db_agent)
    return db_agent


@app.get("/api/tasks", response_model=list[BenchmarkTask])
async def list_tasks(
    db: Session = Depends(get_db),
    limit: int = 100,
    offset: int = 0
):
    """List all benchmark tasks."""
    return db.query(BenchmarkTask).offset(offset).limit(limit).all()


@app.post("/api/tasks", response_model=BenchmarkTask, status_code=201)
async def create_task(
    task: BenchmarkTaskCreate,
    db: Session = Depends(get_db)
):
    """Create a new benchmark task."""
    db_task = BenchmarkTask(**task.model_dump())
    db.add(db_task)
    db.commit()
    db.refresh(db_task)
    return db_task


@app.get("/api/runs", response_model=BenchmarkRunList)
async def list_runs(
    db: Session = Depends(get_db),
    limit: int = 20,
    offset: int = 0
):
    """List benchmark runs with pagination."""
    total = db.query(BenchmarkRun).count()
    runs = db.query(BenchmarkRun).order_by(
        BenchmarkRun.created_at.desc()
    ).offset(offset).limit(limit).all()
    
    return BenchmarkRunList(
        total=total,
        limit=limit,
        offset=offset,
        items=runs
    )


@app.post("/api/runs", response_model=BenchmarkRun, status_code=201)
async def create_run(
    run: BenchmarkRunCreate,
    db: Session = Depends(get_db)
):
    """Execute a benchmark run."""
    # Verify task exists
    task = db.query(BenchmarkTask).filter(BenchmarkTask.id == run.task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Execute the benchmark
    service = BenchmarkService(db)
    try:
        benchmark_run = service.execute_benchmark(
            task,
            agent_config_id=run.agent_config_id,
            agent_name=run.agent_name,
            model_name=run.model_name
        )
        return benchmark_run
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/runs/{run_id}", response_model=BenchmarkRun)
async def get_run(run_id: int, db: Session = Depends(get_db)):
    """Get a specific benchmark run."""
    run = db.query(BenchmarkRun).filter(BenchmarkRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@app.get("/api/runs/{run_id}/stdout")
async def get_run_stdout(run_id: int, db: Session = Depends(get_db)):
    """Get stdout for a benchmark run."""
    run = db.query(BenchmarkRun).filter(BenchmarkRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    
    if not run.stdout_path:
        raise HTTPException(status_code=404, detail="Stdout not available")
    
    try:
        with open(run.stdout_path, "r") as f:
            content = f.read()
        return {"content": content}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Stdout file not found")


@app.get("/api/runs/{run_id}/stderr")
async def get_run_stderr(run_id: int, db: Session = Depends(get_db)):
    """Get stderr for a benchmark run."""
    run = db.query(BenchmarkRun).filter(BenchmarkRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    
    if not run.stderr_path:
        raise HTTPException(status_code=404, detail="Stderr not available")
    
    try:
        with open(run.stderr_path, "r") as f:
            content = f.read()
        return {"content": content}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Stderr file not found")
