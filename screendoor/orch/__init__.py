"""Orchestrators: `launch`, `poke`, `kill` and `throttle` hooks that run
trial jobs as local processes, as Slurm array jobs or in-process."""

from ..auxlib._lazy_attach_stub import lazy_attach_stub

__getattr__, __dir__, __all__ = lazy_attach_stub(__name__, __file__)
