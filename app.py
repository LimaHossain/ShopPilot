from pathlib import Path
import csv

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

import re
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="ShopPilot API",
    description="Product catalog and search API for a local IT shop",
    version="0.3.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
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


@app.get("/recommend")
def recommend_products(
    q: str = Query(
        ...,
        min_length=1,
        description="What product does the customer want?",
    ),
    max_budget: float | None = Query(default=None, ge=0),
    brand: str | None = None,
    limit: int = Query(default=5, ge=1, le=20),
):
    # Split the customer's request into search terms
    keywords = q.lower().split()

    candidates = []

    for product in PRODUCTS:
        # Apply the budget filter
        if max_budget is not None:
            if product.price_bdt is None:
                continue
            if product.price_bdt > max_budget:
                continue

        # Apply the optional brand filter
        if brand and brand.lower() not in product.brand.lower():
            continue

        # Search across the available product information
        searchable_text = " ".join([
            product.name,
            product.category,
            product.brand,
            product.specifications,
            product.description,
        ]).lower()

        matched_keywords = [
            word for word in keywords
            if word in searchable_text
        ]

        # Ignore products that match none of the search terms
        if not matched_keywords:
            continue

        score = len(matched_keywords)

        candidates.append({
            "product": product,
            "score": score,
            "matched_keywords": matched_keywords,
        })

    # Prioritize products matching more keywords.
    # For equal scores, show lower listed prices first.
    candidates.sort(
        key=lambda item: (
            -item["score"],
            item["product"].price_bdt
            if item["product"].price_bdt is not None
            else float("inf"),
        )
    )

    recommendations = []

    for item in candidates[:limit]:
        product = item["product"]

        explanation = (
            "Matches your search for: "
            + ", ".join(item["matched_keywords"])
        )

        if max_budget is not None:
            explanation += (
                f". Listed price is within your "
                f"budget of BDT {max_budget:,.0f}"
            )

        recommendations.append({
            "product": product,
            "match_score": item["score"],
            "reason": explanation,
        })

    return {
        "query": q,
        "budget_bdt": max_budget,
        "total_matches": len(candidates),
        "recommendations": recommendations,
        "notice": (
            "Listed prices may need confirmation. "
            "Stock availability is not verified."
        ),
    }


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=500)


@app.post("/chat")
def chat(request: ChatRequest):
    message = request.message.strip()
    text = message.lower()

    # Extract a budget from phrases such as:
    # "under 5000", "below ৳3,000", "less than 2000"
    budget_match = re.search(
        r"(?:under|below|within|less than|max(?:imum)?(?: budget)?)"
        r"\s*(?:৳|tk\.?\s*)?([\d,]+)",
        text,
    )

    budget = None
    if budget_match:
        budget = float(budget_match.group(1).replace(",", ""))

    # Identify common product-related keywords
    stop_words = {
        "i", "me", "my", "a", "an", "the", "to", "for", "of",
        "with", "and", "or", "please", "want", "need", "find",
        "show", "recommend", "recommendation", "looking", "buy",
        "get", "some", "good", "best", "price", "product",
        "products", "under", "below", "within", "less", "than",
        "maximum", "max", "budget", "tk", "taka", "bdt",
    }

    # Remove budget phrases before searching for product keywords
    search_text = re.sub(
        r"(?:under|below|within|less than|max(?:imum)?(?: budget)?)"
        r"\s*(?:৳|tk\.?\s*)?[\d,]+",
        " ",
        text,
    )
    search_text = re.sub(r"[৳,]", " ", search_text)

    keywords = [
        word for word in re.findall(r"[a-zA-Z0-9]+", search_text)
        if word not in stop_words and not word.isdigit()
    ]

    # Search the catalog and rank matches
    matches = []

    for product in PRODUCTS:
        if budget is not None:
            if product.price_bdt is None or product.price_bdt > budget:
                continue

        searchable = " ".join([
            product.name,
            product.category,
            product.brand,
            product.specifications,
            product.description,
        ]).lower()

        matched = [word for word in keywords if word in searchable]

        if matched:
            matches.append({
                "product": product,
                "score": len(matched),
                "matched": matched,
            })

    matches.sort(
        key=lambda item: (
            -item["score"],
            item["product"].price_bdt
            if item["product"].price_bdt is not None
            else float("inf"),
        )
    )

    top_matches = matches[:5]

    if top_matches:
        response_text = (
            f"I found {len(matches)} matching product(s) for your request. "
            "Here are the best keyword matches."
        )
        if budget is not None:
            response_text += f" I filtered for listed prices up to ৳{budget:,.0f}."
    elif budget is not None:
        response_text = (
            f"I couldn't find matching products within ৳{budget:,.0f}. "
            "Try a different product name or a higher budget."
        )
    else:
        response_text = (
            "I couldn't find a clear product match. Try asking for a "
            "keyboard, headset, mouse, or a brand such as Onikuma "
            "or Royal Kludge."
        )

    return {
        "reply": response_text,
        "products": [
            {
                **item["product"].model_dump(),
                "match_reason": (
                    "Matched keywords: " + ", ".join(item["matched"])
                ),
            }
            for item in top_matches
        ],
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
