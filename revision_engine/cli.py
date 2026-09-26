"""Command-line entry point: rv2 build | check | serve | narrate."""

from __future__ import annotations

import argparse
import sys

from revision_engine import __version__


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="rv2", description="reVision static-site builder.")
    p.add_argument("--version", action="version", version=f"rv2 {__version__}")
    p.add_subparsers(dest="command", metavar="command")
    return p


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    if args.command is None:
        parser.print_help(sys.stderr)
        return 2
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
