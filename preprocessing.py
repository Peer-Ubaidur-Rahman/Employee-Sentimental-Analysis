"""
preprocessing.py - text cleaning shared by training and prediction.

Steps: strip HTML -> expand contractions -> lowercase -> keep letters only ->
tokenize -> remove stop words (but KEEP negations such as "not"/"never") -> lemmatize.

Keeping negations matters: "not happy" and "happy" must not look identical to the model.

NLTK is used when its corpora are available. If they cannot be loaded (e.g. no internet
on first run), a lightweight built-in fallback is used and BACKEND is set to "fallback".
The backend name is stored with the trained model so a mismatch can be detected.
"""
import os
import re
import warnings

BACKEND = "fallback"
_NEGATIONS = {"no", "nor", "not", "never", "none", "nothing", "neither", "without", "cannot", "hardly", "barely"}

_FALLBACK_STOPWORDS = set("""
i me my myself we our ours ourselves you your yours yourself yourselves he him his himself she her hers
herself it its itself they them their theirs themselves what which who whom this that these those am is
are was were be been being have has had having do does did doing a an the and but if or because as until
while of at by for with about against between into through during before after above below to from up
down in out on off over under again further then once here there when where why how all any both each
few more most other some such only own same so than too very s t can will just don should now d ll m o
re ve y ain aren couldn didn doesn hadn hasn haven isn ma mightn mustn needn shan shouldn wasn weren won
wouldn would could
""".split())

_stop_words = set(_FALLBACK_STOPWORDS)
_lemmatize_impl = None
_tokenize_impl = None


def _fallback_tokenize(text):
    return re.findall(r"[a-z]+", text)


def _fallback_lemmatize(token):
    for suffix in ("ies", "ing", "ed", "es", "s"):
        if token.endswith(suffix) and len(token) - len(suffix) >= 3:
            stem = token[: -len(suffix)]
            return stem + "y" if suffix == "ies" else stem
    return token


def _init_nltk():
    """Try to switch to real NLTK. Never raises."""
    global BACKEND, _stop_words, _lemmatize_impl, _tokenize_impl
    try:
        import nltk
        from nltk.corpus import stopwords
        from nltk.stem import WordNetLemmatizer
        from nltk.tokenize import word_tokenize
    except ImportError:
        return

    needed = {"corpora/stopwords": "stopwords", "corpora/wordnet": "wordnet",
              "corpora/omw-1.4": "omw-1.4", "tokenizers/punkt": "punkt",
              "tokenizers/punkt_tab": "punkt_tab"}
    allow_download = os.environ.get("NLTK_AUTO_DOWNLOAD", "true").lower() in ("1", "true", "yes")
    for path, pkg in needed.items():
        try:
            nltk.data.find(path)
        except LookupError:
            if not allow_download:
                return
            try:
                nltk.download(pkg, quiet=True)
                nltk.data.find(path)
            except Exception:
                if pkg in ("omw-1.4", "punkt"):
                    continue  # optional for some NLTK versions
                return
    try:
        lemmatizer = WordNetLemmatizer()
        lemmatizer.lemmatize("tests")  # forces corpus load
        _stop_words = set(stopwords.words("english"))
        _tokenize_impl = word_tokenize
        _lemmatize_impl = lemmatizer.lemmatize
        BACKEND = "nltk"
    except Exception:
        return


_init_nltk()
_stop_words = {w for w in _stop_words if w not in _NEGATIONS}
if BACKEND != "nltk":
    warnings.warn(
        "NLTK data not available - using the built-in fallback tokenizer/lemmatizer. "
        "Run: python -m nltk.downloader stopwords wordnet omw-1.4 punkt punkt_tab",
        RuntimeWarning,
    )

_HTML_RE = re.compile(r"<[^>]+>")
_CONTRACTIONS = [(r"won't", "will not"), (r"can't", "can not"), (r"cannot", "can not"),
                 (r"n't", " not"), (r"'re", " are"), (r"'ve", " have"), (r"'ll", " will"),
                 (r"'m", " am"), (r"'d", " would"), (r"'s", "")]


def clean_text(text) -> str:
    """Return normalized text for TF-IDF. Invalid/empty input yields an empty string."""
    if not isinstance(text, str):
        return ""
    text = _HTML_RE.sub(" ", text).lower().replace("\u2019", "'")
    for pattern, repl in _CONTRACTIONS:
        text = re.sub(pattern, repl, text)
    text = re.sub(r"[^a-z\s]", " ", text)  # drops punctuation, digits, symbols
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return ""
    tokens = _tokenize_impl(text) if _tokenize_impl else _fallback_tokenize(text)
    lemma = _lemmatize_impl or _fallback_lemmatize
    out = [lemma(t) for t in tokens if t.isalpha() and len(t) > 1 and t not in _stop_words]
    return " ".join(out)


def clean_batch(texts):
    return [clean_text(t) for t in texts]
