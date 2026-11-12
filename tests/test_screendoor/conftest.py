import pytest

from screendoor.testing import FakeClock


@pytest.fixture
def clock():
    with FakeClock() as c:
        yield c


@pytest.fixture
def workdir(tmp_path):
    return str(tmp_path / "wd")
