"""JSONL records, one `O_APPEND` write per line, or under fcntl locks with
`lock=True` for filesystems where appends can tear (NFS across nodes)."""

from ...auxlib._lazy_attach_stub import lazy_attach_stub

__getattr__, __dir__, __all__ = lazy_attach_stub(__name__, __file__)
