"""Database models for AgentBench."""

from datetime import datetime
from typing import Optional
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, JSON, Float, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class AgentConfig(Base):
    """Configuration for an agent adapter."""
    __tablename__ = "agent_configs"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), unique=True, nullable=False)
    description = Column(Text, nullable=True)
    command_template = Column(Text, nullable=False, default="qwen -p \"{prompt}\"")
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    benchmark_tasks = relationship("BenchmarkTask", back_populates="default_agent")
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

    # Relationships
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

    # Agent identity
    agent_name = Column(String(255), nullable=True)
    model_name = Column(String(255), nullable=True)

    # Execution timestamps
    started_at = Column(DateTime, nullable=True)
    ended_at = Column(DateTime, nullable=True)
    duration_seconds = Column(Float, nullable=True)

    # Exit status
    exit_code = Column(Integer, nullable=True)
    success = Column(Boolean, nullable=True)

    # Test results
    test_command = Column(String(1024), nullable=True)
    test_passed = Column(Integer, default=0)
    test_failed = Column(Integer, default=0)
    test_error = Column(Text, nullable=True)
    tests_passed = Column(Boolean, nullable=True)

    # Git diff statistics
    files_changed = Column(Integer, default=0)
    insertions = Column(Integer, default=0)
    deletions = Column(Integer, default=0)
    diff_stats = Column(Text, nullable=True)

    # Output logs (stored in files, path recorded here)
    stdout_path = Column(String(1024), nullable=True)
    stderr_path = Column(String(1024), nullable=True)

    # Full results as JSON for flexibility
    results = Column(JSON, nullable=True)

    # Optional token metrics
    prompt_tokens = Column(Integer, nullable=True)
    completion_tokens = Column(Integer, nullable=True)
    total_tokens = Column(Integer, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
