import textwrap


def format_cli_description(text: str) -> str:
    return textwrap.dedent(text).strip() + "\n"
