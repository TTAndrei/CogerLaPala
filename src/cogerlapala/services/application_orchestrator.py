from __future__ import annotations

from typing import Literal

from cogerlapala.models import (
    ApplicationActionResult,
    CandidateProfile,
    ExecutionOptions,
    FormQuestion,
    JobPosting,
)
from cogerlapala.services.ai_mapper import AIAnswerGenerator
from cogerlapala.services.browser_automator import BrowserAutomator
from cogerlapala.services.linkedin_easy_apply import LinkedInEasyApplyAutomator


class ApplicationOrchestrator:
    def __init__(
        self,
        answer_generator: AIAnswerGenerator,
        automator: BrowserAutomator,
        linkedin_automator: LinkedInEasyApplyAutomator | None = None,
    ) -> None:
        self.answer_generator = answer_generator
        self.automator = automator
        self.linkedin_automator = linkedin_automator

    async def execute(
        self,
        profile: CandidateProfile,
        posting: JobPosting,
        execution: ExecutionOptions,
    ) -> ApplicationActionResult:
        if execution.require_human_review and not execution.dry_run:
            return ApplicationActionResult(
                posting_id=posting.id,
                title=posting.title,
                company=posting.company,
                status="skipped",
                details="Skipped because require_human_review=true and dry_run=false.",
            )

        questions = self._build_default_questions(posting)
        answers = self.answer_generator.generate(
            profile=profile,
            posting=posting,
            questions=questions,
        )

        if not execution.enable_browser_automation:
            return ApplicationActionResult(
                posting_id=posting.id,
                title=posting.title,
                company=posting.company,
                status="dry-run",
                details=f"Automation disabled. Prepared {len(answers)} answers.",
            )

        status: Literal["dry-run", "submitted", "failed"]
        if posting.source.lower() == "linkedin" and self.linkedin_automator is not None:
            status, details, screenshot_path = await self.linkedin_automator.apply(
                posting=posting,
                answers=answers,
                cv_path=profile.cv_path,
                dry_run=execution.dry_run,
                screenshot_each_step=execution.screenshot_each_step,
            )
        else:
            status, details, screenshot_path = await self.automator.apply(
                posting=posting,
                answers=answers,
                cv_path=profile.cv_path,
                dry_run=execution.dry_run,
                screenshot_each_step=execution.screenshot_each_step,
            )

        return ApplicationActionResult.model_validate(
            {
                "posting_id": posting.id,
                "title": posting.title,
                "company": posting.company,
                "status": status,
                "details": details,
                "screenshot_path": screenshot_path,
            }
        )

    def _build_default_questions(self, posting: JobPosting) -> list[FormQuestion]:
        questions = [
            FormQuestion(label="Full name", question_type="text", required=True),
            FormQuestion(label="Email", question_type="text", required=True),
            FormQuestion(label="Phone", question_type="text", required=False),
            FormQuestion(label="Location", question_type="text", required=True),
            FormQuestion(label="Salary expectation", question_type="text", required=False),
            FormQuestion(label="Cover letter", question_type="textarea", required=False),
        ]

        for skill in posting.required_skills[:4]:
            questions.append(
                FormQuestion(
                    label=f"Do you have experience with {skill}?",
                    question_type="boolean",
                    required=True,
                    options=["Yes", "No"],
                )
            )

        return questions
