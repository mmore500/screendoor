"""Run each job as one `sbatch --array`, polled with one `squeue` per
tick."""

from ...auxlib._lazy_attach_stub import lazy_attach_stub

__getattr__, __dir__, __all__ = lazy_attach_stub(__name__, __file__)
