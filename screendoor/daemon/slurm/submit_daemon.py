"""Start (or extend) the Slurm daemon chain for a dispatchdir."""

import argparse
import sys

from ...auxlib._begin_prod_logging import begin_prod_logging
from ...auxlib._format_cli_description import format_cli_description
from ._submit_daemon import submit_daemon


def main(argv: list[str] | None = None) -> int:
    """Run `submit_daemon` from the command line, printing any job id
    queued; return the exit code."""
    parser = argparse.ArgumentParser(
        prog="python3 -m screendoor.daemon.slurm.submit_daemon",
        description=format_cli_description(__doc__),
    )
    parser.add_argument("--dispatchdir", default=".")
    parser.add_argument(
        "--python",
        help="command that runs python with screendoor importable",
    )
    parser.add_argument("--sbatch-flags", default="")
    parser.add_argument("--script-dir", default="~/slurmscripts")
    parser.add_argument("--log-dir", default="~/slurmlogs")
    parser.add_argument(
        "--successor", action="store_true", help=argparse.SUPPRESS
    )
    args = parser.parse_args(argv)
    begin_prod_logging(args.dispatchdir)
    job = submit_daemon(**vars(args))
    if job:
        print(job)
    return 0


if __name__ == "__main__":
    sys.exit(main())
