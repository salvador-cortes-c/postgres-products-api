from __future__ import annotations

from datetime import datetime
import os
from typing import Any

import psycopg
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from psycopg.rows import dict_row


class HealthResponse(BaseModel):
    status: str


class StoreResponse(BaseModel):
    id: int
    name: str
    created_at: datetime


class CategoryResponse(BaseModel):
    id: int
    name: str
    url: str
    source_url: str
    created_at: datetime


class ProductSummaryResponse(BaseModel):
    product_key: str
    name: str
    packaging_format: str
    image_url: str
    store_name: str | None = None
    price_cents: int | None = None
    unit_price_text: str
    promo_price_cents: int | None = None
    promo_unit_price_text: str
    scraped_at: datetime


class ProductLatestPriceResponse(BaseModel):
    product_key: str
    name: str
    packaging_format: str
    image_url: str
    store_name: str | None = None
    price_cents: int | None = None
    unit_price_text: str
    promo_price_cents: int | None = None
    promo_unit_price_text: str
    source_url: str
    scraped_at: datetime


class PriceHistoryEntryResponse(BaseModel):
    id: int
    product_key: str
    store_name: str | None = None
    price_cents: int | None = None
    unit_price_text: str
    promo_price_cents: int | None = None
    promo_unit_price_text: str
    source_url: str
    scraped_at: datetime
    provider: str


def _database_url() -> str:
    value = os.getenv("DATABASE_URL")
    if not value:
        raise RuntimeError("DATABASE_URL is not set")
    return value


def _fetch_all(query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    with psycopg.connect(_database_url(), row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall()
            return [dict(row) for row in rows]


def _fetch_one(query: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    with psycopg.connect(_database_url(), row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            row = cur.fetchone()
            return dict(row) if row else None


app = FastAPI(title="New World Scraper API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    _ = _database_url()
    return HealthResponse(status="ok")


@app.get("/stores", response_model=list[StoreResponse])
def stores() -> list[StoreResponse]:
    rows = _fetch_all("SELECT id, name, created_at FROM stores ORDER BY name ASC")
    return [StoreResponse.model_validate(row) for row in rows]


@app.get("/categories", response_model=list[CategoryResponse])
def categories() -> list[CategoryResponse]:
    rows = _fetch_all("SELECT id, name, url, source_url, created_at FROM categories ORDER BY name ASC")
    return [CategoryResponse.model_validate(row) for row in rows]


@app.get("/products", response_model=list[ProductSummaryResponse])
def products(
    q: str | None = None,
    store: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> list[ProductSummaryResponse]:
    filters: list[str] = []
    params: list[Any] = []

    if q:
        filters.append("p.name ILIKE %s")
        params.append(f"%{q}%")

    if store:
        filters.append("s.name = %s")
        params.append(store)

    where_sql = f"WHERE {' AND '.join(filters)}" if filters else ""

    # DISTINCT ON returns latest snapshot per product (optionally per store filter).
    query = f"""
        SELECT DISTINCT ON (p.product_key)
            p.product_key,
            p.name,
            p.packaging_format,
            p.image_url,
            s.name AS store_name,
            ps.price_cents,
            ps.unit_price_text,
            ps.promo_price_cents,
            ps.promo_unit_price_text,
            ps.scraped_at
        FROM products p
        JOIN price_snapshots ps ON ps.product_key = p.product_key
        LEFT JOIN stores s ON s.id = ps.store_id
        {where_sql}
        ORDER BY p.product_key, ps.scraped_at DESC
        LIMIT %s OFFSET %s;
    """
    params.extend([limit, offset])
    rows = _fetch_all(query, tuple(params))
    return [ProductSummaryResponse.model_validate(row) for row in rows]


@app.get("/products/{product_key}/latest", response_model=ProductLatestPriceResponse)
def latest_price(product_key: str, store: str | None = None) -> ProductLatestPriceResponse:
    if store:
        row = _fetch_one(
            """
            SELECT
                p.product_key,
                p.name,
                p.packaging_format,
                p.image_url,
                s.name AS store_name,
                ps.price_cents,
                ps.unit_price_text,
                ps.promo_price_cents,
                ps.promo_unit_price_text,
                ps.source_url,
                ps.scraped_at
            FROM products p
            JOIN price_snapshots ps ON ps.product_key = p.product_key
            LEFT JOIN stores s ON s.id = ps.store_id
            WHERE p.product_key = %s AND s.name = %s
            ORDER BY ps.scraped_at DESC
            LIMIT 1;
            """,
            (product_key, store),
        )
    else:
        row = _fetch_one(
            """
            SELECT
                p.product_key,
                p.name,
                p.packaging_format,
                p.image_url,
                s.name AS store_name,
                ps.price_cents,
                ps.unit_price_text,
                ps.promo_price_cents,
                ps.promo_unit_price_text,
                ps.source_url,
                ps.scraped_at
            FROM products p
            JOIN price_snapshots ps ON ps.product_key = p.product_key
            LEFT JOIN stores s ON s.id = ps.store_id
            WHERE p.product_key = %s
            ORDER BY ps.scraped_at DESC
            LIMIT 1;
            """,
            (product_key,),
        )

    if row is None:
        raise HTTPException(status_code=404, detail="Product snapshot not found")
    return ProductLatestPriceResponse.model_validate(row)


@app.get("/products/{product_key}/history", response_model=list[PriceHistoryEntryResponse])
def price_history(
    product_key: str,
    store: str | None = None,
    limit: int = Query(default=365, ge=1, le=5000),
) -> list[PriceHistoryEntryResponse]:
    if store:
        rows = _fetch_all(
            """
            SELECT
                ps.id,
                ps.product_key,
                s.name AS store_name,
                ps.price_cents,
                ps.unit_price_text,
                ps.promo_price_cents,
                ps.promo_unit_price_text,
                ps.source_url,
                ps.scraped_at,
                ps.provider
            FROM price_snapshots ps
            LEFT JOIN stores s ON s.id = ps.store_id
            WHERE ps.product_key = %s AND s.name = %s
            ORDER BY ps.scraped_at DESC
            LIMIT %s;
            """,
            (product_key, store, limit),
        )
        return [PriceHistoryEntryResponse.model_validate(row) for row in rows]

    rows = _fetch_all(
        """
        SELECT
            ps.id,
            ps.product_key,
            s.name AS store_name,
            ps.price_cents,
            ps.unit_price_text,
            ps.promo_price_cents,
            ps.promo_unit_price_text,
            ps.source_url,
            ps.scraped_at,
            ps.provider
        FROM price_snapshots ps
        LEFT JOIN stores s ON s.id = ps.store_id
        WHERE ps.product_key = %s
        ORDER BY ps.scraped_at DESC
        LIMIT %s;
        """,
        (product_key, limit),
    )
    return [PriceHistoryEntryResponse.model_validate(row) for row in rows]
