# Skeletonizing Avida organisms

`avida_fitness.py` scores one genome on Avida's Test CPU (`avida -a`) and
prints `!!!screendoor:payload {"score": fitness, "viable": ..., "tasks":
[...]}`. It runs Avida in the [devosoft/avida](https://github.com/devosoft/avida)
container, `ghcr.io/devosoft/avida:latest`, through `singularity exec`, so
it needs Singularity or Apptainer and nothing else. Knocked-out sites are
`nop-X` (`A`). `make_dispatch.py` accepts a knockout if it is viable, keeps
every wildtype task and keeps fitness within `--rel-tol` (2%) of the
wildtype's.

From this directory, with screendoor installed:

```bash
mkdir -p work && cp dispatch_hooks.json work/   # the daemon's hooks
python3 make_dispatch.py nand_50 --policy hybrid \
  | python3 -m screendoor.daemon.submit_dispatch - --dispatchdir work
python3 -m screendoor.daemon.run_busyloop --dispatchdir work
```

The organism is a name in `organisms.json`, or `seq:<genome>`. `--policy`
is `ddmin`, `minesweeper`, `hybrid` or `gama`. `--num-control-trials N`
(default 40) sets how many wildtype controls scores are judged against;
the Test CPU is deterministic, so these all agree, and any loss in fitness
beyond `--rel-tol` is a loss. `--assay-kwargs JSON` adds assay kwargs.
GAMA's defaults are the paper's cluster-scale population sizes, so smaller
ones are a good idea here:

```bash
python3 make_dispatch.py nand_50 --policy gama --assay-kwargs \
  '{"guess_subsets": 16, "add_combinations": 32, "elite_size": 8,
    "mate_children": 24, "mate_patience": 3}'
```

Each trial starts a container, which costs a second or two. For many
trials, or on a cluster where the nodes should not all pull the image at
once, pull it once to a file on shared storage and point the trials at it:

```bash
singularity pull avida.sif docker://ghcr.io/devosoft/avida:latest
python3 make_dispatch.py nand_50 --image "$PWD/avida.sif" --orchestrator slurm
```

`run_local.sh [dispatchdir]` submits every policy for a few organisms and
runs the busy-loop daemon with the subprocess orchestrator. With
`KILL_AFTER_S=N`, it SIGKILLs the daemon after N seconds and restarts it,
to show that dispatches resume from their records.
