/**
 * Centralized API service for communicating with the FastAPI backend.
 * Base URL is configurable via VITE_API_BASE_URL environment variable.
 */

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api';

async function request(endpoint, options = {}) {
  const url = `${API_BASE_URL}${endpoint}`;
  try {
    const res = await fetch(url, {
      headers: {
        'Content-Type': 'application/json',
        ...(options.headers || {}),
      },
      ...options,
    });

    if (!res.ok) {
      let errorDetail = `Request failed with status ${res.status}`;
      try {
        const errorData = await res.json();
        if (errorData.detail) {
          errorDetail = typeof errorData.detail === 'string' ? errorData.detail : JSON.stringify(errorData.detail);
        }
      } catch {
        // Fall back to status text
      }
      throw new Error(errorDetail);
    }

    return await res.json();
  } catch (err) {
    console.error(`API Error on ${endpoint}:`, err);
    throw err;
  }
}

export const apiService = {
  /**
   * Fetch paginated news feed with optional filters.
   */
  async getNewsFeed({ page = 1, pageSize = 12, category, source, status, clusterId } = {}) {
    const params = new URLSearchParams({
      page: String(page),
      page_size: String(pageSize),
    });
    if (category && category !== 'All') params.append('category', category);
    if (source) params.append('source', source);
    if (status) params.append('status', status);
    if (clusterId) params.append('cluster_id', clusterId);

    return request(`/news?${params.toString()}`);
  },

  /**
   * Fetch single article details by ID.
   */
  async getArticle(id) {
    return request(`/news/${encodeURIComponent(id)}`);
  },

  /**
   * Request on-demand AI summarization for an article.
   */
  async generateSummary(id) {
    return request(`/news/${encodeURIComponent(id)}/summarize`, {
      method: 'POST',
    });
  },

  /**
   * Fetch semantically related articles for an article ID.
   */
  async getRelatedNews(id, { topK = 5, minScore = 0.35 } = {}) {
    const params = new URLSearchParams({
      top_k: String(topK),
      min_score: String(minScore),
    });
    return request(`/news/${encodeURIComponent(id)}/related?${params.toString()}`);
  },

  /**
   * Fetch available categories with article counts.
   */
  async getCategories() {
    return request('/categories');
  },

  /**
   * Keyword search across title, description, and content.
   */
  async searchNews(query, { page = 1, pageSize = 12, category } = {}) {
    const params = new URLSearchParams({
      q: query.trim(),
      page: String(page),
      page_size: String(pageSize),
    });
    if (category && category !== 'All') params.append('category', category);
    return request(`/search?${params.toString()}`);
  },

  /**
   * FAISS semantic vector search by natural language concept.
   */
  async semanticSearch(query, { topK = 10, minScore = 0.35, category } = {}) {
    const params = new URLSearchParams({
      q: query.trim(),
      top_k: String(topK),
      min_score: String(minScore),
    });
    if (category && category !== 'All') params.append('category', category);
    return request(`/search/semantic?${params.toString()}`);
  },

  /**
   * Fetch trending articles ranked by prominence & recency.
   */
  async getTrending(limit = 8) {
    return request(`/trending?limit=${limit}`);
  },

  /**
   * Ask the news-grounded RAG chatbot a question.
   */
  async askChatbot(question, topK = 4) {
    return request('/chat/ask', {
      method: 'POST',
      body: JSON.stringify({ question: question.trim(), top_k: topK }),
    });
  },

  /**
   * Request plain-English educational context for a specific article.
   */
  async explainArticle(id) {
    return request(`/chat/explain/${encodeURIComponent(id)}`);
  },

  /**
   * Backend health check.
   */
  async getHealth() {
    return request('/health');
  },
};

export default apiService;
