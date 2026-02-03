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

**Slow down navigation (recommended for rate limits / slow browsers):**

```bash
python -m aesopic_assignment.cli --repo openclaw/openclaw --action-delay-ms 4000
```
Optionally add Playwright slow motion for extra caution:
`--slow-mo-ms 100`

Throttle DOM probing if your browser is slow or pages are heavy:
`--dom-probe-interval-ms 10000`

Print console logs of each step:
`--verbose`

Reduce screenshot overhead:
`--screenshot-interval-steps 2` (every 2 steps) and `--screenshot-timeout-ms 8000`

**Other options:** `--fields version,tag,author,...` · `--headless` to hide the browser.

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

- **Vision-driven:** GPT-4 Vision (or stub) classifies page state and decides next action (search, click repo, click Releases). Extraction is also vision-based (screenshot → JSON); no hardcoded selectors.
- **Fallbacks:** Uses semantic roles (e.g. `searchbox`, link text) and URL heuristics when vision confidence is low. Tries system Chrome first, then Playwright Chromium.
- **Logging:** Steps and screenshots go to `runs/<timestamp>/`.

## Structure

- `planner.py` – Prompt/repo → plan (goal, search query, required entities)
- `navigator.py` – Start at github.com → search → click repo → click Releases (vision + heuristics)
- `vision.py` – State classification + next action + release extraction (OpenAI / stub)
- `extractor.py` – Vision-based extraction from releases page (no selectors)
- `playwright_driver.py` – Browser wrapper (Chrome / Chromium), semantic actions only
- `models.py` – Shared dataclasses
