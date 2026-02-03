from __future__ import annotations

import argparse
import json
import os

from dotenv import load_dotenv

from .extractor import Extractor
from .models import NavigatorConfig
from .navigator import Navigator
from .planner import Planner
from .run_logging import RunLogger
from .vision import OpenAIVisionModel, StubVisionModel


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="GitHub release scraper: vision-first + Playwright")
    p.add_argument("repo", nargs="?", default=None, help="Repo owner/name (e.g. openclaw/openclaw)")
    p.add_argument("--repo", dest="repo_flag", type=str, default=None, help="Same as positional repo")
    p.add_argument("--prompt", type=str, default=None, help="Natural language prompt (repo inferred from text)")
    p.add_argument("--vision-model", type=str, default="gpt-4o-mini", help="OpenAI vision model")
    p.add_argument("--headless", action="store_true", help="Run browser headless")
    p.add_argument("--quiet", action="store_true", help="No console logs")
    p.add_argument("--no-block-resources", action="store_true", help="Don't block images/fonts (slower)")
    p.add_argument("--action-delay-ms", type=int, default=1000, help="Delay after each action (ms)")
    p.add_argument("--screenshot-timeout-ms", type=int, default=8000, help="Screenshot timeout (ms)")
    return p.parse_args()


def main() -> None:
    load_dotenv()
    args = parse_args()
    repo = args.repo_flag or args.repo
    plan = Planner().plan(prompt=args.prompt, repo=repo, fields=None)
    logger = RunLogger(print_to_console=not args.quiet)
    logger.log_event(f"[cli] plan repo={plan.repo!r} search_query={plan.search_query!r} goal={plan.goal!r}")
    logger.log_event(f"[cli] run_dir={logger.run_dir}")
    vision = OpenAIVisionModel(model=args.vision_model) if os.getenv("OPENAI_API_KEY") else StubVisionModel()
    config = NavigatorConfig(
        headless=args.headless,
        verbose=not args.quiet,
        action_delay_ms=max(0, args.action_delay_ms),
        screenshot_timeout_ms=max(2000, args.screenshot_timeout_ms),
        block_resources=not args.no_block_resources,
    )
    nav = Navigator(config=config, logger=logger, vision=vision)

    try:
        nav.run(plan)
        result = Extractor(nav.driver, vision=vision, logger=logger).extract_latest(plan)
        out = {
            "repository": result.repository,
            "latest_release": {
                k: v for k, v in {
                    "version": result.version,
                    "tag": result.tag,
                    "author": result.author,
                    "published_at": result.published_at,
                    "notes": result.notes,
                }.items() if v is not None
            },
        }
        if result.assets:
            out["latest_release"]["assets"] = [{"name": a.name, "url": a.url} for a in result.assets]
        logger.log_result(out)
        print(json.dumps(out, indent=2))
    except KeyboardInterrupt:
        logger.stop()
        print("\nCtrl+C — exiting.")
    finally:
        try:
            nav.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
