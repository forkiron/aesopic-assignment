from __future__ import annotations

import json
import os
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, Optional


class RunLogger:
    def __init__(self, base_dir: str = "runs", print_to_console: bool = False) -> None:
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        self.run_dir = Path(base_dir) / timestamp
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.step = 0
        self.print_to_console = print_to_console

    def log_action(self, action: Dict[str, Any]) -> None:
        path = self.run_dir / f"step_{self.step:02d}.json"
        with path.open("w", encoding="utf-8") as handle:
            json.dump(action, handle, indent=2)

    def log_screenshot(self, page, label: Optional[str] = None, timeout_ms: int = 10_000) -> Optional[str]:
        suffix = label or f"step_{self.step:02d}"
        path = self.run_dir / f"{suffix}.png"
        try:
            page.screenshot(path=str(path), full_page=True, timeout=timeout_ms)
            return str(path)
        except Exception as exc:
            self.log_event(f"[nav] screenshot_failed error={type(exc).__name__}")
            return None

    def log_result(self, payload: Dict[str, Any]) -> None:
        path = self.run_dir / "result.json"
        with path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)

    def bump(self) -> None:
        self.step += 1

    def log_event(self, message: str) -> None:
        path = self.run_dir / "events.log"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(message + "\n")
        if self.print_to_console:
            print(message)
