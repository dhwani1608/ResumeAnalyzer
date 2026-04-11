from __future__ import annotations

import hashlib

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import insert, select

from api.middleware.auth import api_key_auth
from api.models.resume import JobDescription
from core.database import MatchResultModel, NormalizedProfileModel, AsyncSessionLocal


router = APIRouter()


@router.post("/match")
async def match_candidate(body: dict, request: Request, _: str = Depends(api_key_auth)):
    candidate_id = body.get("candidate_id")
    job_text = body.get("job_description", "")
    if not candidate_id or not job_text:
        raise HTTPException(status_code=400, detail={"error": "bad_request", "detail": "candidate_id and job_description are required", "field": "body"})

    async with AsyncSessionLocal() as session:
        res = await session.execute(
            select(NormalizedProfileModel).where(NormalizedProfileModel.candidate_id == candidate_id).order_by(NormalizedProfileModel.id.desc())
        )
        row = res.scalar_one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail={"error": "not_found", "detail": "Candidate profile not found", "field": "candidate_id"})

    normalized = row.skills_json
    from api.models.resume import NormalizedProfile

    profile_model = NormalizedProfile(**normalized)

    jd = JobDescription(
        description=job_text,
        required_skills=body.get("required_skills", []),
        nice_to_have_skills=body.get("nice_to_have_skills", []),
        min_years_experience=float(body.get("min_years_experience", 0)),
    )
    result = await request.app.state.matcher.match(profile_model, jd)

    async with AsyncSessionLocal() as session:
        await session.execute(
            insert(MatchResultModel).values(
                candidate_id=candidate_id,
                job_description_hash=hashlib.sha256(job_text.encode("utf-8")).hexdigest(),
                score=result.score,
                matched_skills=result.matched_skills,
                missing_skills=result.missing_skills,
            )
        )
        await session.commit()

    return {"request_id": request.state.request_id, "match_result": result.model_dump()}
