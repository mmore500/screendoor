"""Built-in assays: churn functions for smoke tests, potentiation scans
and skeletonization."""

from ..auxlib._lazy_attach_stub import lazy_attach_stub

__getattr__, __dir__, __all__ = lazy_attach_stub(__name__, __file__)
