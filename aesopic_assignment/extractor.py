from __future__ import annotations

import tempfile
from pathlib import Path
from typing import List, Optional

from .models import Asset, ExtractedRelease, PlannerOutput
from .playwright_driver import PlaywrightDriver
from .vision import VisionModel


class Extractor:
    """Extract latest release info. Uses vision when available (no hardcoded selectors)."""

    def __init__(self, driver: PlaywrightDriver, vision: Optional[VisionModel] = None) -> None:
        self.driver = driver
        self.vision = vision

    def extract_latest(self, plan: PlannerOutput) -> ExtractedRelease:
        release = ExtractedRelease(repository=plan.repo)
        release.raw = {"url": self.driver.url()}

        # Vision-based extraction (assignment: no hardcoded CSS selectors)
        if self.vision is not None:
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                path = f.name
            try:
                self.driver.page.screenshot(path=path, full_page=True)
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
                    return release
            finally:
                Path(path).unlink(missing_ok=True)

        # Fallback when no vision: minimal output, no selectors (assignment constraint)
        return release

