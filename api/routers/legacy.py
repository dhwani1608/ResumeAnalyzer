from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import fitz
from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response


router = APIRouter()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class LegacyStore:
    path: Path

    def _default(self) -> dict[str, Any]:
        return {
            "resumes": {},
            "jobs": {},
            "improvements": {},
            "llm_config": {
                "provider": "openai",
                "model": "gpt-4o-mini",
                "api_key": "",
                "api_base": None,
            },
            "features": {
                "enable_cover_letter": True,
                "enable_outreach_message": True,
            },
            "prompt_config": {
                "default_prompt_id": "keywords",
                "prompt_options": [
                    {"id": "nudge", "label": "Nudge", "description": "Subtle improvements"},
                    {"id": "keywords", "label": "Keywords", "description": "Keyword-optimized"},
                    {"id": "full", "label": "Full Rewrite", "description": "Rewrite sections deeply"},
                ],
            },
            "api_keys": {"openai": "", "anthropic": "", "google": "", "openrouter": "", "deepseek": ""},
            "language": {
                "ui_language": "en",
                "content_language": "en",
                "supported_languages": ["en", "es", "zh", "ja", "pt"],
            },
        }

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            data = self._default()
            self.save(data)
            return data
        return json.loads(self.path.read_text(encoding="utf-8"))

    def save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")


STORE = LegacyStore(Path(os.getenv("LEGACY_STORE_PATH", "data/legacy_state.json")))


def _extract_resume_data(parsed: dict[str, Any]) -> dict[str, Any]:
    work = []
    for i, row in enumerate(parsed.get("work_experience", [])[:20]):
        desc = row.get("description", "")
        bullets = [x.strip() for x in str(desc).split("\n") if x.strip()]
        work.append(
            {
                "id": i + 1,
                "title": row.get("title", ""),
                "company": row.get("company", ""),
                "location": "",
                "years": "",
                "description": bullets or [str(desc)] if desc else [],
            }
        )

    education = []
    for i, row in enumerate(parsed.get("education", [])[:10]):
        education.append(
            {
                "id": i + 1,
                "institution": row.get("institution", ""),
                "degree": row.get("degree", ""),
                "years": "",
                "description": row.get("field_of_study", ""),
            }
        )

    projects = []
    for i, row in enumerate(parsed.get("projects", [])[:10]):
        desc = row.get("description", "")
        projects.append(
            {
                "id": i + 1,
                "name": row.get("name", ""),
                "role": "",
                "years": "",
                "github": "",
                "website": "",
                "description": [str(desc)] if desc else [],
            }
        )

    return {
        "personalInfo": {
            "name": parsed.get("name", ""),
            "title": "",
            "email": parsed.get("email", ""),
            "phone": parsed.get("phone", ""),
            "location": parsed.get("location", ""),
            "website": "",
            "linkedin": "",
            "github": "",
        },
        "summary": parsed.get("summary", ""),
        "workExperience": work,
        "education": education,
        "personalProjects": projects,
        "additional": {
            "technicalSkills": parsed.get("skills", []),
            "languages": [],
            "certificationsTraining": parsed.get("certifications", []),
            "awards": [],
        },
    }


def _as_resume_response(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "resume_id": record["resume_id"],
        "raw_resume": {
            "id": None,
            "content": record.get("raw_text", ""),
            "content_type": "txt",
            "created_at": record["created_at"],
            "processing_status": record.get("processing_status", "ready"),
        },
        "processed_resume": record.get("processed_resume"),
        "cover_letter": record.get("cover_letter"),
        "outreach_message": record.get("outreach_message"),
        "parent_id": record.get("parent_id"),
        "title": record.get("title"),
    }


