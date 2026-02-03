from __future__ import annotations

from dataclasses import asdict
from playwright.sync_api import Page, sync_playwright

from .models import Action, NavigatorConfig

_BROWSER_INSTALL_MSG = (
    "No browser available. Either:\n"
    "  1. Install Google Chrome and run again (we'll use it), or\n"
    "  2. Run: python -m playwright install chromium\n"
    "  3. Or run this pipeline on Google Colab (see README)."
)


class PlaywrightDriver:
    def __init__(self, config: NavigatorConfig) -> None:
        self.config = config
        self.playwright = sync_playwright().start()
        self.browser = None
        self.browser = self._launch_browser()
        self.page = self.browser.new_page()
        self.page.set_default_timeout(config.timeout_ms)
        if config.verbose:
            self.page.on(
                "console",
                lambda msg: print(f"[browser:{msg.type}] {msg.text}"),
            )
        # Reduce GPU/WebGL issues on slower machines.
        try:
            self.page.emulate_media(reduced_motion="reduce")
        except Exception:
            pass

    def _launch_browser(self):
        # Prefer system Chrome (no playwright install needed)
        for channel in ("chrome", "chromium", "msedge"):
            try:
                return self.playwright.chromium.launch(
                    headless=self.config.headless,
                    channel=channel,
                    slow_mo=self.config.slow_mo_ms,
                )
            except Exception:
                continue
        # Fallback: Playwright's bundled Chromium
        try:
            return self.playwright.chromium.launch(
                headless=self.config.headless,
                slow_mo=self.config.slow_mo_ms,
            )
        except Exception as e:
            self.playwright.stop()
            err_text = str(e).lower()
            if "executable doesn't exist" in err_text or "please run the following" in err_text:
                raise RuntimeError(_BROWSER_INSTALL_MSG) from e
            raise

    def close(self) -> None:
        if self.browser:
            self.browser.close()
        self.playwright.stop()

    def goto(self, url: str) -> None:
        self.page.goto(url, wait_until="domcontentloaded")
        # Assignment: no auth. Dismiss any GitHub "Sign in" prompt so we can use public pages.
        if "github.com" in url:
            self.page.keyboard.press("Escape")
            self.wait(300)

    def click_by_role(self, role: str, name: str) -> bool:
        locator = self.page.get_by_role(role, name=name)
        if locator.count() > 0:
            locator.first.click()
            return True
        return False

    def click_by_text(self, text: str) -> bool:
        locator = self.page.get_by_text(text, exact=False)
        if locator.count() > 0:
            locator.first.click()
            return True
        return False

    def fill_searchbox_and_submit(self, text: str) -> bool:
        """Find search by role/placeholder (no hardcoded selectors) and type + Enter."""
        search = self.page.get_by_role("searchbox")
        if search.count() == 0:
            search = self.page.get_by_placeholder("Search")
        if search.count() == 0:
            search = self.page.get_by_placeholder("Search or jump to...")
        if search.count() == 0:
            search = self.page.get_by_placeholder("Search GitHub")
        if search.count() == 0:
            return False
        search.first.fill(text)
        search.first.press("Enter")
        return True

    def goto_search(self, query: str) -> None:
        """Go straight to GitHub search results (avoids sign-up homepage)."""
        from urllib.parse import quote_plus
        self.goto(f"https://github.com/search?q={quote_plus(query)}&type=repositories")

    def type_text(self, selector: str, text: str, clear: bool = True) -> None:
        if clear:
            self.page.fill(selector, text)
        else:
            self.page.type(selector, text)

    def press(self, selector: str, key: str) -> None:
        self.page.press(selector, key)

    def scroll(self, amount: int = 800) -> None:
        self.page.mouse.wheel(0, amount)

    def back(self) -> None:
        self.page.go_back(wait_until="domcontentloaded")

    def wait(self, ms: int = 1000) -> None:
        self.page.wait_for_timeout(ms)

    def accessibility_snapshot(self) -> dict:
        """Return accessibility tree if available (deprecated in newer Playwright)."""
        try:
            acc = getattr(self.page, "accessibility", None)
            if acc is not None and hasattr(acc, "snapshot"):
                return acc.snapshot() or {}
        except Exception:
            pass
        return {}

    def title(self) -> str:
        return self.page.title()

    def url(self) -> str:
        return self.page.url
