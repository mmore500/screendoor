"""Run trials, one after another, and record how each ended."""

import argparse
import sys

from ..auxlib._format_cli_description import format_cli_description


def main(argv: list[str] | None = None) -> int:
    """Run the worker from the command line.

    Parameters
    ----------
    argv : list of str or None, default None
        The arguments; ``sys.argv[1:]`` if None.

    Returns
    -------
    int
        The process exit code.
    """
    from ._worker import worker

    parser = argparse.ArgumentParser(
        prog="python3 -m screendoor.trial.worker",
        description=format_cli_description(__doc__),
    )
    parser.add_argument("--dispatchdir", required=True)
    parser.add_argument("--dispatch", required=True, help="dispatch_uuid")
    parser.add_argument("trials", nargs="+", help="trial_uuid")
    args = parser.parse_args(argv)
    return worker(args.dispatchdir, args.dispatch, args.trials)


if __name__ == "__main__":
    sys.exit(main())