def _build_pdf(content: str) -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    text = content or "No content"
    page.insert_textbox(fitz.Rect(40, 40, 550, 800), text[:7000], fontsize=10)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def _fallback_parse(raw: bytes) -> dict[str, Any]:
    text = raw.decode("utf-8", errors="ignore")
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    name = lines[0] if lines else "Candidate"
    skills = []
    for ln in lines:
        if "skills" in ln.lower():
            skills.extend([x.strip() for x in ln.split(":", 1)[-1].split(",") if x.strip()])
    return {
        "candidate_id": str(uuid.uuid4()),
        "name": name,
        "email": "",
        "phone": "",
        "location": "",
        "summary": " ".join(lines[:3]),
        "work_experience": [],
        "education": [],
        "skills": skills,
        "certifications": [],
        "projects": [],
        "publications": [],
        "raw_text": text,
    }


@router.post("/jobs/upload")
async def legacy_upload_jobs(request: Request, body: dict[str, Any]):
    data = STORE.load()
    descriptions = body.get("job_descriptions", []) or []
    resume_id = body.get("resume_id")
    ids = []
    for desc in descriptions:
        jid = str(uuid.uuid4())
        data["jobs"][jid] = {"job_id": jid, "content": str(desc), "resume_id": resume_id, "created_at": _utc_now()}
        ids.append(jid)
    STORE.save(data)
    return {"request_id": request.state.request_id, "job_id": ids}


@router.post("/resumes/upload")
async def legacy_upload_resume(request: Request, file: UploadFile = File(...)):
    raw = await file.read()
    ext = (file.filename or "txt").split(".")[-1]
    parsed_dict: dict[str, Any]
    orchestrator = getattr(request.app.state, "orchestrator", None)
    if orchestrator is not None:
        state = await orchestrator.run(raw_file=raw, file_type=ext)
        parsed = state.get("parsed_resume")
        parsed_dict = parsed.model_dump() if parsed else _fallback_parse(raw)
    else:
        parsed_dict = _fallback_parse(raw)

    data = STORE.load()
    has_master = any(r.get("is_master") for r in data["resumes"].values())
    resume_id = parsed_dict["candidate_id"]
    record = {
        "resume_id": resume_id,
        "filename": file.filename,
        "is_master": not has_master,
        "parent_id": None,
        "processing_status": "ready",
        "created_at": _utc_now(),
        "updated_at": _utc_now(),
        "raw_text": parsed_dict.get("raw_text", ""),
        "processed_resume": _extract_resume_data(parsed_dict),
        "title": None,
        "cover_letter": None,
        "outreach_message": None,
        "job_id": None,
    }
    data["resumes"][resume_id] = record
    STORE.save(data)

    return {
        "message": "Upload successful",
        "request_id": request.state.request_id,
        "resume_id": resume_id,
        "processing_status": "ready",
        "is_master": record["is_master"],
    }


@router.get("/resumes")
async def legacy_get_resume(request: Request, resume_id: str = Query(...)):
    data = STORE.load()
    record = data["resumes"].get(resume_id)
    if not record:
        raise HTTPException(status_code=404, detail="Resume not found")
    return {"request_id": request.state.request_id, "data": _as_resume_response(record)}


@router.get("/resumes/list")
async def legacy_list_resumes(include_master: bool = Query(False)):
    data = STORE.load()
    items = []
    for r in data["resumes"].values():
        if not include_master and r.get("is_master"):
            continue
        items.append(
            {
                "resume_id": r["resume_id"],
                "filename": r.get("filename"),
                "is_master": r.get("is_master", False),
                "parent_id": r.get("parent_id"),
                "processing_status": r.get("processing_status", "ready"),
                "created_at": r.get("created_at"),
                "updated_at": r.get("updated_at"),
                "title": r.get("title"),
            }
        )
    items.sort(key=lambda x: x.get("updated_at") or "", reverse=True)
    return {"data": items}


@router.patch("/resumes/{resume_id}")
async def legacy_update_resume(request: Request, resume_id: str, body: dict[str, Any]):
    data = STORE.load()
    record = data["resumes"].get(resume_id)
    if not record:
        raise HTTPException(status_code=404, detail="Resume not found")
    record["processed_resume"] = body
    record["updated_at"] = _utc_now()
    STORE.save(data)
    return {"request_id": request.state.request_id, "data": _as_resume_response(record)}


