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
      text: 'Welcome to the News AI Assistant! I answer questions strictly based on verified news articles stored in PostgreSQL. Ask me about recent headlines, technological advancements, or global events.',
      sources: [],
    },
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);

  const sendMessage = async (questionText) => {
    const query = (questionText || input).trim();
    if (!query || loading) return;

    setMessages((prev) => [...prev, { role: 'user', text: query }]);
    if (!questionText) setInput('');
    setLoading(true);

    try {
      const data = await apiService.askChatbot(query, 4);
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
        <h2 className="section-heading">News AI Retrieval Assistant</h2>
        <p className="section-subheading">
          Answers grounded strictly in collected news facts using FAISS semantic search and Groq LLM synthesis.
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
                  <div className="sources-title">Referenced News Sources:</div>
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
              <span>Retrieving relevant news context and synthesizing response...</span>
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
            {loading ? 'Thinking...' : 'Ask Assistant'}
          </button>
        </form>
      </div>
    </section>
  );
}

export default ChatbotPanel;
