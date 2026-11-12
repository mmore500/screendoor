import os
import subprocess
import sys

import screendoor as scd


def test_import_screendoor_is_lazy():
    code = "import sys, screendoor; print(*sys.modules)"
    out = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "screendoor.daemon" not in out
    assert "screendoor.orch" not in out


def test_attribute_chain():
    assert callable(scd.orch.slurm.launch)
    assert callable(scd.assaylib.skeletonize.hybrid.churn)
    assert "hybrid" in dir(scd.assaylib.skeletonize)
    assert scd.auxlib.canonical_json({"b": 1, "a": 2}) == '{"a":2,"b":1}'


def test_stdlib_only():
    """Importing every module pulls in nothing outside the stdlib."""
    root = os.path.dirname(os.path.dirname(scd.__file__))
    code = f"""
import sys; sys.path.insert(0, {root!r})
import importlib, pkgutil, screendoor
for m in pkgutil.walk_packages(screendoor.__path__, 'screendoor.'):
    importlib.import_module(m.name)
ours = set(sys.stdlib_module_names) | {{'screendoor', '__main__'}}
theirs = {{n.split('.')[0] for n in sys.modules}} - ours
assert not [n for n in theirs if not n.startswith('_')], theirs
"""
    # -S skips site hooks (.pth files), which may import third-party code
    subprocess.run([sys.executable, "-S", "-c", code], check=True)
