# Observations Document

## Approach

- **Vision-first navigation:** Each step takes a viewport screenshot, sends it to an OpenAI vision model (e.g. gpt-4o-mini), and uses the model’s classification (home, search_results, repo_page, releases_page) and suggested action (type_search, click, done) to decide what to do next. Playwright then performs the action (search bar focus/type, or click by role/text). Prompts are written in natural language so the model isn’t driven by rigid rules.

- **URL as backup:** When the screenshot is ambiguous (e.g. search results page still shows the same header as home), the current URL is used to override state so we don’t get stuck.

- **Prompt-driven behavior:** If the user passes only a repo (e.g. `openclaw/openclaw`), the goal is “latest release” and we output the fixed JSON shape. If they pass a natural-language prompt, an LLM infers both the repo and the goal (latest_release, code, or custom). For “code” we stop on the repo’s Code tab and return flexible extraction; for “latest_release” we go to Releases and return the fixed release JSON; for “custom” we still navigate and extract according to the prompt.

- **Release extraction (no selectors):** For the “latest release” goal we: (1) zoom out so more of the page fits in one view, (2) take a full-page screenshot and ask the vision model **where** the latest release block is (top/bottom percent of the page), (3) use Playwright to gather **only the text** in that vertical region (TreeWalker + layout bounds—no CSS), (4) send that raw text to an LLM to parse into structured JSON (version, tag, author, published_at, notes, assets). Notes are normalized (collapse blank lines, trim) for readability. If locate or parse fails, we fall back to a one-shot vision extraction from a viewport screenshot.

## What worked

- Vision state + action from a single screenshot is enough to drive the flow (home → search → repo → releases, or stop on repo for “code” goal) without DOM scraping.
- Semantic Playwright (get_by_role, get_by_text, get_by_placeholder) is sufficient for clicking and search; no selectors needed.
- Search via keyboard (“/” to focus GitHub search, then type + Enter) works when the viewport fits the page.
- URL override when vision misclassifies (e.g. “home” on search results) prevents loops.
- Zoom out + “locate region” + “get text in region” + “parse text” gives the correct latest release (the one with the “Latest” badge) and avoids pulling an older release from further down the page. Text-based parsing also produces cleaner, normalized notes.

## What didn’t / trade-offs

- **Search bar vs URL:** If the search bar isn’t visible or focus fails, we don’t fall back to `goto_search`, so the run can stall on home. Trade-off: strict “use the UI” vs robustness.
- **Vision cost/latency:** Every step and the extraction (locate + parse, or fallback one-shot) call the API; that’s slower and more expensive than a direct navigation and DOM parse, but matches the assignment’s vision-first requirement.
- **Region text:** Getting text by vertical percent relies on layout (getBoundingClientRect + scroll). Zoom and dynamic content can sometimes make the region slightly off; the fallback one-shot extraction helps when that happens.

## Limitations

- Depends on OpenAI API key and availability; no vision means URL heuristics only and no extraction.
- Single-repo, single “latest” release; no pagination or multi-repo.
- GitHub-only; navigation and extraction prompts are tailored to GitHub.
- “Code” and “custom” goals use a single flexible extraction (screenshot → answer the prompt); no multi-step extraction for those.

## Future improvements

- Optional fallback to `goto_search` when `fill_search_and_submit` fails (e.g. flag `--allow-url-search`).
- Retry/backoff for vision API errors.
- Support for “pre-release” or “latest by date” vs “latest” tag.
- Richer handling for “custom” goals (e.g. multiple pages or targeted regions).
