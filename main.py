from __future__ import annotations

from datetime import datetime
import os
import secrets
from typing import Any

import psycopg
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Security, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.security import APIKeyHeader
from pydantic import BaseModel
from psycopg.rows import dict_row


class HealthResponse(BaseModel):
    status: str


class SupermarketResponse(BaseModel):
    id: int
    name: str
    code: str
    created_at: datetime


class StoreResponse(BaseModel):
    id: int
    supermarket_id: int | None = None
    supermarket_name: str | None = None
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
    supermarket_name: str | None = None
    price_cents: int | None = None
    unit_price_text: str
    promo_price_cents: int | None = None
    promo_unit_price_text: str
    scraped_at: datetime


class CategoryProductsResponse(BaseModel):
    category: CategoryResponse
    products: list[ProductSummaryResponse]


class ProductLatestPriceResponse(BaseModel):
    product_key: str
    name: str
    packaging_format: str
    image_url: str
    store_name: str | None = None
    supermarket_name: str | None = None
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
    supermarket_name: str | None = None
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


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _csv_env(name: str) -> list[str]:
    value = os.getenv(name, "")
    return [item.strip() for item in value.split(",") if item.strip()]


def _is_production() -> bool:
    app_env = os.getenv("APP_ENV")
    if app_env and app_env.strip():
        return app_env.strip().lower() in {"prod", "production"}

    hosted_markers = (
        "RAILWAY_ENVIRONMENT_NAME",
        "RAILWAY_PROJECT_ID",
        "RAILWAY_SERVICE_ID",
        "VERCEL",
        "K_SERVICE",
    )
    return any(os.getenv(name) for name in hosted_markers)


def _docs_enabled() -> bool:
    return _env_flag("ENABLE_DOCS", default=not _is_production())


def _auth_required() -> bool:
    return _env_flag("REQUIRE_API_KEY", default=_is_production())


def _allowed_origins() -> list[str]:
    configured = _csv_env("ALLOWED_ORIGINS")
    if configured:
        return configured
    return [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]


api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def _api_key() -> str | None:
    return os.getenv("API_KEY")


def _require_api_key(api_key: str | None = Security(api_key_header)) -> None:
    expected_api_key = _api_key()
    if not expected_api_key:
        if _auth_required():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="API authentication is not configured",
            )
        return
    provided_api_key = api_key or ""
    if not secrets.compare_digest(provided_api_key, expected_api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )


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


docs_enabled = _docs_enabled()

app = FastAPI(
    title="NZ Supermarket Products API",
    version="0.3.0",
    docs_url="/docs" if docs_enabled else None,
    redoc_url="/redoc" if docs_enabled else None,
    openapi_url="/openapi.json" if docs_enabled else None,
)

allowed_hosts = _csv_env("ALLOWED_HOSTS")
if allowed_hosts:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins(),
    allow_origin_regex=os.getenv("ALLOWED_ORIGIN_REGEX") or None,
    allow_credentials=False,
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["Accept", "Content-Type", "X-API-Key"],
    max_age=600,
)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")

    if request.url.path not in {"/docs", "/redoc", "/openapi.json"}:
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
        )

    forwarded_proto = request.headers.get("x-forwarded-proto", request.url.scheme).lower()
    if forwarded_proto == "https":
        response.headers.setdefault("Strict-Transport-Security", "max-age=63072000; includeSubDomains")

    return response


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    _ = _database_url()
    return HealthResponse(status="ok")


@app.get("/supermarkets", response_model=list[SupermarketResponse])
def supermarkets(_: None = Depends(_require_api_key)) -> list[SupermarketResponse]:
    rows = _fetch_all("SELECT id, name, code, created_at FROM supermarkets ORDER BY name ASC")
    return [SupermarketResponse.model_validate(row) for row in rows]


@app.get("/stores", response_model=list[StoreResponse])
def stores(
    supermarket: str | None = None,
    _: None = Depends(_require_api_key),
) -> list[StoreResponse]:
    params: list[Any] = []
    where_sql = ""
    if supermarket:
        where_sql = "WHERE sm.name = %s"
        params.append(supermarket)
    rows = _fetch_all(
        f"""
        SELECT s.id, s.supermarket_id, sm.name AS supermarket_name, s.name, s.created_at
        FROM stores s
        LEFT JOIN supermarkets sm ON sm.id = s.supermarket_id
        {where_sql}
        ORDER BY sm.name ASC NULLS LAST, s.name ASC
        """,
        tuple(params),
    )
    return [StoreResponse.model_validate(row) for row in rows]


@app.get("/categories", response_model=list[CategoryResponse])
def categories(_: None = Depends(_require_api_key)) -> list[CategoryResponse]:
    rows = _fetch_all("SELECT id, name, url, source_url, created_at FROM categories ORDER BY name ASC")
    return [CategoryResponse.model_validate(row) for row in rows]


