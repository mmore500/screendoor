"""Print the state of every dispatch in a workdir."""

import argparse
import io
import json
import sys

from ..auxlib._format_cli_description import format_cli_description


def main(argv=None) -> int:
    from ._print_status import print_status

    parser = argparse.ArgumentParser(
        prog="python3 -m screendoor.daemon.print_status",
        description=format_cli_description(__doc__),
    )
    parser.add_argument("--workdir", default=".")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.json:
        rows = print_status(args.workdir, file=io.StringIO())
        print(json.dumps(rows, indent=2))
    else:
        print_status(args.workdir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
