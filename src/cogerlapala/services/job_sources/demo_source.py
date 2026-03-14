from __future__ import annotations

from typing import Iterable

from cogerlapala.models import JobPosting, SearchParameters


class DemoAutonomousSource:
    source_name = "demo"

    def __init__(self) -> None:
        self._catalogue = [
            JobPosting(
                id="demo-001",
                title="Backend Python Engineer",
                company="Nordic Data Labs",
                location="Madrid",
                url="https://example.org/jobs/demo-001",
                source=self.source_name,
                description="Build APIs with Python, FastAPI and cloud services.",
                required_skills=["python", "fastapi", "postgresql", "docker"],
                remote=True,
                salary_min=42000,
                salary_max=55000,
            ),
            JobPosting(
                id="demo-002",
                title="Automation QA Engineer",
                company="Atlas Retail Tech",
                location="Barcelona",
                url="https://example.org/jobs/demo-002",
                source=self.source_name,
                description="Improve quality pipelines with Playwright and CI.",
                required_skills=["playwright", "typescript", "ci", "testing"],
                remote=True,
                salary_min=35000,
                salary_max=47000,
            ),
            JobPosting(
                id="demo-003",
                title="AI Integrations Developer",
                company="Horizon Hiring Systems",
                location="Remote - EU",
                url="https://example.org/jobs/demo-003",
                source=self.source_name,
                description="Integrate LLM APIs, automate workflows and handle structured prompts.",
                required_skills=["python", "openai", "automation", "api"],
                remote=True,
                salary_min=45000,
                salary_max=62000,
            ),
            JobPosting(
                id="demo-004",
                title="Talent Platform Automation Specialist",
                company="Talent Flux",
                location="Valencia",
                url="https://example.org/jobs/demo-004",
                source=self.source_name,
                description="Automate ATS and recruitment operations with browser workflows.",
                required_skills=["selenium", "playwright", "python", "scraping"],
                remote=False,
                salary_min=30000,
                salary_max=42000,
            ),
        ]

    async def search(self, params: SearchParameters) -> list[JobPosting]:
        keywords = {value.lower() for value in params.keywords}
        sectors = {value.lower() for value in params.sectors}
        locations = params.location_values()

        results = [
            posting
            for posting in self._catalogue
            if self._matches(posting, keywords, sectors, params, locations)
        ]

        if len(results) < min(3, params.max_results_per_source):
            results.extend(
                self._synthesize_jobs(
                    keywords=keywords,
                    location=locations[0] if locations else "Remote",
                    count=min(3, params.max_results_per_source) - len(results),
                )
            )

        return results[: params.max_results_per_source]

    def _matches(
        self,
        posting: JobPosting,
        keywords: set[str],
        sectors: set[str],
        params: SearchParameters,
        locations: list[str],
    ) -> bool:
        text = " ".join(
            [
                posting.title,
                posting.company,
                posting.description,
                " ".join(posting.required_skills),
            ]
        ).lower()

        keyword_ok = not keywords or any(word in text for word in keywords)
        sector_ok = not sectors or any(sector in text for sector in sectors)

        location_ok = True
        if locations:
            location_ok = (
                any(location.lower() in posting.location.lower() for location in locations)
                or posting.remote
            )

        remote_ok = not params.remote_only or posting.remote
        return keyword_ok and sector_ok and location_ok and remote_ok

    def _synthesize_jobs(self, keywords: Iterable[str], location: str, count: int) -> list[JobPosting]:
        generated: list[JobPosting] = []
        seed_words = list(keywords) if keywords else ["automation", "python", "ai"]

        for index in range(count):
            keyword = seed_words[index % len(seed_words)]
            normalized = keyword.strip().replace(" ", "-")
            generated.append(
                JobPosting(
                    id=f"demo-generated-{index + 1}",
                    title=f"{keyword.title()} Workflow Engineer",
                    company=f"Autonomous Hiring Co {index + 1}",
                    location=location,
                    url=f"https://example.org/jobs/generated-{normalized}-{index + 1}",
                    source=self.source_name,
                    description=f"Automate job application flows focused on {keyword}.",
                    required_skills=[keyword, "python", "playwright"],
                    remote=True,
                )
            )

        return generated
