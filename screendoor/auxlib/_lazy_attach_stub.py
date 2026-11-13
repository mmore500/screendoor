import ast
import importlib
import os
import sys
import typing


def lazy_attach_stub(
    package_name: str, init_file: str
) -> tuple[
    typing.Callable[[str], typing.Any],
    typing.Callable[[], list[str]],
    list[str],
]:
    """Attach the names a package's `__init__.pyi` stub imports to the
    package lazily, importing each on first access.

    The stub may use `from ._mod import name` and `from . import sub`.

    Parameters
    ----------
    package_name : str
        The package's `__name__`.
    init_file : str
        The package's `__file__`; the stub sits beside it.

    Returns
    -------
    tuple
        `(__getattr__, __dir__, __all__)`, to assign at module level.
    """
    stub = os.path.splitext(init_file)[0] + ".pyi"
    try:
        with open(stub, encoding="utf-8") as fh:
            source = fh.read()
    except OSError:  # inside a zipapp: ask the package's loader
        loader = sys.modules[package_name].__spec__.loader
        source = loader.get_data(stub).decode()

    targets = {}  # public name -> (relative module, attribute or None)
    for node in ast.parse(source).body:
        if isinstance(node, ast.ImportFrom) and node.level == 1:
            for alias in node.names:
                targets[alias.asname or alias.name] = (
                    (f".{node.module}", alias.name)
                    if node.module
                    else (f".{alias.name}", None)
                )

    def __getattr__(name: str) -> typing.Any:
        if name not in targets:
            raise AttributeError(
                f"module {package_name!r} has no attribute {name!r}"
            )
        modname, attr = targets[name]
        module = importlib.import_module(modname, package_name)
        value = module if attr is None else getattr(module, attr)
        setattr(sys.modules[package_name], name, value)
        return value

    return __getattr__, lambda: sorted(targets), sorted(targets)
