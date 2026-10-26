"""
Article enrichment utilities shared by the backend and the AI worker.

Every microservice keeps its own copy of this module so that each Docker build
context stays self-contained (backend/app/services/enrichment.py and
worker/app/enrichment.py are identical; collector/app/classifier.py holds the
topic classifier only).

Provides:
  * analyze_sentiment()      VADER sentiment -> (label, compound score)
  * grounding_score()        Fact-Grounding score of an AI summary vs. its source text
  * extract_keywords()       lightweight keyword extraction for trending-topic detection
  * estimate_reading_time()  minutes at ~220 words per minute
  * classify_topic()         keyword-based topic classifier with canonical categories
"""
from __future__ import annotations

import math
import re
from collections import Counter
from typing import Dict, Iterable, List, Optional, Tuple

CANONICAL_CATEGORIES = [
    "World",
    "Politics",
    "Business",
    "Technology",
    "Science",
    "Health",
    "Sports",
    "Entertainment",
    "India",
    "General",
]

STOPWORDS = set(
    """
    a about above after again against all also am an and any are as at be because been before being below
    between both but by can could did do does doing down during each few for from further had has have having
    he her here hers herself him himself his how i if in into is it its itself just me more most my myself no
    nor not now of off on once only or other our ours ourselves out over own same she should so some such than
    that the their theirs them themselves then there these they this those through to too under until up very
    was we were what when where which while who whom why will with would you your yours yourself yourselves
    said says say new news year years one two three first last week weeks day days time times may might
    get gets got make makes made people mr mrs ms us via amid since still per told according including
    could would should over after before like just many much more most also back even well way ago
    longer open keeps kept holds held big small high low next latest early late amid set sets need
    """.split()
)

TOPIC_KEYWORDS: Dict[str, List[str]] = {
    "Technology": [
        "ai", "artificial intelligence", "software", "app", "apple", "google", "microsoft", "meta", "openai",
        "chip", "chips", "semiconductor", "cyber", "hack", "hacker", "data breach", "smartphone", "iphone",
        "android", "startup", "tech", "robot", "algorithm", "cloud", "internet", "computer", "gadget",
        "nvidia", "tesla", "crypto", "bitcoin", "blockchain", "llm", "chatbot", "quantum",
    ],
    "Business": [
        "market", "markets", "stock", "stocks", "shares", "economy", "economic", "inflation", "interest rate",
        "bank", "banks", "profit", "revenue", "earnings", "trade", "tariff", "tariffs", "gdp", "company",
        "companies", "ceo", "investor", "investors", "merger", "acquisition", "sales", "retail", "oil price",
        "jobs", "unemployment", "budget", "rupee", "dollar", "sensex", "nifty", "ipo",
    ],
    "Politics": [
        "election", "elections", "minister", "parliament", "president", "senate", "congress", "government",
        "vote", "voters", "policy", "party", "campaign", "prime minister", "bill", "lawmakers", "opposition",
        "democrat", "republican", "cabinet", "supreme court", "lok sabha", "rajya sabha", "bjp",
    ],
    "Science": [
        "science", "scientist", "scientists", "research", "researchers", "study", "space", "nasa", "isro",
        "planet", "climate", "species", "physics", "astronomy", "fossil", "telescope", "experiment", "galaxy",
        "rocket", "satellite", "mars", "moon", "biology", "ocean", "emissions", "carbon",
    ],
    "Health": [
        "health", "hospital", "doctor", "doctors", "patients", "disease", "virus", "vaccine", "cancer",
        "medical", "medicine", "drug", "drugs", "nhs", "covid", "outbreak", "mental health", "treatment",
        "obesity", "diabetes", "who", "pandemic", "surgery", "nutrition",
    ],
    "Sports": [
        "football", "cricket", "tennis", "match", "league", "cup", "olympic", "olympics", "goal", "coach",
        "tournament", "championship", "fifa", "ipl", "nba", "player", "players", "team", "season", "score",
        "wicket", "premier league", "grand prix", "f1", "athlete", "final",
    ],
    "Entertainment": [
        "film", "movie", "music", "album", "actor", "actress", "celebrity", "tv", "series", "netflix",
        "bollywood", "hollywood", "oscar", "festival", "concert", "singer", "box office", "show", "streaming",
        "award", "awards", "director", "theatre",
    ],
    "World": [
        "war", "ukraine", "russia", "china", "gaza", "israel", "un", "united nations", "nato", "military",
        "troops", "ceasefire", "refugees", "embassy", "sanctions", "border", "diplomat", "summit", "iran",
        "earthquake", "flood", "foreign",
    ],
    "India": [
        "india", "indian", "delhi", "mumbai", "bengaluru", "kolkata", "chennai", "modi", "maharashtra",
        "kerala", "uttar pradesh", "karnataka", "tamil nadu", "gujarat", "punjab",
    ],
}

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z\-']+")
_SENT_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")

