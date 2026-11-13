"""Cancel in-progress trials and pause dispatches, until resume_dispatch."""

import argparse
import sys

from ..auxlib._format_cli_description import format_cli_description
from ._kill_dispatch import kill_dispatch
from .slurm._submit_daemon import cancel_chain


def main(argv: list[str] | None = None) -> int:
    """Run `kill_dispatch` from the command line; return the exit code."""
    parser = argparse.ArgumentParser(
        prog="python3 -m screendoor.daemon.kill_dispatch",
        description=format_cli_description(__doc__),
    )
    parser.add_argument(
        "dispatch",
        nargs="*",
        help="dispatch_uuid, or a prefix of one (default: every open one)",
    )
    parser.add_argument("--dispatchdir", default=".")
    parser.add_argument(
        "--slurm",
        action="store_true",
        help="also cancel the queued Slurm daemon job, if no dispatch is "
        "left active",
    )
    args = parser.parse_args(argv)
    try:
        killed = kill_dispatch(args.dispatchdir, args.dispatch)
    except LookupError as e:
        print(f"screendoor: {e.args[0]}", file=sys.stderr)
        return 2
    for dispatch_uuid in killed:
        print(dispatch_uuid)
    if args.slurm:
        cancel_chain(args.dispatchdir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
