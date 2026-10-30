import "./ProductCard.css";

function formatPrice(price) {
  if (price === null || price === undefined || price === "") {
    return "Price to be confirmed";
  }

  const numericPrice = Number(price);

  if (!Number.isFinite(numericPrice)) {
    return "Price to be confirmed";
  }

  return `৳${numericPrice.toLocaleString("en-BD")}`;
}

function ProductCard({ product, onAskProduct, disabled }) {
  const name = product.name || "Unnamed product";
  const brand = product.brand || "Brand not specified";
  const category = product.category || "General";
  const specifications = product.specifications || "";
  const description = product.description || "";
  const matchReason = product.match_reason || "";

  const hasPrice =
    product.price_bdt !== null &&
    product.price_bdt !== undefined &&
    product.price_bdt !== "";

  const priceBasis = (product.price_basis || "").toLowerCase();

  const priceNeedsConfirmation =
    !hasPrice ||
    priceBasis.includes("confirm") ||
    priceBasis.includes("cp");

  const stockIsUnknown =
    product.stock_quantity === null ||
    product.stock_quantity === undefined ||
    product.stock_quantity === "";

  return (
    <article className="product-card">
      <div className="product-card__visual">
        <span className="product-card__visual-icon" aria-hidden="true">
          {category.toLowerCase().includes("headphone") ||
          category.toLowerCase().includes("earbud")
            ? "🎧"
            : category.toLowerCase().includes("mouse")
              ? "🖱️"
              : category.toLowerCase().includes("keyboard")
                ? "⌨️"
                : "💻"}
        </span>

        <span className="product-card__category">{category}</span>
      </div>

      <div className="product-card__content">
        <div className="product-card__brand">{brand}</div>

        <h3 className="product-card__name">{name}</h3>

        {product.product_id && (
          <p className="product-card__id">
            Product ID: {product.product_id}
          </p>
        )}

        <div className="product-card__price">
          {formatPrice(product.price_bdt)}
        </div>

        {priceNeedsConfirmation && (
          <p className="product-card__notice">
            Listed price only — confirm the current selling price.
          </p>
        )}

        {specifications && (
          <div className="product-card__details">
            <h4>Specifications</h4>
            <p>{specifications}</p>
          </div>
        )}

        {description && (
          <p className="product-card__description">{description}</p>
        )}

        <div className="product-card__stock">
          <span className="product-card__stock-dot" />
          {stockIsUnknown
            ? "Availability needs confirmation"
            : `Recorded stock quantity: ${product.stock_quantity}`}
        </div>

        {matchReason && (
          <p className="product-card__match">
            <span aria-hidden="true">✦</span> {matchReason}
          </p>
        )}

        <button
        type="button"
        className="product-card__button"
        disabled={disabled}
        onClick={() => onAskProduct?.(product)}
        >
          Ask about this product
          <span aria-hidden="true"> →</span>
        </button>
      </div>
    </article>
  );
}

export default ProductCard;
