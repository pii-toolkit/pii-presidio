"""Persist the Mapping to JSON so anonymization survives across processes.

This is the realistic shape of an LLM-pipeline gateway: the anonymizer runs in
one service, the deanonymizer in another. The Mapping JSON is the only thing
they share.

Run:

    python examples/02_persisted_mapping.py
"""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from pii_veil import Mapping, Shield
from presidio_analyzer import AnalyzerEngine, RecognizerRegistry
from presidio_analyzer.nlp_engine import NlpEngineProvider
from presidio_anonymizer import AnonymizerEngine

from pii_presidio import (
    ReversibleReplaceOperator,
    get_recognizers,
    reversible_operators,
)


def anonymize_in_process_a(text: str, mapping_path: Path) -> str:
    """Process A: detect + anonymize, then persist the Mapping."""
    nlp_engine = NlpEngineProvider(
        nlp_configuration={
            "nlp_engine_name": "spacy",
            "models": [{"lang_code": "pl", "model_name": "pl_core_news_sm"}],
        }
    ).create_engine()
    registry = RecognizerRegistry(supported_languages=["pl"])
    for r in get_recognizers(["pl"]):
        registry.add_recognizer(r)
    analyzer = AnalyzerEngine(
        registry=registry,
        nlp_engine=nlp_engine,
        supported_languages=["pl"],
    )

    anonymizer = AnonymizerEngine()
    anonymizer.add_anonymizer(ReversibleReplaceOperator)

    mapping = Mapping()
    results = analyzer.analyze(text=text, language="pl")
    anonymized = anonymizer.anonymize(
        text=text,
        analyzer_results=results,
        operators=reversible_operators(mapping),
    )

    # Persist the Mapping. JSON is plain UTF-8 text -- safe to put in any
    # store, but treat it as sensitive: it contains the original PII values.
    mapping_path.write_text(mapping.to_json(), encoding="utf-8")
    return anonymized.text


def deanonymize_in_process_b(anonymized_text: str, mapping_path: Path) -> str:
    """Process B: load the Mapping, deanonymize. No detectors needed."""
    raw = mapping_path.read_text(encoding="utf-8")
    mapping = Mapping.from_json(raw)
    return Shield(mapping=mapping).deanonymize(anonymized_text)


def main() -> None:
    text = (
        "Klient: Jan Nowak, PESEL 44051401359. "
        "Email: jan.nowak@firma.pl. Konto: PL61109010140000071219812874."
    )

    with TemporaryDirectory() as tmp:
        mapping_file = Path(tmp) / "mapping.json"

        anonymized = anonymize_in_process_a(text, mapping_file)
        print("Process A produced anonymized text:")
        print(f"  {anonymized}")
        print()
        print("Persisted mapping JSON (truncated):")
        snippet = json.dumps(json.loads(mapping_file.read_text(encoding="utf-8")), indent=2)
        print("\n".join("  " + line for line in snippet.splitlines()[:8]) + "\n  ...")
        print()

        restored = deanonymize_in_process_b(anonymized, mapping_file)
        print("Process B restored:")
        print(f"  {restored}")
        assert restored == text


if __name__ == "__main__":
    main()
