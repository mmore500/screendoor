"""List screendoor's commands."""

COMMANDS = {
    "screendoor.daemon.submit_dispatch": "submit a dispatch (JSON or -)",
    "screendoor.daemon.run_busyloop": "tick, sleep, repeat until none open",
    "screendoor.daemon.run_tick_once": "tick due dispatches once (cron)",
    "screendoor.daemon.slurm.submit_daemon": "start the Slurm daemon chain",
    "screendoor.daemon.kill_dispatch": "cancel trials and pause dispatches",
    "screendoor.daemon.resume_dispatch": "resume killed dispatches",
    "screendoor.daemon.print_status": "show every dispatch in a workdir",
    "screendoor.daemon.replay_dispatch": "replay churn over a run dir",
    "screendoor.trial.worker": "run trials (launched for you)",
}

if __name__ == "__main__":
    from . import __version__

    print(f"screendoor {__version__}\n")
    for cmd, what in COMMANDS.items():
        print(f"  python3 -m {cmd:42} {what}")
