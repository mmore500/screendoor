import inspect
import re

import pytest

import screendoor as scd

MODULES = (
    scd.orch.inline,
    scd.orch.slurm,
    scd.orch.subprocess,
    scd.notify.log,
    scd.notify.null,
    scd.notify.pushover,
    scd.record.appendjsonl,
    scd.record.lockedjsonl,
    scd.record.slottedjsonl,
    scd.unblock,
    scd.cleanup,
)
FACTORY = re.compile(
    r"(launch|poke|kill|throttle|notify\w*|flush|setup|prep_trial_payloads"
    r"|(read|write)_\w+|all_trials_ready|tar|clear)$"
)
FACTORIES = [
    (f"{m.__name__}.{name}", getattr(m, name))
    for m in MODULES
    for name in dir(m)
    if FACTORY.match(name)
]


@pytest.mark.parametrize(
    "name,factory", FACTORIES, ids=[n for n, _ in FACTORIES]
)
def test_hook_factories_take_keywords_only(name, factory):
    params = inspect.signature(factory).parameters.values()
    assert all(p.kind is p.KEYWORD_ONLY for p in params), name


def test_every_module_has_factories():
    assert {name.rsplit(".", 1)[0] for name, _ in FACTORIES} == {
        m.__name__ for m in MODULES
    }
