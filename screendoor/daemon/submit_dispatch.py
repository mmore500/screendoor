"""Submit a dispatch (JSON file, or - for stdin) to a workdir.

This only records the dispatch. Start a daemon separately to run it.
"""

import argparse
import json
import sys

from ..auxlib._format_cli_description import format_cli_description


def main(argv=None) -> int:
    from ._submit_dispatch import submit_dispatch

    parser = argparse.ArgumentParser(
        prog="python3 -m screendoor.daemon.submit_dispatch",
        description=format_cli_description(__doc__),
    )
    parser.add_argument("dispatch", help="path to a JSON dispatch, or -")
    parser.add_argument("--workdir", default=".")
    args = parser.parse_args(argv)
    with sys.stdin if args.dispatch == "-" else open(args.dispatch) as fh:
        text = fh.read()
    try:
        uid = submit_dispatch(json.loads(text), args.workdir)
    except ValueError as e:
        print(f"screendoor: invalid dispatch: {e}", file=sys.stderr)
        return 2
    print(uid)
    return 0


if __name__ == "__main__":
    sys.exit(main())
