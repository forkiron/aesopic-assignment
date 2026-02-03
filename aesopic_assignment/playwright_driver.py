"""Playwright driver: launch browser, goto, screenshot (viewport), click/fill. Vision is first layer; this executes."""
from __future__ import annotations

from urllib.parse import quote_plus
from playwright.sync_api import sync_playwright

from .models import NavigatorConfig

_BROWSER_MSG = (
    "No browser. Install Chrome, or run: python -m playwright install chromium"
)


class PlaywrightDriver:
    def __init__(self, config: NavigatorConfig) -> None:
        self.config = config
        self.pw = sync_playwright().start()
        self.browser = self._launch()
        self.context = self.browser.new_context(viewport={"width": 1920, "height": 1080})
        self.page = self.context.new_page()
        self.page.set_default_timeout(config.timeout_ms)
        if config.verbose:
            self.page.on("console", lambda m: print(f"[browser] {m.text}"))
        if config.block_resources:
            self._block_resources()
        try:
            self.page.emulate_media(reduced_motion="reduce")
        except Exception:
            pass

    def _launch(self):
        for channel in ("chrome", "chromium", "msedge"):
            try:
                return self.pw.chromium.launch(headless=self.config.headless, channel=channel)
            except Exception:
                continue
        try:
            return self.pw.chromium.launch(headless=self.config.headless)
        except Exception as e:
            self.pw.stop()
            if "executable doesn't exist" in str(e).lower() or "please run" in str(e).lower():
                raise RuntimeError(_BROWSER_MSG) from e
            raise

    def _block_resources(self):
        """Block heavy resources to reduce lag (Playwright best practice)."""
        def route(route):
            r = route.request
            if r.resource_type in ("image", "font", "media", "imageset"):
                return route.abort()
            return route.continue_()
        self.page.route("**/*", route)

    def close(self) -> None:
        try:
            if self.context:
                self.context.close()
            if self.browser:
                self.browser.close()
            self.pw.stop()
        except Exception:
            pass

    def goto(self, url: str) -> None:
        self.page.goto(url, wait_until="load", timeout=self.config.timeout_ms)
        self.page.wait_for_load_state("domcontentloaded", timeout=self.config.timeout_ms)
        self.wait(500)
        if "github.com" in url:
            self.page.keyboard.press("Escape")
            self.wait(300)

    def wait(self, ms: int) -> None:
        self.page.wait_for_timeout(ms)

    def click_by_role(self, role: str, name: str) -> bool:
        loc = self.page.get_by_role(role, name=name)
        if loc.count() > 0:
            loc.first.click()
            return True
        return False

    def click_by_text(self, text: str) -> bool:
        loc = self.page.get_by_text(text, exact=False)
        if loc.count() > 0:
            loc.first.click()
            return True
        return False

    def fill_search_and_submit(self, query: str) -> bool:
        search = self.page.get_by_role("searchbox")
        if search.count() == 0:
            search = self.page.get_by_placeholder("Search or jump to...")
        if search.count() == 0:
            search = self.page.get_by_placeholder("Search GitHub")
        if search.count() == 0:
            return False
        search.first.fill(query)
        search.first.press("Enter")
        return True

    def goto_search(self, query: str) -> None:
        self.goto(f"https://github.com/search?q={quote_plus(query)}&type=repositories")

    def url(self) -> str:
        return self.page.url

    def title(self) -> str:
        return self.page.title()
