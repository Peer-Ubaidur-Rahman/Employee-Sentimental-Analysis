"""
train_model.py - reproducible training pipeline (TF-IDF + Logistic Regression).

Order of operations (no data leakage):
  1. load + validate dataset   2. clean text   3. TRAIN/TEST SPLIT
  4. fit TF-IDF on TRAIN ONLY  5. train Logistic Regression (class_weight=balanced)
  6. evaluate on the test split and on the separate challenge set
  7. save model, vectorizer and metrics.json

Run:  python train_model.py [--dataset path.csv] [--test-size 0.2]
"""
import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone

import joblib
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (accuracy_score, classification_report, confusion_matrix,
                             precision_recall_fscore_support)
from sklearn.model_selection import train_test_split

import preprocessing
from config import BaseConfig
from vectorizer import build_vectorizer, save_vectorizer

LABELS = ["Negative", "Neutral", "Positive"]
MODEL_FILE = "sentiment_classifier.joblib"
METRICS_FILE = "metrics.json"
RANDOM_STATE = 42


def load_dataset(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        sys.exit(f"Dataset not found: {path}")
    df = pd.read_csv(path)
    missing = {"feedback", "sentiment"} - set(df.columns)
    if missing:
        sys.exit(f"Dataset must contain columns 'feedback' and 'sentiment'; missing {sorted(missing)}")
    df = df.dropna(subset=["feedback", "sentiment"]).copy()
    df["sentiment"] = df["sentiment"].astype(str).str.strip().str.capitalize()
    bad = sorted(set(df["sentiment"]) - set(LABELS))
    if bad:
        sys.exit(f"Unknown sentiment labels in dataset: {bad}. Allowed: {LABELS}")
    df["clean"] = preprocessing.clean_batch(df["feedback"])
    df = df[df["clean"].str.len() > 0]
    if df["sentiment"].nunique() < 3:
        sys.exit("Dataset must contain all three classes: Positive, Neutral, Negative.")
    return df.reset_index(drop=True)


def _summary(y_true, y_pred):
    p, r, f, _ = precision_recall_fscore_support(y_true, y_pred, average="weighted", zero_division=0)
    pm, rm, fm, _ = precision_recall_fscore_support(y_true, y_pred, average="macro", zero_division=0)
    return {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "precision_weighted": float(p), "recall_weighted": float(r), "f1_weighted": float(f),
        "precision_macro": float(pm), "recall_macro": float(rm), "f1_macro": float(fm),
        "confusion_matrix": confusion_matrix(y_true, y_pred, labels=LABELS).tolist(),
        "n": int(len(y_true)),
    }


def _print_block(title, y_true, y_pred, summary):
    print(f"\n{'=' * 60}\n{title}\n{'=' * 60}")
    print(f"Accuracy : {summary['accuracy']:.4f}")
    print(f"Precision: {summary['precision_weighted']:.4f} (weighted)  {summary['precision_macro']:.4f} (macro)")
    print(f"Recall   : {summary['recall_weighted']:.4f} (weighted)  {summary['recall_macro']:.4f} (macro)")
    print(f"F1 Score : {summary['f1_weighted']:.4f} (weighted)  {summary['f1_macro']:.4f} (macro)")
    print("\nClassification report:")
    print(classification_report(y_true, y_pred, labels=LABELS, zero_division=0))
    print("Confusion matrix (rows = actual, columns = predicted)")
    print("Labels:", LABELS)
    for label, row in zip(LABELS, summary["confusion_matrix"]):
        print(f"  {label:<9}", row)


def run(dataset_path, challenge_path, test_size, model_dir):
    df = load_dataset(dataset_path)
    print(f"Loaded {len(df)} rows from {dataset_path}")
    print("Class counts:", df["sentiment"].value_counts().to_dict())
    print(f"Preprocessing backend: {preprocessing.BACKEND}")

    # 3. split BEFORE fitting the vectorizer
    X_train, X_test, y_train, y_test = train_test_split(
        df["clean"], df["sentiment"], test_size=test_size,
        random_state=RANDOM_STATE, stratify=df["sentiment"])

    # 4. TF-IDF fitted on the training portion only
    vectorizer = build_vectorizer()
    Xtr = vectorizer.fit_transform(X_train)
    Xte = vectorizer.transform(X_test)

    # 5. Logistic Regression with class balancing
    clf = LogisticRegression(C=1.0, max_iter=1000, class_weight="balanced", random_state=RANDOM_STATE)
    clf.fit(Xtr, y_train)

    # 6. evaluation
    pred = clf.predict(Xte)
    test_summary = _summary(y_test, pred)
    _print_block("HELD-OUT TEST SPLIT (same distribution as training)", y_test, pred, test_summary)

    challenge_summary = None
    if challenge_path and os.path.exists(challenge_path):
        ch = load_dataset(challenge_path)
        ch_pred = clf.predict(vectorizer.transform(ch["clean"]))
        challenge_summary = _summary(ch["sentiment"], ch_pred)
        _print_block("CHALLENGE SET (handwritten, never used in training)", ch["sentiment"], ch_pred, challenge_summary)

    with open(dataset_path, "rb") as fh:
        digest = hashlib.sha256(fh.read()).hexdigest()
    sources = sorted(df["source"].unique().tolist()) if "source" in df.columns else ["unspecified"]
    synthetic = all(str(s).startswith("synthetic") for s in sources)
    version = f"lr-tfidf-{datetime.now(timezone.utc):%Y%m%d%H%M}-{digest[:8]}"

    os.makedirs(model_dir, exist_ok=True)
    save_vectorizer(vectorizer, model_dir)
    joblib.dump(clf, os.path.join(model_dir, MODEL_FILE))
    metrics = {
        "model_version": version,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "dataset_path": os.path.basename(dataset_path), "dataset_sha256": digest,
        "dataset_rows": int(len(df)), "dataset_sources": sources, "dataset_is_synthetic": synthetic,
        "preprocessing_backend": preprocessing.BACKEND, "labels": LABELS,
        "test_size": test_size, "random_state": RANDOM_STATE,
        "test_split": test_summary, "challenge_set": challenge_summary,
    }
    with open(os.path.join(model_dir, METRICS_FILE), "w", encoding="utf-8") as fh:
        json.dump(metrics, fh, indent=2)

    print(f"\nModel saved:      {os.path.join(model_dir, MODEL_FILE)}")
    print(f"Vectorizer saved: {os.path.join(model_dir, 'tfidf_vectorizer.joblib')}")
    print(f"Metrics saved:    {os.path.join(model_dir, METRICS_FILE)}  (version {version})")
    if synthetic:
        print("\nWARNING: the dataset is SYNTHETIC. These scores demonstrate that the pipeline works;\n"
              "they are NOT evidence of real-world accuracy. Retrain on real labelled feedback.")
    return metrics


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--dataset", default=BaseConfig.DATASET_PATH)
    parser.add_argument("--challenge", default=BaseConfig.CHALLENGE_PATH)
    parser.add_argument("--test-size", type=float, default=0.2)
    parser.add_argument("--model-dir", default=BaseConfig.MODEL_DIR)
    args = parser.parse_args()
    run(args.dataset, args.challenge, args.test_size, args.model_dir)


if __name__ == "__main__":
    main()
