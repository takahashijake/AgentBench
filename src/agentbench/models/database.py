"""Database models for AgentBench."""

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, relationship

from ..timeutils import utc_now


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
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

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
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

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

    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)


class Experiment(Base):
    """Persisted tasks × agents × repetitions benchmark plan."""

    __tablename__ = "experiments"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    repetitions = Column(Integer, nullable=False, default=1)
    stop_on_error = Column(Boolean, nullable=False, default=False)
    status = Column(String(64), nullable=False, default="pending")
    task_ids = Column(JSON, nullable=False)
    agent_config_ids = Column(JSON, nullable=False)
    task_snapshots = Column(JSON, nullable=False)
    agent_snapshots = Column(JSON, nullable=False)
    planned_runs = Column(Integer, nullable=False, default=0)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    trials = relationship(
        "ExperimentTrial",
        back_populates="experiment",
        cascade="all, delete-orphan",
        order_by="ExperimentTrial.ordinal",
    )
    executions = relationship(
        "ExperimentExecution",
        back_populates="experiment",
        cascade="all, delete-orphan",
        order_by="ExperimentExecution.id",
    )
    worker_attempts = relationship(
        "ExperimentWorkerAttempt",
        back_populates="experiment",
        cascade="all, delete-orphan",
        order_by="ExperimentWorkerAttempt.id",
    )
    budget = relationship(
        "ExperimentBudget",
        back_populates="experiment",
        cascade="all, delete-orphan",
        uselist=False,
    )


class ExperimentExecution(Base):
    """One persisted execution attempt for an experiment."""

    __tablename__ = "experiment_executions"

    id = Column(Integer, primary_key=True, index=True)
    experiment_id = Column(
        Integer, ForeignKey("experiments.id"), nullable=False, index=True
    )
    mode = Column(String(64), nullable=False)
    max_workers = Column(Integer, nullable=False, default=1)
    status = Column(String(64), nullable=False, default="running")
    details = Column(JSON, nullable=True)
    started_at = Column(DateTime, nullable=False, default=utc_now)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    experiment = relationship("Experiment", back_populates="executions")


class ExperimentBudget(Base):
    """Durable scheduling budget and aggregate reservation state."""

    __tablename__ = "experiment_budgets"

    id = Column(Integer, primary_key=True, index=True)
    experiment_id = Column(
        Integer, ForeignKey("experiments.id"), nullable=False, unique=True, index=True
    )
    policy = Column(JSON, nullable=False)
    status = Column(String(64), nullable=False, default="active", index=True)
    reserved_trials = Column(Integer, nullable=False, default=0)
    exhaustion_reason = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=True)
    exhausted_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    experiment = relationship("Experiment", back_populates="budget")
    reservations = relationship(
        "ExperimentBudgetReservation",
        back_populates="budget",
        cascade="all, delete-orphan",
        order_by="ExperimentBudgetReservation.id",
    )


class ExperimentBudgetReservation(Base):
    """One conservative budget slot consumed before agent execution."""

    __tablename__ = "experiment_budget_reservations"

    id = Column(Integer, primary_key=True, index=True)
    budget_id = Column(
        Integer, ForeignKey("experiment_budgets.id"), nullable=False, index=True
    )
    trial_id = Column(
        Integer,
        ForeignKey("experiment_trials.id"),
        nullable=False,
        unique=True,
        index=True,
    )
    reserved_at = Column(DateTime, nullable=False, default=utc_now)
    details = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=utc_now)

    budget = relationship("ExperimentBudget", back_populates="reservations")
    trial = relationship("ExperimentTrial")


class WorkerRegistration(Base):
    """Durable worker identity and normalized scheduling capabilities."""

    __tablename__ = "worker_registrations"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(String(255), nullable=False, unique=True, index=True)
    status = Column(String(64), nullable=False, default="active", index=True)
    capabilities = Column(JSON, nullable=False)
    metadata_json = Column(JSON, nullable=True)
    registered_at = Column(DateTime, nullable=False, default=utc_now)
    heartbeat_at = Column(DateTime, nullable=False, default=utc_now)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)


class ExperimentWorkerAttempt(Base):
    """Durable cross-process ownership record for one trial claim."""

    __tablename__ = "experiment_worker_attempts"

    id = Column(Integer, primary_key=True, index=True)
    experiment_id = Column(
        Integer, ForeignKey("experiments.id"), nullable=False, index=True
    )
    trial_id = Column(
        Integer, ForeignKey("experiment_trials.id"), nullable=False, index=True
    )
    owner_id = Column(String(255), nullable=False, index=True)
    lease_token = Column(String(64), nullable=False, unique=True, index=True)
    status = Column(String(64), nullable=False, default="active", index=True)
    acquired_at = Column(DateTime, nullable=False, default=utc_now)
    heartbeat_at = Column(DateTime, nullable=False, default=utc_now)
    expires_at = Column(DateTime, nullable=False, index=True)
    completed_at = Column(DateTime, nullable=True)
    details = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    experiment = relationship("Experiment", back_populates="worker_attempts")
    trial = relationship("ExperimentTrial", back_populates="worker_attempts")


class ExperimentTrial(Base):
    """One planned cell in an experiment matrix."""

    __tablename__ = "experiment_trials"
    __table_args__ = (
        UniqueConstraint(
            "experiment_id",
            "task_id",
            "agent_config_id",
            "repetition",
            name="uq_experiment_trial_cell",
        ),
        UniqueConstraint(
            "experiment_id",
            "ordinal",
            name="uq_experiment_trial_ordinal",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    experiment_id = Column(
        Integer, ForeignKey("experiments.id"), nullable=False, index=True
    )
    task_id = Column(Integer, ForeignKey("benchmark_tasks.id"), nullable=False)
    agent_config_id = Column(Integer, ForeignKey("agent_configs.id"), nullable=False)
    repetition = Column(Integer, nullable=False)
    ordinal = Column(Integer, nullable=False)
    status = Column(String(64), nullable=False, default="planned")
    benchmark_run_id = Column(
        Integer,
        ForeignKey("benchmark_runs.id"),
        nullable=True,
        unique=True,
    )
    error = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    experiment = relationship("Experiment", back_populates="trials")
    task = relationship("BenchmarkTask")
    agent_config = relationship("AgentConfig")
    benchmark_run = relationship("BenchmarkRun")
    worker_attempts = relationship(
        "ExperimentWorkerAttempt",
        back_populates="trial",
        cascade="all, delete-orphan",
        order_by="ExperimentWorkerAttempt.id",
    )
