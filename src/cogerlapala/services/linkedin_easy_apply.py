from __future__ import annotations

import asyncio
import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from playwright.async_api import Browser, BrowserContext, Locator, Page, Playwright, async_playwright

from cogerlapala.models import FormAnswer, JobPosting

try:
    from openai import OpenAI
except Exception:  # pragma: no cover - optional dependency runtime guard
    OpenAI = None  # type: ignore[assignment]


class LinkedInEasyApplyAutomator:
    def __init__(
        self,
        storage_state_path: str,
        screenshot_dir: str,
        email: str | None = None,
        password: str | None = None,
        headless: bool = False,
        manual_login_timeout_seconds: int = 180,
        ai_api_key: str | None = None,
        ai_navigation_enabled: bool = True,
        ai_navigation_model: str = "gpt-4.1-mini",
        ai_navigation_max_attempts: int = 1,
    ) -> None:
        self.storage_state_path = Path(storage_state_path)
        self.screenshot_dir = Path(screenshot_dir)
        self.email = email
        self.password = password
        self.headless = headless
        self.manual_login_timeout_seconds = max(manual_login_timeout_seconds, 30)
        self.ai_navigation_enabled = ai_navigation_enabled
        self.ai_navigation_model = ai_navigation_model
        self.ai_navigation_max_attempts = max(ai_navigation_max_attempts, 0)
        self.ai_client = OpenAI(api_key=ai_api_key) if (ai_api_key and OpenAI) else None

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
                        "button",
                        name=re.compile(
                            r"(easy\s*apply|solicitud\s*sencilla|solicitud\s+simplificada|"
                            r"aplicar\s+facilmente|solicitar\s+facilmente)",
                            re.IGNORECASE,
                        ),
                    )
                    if await easy_apply_button.count() == 0:
                        return await self._handle_external_apply(
                            page=page,
                            posting=posting,
                            answers=answers,
                            cv_path=cv_path,
                            dry_run=dry_run,
                            screenshot_each_step=screenshot_each_step,
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

                        advanced = await self._advance_step(page, modal.first, step)
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

    async def _handle_external_apply(
        self,
        page: Page,
        posting: JobPosting,
        answers: list[FormAnswer],
        cv_path: str | None,
        dry_run: bool,
        screenshot_each_step: bool,
    ) -> tuple[Literal["dry-run", "submitted", "failed"], str, str | None]:
        screenshot_path: str | None = None

        apply_control = await self._find_external_apply_control(page)
        if apply_control is None:
            if screenshot_each_step:
                screenshot_path = str(self._external_step_screenshot_file(posting.id, 0))
                await page.screenshot(path=screenshot_path, full_page=True)
            return (
                "failed",
                "Easy Apply not available and no external Apply control was found.",
                screenshot_path,
            )

        target_page = await self._click_apply_control(page, apply_control)

        for step in range(1, 9):
            root = target_page.locator("body")
            await self._fill_answers(root, answers)
            if cv_path:
                await self._upload_cv(root, cv_path)

            if screenshot_each_step:
                screenshot_path = str(self._external_step_screenshot_file(posting.id, step))
                await target_page.screenshot(path=screenshot_path, full_page=True)

            submit_control = await self._find_submit_control(target_page)
            if submit_control is not None:
                if dry_run:
                    return (
                        "dry-run",
                        "Reached submit in external apply flow. Submission skipped by dry-run.",
                        screenshot_path,
                    )

                await submit_control.click()
                await target_page.wait_for_timeout(1800)
                return (
                    "submitted",
                    "Application submitted through external apply flow.",
                    screenshot_path,
                )

            advanced = await self._advance_step(page=target_page, root=root, step=100 + step)
            if not advanced:
                break

        if dry_run:
            return (
                "dry-run",
                "External apply opened but submit step was not reached.",
                screenshot_path,
            )

        return (
            "failed",
            "External apply flow could not reach a submit action.",
            screenshot_path,
        )

    async def _find_external_apply_control(self, page: Page) -> Locator | None:
        apply_pattern = re.compile(
            r"(apply|apply\s*now|solicitar|postular|inscribirse|candidatar)",
            re.IGNORECASE,
        )

        forbidden = [
            "easy apply",
            "solicitud sencilla",
            "saved",
            "guardado",
        ]

        button = await self._first_clickable_control(
            root=page,
            role="button",
            pattern=apply_pattern,
            forbidden_words=forbidden,
        )
        if button is not None:
            return button

        link = await self._first_clickable_control(
            root=page,
            role="link",
            pattern=apply_pattern,
            forbidden_words=forbidden,
        )
        if link is not None:
            return link

        css_fallbacks = [
            "button.jobs-apply-button",
            "a.jobs-apply-button",
            "button[data-control-name*='apply']",
            "a[data-control-name*='apply']",
        ]

        for selector in css_fallbacks:
            control = page.locator(selector)
            count = await control.count()
            for index in range(min(count, 8)):
                current = control.nth(index)
                try:
                    if not await current.is_visible():
                        continue
                    if selector.startswith("button") and await current.is_disabled():
                        continue
                except Exception:
                    continue

                text = await self._read_control_text(current)
                lower = text.lower()
                if any(word in lower for word in forbidden):
                    continue
                if self._is_dangerous_button_label(lower):
                    continue

                return current

        return None

    async def _find_submit_control(self, page: Page) -> Locator | None:
        submit_pattern = re.compile(
            r"(submit|send\s*application|enviar\s*solicitud|postular|solicitar|finish|done)",
            re.IGNORECASE,
        )
        by_role = await self._first_clickable_control(
            root=page,
            role="button",
            pattern=submit_pattern,
            forbidden_words=["cancel", "dismiss", "close", "cerrar", "descartar"],
        )
        if by_role is not None:
            return by_role

        submit_inputs = page.locator("input[type='submit'], button[type='submit']")
        count = await submit_inputs.count()
        for index in range(min(count, 10)):
            control = submit_inputs.nth(index)
            try:
                if not await control.is_visible():
                    continue
                if await control.is_disabled():
                    continue
            except Exception:
                continue

            text = await self._read_control_text(control)
            if self._is_dangerous_button_label(text):
                continue
            return control

        return None

    async def _click_apply_control(self, page: Page, control: Locator) -> Page:
        context = page.context
        opened_page: Page | None = None

        try:
            async with context.expect_page(timeout=4000) as page_info:
                await control.click()
            opened_page = page_info.value
        except Exception:
            pass

        target_page = opened_page or page
        await target_page.wait_for_timeout(1600)
        return target_page

    async def _first_clickable_control(
        self,
        root: Page | Locator,
        role: str,
        pattern: re.Pattern[str],
        forbidden_words: list[str],
    ) -> Locator | None:
        controls = root.get_by_role(role, name=pattern)
        count = await controls.count()
        for index in range(min(count, 30)):
            control = controls.nth(index)
            try:
                if not await control.is_visible():
                    continue
                if role == "button" and await control.is_disabled():
                    continue
            except Exception:
                continue

            text = await self._read_control_text(control)
            lower = text.lower()
            if any(word in lower for word in forbidden_words):
                continue
            if self._is_dangerous_button_label(lower):
                continue

            return control

        return None

    async def _read_control_text(self, control: Locator) -> str:
        parts: list[str] = []
        try:
            parts.append((await control.inner_text()).strip())
        except Exception:
            pass
        for attr in ["aria-label", "title"]:
            try:
                value = (await control.get_attribute(attr) or "").strip()
            except Exception:
                value = ""
            if value:
                parts.append(value)
        return " ".join(part for part in parts if part).strip()

    async def _advance_step(self, page: Page, root: Locator, step: int) -> bool:
        labels = [
            r"^Next$",
            r"Siguiente",
            r"Continue",
            r"Continuar",
            r"Review",
            r"Revisar",
            r"Continue to next step",
            r"Go to review",
            r"Revisar solicitud",
        ]

        for label in labels:
            button = root.get_by_role("button", name=re.compile(label, re.IGNORECASE))
            if await button.count() == 0:
                continue
            if await button.first.is_disabled():
                continue
            await button.first.click()
            await page.wait_for_timeout(1200)
            return True

        if self.ai_navigation_enabled and self.ai_client and self.ai_navigation_max_attempts > 0:
            for _ in range(self.ai_navigation_max_attempts):
                clicked = await self._advance_step_with_ai(page=page, root=root, step=step)
                if clicked:
                    return True

        return False

    async def _advance_step_with_ai(self, page: Page, root: Locator, step: int) -> bool:
        candidates = await self._collect_button_candidates(root)
        if not candidates:
            return False

        modal_text = (await root.inner_text()).strip()
        modal_text = modal_text[:3500]

        prompt_payload = {
            "goal": "Choose the best button to continue a LinkedIn Easy Apply flow.",
            "step": step,
            "modal_text": modal_text,
            "buttons": candidates,
            "rules": [
                "Prefer next/continue/review/submit progression",
                "Never choose dismiss, close, cancel, discard, not now",
                "If no valid progression button exists, return action=none",
                "Return strict JSON only",
            ],
            "response_schema": {
                "action": "click | none",
                "button_id": "number or null",
                "reason": "short string",
            },
        }

        try:
            assert self.ai_client is not None
            response = await asyncio.to_thread(
                self.ai_client.responses.create,
                model=self.ai_navigation_model,
                input=[
                    {
                        "role": "system",
                        "content": (
                            "You are an assistant choosing which button to click in a job application modal. "
                            "Return JSON only."
                        ),
                    },
                    {"role": "user", "content": json.dumps(prompt_payload)},
                ],
                text={"format": {"type": "json_object"}},
            )
            text = self._extract_output_text(response)
            decision = json.loads(text)
        except Exception:
            return False

        action = str(decision.get("action", "none")).strip().lower()
        if action != "click":
            return False

        chosen_id = decision.get("button_id")
        if not isinstance(chosen_id, int):
            return False

        chosen = next((item for item in candidates if item["id"] == chosen_id), None)
        if not chosen:
            return False

        label_text = str(chosen.get("text", ""))
        if self._is_dangerous_button_label(label_text):
            return False

        button = root.locator("button").nth(chosen_id)
        if await button.count() == 0:
            return False
        if await button.is_disabled():
            return False

        await button.click()
        await page.wait_for_timeout(1400)
        return True

    async def _collect_button_candidates(self, root: Locator) -> list[dict[str, Any]]:
        buttons = root.locator("button")
        count = await buttons.count()
        candidates: list[dict[str, Any]] = []

        for index in range(min(count, 40)):
            button = buttons.nth(index)
            try:
                if not await button.is_visible():
                    continue
                if await button.is_disabled():
                    continue
            except Exception:
                continue

            text = (await button.inner_text()).strip()
            aria_label = (await button.get_attribute("aria-label") or "").strip()
            title = (await button.get_attribute("title") or "").strip()
            merged_text = " ".join(part for part in [text, aria_label, title] if part).strip()
            if not merged_text:
                continue
            if self._is_dangerous_button_label(merged_text):
                continue

            candidates.append(
                {
                    "id": index,
                    "text": merged_text,
                }
            )

        return candidates

    def _is_dangerous_button_label(self, label: str) -> bool:
        lower = label.lower()
        danger_words = [
            "dismiss",
            "discard",
            "cancel",
            "close",
            "not now",
            "cerrar",
            "descartar",
            "cancelar",
            "omitir",
            "salir",
        ]
        return any(word in lower for word in danger_words)

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

        raise ValueError("OpenAI response did not contain text output")

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

    def _external_step_screenshot_file(self, posting_id: str, step: int) -> Path:
        timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        return self.screenshot_dir / f"{posting_id}-external-step{step}-{timestamp}.png"
