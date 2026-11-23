"""
TF-IDF Retrieval Engine for FormEase Document-Grounded Chatbot.
Performs traditional NLP retrieval using Scikit-Learn:
- Text normalization & tokenization
- Cosine similarity scoring
- Relevance threshold comparison
- Ranked, multi-passage retrieval with source references
"""
from typing import List, Dict, Any, Optional, Tuple
import numpy as np
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from ..core.config import settings

class RetrievedPassage:
    def __init__(
        self,
        content: str,
        page_number: int,
        section_title: str,
        chunk_id: Optional[str],
        similarity_score: float,
        is_weak_match: bool,
        is_original_chunk: bool
    ):
        self.content = content
        self.page_number = page_number
        self.section_title = section_title
        self.chunk_id = chunk_id
        self.similarity_score = round(float(similarity_score), 4)
        self.is_weak_match = is_weak_match
        self.is_original_chunk = is_original_chunk

    def to_dict(self) -> Dict[str, Any]:
        return {
            "content": self.content,
            "page_number": self.page_number,
            "section_title": self.section_title,
            "chunk_id": self.chunk_id,
            "similarity_score": self.similarity_score,
            "is_weak_match": self.is_weak_match,
            "is_original_chunk": self.is_original_chunk
        }

def simple_stem(word: str) -> str:
    """
    Lightweight rule-based suffix stemming for robust document search
    without requiring external NLTK model downloads.
    """
    word = word.lower()
    for suffix in ('ing', 'able', 'tion', 'tions', 'ment', 'ments', 'ies', 'es', 's', 'ed', 'ly'):
        if word.endswith(suffix) and len(word) > len(suffix) + 2:
            return word[:-len(suffix)]
    return word

def stem_tokenizer(text: str) -> List[str]:
    import re
    words = re.findall(r'(?u)\b\w+\b', text.lower())
    # Remove stopwords before stemming so terms like "this" cannot turn into
    # non-stopword tokens ("thi") and spuriously match document introductions.
    return [simple_stem(w) for w in words if w not in ENGLISH_STOP_WORDS]


def expand_retrieval_query(question: str) -> str:
    """Add document-language synonyms for broad purpose/overview questions."""
    import re
    normalized = question.lower()
    is_purpose_question = (
        re.search(r"\b(purpose|aim|objective|goal|intent|intention|scope)\b", normalized)
        or re.search(r"\bwhat\b.{0,35}\b(?:document|agreement|contract|policy|notice|form)\b.{0,20}\babout\b", normalized)
        or re.search(r"\bwhy\b.{0,25}\b(?:document|agreement|contract|policy|notice|form)\b", normalized)
    )
    if not is_purpose_question:
        return question
    return question + " purpose objective aim intent scope establishes sets out outlines governs provides describes covers agreement contract policy notice terms conditions obligations responsibilities rights"

class TFIDFRetriever:
    def __init__(self, threshold: float = None):
        self.threshold = threshold or settings.TFIDF_RELEVANCE_THRESHOLD
        self.vectorizer = TfidfVectorizer(
            max_features=settings.TFIDF_MAX_FEATURES,
            tokenizer=stem_tokenizer,
            token_pattern=None,
            sublinear_tf=True
        )
        self.corpus_passages: List[Dict[str, Any]] = []
        self.tfidf_matrix = None
        self.is_fitted = False

    def fit_corpus(self, chunks: List[Dict[str, Any]], analysis_components: Optional[List[Dict[str, Any]]] = None):
        """
        Fits TF-IDF only on original document chunks, so generated analysis text
        cannot skew original passage ranking or become chatbot evidence.
        """
        self.corpus_passages = []
        texts = []

        # 1. Primary: Original document chunks
        for c in chunks:
            text = c.get("content", "").strip()
            if text:
                texts.append(text)
                self.corpus_passages.append({
                    "content": text,
                    "page_number": c.get("page_number", 1),
                    "section_title": c.get("section_title", "Original Document"),
                    "chunk_id": c.get("id"),
                    "is_original_chunk": True
                })

        if not texts:
            self.is_fitted = False
            return

        self.tfidf_matrix = self.vectorizer.fit_transform(texts)
        self.is_fitted = True

    def query(self, question: str) -> Optional[RetrievedPassage]:
        """
        Backwards-compatible single best passage query.
        """
        matches = self.query_many(question, top_k=1)
        return matches[0] if matches else None

    def query_many(self, question: str, top_k: int = 3) -> List[RetrievedPassage]:
        """Return several distinct, ranked passages with original document citations."""
        if not self.is_fitted or not question.strip():
            return []

        query_vec = self.vectorizer.transform([expand_retrieval_query(question.strip())])
        similarities = cosine_similarity(query_vec, self.tfidf_matrix)[0]
        ranked = sorted(enumerate(similarities), key=lambda pair: float(pair[1]), reverse=True)
        results: List[RetrievedPassage] = []
        seen = set()
        for idx, score in ranked:
            score = float(score)
            passage = self.corpus_passages[idx]
            if score <= 0.001:
                break
            # Answers and citations must be grounded in the actual uploaded text.
            if not passage["is_original_chunk"]:
                continue
            identity = (passage["page_number"], passage["content"][:180])
            if identity in seen:
                continue
            seen.add(identity)
            results.append(RetrievedPassage(
                content=passage["content"],
                page_number=passage["page_number"],
                section_title=passage["section_title"],
                chunk_id=passage["chunk_id"],
                similarity_score=score,
                is_weak_match=score < self.threshold,
                is_original_chunk=True
            ))
            if len(results) >= max(1, top_k):
                break
        return results
