import tempfile
from pathlib import Path
import pytest


@pytest.fixture
def tmp_data(tmp_path):
    d = tmp_path / "data"
    d.mkdir()
    (d / "projects").mkdir()
    (d / "projects" / "test-proj").mkdir(parents=True)
    return d