@app.get("/categories/{category_id}/products", response_model=CategoryProductsResponse)
def category_products(
    category_id: int,
    q: str | None = None,
    store: str | None = None,
    supermarket: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    _: None = Depends(_require_api_key),
) -> CategoryProductsResponse:
    category_row = _fetch_one(
        "SELECT id, name, url, source_url, created_at FROM categories WHERE id = %s",
        (category_id,),
    )
    if category_row is None:
        raise HTTPException(status_code=404, detail="Category not found")

    filters = ["pc.category_id = %s"]
    params: list[Any] = [category_id]

    if q:
        filters.append("p.name ILIKE %s")
        params.append(f"%{q}%")

    if store:
        filters.append("s.name = %s")
        params.append(store)

    if supermarket:
        filters.append("sm.name = %s")
        params.append(supermarket)

    where_sql = f"WHERE {' AND '.join(filters)}"
    product_rows = _fetch_all(
        f"""
        SELECT DISTINCT ON (p.product_key)
            p.product_key,
            p.name,
            p.packaging_format,
            p.image_url,
            s.name AS store_name,
            sm.name AS supermarket_name,
            ps.price_cents,
            ps.unit_price_text,
            ps.promo_price_cents,
            ps.promo_unit_price_text,
            ps.scraped_at
        FROM product_categories pc
        JOIN products p ON p.product_key = pc.product_key
        JOIN price_snapshots ps ON ps.product_key = p.product_key
        LEFT JOIN stores s ON s.id = ps.store_id
        LEFT JOIN supermarkets sm ON sm.id = COALESCE(ps.supermarket_id, s.supermarket_id)
        {where_sql}
        ORDER BY p.product_key, ps.scraped_at DESC
        LIMIT %s OFFSET %s;
        """,
        tuple([*params, limit, offset]),
    )
    return CategoryProductsResponse(
        category=CategoryResponse.model_validate(category_row),
        products=[ProductSummaryResponse.model_validate(row) for row in product_rows],
    )


@app.get("/products", response_model=list[ProductSummaryResponse])
def products(
    q: str | None = None,
    store: str | None = None,
    supermarket: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    _: None = Depends(_require_api_key),
) -> list[ProductSummaryResponse]:
    filters: list[str] = []
    params: list[Any] = []

    if q:
        filters.append("p.name ILIKE %s")
        params.append(f"%{q}%")

    if store:
        filters.append("s.name = %s")
        params.append(store)

    if supermarket:
        filters.append("sm.name = %s")
        params.append(supermarket)

    where_sql = f"WHERE {' AND '.join(filters)}" if filters else ""

    # DISTINCT ON returns latest snapshot per product (optionally per store filter).
    query = f"""
        SELECT DISTINCT ON (p.product_key)
            p.product_key,
            p.name,
            p.packaging_format,
            p.image_url,
            s.name AS store_name,
            sm.name AS supermarket_name,
            ps.price_cents,
            ps.unit_price_text,
            ps.promo_price_cents,
            ps.promo_unit_price_text,
            ps.scraped_at
        FROM products p
        JOIN price_snapshots ps ON ps.product_key = p.product_key
        LEFT JOIN stores s ON s.id = ps.store_id
        LEFT JOIN supermarkets sm ON sm.id = COALESCE(ps.supermarket_id, s.supermarket_id)
        {where_sql}
        ORDER BY p.product_key, ps.scraped_at DESC
        LIMIT %s OFFSET %s;
    """
    params.extend([limit, offset])
    rows = _fetch_all(query, tuple(params))
    return [ProductSummaryResponse.model_validate(row) for row in rows]


@app.get("/products/{product_key}/latest", response_model=ProductLatestPriceResponse)
def latest_price(
    product_key: str,
    store: str | None = None,
    supermarket: str | None = None,
    _: None = Depends(_require_api_key),
) -> ProductLatestPriceResponse:
    filters = ["p.product_key = %s"]
    params: list[Any] = [product_key]
    if store:
        filters.append("s.name = %s")
        params.append(store)
    if supermarket:
        filters.append("sm.name = %s")
        params.append(supermarket)

    row = _fetch_one(
        f"""
        SELECT
            p.product_key,
            p.name,
            p.packaging_format,
            p.image_url,
            s.name AS store_name,
            sm.name AS supermarket_name,
            ps.price_cents,
            ps.unit_price_text,
            ps.promo_price_cents,
            ps.promo_unit_price_text,
            ps.source_url,
            ps.scraped_at
        FROM products p
        JOIN price_snapshots ps ON ps.product_key = p.product_key
        LEFT JOIN stores s ON s.id = ps.store_id
        LEFT JOIN supermarkets sm ON sm.id = COALESCE(ps.supermarket_id, s.supermarket_id)
        WHERE {' AND '.join(filters)}
        ORDER BY ps.scraped_at DESC
        LIMIT 1;
        """,
        tuple(params),
    )

    if row is None:
        raise HTTPException(status_code=404, detail="Product snapshot not found")
    return ProductLatestPriceResponse.model_validate(row)


@app.get("/products/{product_key}/history", response_model=list[PriceHistoryEntryResponse])
def price_history(
    product_key: str,
    store: str | None = None,
    supermarket: str | None = None,
    limit: int = Query(default=365, ge=1, le=5000),
    _: None = Depends(_require_api_key),
) -> list[PriceHistoryEntryResponse]:
    filters = ["ps.product_key = %s"]
    params: list[Any] = [product_key]
    if store:
        filters.append("s.name = %s")
        params.append(store)
    if supermarket:
        filters.append("sm.name = %s")
        params.append(supermarket)

    rows = _fetch_all(
        f"""
        SELECT
            ps.id,
            ps.product_key,
            s.name AS store_name,
            sm.name AS supermarket_name,
            ps.price_cents,
            ps.unit_price_text,
            ps.promo_price_cents,
            ps.promo_unit_price_text,
            ps.source_url,
            ps.scraped_at,
            ps.provider
        FROM price_snapshots ps
        LEFT JOIN stores s ON s.id = ps.store_id
        LEFT JOIN supermarkets sm ON sm.id = COALESCE(ps.supermarket_id, s.supermarket_id)
        WHERE {' AND '.join(filters)}
        ORDER BY ps.scraped_at DESC
        LIMIT %s;
        """,
        tuple([*params, limit]),
    )
    return [PriceHistoryEntryResponse.model_validate(row) for row in rows]
