"""Cancel in-progress trials and pause dispatches, until resume_dispatch."""

import argparse
import sys

from ..auxlib._format_cli_description import format_cli_description


def main(argv=None) -> int:
    from ._kill_dispatch import kill_dispatch

    parser = argparse.ArgumentParser(
        prog="python3 -m screendoor.daemon.kill_dispatch",
        description=format_cli_description(__doc__),
    )
    parser.add_argument(
        "dispatch", nargs="*", help="dispatch_uuid (default: every open one)"
    )
    parser.add_argument("--workdir", default=".")
    parser.add_argument(
        "--slurm",
        action="store_true",
        help="also cancel the queued Slurm daemon job, if no dispatch is "
        "left active",
    )
    args = parser.parse_args(argv)
    for dispatch_uuid in kill_dispatch(args.workdir, args.dispatch):
        print(dispatch_uuid)
    if args.slurm:
        from .slurm._submit_daemon import cancel_chain

        cancel_chain(args.workdir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
