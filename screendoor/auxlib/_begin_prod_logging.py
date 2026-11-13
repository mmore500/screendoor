import logging
import os


def begin_prod_logging(dispatchdir: str) -> None:
    """Configure logging to stderr and to `<dispatchdir>/dispatch_log.txt`.

    Parameters
    ----------
    dispatchdir : str
        Path of the dispatchdir, created if missing.
    """
    os.makedirs(dispatchdir, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(os.path.join(dispatchdir, "dispatch_log.txt")),
        ],
        force=True,
    )
