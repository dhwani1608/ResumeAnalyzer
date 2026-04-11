from pydantic import BaseModel, Field
from typing import List


class CandidateSkillsResponse(BaseModel):
    request_id: str
    candidate_id: str
    skills: List[str] = Field(default_factory=list)
    implied_skills: List[str] = Field(default_factory=list)
