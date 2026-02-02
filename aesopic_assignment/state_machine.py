from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PageState:
    name: str
    confidence: float
    reason: str


def detect_state(url: str, title: str, text_sample: str) -> PageState:
    normalized_title = title.lower()
    normalized_url = url.lower()
    normalized_text = text_sample.lower()

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
    if "github" in normalized_title or normalized_url == "https://github.com/" or normalized_url == "https://github.com":
        return PageState("home", 0.4, "github landing")
    return PageState("unknown", 0.2, "no match")
