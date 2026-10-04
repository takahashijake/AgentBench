"""Pydantic schemas for AgentBench API."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class AgentConfigBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    command_template: str = Field(default="qwen -p {prompt}")
    enabled: bool = True


class AgentConfigCreate(AgentConfigBase):
    pass


class AgentConfigUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    command_template: Optional[str] = None
    enabled: Optional[bool] = None


class AgentConfig(AgentConfigBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BenchmarkTaskBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str = Field(..., min_length=1)
    repository_path: str = Field(..., min_length=1)
    base_commit: str = Field(..., min_length=40, max_length=64)
    agent_prompt: str = Field(..., min_length=1)
    setup_command: Optional[str] = None
    test_command: str = Field(default="pytest")
    timeout: int = Field(default=300, ge=1, le=3600)
    enabled: bool = True


class BenchmarkTaskCreate(BenchmarkTaskBase):
    agent_config_id: Optional[int] = None


class BenchmarkTaskUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    repository_path: Optional[str] = None
    base_commit: Optional[str] = Field(None, min_length=40, max_length=64)
    agent_prompt: Optional[str] = None
    setup_command: Optional[str] = None
    test_command: Optional[str] = None
    timeout: Optional[int] = Field(None, ge=1, le=3600)
    enabled: Optional[bool] = None
    agent_config_id: Optional[int] = None


class BenchmarkTask(BenchmarkTaskBase):
    id: int
    agent_config_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class BenchmarkRunBase(BaseModel):
    task_id: int
    agent_name: Optional[str] = None
    model_name: Optional[str] = None


class BenchmarkRunCreate(BenchmarkRunBase):
    agent_config_id: Optional[int] = None
    agent_name: Optional[str] = None
    model_name: Optional[str] = None


class BenchmarkRun(BenchmarkRunBase):
    id: int
    agent_config_id: Optional[int] = None
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    exit_code: Optional[int] = None
    success: Optional[bool] = None
    test_command: Optional[str] = None
    test_passed: int = 0
    test_failed: int = 0
    test_error: Optional[str] = None
    tests_passed: Optional[bool] = None
    files_changed: int = 0
    insertions: int = 0
    deletions: int = 0
    diff_stats: Optional[str] = None
    stdout_path: Optional[str] = None
    stderr_path: Optional[str] = None
    results: Optional[Dict[str, Any]] = None
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class BenchmarkRunList(BaseModel):
    total: int
    limit: int
    offset: int
    items: List[BenchmarkRun]


class DiffStats(BaseModel):
    files_changed: int
    insertions: int
    deletions: int
    diff_stats: Optional[str] = None


class TestResult(BaseModel):
    command: str
    passed: bool
    tests_passed: int
    tests_failed: int
    error: Optional[str] = None
    output: Optional[str] = None


class BenchmarkRunResult(BaseModel):
    run_id: int
    task_id: int
    task_name: str
    agent_name: Optional[str] = None
    model_name: Optional[str] = None
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    exit_code: Optional[int] = None
    success: Optional[bool] = None
    test_result: Optional[TestResult] = None
    diff_stats: Optional[DiffStats] = None
    stdout_path: Optional[str] = None
    stderr_path: Optional[str] = None
    results: Optional[Dict[str, Any]] = None
