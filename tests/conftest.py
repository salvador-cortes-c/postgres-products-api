from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator

import psycopg
import pytest


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "db" / "schema.sql"


def _integration_database_url() -> str:
    value = os.getenv("TEST_DATABASE_URL")
    if not value:
        pytest.skip("TEST_DATABASE_URL is not set; skipping integration tests")
    return value


@pytest.fixture(scope="session")
def integration_database_url() -> str:
    return _integration_database_url()


@pytest.fixture(scope="session", autouse=True)
def ensure_test_schema() -> Iterator[None]:
    integration_database_url = os.getenv("TEST_DATABASE_URL")
    if not integration_database_url:
        yield
        return

    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    with psycopg.connect(integration_database_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(schema_sql)
    yield


@pytest.fixture(autouse=True)
def reset_test_database() -> Iterator[None]:
    integration_database_url = os.getenv("TEST_DATABASE_URL")
    if not integration_database_url:
        yield
        return

    with psycopg.connect(integration_database_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                TRUNCATE TABLE
                    price_snapshots,
                    product_categories,
                    crawl_runs,
                    categories,
                    stores,
                    supermarkets,
                    products
                RESTART IDENTITY CASCADE;
                """
            )
    yield