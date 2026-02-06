# Observations Document

## File overview

- **`cli.py`** – Entry point that runs and prints everything. Handles Ctrl+C and output shape (fixed release vs flexible `result`).

- **`planner.py`** – Turns user input into a plan. If repo is given explicitly, goal is `latest_release`. If only a prompt is given, an LLM infers repo (owner/name) and goal (`latest_release` | `code` | `custom`) by logic. Produces `PlannerOutput`: repo, goal, search_query, required_entities, success_criteria, user_prompt.

- **`navigator.py`** – Vision navigator. Starts at github home pg, then: screenshot → vision identifies page and suggests action based on the page (type_search, click, done) → URL can override state when vision says “home” but we’re on search/repo/releases → Playwright performs the action. Stops when on releases page, or on repo page when goal is `code`/`custom`. allbacks of (click by role/text, direct goto) when vision doesn’t act.

- **`vision.py`** – OpenAI vision interface. **classify_state**: screenshot → page type + next action (for navigator). **locate_latest_release_region**: screenshot → top/bottom percent of page for the “Latest” release block. **parse_release_text**: raw text → structured release JSON (version, tag, author, notes, assets). **extract_release**: one-shot screenshot → release JSON (fallback). **extract_for_prompt**: screenshot + user question → flexible `result` (for code/custom goals). Helpers: image→data URL, normalize notes (collapse blank lines).

- **`extractor.py`** – Runs after nav. For `latest_release`: zoom out, screenshot, locate region, get text in that region via Playwright, parse text to JSON; on failure falls back to one-shot vision extraction. For `code`/`custom`: full-page screenshot, vision answers the user’s prompt, returns `{repository, result}`.

- **`playwright_driver.py`** – Launches browser, creates a context and page, optional resource blocking. Exposes: goto, wait, screenshot, set_zoom, get_page_height, get_text_in_region (TreeWalker + layout Y range, no selectors), scroll_releases_page_for_extraction, click_by_role, click_by_text, fill_search_and_submit (GitHub “/” shortcut or searchbox depending on vision response).

- **`state_machine.py`** – URL/title heuristics to infer page state (home, search_results, repo_page, releases_page, unknown). Used when vision isn’t available (purely as a fallback) or to override vision when the URL clearly indicates the page type.

- **`run_logging.py`** – Per-run log dir under `runs/<timestamp>/`. Writes events.log, step*\*.json (actions), step*\*.png (screenshots), result.json. Stops writing after `stop()` (e.g. Ctrl+C). I used this just to visualize the process of screenshots and seeing what the LLM was picking up.

- **`models.py`** – Shared dataclasses: PlannerOutput, Action, NavigatorConfig, Asset, ExtractedRelease.

## Design decisions

- **Architecture:** Single pipeline: plan → navigate (vision + Playwright) → extract. Planner, Navigator, Extractor, and Vision are separate so we can swap vision providers or add goals without rewriting the loop. Playwright is the only browser dependency; vision is behind an interface (StubVisionModel when no API key).

- **Vision integration:** Vision is used for observation and extraction only, not for executing clicks. We send screenshots and get back state + suggested action (or region, or parsed JSON); Playwright performs the actions. This keeps vision stateless and avoids “vision says click here” coordinate issues. We use the OpenAI Responses API for image inputs (classify, locate, one-shot extract) and Chat API for text parsing (parse_release_text).

- **Error handling:** (1) No API key → StubVisionModel (confidence 0), so navigator uses URL heuristics and extractor returns minimal/empty release. (2) Vision API errors → logged to stderr, we return None and caller falls back (e.g. extractor tries one-shot extract or returns empty fields). (3) Navigation max_steps → RuntimeError. (4) Ctrl+C → RunLogger.stop() so we don’t write half a run; then exit.

## Approach

- **Vision navigation:** Each step takes a viewport screenshot, sends it to an OpenAI vision model (e.g. gpt-4o-mini), and uses the model’s classification (home, search_results, repo_page, releases_page) and suggested action (type_search, click, done) to decide what to do next. Playwright then performs the action (search bar focus/type, or click by role/text). Prompts are written in natural language so the model isn’t driven by rigid rules.

- **URL as backup:** When the screenshot is ambiguous (e.g. search results page still shows the same header as home), the current URL is used to override state so we don’t get stuck.

- **Prompt-driven behavior:** If the user passes only a repo (e.g. `openclaw/openclaw`), the goal is “latest release” and we output the fixed JSON shape. If they pass a natural-language prompt, an LLM infers both the repo and the goal (latest_release, code, or custom). For “code” we stop on the repo’s Code tab and return flexible extraction; for “latest_release” we go to Releases and return the fixed release JSON; for “custom” we still navigate and extract according to the prompt.

- **Release extraction (no selectors):** For the “latest release” goal we: (1) zoom out so more of the page fits in one view, (2) take a full-page screenshot and ask the vision model **where** the latest release block is (top/bottom percent of the page), (3) use Playwright to gather **only the text** in that vertical region (TreeWalker + layout bounds—no CSS), (4) send that raw text to an LLM to parse into structured JSON (version, tag, author, published_at, notes, assets). Notes are normalized (collapse blank lines, trim) for readability. If locate or parse fails, we fall back to a one-shot vision extraction from a viewport screenshot.

## What worked