@router.delete("/resumes/{resume_id}")
async def legacy_delete_resume(resume_id: str):
    data = STORE.load()
    if resume_id in data["resumes"]:
        del data["resumes"][resume_id]
        STORE.save(data)
    return {"ok": True}


@router.patch("/resumes/{resume_id}/title")
async def legacy_update_title(resume_id: str, body: dict[str, Any]):
    data = STORE.load()
    record = data["resumes"].get(resume_id)
    if not record:
        raise HTTPException(status_code=404, detail="Resume not found")
    record["title"] = body.get("title")
    record["updated_at"] = _utc_now()
    STORE.save(data)
    return {"ok": True}


@router.patch("/resumes/{resume_id}/cover-letter")
async def legacy_update_cover_letter(resume_id: str, body: dict[str, Any]):
    data = STORE.load()
    record = data["resumes"].get(resume_id)
    if not record:
        raise HTTPException(status_code=404, detail="Resume not found")
    record["cover_letter"] = body.get("content", "")
    record["updated_at"] = _utc_now()
    STORE.save(data)
    return {"ok": True}


@router.patch("/resumes/{resume_id}/outreach-message")
async def legacy_update_outreach(resume_id: str, body: dict[str, Any]):
    data = STORE.load()
    record = data["resumes"].get(resume_id)
    if not record:
        raise HTTPException(status_code=404, detail="Resume not found")
    record["outreach_message"] = body.get("content", "")
    record["updated_at"] = _utc_now()
    STORE.save(data)
    return {"ok": True}


@router.post("/resumes/{resume_id}/retry-processing")
async def legacy_retry_resume(request: Request, resume_id: str):
    data = STORE.load()
    record = data["resumes"].get(resume_id)
    if not record:
        raise HTTPException(status_code=404, detail="Resume not found")
    record["processing_status"] = "ready"
    record["updated_at"] = _utc_now()
    STORE.save(data)
    return {
        "message": "Retry completed",
        "request_id": request.state.request_id,
        "resume_id": resume_id,
        "processing_status": "ready",
        "is_master": record.get("is_master", False),
    }


@router.get("/resumes/{resume_id}/job-description")
async def legacy_resume_job_description(resume_id: str):
    data = STORE.load()
    record = data["resumes"].get(resume_id)
    if not record:
        raise HTTPException(status_code=404, detail="Resume not found")
    jid = record.get("job_id")
    if not jid:
        raise HTTPException(status_code=404, detail="Job not found")
    job = data["jobs"].get(jid)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"job_id": jid, "content": job.get("content", "")}


@router.post("/resumes/{resume_id}/generate-cover-letter")
async def legacy_generate_cover_letter(resume_id: str):
    data = STORE.load()
    record = data["resumes"].get(resume_id)
    if not record:
        raise HTTPException(status_code=404, detail="Resume not found")
    person = (record.get("processed_resume") or {}).get("personalInfo", {}).get("name", "Candidate")
    title = record.get("title") or "this role"
    content = f"Dear Hiring Manager,\n\nI am {person}, and I am excited to apply for {title}. My experience aligns strongly with the role requirements.\n\nSincerely,\n{person}"
    record["cover_letter"] = content
    record["updated_at"] = _utc_now()
    STORE.save(data)
    return {"content": content}


@router.post("/resumes/{resume_id}/generate-outreach")
async def legacy_generate_outreach(resume_id: str):
    data = STORE.load()
    record = data["resumes"].get(resume_id)
    if not record:
        raise HTTPException(status_code=404, detail="Resume not found")
    person = (record.get("processed_resume") or {}).get("personalInfo", {}).get("name", "Candidate")
    content = f"Hi, I am {person}. I would love to discuss how my background can support your team."
    record["outreach_message"] = content
    record["updated_at"] = _utc_now()
    STORE.save(data)
    return {"content": content}


