"""Builds a plan from CLI: repo and/or prompt. With prompt, LLM infers repo and goal; with repo only, goal is latest_release."""
from __future__ import annotations

import os
import re
from dataclasses import asdict
from typing import Iterable, List, Optional

from .models import PlannerOutput

DEFAULT_FIELDS = ["version", "tag", "author", "published_at", "notes", "assets"]


def _extract_repo_and_goal_with_llm(prompt: str) -> tuple[Optional[str], str]:
    """Use an LLM to infer repo and goal from the user prompt. Goal: latest_release | code | custom."""
    if not prompt or not prompt.strip():
        return None, "latest_release"
    try:
        from openai import OpenAI
        if not (os.getenv("OPENAI_API_KEY") or "").strip():
            return None, "latest_release"
        client = OpenAI()
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "From the user's message, figure out which GitHub repo they mean (reply as owner/name) and what they want: latest_release (versions, releases, changelog), code (source/root code), or custom (features, docs, etc.). Reply in one line: repo: owner/name goal: <one of latest_release, code, custom>",
                },
                {"role": "user", "content": prompt.strip()},
            ],
            max_tokens=80,
        )
        text = (resp.choices[0].message.content or "").strip()
        repo = None
        goal = "latest_release"
        if "repo:" in text:
            m = re.search(r"repo:\s*([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)", text, re.I)
            if m:
                repo = m.group(1).strip()
        if "goal:" in text:
            g = re.search(r"goal:\s*(\w+)", text, re.I)
            if g and g.group(1).lower() in ("latest_release", "code", "custom"):
                goal = g.group(1).lower()
        return repo, goal
    except Exception:
        return None, "latest_release"


class Planner:
    """
    Text planner: prompt or repo -> plan. Uses LLM to interpret prompt when available, else regex/heuristic.
    """

    def plan(
        self,
        prompt: Optional[str],
        repo: Optional[str],
        fields: Optional[Iterable[str]] = None,
    ) -> PlannerOutput:
        has_explicit_repo = bool(repo and repo.strip())
        prompt_text = (prompt or "").strip()

        if has_explicit_repo:
            resolved_repo = (repo or "").strip()
            goal = "latest_release"
        elif prompt_text:
            llm_repo, goal = _extract_repo_and_goal_with_llm(prompt_text)
            resolved_repo = llm_repo or self._extract_repo(prompt_text)
        else:
            resolved_repo = None
            goal = "latest_release"

        if not resolved_repo:
            raise ValueError("Unable to resolve repo. Pass --repo owner/name or include it in --prompt.")

        normalized_fields = self._normalize_fields(fields)
        search_query = resolved_repo.split("/", 1)[-1] if "/" in resolved_repo else resolved_repo
        if goal == "latest_release":
            required_entities = [resolved_repo, "Releases"]
            success_criteria = [f"on releases page for {resolved_repo}", "latest release identified"]
        else:
            required_entities = [resolved_repo]
            success_criteria = [f"on repo or target page for {resolved_repo}"]

        return PlannerOutput(
            platform="github",
            repo=resolved_repo,
            goal=goal,
            fields=normalized_fields,
            required_entities=required_entities,
            success_criteria=success_criteria,
            search_query=search_query,
            user_prompt=prompt_text if prompt_text else None,
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
        """Regex/heuristic: owner/name first, else single word as owner/name (skip common verbs)."""
        if not text:
            return None
        match = re.search(r"([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)", text)
        if match:
            return match.group(1)
        skip = {"latest", "release", "find", "the", "and", "its", "key", "features", "list", "get", "search", "for", "current", "related", "tags", "releases"}
        words = re.findall(r"\b([a-zA-Z][a-zA-Z0-9_.-]{1,40})\b", text)
        for w in words:
            name = w.lower()
            if name not in skip and "/" not in w:
                return f"{w}/{w}"
        return None
