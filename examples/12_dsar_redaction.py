"""GDPR Art. 15 DSAR response builder with selective reversibility.

When subject A asks for "all data we hold about me", the corpus that comes
back from your search index will mention other people too: the support
agent, third parties cc'd, other customers in shared threads. Those people's
PII must be redacted from what's delivered to A.

Two artifacts come out of the same source:

- Internal-review pass: nothing redacted, used by legal to QA the response.
- External-delivery pass: A's PII left visible (it's their data); everyone
  else's PII tokenized.

Two practical wrinkles this example covers:

1. ``pii-presidio`` ships pattern-and-checksum recognizers, not a NER
   model. Names ("Bartosz Wiśniewski") aren't caught by regex. Realistic
   DSAR tooling carries a known-names list per case file -- those names get
   pre-allocated in the Mapping and replaced via straight string substitution
   before Presidio runs. The example demonstrates this.
2. The redaction Mapping should be persisted into a case-keyed vault so
   legal can later reverse a token to confirm an identity if the deliverable
   is challenged. Shown via ``Mapping.to_dict()``.

Run:

    python examples/12_dsar_redaction.py
"""

from __future__ import annotations

from pii_core import PIIType
from pii_veil import Mapping
from presidio_analyzer import AnalyzerEngine, RecognizerRegistry
from presidio_analyzer.nlp_engine import NlpEngineProvider
from presidio_anonymizer import AnonymizerEngine

from pii_presidio import (
    ReversibleReplaceOperator,
    get_recognizers,
    reversible_operators,
)


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
    analyzer = AnalyzerEngine(registry=registry, nlp_engine=nlp_engine, supported_languages=["pl"])
    anonymizer = AnonymizerEngine()
    anonymizer.add_anonymizer(ReversibleReplaceOperator)
    return analyzer, anonymizer


def deliver_to_subject(
    text: str,
    subject_values: dict[str, PIIType],
    third_party_names: list[str],
    analyzer: AnalyzerEngine,
    anonymizer: AnonymizerEngine,
) -> tuple[str, Mapping]:
    """Return the external-delivery view + the third-party Mapping for vault storage.

    Strategy:
    1. Pre-allocate tokens for known third-party names (NER blind spot) and
       replace them in the text before Presidio runs.
    2. Run Presidio anonymization to tokenize regex-detected PII.
    3. Reverse the subset of tokens that point at the requesting subject's
       values back to their originals.
    """
    third_party_mapping = Mapping()

    # Step 1: known names get tokenized via straight string substitution.
    working = text
    for name in third_party_names:
        if name in working:
            token = third_party_mapping.token_for(name, PIIType.PERSON)
            working = working.replace(name, token)

    # Step 2: Presidio handles regex-detectable PII.
    results = analyzer.analyze(text=working, language="pl")
    anon = anonymizer.anonymize(
        text=working,
        analyzer_results=results,
        operators=reversible_operators(third_party_mapping),
    ).text

    # Step 3: walk the Mapping; restore originals for anything that's actually
    # the subject's PII. Use to_dict() rather than reaching into private state.
    subject_pairs = {(t, v) for v, t in subject_values.items()}
    for entry in third_party_mapping.to_dict()["entries"]:
        token = entry["token"]
        pii_type = PIIType(entry["type"])
        value = entry["value"]
        if (pii_type, value) in subject_pairs:
            anon = anon.replace(token, value)

    return anon, third_party_mapping


def main() -> None:
    analyzer, anonymizer = build_pipeline()

    # Anna is the requester. The case file knows her PII (we want it visible
    # in the deliverable) and the names of third parties who appear in her
    # records (we want them redacted because pattern detectors won't catch
    # personal names).
    subject_values: dict[str, PIIType] = {
        "Anna Nowak": PIIType.PERSON,
        "anna.nowak@example.pl": PIIType.EMAIL,
        "02070803628": PIIType.PL_PESEL,
    }
    third_party_names = ["Bartosz Wiśniewski"]

    corpus = [
        "Klient: Anna Nowak (PESEL 02070803628). Email: anna.nowak@example.pl.",
        "Anna Nowak złożyła reklamację. Sprawę przejął Bartosz Wiśniewski "
        "(bartosz@example.com), który skontaktował się z PESEL 44051401359.",
        "Faktura wystawiona dla anna.nowak@example.pl, NIP 5260001246, "
        "kopia do bartosz@example.com.",
    ]

    print("=== Internal-review pass (nothing redacted) ===")
    for line in corpus:
        print(f"  {line}")

    print("\n=== External-delivery pass for Anna Nowak ===")
    last_mapping: Mapping | None = None
    for line in corpus:
        delivered, m = deliver_to_subject(
            line, subject_values, third_party_names, analyzer, anonymizer
        )
        print(f"  {delivered}")
        last_mapping = m

    print(
        "\n  Anna's name, email, and PESEL stay visible (it's her data). "
        "Bartosz's name and email are tokenized; the other PESEL and NIP "
        "are tokenized as third-party PII."
    )

    if last_mapping is not None:
        print(
            f"\n  The third-party Mapping for the last line holds "
            f"{len(last_mapping)} entries. In production, persist each line's "
            f"Mapping into a case-keyed vault so legal can reverse a specific "
            f"token if the deliverable is challenged."
        )


if __name__ == "__main__":
    main()