_vader = None


def _get_vader():
    global _vader
    if _vader is None:
        try:
            from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

            _vader = SentimentIntensityAnalyzer()
        except Exception:  # pragma: no cover - dependency missing
            _vader = False
    return _vader or None


_POS_WORDS = {"win", "wins", "growth", "record", "breakthrough", "success", "gain", "gains", "hope", "improve",
              "improves", "celebrate", "boost", "rise", "rises", "agreement", "peace", "recovery", "award"}
_NEG_WORDS = {"war", "dead", "death", "deaths", "killed", "crisis", "crash", "fall", "falls", "loss", "losses",
              "attack", "fraud", "fear", "fears", "cut", "cuts", "strike", "flood", "disaster", "decline", "warn"}


def _compound(text: str) -> float:
    analyzer = _get_vader()
    if analyzer is not None:
        return float(analyzer.polarity_scores(text)["compound"])
    words = [w.lower() for w in _WORD_RE.findall(text)]
    pos = sum(1 for w in words if w in _POS_WORDS)
    neg = sum(1 for w in words if w in _NEG_WORDS)
    return 0.0 if pos == neg else (pos - neg) / max(1, pos + neg)


def analyze_sentiment(text: str, title: Optional[str] = None) -> Tuple[str, float]:
    """
    Return (label, score in [-1, 1]).

    News prose is long and mostly neutral, so a single VADER score over the whole text saturates.
    We score each sentence separately and average them; the headline (if given) counts twice
    because it carries the article's framing.
    """
    text = (text or "").strip()
    if not text and not title:
        return "neutral", 0.0

    sentences = [s for s in _SENT_SPLIT_RE.split(text[:3000]) if s.strip()] if text else []
    if title:
        sentences = [title, title] + sentences
    scores = [_compound(s) for s in sentences] or [0.0]
    compound = sum(scores) / len(scores)

    if compound >= 0.15:
        label = "positive"
    elif compound <= -0.15:
        label = "negative"
    else:
        label = "neutral"
    return label, round(compound, 4)


def _content_words(text: str) -> List[str]:
    return [w.lower().strip("-'") for w in _WORD_RE.findall(text or "") if w.lower() not in STOPWORDS and len(w) > 2]


def _stem(word: str) -> str:
    for suffix in ("ing", "ed", "es", "s"):
        if len(word) > 4 and word.endswith(suffix):
            return word[: -len(suffix)]
    return word


def grounding_score(summary: str, source_text: str) -> Optional[float]:
    """
    Fact-Grounding score: share of the summary's content words that are supported by the source text,
    averaged per sentence. 1.0 means every claim-bearing word is traceable to the source; low values flag
    possible hallucination. Deterministic, cheap and model-independent.
    """
    summary = (summary or "").strip()
    source_text = (source_text or "").strip()
    if not summary or not source_text:
        return None

    source_vocab = {_stem(w) for w in _content_words(source_text)}
    if not source_vocab:
        return None

    sentence_scores = []
    for sentence in _SENT_SPLIT_RE.split(summary):
        words = [_stem(w) for w in _content_words(sentence)]
        if not words:
            continue
        supported = sum(1 for w in words if w in source_vocab)
        sentence_scores.append(supported / len(words))

    if not sentence_scores:
        return None
    return round(sum(sentence_scores) / len(sentence_scores), 3)


