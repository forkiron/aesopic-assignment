# Autonomous Web Navigation with Vision Models (Aesopic Assignment)

Tool that uses **vision models** to autonomously navigate GitHub and extract release information. No hardcoded CSS selectors—works even if GitHub’s HTML changes.

## Navigation flow (per assignment)

1. Start at **github.com**
2. **Search** for the repo (e.g. `openclaw`)
3. **Click** the correct repository (e.g. `openclaw/openclaw`)
4. **Click** the “Releases” section
5. **Extract** the latest release as structured JSON (vision-based; no selectors)

## Setup

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

**Browser (pick one):**

- **Option A (recommended):** Install [Google Chrome](https://www.google.com/chrome/). The tool will use it; no Playwright browser install needed.
- **Option B:** `python -m playwright install chromium` (downloads ~170MB).

**API key (for vision):**

```bash
cp .env.example .env
# Edit .env and set OPENAI_API_KEY=sk-...
# The CLI loads .env automatically.
```

## Run

**Example (assignment spec):**

```bash
python -m aesopic_assignment.cli --repo openclaw/openclaw
```

**With prompt (bonus):**

```bash
python -m aesopic_assignment.cli --prompt "search for openclaw and get the current release and related tags"
```

**Optional:** `--headless`, `--quiet`, `--action-delay-ms 1000`, `--screenshot-timeout-ms 8000`, `--no-block-resources` (disable image/font blocking if pages break)

Output is JSON in the required shape, e.g.:

```json
{
  "repository": "openclaw/openclaw",
  "latest_release": {
    "version": "v2026.1.29",
    "tag": "77e703c",
    "author": "steipete"
  }
}
```

## Design

**First layer: OpenAI Vision LLM.** We observe the page by sending a screenshot to the vision model; it returns page state and the next action (type_search, click, done). Extraction is also vision-based (releases screenshot → JSON). No DOM or selectors for observation.

**Fallback / execution: Playwright.** Playwright runs the browser (Chrome/Chromium), loads pages, takes the viewport screenshots we send to the LLM, and executes the actions the LLM chooses (goto, click by role/text). If we have no screenshot or no API key, we fall back to URL/title-only heuristics and still use Playwright to act.

So: **observe with vision first**, then **run with Playwright** (and fall back to non-vision observation only when needed).

- **Logging:** Steps and screenshots in `runs/<timestamp>/`. Use `--quiet` to disable console logs.

## Structure

- `planner.py` – Prompt/repo → plan (goal, search query, required entities)
- `navigator.py` – Start at github.com → search → click repo → click Releases (vision + heuristics)
- `vision.py` – State classification + next action + release extraction (OpenAI / stub)
- `extractor.py` – Vision-based extraction from releases page (no selectors)
- `playwright_driver.py` – Browser wrapper (Chrome / Chromium), semantic actions only
- `models.py` – Shared dataclasses
