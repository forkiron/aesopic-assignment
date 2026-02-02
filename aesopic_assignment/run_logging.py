from __future__ import annotations

import json
import os
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, Optional


class RunLogger:
    def __init__(self, base_dir: str = "runs") -> None:
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        self.run_dir = Path(base_dir) / timestamp
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.step = 0

    def log_action(self, action: Dict[str, Any]) -> None:
        path = self.run_dir / f"step_{self.step:02d}.json"
        with path.open("w", encoding="utf-8") as handle:
            json.dump(action, handle, indent=2)

    def log_screenshot(self, page, label: Optional[str] = None) -> str:
        suffix = label or f"step_{self.step:02d}"
        path = self.run_dir / f"{suffix}.png"
        page.screenshot(path=str(path), full_page=True)
        return str(path)

    def log_result(self, payload: Dict[str, Any]) -> None:
        path = self.run_dir / "result.json"
        with path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)

    def bump(self) -> None:
        self.step += 1

