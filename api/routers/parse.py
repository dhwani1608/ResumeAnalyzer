from __future__ import annotations

import hashlib
import json
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy import insert

from api.middleware.auth import api_key_auth
from api.routers.legacy import STORE, _extract_resume_data
from core.database import Candidate, NormalizedProfileModel, ParsedResumeModel, AsyncSessionLocal
from core.job_queue import JobQueue


router = APIRouter()
queue = JobQueue()


@router.post("/parse")
async def parse_resume(request: Request, file: UploadFile = File(...), job_id: str = Form(None), _: str = Depends(api_key_auth)):
    raw = await file.read()
    orchestrator = request.app.state.orchestrator
    state = await orchestrator.run(raw_file=raw, file_type=(file.filename or "txt").split(".")[-1])
    parsed = state.get("parsed_resume")
    profile = state.get("normalized_profile")

    if not parsed:
        raise HTTPException(status_code=400, detail={"error": "parse_failed", "detail": "Could not parse resume", "field": "file"})

    file_hash = hashlib.sha256(raw).hexdigest()
    async with AsyncSessionLocal() as session:
        await session.execute(insert(Candidate).values(id=parsed.candidate_id, name=parsed.name, email=parsed.email, raw_text=parsed.raw_text, file_hash=file_hash))
        await session.execute(insert(ParsedResumeModel).values(candidate_id=parsed.candidate_id, parsed_json=parsed.model_dump()))
        if profile:
            await session.execute(
                insert(NormalizedProfileModel).values(
                    candidate_id=parsed.candidate_id,
                    skills_json=profile.model_dump(),
                    implied_skills_json={"implied": profile.implied_skills},
                )
            )
        await session.commit()
    # Persist to shared local store as a fallback for no-DB mode.
    legacy = STORE.load()
    legacy["resumes"][parsed.candidate_id] = {
        "resume_id": parsed.candidate_id,
        "filename": file.filename,
        "is_master": False if legacy["resumes"] else True,
        "parent_id": None,
        "processing_status": "ready",
        "created_at": parsed.model_dump().get("candidate_id", ""),
        "updated_at": parsed.model_dump().get("candidate_id", ""),
        "raw_text": parsed.raw_text,
        "processed_resume": _extract_resume_data(parsed.model_dump()),
        "title": parsed.name or None,
        "cover_letter": None,
        "outreach_message": None,
        "job_id": job_id,
    }
    # Use real timestamps
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    legacy["resumes"][parsed.candidate_id]["created_at"] = now
    legacy["resumes"][parsed.candidate_id]["updated_at"] = now
    STORE.save(legacy)

    return {
        "request_id": request.state.request_id,
        "parsed_resume": parsed.model_dump(),
        "normalized_profile": profile.model_dump() if profile else None,
        "errors": state.get("errors", []),
        "agent_traces": [t.model_dump() for t in state.get("agent_traces", [])],
    }


@router.post("/parse/batch")
async def parse_batch(request: Request, files: list[UploadFile] = File(...), _: str = Depends(api_key_auth)):
    serialized = []
    for f in files:
        raw = await f.read()
        serialized.append({"filename": f.filename, "bytes": raw.hex(), "file_type": (f.filename or "txt").split(".")[-1]})

    job_id = await queue.enqueue({"items": serialized})
    return {"request_id": request.state.request_id, "job_id": job_id, "status": "queued"}
