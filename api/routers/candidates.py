from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select

from api.middleware.auth import api_key_auth
from api.routers.legacy import STORE
from core.database import NormalizedProfileModel, Candidate, AsyncSessionLocal


router = APIRouter()

@router.get("/candidates")
async def list_candidates(request: Request, _: str = Depends(api_key_auth)):
    async with AsyncSessionLocal() as session:
        res = await session.execute(select(Candidate).order_by(Candidate.created_at.desc()))
        candidates = res.scalars().all()
        out = []
        for c in candidates:
            out.append({
                "id": c.id,
                "name": c.name or "Unknown",
                "email": c.email or "",
                "created_at": c.created_at.isoformat()
            })
        if out:
            return {"request_id": request.state.request_id, "candidates": out}

    # Fallback for local no-DB mode
    data = STORE.load()
    for r in sorted(data.get("resumes", {}).values(), key=lambda x: x.get("created_at", ""), reverse=True):
        out.append({
            "id": r.get("resume_id"),
            "name": (r.get("processed_resume", {}).get("personalInfo", {}) or {}).get("name") or r.get("title") or "Unknown",
            "email": "",
            "created_at": r.get("created_at", "")
        })
    return {"request_id": request.state.request_id, "candidates": out}

@router.get("/candidates/{candidate_id}")
async def get_candidate(candidate_id: str, request: Request, _: str = Depends(api_key_auth)):
    async with AsyncSessionLocal() as session:
        res = await session.execute(select(Candidate).where(Candidate.id == candidate_id))
        c = res.scalar_one_or_none()
        if c:
            return {"request_id": request.state.request_id, "candidate": {"id": c.id, "name": c.name, "email": c.email, "raw_text": c.raw_text, "created_at": c.created_at.isoformat()}}

    data = STORE.load()
    rec = data.get("resumes", {}).get(candidate_id)
    if not rec:
        raise HTTPException(404, "Candidate not found")
    return {
        "request_id": request.state.request_id,
        "candidate": {
            "id": rec.get("resume_id"),
            "name": (rec.get("processed_resume", {}).get("personalInfo", {}) or {}).get("name") or "Unknown",
            "email": "",
            "raw_text": rec.get("raw_text", ""),
            "created_at": rec.get("created_at", ""),
        },
    }


@router.get("/candidates/{candidate_id}/skills")
async def candidate_skills(candidate_id: str, request: Request, _: str = Depends(api_key_auth)):
    async with AsyncSessionLocal() as session:
        res = await session.execute(
            select(NormalizedProfileModel).where(NormalizedProfileModel.candidate_id == candidate_id).order_by(NormalizedProfileModel.id.desc())
        )
        row = res.scalar_one_or_none()
        if row:
            payload = row.skills_json or {}
            skills = [s.get("skill", {}).get("canonical", "") for s in payload.get("normalized_skills", []) if s.get("skill")]
            return {
                "request_id": request.state.request_id,
                "candidate_id": candidate_id,
                "skills": skills,
                "implied_skills": payload.get("implied_skills", []),
            }

    # Fallback for local no-DB mode
    data = STORE.load()
    rec = data.get("resumes", {}).get(candidate_id)
    if not rec:
        raise HTTPException(status_code=404, detail={"error": "not_found", "detail": "Candidate profile not found", "field": "candidate_id"})
    skills = ((rec.get("processed_resume", {}).get("additional", {}) or {}).get("technicalSkills")) or []
    return {
        "request_id": request.state.request_id,
        "candidate_id": candidate_id,
        "skills": skills,
        "implied_skills": [],
    }
