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
    parser = argparse.ArgumentParser(description="Aesopic assignment pipeline")
    parser.add_argument("--prompt", type=str, default=None, help="Natural language prompt")
    parser.add_argument("--repo", type=str, default=None, help="Repo owner/name")
    parser.add_argument(
        "--fields",
        type=str,
        default=None,
        help="Comma-separated fields: version,tag,author,published_at,notes,assets",
    )
    parser.add_argument(
        "--vision-model",
        type=str,
        default="gpt-4o-mini",
        help="OpenAI vision model name (default: gpt-4o-mini)",
    )
    parser.add_argument("--headless", action="store_true", help="Run browser in headless mode (no window)")
    parser.add_argument(
        "--action-delay-ms",
        type=int,
        default=4000,
        help="Delay after each high-level action (ms). Helps with slow browsers / rate limits.",
    )
    parser.add_argument(
        "--slow-mo-ms",
        type=int,
        default=0,
        help="Playwright slow motion (ms) between low-level actions.",
    )
    parser.add_argument(
        "--dom-probe-interval-ms",
        type=int,
        default=10000,
        help="Minimum interval between DOM text/a11y probes (ms).",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print navigation logs to the console.",
    )
    parser.add_argument(
        "--screenshot-interval-steps",
        type=int,
        default=1,
        help="Take a screenshot every N steps (1 = every step).",
    )
    parser.add_argument(
        "--screenshot-timeout-ms",
        type=int,
        default=10000,
        help="Screenshot timeout (ms) to avoid hangs.",
    )
    return parser.parse_args()


def main() -> None:
    load_dotenv()
    args = parse_args()
    fields = args.fields.split(",") if args.fields else None
    headless = args.headless  # default: show browser so you can see it

    planner = Planner()
    plan = planner.plan(prompt=args.prompt, repo=args.repo, fields=fields)

    logger = RunLogger(print_to_console=args.verbose)
    if os.getenv("OPENAI_API_KEY"):
        vision = OpenAIVisionModel(model=args.vision_model)
    else:
        vision = StubVisionModel()
    navigator = Navigator(
        config=NavigatorConfig(
            headless=headless,
            action_delay_ms=max(0, int(args.action_delay_ms)),
            slow_mo_ms=max(0, int(args.slow_mo_ms)),
            dom_probe_interval_ms=max(0, int(args.dom_probe_interval_ms)),
            verbose=bool(args.verbose),
            screenshot_interval_steps=max(1, int(args.screenshot_interval_steps)),
            screenshot_timeout_ms=max(0, int(args.screenshot_timeout_ms)),
        ),
        logger=logger,
        vision=vision,
    )

    try:
        navigator.run(plan)
        extractor = Extractor(navigator.driver, vision=vision)
        result = extractor.extract_latest(plan)
        # Assignment expected format: { "repository", "latest_release": { "version", "tag", "author" } }
        out = {
            "repository": result.repository,
            "latest_release": {
                "version": result.version,
                "tag": result.tag,
                "author": result.author,
                "published_at": result.published_at,
                "notes": result.notes,
            },
        }
        if result.assets:
            out["latest_release"]["assets"] = [{"name": a.name, "url": a.url} for a in result.assets]
        out["latest_release"] = {k: v for k, v in out["latest_release"].items() if v is not None}
        logger.log_result(out)
        print(json.dumps(out, indent=2))
    finally:
        navigator.close()


if __name__ == "__main__":
    main()
