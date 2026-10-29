from pathlib import Path
import csv

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

import re
from fastapi.middleware.cors import CORSMiddleware

import os
from dotenv import load_dotenv
from openai import OpenAI

BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = BASE_DIR / ".env"

load_dotenv(dotenv_path=ENV_FILE, override=True)

HF_TOKEN = os.getenv("HF_TOKEN")
HF_MODEL = os.getenv(
    "HF_MODEL",
    "openai/gpt-oss-120b:fastest",
)


ai_client = None

if HF_TOKEN and HF_TOKEN.strip():
    ai_client = OpenAI(
        base_url="https://router.huggingface.co/v1",
        api_key=HF_TOKEN.strip(),
    )

print("ShopPilot configuration:")
print("App directory:", BASE_DIR)
print(".env file exists:", ENV_FILE.is_file())
print("HF_TOKEN loaded:", bool(HF_TOKEN and HF_TOKEN.strip()))
print("HF_MODEL:", HF_MODEL)
print("AI client initialized:", ai_client is not None)


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

    # Keep the product catalog as the source of product facts.
    # Limit context size to keep requests small.
    catalog_context = []

    for product in PRODUCTS:
        catalog_context.append({
            "product_id": product.product_id,
            "name": product.name,
            "brand": product.brand,
            "category": product.category,
            "price_bdt": product.price_bdt,
            "price_basis": product.price_basis,
            "specifications": product.specifications,
            "description": product.description,
        })

    # First use the existing search to find relevant products.
    words = [
        word.lower()
        for word in re.findall(r"[a-zA-Z0-9]+", message)
        if len(word) > 1
    ]

    ranked = []

    for product in PRODUCTS:
        searchable = " ".join([
            product.name,
            product.brand,
            product.category,
            product.specifications,
            product.description,
        ]).lower()

        score = sum(1 for word in words if word in searchable)

        if score:
            ranked.append((score, product))

    ranked.sort(
        key=lambda item: (
            -item[0],
            item[1].price_bdt
            if item[1].price_bdt is not None
            else float("inf"),
        )
    )

    relevant_products = [product for _, product in ranked[:8]]

    # If search doesn't identify products, provide a small catalog sample.
    if not relevant_products:
        relevant_products = PRODUCTS[:5]

    context = [
        {
            "product_id": p.product_id,
            "name": p.name,
            "brand": p.brand,
            "category": p.category,
            "price_bdt": p.price_bdt,
            "price_basis": p.price_basis,
            "specifications": p.specifications,
            "description": p.description,
        }
        for p in relevant_products
    ]

    # Keep the chatbot useful if no API token is configured.
    if ai_client is None:
        return {
            "reply": (
                "The AI model is not configured yet. "
                "Please check the HF_TOKEN setting in your .env file."
            ),
            "products": [
                {
                    **p.model_dump(),
                    "match_reason": "Matched your search keywords",
                }
                for p in relevant_products[:5]
            ],
        }

    system_prompt = """
You are ShopPilot, a helpful shopping assistant for an IT products shop.

Rules:
- Answer the customer's question clearly and politely.
- Use only the supplied catalog context for product facts.
- Never invent prices, specifications, product availability, or discounts.
- Treat price_bdt as a listed price, not a guaranteed current selling price.
- If stock is unknown, say the shop must confirm availability.
- Recommend products from the supplied context when relevant.
- If the context does not contain enough information, say so.
- Do not claim you have placed an order or contacted the shop.
- The customer may write in English or Bangla. Respond in the language
  that best matches their message.
"""

    try:
        completion = ai_client.chat.completions.create(
            model=HF_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": (
                        f"Catalog context:\n{context}\n\n"
                        f"Customer message:\n{message}"
                    ),
                },
            ],
            max_tokens=350,
        )

        answer = completion.choices[0].message.content

        if not answer:
            answer = (
                "I couldn't generate a response just now. "
                "Please try asking another way."
            )

        return {
            "reply": answer,
            "products": [
                {
                    **p.model_dump(),
                    "match_reason": "Selected as relevant catalog context",
                }
                for p in relevant_products[:5]
            ],
        }

    except Exception as exc:
        # Log details in the backend terminal, not in the customer response.
        print(f"Hosted AI request failed: {type(exc).__name__}: {exc}")

        return {
            "reply": (
                "I'm having trouble reaching the AI service right now. "
                "Please try again shortly. You can still browse the "
                "product catalog."
            ),
            "products": [
                {
                    **p.model_dump(),
                    "match_reason": "Catalog fallback result",
                }
                for p in relevant_products[:5]
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
