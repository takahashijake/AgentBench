"""Pydantic schemas for AgentBench API."""

from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field


class AgentConfigBase(BaseModel):
    """Base schema for agent configuration."""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    command_template: str = Field(default="qwen -p \"{prompt}\"")
    enabled: bool = True


class AgentConfigCreate(AgentConfigBase):
    """Schema for creating a new agent configuration."""
    pass


class AgentConfigUpdate(BaseModel):
    """Schema for updating an agent configuration."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    command_template: Optional[str] = None
    enabled: Optional[bool] = None


class AgentConfig(AgentConfigBase):
    """Schema for agent configuration with database fields."""
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class BenchmarkTaskBase(BaseModel):
    """Base schema for benchmark task."""
    name: str = Field(..., min_length=1, max_length=255)
    description: str = Field(..., min_length=1)
    repository_path: str = Field(..., min_length=1)
    base_commit: str = Field(..., min_length=40, max_length=64)
    agent_prompt: str = Field(..., min_length=1)
    setup_command: Optional[str] = None
    test_command: str = Field(default="pytest")
    timeout: int = Field(default=300, ge=60, le=3600)
    enabled: bool = True


class BenchmarkTaskCreate(BenchmarkTaskBase):
    """Schema for creating a new benchmark task."""
    agent_config_id: Optional[int] = None


class BenchmarkTaskUpdate(BaseModel):
    """Schema for updating a benchmark task."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    repository_path: Optional[str] = None
    base_commit: Optional[str] = Field(None, min_length=40, max_length=64)
    agent_prompt: Optional[str] = None
    setup_command: Optional[str] = None
    test_command: Optional[str] = None
    timeout: Optional[int] = Field(None, ge=60, le=3600)
    enabled: Optional[bool] = None
    agent_config_id: Optional[int] = None


class BenchmarkTask(BenchmarkTaskBase):
    """Schema for benchmark task with database fields."""
    id: int
    agent_config_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class BenchmarkRunBase(BaseModel):
    """Base schema for benchmark run."""
    task_id: int
    agent_name: Optional[str] = None
    model_name: Optional[str] = None


class BenchmarkRunCreate(BenchmarkRunBase):
    """Schema for creating a new benchmark run."""
    agent_config_id: Optional[int] = None
    agent_name: Optional[str] = None
    model_name: Optional[str] = None


class BenchmarkRun(BenchmarkRunBase):
    """Schema for benchmark run with database fields."""
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
    """Schema for listing benchmark runs with pagination."""
    total: int
    limit: int
    offset: int
    items: List[BenchmarkRun]


class DiffStats(BaseModel):
    """Schema for git diff statistics."""
    files_changed: int
    insertions: int
    deletions: int
    diff_stats: Optional[str] = None


class TestResult(BaseModel):
    """Schema for test execution results."""
    command: str
    passed: bool
    tests_passed: int
    tests_failed: int
    error: Optional[str] = None
    output: Optional[str] = None


class BenchmarkRunResult(BaseModel):
    """Schema for complete benchmark run result."""
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
