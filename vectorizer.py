"""vectorizer.py - TF-IDF configuration and persistence helpers."""
import os

import joblib
from sklearn.feature_extraction.text import TfidfVectorizer

VECTORIZER_FILE = "tfidf_vectorizer.joblib"


def build_vectorizer() -> TfidfVectorizer:
    """Unigrams + bigrams (bigrams capture 'not happy'); sublinear TF damps repeated words."""
    return TfidfVectorizer(ngram_range=(1, 2), min_df=2, max_features=5000, sublinear_tf=True)


def save_vectorizer(vectorizer, model_dir: str) -> str:
    os.makedirs(model_dir, exist_ok=True)
    path = os.path.join(model_dir, VECTORIZER_FILE)
    joblib.dump(vectorizer, path)
    return path


def load_vectorizer(model_dir: str):
    path = os.path.join(model_dir, VECTORIZER_FILE)
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    return joblib.load(path)
