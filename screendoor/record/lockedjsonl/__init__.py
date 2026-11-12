"""JSONL records whose every append and read holds an fcntl lock, for
filesystems where O_APPEND alone does not keep lines whole (NFS)."""

from ...auxlib._lazy_attach_stub import lazy_attach_stub

__getattr__, __dir__, __all__ = lazy_attach_stub(__name__, __file__)
