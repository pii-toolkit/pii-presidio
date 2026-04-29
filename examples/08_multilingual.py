"""Single Presidio pipeline handling both Polish and English documents.

Polish identifiers (PESEL, NIP, IBAN) are tagged ``supported_language="pl"``.
Cross-language detectors (email, credit card) get registered once per
language so they fire in either pipeline. This is the right shape when your
service ingests multi-language traffic and language is detected upstream.

Run:

    python examples/08_multilingual.py

Prerequisites:

    python -m spacy download pl_core_news_sm
    python -m spacy download en_core_web_sm
"""

from __future__ import annotations

from presidio_analyzer import AnalyzerEngine, RecognizerRegistry
from presidio_analyzer.nlp_engine import NlpEngineProvider

from pii_presidio import get_recognizers


def main() -> None:
    nlp_engine = NlpEngineProvider(
        nlp_configuration={
            "nlp_engine_name": "spacy",
            "models": [
                {"lang_code": "pl", "model_name": "pl_core_news_sm"},
                {"lang_code": "en", "model_name": "en_core_web_sm"},
            ],
        }
    ).create_engine()

    registry = RecognizerRegistry(supported_languages=["pl", "en"])
    # get_recognizers(["pl", "en"]) emits Polish recognizers tagged "pl" plus
    # cross-language recognizers (email, credit card) emitted once per
    # language. So an English document still gets email/credit-card detection.
    for recognizer in get_recognizers(["pl", "en"]):
        registry.add_recognizer(recognizer)

    analyzer = AnalyzerEngine(
        registry=registry,
        nlp_engine=nlp_engine,
        supported_languages=["pl", "en"],
    )

    pl_text = "Mój PESEL to 44051401359, kontakt: jan@example.pl."
    en_text = "Reach me at jane@example.com or via card 4532015112830366."

    print("--- Polish ---")
    print(f"  {pl_text}")
    for r in sorted(analyzer.analyze(text=pl_text, language="pl"), key=lambda x: x.start):
        print(f"  -> {r.entity_type:15s} score={r.score:.2f}  {pl_text[r.start : r.end]!r}")

    print("\n--- English ---")
    print(f"  {en_text}")
    for r in sorted(analyzer.analyze(text=en_text, language="en"), key=lambda x: x.start):
        print(f"  -> {r.entity_type:15s} score={r.score:.2f}  {en_text[r.start : r.end]!r}")


if __name__ == "__main__":
    main()
