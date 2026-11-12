import pytest

from screendoor.testing import FakeClock, write_dispatchdir_hooks


@pytest.fixture
def clock():
    with FakeClock() as c:
        yield c


@pytest.fixture
def dispatchdir(tmp_path):
    """A dispatchdir whose dispatch_hooks.json sets every daemon hook."""
    path = str(tmp_path / "wd")
    write_dispatchdir_hooks(path)
    return path
