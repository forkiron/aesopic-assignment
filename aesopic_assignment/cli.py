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
    parser.add_argument("--headless", action="store_true", help="Run browser in headless mode")
    parser.add_argument("--no-headless", action="store_true", help="Run browser with UI")
    return parser.parse_args()


def main() -> None:
    load_dotenv()
    args = parse_args()
    fields = args.fields.split(",") if args.fields else None
    headless = True
    if args.no_headless:
        headless = False
    elif args.headless:
        headless = True

    planner = Planner()
    plan = planner.plan(prompt=args.prompt, repo=args.repo, fields=fields)

    logger = RunLogger()
    if os.getenv("OPENAI_API_KEY"):
        vision = OpenAIVisionModel(model=args.vision_model)
    else:
        vision = StubVisionModel()
    navigator = Navigator(config=NavigatorConfig(headless=headless), logger=logger, vision=vision)

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
