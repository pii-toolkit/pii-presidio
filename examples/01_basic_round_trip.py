"""Basic round trip: analyze a Polish document, anonymize, then deanonymize.

Run:

    python examples/01_basic_round_trip.py

Prerequisites:

    pip install pii-presidio
    python -m spacy download pl_core_news_sm
"""

from __future__ import annotations

from pii_veil import Mapping, Shield
from presidio_analyzer import AnalyzerEngine, RecognizerRegistry
from presidio_analyzer.nlp_engine import NlpEngineProvider
from presidio_anonymizer import AnonymizerEngine

from pii_presidio import (
    ReversibleReplaceOperator,
    get_recognizers,
    reversible_operators,
)


def build_analyzer() -> AnalyzerEngine:
    nlp_engine = NlpEngineProvider(
        nlp_configuration={
            "nlp_engine_name": "spacy",
            "models": [{"lang_code": "pl", "model_name": "pl_core_news_sm"}],
        }
    ).create_engine()

    registry = RecognizerRegistry(supported_languages=["pl"])
    for recognizer in get_recognizers(["pl"]):
        registry.add_recognizer(recognizer)

    return AnalyzerEngine(
        registry=registry,
        nlp_engine=nlp_engine,
        supported_languages=["pl"],
    )


def main() -> None:
    text = (
        "Dzień dobry, nazywam się Anna Kowalska. "
        "Mój PESEL to 44051401359, NIP firmy: 526-000-12-46. "
        "Proszę o kontakt: anna@example.pl lub +48 600 123 456."
    )

    analyzer = build_analyzer()
    results = analyzer.analyze(text=text, language="pl")

    print("Detected entities:")
    for r in sorted(results, key=lambda x: x.start):
        print(f"  {r.entity_type:15s} score={r.score:.2f}  {text[r.start : r.end]!r}")

    mapping = Mapping()
    anonymizer = AnonymizerEngine()
    anonymizer.add_anonymizer(ReversibleReplaceOperator)

    anonymized = anonymizer.anonymize(
        text=text,
        analyzer_results=results,
        operators=reversible_operators(mapping),
    )

    print("\nAnonymized:")
    print(f"  {anonymized.text}")

    restored = Shield(mapping=mapping).deanonymize(anonymized.text)
    print("\nRestored:")
    print(f"  {restored}")
    assert restored == text, "round-trip mismatch"
    print("\nRound trip succeeded.")


if __name__ == "__main__":
    main()
