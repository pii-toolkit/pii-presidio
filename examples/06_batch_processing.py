"""Batch-anonymize a folder of documents into one shared Mapping.

The same person/email/PESEL appearing in multiple files gets the same token
across the entire batch. Useful for anonymizing a corpus before fine-tuning,
or scrubbing a folder of customer support transcripts.

Run:

    python examples/06_batch_processing.py
"""

from __future__ import annotations

from dataclasses import dataclass
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


@dataclass
class Document:
    name: str
    text: str


SAMPLE_DOCS = [
    Document(
        "ticket-001.txt",
        "Klient: Jan Kowalski, PESEL 44051401359, email jan@example.pl. "
        "Zgłasza problem z logowaniem.",
    ),
    Document(
        "ticket-002.txt",
        "Ten sam klient (jan@example.pl) ponownie kontaktuje się w sprawie "
        "konta PL61109010140000071219812874.",
    ),
    Document(
        "ticket-003.txt",
        "Inny klient: Anna Nowak, PESEL 02070803628, NIP 5260001246. "
        "Email anna@example.pl, tel +48 600 123 456.",
    ),
]


def build_pipeline() -> tuple[AnalyzerEngine, AnonymizerEngine]:
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
    return analyzer, anonymizer


def main() -> None:
    analyzer, anonymizer = build_pipeline()
    mapping = Mapping()  # Shared across the whole batch.

    with TemporaryDirectory() as tmp:
        out_dir = Path(tmp)

        # Write the originals so the example reflects a realistic folder layout.
        for doc in SAMPLE_DOCS:
            (out_dir / f"orig_{doc.name}").write_text(doc.text, encoding="utf-8")

        # Anonymize each document; the same Mapping accumulates entries across
        # all calls, so jan@example.pl in ticket-001 and ticket-002 becomes the
        # same [EMAIL_001] token in both outputs.
        for doc in SAMPLE_DOCS:
            results = analyzer.analyze(text=doc.text, language="pl")
            anonymized = anonymizer.anonymize(
                text=doc.text,
                analyzer_results=results,
                operators=reversible_operators(mapping),
            ).text
            (out_dir / f"anon_{doc.name}").write_text(anonymized, encoding="utf-8")
            print(f"--- {doc.name} ---")
            print(f"  {anonymized}")
            print()

        # Persist the shared Mapping once for the whole batch.
        mapping_file = out_dir / "batch_mapping.json"
        mapping_file.write_text(mapping.to_json(), encoding="utf-8")

        # Show the consistency property: same value -> same token across files.
        print(f"Mapping has {len(mapping)} unique values across {len(SAMPLE_DOCS)} docs.")

        # Restore everything to verify the round-trip.
        shield = Shield(mapping=Mapping.from_json(mapping_file.read_text(encoding="utf-8")))
        for doc in SAMPLE_DOCS:
            anon_text = (out_dir / f"anon_{doc.name}").read_text(encoding="utf-8")
            restored = shield.deanonymize(anon_text)
            assert restored == doc.text, f"round-trip failed for {doc.name}"
        print("All documents round-trip cleanly.")


if __name__ == "__main__":
    main()
