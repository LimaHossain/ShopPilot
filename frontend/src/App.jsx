import ProductCard from "./ProductCard";
import { useState, useEffect, useRef } from "react";
import "./App.css";

const API_URL = "http://127.0.0.1:8000";

const SUGGESTIONS = [
  "Best headset under 3000 taka",
  "আমার বাজেট ৫০০০ টাকা, একটি মাউস দিন",
  "Gaming keyboard suggestions",
];

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
  const bottomRef = useRef(null);

  // Scroll to the newest message whenever the chat changes.
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  async function sendMessage(eventOrMessage) {
    // Supports form submissions, suggestion chips and product-card questions.
    if (typeof eventOrMessage !== "string") {
      eventOrMessage?.preventDefault();
    }

    const message =
      typeof eventOrMessage === "string"
        ? eventOrMessage.trim()
        : input.trim();

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
          text: data.reply || "I couldn't generate a response.",
          products: data.products || [],
        },
      ]);
    } catch (error) {
      console.error("Chat request failed:", error);

      setMessages((previous) => [
        ...previous,
        {
          role: "bot",
          text: "I couldn't connect to ShopPilot. Please check that the backend is running and try again.",
          products: [],
        },
      ]);
    } finally {
      setLoading(false);
    }
  }

  function handleAskProduct(product) {
    const question = `Tell me more about ${product.name} (Product ID: ${product.product_id}). Explain its specifications and listed price, and tell me what I should confirm with the shop.`;

    sendMessage(question);
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

                {message.products && message.products.length > 0 && (
                  <div className="product-list">
                    {message.products.map((product) => (
                      <ProductCard
                        key={product.product_id}
                        product={product}
                        onAskProduct={handleAskProduct}
                        disabled={loading}
                      />
                    ))}

                    <p className="disclaimer">
                      Prices and stock should be confirmed with the shop.
                    </p>
                  </div>
                )}
              </div>
            </div>
          ))}

          {messages.length === 1 && (
            <div className="suggestions">
              {SUGGESTIONS.map((text) => (
                <button
                  key={text}
                  type="button"
                  disabled={loading}
                  onClick={() => sendMessage(text)}
                >
                  {text}
                </button>
              ))}
            </div>
          )}

          {loading && (
            <div className="message-row bot">
              <div className="bubble typing">
                Searching the catalog...
              </div>
            </div>
          )}

          <div ref={bottomRef} />
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
