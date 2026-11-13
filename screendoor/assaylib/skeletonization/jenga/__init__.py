"""Skeletonize by pulling removable components one at a time, like Jenga
blocks."""

from ....auxlib._lazy_attach_stub import lazy_attach_stub

__getattr__, __dir__, __all__ = lazy_attach_stub(__name__, __file__)
