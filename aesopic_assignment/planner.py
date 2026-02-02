from __future__ import annotations

import re
from dataclasses import asdict
from typing import Iterable, List, Optional

from .models import PlannerOutput

DEFAULT_FIELDS = ["version", "tag", "author", "published_at", "notes", "assets"]


class Planner:
    """
    Simple text planner that turns a prompt or repo into a strict spec.

    This is intentionally minimal and deterministic; replace with an LLM if desired.
    """

    def plan(
        self,
        prompt: Optional[str],
        repo: Optional[str],
        fields: Optional[Iterable[str]] = None,
    ) -> PlannerOutput:
        resolved_repo = repo or self._extract_repo(prompt or "")
        if not resolved_repo:
            raise ValueError("Unable to resolve repo. Pass --repo owner/name or include it in --prompt.")

        normalized_fields = self._normalize_fields(fields)
        # Search query: repo name (assignment: search for "openclaw")
        search_query = resolved_repo.split("/", 1)[-1] if "/" in resolved_repo else resolved_repo
        return PlannerOutput(
            platform="github",
            repo=resolved_repo,
            goal="latest_release",
            fields=normalized_fields,
            required_entities=[resolved_repo, "Releases"],
            success_criteria=[
                f"on releases page for {resolved_repo}",
                "latest release identified by newest date or latest label",
            ],
            search_query=search_query,
        )

    def to_json(self, plan: PlannerOutput) -> dict:
        return asdict(plan)

    def _normalize_fields(self, fields: Optional[Iterable[str]]) -> List[str]:
        if not fields:
            return list(DEFAULT_FIELDS)
        clean = []
        for value in fields:
            candidate = value.strip()
            if candidate:
                clean.append(candidate)
        return clean or list(DEFAULT_FIELDS)

    def _extract_repo(self, text: str) -> Optional[str]:
        if not text:
            return None
        match = re.search(r"([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)", text)
        if match:
            return match.group(1)
        return None
