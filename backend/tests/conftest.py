import os
import shutil
from pathlib import Path

import pytest

os.environ["WORKSPACE_ROOT"] = "data/test-workspaces"


@pytest.fixture(scope="session", autouse=True)
def isolated_workspace_root():
    root = (Path(__file__).resolve().parents[1] / "data" / "test-workspaces").resolve()
    expected_parent = (Path(__file__).resolve().parents[1] / "data").resolve()
    if root.parent != expected_parent:
        raise RuntimeError("Test workspace root escaped backend/data")
    shutil.rmtree(root, ignore_errors=True)
    yield root
    shutil.rmtree(root, ignore_errors=True)
