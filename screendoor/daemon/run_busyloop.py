"""Tick dispatches, sleeping until the next firing; exit when none is open."""

import argparse
import sys

from ..auxlib._begin_prod_logging import begin_prod_logging
from ..auxlib._format_cli_description import format_cli_description


def main(argv: list[str] | None = None) -> int:
    """Run run_busyloop from the command line.

    Parameters
    ----------
    argv : list of str or None, default None
        The arguments; None for ``sys.argv[1:]``.

    Returns
    -------
    int
        The exit code: 0.
    """
    from ._run_busyloop import run_busyloop
    from ._signals import install_usr1_handler

    parser = argparse.ArgumentParser(
        prog="python3 -m screendoor.daemon.run_busyloop",
        description=format_cli_description(__doc__),
    )
    parser.add_argument("--dispatchdir", default=".")
    args = parser.parse_args(argv)
    begin_prod_logging(args.dispatchdir)
    install_usr1_handler()
    run_busyloop(args.dispatchdir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
