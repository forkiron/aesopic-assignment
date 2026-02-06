# Observations Document

## Approach

- **Vision-first navigation:** Each step takes a viewport screenshot, sends it to an OpenAI vision model (e.g. gpt-4o-mini), and uses the model’s classification (home, search_results, repo_page, releases_page) and suggested action (type_search, click, done) to decide what to do next. Playwright then performs the action (search bar focus/type, or click by role/text).

- **URL as backup:** When the screenshot is ambiguous (e.g. search results page still shows the same header as home), the current URL is used to override state so we don’t get stuck.

- **Extraction:** The target page is not fixed to “releases” only: the flow is driven by the goal (currently “latest release”), but the same pattern (navigate → scroll → full-page screenshot → vision) can apply to other pages (e.g. Code, Issues, Wiki) if the goal or prompt asks for different info. For the current “latest release” goal we: scroll the releases page to load content below the fold, take a full-page screenshot, and send it to the vision model to extract **additional metadata**: release notes, download links (assets), publish date, plus version, tag, author. The user’s **natural-language prompt** (e.g. “Find the latest React release and list its key features”) is passed into the vision step so the model can return flexible, query-specific info (e.g. key features in notes, or other visible details). Any GitHub repo works via `--repo owner/name` or by inferring repo from the prompt (LLM).

## What worked

- Vision state + action from a single screenshot is enough to drive the flow (home → search → repo → releases) without DOM scraping.
- Semantic Playwright (get_by_role, get_by_text, get_by_placeholder) is sufficient for clicking and search; no selectors needed.
- Search via keyboard (“/” to focus GitHub search, then type + Enter) works when the viewport fits the page; avoiding a second click after submit fixed confusion.
- URL override when vision misclassifies (e.g. “home” on search results) prevents loops.
- Full-page screenshot + scroll before extraction captures release notes and download links that are below the fold.

## What didn’t / trade-offs

- **Search bar vs URL:** If the search bar isn’t visible or focus fails (e.g. window size, timing), we don’t fall back to `goto_search` anymore so the run can stall on home. Trade-off: strict “use the UI” vs robustness. A configurable fallback could be re-added.
- **Vision cost/latency:** Every step and the final extraction call the API; that’s slower and more expensive than a single direct navigation to `.../releases` and DOM parse, but matches the assignment’s “vision to understand and decide” requirement.
- **Structured output:** The vision schema is strict (all fields required). If the model omits or hallucinates a field, the API can return 400; we then fall back to minimal JSON. Tuning the schema (e.g. optional fields) could improve reliability.

## Limitations

- Depends on OpenAI API key and availability; no vision means URL heuristics only and no extraction.
- Current implementation targets the **releases** page and “latest release” only; other pages (Code, Issues, etc.) or other query types would need a broader goal and possibly more vision states/actions.
- Single-repo, single “latest” release; no pagination or multi-repo.
- GitHub-only; navigation and extraction prompts are tailored to GitHub.
- Full-page screenshot for extraction can be slow on long release notes.

## Future improvements

- **Flexible targets:** Let the prompt or goal choose the target page (releases vs Code vs Issues, etc.) and extract the relevant metadata (release notes, download links, publish dates, file tree, issue list, etc.).
- Optional fallback to `goto_search` when `fill_search_and_submit` fails (e.g. flag `--allow-url-search`).
- Retry/backoff for vision API errors.
- Support for “pre-release” or “latest by date” vs “latest” tag.
- Optional shorter notes (e.g. first N chars) to reduce token use and latency.
