"""Resume killed dispatches. Start the daemon separately if it exited."""

import argparse
import sys

from ..auxlib._format_cli_description import format_cli_description
from ._resume_dispatch import resume_dispatch


def main(argv: list[str] | None = None) -> int:
    """Run `resume_dispatch` from the command line; return the exit code."""
    parser = argparse.ArgumentParser(
        prog="python3 -m screendoor.daemon.resume_dispatch",
        description=format_cli_description(__doc__),
    )
    parser.add_argument(
        "dispatch",
        nargs="*",
        help="dispatch_uuid, or a prefix of one (default: every killed one)",
    )
    parser.add_argument("--dispatchdir", default=".")
    args = parser.parse_args(argv)
    try:
        resumed = resume_dispatch(args.dispatchdir, args.dispatch)
    except LookupError as e:
        print(f"screendoor: {e.args[0]}", file=sys.stderr)
        return 2
    for dispatch_uuid in resumed:
        print(dispatch_uuid)
    return 0


if __name__ == "__main__":
    sys.exit(main())
