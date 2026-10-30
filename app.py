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


# ---------------------------------------------------------------------------
# Bangla / English understanding helpers used by /chat
# ---------------------------------------------------------------------------

BENGALI_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")

# Each concept lists words a customer might type (English and Bangla).
# The English (ASCII) words are also used to match the product's
# category and name in your catalog. Add more words for your own catalog.
CATEGORY_TERMS = {
    "headset": [
        "headset", "headphone", "earphone", "earbud",
        "হেডসেট", "হেডফোন", "হেড ফোন", "ইয়ারফোন", "ইয়ারবাড",
    ],
    "keyboard": [
        "keyboard",
        "কীবোর্ড", "কিবোর্ড", "কি-বোর্ড", "কি বোর্ড",
    ],
    "mouse": ["mouse", "mice", "মাউস"],
    "laptop": ["laptop", "notebook", "ল্যাপটপ"],
    "monitor": ["monitor", "মনিটর"],
    "router": ["router", "রাউটার"],
    "webcam": ["webcam", "ওয়েবক্যাম", "ওয়েব ক্যাম"],
    "speaker": ["speaker", "স্পিকার"],
    "printer": ["printer", "প্রিন্টার"],
    "charger": ["charger", "চার্জার"],
    "pendrive": ["pendrive", "pen drive", "পেনড্রাইভ", "পেন ড্রাইভ"],
}

STOP_WORDS = {
    "the", "and", "for", "with", "best", "good", "great", "nice",
    "budget", "suggest", "recommend", "please", "need", "want",
    "under", "within", "below", "tk", "taka", "bdt", "me", "my",
    "can", "you", "any", "some", "buy", "show",
}


def parse_budget(message: str) -> float | None:
    """Find a budget like 3000, ৩০০০, 3,000, 3k or ৩ হাজার."""
    text = message.translate(BENGALI_DIGITS).replace(",", "").lower()

    thousands = re.search(
        r"(\d+(?:\.\d+)?)\s*(?:k\b|thousand|হাজার)", text
    )
    if thousands:
        return float(thousands.group(1)) * 1000

    for number in re.findall(r"\d+(?:\.\d+)?", text):
        value = float(number)
        if value >= 100:
            return value

    return None


def detect_categories(message: str) -> list[str]:
    """Return product types the customer asked for (English or Bangla)."""
    text = message.lower()
    found = []

    for concept, terms in CATEGORY_TERMS.items():
        for term in terms:
            if term.isascii():
                hit = re.search(rf"\b{re.escape(term)}", text)
            else:
                hit = term in text

            if hit:
                found.append(concept)
                break

    return found


def product_in_category(product: Product, concept: str) -> bool:
    terms = [t for t in CATEGORY_TERMS[concept] if t.isascii()]
    text = f"{product.category} {product.name}".lower()
    return any(term in text for term in terms)


def detect_brands(message: str) -> list[str]:
    """Return catalog brands mentioned in the message (English names)."""
    text = message.lower()
    brands = {p.brand.lower() for p in PRODUCTS if p.brand}

    return [
        brand for brand in brands
        if re.search(rf"\b{re.escape(brand)}\b", text)
    ]


