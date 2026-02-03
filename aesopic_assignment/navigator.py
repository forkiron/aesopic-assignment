"""Vision-first navigation: screenshot → OpenAI Vision → act via Playwright. No DOM scraping."""
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
        self.logger = logger or RunLogger(print_to_console=self.config.verbose)
        self.driver = PlaywrightDriver(self.config)

    def close(self) -> None:
        self.driver.close()

    def run(self, plan: PlannerOutput) -> None:
        github_home = "https://github.com"
        repo_url = f"https://github.com/{plan.repo}"
        self.logger.log_event(f"[nav] start repo={plan.repo} search_query={plan.search_query}")
        self.logger.log_event(f"[nav] action goto url={github_home}")
        self._act(Action(kind="goto", target=github_home))
        self._act(Action(kind="wait", value="2000"))

        for step in range(self.config.max_steps):
            screenshot_path = self.logger.log_screenshot(
                self.driver.page,
                timeout_ms=self.config.screenshot_timeout_ms,
            )
            state, vision_state = self._observe(plan, screenshot_path)
            self.logger.log_event(
                f"[nav] step={step+1} url={self.driver.url()!r} state={state.name} confidence={vision_state.confidence:.2f} action={vision_state.action or 'none'} target={vision_state.target or ''}"
            )

            # Done?
            if state.name == "releases_page" or vision_state.action == "done":
                self.logger.log_event("[nav] reached releases")
                return

            # Act from vision (first layer)
            if vision_state.action == "type_search":
                q = (vision_state.target or plan.search_query).strip()
                if q and self.driver.fill_search_and_submit(q):
                    self.logger.log_event(f"[nav] action fill_search query={q!r}")
                    self._act(Action(kind="wait", value="1500"))
                    continue
                self.logger.log_event(f"[nav] action goto_search query={plan.search_query!r}")
                self.driver.goto_search(plan.search_query)
                self._act(Action(kind="wait", value="1500"))
                continue

            if vision_state.action == "click" and vision_state.target:
                if self.driver.click_by_text(vision_state.target) or self.driver.click_by_role("link", vision_state.target):
                    self.logger.log_event(f"[nav] action click target={vision_state.target!r}")
                    self._act(Action(kind="wait", value="1500"))
                    continue

            # Fallback: URL-based (Playwright only, no DOM)
            if "/releases" in self.driver.url() and plan.repo in self.driver.url():
                self.logger.log_event("[nav] fallback already_on_releases")
                return
            if state.name == "repo_page":
                if self.driver.click_by_role("link", "Releases") or self.driver.click_by_text("Releases"):
                    self.logger.log_event("[nav] fallback click Releases")
                    self._act(Action(kind="wait", value="1500"))
                    continue
            if state.name == "home":
                self.logger.log_event(f"[nav] fallback goto_search query={plan.search_query!r}")
                self.driver.goto_search(plan.search_query)
                self._act(Action(kind="wait", value="1500"))
                continue
            if state.name == "search_results":
                if self.driver.click_by_text(plan.repo) or self.driver.click_by_role("link", plan.repo):
                    self.logger.log_event(f"[nav] fallback click repo={plan.repo!r}")
                    self._act(Action(kind="wait", value="1500"))
                    continue

            # Stuck: direct goto
            url = f"https://github.com/{plan.repo}/releases"
            self.logger.log_event(f"[nav] fallback direct goto url={url}")
            self.driver.goto(url)
            self._act(Action(kind="wait", value="1500"))

        raise RuntimeError("Navigation failed: max steps exceeded")

    def _observe(self, plan: PlannerOutput, screenshot_path: Optional[str]) -> tuple[PageState, VisionDecision]:
        vision_state = self.vision.classify_state(screenshot_path, plan.required_entities)
        if screenshot_path and vision_state.confidence > 0:
            return PageState(vision_state.state, vision_state.confidence, "vision"), vision_state
        url = self.driver.url()
        title = self.driver.title()
        heuristic = detect_state(url=url, title=title, text_sample="")
        return heuristic, vision_state

    def _act(self, action: Action) -> None:
        self.logger.log_action(asdict(action))
        if action.kind == "goto" and action.target:
            self.driver.goto(action.target)
        elif action.kind == "click" and action.target:
            self.driver.click_by_text(action.target)
        elif action.kind == "wait":
            ms = int(action.value or "1000")
            self.driver.wait(ms)
        if action.kind != "wait" and self.config.action_delay_ms > 0:
            self.driver.wait(self.config.action_delay_ms)
        self.logger.bump()
