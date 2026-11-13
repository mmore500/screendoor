import textwrap


def format_cli_description(text: str) -> str:
    """Dedent and strip `text`, such as a module docstring, for use as an
    argparse description.

    Parameters
    ----------
    text : str
        The description.

    Returns
    -------
    str
        The text, ending in a single newline.
    """
    return textwrap.dedent(text).strip() + "\n"
