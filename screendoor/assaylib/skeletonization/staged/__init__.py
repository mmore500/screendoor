"""Skeletonize in stages: screen out lethal knockouts with a cheap
pass/fail test, rank the remaining sites by regression on scored trials,
then confirm one cutoff."""

from ....auxlib._lazy_attach_stub import lazy_attach_stub

__getattr__, __dir__, __all__ = lazy_attach_stub(__name__, __file__)
