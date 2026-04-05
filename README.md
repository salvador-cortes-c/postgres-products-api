# Postgres Products API

A FastAPI service for read-only access to product pricing data from the NZ supermarket scraper. The API provides REST endpoints to query supermarkets, stores, products, categories, and historical price snapshots from a PostgreSQL database.

The API uses explicit Pydantic response models, so endpoint responses are typed, validated, and reflected accurately in the generated OpenAPI schema.

## Features

- **Product Search** - Query products by name with store and supermarket filtering
- **Category Browsing** - Fetch a category and its latest products in one call
- **Price History** - Track price changes over time
- **Supermarket Information** - List supported supermarket brands
- **Store Information** - List all stores, optionally filtered by supermarket
- **Health Check** - Verify API and database connectivity
- **API Key Protection** - Optional header-based auth for public deployments
- **Deployment Hardening** - Safer CORS defaults, trusted host filtering, hidden docs in production, and response security headers

## Prerequisites

- Docker & Docker Compose (recommended for local development)
- Python 3.12+ (if running without Docker)
- PostgreSQL 14+ (if running locally)

## Quick Start with Docker Compose

The easiest way to get started is with Docker Compose, which automatically sets up PostgreSQL and the API:

```bash
# Start both the API and PostgreSQL database
docker compose up -d --build

# Initialize the database schema (runs automatically on first start)
# The schema.sql is applied via docker-entrypoint-initdb.d

# Check API health
curl http://localhost:8000/health

# View API documentation
$BROWSER http://localhost:8000/docs
```

The API will be available at `http://localhost:8000` and the database at `localhost:5432`.

## Local Development (Without Docker)

### 1. Set Up PostgreSQL

Option A: Local PostgreSQL installation
```bash
sudo apt-get install postgresql postgresql-contrib  # Ubuntu/Debian
brew install postgresql                               # macOS
```

Option B: Use Supabase or Neon for cloud PostgreSQL
```bash
# Get your free database from:
# https://supabase.com (PostgreSQL with 500MB free tier)
# https://www.neon.tech (PostgreSQL with free tier)
```

### 2. Create Database and Apply Schema

```bash
# Local PostgreSQL
createdb products_db
psql products_db -f db/schema.sql

# Or for cloud (e.g., Supabase):
psql "postgresql://user:password@host:5432/database_name" -f db/schema.sql
```

### 3. Set Up Python Environment

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

pip install -r requirements.txt
```

### 4. Configure Database URL

```bash
# Local PostgreSQL (default)
export DATABASE_URL="postgresql://localhost/products_db"

# Or cloud PostgreSQL (Supabase/Neon)
export DATABASE_URL="postgresql://user:password@host:5432/database_name"
```

Optional: protect all read endpoints except `/health` with an API key:

```bash
export API_KEY="replace-with-a-long-random-secret"
```

### 5. Run the API

```bash
uvicorn main:app --reload
```

The API will be available at `http://localhost:8000`.

## API Endpoints

### Health Check

```bash
GET /health
```

Response:
```json
{"status": "ok"}
```

### Supermarkets

```bash
GET /supermarkets
```

Returns all supermarket brands sorted by name.

### Stores

```bash
GET /stores?supermarket=New%20World
```

Returns all stores sorted by name, with optional supermarket filtering.

### Categories

```bash
GET /categories
```

Returns all product categories sorted by name.

### Category Products

```bash
GET /categories/{category_id}/products?q=search_term&store=store_name&supermarket=supermarket_name&limit=100&offset=0
```

Returns the requested category plus the latest snapshot per product within that category.

Example:
```bash
curl "http://localhost:8000/categories/1/products"
curl "http://localhost:8000/categories/1/products?store=New%20World%20Karori"
curl "http://localhost:8000/categories/1/products?supermarket=New%20World"
```

### Products Search

```bash
GET /products?q=search_term&store=store_name&supermarket=supermarket_name&limit=100&offset=0
```

Query parameters:
- `q` - Search products by name (partial match, case-insensitive)
- `store` - Filter by store name
- `supermarket` - Filter by supermarket brand
- `limit` - Results per page (default: 100, max: 1000)
- `offset` - Pagination offset (default: 0)

Example:
```bash
# Search for all milk products
curl "http://localhost:8000/products?q=milk&limit=20"

# Search in specific store
curl "http://localhost:8000/products?q=milk&store=New%20World%20Karori"

# Search across a supermarket brand
curl "http://localhost:8000/products?q=milk&supermarket=New%20World"
```

### Latest Price

```bash
GET /products/{product_key}/latest?store=store_name&supermarket=supermarket_name
```

