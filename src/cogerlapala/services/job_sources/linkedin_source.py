from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Literal
from urllib.parse import quote_plus

from playwright.async_api import (
    Browser,
    BrowserContext,
    Locator,
    Page,
    Playwright,
    async_playwright,
)

from cogerlapala.models import JobPosting, SearchParameters


class LinkedInSource:
    """LinkedIn job search source based on an authenticated browser session.

    Notes:
    - Uses normal login/session, no anti-bot bypass.
    - Persists storage state to avoid logging in on each run.
    - Returns only metadata needed by the pipeline.
    """

    source_name = "linkedin"

    _SKILL_HINTS = {
        "python",
        "java",
        "javascript",
        "typescript",
        "fastapi",
        "django",
        "flask",
        "playwright",
        "selenium",
        "sql",
        "postgresql",
        "aws",
        "azure",
        "docker",
        "kubernetes",
        "react",
        "node",
        "api",
        "automation",
        "ai",
        "openai",
    }

    def __init__(
        self,
        email: str | None = None,
        password: str | None = None,
        storage_state_path: str = ".artifacts/linkedin-storage-state.json",
        headless: bool = False,
        manual_login_timeout_seconds: int = 180,
        max_search_pages: int = 3,
    ) -> None:
        self.email = email
        self.password = password
        self.storage_state_path = Path(storage_state_path)
        self.headless = headless
        self.manual_login_timeout_seconds = max(manual_login_timeout_seconds, 30)
        self.max_search_pages = max(max_search_pages, 1)

    async def search(self, params: SearchParameters) -> list[JobPosting]:
        collected: list[JobPosting] = []
        seen_urls: set[str] = set()
        locations = params.location_values() or ["Spain"]

        async with async_playwright() as playwright:
            browser = await self._launch_browser(playwright)
            context = await self._new_context(browser)
            page = await context.new_page()

            try:
                authenticated = await self._ensure_authenticated(page)
                if not authenticated:
                    return []

                for search_location in locations:
                    if len(collected) >= params.max_results_per_source:
                        break

                    search_url = self._build_search_url(params, search_location)
                    await page.goto(search_url, wait_until="domcontentloaded", timeout=60000)
                    await page.wait_for_timeout(2000)

                    for page_index in range(self.max_search_pages):
                        await self._scroll_results(page)
                        jobs = await self._extract_jobs_from_page(
                            page,
                            easy_apply_only=params.linkedin_easy_apply_only,
                        )

                        for job in jobs:
                            if job.url in seen_urls:
                                continue
                            seen_urls.add(job.url)
                            collected.append(job)
                            if len(collected) >= params.max_results_per_source:
                                break

                        if len(collected) >= params.max_results_per_source:
                            break

                        if not await self._goto_next_page(page, page_index + 2):
                            break

                await self._save_storage_state(context)
                return collected[: params.max_results_per_source]
            finally:
                await context.close()
                await browser.close()

    async def _launch_browser(self, playwright: Playwright) -> Browser:
        mode: Literal[True, False] = True if self.headless else False
        launch_options: list[tuple[bool, str | None]] = [
            (mode, None),
            (mode, "msedge"),
        ]

        if self.headless:
            launch_options.extend(
                [
                    (False, None),
                    (False, "msedge"),
                ]
            )

        errors: list[str] = []
        for headless, channel in launch_options:
            try:
                if channel is None:
                    return await playwright.chromium.launch(headless=headless)
                return await playwright.chromium.launch(headless=headless, channel=channel)
            except Exception as exc:
                errors.append(f"headless={headless}, channel={channel}: {exc}")

        raise RuntimeError("Unable to launch browser for LinkedIn source: " + " | ".join(errors))

    async def _new_context(self, browser: Browser) -> BrowserContext:
        if self.storage_state_path.exists():
            return await browser.new_context(storage_state=str(self.storage_state_path))
        return await browser.new_context()

    async def _ensure_authenticated(self, page: Page) -> bool:
        await page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=60000)
        if self._is_authenticated_url(page.url):
            return True

        await page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded", timeout=60000)

        if self.email and self.password:
            username = page.locator("#username")
            passwd = page.locator("#password")
            if await username.count() > 0 and await passwd.count() > 0:
                await username.first.fill(self.email)
                await passwd.first.fill(self.password)
                await page.locator("button[type='submit']").first.click()
                await page.wait_for_timeout(3000)

            if self._is_authenticated_url(page.url):
                return True

        if self.headless:
            return False

        # Allow manual login and MFA challenge resolution when running headed.
        deadline = time.monotonic() + float(self.manual_login_timeout_seconds)
        while time.monotonic() < deadline:
            if self._is_authenticated_url(page.url):
                return True
            await page.wait_for_timeout(1000)

        return False

    def _is_authenticated_url(self, url: str) -> bool:
        normalized = url.lower()
        if "linkedin.com/login" in normalized:
            return False
        if "linkedin.com/checkpoint" in normalized:
            return False
        return (
            "linkedin.com/feed" in normalized
            or "linkedin.com/jobs" in normalized
            or "linkedin.com/in/" in normalized
        )

    async def _save_storage_state(self, context: BrowserContext) -> None:
        self.storage_state_path.parent.mkdir(parents=True, exist_ok=True)
        await context.storage_state(path=str(self.storage_state_path))

    def _build_search_url(self, params: SearchParameters, location_value: str) -> str:
        keywords = quote_plus(" ".join(params.keywords).strip() or "software engineer")
        location = quote_plus(location_value.strip() or "Spain")

        query_items = [
            f"keywords={keywords}",
            f"location={location}",
            "position=1",
            "pageNum=0",
        ]

        if params.linkedin_easy_apply_only:
            query_items.append("f_AL=true")

        if params.remote_only:
            query_items.append("f_WT=2")

        return "https://www.linkedin.com/jobs/search/?" + "&".join(query_items)

    async def _scroll_results(self, page: Page) -> None:
        for _ in range(5):
            await page.mouse.wheel(0, 4000)
            await page.wait_for_timeout(450)

    async def _extract_jobs_from_page(self, page: Page, easy_apply_only: bool) -> list[JobPosting]:
        jobs: list[JobPosting] = []
        cards = page.locator(
            "li.jobs-search-results__list-item, li.scaffold-layout__list-item, div.job-card-container"
        )
        count = await cards.count()

        for index in range(min(count, 40)):
            card = cards.nth(index)

            if easy_apply_only and not await self._card_supports_easy_apply(card):
                continue

            try:
                await card.scroll_into_view_if_needed()
            except Exception:
                pass

            href = await self._first_attr(
                card,
                [
                    "a.job-card-list__title",
                    "a.job-card-container__link",
                    "a[href*='/jobs/view/']",
                ],
                "href",
            )
            canonical_url = self._canonical_job_url(href)
            if not canonical_url:
                continue

            try:
                await card.click(timeout=2500)
                await page.wait_for_timeout(600)
            except Exception:
                pass

            title = await self._first_text(
                card,
                [
                    "a.job-card-list__title",
                    "a.job-card-container__link",
                    "strong",
                ],
            )
            company = await self._first_text(
                card,
                [
                    ".job-card-container__company-name",
                    ".artdeco-entity-lockup__subtitle",
                    ".job-card-list__subtitle",
                ],
            )
            location = await self._first_text(
                card,
                [
                    ".job-card-container__metadata-item",
                    ".artdeco-entity-lockup__caption",
                ],
            )
            description = await self._extract_description(page)

            if not title:
                title = "LinkedIn Job"
            if not company:
                company = "Unknown company"
            if not location:
                location = "Unknown location"

            remote = (
                "remote" in location.lower()
                or "remoto" in location.lower()
                or "remote" in description.lower()
            )

            jobs.append(
                JobPosting(
                    id=self._extract_job_id(canonical_url),
                    title=title,
                    company=company,
                    location=location,
                    url=canonical_url,
                    source=self.source_name,
                    description=description or f"{title} at {company}",
                    required_skills=self._extract_skills(description),
                    remote=remote,
                )
            )

        return jobs

    async def _card_supports_easy_apply(self, card: Locator) -> bool:
        easy_words = [
            "easy apply",
            "solicitud sencilla",
            "solicitud simplificada",
            "aplicar facilmente",
            "solicitar facilmente",
        ]

        badge_selectors = [
            ".job-card-container__apply-method",
            ".job-card-list__apply-method",
            "span.artdeco-inline-feedback__message",
        ]

        for selector in badge_selectors:
            loc = card.locator(selector)
            if await loc.count() == 0:
                continue
            text = (await loc.first.inner_text()).strip().lower()
            if any(word in text for word in easy_words):
                return True

        text = (await card.inner_text()).strip().lower()
        return any(word in text for word in easy_words)

    async def _extract_description(self, page: Page) -> str:
        selectors = [
            "div.jobs-description-content__text",
            "div.jobs-box__html-content",
            "section.show-more-less-html",
            "div.jobs-description__content",
        ]

        for selector in selectors:
            loc = page.locator(selector)
            if await loc.count() == 0:
                continue
            text = (await loc.first.inner_text()).strip()
            if text:
                return text[:3500]

        return ""

    async def _goto_next_page(self, page: Page, page_number: int) -> bool:
        page_button = page.locator(f"button[aria-label='Page {page_number}']")
        if await page_button.count() > 0:
            await page_button.first.click()
            await page.wait_for_timeout(1800)
            return True

        page_button_es = page.locator(f"button[aria-label='Página {page_number}']")
        if await page_button_es.count() > 0:
            await page_button_es.first.click()
            await page.wait_for_timeout(1800)
            return True

        next_button = page.get_by_role("button", name=re.compile(r"(next|siguiente)", re.IGNORECASE))
        if await next_button.count() > 0 and not await next_button.first.is_disabled():
            await next_button.first.click()
            await page.wait_for_timeout(1800)
            return True

        return False

    async def _first_text(self, root: Page | Locator, selectors: list[str]) -> str:
        for selector in selectors:
            loc = root.locator(selector)
            if await loc.count() == 0:
                continue
            text = (await loc.first.inner_text()).strip()
            if text:
                return text
        return ""

    async def _first_attr(self, root: Page | Locator, selectors: list[str], attr: str) -> str | None:
        for selector in selectors:
            loc = root.locator(selector)
            if await loc.count() == 0:
                continue
            value = await loc.first.get_attribute(attr)
            if value:
                return value
        return None

    def _canonical_job_url(self, url: str | None) -> str | None:
        if not url:
            return None
        match = re.search(r"/jobs/view/(\d+)", url)
        if match:
            return f"https://www.linkedin.com/jobs/view/{match.group(1)}/"
        if url.startswith("https://"):
            return url
        if url.startswith("/"):
            return "https://www.linkedin.com" + url
        return None

    def _extract_job_id(self, url: str) -> str:
        match = re.search(r"/jobs/view/(\d+)", url)
        if match:
            return f"linkedin-{match.group(1)}"
        return f"linkedin-{abs(hash(url))}"

    def _extract_skills(self, description: str) -> list[str]:
        lower = description.lower()
        found = [skill for skill in self._SKILL_HINTS if skill in lower]
        return sorted(set(found))[:12]
