from __future__ import annotations

from fastapi.testclient import TestClient

import main


client = TestClient(main.app)


def test_health_returns_ok(monkeypatch) -> None:
    monkeypatch.setattr(main, "_database_url", lambda: "postgresql://example")

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_stores_endpoint_returns_rows(monkeypatch) -> None:
    monkeypatch.setattr(
        main,
        "_fetch_all",
        lambda query, params=(): [
            {"id": 1, "name": "New World Karori", "created_at": "2026-04-02T00:00:00Z"}
        ],
    )

    response = client.get("/stores")

    assert response.status_code == 200
    assert response.json()[0]["name"] == "New World Karori"


def test_stores_endpoint_requires_api_key_when_configured(monkeypatch) -> None:
    monkeypatch.setenv("API_KEY", "secret-key")

    response = client.get("/stores")

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid or missing API key"}


def test_stores_endpoint_accepts_api_key_when_configured(monkeypatch) -> None:
    monkeypatch.setenv("API_KEY", "secret-key")
    monkeypatch.setattr(
        main,
        "_fetch_all",
        lambda query, params=(): [
            {"id": 1, "name": "New World Karori", "created_at": "2026-04-02T00:00:00Z"}
        ],
    )

    response = client.get("/stores", headers={"X-API-Key": "secret-key"})

    assert response.status_code == 200
    assert response.json()[0]["name"] == "New World Karori"


def test_products_endpoint_forwards_filters(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_fetch_all(query: str, params: tuple[object, ...] = ()) -> list[dict[str, object]]:
        captured["query"] = query
        captured["params"] = params
        return [
            {
                "product_key": "milk-1l",
                "name": "Milk 1L",
                "packaging_format": "1L",
                "image_url": "https://example.test/milk.jpg",
                "store_name": "New World Karori",
                "price_cents": 379,
                "unit_price_text": "$3.79/L",
                "promo_price_cents": None,
                "promo_unit_price_text": "",
                "scraped_at": "2026-04-02T00:00:00Z",
            }
        ]

    monkeypatch.setattr(main, "_fetch_all", fake_fetch_all)

    response = client.get("/products", params={"q": "milk", "store": "New World Karori", "limit": 20, "offset": 5})

    assert response.status_code == 200
    assert response.json()[0]["product_key"] == "milk-1l"
    assert "p.name ILIKE %s" in str(captured["query"])
    assert "s.name = %s" in str(captured["query"])
    assert captured["params"] == ("%milk%", "New World Karori", 20, 5)


def test_latest_price_returns_404_when_missing(monkeypatch) -> None:
    monkeypatch.setattr(main, "_fetch_one", lambda query, params=(): None)

    response = client.get("/products/missing/latest")

    assert response.status_code == 404
    assert response.json() == {"detail": "Product snapshot not found"}


def test_price_history_endpoint_uses_store_filter(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_fetch_all(query: str, params: tuple[object, ...] = ()) -> list[dict[str, object]]:
        captured["query"] = query
        captured["params"] = params
        return [
            {
                "id": 1,
                "product_key": "milk-1l",
                "store_name": "New World Karori",
                "price_cents": 379,
                "unit_price_text": "$3.79/L",
                "promo_price_cents": None,
                "promo_unit_price_text": "",
                "source_url": "https://example.test/milk",
                "scraped_at": "2026-04-02T00:00:00Z",
                "provider": "playwright",
            }
        ]

    monkeypatch.setattr(main, "_fetch_all", fake_fetch_all)

    response = client.get("/products/milk-1l/history", params={"store": "New World Karori", "limit": 30})

    assert response.status_code == 200
    assert response.json()[0]["provider"] == "playwright"
    assert "s.name = %s" in str(captured["query"])
    assert captured["params"] == ("milk-1l", "New World Karori", 30)


def test_category_products_endpoint_returns_category_and_products(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_fetch_one(query: str, params: tuple[object, ...] = ()) -> dict[str, object] | None:
        captured["category_params"] = params
        return {
            "id": 1,
            "name": "Milk",
            "url": "https://example.test/category/milk",
            "source_url": "https://example.test/source/milk",
            "created_at": "2026-04-02T00:00:00Z",
        }

    def fake_fetch_all(query: str, params: tuple[object, ...] = ()) -> list[dict[str, object]]:
        captured["product_query"] = query
        captured["product_params"] = params
        return [
            {
                "product_key": "milk-1l",
                "name": "Milk 1L",
                "packaging_format": "1L",
                "image_url": "https://example.test/milk.jpg",
                "store_name": "New World Karori",
                "price_cents": 379,
                "unit_price_text": "$3.79/L",
                "promo_price_cents": None,
                "promo_unit_price_text": "",
                "scraped_at": "2026-04-02T00:00:00Z",
            }
        ]

    monkeypatch.setattr(main, "_fetch_one", fake_fetch_one)
    monkeypatch.setattr(main, "_fetch_all", fake_fetch_all)

    response = client.get("/categories/1/products", params={"store": "New World Karori", "limit": 20, "offset": 5})

    assert response.status_code == 200
    payload = response.json()
    assert payload["category"]["name"] == "Milk"
    assert payload["products"][0]["product_key"] == "milk-1l"
    assert captured["category_params"] == (1,)
    assert "pc.category_id = %s" in str(captured["product_query"])
    assert "s.name = %s" in str(captured["product_query"])
    assert captured["product_params"] == (1, "New World Karori", 20, 5)


def test_category_products_endpoint_returns_404_when_category_missing(monkeypatch) -> None:
    monkeypatch.setattr(main, "_fetch_one", lambda query, params=(): None)

    response = client.get("/categories/999/products")

    assert response.status_code == 404
    assert response.json() == {"detail": "Category not found"}


def test_products_endpoint_rejects_invalid_limit() -> None:
    response = client.get("/products", params={"limit": 0})

    assert response.status_code == 422