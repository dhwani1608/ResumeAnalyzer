from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Dict, List

from rapidfuzz import fuzz
from sqlalchemy import insert

from api.models.resume import CanonicalSkill, NormalizedProfile, NormalizedSkill
from core.database import UnknownSkill
from core.vector_store import VectorStore


class NormalizationAgent:
    def __init__(self, taxonomy_path: str, session_factory=None):
        self.taxonomy_path = Path(taxonomy_path)
        self.threshold = 85
        self.session_factory = session_factory
        try:
            self.vector_store = VectorStore(collection_name="canonical_skills")
        except Exception:
            self.vector_store = None
        self.taxonomy: Dict[str, dict] = json.loads(self.taxonomy_path.read_text(encoding="utf-8"))
        self.alias_to_canonical = self._build_alias_map(self.taxonomy)

    def _build_alias_map(self, taxonomy: Dict[str, dict]) -> Dict[str, str]:
        amap: Dict[str, str] = {}
        for canonical, meta in taxonomy.items():
            amap[canonical.lower()] = canonical
            for alias in meta.get("aliases", []):
                amap[alias.lower()] = canonical
        return amap

    async def warmup(self) -> None:
        if self.vector_store is not None:
            await self.vector_store.upsert_skills(self.taxonomy.keys())

    async def normalize(self, skill: str) -> CanonicalSkill:
        raw = skill.strip()
        if not raw:
            return CanonicalSkill(raw=skill, canonical="", category="Unknown", parent="Unknown", confidence=0)

        if raw.lower() in self.alias_to_canonical:
            canonical = self.alias_to_canonical[raw.lower()]
            meta = self.taxonomy.get(canonical, {})
            return CanonicalSkill(
                raw=raw,
                canonical=canonical,
                category=meta.get("category", "Unknown"),
                parent=meta.get("parent", "Unknown"),
                aliases=meta.get("aliases", []),
                confidence=1.0,
            )

        best = ("", 0.0)
        for canonical in self.taxonomy.keys():
            score = fuzz.ratio(raw.lower(), canonical.lower())
            if score > best[1]:
                best = (canonical, score)

        if best[1] >= self.threshold:
            meta = self.taxonomy[best[0]]
            return CanonicalSkill(
                raw=raw,
                canonical=best[0],
                category=meta.get("category", "Unknown"),
                parent=meta.get("parent", "Unknown"),
                aliases=meta.get("aliases", []),
                confidence=best[1] / 100.0,
            )

        fallback = await self.vector_store.semantic_search(raw, k=1) if self.vector_store else []
        if fallback:
            canonical = fallback[0]
            meta = self.taxonomy.get(canonical, {})
            return CanonicalSkill(
                raw=raw,
                canonical=canonical,
                category=meta.get("category", "Unknown"),
                parent=meta.get("parent", "Unknown"),
                aliases=meta.get("aliases", []),
                confidence=0.75,
            )

        return CanonicalSkill(raw=raw, canonical=raw, category="Unknown", parent="Unknown", confidence=0.0)

    async def infer_implied_skills(self, skills: List[str]) -> List[str]:
        s = {x.lower() for x in skills}
        implied: list[str] = []
        if {"tensorflow", "pytorch"}.issubset(s):
            implied.append("Deep Learning")
        if {"react", "redux"}.issubset(s):
            implied.append("Frontend Development")
        if {"aws", "kubernetes"}.issubset(s):
            implied.append("Cloud Native")
        return implied

    async def estimate_proficiency(self, skill: str, context: str) -> str:
        c = context.lower()
        years_match = re.search(r"(\d+)\+?\s*years", c)
        years = int(years_match.group(1)) if years_match else 0
        if years >= 5 or "senior" in c or "lead" in c:
            return "Expert"
        if years >= 2:
            return "Intermediate"
        return "Beginner"

    async def flag_unknown(self, skill: str, context: str = "") -> None:
        if not self.session_factory:
            return
        async with self.session_factory() as session:
            await session.execute(insert(UnknownSkill).values(raw_skill=skill, context=context))
            await session.commit()

    async def build_profile(self, candidate_id: str, raw_skills: List[str], context: str = "") -> NormalizedProfile:
        normalized: list[NormalizedSkill] = []
        unknown: list[str] = []

        for raw_skill in raw_skills:
            canonical = await self.normalize(raw_skill)
            if canonical.category == "Unknown":
                unknown.append(raw_skill)
                await self.flag_unknown(raw_skill, context)
            proficiency = await self.estimate_proficiency(canonical.canonical, context)
            normalized.append(NormalizedSkill(skill=canonical, proficiency=proficiency))

        implied = await self.infer_implied_skills([n.skill.canonical for n in normalized])
        return NormalizedProfile(
            candidate_id=candidate_id,
            normalized_skills=normalized,
            implied_skills=implied,
            unknown_skills=unknown,
            summary=f"{len(normalized)} normalized skills",
        )