def build_fallback_reply(
    message: str, products: list[Product], budget: float | None
) -> str:
    """Plain reply used when the AI service is unavailable."""
    is_bangla = bool(re.search(r"[\u0980-\u09FF]", message))

    if not products:
        return (
            "দুঃখিত, আপনার অনুরোধ অনুযায়ী কোনো পণ্য খুঁজে পাইনি। অন্যভাবে লিখে চেষ্টা করুন।"
            if is_bangla
            else "Sorry, I couldn't find matching products. Please try rephrasing."
        )

    in_budget = budget is not None and any(
        p.price_bdt is not None and p.price_bdt <= budget
        for p in products
    )

    if is_bangla:
        text = "আপনার জন্য কিছু পণ্য নিচে দেওয়া হলো।"

        if budget is not None:
            text += (
                f" এগুলো ৳{budget:,.0f} বাজেটের মধ্যে।"
                if in_budget
                else f" ৳{budget:,.0f} বাজেটের মধ্যে কোনো পণ্য পাইনি, তাই কাছাকাছি পণ্য দেখানো হলো।"
            )

        return text + " দাম ও স্টক কেনার আগে দোকান থেকে নিশ্চিত করে নিন।"

    text = "Here are some products that match your request."

    if budget is not None:
        text += (
            f" These are within your budget of BDT {budget:,.0f}."
            if in_budget
            else f" Nothing matched BDT {budget:,.0f} exactly, so these are the closest options."
        )

    return text + " Please confirm prices and stock with the shop before buying."


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

    # 1. Understand the request (works for English and Bangla).
    budget = parse_budget(message)
    categories = detect_categories(message)
    brands = detect_brands(message)

    # English words only; numbers and filler words are ignored.
    words = [
        word.lower()
        for word in re.findall(
            r"[a-zA-Z0-9]+", message.translate(BENGALI_DIGITS)
        )
        if len(word) > 1
        and not word.isdigit()
        and word.lower() not in STOP_WORDS
    ]

    # 2. Narrow the catalog by product type, then by budget.
    pool = PRODUCTS

    if categories:
        pool = [
            p for p in PRODUCTS
            if any(product_in_category(p, c) for c in categories)
        ]

    brand_note = ""
    brand_matched = False

    if brands:
        brand_pool = [p for p in pool if p.brand.lower() in brands]

        if brand_pool:
            pool = brand_pool
            brand_matched = True
        else:
            brand_note = (
                "No matching product from the requested brand "
                "was found; other brands are shown."
            )

    # A detected type or brand means we trust the filter, so keep
    # everything that passed it instead of requiring keyword matches.
    has_filter = bool(categories or brand_matched)

    budget_note = ""

    if budget is not None and pool:
        within_budget = [
            p for p in pool
            if p.price_bdt is not None and p.price_bdt <= budget
        ]

        if within_budget:
            pool = within_budget
            budget_note = (
                f"Only products with a listed price up to "
                f"BDT {budget:,.0f} are included."
            )
        else:
            budget_note = (
                f"No matching product has a listed price within "
                f"BDT {budget:,.0f}. The closest options are shown."
            )

    # 3. Rank what is left.
    scored = []

    for product in pool:
        searchable = " ".join([
            product.name,
            product.brand,
            product.category,
            product.specifications,
            product.description,
        ]).lower()

        score = sum(1 for word in words if word in searchable)
        scored.append((score, product))

    # With no type or brand detected, require at least one keyword match.
    if not has_filter:
        scored = [(s, p) for s, p in scored if s > 0]

    scored.sort(
        key=lambda item: (
            -item[0],
            item[1].price_bdt
            if item[1].price_bdt is not None
            else float("inf"),
        )
    )

    relevant_products = [product for _, product in scored[:8]]

    # Only fall back to a sample when we couldn't tell what was asked.
    if not relevant_products and not has_filter:
        relevant_products = pool[:5]

    category_note = ""

    if categories and not relevant_products:
        category_note = (
            "The catalog has no products matching: "
            + ", ".join(categories)
            + "."
        )

    def match_reason(product: Product) -> str:
        parts = []

        if categories:
            parts.append("Matches the product type you asked for")
        elif brand_matched:
            parts.append("Matches the brand you asked for")
        else:
            parts.append("Matches your search keywords")

        if (
            budget is not None
            and product.price_bdt is not None
            and product.price_bdt <= budget
        ):
            parts.append("listed price is within your budget")

        return "; ".join(parts)

    def product_cards(products: list[Product]) -> list[dict]:
        return [
            {**p.model_dump(), "match_reason": match_reason(p)}
            for p in products[:5]
        ]

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
            "products": product_cards(relevant_products),
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
- If the context is empty or does not contain enough information, say so.
- Do not claim you have placed an order or contacted the shop.
- The customer may write in English or Bangla. Respond in the language
  that best matches their message.
"""

    notes = " ".join(
        n for n in [budget_note, category_note, brand_note] if n
    )

    try:
        completion = ai_client.chat.completions.create(
            model=HF_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": (
                        f"Catalog context:\n{context}\n\n"
                        f"Search notes: {notes or 'None'}\n\n"
                        f"Customer message:\n{message}"
                    ),
                },
            ],
            # Reasoning models spend part of this on thinking,
            # so a small limit can leave the visible answer empty.
            max_tokens=800,
        )

        answer = completion.choices[0].message.content

        if not answer:
            answer = (
                "I couldn't generate a response just now. "
                "Please try asking another way."
            )

        return {
            "reply": answer,
            "products": product_cards(relevant_products),
        }

    except Exception as exc:
        # Log details in the backend terminal, not in the customer response.
        print(f"Hosted AI request failed: {type(exc).__name__}: {exc}")

        return {
            "reply": build_fallback_reply(
                message, relevant_products, budget
            ),
            "products": product_cards(relevant_products),
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