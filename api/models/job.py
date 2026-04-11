from pydantic import BaseModel, Field
from typing import List


class JobRequest(BaseModel):
    title: str = ""
    description: str
    required_skills: List[str] = Field(default_factory=list)
    nice_to_have_skills: List[str] = Field(default_factory=list)
    min_years_experience: float = 0.0
