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
    search_query: str = ""


@dataclass
class Action:
    kind: str
    target: str | None = None
    value: str | None = None
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class NavigatorConfig:
    headless: bool = False
    timeout_ms: int = 30_000
    max_steps: int = 15
    min_confidence: float = 0.5
    action_delay_ms: int = 1_000
    screenshot_timeout_ms: int = 8_000
    verbose: bool = True
    block_resources: bool = True  # block images/fonts to reduce lag (Playwright best practice)


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
