from __future__ import annotations

import re
import time
from datetime import datetime
from pathlib import Path
from typing import Literal

from playwright.async_api import Browser, BrowserContext, Locator, Page, Playwright, async_playwright

from cogerlapala.models import FormAnswer, JobPosting


class LinkedInEasyApplyAutomator:
    def __init__(
        self,
        storage_state_path: str,
        screenshot_dir: str,
        email: str | None = None,
        password: str | None = None,
        headless: bool = False,
        manual_login_timeout_seconds: int = 180,
    ) -> None:
        self.storage_state_path = Path(storage_state_path)
        self.screenshot_dir = Path(screenshot_dir)
        self.email = email
        self.password = password
        self.headless = headless
        self.manual_login_timeout_seconds = max(manual_login_timeout_seconds, 30)

    async def apply(
        self,
        posting: JobPosting,
        answers: list[FormAnswer],
        cv_path: str | None,
        dry_run: bool,
        screenshot_each_step: bool,
    ) -> tuple[Literal["dry-run", "submitted", "failed"], str, str | None]:
        screenshot_path: str | None = None

        try:
            self.screenshot_dir.mkdir(parents=True, exist_ok=True)

            async with async_playwright() as playwright:
                browser = await self._launch_browser(playwright)
                context = await self._new_context(browser)
                page = await context.new_page()

                try:
                    if not await self._ensure_authenticated(page):
                        return (
                            "failed",
                            "LinkedIn login required. Run in non-headless mode and complete login/MFA.",
                            None,
                        )

                    await page.goto(posting.url, wait_until="domcontentloaded", timeout=60000)
                    await page.wait_for_timeout(1800)

                    easy_apply_button = page.get_by_role(
                        "button", name=re.compile(r"(easy apply|solicitud sencilla)", re.IGNORECASE)
                    )
                    if await easy_apply_button.count() == 0:
                        return (
                            "failed",
                            "Easy Apply not available for this job.",
                            None,
                        )

                    await easy_apply_button.first.click()
                    await page.wait_for_timeout(1200)

                    for step in range(1, 12):
                        modal = page.locator("div.jobs-easy-apply-modal")
                        if await modal.count() == 0:
                            return (
                                "failed",
                                "Easy Apply modal not found after opening application.",
                                screenshot_path,
                            )

                        await self._fill_answers(modal.first, answers)
                        if cv_path:
                            await self._upload_cv(modal.first, cv_path)

                        if screenshot_each_step:
                            screenshot_path = str(self._step_screenshot_file(posting.id, step))
                            await page.screenshot(path=screenshot_path, full_page=True)

                        submit_button = modal.first.get_by_role(
                            "button",
                            name=re.compile(r"(submit application|enviar solicitud)", re.IGNORECASE),
                        )
                        if await submit_button.count() > 0:
                            if await submit_button.first.is_disabled():
                                return (
                                    "failed",
                                    "Submit is disabled. Some required fields may still be missing.",
                                    screenshot_path,
                                )

                            if dry_run:
                                await self._discard_modal(page)
                                return (
                                    "dry-run",
                                    "Reached final submit step on LinkedIn. Submission skipped by dry-run.",
                                    screenshot_path,
                                )

                            await submit_button.first.click()
                            await page.wait_for_timeout(1800)
                            await self._save_storage_state(context)
                            return (
                                "submitted",
                                "Application submitted through LinkedIn Easy Apply.",
                                screenshot_path,
                            )

                        advanced = await self._advance_step(page, modal.first)
                        if not advanced:
                            break

                    if dry_run:
                        await self._discard_modal(page)
                        return (
                            "dry-run",
                            "Dry-run ended before final submit step.",
                            screenshot_path,
                        )

                    return (
                        "failed",
                        "Could not complete Easy Apply flow automatically.",
                        screenshot_path,
                    )
                finally:
                    await context.close()
                    await browser.close()
        except Exception as exc:
            if dry_run:
                return (
                    "dry-run",
                    f"LinkedIn dry-run fallback without submission: {exc}",
                    screenshot_path,
                )
            return ("failed", f"LinkedIn Easy Apply failed: {exc}", screenshot_path)

    async def _launch_browser(self, playwright: Playwright) -> Browser:
        launch_options: list[tuple[bool, str | None]] = [
            (self.headless, None),
            (self.headless, "msedge"),
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

        raise RuntimeError("Unable to launch browser for LinkedIn apply: " + " | ".join(errors))

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

        # Allow manual login/MFA in a visible browser window.
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

    async def _fill_answers(self, root: Locator, answers: list[FormAnswer]) -> None:
        for answer in answers:
            await self._fill_single(root, answer)

    async def _fill_single(self, root: Locator, answer: FormAnswer) -> None:
        locator = root.get_by_label(answer.label, exact=False)
        if await locator.count() == 0:
            locator = root.get_by_placeholder(answer.label, exact=False)
        if await locator.count() == 0:
            return

        field = locator.first
        tag_name = await field.evaluate("element => element.tagName.toLowerCase()")
        input_type = (await field.get_attribute("type") or "").lower()

        if input_type == "checkbox":
            normalized = answer.answer.strip().lower()
            if normalized in {"yes", "true", "1"}:
                await field.check()
            else:
                await field.uncheck()
            return

        if input_type == "radio":
            normalized = answer.answer.strip().lower()
            if normalized in {"yes", "true", "1"}:
                await field.check()
            return

        if tag_name == "select":
            try:
                await field.select_option(label=answer.answer)
            except Exception:
                await field.select_option(value=answer.answer)
            return

        await field.fill(answer.answer)

    async def _upload_cv(self, root: Locator, cv_path: str) -> None:
        path = Path(cv_path)
        if not path.exists():
            return

        file_input = root.locator("input[type='file']")
        if await file_input.count() > 0:
            await file_input.first.set_input_files(str(path.resolve()))

    async def _advance_step(self, page: Page, root: Locator) -> bool:
        labels = [
            r"^Next$",
            r"Siguiente",
            r"Continue",
            r"Continuar",
            r"Review",
            r"Revisar",
        ]

        for label in labels:
            button = root.get_by_role("button", name=re.compile(label, re.IGNORECASE))
            if await button.count() == 0:
                continue
            if await button.first.is_disabled():
                return False
            await button.first.click()
            await page.wait_for_timeout(1200)
            return True

        return False

    async def _discard_modal(self, page: Page) -> None:
        dismiss = page.get_by_role("button", name=re.compile(r"(dismiss|close|cerrar)", re.IGNORECASE))
        if await dismiss.count() > 0:
            await dismiss.first.click()
            await page.wait_for_timeout(300)

        discard = page.get_by_role("button", name=re.compile(r"(discard|descartar)", re.IGNORECASE))
        if await discard.count() > 0:
            await discard.first.click()
            await page.wait_for_timeout(300)

    async def _save_storage_state(self, context: BrowserContext) -> None:
        self.storage_state_path.parent.mkdir(parents=True, exist_ok=True)
        await context.storage_state(path=str(self.storage_state_path))

    def _step_screenshot_file(self, posting_id: str, step: int) -> Path:
        timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        return self.screenshot_dir / f"{posting_id}-linkedin-step{step}-{timestamp}.png"
