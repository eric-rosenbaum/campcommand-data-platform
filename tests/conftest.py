from pathlib import Path

import pytest

from campcommand.clients import load_clients
from campcommand.contracts import ContractRegistry

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def registry() -> ContractRegistry:
    return ContractRegistry(REPO / "contracts")


@pytest.fixture(scope="session")
def clients():
    return load_clients(REPO / "clients")
