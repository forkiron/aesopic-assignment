from __future__ import annotations

from dataclasses import asdict
from typing import Optional

from .models import Action, NavigatorConfig, PlannerOutput
from .playwright_driver import PlaywrightDriver
from .run_logging import RunLogger
from .state_machine import PageState, detect_state
from .vision import StubVisionModel, VisionModel, VisionDecision


class Navigator:
    def __init__(
        self,
        config: Optional[NavigatorConfig] = None,
        vision: Optional[VisionModel] = None,
        logger: Optional[RunLogger] = None,
    ) -> None:
        self.config = config or NavigatorConfig()
        self.vision = vision or StubVisionModel()
        self.logger = logger or RunLogger()
        self.driver = PlaywrightDriver(self.config)

    def close(self) -> None:
        self.driver.close()

    def run(self, plan: PlannerOutput) -> None:
        # Assignment flow: start at github.com, then search → click repo → click Releases
        github_home = "https://github.com"
        repo_url = f"https://github.com/{plan.repo}"
        self._act(Action(kind="goto", target=github_home))
        self._act(Action(kind="wait", value="1500"))

        for _ in range(self.config.max_steps):
            screenshot_path = self.logger.log_screenshot(self.driver.page)
            state, vision_state = self._observe(plan, screenshot_path)

            if state.name == "releases_page" and state.confidence >= self.config.min_confidence:
                return

            # Use vision's recommended action when confidence is high
            if vision_state.confidence >= self.config.min_confidence and vision_state.action:
                if vision_state.action == "done" and state.name == "releases_page":
                    return
                if vision_state.action == "type_search":
                    query = vision_state.target or plan.search_query
                    if self.driver.fill_searchbox_and_submit(query):
                        self._act(Action(kind="wait", value="2000"))
                        continue
                if vision_state.action == "click" and vision_state.target:
                    if self.driver.click_by_text(vision_state.target) or self.driver.click_by_role("link", vision_state.target):
                        self._act(Action(kind="wait", value="2000"))
                        continue

            # Heuristic fallbacks (semantic: role/text, no hardcoded CSS)
            if state.name == "repo_page":
                if self._click_releases_link():
                    self._act(Action(kind="wait", value="2000"))
                    continue

            if state.name == "home":
                if self.driver.fill_searchbox_and_submit(plan.search_query):
                    self._act(Action(kind="wait", value="2000"))
                    continue
                # Homepage is sign-up focused and has no visible search box → go straight to search
                self.driver.goto_search(plan.search_query)
                self._act(Action(kind="wait", value="2000"))
                continue
                self._act(Action(kind="goto", target=repo_url))
                continue

            if state.name == "search_results":
                if self.driver.click_by_text(plan.repo) or self.driver.click_by_role("link", plan.repo):
                    self._act(Action(kind="wait", value="2000"))
                    continue

            if self._verification_pass(plan.repo):
                return

        raise RuntimeError("Navigation failed: max steps exceeded")

    def _observe(self, plan: PlannerOutput, screenshot_path: str) -> tuple[PageState, VisionDecision]:
        title = self.driver.title()
        url = self.driver.url()
        text_sample = self.driver.page.locator("body").inner_text()[:2000]

        vision_state = self.vision.classify_state(screenshot_path, plan.required_entities)
        if vision_state.confidence >= self.config.min_confidence and self._entities_satisfied(
            plan.required_entities, vision_state.found_entities
        ):
            return PageState(vision_state.state, vision_state.confidence, "vision classification"), vision_state

        heuristic = detect_state(url=url, title=title, text_sample=text_sample)
        if self._a11y_verification_pass(plan):
            return heuristic, vision_state
        return heuristic, vision_state

    def _click_releases_link(self) -> bool:
        # Preferred: a11y role match, fallback to visible text.
        if self.driver.click_by_role("link", "Releases"):
            return True
        return self.driver.click_by_text("Releases")

    def _verification_pass(self, repo: str) -> bool:
        # Deterministic check on page content to see if repo appears.
        if repo.lower() in self.driver.page.locator("body").inner_text().lower():
            if "/releases" in self.driver.url().lower():
                return True
        return False

    def _a11y_verification_pass(self, plan: PlannerOutput) -> bool:
        snapshot = self.driver.accessibility_snapshot()
        if not snapshot:
            return False
        names = self._collect_a11y_names(snapshot)
        names_lower = " ".join(names).lower()
        for entity in plan.required_entities:
            if entity.lower() not in names_lower:
                return False
        return True

    def _entities_satisfied(self, required: list[str], found: list[str]) -> bool:
        if not required:
            return True
        found_lower = " ".join(found).lower()
        for entity in required:
            if entity.lower() not in found_lower:
                return False
        return True

    def _collect_a11y_names(self, node) -> list[str]:
        names = []
        if not isinstance(node, dict):
            return names
        name = node.get("name")
        if isinstance(name, str) and name.strip():
            names.append(name.strip())
        for child in node.get("children", []) or []:
            names.extend(self._collect_a11y_names(child))
        return names

    def _act(self, action: Action) -> None:
        self.logger.log_action(asdict(action))
        if action.kind == "goto" and action.target:
            self.driver.goto(action.target)
        elif action.kind == "click" and action.target:
            self.driver.click_by_text(action.target)
        elif action.kind == "wait":
            ms = int(action.value or "1000")
            self.driver.wait(ms)
        elif action.kind == "scroll":
            self.driver.scroll(int(action.value or "800"))
        elif action.kind == "back":
            self.driver.back()

        self.logger.bump()
