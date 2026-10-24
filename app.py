from pathlib import Path
import csv

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field


app = FastAPI(
    title="ShopPilot API",
    description="Product catalog and search API for a local IT shop",
    version="0.3.0",
)

# Always locate products.csv beside this file
CSV_FILE = Path(__file__).parent / "products.csv"


class Product(BaseModel):
    product_id: str
    name: str
    category: str = ""
    brand: str = ""
    price_bdt: float | None = Field(default=None, ge=0)
    price_basis: str = ""
    stock_quantity: int | None = Field(default=None, ge=0)
    specifications: str = ""
    description: str = ""


def load_products() -> list[Product]:
    if not CSV_FILE.exists():
        raise RuntimeError(
            f"Could not find products.csv at: {CSV_FILE}"
        )

    products = []
    seen_ids = set()

    with CSV_FILE.open(
        mode="r", encoding="utf-8-sig", newline=""
    ) as file:
        reader = csv.DictReader(file)

        required_columns = {
            "product_id",
            "name",
            "category",
            "brand",
            "price_bdt",
            "price_basis",
            "stock_quantity",
            "specifications",
            "description",
        }

        if not reader.fieldnames or not required_columns.issubset(
            set(reader.fieldnames)
        ):
            raise RuntimeError(
                "products.csv is missing required columns."
            )

        for row in reader:
            product_id = (row.get("product_id") or "").strip()
            name = (row.get("name") or "").strip()

            if not product_id or not name:
                continue

            if product_id in seen_ids:
                raise RuntimeError(
                    f"Duplicate product ID: {product_id}"
                )
            seen_ids.add(product_id)

            raw_price = (row.get("price_bdt") or "").strip()
            raw_stock = (row.get("stock_quantity") or "").strip()

            products.append(
                Product(
                    product_id=product_id,
                    name=name,
                    category=(row.get("category") or "").strip(),
                    brand=(row.get("brand") or "").strip(),
                    price_bdt=float(raw_price) if raw_price else None,
                    price_basis=(row.get("price_basis") or "").strip(),
                    stock_quantity=int(raw_stock) if raw_stock else None,
                    specifications=(
                        row.get("specifications") or ""
                    ).strip(),
                    description=(
                        row.get("description") or ""
                    ).strip(),
                )
            )

    return products


PRODUCTS = load_products()


@app.get("/")
def home():
    return {
        "message": "Welcome to ShopPilot API!",
        "docs": "/docs",
    }


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "product_count": len(PRODUCTS),
    }


@app.get("/products")
def get_products(
    q: str | None = Query(
        default=None,
        description="Search product names, brands, categories, and details",
    ),
    category: str | None = None,
    brand: str | None = None,
    min_price: float | None = Query(default=None, ge=0),
    max_price: float | None = Query(default=None, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    if (
        min_price is not None
        and max_price is not None
        and min_price > max_price
    ):
        raise HTTPException(
            status_code=400,
            detail="min_price cannot be greater than max_price.",
        )

    results = PRODUCTS

    # Search across product information
    if q and q.strip():
        words = q.strip().lower().split()

        def matches_search(product: Product) -> bool:
            searchable_text = " ".join(
                [
                    product.name,
                    product.category,
                    product.brand,
                    product.specifications,
                    product.description,
                ]
            ).lower()

            # Every search word must appear somewhere
            return all(word in searchable_text for word in words)

        results = [
            product for product in results
            if matches_search(product)
        ]

    # Filter by category
    if category and category.strip():
        results = [
            product for product in results
            if category.strip().lower() in product.category.lower()
        ]

    # Filter by brand
    if brand and brand.strip():
        results = [
            product for product in results
            if brand.strip().lower() in product.brand.lower()
        ]

    # Filter by minimum price
    if min_price is not None:
        results = [
            product for product in results
            if product.price_bdt is not None
            and product.price_bdt >= min_price
        ]

    # Filter by maximum price
    if max_price is not None:
        results = [
            product for product in results
            if product.price_bdt is not None
            and product.price_bdt <= max_price
        ]

    total = len(results)
    paginated_results = results[offset:offset + limit]

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "products": paginated_results,
    }


@app.get("/products/{product_id}")
def get_product(product_id: str):
    for product in PRODUCTS:
        if product.product_id == product_id:
            return product

    raise HTTPException(
        status_code=404,
        detail=f"Product '{product_id}' not found.",
    )
