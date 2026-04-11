from __future__ import annotations

import os
from typing import Iterable

from sentence_transformers import SentenceTransformer

from api.models.resume import JobDescription, MatchResult, NormalizedProfile


def _cosine(a, b) -> float:
    denom = (float((a * a).sum()) ** 0.5) * (float((b * b).sum()) ** 0.5)
    if denom == 0:
        return 0.0
    return float((a @ b) / denom)


class MatchingAgent:
    def __init__(self):
        model_name = os.getenv("MATCH_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
        try:
            self.model = SentenceTransformer(model_name)
        except Exception:
            self.model = None
        self.threshold = float(os.getenv("MATCH_THRESHOLD", "0.65"))
        self.learning_map = {
            "Kubernetes": "Learn Kubernetes basics, then deploy a microservice on EKS/GKE.",
            "System Design": "Practice HLD + LLD with scalability case studies.",
            "SQL": "Complete advanced SQL joins, window functions, and indexing labs.",
        }

    def _best_similarity(self, source: str, targets: Iterable[str]) -> float:
        t = [x for x in targets if x]
        if not t:
            return 0.0
        if self.model is None:
            src_tokens = set(source.lower().split())
            score = 0.0
            for item in t:
                tgt_tokens = set(item.lower().split())
                overlap = len(src_tokens & tgt_tokens)
                union = len(src_tokens | tgt_tokens) or 1
                score = max(score, overlap / union)
            return score
        embeds = self.model.encode([source] + t)
        src = embeds[0]
        return max(_cosine(src, e) for e in embeds[1:])

    async def match(self, candidate: NormalizedProfile, job: JobDescription) -> MatchResult:
        cand_skills = [s.skill.canonical for s in candidate.normalized_skills] + candidate.implied_skills
        req = list(dict.fromkeys(job.required_skills))
        nice = list(dict.fromkeys(job.nice_to_have_skills))

        req_scores = [self._best_similarity(r, cand_skills) for r in req] if req else [0.0]
        nice_scores = [self._best_similarity(n, cand_skills) for n in nice] if nice else [0.0]

        req_score = sum(req_scores) / max(len(req_scores), 1)
        nice_score = sum(nice_scores) / max(len(nice_scores), 1)

        total_years = max((w.skill.confidence for w in candidate.normalized_skills), default=0.0) * 10
        exp_depth = min(total_years / max(job.min_years_experience, 1.0), 1.0)

        final = 0.6 * req_score + 0.2 * nice_score + 0.2 * exp_depth
        matched = [r for r, s in zip(req, req_scores) if s >= 0.65] + [n for n, s in zip(nice, nice_scores) if s >= 0.65]
        missing = [r for r, s in zip(req, req_scores) if s < 0.65]

        suggestions = [self.learning_map.get(ms, f"Build hands-on project and course track for {ms}.") for ms in missing]

        return MatchResult(
            candidate_id=candidate.candidate_id,
            score=round(final, 4),
            above_threshold=final >= self.threshold,
            matched_skills=matched,
            missing_skills=missing,
            upskilling_suggestions=suggestions,
            details={
                "required_score": round(req_score, 4),
                "nice_to_have_score": round(nice_score, 4),
                "experience_depth": round(exp_depth, 4),
            },
        )
