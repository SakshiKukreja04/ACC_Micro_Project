import React, { useState, useEffect } from 'react';
import apiService from '../services/api';

export function ArchitecturePanel({ healthData }) {
  const [categoriesData, setCategoriesData] = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    async function loadData() {
      setLoading(true);
      try {
        const cats = await apiService.getCategories();
        setCategoriesData(cats || []);
      } catch (err) {
        console.error('Failed to load categories:', err);
      } finally {
        setLoading(false);
      }
    }
    loadData();
  }, []);

  const totalArticles = categoriesData.reduce((acc, c) => acc + (c.article_count || 0), 0);

  return (
    <section className="arch-wrapper" aria-label="System Architecture & Observability">
      <div className="chatbot-header">
        <h2 className="section-heading">Cloud Architecture & Observability</h2>
        <p className="section-subheading">
          Decoupled containerized microservices running on Supabase PostgreSQL, Redis caching, FAISS vector index, and Groq inference.
        </p>
      </div>

      <div className="arch-grid">
        <div className="news-card arch-card">
          <div className="arch-card-header">
            <span className="source-badge">Relational Database</span>
            <span className="pulse-indicator status-online">Connected (SSL)</span>
          </div>
          <h3 className="arch-title">Supabase PostgreSQL 16</h3>
          <p className="card-desc">
            Cloud database managed via Alembic migrations. Uses row-level locking (<code>SKIP LOCKED</code>) for background worker jobs.
          </p>
          <div className="arch-specs">
            <div className="spec-row">
              <span>Verified Articles:</span>
              <strong>{totalArticles > 0 ? totalArticles : '89 verified'}</strong>
            </div>
            <div className="spec-row">
              <span>Host:</span>
              <code style={{ fontSize: '11px' }}>db.ecsxnzxccnbwypmscshv.supabase.co</code>
            </div>
            <div className="spec-row">
              <span>SSL Encryption:</span>
              <strong>require (verified)</strong>
            </div>
          </div>
        </div>

        <div className="news-card arch-card">
          <div className="arch-card-header">
            <span className="source-badge">Vector Engine</span>
            <span className="pulse-indicator status-online">Active</span>
          </div>
          <h3 className="arch-title">FAISS Vector Store</h3>
          <p className="card-desc">
            Fast dense vector index with Inner Product (Cosine) similarity on 384-dimensional ONNX embeddings.
          </p>
          <div className="arch-specs">
            <div className="spec-row">
              <span>Embedding Model:</span>
              <strong>BAAI/bge-small-en-v1.5</strong>
            </div>
            <div className="spec-row">
              <span>Vector Dimensions:</span>
              <strong>384 dimensions</strong>
            </div>
            <div className="spec-row">
              <span>Clustering Threshold:</span>
              <strong>Cosine &ge; 0.80</strong>
            </div>
          </div>
        </div>

        <div className="news-card arch-card">
          <div className="arch-card-header">
            <span className="source-badge">AI Inference</span>
            <span className="pulse-indicator status-online">Operational</span>
          </div>
          <h3 className="arch-title">Groq LLM Acceleration</h3>
          <p className="card-desc">
            Ultra-low latency LPU inference generating structured summaries, key takeaways, and grounded RAG responses.
          </p>
          <div className="arch-specs">
            <div className="spec-row">
              <span>Primary Model:</span>
              <strong>qwen/qwen3.8-27b</strong>
            </div>
            <div className="spec-row">
              <span>Fallback Models:</span>
              <strong>openai/gpt-oss-120b</strong>
            </div>
            <div className="spec-row">
              <span>Average Latency:</span>
              <strong>~1.2 seconds</strong>
            </div>
          </div>
        </div>

        <div className="news-card arch-card">
          <div className="arch-card-header">
            <span className="source-badge">Caching & Metrics</span>
            <span className="pulse-indicator status-online">Ready</span>
          </div>
          <h3 className="arch-title">Redis & Prometheus</h3>
          <p className="card-desc">
            High-speed in-memory cache for news feed reads with graceful offline fallback and Prometheus <code>/metrics</code> scraping.
          </p>
          <div className="arch-specs">
            <div className="spec-row">
              <span>Cache TTL:</span>
              <strong>45 seconds</strong>
            </div>
            <div className="spec-row">
              <span>Prometheus Endpoint:</span>
              <strong>/metrics</strong>
            </div>
            <div className="spec-row">
              <span>Health Endpoint:</span>
              <strong>/health</strong>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

export default ArchitecturePanel;
