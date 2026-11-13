"""Tick every due open dispatch in a dispatchdir once, then exit (cron mode)."""

import argparse
import sys

from ..auxlib._begin_prod_logging import begin_prod_logging
from ..auxlib._format_cli_description import format_cli_description
from ._run_tick_once import run_tick_once
from ._signals import install_usr1_handler


def main(argv: list[str] | None = None) -> int:
    """Run `run_tick_once` from the command line; return the exit code."""
    parser = argparse.ArgumentParser(
        prog="python3 -m screendoor.daemon.run_tick_once",
        description=format_cli_description(__doc__),
    )
    parser.add_argument("--dispatchdir", default=".")
    parser.add_argument(
        "--force",
        action="store_true",
        help="tick open dispatches even if not yet due",
    )
    args = parser.parse_args(argv)
    begin_prod_logging(args.dispatchdir)
    install_usr1_handler()
    run_tick_once(args.dispatchdir, force=args.force)
    return 0


if __name__ == "__main__":
    sys.exit(main())
