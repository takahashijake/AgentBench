"""Agent and benchmark-task resource routes."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...models import (
    AgentConfig as AgentConfigModel,
    BenchmarkTask as BenchmarkTaskModel,
)
from ...schemas import (
    AgentConfig as AgentConfigSchema,
    AgentConfigCreate,
    BenchmarkTask as BenchmarkTaskSchema,
    BenchmarkTaskCreate,
)
from ..context import get_db


router = APIRouter()


@router.get("/api/agents", response_model=list[AgentConfigSchema])
def list_agents(db: Session = Depends(get_db)):
    return db.query(AgentConfigModel).all()


@router.post("/api/agents", response_model=AgentConfigSchema, status_code=201)
def create_agent(agent: AgentConfigCreate, db: Session = Depends(get_db)):
    db_agent = AgentConfigModel(**agent.model_dump())
    db.add(db_agent)
    db.commit()
    db.refresh(db_agent)
    return db_agent


@router.get("/api/tasks", response_model=list[BenchmarkTaskSchema])
def list_tasks(db: Session = Depends(get_db), limit: int = 100, offset: int = 0):
    return db.query(BenchmarkTaskModel).offset(offset).limit(limit).all()


@router.post("/api/tasks", response_model=BenchmarkTaskSchema, status_code=201)
def create_task(task: BenchmarkTaskCreate, db: Session = Depends(get_db)):
    db_task = BenchmarkTaskModel(**task.model_dump())
    db.add(db_task)
    db.commit()
    db.refresh(db_task)
    return db_task
