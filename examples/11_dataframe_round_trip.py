"""Reversible anonymization of a Pandas DataFrame: structured columns + free-text notes.

A common shape: a CSV / Parquet table mixes typed PII columns (names,
emails, PESELs, IBANs) with one or more free-text "notes" columns that may
contain additional PII inline. Anonymize both kinds in one pass with a
shared Mapping so the same value yields the same token regardless of where
it appeared.

The Mapping is the round-trip handle. Persist it to a vault; without it the
DataFrame stays anonymized forever.

Caveat: ``pii-presidio`` ships pattern-and-checksum recognizers. Personal
names mentioned inside free-text notes (e.g. row 2's notes referencing
"Jan Kowalski") aren't caught -- there's no NER for PERSON in our default
set. For DataFrames that need name detection in notes, either preload a
known-names list (see ``12_dsar_redaction.py``) or register Presidio's
``SpacyRecognizer`` for the language you're targeting.

Requires: ``pip install pandas``

Run:

    python examples/11_dataframe_round_trip.py
"""

from __future__ import annotations

import pandas as pd
from pii_core import PIIType
from pii_veil import Mapping, Shield
from presidio_analyzer import AnalyzerEngine, RecognizerRegistry
from presidio_analyzer.nlp_engine import NlpEngineProvider
from presidio_anonymizer import AnonymizerEngine

from pii_presidio import (
    ReversibleReplaceOperator,
    get_recognizers,
    reversible_operators,
)

# Column -> PIIType mapping for typed columns. The free-text "notes" column is
# scanned by the analyzer pipeline; typed columns skip detection and tokenize
# the whole cell value as the declared type.
TYPED_COLUMNS: dict[str, PIIType] = {
    "name": PIIType.PERSON,
    "pesel": PIIType.PL_PESEL,
    "nip": PIIType.PL_NIP,
    "email": PIIType.EMAIL,
    "iban": PIIType.PL_IBAN,
}


def anonymize_dataframe(
    df: pd.DataFrame,
    notes_columns: list[str],
    analyzer: AnalyzerEngine,
    anonymizer: AnonymizerEngine,
    mapping: Mapping,
) -> pd.DataFrame:
    out = df.copy()
    # Typed columns: tokenize the cell value directly.
    for col, pii_type in TYPED_COLUMNS.items():
        if col not in out.columns:
            continue
        out[col] = out[col].map(
            lambda v, t=pii_type: mapping.token_for(v, t) if isinstance(v, str) and v else v
        )

    # Free-text columns: run the analyzer on each cell.
    for col in notes_columns:
        if col not in out.columns:
            continue

        def _scan(text: object) -> object:
            if not isinstance(text, str) or not text:
                return text
            results = analyzer.analyze(text=text, language="pl")
            if not results:
                return text
            return anonymizer.anonymize(
                text=text,
                analyzer_results=results,
                operators=reversible_operators(mapping),
            ).text

        out[col] = out[col].map(_scan)
    return out


def deanonymize_dataframe(df: pd.DataFrame, mapping: Mapping) -> pd.DataFrame:
    shield = Shield(mapping=mapping)
    out = df.copy()
    # All textual columns can be passed through Shield -- non-token text falls
    # through unchanged.
    for col in out.columns:
        out[col] = out[col].map(lambda v: shield.deanonymize(v) if isinstance(v, str) else v)
    return out


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
    analyzer = AnalyzerEngine(registry=registry, nlp_engine=nlp_engine, supported_languages=["pl"])
    anonymizer = AnonymizerEngine()
    anonymizer.add_anonymizer(ReversibleReplaceOperator)

    df = pd.DataFrame(
        [
            {
                "id": "A-1001",
                "name": "Jan Kowalski",
                "pesel": "44051401359",
                "nip": "5260001246",
                "email": "jan@example.pl",
                "iban": "PL61109010140000071219812874",
                "notes": "Klient dzwonił w sprawie konta. Drugi kontakt: anna@example.pl.",
            },
            {
                "id": "A-1002",
                "name": "Anna Nowak",
                "pesel": "02070803628",
                "nip": "5260001246",
                "email": "anna@example.pl",
                "iban": "PL61109010140000071219812874",
                "notes": "Reklamacja przesłana przez Jan Kowalski (PESEL 44051401359).",
            },
        ]
    )

    print("=== Original DataFrame ===")
    print(df.to_string(index=False))

    mapping = Mapping()
    anon_df = anonymize_dataframe(df, ["notes"], analyzer, anonymizer, mapping)
    print("\n=== Anonymized ===")
    print(anon_df.to_string(index=False))

    print(f"\n  Mapping has {len(mapping)} unique values.")
    # Note: Jan Kowalski's PESEL appears in row 1's pesel column AND in row 2's
    # notes column. Both should resolve to the same token because they share
    # the Mapping.

    restored = deanonymize_dataframe(anon_df, mapping)
    print("\n=== Restored ===")
    print(restored.to_string(index=False))
    assert restored.equals(df), "round-trip mismatch"
    print("\nDataFrame round-trip succeeded.")


if __name__ == "__main__":
    main()
