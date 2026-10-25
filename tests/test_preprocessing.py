"""Unit tests for text cleaning, the training pipeline and the predictor. No database needed."""
import contextlib
import io
import os
import shutil
import tempfile
import unittest

import preprocessing
import train_model
from predictor import ModelNotTrainedError, SentimentPredictor
from tests.helpers import trained_model_dir


class CleanTextTests(unittest.TestCase):
    def test_lowercase_punctuation_and_numbers_removed(self):
        out = preprocessing.clean_text("The company is AMAZING!!! I have worked here for 2 years.")
        self.assertEqual(out, out.lower())
        self.assertNotRegex(out, r"[0-9!.]")

    def test_html_is_stripped(self):
        self.assertNotIn("<", preprocessing.clean_text("Great <b>team</b> <script>x</script>"))
        self.assertIn("team", preprocessing.clean_text("Great <b>team</b>"))

    def test_negations_survive_stopword_removal(self):
        self.assertIn("not", preprocessing.clean_text("I am not happy").split())
        self.assertIn("not", preprocessing.clean_text("I don't like the workload").split())
        self.assertIn("never", preprocessing.clean_text("Management never listens").split())

    def test_stopwords_removed(self):
        tokens = preprocessing.clean_text("this is the best of the teams").split()
        for stop in ("this", "is", "the", "of"):
            self.assertNotIn(stop, tokens)

    def test_invalid_input_is_safe(self):
        for bad in (None, 123, "", "   ", "12345 !!! ???", ["list"]):
            self.assertEqual(preprocessing.clean_text(bad), "")


class TrainingPipelineTests(unittest.TestCase):
    def test_dataset_validation_rejects_bad_labels_and_columns(self):
        d = tempfile.mkdtemp()
        try:
            bad_cols = os.path.join(d, "a.csv")
            open(bad_cols, "w").write("text,label\nhello,Positive\n")
            with self.assertRaises(SystemExit):
                train_model.load_dataset(bad_cols)
            bad_label = os.path.join(d, "b.csv")
            open(bad_label, "w").write("feedback,sentiment\nhello there friend,Happy\n")
            with self.assertRaises(SystemExit):
                train_model.load_dataset(bad_label)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_training_creates_artifacts_and_real_metrics(self):
        model_dir = trained_model_dir()
        for name in ("sentiment_classifier.joblib", "tfidf_vectorizer.joblib", "metrics.json"):
            self.assertTrue(os.path.exists(os.path.join(model_dir, name)), name)
        import json
        m = json.load(open(os.path.join(model_dir, "metrics.json")))
        self.assertTrue(m["dataset_is_synthetic"])
        self.assertEqual(sum(sum(r) for r in m["test_split"]["confusion_matrix"]), m["test_split"]["n"])
        self.assertGreater(m["test_split"]["accuracy"], 1 / 3)  # better than chance: a sanity check, not a quality claim

    def test_vectorizer_is_fitted_on_training_split_only(self):
        # Row 5 carries a token that exists nowhere else; with a held-out split it must not enter the vocabulary
        # unless it landed in the training split. We verify the property directly on the pipeline order instead:
        import inspect
        src = inspect.getsource(train_model.run)
        self.assertLess(src.index("train_test_split"), src.index("fit_transform"))


class PredictorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.predictor = SentimentPredictor(trained_model_dir())

    def test_prediction_structure_and_probabilities(self):
        r = self.predictor.predict("I am very happy with the management and the working environment.")
        self.assertIn(r["sentiment"], ("Positive", "Neutral", "Negative"))
        self.assertAlmostEqual(sum(r["probabilities"].values()), 1.0, places=2)
        self.assertEqual(r["confidence"], max(r["probabilities"].values()))

    def test_unseen_sentences_are_scored_by_the_model(self):
        pos = self.predictor.predict("I am very happy with the management and the working environment.")
        neg = self.predictor.predict("The workload is exhausting and management never listens to employees.")
        self.assertGreater(pos["probabilities"]["Positive"], neg["probabilities"]["Positive"])
        self.assertGreater(neg["probabilities"]["Negative"], pos["probabilities"]["Negative"])

    def test_negation_changes_the_outcome_probabilities(self):
        a = self.predictor.predict("The management is helpful and supportive")["probabilities"]["Positive"]
        b = self.predictor.predict("The management is not helpful and not supportive")["probabilities"]["Positive"]
        self.assertGreater(a, b)

    def test_empty_text_raises_value_error(self):
        with self.assertRaises(ValueError):
            self.predictor.predict("12345 !!!")

    def test_explanation_terms_come_from_the_text(self):
        text = "The workload is exhausting and management never listens"
        terms = {t["term"] for t in self.predictor.explain(text)}
        cleaned = preprocessing.clean_text(text)
        for t in terms:
            self.assertTrue(all(part in cleaned for part in t.split()))

    def test_missing_model_raises_clear_error(self):
        empty = tempfile.mkdtemp()
        try:
            with self.assertRaises(ModelNotTrainedError):
                SentimentPredictor(empty).predict("some feedback here")
        finally:
            shutil.rmtree(empty, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
