from __future__ import annotations

import json
import re
from typing import Any

from cogerlapala.models import CandidateProfile, FormAnswer, FormQuestion, JobPosting

try:
    from openai import OpenAI
except Exception:  # pragma: no cover - optional dependency runtime guard
    OpenAI = None  # type: ignore[assignment]


class HeuristicAnswerGenerator:
    def generate(
        self,
        profile: CandidateProfile,
        posting: JobPosting,
        questions: list[FormQuestion],
    ) -> list[FormAnswer]:
        answers: list[FormAnswer] = []

        for question in questions:
            label = question.label.lower()

            if "name" in label:
                answers.append(FormAnswer(label=question.label, answer=profile.full_name, confidence=0.99))
                continue
            if "email" in label:
                answers.append(FormAnswer(label=question.label, answer=profile.email, confidence=0.99))
                continue
            if "phone" in label or "mobile" in label:
                answers.append(
                    FormAnswer(label=question.label, answer=profile.phone or "", confidence=0.95)
                )
                continue
            if "location" in label or "city" in label:
                answers.append(FormAnswer(label=question.label, answer=profile.location, confidence=0.95))
                continue
            if "salary" in label:
                salary_text = (
                    str(profile.salary_expectation_min)
                    if profile.salary_expectation_min is not None
                    else "Negotiable"
                )
                answers.append(FormAnswer(label=question.label, answer=salary_text, confidence=0.75))
                continue
            if "linkedin" in label:
                answers.append(FormAnswer(label=question.label, answer="", confidence=0.2))
                continue
            if "cover" in label or "letter" in label:
                answers.append(
                    FormAnswer(
                        label=question.label,
                        answer=self._cover_letter(profile=profile, posting=posting),
                        confidence=0.8,
                    )
                )
                continue

            matched_skill = self._extract_skill_question(label)
            if matched_skill:
                has_skill = matched_skill.lower() in {_skill.lower() for _skill in profile.skills}
                answer = "Yes" if has_skill else "No"
                answers.append(FormAnswer(label=question.label, answer=answer, confidence=0.85))
                continue

            fallback = profile.summary or profile.headline or "Available on request"
            answers.append(FormAnswer(label=question.label, answer=fallback, confidence=0.5))

        return answers

    def _extract_skill_question(self, question_label: str) -> str | None:
        match = re.search(r"experience with ([a-z0-9+.# -]+)", question_label)
        if not match:
            return None
        return match.group(1).strip()

    def _cover_letter(self, profile: CandidateProfile, posting: JobPosting) -> str:
        top_skills = ", ".join(profile.skills[:4]) or "automation"
        return (
            f"I am interested in the {posting.title} role at {posting.company}. "
            f"My background in {top_skills} aligns with your requirements, "
            "and I can contribute from day one."
        )


class AIAnswerGenerator:
    def __init__(self, api_key: str | None, model: str) -> None:
        self.model = model
        self.heuristic = HeuristicAnswerGenerator()
        self.client = OpenAI(api_key=api_key) if (api_key and OpenAI) else None

    def generate(
        self,
        profile: CandidateProfile,
        posting: JobPosting,
        questions: list[FormQuestion],
    ) -> list[FormAnswer]:
        fallback_answers = self.heuristic.generate(profile=profile, posting=posting, questions=questions)
        if not self.client:
            return fallback_answers

        try:
            prompt_payload = {
                "profile": profile.model_dump(),
                "posting": posting.model_dump(),
                "questions": [question.model_dump() for question in questions],
                "rules": [
                    "Return strict JSON object with key 'answers'",
                    "answers must be array of {label, answer, confidence}",
                    "confidence must be from 0 to 1",
                    "Do not omit required questions",
                ],
            }

            response = self.client.responses.create(
                model=self.model,
                input=[
                    {
                        "role": "system",
                        "content": (
                            "You map job application form questions to candidate profile answers. "
                            "Output JSON only."
                        ),
                    },
                    {"role": "user", "content": json.dumps(prompt_payload)},
                ],
                text={"format": {"type": "json_object"}},
            )

            text = self._extract_output_text(response)
            payload = json.loads(text)
            ai_answers = payload.get("answers", [])
            parsed_answers = [
                FormAnswer(
                    label=item["label"],
                    answer=str(item["answer"]),
                    confidence=float(item.get("confidence", 0.6)),
                )
                for item in ai_answers
                if isinstance(item, dict) and "label" in item and "answer" in item
            ]

            if not parsed_answers:
                return fallback_answers

            merged = {answer.label: answer for answer in fallback_answers}
            for answer in parsed_answers:
                merged[answer.label] = answer
            return [merged[question.label] for question in questions if question.label in merged]
        except Exception:
            return fallback_answers

    def _extract_output_text(self, response: Any) -> str:
        output_text = getattr(response, "output_text", None)
        if isinstance(output_text, str) and output_text.strip():
            return output_text

        output = getattr(response, "output", None)
        if isinstance(output, list):
            for event in output:
                content = event.get("content") if isinstance(event, dict) else None
                if isinstance(content, list):
                    for chunk in content:
                        text = chunk.get("text") if isinstance(chunk, dict) else None
                        if isinstance(text, str) and text.strip():
                            return text

        raise ValueError("OpenAI response did not contain JSON text output")
