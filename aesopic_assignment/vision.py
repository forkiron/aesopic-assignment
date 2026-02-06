"""Vision interface: classify page + action, locate release region, parse release text, one-shot extract, extract-for-prompt. OpenAI implementation + stub."""
from __future__ import annotations

import base64
import json
import os
import sys
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from openai import OpenAI


@dataclass
class VisionDecision:
    confidence: float
    state: str
    found_entities: List[str]
    action: Optional[str] = None   # "type_search" | "click" | "done" | None
    target: Optional[str] = None  # for click: link text; for type_search: query string


class VisionModel:
    def classify_state(
        self,
        screenshot_path: Optional[str],
        required_entities: List[str],
        goal: str = "latest_release",
    ) -> VisionDecision:
        raise NotImplementedError

    def extract_release(
        self, screenshot_path: str, repository: str, user_prompt: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Extract latest release JSON from a releases page screenshot. No hardcoded selectors."""
        raise NotImplementedError

    def extract_for_prompt(
        self, screenshot_path: str, repository: str, user_prompt: str
    ) -> Optional[Dict[str, Any]]:
        """Extract from the current page whatever the user asked (e.g. root code, key features). Returns dict with 'result' key."""
        raise NotImplementedError

    def locate_latest_release_region(
        self, screenshot_path: str, page_height_px: int
    ) -> Optional[Dict[str, float]]:
        """From a releases page screenshot, return where the latest release block is: top_percent and bottom_percent (0-100) of page height."""
        raise NotImplementedError

    def parse_release_text(self, raw_text: str, repository: str) -> Optional[Dict[str, Any]]:
        """Turn raw release block text into structured release JSON (version, tag, author, published_at, notes, assets)."""
        raise NotImplementedError


class StubVisionModel(VisionModel):
    """
    Placeholder vision model.

    This intentionally does not perform real vision inference. It returns a low
    confidence result so the navigator falls back to DOM heuristics.
    """

    def classify_state(
        self,
        screenshot_path: Optional[str],
        required_entities: List[str],
        goal: str = "latest_release",
    ) -> VisionDecision:
        return VisionDecision(confidence=0.0, state="unknown", found_entities=[], action=None, target=None)

    def extract_release(
        self, screenshot_path: str, repository: str, user_prompt: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        return None

    def extract_for_prompt(
        self, screenshot_path: str, repository: str, user_prompt: str
    ) -> Optional[Dict[str, Any]]:
        return None

    def locate_latest_release_region(
        self, screenshot_path: str, page_height_px: int
    ) -> Optional[Dict[str, float]]:
        return None

    def parse_release_text(self, raw_text: str, repository: str) -> Optional[Dict[str, Any]]:
        return None


class OpenAIVisionModel(VisionModel):
    """Uses OpenAI Responses API for image inputs (classify, locate, extract_release, extract_for_prompt); Chat for parse_release_text."""
    def __init__(self, model: str = "gpt-4o-mini", max_tokens: int = 400) -> None:
        self.model = model
        self.max_tokens = max_tokens
        self.client = OpenAI()

    def classify_state(
        self,
        screenshot_path: Optional[str],
        required_entities: List[str],
        goal: str = "latest_release",
    ) -> VisionDecision:
        if not screenshot_path:
            return VisionDecision(confidence=0.0, state="unknown", found_entities=[], action=None, target=None)
        try:
            image_url = _image_to_data_url(screenshot_path)
            on_repo = (
                "On repo_page you're done (action=done, target empty). "
                if goal == "code"
                else "On repo_page go to Releases (action=click, target=Releases). "
            )
            goal_note = f" User goal: {goal}." if goal != "latest_release" else ""
            instructions = (
                "Look at this GitHub page and decide what kind of page it is and what to do next.\n\n"
                "Page types: home (main GitHub page), search_results (list of repos), repo_page (one repo's main page), releases_page (releases list), or unknown.\n\n"
                "What to do: on home, use the search bar (action=type_search, target=search query). "
                "On search_results, pick the right repo from the list (action=click, target=exact link text like owner/repo). "
                + on_repo
                + "On releases_page you're done (action=done). Otherwise action=none.\n\n"
                f"Note which of these you can see: {', '.join(required_entities)}. Set confidence 0-1."
                + goal_note
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
                "required": ["state", "confidence", "found_entities", "action", "target", "notes"],
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
        except Exception as e:
            print(f"[vision] classify_state failed: {type(e).__name__}: {e}", file=sys.stderr)
            return VisionDecision(confidence=0.0, state="unknown", found_entities=[], action=None, target=None)

    def extract_release(
        self, screenshot_path: str, repository: str, user_prompt: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Extract latest release from screenshot using vision (no hardcoded selectors)."""
        try:
            image_url = _image_to_data_url(screenshot_path)
            instructions = (
                "This is a GitHub releases page. One release is marked as the current latest (usually a green \"Latest\" badge near the top). "
                "Extract only that one — version, tag, author, published_at (use the date or relative time shown), notes (full body), and assets (name + url for each download). "
                "Ignore any older releases listed below."
            )
            if user_prompt and user_prompt.strip():
                instructions += f"\n\nUser also asked: \"{user_prompt.strip()}\" — include any relevant extra detail in notes (e.g. key features) if visible."
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
                            "assets": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {"name": {"type": "string"}, "url": {"type": "string"}},
                                    "required": ["name", "url"],
                                    "additionalProperties": False,
                                },
                            },
                        },
                        "required": ["version", "tag", "author", "published_at", "notes", "assets"],
                        "additionalProperties": False,
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
                max_output_tokens=1200,
            )
            payload = json.loads(response.output_text)
            lr = payload.get("latest_release") or {}
            assets = lr.get("assets") or []
            return {
                "repository": payload.get("repository") or repository,
                "version": lr.get("version"),
                "tag": lr.get("tag"),
                "author": lr.get("author"),
                "published_at": lr.get("published_at"),
                "notes": lr.get("notes"),
                "assets": [{"name": a.get("name", ""), "url": a.get("url", "")} for a in assets],
                "raw": {"url": None, "vision_extracted": True},
            }
        except Exception as e:
            print(f"[vision] extract_release failed: {type(e).__name__}: {e}", file=sys.stderr)
            return None

    def extract_for_prompt(
        self, screenshot_path: str, repository: str, user_prompt: str
    ) -> Optional[Dict[str, Any]]:
        """Extract from the current page what the user asked (e.g. root code, key features)."""
        try:
            image_url = _image_to_data_url(screenshot_path)
            instructions = (
                f"This is a GitHub page for {repository}. The user asked: \"{user_prompt.strip()}\". "
                "From what you see in the screenshot, answer their question — e.g. describe the code layout, "
                "list key features, or summarize visible info. Return a JSON object with one key 'result' (string or structured)."
            )
            schema = {
                "type": "object",
                "properties": {
                    "result": {
                        "oneOf": [
                            {"type": "string"},
                            {"type": "object"},
                            {"type": "array"},
                        ],
                    },
                },
                "required": ["result"],
                "additionalProperties": False,
            }
            response = self.client.responses.create(
                model=self.model,
                input=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": instructions},
                            {"type": "input_image", "image_url": image_url, "detail": "high"},
                        ],
                    }
                ],
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "prompt_result",
                        "schema": schema,
                        "strict": False,
                    }
                },
                max_output_tokens=1500,
            )
            payload = json.loads(response.output_text)
            result = payload.get("result")
            return {"repository": repository, "result": result}
        except Exception as e:
            print(f"[vision] extract_for_prompt failed: {type(e).__name__}: {e}", file=sys.stderr)
            return None

    def locate_latest_release_region(
        self, screenshot_path: str, page_height_px: int
    ) -> Optional[Dict[str, float]]:
        """Return top_percent and bottom_percent (0-100) where the latest release block is."""
        try:
            image_url = _image_to_data_url(screenshot_path)
            instructions = (
                "This is a GitHub releases page. You should see that it states (latest release) or (Latest) somewhere on the page. "
                "Identify where that single release block starts and ends vertically. Reply with two numbers as a percentage of the full page height: "
                "top_percent (where the latest release section starts, often near 0) and bottom_percent (where it ends, before the next release). "
                "Be precise so we capture only that block, not older releases below."
            )
            schema = {
                "type": "object",
                "properties": {
                    "top_percent": {"type": "number", "minimum": 0, "maximum": 100},
                    "bottom_percent": {"type": "number", "minimum": 0, "maximum": 100},
                },
                "required": ["top_percent", "bottom_percent"],
                "additionalProperties": False,
            }
            response = self.client.responses.create(
                model=self.model,
                input=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": instructions},
                            {"type": "input_text", "text": f"Page height in pixels: {page_height_px}"},
                            {"type": "input_image", "image_url": image_url, "detail": "high"},
                        ],
                    }
                ],
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "release_region",
                        "schema": schema,
                        "strict": True,
                    }
                },
                max_output_tokens=100,
            )
            payload = json.loads(response.output_text)
            top = float(payload.get("top_percent", 0))
            bottom = float(payload.get("bottom_percent", 30))
            if top >= bottom:
                bottom = top + 30  # Sanity: region has positive height
            return {"top_percent": top, "bottom_percent": min(100, bottom)}
        except Exception as e:
            print(f"[vision] locate_latest_release_region failed: {type(e).__name__}: {e}", file=sys.stderr)
            return None

    def parse_release_text(self, raw_text: str, repository: str) -> Optional[Dict[str, Any]]:
        """Turn raw text from the latest release block into structured JSON."""
        if not (raw_text or raw_text.strip()):
            return None
        try:
            system = (
                "You are given raw text from a GitHub release block. Extract and return a JSON object with keys: "
                "repository (string), latest_release (object with version, tag, author, published_at, notes, assets). "
                "assets is an array of {name, url}. Use only the text provided; leave fields empty if missing. "
                "Format the notes field for readability: use clean markdown (e.g. ## Changes then one line per bullet with '- '). "
                "One newline between bullets, at most one blank line between sections. No escaped newlines or messy whitespace."
            )
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": f"Repository: {repository}\n\nRaw text:\n{raw_text[:12000]}"},
                ],
                response_format={"type": "json_object"},
                max_tokens=2000,
            )
            content = resp.choices[0].message.content
            if not content:
                return None
            payload = json.loads(content)
            lr = payload.get("latest_release") or {}
            assets = lr.get("assets") or []
            notes = lr.get("notes")
            if isinstance(notes, str) and notes.strip():
                notes = _normalize_notes(notes)
            return {
                "repository": payload.get("repository") or repository,
                "version": lr.get("version"),
                "tag": lr.get("tag"),
                "author": lr.get("author"),
                "published_at": lr.get("published_at"),
                "notes": notes,
                "assets": [{"name": a.get("name", ""), "url": a.get("url", "")} for a in assets],
                "raw": {"url": None, "text_parsed": True},
            }
        except Exception as e:
            print(f"[vision] parse_release_text failed: {type(e).__name__}: {e}", file=sys.stderr)
            return None


def _normalize_notes(notes: str) -> str:
    """Collapse runs of blank lines to one; trim each line and the whole string."""
    if not notes or not notes.strip():
        return notes
    lines = [line.strip() for line in notes.splitlines()]
    out: List[str] = []
    prev_blank = False
    for ln in lines:
        if not ln:
            if not prev_blank:
                out.append("")
            prev_blank = True
            continue
        prev_blank = False
        out.append(ln)
    return "\n".join(out).strip()


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
