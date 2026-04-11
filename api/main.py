from __future__ import annotations

import hashlib
import json
import os
import uuid
from typing import Any

import structlog
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from agents.matching_agent import MatchingAgent
from agents.normalization_agent import NormalizationAgent
from agents.orchestrator import PipelineOrchestrator
from agents.parsing_agent import ParsingAgent
from api.middleware.auth import api_key_auth
from api.middleware.rate_limiter import rate_limiter
from api.routers import auth, candidates, jobs, legacy, match, parse, taxonomy
from core.database import AsyncSessionLocal, init_db


structlog.configure(processors=[structlog.processors.JSONRenderer()])
logger = structlog.get_logger(__name__)

app = FastAPI(title="Talent Intelligence API", version="1.0.0")

# Allow environment-specific origins
origins = os.getenv("ALLOWED_ORIGINS", "*").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins if origins != ["*"] else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    request.state.request_id = request_id

    key = request.headers.get("X-API-Key", "")
    if request.url.path.startswith("/api/v1"):
        key_hash = hashlib.sha256(key.encode("utf-8")).hexdigest() if key else "anonymous"
        try:
            await rate_limiter.enforce(key_hash)
        except HTTPException as e:
            return JSONResponse(status_code=e.status_code, content={**e.detail, "request_id": request_id})

    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    err = exc.errors()[0] if exc.errors() else {}
    return JSONResponse(
        status_code=422,
        content={
            "error": "validation_error",
            "detail": err.get("msg", "Invalid request"),
            "field": ".".join(str(x) for x in err.get("loc", [])),
            "request_id": request.state.request_id,
        },
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    detail = exc.detail if isinstance(exc.detail, dict) else {"error": "http_error", "detail": str(exc.detail), "field": ""}
    return JSONResponse(status_code=exc.status_code, content={**detail, "request_id": request.state.request_id})


@app.on_event("startup")
async def startup() -> None:
    try:
        await init_db()
    except Exception as e:
        logger.warning("db_init_failed", error=str(e))

    taxonomy_path = os.getenv("TAXONOMY_PATH", "data/taxonomy/skill_taxonomy.json")
    parser = ParsingAgent(model_path=os.getenv("SPACY_MODEL", "en_core_web_sm"))
    normalizer = NormalizationAgent(taxonomy_path=taxonomy_path, session_factory=AsyncSessionLocal)
    try:
        await normalizer.warmup()
    except Exception as e:
        logger.warning("normalizer_warmup_failed", error=str(e))
    matcher = MatchingAgent()
    orchestrator = PipelineOrchestrator(parser, normalizer, matcher, session_factory=AsyncSessionLocal)

    app.state.parser = parser
    app.state.normalizer = normalizer
    app.state.matcher = matcher
    app.state.orchestrator = orchestrator


app.include_router(auth.router, prefix="/api/v1", tags=["auth"])
app.include_router(parse.router, prefix="/api/v1", tags=["parse"])
app.include_router(candidates.router, prefix="/api/v1", tags=["candidates"])
app.include_router(match.router, prefix="/api/v1", tags=["match"])
app.include_router(taxonomy.router, prefix="/api/v1", tags=["taxonomy"])
app.include_router(jobs.router, prefix="/api/v1", tags=["jobs"])
app.include_router(legacy.router, prefix="/api/v1", tags=["legacy"])


@app.get("/")
async def root(request: Request):
    return {"name": "Talent Intelligence API", "request_id": request.state.request_id}
