from __future__ import annotations

from typing import Any
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
import uuid

from api.middleware.auth import api_key_auth
from api.routers.legacy import STORE
from api.middleware.webhooks import webhooks
from core.job_queue import JobQueue
from core.database import Job, JobCandidate, Candidate, AsyncSessionLocal

router = APIRouter()
queue = JobQueue()


@router.get("/jobs/{job_id}/status")
async def get_job_status(job_id: str, request: Request, _: str = Depends(api_key_auth)):
    status = await queue.get_status(job_id)
    return {"request_id": request.state.request_id, "job_id": job_id, **status}


@router.post("/webhooks")
async def register_webhook(payload: dict[str, Any], request: Request, _: str = Depends(api_key_auth)):
    url = payload.get("url", "").strip()
    if not url.startswith("http"):
        raise HTTPException(status_code=400, detail={"error": "invalid_url", "detail": "Webhook url must be http(s)", "field": "url"})
    hook_id = await webhooks.register(url)
    return {"request_id": request.state.request_id, "webhook_id": hook_id, "url": url}


@router.get("/jobs")
async def list_jobs(request: Request, _: str = Depends(api_key_auth)):
    out = []
    async with AsyncSessionLocal() as session:
        res = await session.execute(select(Job).order_by(Job.created_at.desc()))
        jobs = res.scalars().all()
        for j in jobs:
            out.append({
                "id": j.id,
                "role": j.title,
                "dept": j.department,
                "candidates": 0,
                "topMatch": {"name": "--", "score": 0},
                "avgScore": 0,
                "status": j.status,
                "posted": j.created_at.isoformat()
            })
        if out:
            return {"request_id": request.state.request_id, "jobs": out}

    data = STORE.load()
    resumes = data.get("resumes", {})
    for j in sorted(data.get("jobs", {}).values(), key=lambda x: x.get("created_at", ""), reverse=True):
        cid_count = len([r for r in resumes.values() if r.get("job_id") == j.get("job_id")])
        out.append({
            "id": j.get("job_id"),
            "role": (j.get("content", "") or "New Role").split("\n")[0][:80] or "New Role",
            "dept": "",
            "candidates": cid_count,
            "topMatch": {"name": "--", "score": 0},
            "avgScore": 0,
            "status": "ACTIVE",
            "posted": j.get("created_at", ""),
        })
    return {"request_id": request.state.request_id, "jobs": out}


@router.post("/jobs")
async def create_job(body: dict, request: Request, _: str = Depends(api_key_auth)):
    job_id = str(uuid.uuid4())
    async with AsyncSessionLocal() as session:
        new_job = Job(
            id=job_id,
            title=body.get("title", "New Role"),
            department=body.get("department", ""),
            description=body.get("description", "")
        )
        session.add(new_job)
        await session.commit()
    data = STORE.load()
    data["jobs"][job_id] = {
        "job_id": job_id,
        "content": body.get("description", ""),
        "resume_id": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    STORE.save(data)
    return {"request_id": request.state.request_id, "job_id": job_id}


@router.get("/jobs/{job_id}")
async def get_job(job_id: str, request: Request, _: str = Depends(api_key_auth)):
    async with AsyncSessionLocal() as session:
        res = await session.execute(select(Job).where(Job.id == job_id))
        job = res.scalar_one_or_none()
        if job:
            return {"request_id": request.state.request_id, "job": {"id": job.id, "title": job.title, "department": job.department, "description": job.description, "status": job.status}}

    data = STORE.load()
    j = data.get("jobs", {}).get(job_id)
    if not j:
        raise HTTPException(404, "Job not found")
    title = (j.get("content", "") or "New Role").split("\n")[0][:80] or "New Role"
    return {"request_id": request.state.request_id, "job": {"id": job_id, "title": title, "department": "", "description": j.get("content", ""), "status": "ACTIVE"}}


@router.get("/jobs/{job_id}/candidates")
async def get_job_candidates(job_id: str, request: Request, _: str = Depends(api_key_auth)):
    async with AsyncSessionLocal() as session:
        res = await session.execute(
            select(JobCandidate, Candidate)
            .join(Candidate, JobCandidate.candidate_id == Candidate.id)
            .where(JobCandidate.job_id == job_id)
        )
        rows = res.all()
        out = []
        for jc, c in rows:
            out.append({
                "id": c.id,
                "name": c.name or "Unknown",
                "initials": "".join(x[0] for x in (c.name or "U").split()[:2]).upper(),
                "role": "",
                "score": int(jc.match_score),
                "skills": [],
                "column": jc.column_status
            })
        if out:
            return {"request_id": request.state.request_id, "candidates": out}

    data = STORE.load()
    resumes = data.get("resumes", {})
    out = []
    for r in resumes.values():
        if r.get("job_id") == job_id:
            name = (r.get("processed_resume", {}).get("personalInfo", {}) or {}).get("name") or r.get("title") or "Unknown"
            out.append({
                "id": r.get("resume_id"),
                "name": name,
                "initials": "".join(x[0] for x in name.split()[:2]).upper() if name else "U",
                "role": "",
                "score": 80,
                "skills": ((r.get("processed_resume", {}).get("additional", {}) or {}).get("technicalSkills")) or [],
                "column": "MATCHED",
            })
    return {"request_id": request.state.request_id, "candidates": out}
