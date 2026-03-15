from __future__ import annotations

from cogerlapala.config import Settings
from cogerlapala.models import JobEvaluation, JobPosting, PipelineRequest, PipelineResponse
from cogerlapala.services.ai_mapper import AIAnswerGenerator
from cogerlapala.services.application_orchestrator import ApplicationOrchestrator
from cogerlapala.services.browser_automator import BrowserAutomator
from cogerlapala.services.job_sources.base import JobSource
from cogerlapala.services.job_sources.demo_source import DemoAutonomousSource
from cogerlapala.services.job_sources.linkedin_source import LinkedInSource
from cogerlapala.services.linkedin_easy_apply import LinkedInEasyApplyAutomator
from cogerlapala.services.matching import JobMatcher


class ApplicationPipeline:
    def __init__(
        self,
        settings: Settings,
        sources: dict[str, JobSource],
        matcher: JobMatcher,
        orchestrator: ApplicationOrchestrator,
    ) -> None:
        self.settings = settings
        self.sources = sources
        self.matcher = matcher
        self.orchestrator = orchestrator

    async def run(self, request: PipelineRequest) -> PipelineResponse:
        warnings: list[str] = []
        discovered = []

        requested_sources = request.search.sources or list(self.sources)
        for source_name in requested_sources:
            source = self.sources.get(source_name)
            if source is None:
                warnings.append(f"Unknown source '{source_name}' skipped")
                continue
            discovered.extend(await source.search(request.search))

        unique_jobs = self._dedupe_jobs(discovered)
        evaluations = [
            JobEvaluation(
                posting=job,
                decision=self.matcher.evaluate(profile=request.profile, posting=job),
            )
            for job in unique_jobs
        ]

        evaluations.sort(key=lambda item: item.decision.score, reverse=True)
        selected = [item for item in evaluations if item.decision.should_apply]

        max_allowed = min(
            request.execution.max_applications,
            self.settings.max_daily_applications,
        )
        selected = selected[:max_allowed]

        action_results = []
        for item in selected:
            action_results.append(
                await self.orchestrator.execute(
                    profile=request.profile,
                    posting=item.posting,
                    execution=request.execution,
                )
            )

        if not selected:
            warnings.append("No jobs passed the match threshold.")

        if request.execution.require_human_review and not request.execution.dry_run:
            warnings.append(
                "Human review is enabled. Executions are skipped until you disable require_human_review."
            )

        return PipelineResponse(
            discovered_count=len(unique_jobs),
            selected_count=len(selected),
            evaluations=evaluations,
            action_results=action_results,
            warnings=warnings,
        )

    def _dedupe_jobs(self, jobs: list[JobPosting]) -> list[JobPosting]:
        unique_by_url: dict[str, JobPosting] = {}
        for job in jobs:
            unique_by_url[job.url] = job
        return list(unique_by_url.values())


def build_default_pipeline(settings: Settings) -> ApplicationPipeline:
    matcher = JobMatcher(min_score=settings.min_match_score)
    answer_generator = AIAnswerGenerator(
        api_key=settings.openai_api_key,
        model=settings.openai_model,
    )
    orchestrator = ApplicationOrchestrator(
        answer_generator=answer_generator,
        automator=BrowserAutomator(screenshot_dir=settings.screenshot_dir),
        linkedin_automator=LinkedInEasyApplyAutomator(
            storage_state_path=settings.linkedin_storage_state,
            screenshot_dir=settings.screenshot_dir,
            email=settings.linkedin_email,
            password=settings.linkedin_password,
            headless=settings.linkedin_headless,
            manual_login_timeout_seconds=settings.linkedin_manual_login_timeout_seconds,
            ai_api_key=settings.openai_api_key,
            ai_navigation_enabled=settings.linkedin_ai_navigation_enabled,
            ai_navigation_model=settings.linkedin_ai_navigation_model,
            ai_navigation_max_attempts=settings.linkedin_ai_navigation_max_attempts,
        ),
    )

    sources: dict[str, JobSource] = {
        "demo": DemoAutonomousSource(),
        "linkedin": LinkedInSource(
            email=settings.linkedin_email,
            password=settings.linkedin_password,
            storage_state_path=settings.linkedin_storage_state,
            headless=settings.linkedin_headless,
            manual_login_timeout_seconds=settings.linkedin_manual_login_timeout_seconds,
            max_search_pages=settings.linkedin_max_search_pages,
        ),
    }

    return ApplicationPipeline(
        settings=settings,
        sources=sources,
        matcher=matcher,
        orchestrator=orchestrator,
    )
