# Skeletonizing Avida organisms

`avida_fitness.py` scores one sequence on Avida's Test CPU (`avida -a`) and
prints `!!!screendoor:result {"score": fitness, "viable", "tasks", ...}`.
Knocked-out sites are `nop-X` (`A`), as in the 2026-11-03 work. Acceptance
(`make_dispatch.py`) matches `AvidaExactOracle(rel_fitness_tol=0.02)`.

```bash
export AVIDA_BINARY=~/2026-11-03/build/avida/bin/avida
export AVIDA_CONFIG_DIR=~/2026-11-03/vendor/avida/avida-core/support/config
python3 make_dispatch.py nand_50 --policy hybrid \
  | python3 -m screendoor.daemon.submit_dispatch - --workdir work
python3 -m screendoor.daemon.run_busyloop --workdir work
```

`run_local.sh [workdir]` submits every policy for several organisms and runs
the busy-loop daemon with the subprocess orchestrator. With `KILL_AFTER_S=N`,
it SIGKILLs the daemon after N seconds and restarts it.
