from pydantic import BaseModel, Field
from typing import List, Optional


class WorkExperience(BaseModel):
    title: str = ""
    company: str = ""
    start_date: str = ""
    end_date: str = ""
    description: str = ""
    years: float = 0.0


class Education(BaseModel):
    degree: str = ""
    institution: str = ""
    field_of_study: str = ""
    start_date: str = ""
    end_date: str = ""


class Project(BaseModel):
    name: str = ""
    description: str = ""
    technologies: List[str] = Field(default_factory=list)


class ParsedResume(BaseModel):
    candidate_id: str
    name: str = ""
    email: str = ""
    phone: str = ""
    location: str = ""
    summary: str = ""
    work_experience: List[WorkExperience] = Field(default_factory=list)
    education: List[Education] = Field(default_factory=list)
    skills: List[str] = Field(default_factory=list)
    certifications: List[str] = Field(default_factory=list)
    projects: List[Project] = Field(default_factory=list)
    publications: List[str] = Field(default_factory=list)
    raw_text: str


class CanonicalSkill(BaseModel):
    raw: str
    canonical: str
    category: str
    parent: str
    aliases: List[str] = Field(default_factory=list)
    confidence: float = 0.0


class NormalizedSkill(BaseModel):
    skill: CanonicalSkill
    proficiency: str = "Intermediate"


class NormalizedProfile(BaseModel):
    candidate_id: str
    normalized_skills: List[NormalizedSkill] = Field(default_factory=list)
    implied_skills: List[str] = Field(default_factory=list)
    unknown_skills: List[str] = Field(default_factory=list)
    summary: str = ""


class MatchResult(BaseModel):
    candidate_id: str
    score: float
    above_threshold: bool
    matched_skills: List[str] = Field(default_factory=list)
    missing_skills: List[str] = Field(default_factory=list)
    upskilling_suggestions: List[str] = Field(default_factory=list)
    details: dict = Field(default_factory=dict)


class JobDescription(BaseModel):
    title: str = ""
    required_skills: List[str] = Field(default_factory=list)
    nice_to_have_skills: List[str] = Field(default_factory=list)
    min_years_experience: float = 0.0
    description: str = ""


class AgentTrace(BaseModel):
    agent: str
    success: bool
    latency_ms: int
    quality_score: float = 0.0
    error: Optional[str] = None
