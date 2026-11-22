"""
Shared setup for the tests.

Before any test runs, this rebuilds everything from scratch, exactly as a
user would: generate the data, load the database, run the SQL metrics.
Every test then reads from that fresh database, so the tests always check
the current code, not an old copy of the data.
"""

import hashlib
import importlib.util
import sqlite3
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"


def load_module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "src" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def data_fingerprint():
    """One hash per generated CSV, to compare two runs."""
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(DATA_DIR.glob("*.csv"))}


@pytest.fixture(scope="session")
def config():
    with open(ROOT / "rollout_config.toml", "rb") as f:
        return tomllib.load(f)


@pytest.fixture(scope="session")
def pipeline_run():
    """Run the full pipeline once per test session. Returns the data fingerprints
    from two back-to-back generator runs (used by the reproducibility test)."""
    generate = load_module("generate_data")
    generate.main()
    first = data_fingerprint()
    generate.main()
    second = data_fingerprint()
    load_module("load_database").main()
    load_module("calculate_metrics").main()
    return first, second


@pytest.fixture(scope="session")
def db(pipeline_run):
    con = sqlite3.connect(DATA_DIR / "scorecard.db")
    yield con
    con.close()


def count(db, query):
    """Run a query that returns a single number."""
    return db.execute(query).fetchone()[0]
