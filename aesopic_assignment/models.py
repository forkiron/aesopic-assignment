from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class PlannerOutput:
    platform: str
    repo: str
    goal: str
    fields: List[str]
    required_entities: List[str]
    success_criteria: List[str]
    search_query: str = ""  # e.g. "openclaw" to search from GitHub home


@dataclass
class Action:
    kind: str
    target: str | None = None
    value: str | None = None
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class NavigatorConfig:
    headless: bool = True
    timeout_ms: int = 20_000
    max_steps: int = 20
    min_confidence: float = 0.6
    action_delay_ms: int = 4_000  # slow down actions for rate limits / slow browsers
    slow_mo_ms: int = 0  # Playwright-level slow motion (ms) between low-level actions
    dom_probe_interval_ms: int = 10_000  # throttle DOM reads (text/a11y) for slow pages
    verbose: bool = False  # console logs of navigation steps
    screenshot_interval_steps: int = 1  # take screenshot every N steps
    screenshot_timeout_ms: int = 10_000  # screenshot timeout to avoid hangs


@dataclass
class Asset:
    name: str
    url: str


@dataclass
class ExtractedRelease:
    repository: str
    version: Optional[str] = None
    tag: Optional[str] = None
    author: Optional[str] = None
    published_at: Optional[str] = None
    notes: Optional[str] = None
    assets: List[Asset] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)
