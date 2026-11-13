"""Fake time, complete hook sets, crash injection and whole-dispatch
simulation, for tests."""

from ..auxlib._lazy_attach_stub import lazy_attach_stub

__getattr__, __dir__, __all__ = lazy_attach_stub(__name__, __file__)
