"""Re-run churn at every recorded step of a run directory, same seeds."""

import argparse
import sys

from ..auxlib._format_cli_description import format_cli_description


def main(argv=None) -> int:
    from ._replay_dispatch import replay_dispatch

    parser = argparse.ArgumentParser(
        prog="python3 -m screendoor.daemon.replay_dispatch",
        description=format_cli_description(__doc__),
    )
    parser.add_argument("run_dir")
    parser.add_argument("--assay", help="replay this assay expression instead")
    args = parser.parse_args(argv)
    reports = replay_dispatch(args.run_dir, assay=args.assay)
    return int(not all(r["match"] for r in reports))


if __name__ == "__main__":
    sys.exit(main())
