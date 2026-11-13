"""Trial payloads in fixed-size, checksummed slots of one shared file,
which many writers can fill without locks."""

from ...auxlib._lazy_attach_stub import lazy_attach_stub

__getattr__, __dir__, __all__ = lazy_attach_stub(__name__, __file__)
