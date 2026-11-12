# Skeletonizing Avida organisms

`avida_fitness.py` scores one sequence on Avida's Test CPU (`avida -a`) and
prints `!!!screendoor:payload {"score": fitness, "viable", "tasks", ...}`.
Knocked-out sites are `nop-X` (`A`). Acceptance (`make_dispatch.py`) matches
`knockout_skeleton.AvidaExactOracle(rel_fitness_tol=0.02)`: viable, every
wildtype task kept, and fitness within 2% of the wildtype's.

From this directory, with screendoor importable:

```bash
export AVIDA_BINARY=/path/to/avida
export AVIDA_CONFIG_DIR=/path/to/avida-core/support/config
mkdir -p work && cp screendoor.json work/   # the daemon's hooks
python3 make_dispatch.py nand_50 --policy hybrid \
  | python3 -m screendoor.daemon.submit_dispatch - --dispatchdir work
python3 -m screendoor.daemon.run_busyloop --dispatchdir work
```

The organism is a name in `organisms.json`, or `seq:<genome>`.
`run_local.sh [dispatchdir]` submits every policy for several organisms and
runs the busy-loop daemon with the subprocess orchestrator. With
`KILL_AFTER_S=N`, it SIGKILLs the daemon after N seconds and restarts it.
