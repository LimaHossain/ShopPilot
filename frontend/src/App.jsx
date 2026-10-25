
import { useState } from "react";
import "./App.css";

const API_URL = "http://127.0.0.1:8000";

function App() {
  const [messages, setMessages] = useState([
    {
      role: "bot",
      text: "Welcome to ShopPilot! 👋 Tell me what IT product you're looking for, and I'll help you find a match.",
      products: [],
    },
  ]);

  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);

  async function sendMessage(event) {
    event.preventDefault();

    const message = input.trim();
    if (!message || loading) return;

    setMessages((previous) => [
      ...previous,
      { role: "user", text: message, products: [] },
    ]);
    setInput("");
    setLoading(true);

    try {
      const response = await fetch(`${API_URL}/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ message }),
      });

      if (!response.ok) {
        throw new Error(`Server returned ${response.status}`);
      }

      const data = await response.json();

      setMessages((previous) => [
        ...previous,
        {
          role: "bot",
          text: data.reply,
          products: data.products || [],
        },
      ]);
    } catch (error) {
      setMessages((previous) => [
        ...previous,
        {
          role: "bot",
          text: "I couldn't connect to ShopPilot. Please check that the backend is running and try again.",
          products: [],
        },
      ]);
      console.error("Chat request failed:", error);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="page">
      <section className="chat-app">
        <header className="chat-header">
          <div className="brand-icon">S</div>
          <div>
            <h1>ShopPilot</h1>
            <p>IT Shopping Assistant</p>
          </div>
          <span className="status">
            <span className="status-dot" />
            Online
          </span>
        </header>

        <div className="chat-messages">
          {messages.map((message, index) => (
            <div
              className={`message-row ${message.role}`}
              key={index}
            >
              <div className="message-content">
                <div className="bubble">{message.text}</div>

                {message.products.length > 0 && (
                  <div className="product-list">
                    {message.products.map((product) => (
                      <article
                        className="product-card"
                        key={product.product_id}
                      >
                        <div className="product-top">
                          <span className="product-brand">
                            {product.brand || "IT Product"}
                          </span>
                          <span className="product-category">
                            {product.category}
                          </span>
                        </div>

                        <h3>{product.name}</h3>

                        <p className="product-description">
                          {product.specifications ||
                            product.description ||
                            "Product details are not available."}
                        </p>

                        <div className="product-bottom">
                          <strong>
                            {product.price_bdt != null
                              ? `৳${Number(
                                  product.price_bdt
                                ).toLocaleString("en-BD")}`
                              : "Price unavailable"}
                          </strong>
                          <span className="price-note">
                            {product.price_basis || "Price to confirm"}
                          </span>
                        </div>

                        <p className="match-reason">
                          {product.match_reason}
                        </p>
                      </article>
                    ))}
                    <p className="disclaimer">
                      Prices and stock should be confirmed with the shop.
                    </p>
                  </div>
                )}
              </div>
            </div>
          ))}

          {loading && (
            <div className="message-row bot">
              <div className="bubble typing">
                Searching the catalog...
              </div>
            </div>
          )}
        </div>

        <form className="chat-form" onSubmit={sendMessage}>
          <input
            value={input}
            onChange={(event) => setInput(event.target.value)}
            placeholder="Ask about a product or budget..."
            aria-label="Your message"
            maxLength={500}
            disabled={loading}
          />
          <button
            type="submit"
            disabled={loading || !input.trim()}
          >
            {loading ? "..." : "Send"}
          </button>
        </form>

        <footer className="chat-footer">
          ShopPilot · Your IT shopping assistant
        </footer>
      </section>
    </main>
  );
}

export default App;
