/**
 * Centralized API service for communicating with the FastAPI backend.
 * Base URL is configurable via VITE_API_BASE_URL (defaults to /api, proxied by Vite).
 */

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api';

/** Anonymous, browser-local reader id used for bookmarks, history and "For You". No login, no PII. */
function getClientId() {
  const KEY = 'nexus_reader_id';
  try {
    let id = localStorage.getItem(KEY);
    if (!id) {
      id = (crypto.randomUUID ? crypto.randomUUID() : `r${Date.now()}${Math.random().toString(16).slice(2)}`).replace(/[^A-Za-z0-9_-]/g, '');
      localStorage.setItem(KEY, id);
    }
    return id;
  } catch {
    return 'session-reader-0000';
  }
}

export const clientId = getClientId();

async function request(endpoint, options = {}) {
  const url = `${API_BASE_URL}${endpoint}`;
  try {
    const res = await fetch(url, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        'X-Client-Id': clientId,
        ...(options.headers || {}),
      },
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
      const err = new Error(errorDetail);
      err.status = res.status;
      throw err;
    }

    return await res.json();
  } catch (err) {
    console.error(`API Error on ${endpoint}:`, err);
    throw err;
  }
}

export const apiService = {
  // ------------------------------------------------------------------ news
  async getNewsFeed({ page = 1, pageSize = 12, category, source, status, clusterId, sentiment } = {}) {
    const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
    if (category && category !== 'All') params.append('category', category);
    if (source) params.append('source', source);
    if (status) params.append('status', status);
    if (clusterId) params.append('cluster_id', clusterId);
    if (sentiment) params.append('sentiment', sentiment);
    return request(`/news?${params.toString()}`);
  },
  async getArticle(id) {
    return request(`/news/${encodeURIComponent(id)}`);
  },
  async generateSummary(id) {
    return request(`/news/${encodeURIComponent(id)}/summarize`, { method: 'POST' });
  },
  async getRelatedNews(id, { topK = 5 } = {}) {
    return request(`/news/${encodeURIComponent(id)}/related?top_k=${topK}`);
  },
  async getPerspectives(id) {
    return request(`/news/${encodeURIComponent(id)}/perspectives`);
  },
  async getTimeline(id) {
    return request(`/news/${encodeURIComponent(id)}/timeline`);
  },
  async translate(id, lang) {
    return request(`/news/${encodeURIComponent(id)}/translate?lang=${encodeURIComponent(lang)}`);
  },
  async getLanguages() {
    return request('/news/meta/languages');
  },
  async getCategories() {
    return request('/categories');
  },
  async searchNews(query, { page = 1, pageSize = 12, category } = {}) {
    const params = new URLSearchParams({ q: query.trim(), page: String(page), page_size: String(pageSize) });
    if (category && category !== 'All') params.append('category', category);
    return request(`/search?${params.toString()}`);
  },
  async semanticSearch(query, { topK = 10, category } = {}) {
    const params = new URLSearchParams({ q: query.trim(), top_k: String(topK) });
    if (category && category !== 'All') params.append('category', category);
    return request(`/search/semantic?${params.toString()}`);
  },
  async getTrending(limit = 8, category) {
    const params = new URLSearchParams({ limit: String(limit) });
    if (category && category !== 'All') params.append('category', category);
    return request(`/trending?${params.toString()}`);
  },
  async getBriefing({ category, refresh = false } = {}) {
    const params = new URLSearchParams();
    if (category) params.append('category', category);
    if (refresh) params.append('refresh', 'true');
    return request(`/briefing?${params.toString()}`);
  },

  // ------------------------------------------------------------------ AI chat
  async askChatbot(question, topK = 4, history = []) {
    return request('/chat/ask', {
      method: 'POST',
      body: JSON.stringify({ question: question.trim(), top_k: topK, history }),
    });
  },
  async explainArticle(id) {
    return request(`/chat/explain/${encodeURIComponent(id)}`);
  },

  // ------------------------------------------------------------------ personal
  async getBookmarkIds() {
    return request('/me/bookmarks/ids');
  },
  async getBookmarks() {
    return request('/me/bookmarks');
  },
  async addBookmark(id) {
    return request(`/me/bookmarks/${encodeURIComponent(id)}`, { method: 'PUT' });
  },
  async removeBookmark(id) {
    return request(`/me/bookmarks/${encodeURIComponent(id)}`, { method: 'DELETE' });
  },
  async recordEvent(articleId, eventType = 'view') {
    return request('/me/events', {
      method: 'POST',
      body: JSON.stringify({ article_id: articleId, event_type: eventType }),
    }).catch(() => null); // history is best-effort
  },
  async getHistory(limit = 20) {
    return request(`/me/history?limit=${limit}`);
  },
  async getForYou(limit = 12) {
    return request(`/me/for-you?limit=${limit}`);
  },
  async forgetMe() {
    return request('/me', { method: 'DELETE' });
  },

  // ------------------------------------------------------------------ insights & monitoring
  async getInsights(hours = 48) {
    return request(`/insights/overview?hours=${hours}`);
  },
  async getTopics(hours = 24) {
    return request(`/insights/topics?hours=${hours}`);
  },
  async getMonitoring() {
    return request('/monitoring/overview');
  },
  async getHealth() {
    return request('/health');
  },

  /** Subscribe to real-time server-sent events. Returns an unsubscribe function. */
  subscribeEvents(handlers = {}) {
    if (typeof EventSource === 'undefined') return () => {};
    const es = new EventSource(`${API_BASE_URL}/stream/events`);
    ['hello', 'new_articles', 'summaries_ready'].forEach((evt) => {
      es.addEventListener(evt, (e) => {
        try {
          handlers[evt]?.(JSON.parse(e.data));
        } catch {
          /* ignore malformed event */
        }
      });
    });
    es.onopen = () => handlers.open?.();
    es.onerror = () => handlers.error?.();
    return () => es.close();
  },
};

export default apiService;
