"""Add a custom Presidio recognizer alongside the toolkit's built-ins.

Common scenario: your domain has internal identifiers (customer IDs, ticket
numbers, employee codes) that aren't covered by the default toolkit. Build a
``PatternRecognizer`` directly with your regex, register it with the same
``RecognizerRegistry`` we populate, and it works with the same ``Mapping``
and operator pipeline.

Tokens for the custom entity reuse an existing ``PIIType`` (here ``PERSON``)
because the operator only routes through entries it knows about. To get a
dedicated token prefix like ``[CUSTOMER_ID_NNN]`` you'd extend ``pii_core``
with a new ``PIIType`` value and update ``ENTITY_FOR_PII_TYPE`` -- typically
via a thin wrapper package rather than a fork.

Run:

    python examples/05_custom_detector.py
"""

from __future__ import annotations

from pii_core import PIIType
from pii_veil import Mapping, Shield
from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer, RecognizerRegistry
from presidio_analyzer.nlp_engine import NlpEngineProvider
from presidio_anonymizer import AnonymizerEngine

from pii_presidio import (
    ReversibleReplaceOperator,
    get_recognizers,
    reversible_operators,
)


def main() -> None:
    nlp_engine = NlpEngineProvider(
        nlp_configuration={
            "nlp_engine_name": "spacy",
            "models": [{"lang_code": "pl", "model_name": "pl_core_news_sm"}],
        }
    ).create_engine()

    registry = RecognizerRegistry(supported_languages=["pl"])
    for r in get_recognizers(["pl"]):
        registry.add_recognizer(r)

    # Custom recognizer for internal customer IDs (CID-12345). Score 0.85
    # because the pattern is specific enough that a regex match is high-
    # confidence. Context words boost confidence further when the ID appears
    # near terms like "klient" or "customer".
    registry.add_recognizer(
        PatternRecognizer(
            supported_entity="CUSTOMER_ID",
            patterns=[Pattern(name="customer_id", regex=r"\bCID-\d{5}\b", score=0.85)],
            context=["customer", "klient", "id"],
            supported_language="pl",
        )
    )

    analyzer = AnalyzerEngine(
        registry=registry,
        nlp_engine=nlp_engine,
        supported_languages=["pl"],
    )

    text = "Klient CID-12345 (PESEL 44051401359) zgłasza problem przy CID-67890."
    results = analyzer.analyze(text=text, language="pl")
    print("Detected:")
    for r in sorted(results, key=lambda x: x.start):
        print(f"  {r.entity_type:15s} score={r.score:.2f}  {text[r.start : r.end]!r}")

    # Built-in operator handles entities the toolkit knows. For CUSTOMER_ID we
    # tokenize via the Mapping directly and substitute the result into the
    # text -- straightforward because the entity name isn't in
    # ENTITY_FOR_PII_TYPE.
    mapping = Mapping()
    anonymizer = AnonymizerEngine()
    anonymizer.add_anonymizer(ReversibleReplaceOperator)

    anonymized = anonymizer.anonymize(
        text=text,
        analyzer_results=[r for r in results if r.entity_type != "CUSTOMER_ID"],
        operators=reversible_operators(mapping),
    ).text

    # Substitute the custom entity, walking back-to-front so earlier offsets
    # stay valid as we rewrite later spans.
    for r in sorted(
        (r for r in results if r.entity_type == "CUSTOMER_ID"),
        key=lambda x: x.start,
        reverse=True,
    ):
        value = text[r.start : r.end]
        token = mapping.token_for(value, PIIType.PERSON)
        anonymized = anonymized.replace(value, token)

    print(f"\nAnonymized: {anonymized}")
    restored = Shield(mapping=mapping).deanonymize(anonymized)
    print(f"Restored:   {restored}")
    assert restored == text


if __name__ == "__main__":
    main()
