from __future__ import annotations

from datetime import datetime, timezone

import psycopg
from fastapi.testclient import TestClient

import main


def seed_database(database_url: str) -> None:
    with psycopg.connect(database_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO supermarkets (name, code)
                VALUES (%s, %s), (%s, %s)
                """,
                ("New World", "newworld", "Woolworths", "woolworths"),
            )
            cur.execute("SELECT id, code FROM supermarkets ORDER BY id ASC")
            supermarket_rows = {code: supermarket_id for supermarket_id, code in cur.fetchall()}
            cur.execute(
                "INSERT INTO stores (name, supermarket_id) VALUES (%s, %s), (%s, %s)",
                (
                    "New World Karori",
                    supermarket_rows["newworld"],
                    "New World Metro",
                    supermarket_rows["newworld"],
                ),
            )
            cur.execute(
                """
                INSERT INTO categories (name, url, source_url)
                VALUES (%s, %s, %s), (%s, %s, %s)
                """,
                (
                    "Milk",
                    "https://example.test/category/milk",
                    "https://example.test/source/milk",
                    "Bread",
                    "https://example.test/category/bread",
                    "https://example.test/source/bread",
                ),
            )
            cur.execute(
                """
                INSERT INTO products (product_key, name, packaging_format, image_url)
                VALUES (%s, %s, %s, %s), (%s, %s, %s, %s)
                """,
                (
                    "milk-1l",
                    "Milk 1L",
                    "1L",
                    "https://example.test/milk.jpg",
                    "bread-white",
                    "White Bread",
                    "700g",
                    "https://example.test/bread.jpg",
                ),
            )
            cur.execute(
                """
                INSERT INTO product_categories (product_key, category_id)
                VALUES
                    ('milk-1l', 1),
                    ('bread-white', 2)
                """
            )
            cur.execute(
                """
                INSERT INTO crawl_runs (provider, mode, started_at, finished_at, status, error_message)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    "playwright",
                    "full",
                    datetime(2026, 4, 2, 0, 0, tzinfo=timezone.utc),
                    datetime(2026, 4, 2, 0, 5, tzinfo=timezone.utc),
                    "success",
                    "",
                ),
            )
            crawl_run_id = cur.fetchone()[0]
            cur.execute(
                "SELECT id, name FROM stores ORDER BY id ASC"
            )
            store_rows = {name: store_id for store_id, name in cur.fetchall()}
            cur.execute(
                """
                INSERT INTO price_snapshots (
                    product_key,
                    store_id,
                    supermarket_id,
                    price_cents,
                    unit_price_text,
                    promo_price_cents,
                    promo_unit_price_text,
                    source_url,
                    scraped_at,
                    provider,
                    crawl_run_id
                ) VALUES
                    (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s),
                    (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s),
                    (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    "milk-1l",
                    store_rows["New World Karori"],
                    supermarket_rows["newworld"],
                    379,
                    "$3.79/L",
                    None,
                    "",
                    "https://example.test/milk/karori/latest",
                    datetime(2026, 4, 2, 10, 0, tzinfo=timezone.utc),
                    "playwright",
                    crawl_run_id,
                    "milk-1l",
                    store_rows["New World Karori"],
                    supermarket_rows["newworld"],
                    359,
                    "$3.59/L",
                    329,
                    "$3.29/L",
                    "https://example.test/milk/karori/older",
                    datetime(2026, 4, 1, 10, 0, tzinfo=timezone.utc),
                    "playwright",
                    crawl_run_id,
                    "bread-white",
                    store_rows["New World Metro"],
                    supermarket_rows["newworld"],
                    299,
                    "$4.27/kg",
                    None,
                    "",
                    "https://example.test/bread/metro/latest",
                    datetime(2026, 4, 2, 9, 0, tzinfo=timezone.utc),
                    "scrapingbee",
                    crawl_run_id,
                ),
            )


def test_health_checks_real_database(monkeypatch, integration_database_url: str) -> None:
    monkeypatch.setenv("DATABASE_URL", integration_database_url)
    client = TestClient(main.app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_products_returns_latest_snapshot_per_product(monkeypatch, integration_database_url: str) -> None:
    monkeypatch.setenv("DATABASE_URL", integration_database_url)
    seed_database(integration_database_url)
    client = TestClient(main.app)

    response = client.get("/products", params={"q": "milk", "store": "New World Karori"})

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["product_key"] == "milk-1l"
    assert payload[0]["supermarket_name"] == "New World"
    assert payload[0]["price_cents"] == 379


def test_latest_endpoint_returns_current_snapshot(monkeypatch, integration_database_url: str) -> None:
    monkeypatch.setenv("DATABASE_URL", integration_database_url)
    seed_database(integration_database_url)
    client = TestClient(main.app)

    response = client.get("/products/milk-1l/latest", params={"store": "New World Karori"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["product_key"] == "milk-1l"
    assert payload["price_cents"] == 379
    assert payload["source_url"] == "https://example.test/milk/karori/latest"


def test_history_endpoint_returns_descending_snapshots(monkeypatch, integration_database_url: str) -> None:
    monkeypatch.setenv("DATABASE_URL", integration_database_url)
    seed_database(integration_database_url)
    client = TestClient(main.app)

    response = client.get("/products/milk-1l/history", params={"store": "New World Karori", "limit": 10})

    assert response.status_code == 200
    payload = response.json()
    assert [item["price_cents"] for item in payload] == [379, 359]
    assert payload[0]["scraped_at"] > payload[1]["scraped_at"]


def test_stores_and_categories_read_from_database(monkeypatch, integration_database_url: str) -> None:
    monkeypatch.setenv("DATABASE_URL", integration_database_url)
    seed_database(integration_database_url)
    client = TestClient(main.app)

    supermarkets_response = client.get("/supermarkets")
    stores_response = client.get("/stores")
    categories_response = client.get("/categories")

    assert supermarkets_response.status_code == 200
    assert [item["name"] for item in supermarkets_response.json()] == ["New World", "Woolworths"]
    assert stores_response.status_code == 200
    assert [item["name"] for item in stores_response.json()] == ["New World Karori", "New World Metro"]
    assert stores_response.json()[0]["supermarket_name"] == "New World"
    assert categories_response.status_code == 200
    assert [item["name"] for item in categories_response.json()] == ["Bread", "Milk"]


def test_category_products_endpoint_reads_real_database(monkeypatch, integration_database_url: str) -> None:
    monkeypatch.setenv("DATABASE_URL", integration_database_url)
    seed_database(integration_database_url)
    client = TestClient(main.app)

    response = client.get("/categories/1/products", params={"store": "New World Karori"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["category"]["name"] == "Milk"
    assert len(payload["products"]) == 1
    assert payload["products"][0]["product_key"] == "milk-1l"
    assert payload["products"][0]["price_cents"] == 379


def test_api_key_protects_real_endpoint(monkeypatch, integration_database_url: str) -> None:
    monkeypatch.setenv("DATABASE_URL", integration_database_url)
    monkeypatch.setenv("API_KEY", "integration-secret")
    seed_database(integration_database_url)
    client = TestClient(main.app)

    unauthorized_response = client.get("/products")
    authorized_response = client.get("/products", headers={"X-API-Key": "integration-secret"})

    assert unauthorized_response.status_code == 401
    assert unauthorized_response.json() == {"detail": "Invalid or missing API key"}
    assert authorized_response.status_code == 200
    assert len(authorized_response.json()) == 2