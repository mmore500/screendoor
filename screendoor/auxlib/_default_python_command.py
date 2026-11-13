import os
import shlex
import sys


def default_python_command() -> str:
    """Build a shell command that runs this interpreter with this copy of
    screendoor importable.

    Returns
    -------
    str
        `sys.executable`, run with this copy's root prepended to
        `PYTHONPATH`.
    """
    root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    return (
        f"env PYTHONPATH={shlex.quote(os.path.abspath(root))}"
        f"${{PYTHONPATH:+:$PYTHONPATH}} {shlex.quote(sys.executable)}"
    )