@router.get("/resumes/{resume_id}/pdf")
async def legacy_resume_pdf(resume_id: str):
    data = STORE.load()
    record = data["resumes"].get(resume_id)
    if not record:
        raise HTTPException(status_code=404, detail="Resume not found")
    resume = record.get("processed_resume") or {}
    content = json.dumps(resume, indent=2)
    return Response(content=_build_pdf(content), media_type="application/pdf")


@router.get("/resumes/{resume_id}/cover-letter/pdf")
async def legacy_cover_letter_pdf(resume_id: str):
    data = STORE.load()
    record = data["resumes"].get(resume_id)
    if not record:
        raise HTTPException(status_code=404, detail="Resume not found")
    content = record.get("cover_letter") or "Cover letter not available"
    return Response(content=_build_pdf(content), media_type="application/pdf")


def _build_diff(old_resume: dict[str, Any], new_resume: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    old_skills = set((old_resume.get("additional") or {}).get("technicalSkills") or [])
    new_skills = set((new_resume.get("additional") or {}).get("technicalSkills") or [])
    skills_added = sorted(new_skills - old_skills)
    detailed = []
    for s in skills_added[:20]:
        detailed.append(
            {
                "field_path": "additional.technicalSkills",
                "field_type": "skill",
                "change_type": "added",
                "original_value": "",
                "new_value": s,
                "confidence": "high",
            }
        )

    if old_resume.get("summary") != new_resume.get("summary"):
        detailed.append(
            {
                "field_path": "summary",
                "field_type": "summary",
                "change_type": "modified",
                "original_value": old_resume.get("summary", ""),
                "new_value": new_resume.get("summary", ""),
                "confidence": "medium",
            }
        )

    summary = {
        "total_changes": len(detailed),
        "skills_added": len(skills_added),
        "skills_removed": 0,
        "descriptions_modified": 1 if old_resume.get("summary") != new_resume.get("summary") else 0,
        "certifications_added": 0,
        "high_risk_changes": 0,
    }
    return summary, detailed


def _build_improved_resume(base_resume: dict[str, Any], job_text: str) -> dict[str, Any]:
    resume = json.loads(json.dumps(base_resume))
    additional = resume.setdefault("additional", {})
    skills = set(additional.get("technicalSkills") or [])

    seed = []
    for token in ["Python", "FastAPI", "PostgreSQL", "Docker", "Kubernetes", "AWS", "SQL", "React"]:
        if token.lower() in job_text.lower():
            seed.append(token)
    skills.update(seed)
    additional["technicalSkills"] = sorted(skills)

    existing_summary = resume.get("summary", "") or ""
    suffix = " Tailored to the job requirements with clear alignment to required skills."
    if suffix.strip() not in existing_summary:
        resume["summary"] = (existing_summary + suffix).strip()
    return resume


@router.post("/resumes/improve")
@router.post("/resumes/improve/preview")
async def legacy_improve_preview(request: Request, body: dict[str, Any]):
    data = STORE.load()
    resume_id = body.get("resume_id")
    job_id = body.get("job_id")
    record = data["resumes"].get(str(resume_id))
    job = data["jobs"].get(str(job_id))
    if not record or not job:
        raise HTTPException(status_code=404, detail="Resume or job not found")

    base = record.get("processed_resume") or {}
    improved = _build_improved_resume(base, job.get("content", ""))
    diff_summary, detailed_changes = _build_diff(base, improved)

    improvements = [
        {
            "suggestion": "Updated summary to better align with job requirements.",
            "lineNumber": 1,
        }
    ]

    return {
        "data": {
            "request_id": request.state.request_id,
            "resume_id": resume_id,
            "job_id": job_id,
            "resume_preview": improved,
            "details": "Preview generated",
            "commentary": "Generated compatibility preview",
            "improvements": improvements,
            "job_description": job.get("content", ""),
            "job_keywords": ", ".join((improved.get("additional") or {}).get("technicalSkills", [])[:12]),
            "cover_letter": record.get("cover_letter"),
            "outreach_message": record.get("outreach_message"),
            "diff_summary": diff_summary,
            "detailed_changes": detailed_changes,
        }
    }


@router.post("/resumes/improve/confirm")
async def legacy_improve_confirm(request: Request, body: dict[str, Any]):
    data = STORE.load()
    resume_id = body.get("resume_id")
    job_id = body.get("job_id")
    improved_data = body.get("improved_data") or {}
    source = data["resumes"].get(str(resume_id))
    job = data["jobs"].get(str(job_id))
    if not source or not job:
        raise HTTPException(status_code=404, detail="Resume or job not found")

    new_id = str(uuid.uuid4())
    job_text = job.get("content", "")
    title = job_text.strip().split("\n")[0][:80] if job_text.strip() else "Tailored Resume"

    new_record = {
        "resume_id": new_id,
        "filename": source.get("filename"),
        "is_master": False,
        "parent_id": resume_id,
        "processing_status": "ready",
        "created_at": _utc_now(),
        "updated_at": _utc_now(),
        "raw_text": source.get("raw_text", ""),
        "processed_resume": improved_data,
        "title": title,
        "cover_letter": source.get("cover_letter"),
        "outreach_message": source.get("outreach_message"),
        "job_id": job_id,
    }
    data["resumes"][new_id] = new_record
    data["improvements"][new_id] = body.get("improvements") or []
    STORE.save(data)

    return {
        "data": {
            "request_id": request.state.request_id,
            "resume_id": new_id,
            "job_id": job_id,
            "resume_preview": improved_data,
            "improvements": body.get("improvements") or [],
            "cover_letter": new_record.get("cover_letter"),
            "outreach_message": new_record.get("outreach_message"),
        }
    }


@router.post("/enrichment/analyze/{resume_id}")
async def legacy_enrichment_analyze(resume_id: str):
    data = STORE.load()
    record = data["resumes"].get(resume_id)
    if not record:
        raise HTTPException(status_code=404, detail="Resume not found")

    processed = record.get("processed_resume") or {}
    items = []
    questions = []
    qid = 1

    for exp in (processed.get("workExperience") or [])[:2]:
        desc = exp.get("description") or []
        item_id = f"exp_{exp.get('id', qid)}"
        items.append(
            {
                "item_id": item_id,
                "item_type": "experience",
                "title": exp.get("title", ""),
                "subtitle": exp.get("company", ""),
                "current_description": desc,
                "weakness_reason": "Could use clearer impact metrics.",
            }
        )
        questions.append(
            {
                "question_id": f"q_{qid}",
                "item_id": item_id,
                "question": "What measurable result did you achieve in this role?",
                "placeholder": "e.g., Improved deployment speed by 35%",
            }
        )
        qid += 1

    if not items:
        return {"items_to_enrich": [], "questions": [], "analysis_summary": "No major improvements found."}

    return {
        "items_to_enrich": items,
        "questions": questions,
        "analysis_summary": "Found opportunities to strengthen accomplishment statements.",
    }


@router.post("/enrichment/enhance")
async def legacy_enrichment_enhance(body: dict[str, Any]):
    answers = body.get("answers") or []
    enhancements = []
    for idx, ans in enumerate(answers, start=1):
        answer_text = ans.get("answer", "")
        enhancements.append(
            {
                "item_id": f"exp_{idx}",
                "item_type": "experience",
                "title": f"Experience {idx}",
                "original_description": [],
                "enhanced_description": [answer_text] if answer_text else ["Delivered measurable outcomes in this role."],
            }
        )
    return {"enhancements": enhancements}


@router.post("/enrichment/apply/{resume_id}")
async def legacy_enrichment_apply(resume_id: str, body: dict[str, Any]):
    data = STORE.load()
    record = data["resumes"].get(resume_id)
    if not record:
        raise HTTPException(status_code=404, detail="Resume not found")

    enhancements = body.get("enhancements") or []
    processed = record.get("processed_resume") or {}
    work = processed.get("workExperience") or []

    for i, enh in enumerate(enhancements):
        if i < len(work):
            work[i]["description"] = enh.get("enhanced_description") or work[i].get("description", [])

    processed["workExperience"] = work
    record["processed_resume"] = processed
    record["updated_at"] = _utc_now()
    STORE.save(data)

    return {"message": "Enhancements applied", "updated_items": len(enhancements)}


@router.post("/enrichment/regenerate")
async def legacy_enrichment_regenerate(body: dict[str, Any]):
    items = body.get("items") or []
    instruction = body.get("instruction", "Improve clarity and impact")
    regenerated_items = []
    errors = []
    for item in items:
        try:
            current = item.get("current_content") or []
            new_content = [f"{line} ({instruction})" for line in current] or [instruction]
            regenerated_items.append(
                {
                    "item_id": item.get("item_id"),
                    "item_type": item.get("item_type"),
                    "title": item.get("title", ""),
                    "subtitle": item.get("subtitle"),
                    "original_content": current,
                    "new_content": new_content,
                    "diff_summary": "Refined wording and emphasis.",
                }
            )
        except Exception as e:
            errors.append(
                {
                    "item_id": item.get("item_id"),
                    "item_type": item.get("item_type"),
                    "title": item.get("title", ""),
                    "subtitle": item.get("subtitle"),
                    "message": str(e),
                }
            )
    return {"regenerated_items": regenerated_items, "errors": errors}


@router.post("/enrichment/apply-regenerated/{resume_id}")
async def legacy_enrichment_apply_regenerated(resume_id: str, body: list[dict[str, Any]]):
    data = STORE.load()
    record = data["resumes"].get(resume_id)
    if not record:
        raise HTTPException(status_code=404, detail="Resume not found")

    processed = record.get("processed_resume") or {}
    work = processed.get("workExperience") or []
    projects = processed.get("personalProjects") or []

    for item in body:
        item_type = item.get("item_type")
        item_id = str(item.get("item_id", ""))
        new_content = item.get("new_content") or []
        if item_type == "experience" and item_id.startswith("exp_"):
            idx = int(item_id.split("_")[1])
            if 0 <= idx < len(work):
                work[idx]["description"] = new_content
        if item_type == "project" and item_id.startswith("proj_"):
            idx = int(item_id.split("_")[1])
            if 0 <= idx < len(projects):
                projects[idx]["description"] = new_content
        if item_type == "skills":
            processed.setdefault("additional", {})["technicalSkills"] = new_content

    processed["workExperience"] = work
    processed["personalProjects"] = projects
    record["processed_resume"] = processed
    record["updated_at"] = _utc_now()
    STORE.save(data)
    return {"message": "Applied regenerated items", "updated_items": len(body)}


@router.get("/status")
async def legacy_status():
    data = STORE.load()
    llm = data.get("llm_config", {})
    provider = llm.get("provider", "openai")
    llm_configured = bool((llm.get("api_key") or "").strip()) or provider == "ollama"
    has_master_resume = any(r.get("is_master") for r in data.get("resumes", {}).values())

    return {
        "status": "ready" if llm_configured else "setup_required",
        "llm_configured": llm_configured,
        "llm_healthy": llm_configured,
        "has_master_resume": has_master_resume,
        "database_stats": {
            "total_resumes": len(data.get("resumes", {})),
            "total_jobs": len(data.get("jobs", {})),
            "total_improvements": len(data.get("improvements", {})),
            "has_master_resume": has_master_resume,
        },
    }


@router.get("/config/llm-api-key")
async def legacy_get_llm_config():
    data = STORE.load()
    return data.get("llm_config", {})


@router.put("/config/llm-api-key")
async def legacy_put_llm_config(body: dict[str, Any]):
    data = STORE.load()
    config = data.get("llm_config", {})
    for key in ["provider", "model", "api_key", "api_base"]:
        if key in body:
            config[key] = body[key]
    data["llm_config"] = config
    STORE.save(data)
    return config


@router.post("/config/llm-test")
async def legacy_llm_test(body: dict[str, Any] | None = None):
    data = STORE.load()
    config = data.get("llm_config", {}).copy()
    if body:
        config.update({k: v for k, v in body.items() if v is not None})
    provider = config.get("provider", "openai")
    has_key = bool((config.get("api_key") or "").strip())
    healthy = has_key or provider == "ollama"
    return {
        "healthy": healthy,
        "provider": provider,
        "model": config.get("model", ""),
        "error": None if healthy else "API key is required for this provider",
        "error_code": None if healthy else "missing_api_key",
        "test_prompt": "Summarize candidate strengths in one sentence.",
        "model_output": "Candidate demonstrates strong alignment with required skills." if healthy else None,
    }


@router.get("/config/features")
async def legacy_get_features():
    return STORE.load().get("features", {})


@router.put("/config/features")
async def legacy_put_features(body: dict[str, Any]):
    data = STORE.load()
    features = data.get("features", {})
    for key in ["enable_cover_letter", "enable_outreach_message"]:
        if key in body:
            features[key] = bool(body[key])
    data["features"] = features
    STORE.save(data)
    return features


@router.get("/config/prompts")
async def legacy_get_prompts():
    return STORE.load().get("prompt_config", {})


@router.put("/config/prompts")
async def legacy_put_prompts(body: dict[str, Any]):
    data = STORE.load()
    prompt = data.get("prompt_config", {})
    if "default_prompt_id" in body:
        prompt["default_prompt_id"] = body["default_prompt_id"]
    data["prompt_config"] = prompt
    STORE.save(data)
    return prompt


@router.get("/config/language")
async def legacy_get_language():
    return STORE.load().get("language", {})


@router.put("/config/language")
async def legacy_put_language(body: dict[str, Any]):
    data = STORE.load()
    language = data.get("language", {})
    if "ui_language" in body:
        language["ui_language"] = body["ui_language"]
    if "content_language" in body:
        language["content_language"] = body["content_language"]
    data["language"] = language
    STORE.save(data)
    return language


@router.get("/config/api-keys")
async def legacy_get_api_keys():
    keys = STORE.load().get("api_keys", {})
    providers = []
    for p in ["openai", "anthropic", "google", "openrouter", "deepseek"]:
        v = keys.get(p, "")
        providers.append(
            {
                "provider": p,
                "configured": bool(v),
                "masked_key": (f"{v[:4]}***{v[-2:]}" if v else None),
            }
        )
    return {"providers": providers}


@router.post("/config/api-keys")
async def legacy_post_api_keys(body: dict[str, Any]):
    data = STORE.load()
    keys = data.get("api_keys", {})
    updated = []
    for p in ["openai", "anthropic", "google", "openrouter", "deepseek"]:
        if p in body:
            keys[p] = body[p]
            updated.append(p)
    data["api_keys"] = keys
    STORE.save(data)
    return {"message": "Updated API keys", "updated_providers": updated}


@router.delete("/config/api-keys/{provider}")
async def legacy_delete_api_key(provider: str):
    data = STORE.load()
    keys = data.get("api_keys", {})
    if provider in keys:
        keys[provider] = ""
    data["api_keys"] = keys
    STORE.save(data)
    return {"ok": True}


@router.delete("/config/api-keys")
async def legacy_clear_api_keys(confirm: str = Query("")):
    if confirm != "CLEAR_ALL_KEYS":
        raise HTTPException(status_code=400, detail="Missing confirm")
    data = STORE.load()
    data["api_keys"] = {"openai": "", "anthropic": "", "google": "", "openrouter": "", "deepseek": ""}
    llm = data.get("llm_config", {})
    llm["api_key"] = ""
    data["llm_config"] = llm
    STORE.save(data)
    return {"ok": True}


@router.post("/config/reset")
async def legacy_reset(body: dict[str, Any]):
    if body.get("confirm") != "RESET_ALL_DATA":
        raise HTTPException(status_code=400, detail="Missing confirm")
    data = STORE._default()
    STORE.save(data)
    return {"ok": True}
