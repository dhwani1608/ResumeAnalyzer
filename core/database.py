from __future__ import annotations

import os
from datetime import datetime
import importlib.util
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

load_dotenv()

DEFAULT_SQLITE_URL = "sqlite+aiosqlite:///./data/talent_intelligence.db"
DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_SQLITE_URL)

if DATABASE_URL.startswith("sqlite"):
    Path("data").mkdir(parents=True, exist_ok=True)


class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(256), default="")
    email: Mapped[str] = mapped_column(String(256), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Candidate(Base):
    __tablename__ = "candidates"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(256), default="")
    email: Mapped[str] = mapped_column(String(256), default="")
    raw_text: Mapped[str] = mapped_column(Text, default="")
    file_hash: Mapped[str] = mapped_column(String(128), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ParsedResumeModel(Base):
    __tablename__ = "parsed_resumes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    candidate_id: Mapped[str] = mapped_column(ForeignKey("candidates.id"), index=True)
    parsed_json: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class NormalizedProfileModel(Base):
    __tablename__ = "normalized_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    candidate_id: Mapped[str] = mapped_column(ForeignKey("candidates.id"), index=True)
    skills_json: Mapped[dict] = mapped_column(JSON)
    implied_skills_json: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class MatchResultModel(Base):
    __tablename__ = "match_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    candidate_id: Mapped[str] = mapped_column(ForeignKey("candidates.id"), index=True)
    job_description_hash: Mapped[str] = mapped_column(String(128), index=True)
    score: Mapped[float] = mapped_column(Float)
    matched_skills: Mapped[list] = mapped_column(JSON)
    missing_skills: Mapped[list] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    candidate_id: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    parsing_ms: Mapped[int] = mapped_column(Integer, default=0)
    normalization_ms: Mapped[int] = mapped_column(Integer, default=0)
    matching_ms: Mapped[int] = mapped_column(Integer, default=0)
    error_log: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class UnknownSkill(Base):
    __tablename__ = "unknown_skills"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    raw_skill: Mapped[str] = mapped_column(String(256), index=True)
    context: Mapped[str] = mapped_column(Text, default="")
    flagged_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    reviewed: Mapped[bool] = mapped_column(Boolean, default=False)


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key_hash: Mapped[str] = mapped_column(String(256), unique=True, index=True)
    owner: Mapped[str] = mapped_column(String(256), default="")
    rate_limit: Mapped[int] = mapped_column(Integer, default=100)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(256), default="")
    department: Mapped[str] = mapped_column(String(128), default="")
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE")
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class JobCandidate(Base):
    __tablename__ = "job_candidates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), index=True)
    candidate_id: Mapped[str] = mapped_column(ForeignKey("candidates.id"), index=True)
    column_status: Mapped[str] = mapped_column(String(32), default="MATCHED")
    match_score: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class _DummyResult:
    def scalar_one_or_none(self):
        return None

    def scalars(self):
        return self

    def all(self):
        return []


class _DummySession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, *args, **kwargs):
        return _DummyResult()

    async def commit(self):
        return None

    async def rollback(self):
        return None

    async def close(self):
        return None


class _DummySessionMaker:
    def __call__(self):
        return _DummySession()


engine = None
AsyncSessionLocal = _DummySessionMaker()

try:
    engine_kwargs: dict = {"future": True}
    if DATABASE_URL.startswith("sqlite+aiosqlite"):
        if importlib.util.find_spec("aiosqlite") is None:
            raise ModuleNotFoundError("aiosqlite is not installed")
        engine_kwargs["connect_args"] = {"check_same_thread": False}
    engine = create_async_engine(DATABASE_URL, **engine_kwargs)
    AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
except Exception:
    # Keep dummy session maker to allow app startup without DB drivers/services.
    engine = None


async def get_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session


async def init_db() -> None:
    if engine is None:
        return
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
