from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Literal

from playwright.async_api import Browser, Page, Playwright, async_playwright

from cogerlapala.models import FormAnswer, JobPosting


class BrowserAutomator:
    def __init__(self, screenshot_dir: str) -> None:
        self.screenshot_dir = Path(screenshot_dir)

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
                try:
                    page = await browser.new_page()
                    await page.goto(posting.url, timeout=45000, wait_until="domcontentloaded")

                    for answer in answers:
                        await self._fill_field(page, answer)

                    if cv_path:
                        await self._try_upload_cv(page, cv_path)

                    if screenshot_each_step:
                        screenshot_path = str(self._screenshot_file(posting.id))
                        await page.screenshot(path=screenshot_path, full_page=True)

                    if dry_run:
                        return (
                            "dry-run",
                            "Form completed in dry-run mode. Submission skipped.",
                            screenshot_path,
                        )

                    await self._submit(page)
                    return (
                        "submitted",
                        "Application submitted by browser automation.",
                        screenshot_path,
                    )
                finally:
                    await browser.close()
        except Exception as exc:
            if dry_run:
                return (
                    "dry-run",
                    f"Dry-run fallback without browser automation: {exc}",
                    screenshot_path,
                )
            return ("failed", f"Browser automation failed: {exc}", screenshot_path)

    async def _launch_browser(self, playwright: Playwright) -> Browser:
        # Try multiple launch strategies because some Windows setups cannot spawn headless shell.
        launch_options = [
            {"headless": True},
            {"headless": False},
            {"headless": True, "channel": "msedge"},
            {"headless": False, "channel": "msedge"},
        ]
        launch_errors: list[str] = []

        for options in launch_options:
            try:
                return await playwright.chromium.launch(**options)
            except Exception as exc:
                launch_errors.append(f"options={options} error={exc}")

        raise RuntimeError(
            "Unable to launch Chromium. Tried fallbacks. "
            + " | ".join(launch_errors)
        )

    async def _fill_field(self, page: Page, answer: FormAnswer) -> None:
        locator = page.get_by_label(answer.label, exact=False)
        if await locator.count() == 0:
            locator = page.get_by_placeholder(answer.label, exact=False)
        if await locator.count() == 0:
            return

        field = locator.first
        tag_name = await field.evaluate("element => element.tagName.toLowerCase()")
        input_type = await field.get_attribute("type")

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

    async def _try_upload_cv(self, page: Page, cv_path: str) -> None:
        path = Path(cv_path)
        if not path.exists():
            return

        file_input = page.locator("input[type='file']")
        if await file_input.count() > 0:
            await file_input.first.set_input_files(str(path.resolve()))

    async def _submit(self, page: Page) -> None:
        submit_button = page.get_by_role(
            "button", name=re.compile(r"(apply|submit|enviar|postular)", re.IGNORECASE)
        )
        if await submit_button.count() == 0:
            raise RuntimeError("No submit button found")
        await submit_button.first.click()

    def _screenshot_file(self, posting_id: str) -> Path:
        timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        return self.screenshot_dir / f"{posting_id}-{timestamp}.png"
