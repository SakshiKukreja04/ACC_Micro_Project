import React, { useState } from 'react';
import apiService from '../services/api';

const QUICK_PROMPTS = [
  'What is the latest with AI regulation and guidelines?',
  'What are the recent tech and cybersecurity updates?',
  'Summarize recent business and economic news.',
  'What are the main international news stories today?',
];

export function ChatbotPanel() {
  const [messages, setMessages] = useState([
    {
      role: 'assistant',
      text: 'Ask about anything in the collected news. I answer only from those articles and cite them, and you can ask follow-up questions.',
      sources: [],
    },
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);

  const sendMessage = async (questionText) => {
    const query = (questionText || input).trim();
    if (!query || loading) return;

    // Previous turns (excluding the welcome message) give the model context for follow-ups
    const history = messages.slice(1).map((m) => ({ role: m.role, content: m.text })).slice(-6);
    setMessages((prev) => [...prev, { role: 'user', text: query }]);
    if (!questionText) setInput('');
    setLoading(true);

    try {
      const data = await apiService.askChatbot(query, 4, history);
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          text: data.answer,
          sources: data.sources || [],
        },
      ]);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          text: `Unable to retrieve an answer: ${err.message || 'Server connection error'}. Please try again shortly.`,
          sources: [],
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    sendMessage();
  };

  return (
    <section className="chatbot-wrapper" aria-label="News AI Assistant">
      <div className="chatbot-header">
        <h2 className="section-heading">Ask the news</h2>
        <p className="section-subheading">
          Answers come only from collected articles, found by meaning with FAISS and written by the Groq LLM, with numbered sources.
        </p>
      </div>

      <div className="chat-container">
        {/* Quick Suggestion Pills */}
        <div className="quick-prompts-bar">
          <span className="quick-label">Try asking:</span>
          {QUICK_PROMPTS.map((prompt, idx) => (
            <button
              key={idx}
              className="quick-pill-btn"
              onClick={() => sendMessage(prompt)}
              disabled={loading}
            >
              {prompt}
            </button>
          ))}
        </div>

        {/* Message Thread */}
        <div className="chat-messages" role="log" aria-live="polite">
          {messages.map((msg, i) => (
            <div
              key={i}
              className={`chat-bubble ${msg.role === 'user' ? 'chat-user' : 'chat-assistant'}`}
            >
              <div className="chat-text">{msg.text}</div>

              {Array.isArray(msg.sources) && msg.sources.length > 0 && (
                <div className="chat-sources">
                  <div className="sources-title">Sources</div>
                  <ul className="sources-list">
                    {msg.sources.map((s, idx) => (
                      <li key={idx}>
                        [{idx + 1}] <a href={s.canonical_url} target="_blank" rel="noopener noreferrer">
                          {s.title}
                        </a> <span className="source-meta">({s.source_name})</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          ))}

          {loading && (
            <div className="chat-bubble chat-assistant chat-loading">
              <span className="spinner-dot"></span>
              <span>Reading the most relevant articles…</span>
            </div>
          )}
        </div>

        {/* Chat Input Bar */}
        <form onSubmit={handleSubmit} className="chat-input-bar">
          <input
            type="text"
            className="chat-input"
            placeholder="Ask a question about the latest news stories..."
            value={input}
            onChange={(e) => setInput(e.target.value)}
            disabled={loading}
            aria-label="Ask the news chatbot"
          />
          <button type="submit" className="btn-primary" disabled={loading || !input.trim()}>
            {loading ? 'Reading…' : 'Ask'}
          </button>
        </form>
      </div>
    </section>
  );
}

export default ChatbotPanel;