- Vision state + action from a single screenshot is enough to drive the flow (home → search → repo → releases, or stop on repo for “code” goal) without DOM scraping.
- Semantic Playwright (get_by_role, get_by_text, get_by_placeholder) is sufficient for clicking and search; no selectors needed.
- URL override when vision misclassifies (e.g. “home” on search results) prevents loops.
- Zoom out + “locate region” + “get text in region” + “parse text” gives the correct latest release (the one with the “Latest” badge) and avoids pulling an older release from further down the page. Text-based parsing also produces cleaner, normalized notes.

## What didn’t / trade-offs

- **Search bar vs URL:** If the search bar isn’t visible or focus fails the run can stall on home.
- **Vision cost/latency:** Every step and the extraction (locate + parse, or fallback one-shot) call the API; that’s slower and more expensive than a direct navigation and DOM parse.

- **Region text:** Getting text by vertical percent relies on layout (getBoundingClientRect + scroll). Zoom and dynamic content can sometimes make the region slightly off; the fallback one-shot extraction helps when that happens.

- **Fallback vision extraction:** The primary path (zoom → locate region → get text in region → parse text) often fails in practice (e.g. locate returns a bad region, or the text in that region is empty/wrong, or parse_release_text fails). When it does, we fall back to **one-shot vision** (viewport screenshot → extract_release). That fallback usually produces the correct latest release, but it has limitations: (1) viewport-only, so very long notes or assets below the fold can be missed; (2) if the viewport doesn’t clearly show the “Latest” badge, the model could in theory pick an older release; (3) we do more API calls when both paths run (locate + parse fail, then extract_release). In runs we often see `[extract] fallback: vision extract_release` — the pipeline still succeeds, but we’re relying on the fallback rather than the intended locate→text→parse flow.

## Edge cases & failure handling

- **No OpenAI key:** Stub vision returns confidence 0; state comes from URL/title only. Extraction returns repository + empty/minimal release. Navigation can still reach releases via URL fallbacks and direct goto.
- **Vision API failure (rate limit, timeout, 5xx):** Exception is caught in vision layer, logged, and None is returned. Navigator keeps going with heuristic state; extractor uses one-shot extract if locate/parse failed, or returns partial result.
- **Screenshot timeout:** Configurable via `--screenshot-timeout-ms`; on timeout the step gets no path and vision is skipped for that step; URL override or fallback actions can still advance.
- **Search bar not focused / "/" doesn't work:** We do not fall back to URL search. The run can stall on home until max_steps, then fail. This is an intentional trade-off (assignment: use the UI); documented in "What didn't".
- **Locate region or parse_release_text fails:** Extractor falls back to one-shot vision extraction (viewport screenshot → extract_release). This fallback is used often in practice (see “Fallback vision extraction” under What didn’t / trade-offs). If the fallback also fails, we return whatever we have (e.g. repository + empty latest_release).
- **Wrong page (e.g. wrong repo clicked):** No automatic detection. Vision might suggest the correct next action on the next step; URL override doesn't fix "wrong repo". Max_steps eventually triggers.
- **Ctrl+C:** RunLogger.stop() is called so no further log writes; browser is closed in finally. Output may be incomplete.

## Testing & validation

- **Evidence of runs:** Each run writes to `runs/<timestamp>/`: `events.log` (step-by-step), `step_*.json` (actions), `step_*.png` (screenshots), `result.json`. This gives a trace for debugging and for showing that the pipeline was exercised. I used this to visually assess whether each output was valid.
- **Scenarios we validate against:** (1) Repo-only → releases page → fixed JSON with version, tag, author, notes, assets. (2) Prompt "latest release" → same. (3) Prompt "root code for openclaw" → stop on repo page, flexible `result`. (4) Headless and with `--quiet` to ensure no hard dependency on console or visible window.
- **What I didn't test:** Unit tests for vision or Playwright; regression tests; multiple repos in one run; rate limits or API failures. Adding pytest for the planner (regex + LLM parsing) and for state_machine.detect_state would be the first step for a proper test suite.

## Critical reflection

- **Trade-offs we accepted:** (1) No URL search fallback when the search bar fails — I kept running into the issue of the fallback replacing vision, which was annoying so I took it away entirely as it would kinda be like "hardcoding" the solution to find the repository list. (2) Vision on every step is costly and slow, but atleast it can semantically recognize everything on page and figure out a logical plan/goal to work from. A strong suit for this is also that it can . (3) Region-based text extraction can be wrong if the layout is odd or zoom is wrong; we rely on the one-shot fallback and note it in "What didn't".

- **What doesn't work well:** (1) Vision doesn't work for identifying the search button on home page. I can only currently take a picture and recognize its on home page, which prompts to search with a '/'. (2) LLM goal/repo parsing can misclassify (e.g. "custom" vs "latest_release"); we don't validate or correct. (3) Long release notes are truncated in the region or in parse_release_text (max tokens); we don't paginate or chunk.

- **Honest assessment:** The pipeline works for the assigned path and through NLP prompts (repo → releases → correct latest release JSON). Edge cases (no key, API errors, wrong page) are partially handled with fallbacks and clear failure modes rather than hidden crashes.

## Future improvements

- Optional fallback to `goto_search` when `fill_search_and_submit` fails (e.g. flag `--allow-url-search`).
- Retry/backoff for vision API errors, right now its too heavily reliant on vision, if for some reason the prompting is inconcise may lead to faulty errors.
- Richer handling for “custom” goals (e.g. multiple pages or targeted regions) maybe even able to get/summarize code.
