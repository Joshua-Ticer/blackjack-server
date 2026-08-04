from __future__ import annotations

import argparse

from app.tui.app import DEFAULT_BASE_URL, BlackjackApp


def main() -> None:
    parser = argparse.ArgumentParser(prog="blackjack-tui")
    parser.add_argument("--server", default=DEFAULT_BASE_URL)
    parser.add_argument(
        "--demo",
        action="store_true",
        help="play offline against the real engine; no server or database needed",
    )
    parser.add_argument(
        "--pairs",
        action="store_true",
        help="demo only: deal every seat a pair so split is legal every hand",
    )
    args = parser.parse_args()

    if args.demo:
        from app.tui.demo import build

        build(force_pairs=args.pairs)[0].run()
        return

    BlackjackApp(base_url=args.server).run()


if __name__ == "__main__":
    main()
