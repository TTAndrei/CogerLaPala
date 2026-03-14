from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class CandidateProfile(BaseModel):
    full_name: str
    email: str
    phone: str | None = None
    location: str
    headline: str | None = None
    summary: str | None = None
    target_roles: list[str] = Field(default_factory=list)
    sectors: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    years_experience: int = Field(default=0, ge=0)
    salary_expectation_min: int | None = None
    salary_expectation_currency: str | None = None
    cv_path: str | None = None


class SearchParameters(BaseModel):
    keywords: list[str] = Field(default_factory=list)
    location: str | None = None
    remote_only: bool = False
    sectors: list[str] = Field(default_factory=list)
    seniority: str | None = None
    linkedin_easy_apply_only: bool = True
    max_results_per_source: int = Field(default=20, ge=1, le=100)
    sources: list[str] = Field(default_factory=lambda: ["demo"])


class JobPosting(BaseModel):
    id: str
    title: str
    company: str
    location: str
    url: str
    source: str
    description: str
    required_skills: list[str] = Field(default_factory=list)
    remote: bool = False
    salary_min: int | None = None
    salary_max: int | None = None


class ApplicationDecision(BaseModel):
    should_apply: bool
    score: float = Field(ge=0, le=100)
    reasons: list[str] = Field(default_factory=list)


class JobEvaluation(BaseModel):
    posting: JobPosting
    decision: ApplicationDecision


class ExecutionOptions(BaseModel):
    dry_run: bool = True
    enable_browser_automation: bool = True
    require_human_review: bool = True
    max_applications: int = Field(default=5, ge=1, le=50)
    screenshot_each_step: bool = True


class FormQuestion(BaseModel):
    label: str
    question_type: Literal["text", "textarea", "select", "boolean", "number", "file"]
    required: bool = False
    options: list[str] = Field(default_factory=list)


class FormAnswer(BaseModel):
    label: str
    answer: str
    confidence: float = Field(ge=0, le=1)


class ApplicationActionResult(BaseModel):
    posting_id: str
    title: str
    company: str
    status: Literal["skipped", "dry-run", "submitted", "failed"]
    details: str
    screenshot_path: str | None = None


class PipelineRequest(BaseModel):
    profile: CandidateProfile
    search: SearchParameters
    execution: ExecutionOptions = Field(default_factory=ExecutionOptions)


class PipelineResponse(BaseModel):
    discovered_count: int
    selected_count: int
    evaluations: list[JobEvaluation]
    action_results: list[ApplicationActionResult]
    warnings: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=datetime.utcnow)
