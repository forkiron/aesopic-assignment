"""URL/title-based page state detection. Used when vision is unavailable or to override vision (e.g. we're on search results but screenshot looks like home)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PageState:
    name: str
    confidence: float
    reason: str


def detect_state(url: str, title: str, text_sample: str) -> PageState:
    """Infer page state from URL and title. text_sample is optional (e.g. for repo vs releases)."""
    normalized_title = title.lower()
    normalized_url = url.lower().rstrip("/")
    normalized_text = text_sample.lower()

    # Home must be checked before repo (both match github.com).
    if normalized_url in ("https://github.com", "http://github.com"):
        return PageState("home", 0.85, "GitHub homepage URL")
    if "/search" in normalized_url or "search results" in normalized_title:
        return PageState("search_results", 0.9, "url/title indicates search results")
    if "/releases" in normalized_url or "releases" in normalized_title:
        return PageState("releases_page", 0.9, "url/title indicates releases")
    if "github.com/search" in normalized_url or "search?q=" in normalized_url:
        return PageState("search_results", 0.7, "GitHub search URL")
    if "github.com" in normalized_url and "/" in normalized_url and "search" not in normalized_url:
        if "releases" in normalized_text:
            return PageState("repo_page", 0.7, "repo page text includes releases")
        return PageState("repo_page", 0.5, "github url structure")
    if "github" in normalized_title:
        return PageState("home", 0.4, "github landing title")
    return PageState("unknown", 0.2, "no match")
