import signal

STOP = {"requested": False}


def install_usr1_handler() -> None:
    """On SIGUSR1, finish the current tick and stop."""
    signal.signal(
        signal.SIGUSR1, lambda signum, frame: STOP.update(requested=True)
    )
