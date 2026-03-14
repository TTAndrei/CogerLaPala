from __future__ import annotations

import re

from cogerlapala.models import ApplicationDecision, CandidateProfile, JobPosting


def _tokenize(text: str) -> set[str]:
    clean = re.sub(r"[^a-z0-9+.# ]+", " ", text.lower())
    return {token for token in clean.split() if len(token) > 1}


def _safe_ratio(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator


class JobMatcher:
    def __init__(self, min_score: float = 60.0) -> None:
        self.min_score = min_score

    def evaluate(self, profile: CandidateProfile, posting: JobPosting) -> ApplicationDecision:
        reasons: list[str] = []

        candidate_skill_tokens = {_skill.lower() for _skill in profile.skills}
        required_skill_tokens = {_skill.lower() for _skill in posting.required_skills}
        if not required_skill_tokens:
            required_skill_tokens = _tokenize(posting.description)

        matched_skills = candidate_skill_tokens.intersection(required_skill_tokens)
        skill_score = 50.0 * _safe_ratio(len(matched_skills), max(len(required_skill_tokens), 1))
        if matched_skills:
            reasons.append(
                f"Skill overlap: {len(matched_skills)}/{max(len(required_skill_tokens), 1)}"
            )

        posting_text_tokens = _tokenize(
            f"{posting.title} {posting.description} {posting.company}"
        )

        role_hits = 0
        for role in profile.target_roles:
            role_tokens = _tokenize(role)
            if role_tokens and role_tokens.intersection(posting_text_tokens):
                role_hits += 1
        role_score = 25.0 * _safe_ratio(role_hits, max(len(profile.target_roles), 1))
        if role_hits:
            reasons.append(f"Role alignment: {role_hits} role targets matched")

        sector_hits = 0
        for sector in profile.sectors:
            sector_tokens = _tokenize(sector)
            if sector_tokens and sector_tokens.intersection(posting_text_tokens):
                sector_hits += 1
        sector_score = 15.0 * _safe_ratio(sector_hits, max(len(profile.sectors), 1))
        if sector_hits:
            reasons.append(f"Sector alignment: {sector_hits} sector tags matched")

        location_score = 0.0
        if posting.remote:
            location_score = 10.0
            reasons.append("Remote compatible")
        elif profile.location.lower() in posting.location.lower():
            location_score = 10.0
            reasons.append("Location compatible")

        salary_guard_ok = True
        if (
            profile.salary_expectation_min is not None
            and posting.salary_max is not None
            and posting.salary_max < profile.salary_expectation_min
        ):
            salary_guard_ok = False
            reasons.append("Rejected by salary expectation filter")

        raw_score = skill_score + role_score + sector_score + location_score
        score = round(min(raw_score, 100.0), 2)
        should_apply = score >= self.min_score and salary_guard_ok

        if not should_apply and score < self.min_score:
            reasons.append(
                f"Score {score} below threshold {self.min_score}"
            )

        return ApplicationDecision(should_apply=should_apply, score=score, reasons=reasons)
