from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from openai import OpenAI


@dataclass
class VisionDecision:
    confidence: float
    state: str
    found_entities: List[str]
    action: Optional[str] = None   # "type_search" | "click" | "done" | None
    target: Optional[str] = None  # for click: link text; for type_search: query string


class VisionModel:
    def classify_state(self, screenshot_path: str, required_entities: List[str]) -> VisionDecision:
        raise NotImplementedError

    def locate_target(self, screenshot_path: str, label: str) -> Optional[Tuple[int, int]]:
        raise NotImplementedError

    def extract_release(self, screenshot_path: str, repository: str) -> Optional[Dict[str, Any]]:
        """Extract latest release JSON from a releases page screenshot. No hardcoded selectors."""
        raise NotImplementedError


class StubVisionModel(VisionModel):
    """
    Placeholder vision model.

    This intentionally does not perform real vision inference. It returns a low
    confidence result so the navigator falls back to DOM heuristics.
    """

    def classify_state(self, screenshot_path: str, required_entities: List[str]) -> VisionDecision:
        return VisionDecision(confidence=0.0, state="unknown", found_entities=[], action=None, target=None)

    def locate_target(self, screenshot_path: str, label: str) -> Optional[Tuple[int, int]]:
        return None

    def extract_release(self, screenshot_path: str, repository: str) -> Optional[Dict[str, Any]]:
        return None


class OpenAIVisionModel(VisionModel):
    def __init__(self, model: str = "gpt-4o-mini", max_tokens: int = 400) -> None:
        self.model = model
        self.max_tokens = max_tokens
        self.client = OpenAI()

    def classify_state(self, screenshot_path: str, required_entities: List[str]) -> VisionDecision:
        try:
            image_url = _image_to_data_url(screenshot_path)
            instructions = (
                "You are a vision agent that classifies GitHub pages and decides the next navigation action.\n"
                "Identify the page state: home (GitHub homepage), search_results (list of repo results), repo_page (single repo), releases_page (releases list), unknown.\n\n"
                "Decide the next action:\n"
                "- If state is home: use the top search bar. Set action=type_search and target=<search query> (e.g. 'openclaw' for repo openclaw/openclaw).\n"
                "- If state is search_results: you see a LIST of repositories. Use reasoning: which result is the CORRECT repo? Consider repo name, owner, description, stars. Return action=click and target=<exact link text to click>, e.g. 'openclaw/openclaw' (the owner/name of the right repo from the list).\n"
                "- If state is repo_page: set action=click and target=Releases.\n"
                "- If state is releases_page: set action=done and target to empty string.\n"
                "- If unknown: set action=none and target to empty string.\n\n"
                "List which required entities are visible. Return confidence 0-1."
            )
            schema = {
                "type": "object",
                "properties": {
                    "state": {
                        "type": "string",
                        "enum": ["home", "search_results", "repo_page", "releases_page", "unknown"],
                    },
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "found_entities": {"type": "array", "items": {"type": "string"}},
                    "action": {"type": "string", "enum": ["type_search", "click", "done", "none"]},
                    "target": {"type": "string"},
                    "notes": {"type": "string"},
                },
                "required": ["state", "confidence", "found_entities", "action", "target"],
                "additionalProperties": False,
            }

            response = self.client.responses.create(
                model=self.model,
                input=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": instructions},
                            {
                                "type": "input_text",
                                "text": f"Required entities: {', '.join(required_entities)}",
                            },
                            {"type": "input_image", "image_url": image_url, "detail": "auto"},
                        ],
                    }
                ],
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "vision_state",
                        "schema": schema,
                        "strict": True,
                    }
                },
                max_output_tokens=self.max_tokens,
            )

            payload = json.loads(response.output_text)
            action = (payload.get("action") or "none").strip().lower()
            target = payload.get("target") or ""
            if action == "none":
                action = None
            if not (target and str(target).strip()):
                target = None
            else:
                target = str(target).strip()
            return VisionDecision(
                confidence=float(payload["confidence"]),
                state=payload["state"],
                found_entities=list(payload.get("found_entities", [])),
                action=action,
                target=str(target).strip() if target else None,
            )
        except Exception:
            return VisionDecision(confidence=0.0, state="unknown", found_entities=[], action=None, target=None)

    def extract_release(self, screenshot_path: str, repository: str) -> Optional[Dict[str, Any]]:
        """Extract latest release from screenshot using vision (no hardcoded selectors)."""
        try:
            image_url = _image_to_data_url(screenshot_path)
            instructions = (
                "You are viewing a GitHub repository Releases page. Extract the LATEST (most recent) release "
                "as structured JSON. Use only what you see in the screenshot; do not assume.\n"
                "Return: repository (owner/name), latest_release with version (or tag string), tag (git tag if visible), author."
            )
            schema = {
                "type": "object",
                "properties": {
                    "repository": {"type": "string"},
                    "latest_release": {
                        "type": "object",
                        "properties": {
                            "version": {"type": "string"},
                            "tag": {"type": "string"},
                            "author": {"type": "string"},
                            "published_at": {"type": "string"},
                            "notes": {"type": "string"},
                        },
                        "required": [],
                        "additionalProperties": True,
                    },
                },
                "required": ["repository", "latest_release"],
                "additionalProperties": False,
            }
            response = self.client.responses.create(
                model=self.model,
                input=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": instructions},
                            {"type": "input_text", "text": f"Repository: {repository}"},
                            {"type": "input_image", "image_url": image_url, "detail": "high"},
                        ],
                    }
                ],
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "release_data",
                        "schema": schema,
                        "strict": True,
                    }
                },
                max_output_tokens=600,
            )
            payload = json.loads(response.output_text)
            lr = payload.get("latest_release") or {}
            return {
                "repository": payload.get("repository") or repository,
                "version": lr.get("version"),
                "tag": lr.get("tag"),
                "author": lr.get("author"),
                "published_at": lr.get("published_at"),
                "notes": lr.get("notes"),
                "assets": [],
                "raw": {"url": None, "vision_extracted": True},
            }
        except Exception:
            return None


def _image_to_data_url(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    mime = "image/png"
    if ext in {".jpg", ".jpeg"}:
        mime = "image/jpeg"
    elif ext == ".webp":
        mime = "image/webp"
    elif ext == ".gif":
        mime = "image/gif"

    with open(path, "rb") as handle:
        encoded = base64.b64encode(handle.read()).decode("ascii")
    return f"data:{mime};base64,{encoded}"
