"""Skeletonize in stages: find the minimal critical sets with a cheap
pass/fail test, then sort the remaining sites by their cost, estimated by
regression on scored trials, and confirm the longest subcritical prefix."""

from ....auxlib._lazy_attach_stub import lazy_attach_stub

__getattr__, __dir__, __all__ = lazy_attach_stub(__name__, __file__)
