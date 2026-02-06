from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .models import Asset, ExtractedRelease, PlannerOutput
from .playwright_driver import PlaywrightDriver
from .run_logging import RunLogger
from .vision import VisionModel


class Extractor:
    """Extract based on plan goal: latest_release -> fixed release JSON; code/custom -> prompt-driven result."""

    def __init__(
        self,
        driver: PlaywrightDriver,
        vision: Optional[VisionModel] = None,
        logger: Optional[RunLogger] = None,
    ) -> None:
        self.driver = driver
        self.vision = vision
        self.logger = logger

    def extract(self, plan: PlannerOutput) -> Union[ExtractedRelease, Dict[str, Any]]:
        """Dispatch by goal: latest_release -> ExtractedRelease; code/custom -> flexible dict with 'result'."""
        if plan.goal == "latest_release":
            return self._extract_release(plan)
        return self._extract_for_prompt(plan)

    def _extract_release(self, plan: PlannerOutput) -> ExtractedRelease:
        release = ExtractedRelease(repository=plan.repo)
        release.raw = {"url": self.driver.url()}

        if self.logger:
            self.logger.log_event("[extract] start (goal=latest_release)")

        if self.vision is not None:
            if self.logger:
                self.logger.log_event("[extract] zoom out, locate latest block, get text, parse")
            self.driver.scroll_releases_page_for_extraction()
            self.driver.set_zoom(0.5)
            self.driver.wait(400)
            self.driver.page.evaluate("window.scrollTo(0, 0)")
            self.driver.wait(300)
            page_height = self.driver.get_page_height()
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                path = f.name
            try:
                self.driver.page.screenshot(path=path, full_page=True, timeout=20000)
                region = self.vision.locate_latest_release_region(path, page_height)
                if region:
                    top_pct = region.get("top_percent", 0)
                    bottom_pct = region.get("bottom_percent", 40)
                    raw_text = self.driver.get_text_in_region(top_pct, bottom_pct)
                    if raw_text and raw_text.strip():
                        data = self.vision.parse_release_text(raw_text.strip(), plan.repo)
                        if data:
                            release.repository = data.get("repository") or plan.repo
                            release.version = data.get("version")
                            release.tag = data.get("tag")
                            release.author = data.get("author")
                            release.published_at = data.get("published_at")
                            release.notes = data.get("notes")
                            release.raw.update(data.get("raw") or {})
                            if data.get("assets"):
                                release.assets = [
                                    Asset(name=a.get("name", ""), url=a.get("url", ""))
                                    for a in data["assets"]
                                ]
                            if self.logger:
                                self.logger.log_event(
                                    f"[extract] done (locate+text+parse) version={release.version!r} tag={release.tag!r} author={release.author!r}"
                                )
                            return release
                # Fallback: one-shot vision extraction
                if self.logger:
                    self.logger.log_event("[extract] fallback: vision extract_release")
                self.driver.set_zoom(1.0)
                self.driver.scroll_releases_page_for_extraction()
                self.driver.page.screenshot(path=path, full_page=False, timeout=20000)
                data = self.vision.extract_release(path, plan.repo, user_prompt=plan.user_prompt)
                if data:
                    release.repository = data.get("repository") or plan.repo
                    release.version = data.get("version")
                    release.tag = data.get("tag")
                    release.author = data.get("author")
                    release.published_at = data.get("published_at")
                    release.notes = data.get("notes")
                    release.raw.update(data.get("raw") or {})
                    if data.get("assets"):
                        release.assets = [
                            Asset(name=a.get("name", ""), url=a.get("url", ""))
                            for a in data["assets"]
                        ]
                    if self.logger:
                        self.logger.log_event(
                            f"[extract] done vision version={release.version!r} tag={release.tag!r} author={release.author!r}"
                        )
                    return release
            finally:
                try:
                    self.driver.set_zoom(1.0)
                except Exception:
                    pass
                Path(path).unlink(missing_ok=True)

        if self.logger:
            self.logger.log_event("[extract] fallback (no vision)")
        return release

    def _extract_for_prompt(self, plan: PlannerOutput) -> Dict[str, Any]:
        """Screenshot current page and extract what the user asked (goal=code or custom)."""
        if self.logger:
            self.logger.log_event(f"[extract] start (goal={plan.goal}) prompt-driven")
        prompt_text = (plan.user_prompt or "").strip() or "What is visible on this page?"
        out: Dict[str, Any] = {"repository": plan.repo, "result": None}

        if self.vision is not None:
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                path = f.name
            try:
                self.driver.page.screenshot(path=path, full_page=True, timeout=20000)
                data = self.vision.extract_for_prompt(path, plan.repo, prompt_text)
                if data:
                    out["repository"] = data.get("repository", plan.repo)
                    out["result"] = data.get("result")
                if self.logger:
                    self.logger.log_event("[extract] done prompt-driven")
            finally:
                Path(path).unlink(missing_ok=True)
        return out

