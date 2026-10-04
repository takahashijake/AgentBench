"""Database models for AgentBench."""

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class AgentConfig(Base):
    """Configuration for an agent adapter."""

    __tablename__ = "agent_configs"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), unique=True, nullable=False)
    description = Column(Text, nullable=True)
    command_template = Column(Text, nullable=False, default="qwen -p {prompt}")
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    benchmark_tasks = relationship("BenchmarkTask", back_populates="agent_config")
    benchmark_runs = relationship("BenchmarkRun", back_populates="agent_config")


class BenchmarkTask(Base):
    """Represents a software engineering task for benchmarking."""

    __tablename__ = "benchmark_tasks"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    repository_path = Column(String(1024), nullable=False)
    base_commit = Column(String(64), nullable=False)
    agent_prompt = Column(Text, nullable=False)
    setup_command = Column(String(1024), nullable=True)
    test_command = Column(String(1024), nullable=False, default="pytest")
    timeout = Column(Integer, default=300)
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    agent_config_id = Column(Integer, ForeignKey("agent_configs.id"), nullable=True)
    agent_config = relationship("AgentConfig", back_populates="benchmark_tasks")
    benchmark_runs = relationship("BenchmarkRun", back_populates="task")


class BenchmarkRun(Base):
    """Represents one execution of an agent against a benchmark task."""

    __tablename__ = "benchmark_runs"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("benchmark_tasks.id"), nullable=False)
    task = relationship("BenchmarkTask", back_populates="benchmark_runs")

    agent_config_id = Column(Integer, ForeignKey("agent_configs.id"), nullable=True)
    agent_config = relationship("AgentConfig", back_populates="benchmark_runs")

    agent_name = Column(String(255), nullable=True)
    model_name = Column(String(255), nullable=True)

    started_at = Column(DateTime, nullable=True)
    ended_at = Column(DateTime, nullable=True)
    duration_seconds = Column(Float, nullable=True)

    exit_code = Column(Integer, nullable=True)
    success = Column(Boolean, nullable=True)

    test_command = Column(String(1024), nullable=True)
    test_passed = Column(Integer, default=0)
    test_failed = Column(Integer, default=0)
    test_error = Column(Text, nullable=True)
    tests_passed = Column(Boolean, nullable=True)

    files_changed = Column(Integer, default=0)
    insertions = Column(Integer, default=0)
    deletions = Column(Integer, default=0)
    diff_stats = Column(Text, nullable=True)

    stdout_path = Column(String(1024), nullable=True)
    stderr_path = Column(String(1024), nullable=True)

    results = Column(JSON, nullable=True)

    prompt_tokens = Column(Integer, nullable=True)
    completion_tokens = Column(Integer, nullable=True)
    total_tokens = Column(Integer, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
