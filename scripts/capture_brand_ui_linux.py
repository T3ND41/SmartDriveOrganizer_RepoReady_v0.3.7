from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from PIL import Image, ImageStat

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "brand-ui-screenshots"
OUTPUT.mkdir(exist_ok=True)


def capture_theme(theme: str) -> None:
    with tempfile.TemporaryDirectory(prefix="sdo-ui-") as config_home:
        app_data = Path(config_home) / "SmartDriveOrganizer"
        app_data.mkdir(parents=True)
        (app_data / "ui_preferences.json").write_text(
            json.dumps({"theme": theme}), encoding="utf-8"
        )
        env = os.environ.copy()
        env["XDG_CONFIG_HOME"] = config_home
        process = subprocess.Popen(
            [sys.executable, str(ROOT / "run.py")],
            cwd=ROOT,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        try:
            window_id = None
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    error = process.stderr.read().decode("utf-8", errors="replace")
                    raise RuntimeError(
                        f"Application exited in {theme} theme ({process.returncode}): {error}"
                    )
                found = subprocess.run(
                    ["xdotool", "search", "--onlyvisible", "--name", "Smart Drive Organizer"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                ids = [line.strip() for line in found.stdout.splitlines() if line.strip()]
                if ids:
                    window_id = ids[-1]
                    geometry = subprocess.run(
                        ["xdotool", "getwindowgeometry", "--shell", window_id],
                        capture_output=True,
                        text=True,
                        check=False,
                    ).stdout
                    values = {}
                    for line in geometry.splitlines():
                        if "=" in line:
                            key, value = line.split("=", 1)
                            values[key] = value
                    if int(values.get("WIDTH", "0")) >= 900 and int(values.get("HEIGHT", "0")) >= 650:
                        break
                time.sleep(0.5)
            if not window_id:
                raise RuntimeError(f"No Smart Drive Organizer window appeared in {theme} theme")
            subprocess.run(
                ["xdotool", "windowactivate", "--sync", window_id],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            time.sleep(2)
            path = OUTPUT / f"smart-drive-organizer-{theme}.png"
            subprocess.run(["import", "-window", window_id, str(path)], check=True)
            with Image.open(path) as image:
                image.load()
                if image.width < 900 or image.height < 650:
                    raise RuntimeError(f"{theme} screenshot is unexpectedly small: {image.size}")
                stats = ImageStat.Stat(image.convert("RGB"))
                if sum(stats.stddev) < 12 or path.stat().st_size < 10_000:
                    raise RuntimeError(f"{theme} screenshot appears blank or unrendered")
            print(f"Captured {theme}: {path} ({image.width}x{image.height}, {path.stat().st_size} bytes)")
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)


def main() -> int:
    for theme in ("light", "dark", "redline"):
        capture_theme(theme)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
