"""
predictor.py - loads the saved TF-IDF vectorizer + Logistic Regression model and predicts.

Every label comes from model.predict()/predict_proba(); there is no keyword or dictionary
fallback. If artifacts are missing, ModelNotTrainedError is raised and callers must show
a clear message instead of inventing a result.
"""
import json
import os
import threading

import joblib
import numpy as np

import preprocessing
from vectorizer import load_vectorizer

MODEL_FILE = "sentiment_classifier.joblib"
METRICS_FILE = "metrics.json"


class ModelNotTrainedError(RuntimeError):
    """Raised when model artifacts are missing. Fix: run `python train_model.py`."""


class SentimentPredictor:
    def __init__(self, model_dir: str):
        self.model_dir = model_dir
        self._lock = threading.Lock()
        self._model = None
        self._vectorizer = None
        self.metadata = {}

    def _load(self):
        if self._model is not None:
            return
        with self._lock:
            if self._model is not None:
                return
            model_path = os.path.join(self.model_dir, MODEL_FILE)
            try:
                vectorizer = load_vectorizer(self.model_dir)
            except FileNotFoundError as exc:
                raise ModelNotTrainedError(
                    "Sentiment model not found. Run 'python train_model.py' first.") from exc
            if not os.path.exists(model_path):
                raise ModelNotTrainedError("Sentiment model not found. Run 'python train_model.py' first.")
            self._model = joblib.load(model_path)
            self._vectorizer = vectorizer
            meta_path = os.path.join(self.model_dir, METRICS_FILE)
            if os.path.exists(meta_path):
                with open(meta_path, encoding="utf-8") as fh:
                    self.metadata = json.load(fh)

    @property
    def is_ready(self) -> bool:
        try:
            self._load()
            return True
        except ModelNotTrainedError:
            return False

    @property
    def version(self) -> str:
        self._load()
        return self.metadata.get("model_version", "unknown")

    def backend_mismatch(self) -> bool:
        """True if text is being cleaned differently now than when the model was trained."""
        self._load()
        trained = self.metadata.get("preprocessing_backend")
        return bool(trained) and trained != preprocessing.BACKEND

    def predict(self, text: str) -> dict:
        """
        Returns {sentiment, confidence, probabilities{Positive,Neutral,Negative}, model_version}.
        Text that is empty after cleaning cannot be scored: ValueError is raised.
        """
        self._load()
        cleaned = preprocessing.clean_text(text)
        if not cleaned:
            raise ValueError("Feedback contains no analysable words.")
        features = self._vectorizer.transform([cleaned])
        proba = self._model.predict_proba(features)[0]
        probs = {cls: float(p) for cls, p in zip(self._model.classes_, proba)}
        label = self._model.classes_[int(np.argmax(proba))]
        return {
            "sentiment": str(label),
            "confidence": round(float(np.max(proba)), 4),
            "probabilities": {k: round(probs.get(k, 0.0), 4) for k in ("Positive", "Neutral", "Negative")},
            "model_version": self.version,
        }

    def explain(self, text: str, top_n: int = 5) -> list:
        """
        Terms that pushed the prediction toward the predicted class
        (tf-idf weight x class coefficient). Descriptive only, not causal.
        """
        self._load()
        cleaned = preprocessing.clean_text(text)
        if not cleaned:
            return []
        features = self._vectorizer.transform([cleaned])
        proba = self._model.predict_proba(features)[0]
        idx = int(np.argmax(proba))
        coefs = self._model.coef_[idx]
        row = features.tocoo()
        names = self._vectorizer.get_feature_names_out()
        contribs = [(names[j], float(v * coefs[j])) for j, v in zip(row.col, row.data)]
        contribs.sort(key=lambda t: t[1], reverse=True)
        return [{"term": t, "weight": round(w, 3)} for t, w in contribs[:top_n] if w > 0]


_predictors = {}


def get_predictor(model_dir: str) -> SentimentPredictor:
    if model_dir not in _predictors:
        _predictors[model_dir] = SentimentPredictor(model_dir)
    return _predictors[model_dir]


if __name__ == "__main__":
    from config import BaseConfig
    p = get_predictor(BaseConfig.MODEL_DIR)
    for s in ["I am very happy with the management and the working environment.",
              "The workload is exhausting and management never listens to employees.",
              "The workplace is okay and the facilities are standard."]:
        try:
            print(s, "->", p.predict(s))
        except ModelNotTrainedError as e:
            print("ERROR:", e)
            break
