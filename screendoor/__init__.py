"""screendoor: dynamic screens driven by append-only JSONL records."""

__version__ = "0.1.2"

from .auxlib._lazy_attach_stub import lazy_attach_stub  # noqa: E402

__getattr__, __dir__, __all__ = lazy_attach_stub(__name__, __file__)
