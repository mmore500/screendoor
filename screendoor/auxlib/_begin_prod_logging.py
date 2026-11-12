import logging
import os


def begin_prod_logging(workdir: str) -> None:
    """Log to stderr and ``<workdir>/screendoor-log.txt``."""
    os.makedirs(workdir, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(os.path.join(workdir, "screendoor-log.txt")),
        ],
        force=True,
    )
