"""Slotted JSONL v0.1: one fixed-size, checksummed slot per record, so
many writers can fill one shared file with no locks."""

from ...auxlib._lazy_attach_stub import lazy_attach_stub

__getattr__, __dir__, __all__ = lazy_attach_stub(__name__, __file__)
