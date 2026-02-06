"""Browser control only: launch (Chrome/Chromium/Edge), goto, screenshot, zoom, get text in Y-range. Semantic clicks and search; no DOM selectors."""
from __future__ import annotations

import re
from playwright.sync_api import sync_playwright

from .models import NavigatorConfig

_BROWSER_MSG = (
    "No browser. Install Chrome, or run: python -m playwright install chromium"
)

_DEFAULT_VIEWPORT = {"width": 1280, "height": 720}


def _get_viewport_from_screen() -> dict:
    """Match viewport to user's primary screen size (capped so window fits)."""
    try:
        import screeninfo
        monitors = screeninfo.get_monitors()
        if not monitors:
            return _DEFAULT_VIEWPORT
        primary = next((m for m in monitors if m.is_primary), monitors[0])
        # Use primary monitor dimensions; cap to avoid oversized window
        w = min(primary.width, 1920)
        h = min(primary.height, 1080)
        if w < 800 or h < 600:
            return _DEFAULT_VIEWPORT
        return {"width": w, "height": h}
    except Exception:
        return _DEFAULT_VIEWPORT


class PlaywrightDriver:
    def __init__(self, config: NavigatorConfig) -> None:
        self.config = config
        self.pw = sync_playwright().start()
        self.browser = self._launch()
        viewport = _get_viewport_from_screen()
        self.context = self.browser.new_context(viewport=viewport)
        self.page = self.context.new_page()
        self.page.set_default_timeout(config.timeout_ms)
        # Browser console not forwarded (was spamming ERR_FAILED from blocked resources)
        if config.block_resources:
            self._block_resources()
        try:
            self.page.emulate_media(reduced_motion="reduce")
        except Exception:
            pass

    def _launch(self):
        """Prefer system Chrome, then Chromium, then Edge; else bundled Chromium."""
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

    def scroll_releases_page_for_extraction(self) -> None:
        """Scroll the releases page so notes and download links below the fold are loaded/visible."""
        try:
            self.page.evaluate("window.scrollTo(0, 0)")
            self.wait(400)
            self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            self.wait(800)
            self.page.evaluate("window.scrollTo(0, 0)")
            self.wait(400)
        except Exception:
            pass

    def set_zoom(self, scale: float) -> None:
        """Zoom the page (e.g. 0.5 = 50%) so more content fits in view. Resets with scale=1."""
        try:
            self.page.evaluate(f"document.body.style.zoom = '{max(0.25, min(2, scale))}'")
            self.wait(300)
        except Exception:
            pass

    def get_page_height(self) -> int:
        """Total scroll height of the page in pixels."""
        try:
            return int(self.page.evaluate("document.documentElement.scrollHeight || document.body.scrollHeight"))
        except Exception:
            return 0

    def get_text_in_region(self, top_percent: float, bottom_percent: float) -> str:
        """Text nodes whose layout Y (getBoundingClientRect + scrollY) falls in [top_percent, bottom_percent] of page height, joined by newline."""
        try:
            return self.page.evaluate(
                """
                (function(topPct, bottomPct) {
                    var h = document.documentElement.scrollHeight || document.body.scrollHeight;
                    var y0 = (topPct / 100) * h;
                    var y1 = (bottomPct / 100) * h;
                    var out = [];
                    var walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, null, false);
                    var node;
                    while ((node = walker.nextNode())) {
                        var el = node.parentElement;
                        if (!el || el.offsetParent === null) continue;
                        var r = el.getBoundingClientRect();
                        var docY = r.top + window.scrollY;
                        if (docY >= y0 && docY <= y1)
                            out.push(node.textContent.trim());
                    }
                    return out.filter(Boolean).join('\\n');
                })
                """,
                top_percent,
                bottom_percent,
            )
        except Exception:
            return ""

    def click_by_role(self, role: str, name: str) -> bool:
        loc = self.page.get_by_role(role, name=name)
        if loc.count() == 0:
            return False
        try:
            current_url = self.page.url
            loc.first.scroll_into_view_if_needed()
            with self.page.expect_navigation(timeout=5000, wait_until="domcontentloaded"):
                loc.first.click(timeout=5000)
            return True
        except Exception:
            # Click succeeded but no navigation (e.g. button, not link)
            try:
                loc.first.click(timeout=5000)
                self.wait(500)  # Brief wait for any async updates
            except Exception:
                return False
            return True

    def click_by_text(self, text: str) -> bool:
        # Try link first (more likely to navigate)
        link_loc = self.page.get_by_role("link", name=text)
        if link_loc.count() > 0:
            try:
                link_loc.first.scroll_into_view_if_needed()
                with self.page.expect_navigation(timeout=5000, wait_until="domcontentloaded"):
                    link_loc.first.click(timeout=5000)
                return True
            except Exception:
                pass
        # Fallback to any text match
        loc = self.page.get_by_text(text, exact=False)
        if loc.count() > 0:
            try:
                loc.first.scroll_into_view_if_needed()
                with self.page.expect_navigation(timeout=5000, wait_until="domcontentloaded"):
                    loc.first.click(timeout=5000)
                return True
            except Exception:
                # Click succeeded but no navigation
                try:
                    loc.first.click(timeout=5000)
                    self.wait(500)
                except Exception:
                    return False
                return True
        return False

    def fill_search_and_submit(self, query: str) -> bool:
        """On GitHub: '/' focuses search, type + Enter. Else: find searchbox by role/placeholder and fill + Enter."""
        if "github.com" in self.page.url:
            self.page.keyboard.press("/")
            self.wait(500)
            self.page.keyboard.type(query, delay=80)
            self.wait(200)
            self.page.keyboard.press("Enter")
            try:
                self.page.wait_for_url(re.compile(r"github\.com/search\?q="), timeout=8000)
                return True
            except Exception:
                pass
            if "github.com/search" in self.page.url:
                return True
            return False
        search = self.page.get_by_role("searchbox")
        if search.count() == 0:
            search = self.page.get_by_placeholder("Search GitHub")
        if search.count() == 0:
            search = self.page.get_by_placeholder("Search or jump to...")
        if search.count() == 0:
            return False
        first = search.first
        try:
            first.click()
            self.wait(400)
            first.fill("")
            first.fill(query)
            first.press("Enter")
            return True
        except Exception:
            # Opener button: click to open dialog, wait for input, then fill.
            first.click()
            self.wait(800)
            input_loc = self.page.get_by_role("searchbox")
            if input_loc.count() == 0:
                input_loc = self.page.get_by_placeholder("Search GitHub")
            if input_loc.count() == 0:
                return False
            try:
                input_loc.first.wait_for(state="visible", timeout=2000)
            except Exception:
                pass
            input_loc.first.fill(query)
            input_loc.first.press("Enter")
            return True

    def url(self) -> str:
        return self.page.url

    def title(self) -> str:
        return self.page.title()
