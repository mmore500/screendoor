"""Print the state of every dispatch in a dispatchdir."""

import argparse
import json
import sys

from ..auxlib._format_cli_description import format_cli_description
from ._print_status import dispatch_status, print_status


def main(argv: list[str] | None = None) -> int:
    """Run `print_status` (or, with `--json`, `dispatch_status`) from the
    command line; return the exit code."""
    parser = argparse.ArgumentParser(
        prog="python3 -m screendoor.daemon.print_status",
        description=format_cli_description(__doc__),
    )
    parser.add_argument("--dispatchdir", default=".")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.json:
        print(json.dumps(dispatch_status(args.dispatchdir), indent=2))
    else:
        print_status(args.dispatchdir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
