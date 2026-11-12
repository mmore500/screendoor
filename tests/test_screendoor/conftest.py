import pytest

from screendoor.testing import FakeClock, write_workdir_hooks


@pytest.fixture
def clock():
    with FakeClock() as c:
        yield c


@pytest.fixture
def workdir(tmp_path):
    """A workdir whose screendoor.json sets every daemon hook."""
    path = str(tmp_path / "wd")
    write_workdir_hooks(path)
    return path
