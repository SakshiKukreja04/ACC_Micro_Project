import React, { useEffect, useRef, useState } from 'react';
import apiService from '../services/api';
import { PerspectiveLens, StoryTimeline } from './PerspectiveLens';
import { BookmarkButton, GroundingBadge, ReadingTime, SentimentMark } from './ui';

const SPEECH_LANG = {
  hi: 'hi-IN', mr: 'mr-IN', ta: 'ta-IN', te: 'te-IN', bn: 'bn-IN', gu: 'gu-IN', kn: 'kn-IN', ml: 'ml-IN',
  pa: 'pa-IN', ur: 'ur-IN', es: 'es-ES', fr: 'fr-FR', de: 'de-DE', ar: 'ar-SA', ja: 'ja-JP', zh: 'zh-CN',
};

const TABS = [
  { id: 'lens', label: 'Other outlets' },
  { id: 'timeline', label: 'Timeline' },
  { id: 'related', label: 'Related' },
  { id: 'explain', label: 'Explain it simply' },
];

export function ArticleDetailModal({ article, onClose, onSelectRelated, onOpenArticleById, onGenerateSummary, isSaved, onToggleBookmark }) {
  const [relatedList, setRelatedList] = useState([]);
  const [loadingRelated, setLoadingRelated] = useState(false);
  const [explanation, setExplanation] = useState(null);
  const [loadingExplain, setLoadingExplain] = useState(false);
  const [isSummarizing, setIsSummarizing] = useState(false);
  const [tab, setTab] = useState('lens');
  const [languages, setLanguages] = useState([]);
  const [lang, setLang] = useState('');
  const [translation, setTranslation] = useState(null);
  const [translating, setTranslating] = useState(false);
  const [translateError, setTranslateError] = useState(null);
  const [speaking, setSpeaking] = useState(false);
  const closeRef = useRef(null);

  useEffect(() => {
    if (!article) return;
    setExplanation(null);
    setTranslation(null);
    setTranslateError(null);
    setLang('');
    setTab('lens');
    window.speechSynthesis?.cancel();
    setSpeaking(false);
    apiService.recordEvent(article.id, 'view');
    closeRef.current?.focus();

    let isMounted = true;
    setLoadingRelated(true);
    apiService
      .getRelatedNews(article.id, { topK: 4 })
      .then((data) => isMounted && setRelatedList(data || []))
      .catch(() => isMounted && setRelatedList([]))
      .finally(() => isMounted && setLoadingRelated(false));
    return () => {
      isMounted = false;
    };
  }, [article?.id]);

  useEffect(() => {
    apiService.getLanguages().then(setLanguages).catch(() => setLanguages([]));
    const onKey = (e) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    return () => {
      window.removeEventListener('keydown', onKey);
      window.speechSynthesis?.cancel();
    };
  }, [onClose]);

  const handleExplain = async () => {
    if (!article || loadingExplain) return;
    setLoadingExplain(true);
    apiService.recordEvent(article.id, 'explain');
    try {
      const data = await apiService.explainArticle(article.id);
      setExplanation(data.explanation || 'No explanation generated.');
    } catch {
      setExplanation('The explainer is unavailable right now. Try again in a moment.');
    } finally {
      setLoadingExplain(false);
    }
  };

  const handleGenerateSummary = async () => {
    if (!article || isSummarizing) return;
    setIsSummarizing(true);
    try {
      await onGenerateSummary?.(article.id);
    } finally {
      setIsSummarizing(false);
    }
  };

  const handleTranslate = async (code) => {
    setLang(code);
    setTranslateError(null);
    window.speechSynthesis?.cancel();
    setSpeaking(false);
    if (!code) {
      setTranslation(null);
      return;
    }
    setTranslating(true);
    apiService.recordEvent(article.id, 'translate');
    try {
      setTranslation(await apiService.translate(article.id, code));
    } catch (e) {
      setTranslation(null);
      setTranslateError(e.message);
    } finally {
      setTranslating(false);
    }
  };

  const shown = translation || article;
  const speechSupported = typeof window !== 'undefined' && 'speechSynthesis' in window;

  const handleListen = () => {
    if (!speechSupported) return;
    if (speaking) {
      window.speechSynthesis.cancel();
      setSpeaking(false);
      return;
    }
    const takeaways = Array.isArray(shown.key_takeaways) ? shown.key_takeaways.join('. ') : '';
    const text = [shown.title, shown.summary || article.description, takeaways].filter(Boolean).join('. ');
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = translation ? SPEECH_LANG[translation.language] || 'en-US' : 'en-US';
    utterance.rate = 1;
    utterance.onend = () => setSpeaking(false);
    utterance.onerror = () => setSpeaking(false);
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(utterance);
    setSpeaking(true);
    apiService.recordEvent(article.id, 'listen');
  };

  if (!article) return null;

  return (
    <div className="modal-overlay" onClick={onClose} role="dialog" aria-modal="true" aria-labelledby="modal-title">
      <div className="modal-content modal-detail" onClick={(e) => e.stopPropagation()}>
        <button ref={closeRef} className="modal-close" onClick={onClose} aria-label="Close article">
          ✕
        </button>

        <div className="modal-top-tags">
          <span className="source-badge">{article.source_name}</span>
          <span className="category-tag">{article.category}</span>
          {article.published_at && (
            <span className="modal-date">
              {new Date(article.published_at).toLocaleString('en-US', { dateStyle: 'medium', timeStyle: 'short' })}
            </span>
          )}
          <SentimentMark sentiment={article.sentiment} score={article.sentiment_score} />
          <ReadingTime minutes={article.reading_time_minutes} />
        </div>

        <h2 id="modal-title" className="modal-headline" lang={translation ? translation.language : undefined}>
          {shown.title}
        </h2>

        <div className="modal-toolbar">
          <BookmarkButton saved={isSaved} onToggle={() => onToggleBookmark?.(article)} />
          {speechSupported && (
            <button type="button" className={`tool-btn ${speaking ? 'is-active' : ''}`} onClick={handleListen} aria-pressed={speaking}>
              <svg width="16" height="16" viewBox="0 0 24 24" aria-hidden="true">
                {speaking ? (
                  <path d="M7 5h4v14H7zM13 5h4v14h-4z" fill="currentColor" />
                ) : (
                  <path d="M4 9v6h4l5 4V5L8 9H4zm12.5 3a4.5 4.5 0 0 0-2.5-4v8a4.5 4.5 0 0 0 2.5-4z" fill="currentColor" />
                )}
              </svg>
              {speaking ? 'Stop' : 'Listen'}
            </button>
          )}
          <label className="tool-select">
            <span>Read in</span>
            <select value={lang} onChange={(e) => handleTranslate(e.target.value)} disabled={translating}>
              <option value="">English (original)</option>
              {languages.map((l) => (
                <option key={l.code} value={l.code}>{l.name}</option>
              ))}
            </select>
          </label>
          {translating && <span className="tool-status">Translating…</span>}
          {translation?.cached && <span className="tool-status">Cached translation</span>}
        </div>
        {translateError && <p className="tool-error" role="alert">{translateError}</p>}

        <section className="modal-ai-panel">
          <div className="modal-panel-header">
            <span className="ai-sparkle">✨</span>
            <span className="panel-title">AI briefing{translation ? ` · ${translation.language_name}` : ''}</span>
            {!translation && <GroundingBadge score={article.grounding_score} />}
          </div>

          {shown.summary ? (
            <div lang={translation ? translation.language : undefined}>
              <p className="modal-summary-text">{shown.summary}</p>
              {Array.isArray(shown.key_takeaways) && shown.key_takeaways.length > 0 && (
                <div className="modal-takeaways-block">
                  <strong className="takeaways-label">Key takeaways</strong>
                  <ul className="modal-takeaways-list">
                    {shown.key_takeaways.map((item, idx) => (
                      <li key={idx}>{item}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          ) : (
            <div className="ai-generate-prompt" style={{ padding: '8px 0' }}>
              <button className="btn-summarize-ondemand" onClick={handleGenerateSummary} disabled={isSummarizing}>
                {isSummarizing ? (
                  <>
                    <span className="spinner-dot"></span>
                    <span>Summarizing…</span>
                  </>
                ) : (
                  <>
                    <span className="sparkle-icon">✨</span>
                    <span>Summarize this story</span>
                  </>
                )}
              </button>
            </div>
          )}
        </section>

        <section className="modal-body-section">
          <h4 className="section-title">From the publisher</h4>
          <p className="modal-full-text">
            {article.content || article.description || 'This feed provides only a headline. Open the original story for the full text.'}
          </p>
        </section>

        <section className="modal-tabs-section">
          <div className="modal-tabs" role="tablist" aria-label="Story context">
            {TABS.map((t) => (
              <button
                key={t.id}
                role="tab"
                aria-selected={tab === t.id}
                className={`modal-tab ${tab === t.id ? 'active' : ''}`}
                onClick={() => setTab(t.id)}
              >
                {t.label}
              </button>
            ))}
          </div>

          <div className="modal-tab-panel" role="tabpanel">
            {tab === 'lens' && <PerspectiveLens articleId={article.id} onOpenArticle={onOpenArticleById} />}
            {tab === 'timeline' && <StoryTimeline articleId={article.id} onOpenArticle={onOpenArticleById} />}
            {tab === 'related' &&
              (loadingRelated ? (
                <div className="explainer-loading">Finding stories with similar meaning…</div>
              ) : relatedList.length === 0 ? (
                <p className="empty-subtext">No other collected story is close enough in meaning yet.</p>
              ) : (
                <div className="modal-related-grid">
                  {relatedList.map((rel) => (
                    <div key={rel.id} className="related-mini-card">
                      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px', gap: 8 }}>
                        <span className="source-badge" style={{ fontSize: '11px', padding: '2px 8px' }}>{rel.source_name}</span>
                        <span className="similarity-pill">{Math.round(rel.similarity_score * 100)}% similar</span>
                      </div>
                      <h5 className="related-title">
                        <button className="title-link-btn" onClick={() => onSelectRelated(rel)}>{rel.title}</button>
                      </h5>
                      <p className="related-desc">{rel.summary || (rel.description ? `${rel.description.slice(0, 100)}…` : '')}</p>
                    </div>
                  ))}
                </div>
              ))}
            {tab === 'explain' && (
              <div>
                {!explanation && !loadingExplain && (
                  <button className="btn-secondary" onClick={handleExplain}>
                    💡 Explain the background
                  </button>
                )}
                {loadingExplain && <div className="explainer-loading">Writing a plain-English explainer…</div>}
                {explanation && (
                  <div className="explainer-content">
                    <p style={{ whiteSpace: 'pre-line' }}>{explanation}</p>
                  </div>
                )}
              </div>
            )}
          </div>
        </section>

        <div className="modal-footer">
          <a href={article.canonical_url} target="_blank" rel="noopener noreferrer" className="btn-card-primary" style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
            <span>Read the original story</span>
            <span aria-hidden="true">↗</span>
          </a>
          <button className="btn-secondary" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </div>
  );
}

export default ArticleDetailModal;
