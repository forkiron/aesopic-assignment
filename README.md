# Autonomous Web Navigation with Vision Models (Aesopic Assignment)

Tool that uses **vision models** to autonomously navigate GitHub and extract release (or other) information. No hardcoded CSS selectors—works even if GitHub’s HTML changes.

## Navigation flow (per assignment)

1. Start at **github.com**
2. **Search** for the repo (e.g. `openclaw`)
3. **Click** the correct repository (e.g. `openclaw/openclaw`)
4. **Click** the “Releases” section (or stop on the a specific page if the user asked for something else)
5. **Extract** the latest release as structured JSON (vision + text region + LLM parse)

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

**Repo only (releases, fixed JSON):**

```bash
python -m aesopic_assignment.cli openclaw/openclaw
# or
python -m aesopic_assignment.cli --repo openclaw/openclaw
```

**Natural-language prompt (repo and goal inferred):**

```bash
python -m aesopic_assignment.cli --prompt "What's the latest release of openclaw?"
python -m aesopic_assignment.cli --prompt "List key features of the openclaw project"
```

**Optional:** `--headless`, `--quiet`, `--action-delay-ms 1000`, `--screenshot-timeout-ms 8000`, `--no-block-resources`

Output for “latest release” is JSON in this shape (notes are normalized for readability):

```json
{
  "repository": "openclaw/openclaw",
  "latest_release": {
    "version": "2026.2.3",
    "tag": "v2026.2.3",
    "author": "steipete",
    "published_at": "yesterday",
    "notes": "## Changes\n\n- Telegram: remove last @ts-nocheck...\n- Onboarding: add Cloudflare AI Gateway...",
    "assets": [{ "name": "Source code.zip", "url": "https://..." }]
  }
}
```

For “code” or “custom” goals the output is `{"repository": "...", "result": ...}` (flexible).

## Deliverables

- **Source code** – this repo
- **README.md** – this file (setup and run instructions)
- **Observations document** – `OBSERVATIONS.md` (approach, trade-offs, limitations)
- **Sample output** – `sample_output.json` (example JSON for openclaw/openclaw)

## Bonus features

- **Additional metadata:** Release notes, publish date, and download links (assets); notes are cleaned (collapse blank lines, trim) for readable output.
- **Any GitHub repository:** Use any `owner/repo` via CLI.
- **Natural-language prompts:** Repo and goal (latest_release / code / custom) are inferred from the prompt; extraction follows the ask (releases → fixed JSON; code/custom → flexible result).
- **Release extraction pipeline:** Zoom out → vision locates the “latest release” block on the page → Playwright gets only the text in that region (no selectors) → LLM parses that text into structured JSON. This avoids pulling an older release and keeps notes tidy.

## Design

**First layer: OpenAI Vision LLM.** We observe the page by sending a screenshot to the vision model; it returns page state and the next action (type_search, click, done). Prompts are natural language, not hardcoded rule lists. For release extraction we first ask the model where the latest release block is (vertical region), then we get that region’s text and parse it with a second LLM call. No DOM or selectors for observation.

**Execution: Playwright.** Playwright runs the browser (Chrome/Chromium), loads pages, takes screenshots, and executes the actions the LLM chooses. It also exposes “get text in region” (by vertical percent, using layout) so we can copy only the latest-release block’s text. If we have no API key, we fall back to URL/title heuristics and still use Playwright to act.

So: **observe with vision first**, then **act and extract with Playwright** (and optional text→JSON parse).

- **Logging:** Steps and screenshots in `runs/<timestamp>/`. Use `--quiet` to disable console logs.

## Structure

- `planner.py` – Prompt/repo → plan (goal, search query, required entities); LLM infers repo and goal from prompt when needed
- `navigator.py` – Start at github.com → search → click repo → click Releases or stop on repo (vision + URL override)
- `vision.py` – State classification, locate latest-release region, parse release text, one-shot release extraction (OpenAI / stub)
- `extractor.py` – Zoom, locate region, get text, parse; fallback to one-shot vision extraction
- `playwright_driver.py` – Browser wrapper, zoom, get text in region (no selectors), semantic actions
- `models.py` – Shared dataclasses
