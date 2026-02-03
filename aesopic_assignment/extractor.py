from __future__ import annotations

import tempfile
from pathlib import Path
from typing import List, Optional

from .models import Asset, ExtractedRelease, PlannerOutput
from .playwright_driver import PlaywrightDriver
from .run_logging import RunLogger
from .vision import VisionModel


class Extractor:
    """Extract latest release info. Uses vision when available (no hardcoded selectors)."""

    def __init__(
        self,
        driver: PlaywrightDriver,
        vision: Optional[VisionModel] = None,
        logger: Optional[RunLogger] = None,
    ) -> None:
        self.driver = driver
        self.vision = vision
        self.logger = logger

    def extract_latest(self, plan: PlannerOutput) -> ExtractedRelease:
        release = ExtractedRelease(repository=plan.repo)
        release.raw = {"url": self.driver.url()}

        if self.logger:
            self.logger.log_event("[extract] start")

        # Vision-based extraction (assignment: no hardcoded CSS selectors)
        if self.vision is not None:
            if self.logger:
                self.logger.log_event("[extract] using vision")
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                path = f.name
            try:
                self.driver.page.screenshot(path=path, full_page=False, timeout=15000)
                data = self.vision.extract_release(path, plan.repo)
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
                Path(path).unlink(missing_ok=True)

        # Fallback when no vision: minimal output, no selectors (assignment constraint)
        if self.logger:
            self.logger.log_event("[extract] fallback (no vision)")
        return release

