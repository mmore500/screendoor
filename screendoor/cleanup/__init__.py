"""Hooks run once a dispatch completes (`how_cleanup_success` and
`how_cleanup_failure`)."""

from ..auxlib._lazy_attach_stub import lazy_attach_stub

__getattr__, __dir__, __all__ = lazy_attach_stub(__name__, __file__)
