from __future__ import annotations

import json
import os
import re
import uuid
from typing import Any

import litellm
import spacy

from api.models.resume import Education, ParsedResume, Project, WorkExperience
from parsers import extract_docx_text, extract_pdf_text, extract_text


EMAIL_RE = re.compile(r"[\w\.-]+@[\w\.-]+")
PHONE_RE = re.compile(r"(\+?\d[\d\-\s\(\)]{7,}\d)")


class ParsingAgent:
    def __init__(self, model_path: str = "en_core_web_sm"):
        self.model_path = model_path
        try:
            self.nlp = spacy.load(model_path)
        except Exception:
            self.nlp = spacy.blank("en")
        self.fallback_model = os.getenv("LITELLM_MODEL", "gpt-4o-mini")

    async def parse(self, file_bytes: bytes, file_type: str, candidate_id: str | None = None) -> ParsedResume:
        cid = candidate_id or str(uuid.uuid4())
        raw_text = await self._extract_text(file_bytes, file_type)
        doc = self.nlp(raw_text)

        name = ""
        location = ""
        for ent in doc.ents:
            if not name and ent.label_ in {"PERSON", "PER"}:
                name = ent.text
            if not location and ent.label_ in {"GPE", "LOC"}:
                location = ent.text

        email = EMAIL_RE.findall(raw_text)
        phone = PHONE_RE.findall(raw_text)

        skills = self._extract_skills(raw_text)
        work = self._extract_work_experience(raw_text)
        education = self._extract_education(raw_text)
        certs = self._extract_section_list(raw_text, ["certification", "certifications"])
        projects = self._extract_projects(raw_text)
        publications = self._extract_section_list(raw_text, ["publication", "publications"])
        summary = self._extract_summary(raw_text)

        parsed = ParsedResume(
            candidate_id=cid,
            name=name,
            email=email[0] if email else "",
            phone=phone[0] if phone else "",
            location=location,
            summary=summary,
            work_experience=work,
            education=education,
            skills=skills,
            certifications=certs,
            projects=projects,
            publications=publications,
            raw_text=raw_text,
        )

        if not parsed.name or (not parsed.skills and len(raw_text) > 300):
            llm_patch = await self._llm_fallback(raw_text)
            parsed = parsed.model_copy(update=llm_patch)

        if not parsed.name:
            lines = [ln.strip() for ln in raw_text.splitlines() if ln.strip() and len(ln.strip()) > 3]
            if lines:
                parsed = parsed.model_copy(update={"name": lines[0][:50]})

        return parsed

    async def _extract_text(self, file_bytes: bytes, file_type: str) -> str:
        ft = file_type.lower().strip(".")
        if ft == "pdf":
            return await extract_pdf_text(file_bytes)
        if ft in {"doc", "docx"}:
            return await extract_docx_text(file_bytes)
        return await extract_text(file_bytes)

    def _extract_summary(self, raw_text: str) -> str:
        lines = [ln.strip() for ln in raw_text.splitlines() if ln.strip()]
        return " ".join(lines[:4])[:1200]

    def _extract_section(self, raw_text: str, headings: list[str]) -> str:
        lines = raw_text.splitlines()
        in_section = False
        buf: list[str] = []
        for line in lines:
            norm = line.strip().lower()
            if any(h in norm for h in headings):
                in_section = True
                continue
            if in_section and re.match(r"^[A-Z][A-Za-z\s]{2,30}$", line.strip()):
                break
            if in_section:
                buf.append(line)
        return "\n".join(buf).strip()

    def _extract_section_list(self, raw_text: str, headings: list[str]) -> list[str]:
        sec = self._extract_section(raw_text, headings)
        return [s.strip("-* ") for s in sec.splitlines() if s.strip()]

    def _extract_skills(self, raw_text: str) -> list[str]:
        sec = self._extract_section(raw_text, ["skills", "technical skills", "core competencies"])
        if not sec:
            sec = raw_text[:3000]
        tokens = re.split(r"[,\n|/]+", sec)
        cleaned = [t.strip(" -*\t") for t in tokens if 1 < len(t.strip()) < 50]
        return list(dict.fromkeys(cleaned))[:120]

    def _extract_work_experience(self, raw_text: str) -> list[WorkExperience]:
        sec = self._extract_section(raw_text, ["experience", "work experience", "employment"])
        out: list[WorkExperience] = []
        for line in sec.splitlines()[:30]:
            if len(line.strip()) < 6:
                continue
            out.append(WorkExperience(title=line.strip()))
        return out[:20]

    def _extract_education(self, raw_text: str) -> list[Education]:
        sec = self._extract_section(raw_text, ["education", "academic background"])
        out: list[Education] = []
        for line in sec.splitlines()[:20]:
            if len(line.strip()) < 6:
                continue
            out.append(Education(degree=line.strip()))
        return out[:10]

    def _extract_projects(self, raw_text: str) -> list[Project]:
        sec = self._extract_section(raw_text, ["projects", "personal projects"])
        out: list[Project] = []
        for line in sec.splitlines()[:20]:
            if len(line.strip()) < 6:
                continue
            out.append(Project(name=line.strip()))
        return out[:10]

    async def _llm_fallback(self, text: str) -> dict[str, Any]:
        prompt = (
            "Extract resume JSON with keys: name,email,phone,location,skills,summary."
            " Return strict JSON only."
        )
        try:
            response = await litellm.acompletion(
                model=self.fallback_model,
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": text[:12000]},
                ],
                temperature=0,
            )
            content = response.choices[0].message.content
            if "```json" in content:
                content = content.split("```json")[-1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[-1].split("```")[0]
            data = json.loads(content.strip())
            if not isinstance(data, dict):
                return {}
            return data
        except Exception:
            return {}
