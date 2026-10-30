from __future__ import annotations

import argparse


def main() -> int:
    parser = argparse.ArgumentParser(description="Smart Drive Organizer")
    parser.add_argument(
        "--background",
        action="store_true",
        help="Run the saved automatic folder-monitoring service without opening the desktop window.",
    )
    args = parser.parse_args()

    if args.background:
        from smart_drive_organizer.automation import run_background_service
        return run_background_service()

    from smart_drive_organizer.gui import launch
    launch()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