Gets the most recent price snapshot for a product.

Example:
```bash
curl "http://localhost:8000/products/milk-blue-robur-1l/latest"
```

### Price History

```bash
GET /products/{product_key}/history?store=store_name&supermarket=supermarket_name&limit=365
```

Gets historical price snapshots for a product.

Query parameters:
- `store` - Filter by store name (optional)
- `supermarket` - Filter by supermarket brand (optional)
- `limit` - Number of snapshots (default: 365, max: 5000)

Example:
```bash
# Last 365 snapshots for a product across all stores
curl "http://localhost:8000/products/milk-blue-robur-1l/history"

# Last 30 snapshots from a specific store
curl "http://localhost:8000/products/milk-blue-robur-1l/history?limit=30&store=New%20World%20Karori"
```

## Interactive API Docs

Open your browser to:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

These provide interactive exploration of all endpoints.

## Database Schema

The database includes the following tables:

- **products** - Product information (name, packaging, image)
- **supermarkets** - Normalized supermarket brands such as New World, Pak'nSave, and Woolworths
- **stores** - Store locations linked to a supermarket brand
- **categories** - Product categories
- **product_categories** - M:M relationship between products and categories
- **price_snapshots** - Historical price data with timestamps and supermarket/store references
- **crawl_runs** - Metadata about scraping runs

See [db/schema.sql](db/schema.sql) for detailed schema definition.

## Data Flow

1. **Scraper** from [salvador-cortes-c/python-playwright-scraper](https://github.com/salvador-cortes-c/python-playwright-scraper) collects product data
2. **Scraper** stores data in PostgreSQL via `--persist-db` flag
3. **API** reads data from PostgreSQL for frontend consumption

## Deployment

### Cloud Deployment (e.g., Railway, Heroku, DigitalOcean)

1. Create a free PostgreSQL database (Supabase, Neon, or cloud provider)
2. Set `DATABASE_URL` environment variable
3. Deploy the API container with port `8000` exposed:

```bash
# Example container run
docker build -t postgres-products-api .
docker run --rm -p 8000:8000 -e DATABASE_URL="$DATABASE_URL" postgres-products-api
```

### Environment Variables

- `DATABASE_URL` - PostgreSQL connection string (required)
- `API_KEY` - shared secret for `X-API-Key` protection on all read endpoints except `/health` (**required in production**)
- `APP_ENV` - set to `production` to disable `/docs`, `/redoc`, and `/openapi.json` by default
- `REQUIRE_API_KEY` - optional override to force auth outside production too; defaults to `true` in production
- `ALLOWED_ORIGINS` - comma-separated browser origins allowed to call the API (defaults to local Next.js dev origins only)
- `ALLOWED_ORIGIN_REGEX` - optional regex for preview URLs if you need flexible origin matching
- `ALLOWED_HOSTS` - comma-separated hostnames to accept, used to block unexpected `Host` headers
- `ENABLE_DOCS` - set to `true` only when you intentionally want docs exposed in production

Recommended production values:

```bash
export APP_ENV="production"
export API_KEY="replace-with-a-long-random-secret"
export ALLOWED_ORIGINS="https://your-frontend.example.com"
export ALLOWED_HOSTS="your-api.example.com"
```

### Authentication

When `API_KEY` is set, requests to `/stores`, `/categories`, `/categories/{category_id}/products`, `/products`, `/products/{product_key}/latest`, and `/products/{product_key}/history` must include:

```bash
curl -H "X-API-Key: $API_KEY" "http://localhost:8000/products?limit=5"
```

If `API_KEY` is not set, the API stays open only in local development. In production it now **fails closed** and returns `503` until the shared secret is configured.

## Development

### Running Tests

```bash
python -m pytest
```

The test suite uses FastAPI's test client and mocks database access, so it does not require a running PostgreSQL instance.

To run the real Postgres-backed integration tests locally:

```bash
docker compose up -d db
export TEST_DATABASE_URL="postgresql://products_user:products_pass@localhost:5432/products_db"
python -m pytest tests/test_integration.py
```

The integration suite applies [db/schema.sql](db/schema.sql) to the test database, truncates tables between tests, and seeds a small fixture dataset.

### Continuous Integration

GitHub Actions runs syntax validation plus both unit and Postgres-backed integration tests on every push and pull request.

### Code Style

Uses Python 3.12+ features (e.g., `|` for type unions).

## Support

For issues related to scraping or ingestion, see [salvador-cortes-c/python-playwright-scraper](https://github.com/salvador-cortes-c/python-playwright-scraper).

## License

See main project license.