def extract_keywords(text: str, top_n: int = 6) -> List[str]:
    """Extract salient keywords (unigrams and capitalised bigrams) from article text."""
    text = text or ""
    words = _content_words(text)
    counts = Counter(words)

    # Boost proper-noun style bigrams such as "Supreme Court" or "Reserve Bank"
    bigrams = re.findall(r"(?=\b([A-Z][a-z]+ [A-Z][a-z]+)\b)", text)
    for bg in bigrams:
        parts = bg.lower().split()
        if not any(p in STOPWORDS for p in parts):
            counts[bg.lower()] += 2

    ranked = [w for w, _ in counts.most_common(top_n * 3) if not w.isdigit()]
    result: List[str] = []
    for w in ranked:
        if any(w != r and (w in r.split() or r in w.split()) for r in result):
            continue
        result.append(w)
        if len(result) >= top_n:
            break
    return result


def estimate_reading_time(text: str, wpm: int = 220) -> int:
    words = len((text or "").split())
    return max(1, math.ceil(words / wpm))


def classify_topic(title: str, text: str = "", fallback: str = "General") -> str:
    """Keyword-based topic classifier. Title matches weigh 3x body matches."""
    title_l = f" {(title or '').lower()} "
    body_l = f" {(text or '').lower()[:1500]} "
    scores: Dict[str, float] = {}
    for category, keywords in TOPIC_KEYWORDS.items():
        score = 0.0
        for kw in keywords:
            pattern = f" {kw} "
            if pattern in title_l:
                score += 3
            if pattern in body_l:
                score += 1
        if score:
            scores[category] = score
    if not scores:
        return normalize_category(fallback)
    best = max(scores.items(), key=lambda kv: kv[1])
    return best[0] if best[1] >= 2 else normalize_category(fallback)


def normalize_category(name: Optional[str]) -> str:
    """Map an arbitrary category label onto the canonical category set."""
    if not name:
        return "General"
    cleaned = name.strip().lower()
    for cat in CANONICAL_CATEGORIES:
        if cleaned == cat.lower():
            return cat
    aliases = {
        "tech": "Technology", "ai": "Technology", "gadgets": "Technology", "science & tech": "Technology",
        "economy": "Business", "finance": "Business", "markets": "Business", "money": "Business",
        "sport": "Sports", "arts": "Entertainment", "culture": "Entertainment", "movies": "Entertainment",
        "international": "World", "global": "World", "national": "India", "environment": "Science",
        "science & environment": "Science", "us": "Politics", "us news": "Politics",
    }
    return aliases.get(cleaned, "General")


def enrich_article(title: str, description: Optional[str], content: Optional[str], summary: Optional[str]) -> Dict:
    """Compute every enrichment field for an article in one call."""
    source_text = " ".join(t for t in [title, description, content] if t)
    body = content if content and len(content) > len(description or "") else (description or summary or "")
    label, score = analyze_sentiment(body, title=title)
    return {
        "sentiment": label,
        "sentiment_score": score,
        "grounding_score": grounding_score(summary or "", source_text) if summary else None,
        "reading_time_minutes": estimate_reading_time(content or description or title),
        "keywords": extract_keywords(f"{title}. {description or ''} {content or ''}"),
    }


def top_terms(texts: Iterable[str], top_n: int = 30) -> Counter:
    """Count keyword frequency across a set of texts (used for trending topic spikes)."""
    counter: Counter = Counter()
    for t in texts:
        counter.update(set(extract_keywords(t, top_n=8)))
    return counter
