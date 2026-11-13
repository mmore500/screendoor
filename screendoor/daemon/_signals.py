import signal

STOP = {"requested": False}


def install_usr1_handler() -> None:
    """Make SIGUSR1 ask the daemon to finish its current tick and stop."""
    signal.signal(
        signal.SIGUSR1, lambda signum, frame: STOP.update(requested=True)
    )
