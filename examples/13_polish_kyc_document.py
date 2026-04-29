"""End-to-end Polish KYC artifact: real identifier shapes, real checksum logic.

Realistic onboarding bundle: ID-card number + PESEL for the individual,
NIP / REGON / KRS for the related company, IBAN for the account. Plus a
deliberately-bad PESEL (correct shape, wrong checksum) that the toolkit
must reject.

This is the showcase example for the locale value proposition: hashed PESEL
isn't anonymous under Polish UODO interpretation (the search space is
brute-forceable), so reversible tokenization with an out-of-band Mapping is
the regulator-defensible posture for handling these documents in LLM
pipelines.

Run:

    python examples/13_polish_kyc_document.py
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

KYC_DOCUMENT = """\
KARTA KLIENTA -- ONBOARDING

Klient indywidualny:
  Imię i nazwisko: Anna Maria Nowak
  PESEL: 02070803628
  Numer dowodu osobistego: ABC123456
  Adres email: anna.nowak@example.pl
  Telefon: +48 600 123 456

Powiązany podmiot gospodarczy:
  Nazwa: Nowak Consulting Sp. z o.o.
  NIP: 526-000-12-46
  REGON: 123456785
  KRS: 0000123456
  Konto rozliczeniowe: PL61109010140000071219812874

Uwagi compliance:
  Numer 44051401358 podany przez klienta jako alternatywny PESEL nie został
  potwierdzony (suma kontrolna nieprawidłowa). Wymagana ponowna weryfikacja.
"""


def build_pipeline() -> tuple[AnalyzerEngine, AnonymizerEngine]:
    nlp_engine = NlpEngineProvider(
        nlp_configuration={
            "nlp_engine_name": "spacy",
            "models": [{"lang_code": "pl", "model_name": "pl_core_news_sm"}],
        }
    ).create_engine()
    registry = RecognizerRegistry(supported_languages=["pl"])
    # KRS is opt-in because its raw regex (10 digits) collides with ordinary
    # numbers; register the full set including KRS for this KYC pipeline.
    for r in get_recognizers(["pl"], include_opt_in=True):
        registry.add_recognizer(r)
    analyzer = AnalyzerEngine(registry=registry, nlp_engine=nlp_engine, supported_languages=["pl"])
    anonymizer = AnonymizerEngine()
    anonymizer.add_anonymizer(ReversibleReplaceOperator)
    return analyzer, anonymizer


def main() -> None:
    analyzer, anonymizer = build_pipeline()

    print("=== Source document ===")
    print(KYC_DOCUMENT)

    results = analyzer.analyze(text=KYC_DOCUMENT, language="pl")

    print("=== Detection report ===")
    for r in sorted(results, key=lambda x: x.start):
        snippet = KYC_DOCUMENT[r.start : r.end]
        print(f"  {r.entity_type:18s} score={r.score:.2f}  {snippet!r}")

    # The deliberately-bad PESEL (44051401358, last digit perturbed) must
    # NOT appear in the detection report -- our PESEL recognizer rejects
    # checksum failures via Presidio's validate_result hook.
    bad_pesel = "44051401358"
    matched_bad = any(
        KYC_DOCUMENT[r.start : r.end] == bad_pesel and r.entity_type == "PL_PESEL" for r in results
    )
    assert not matched_bad, "checksum-bad PESEL was incorrectly accepted"
    print(f"\n  Confirmed: {bad_pesel!r} was rejected (PESEL checksum failed).")

    print("\n=== Reversible anonymization ===")
    mapping = Mapping()
    anon_text = anonymizer.anonymize(
        text=KYC_DOCUMENT,
        analyzer_results=results,
        operators=reversible_operators(mapping),
    ).text
    print(anon_text)
    print(f"  Mapping holds {len(mapping)} entries.")

    # Round trip via Shield -- the cross-package contract.
    restored = Shield(mapping=mapping).deanonymize(anon_text)
    assert restored == KYC_DOCUMENT, "round-trip mismatch"
    print("\nRound trip succeeded.")


if __name__ == "__main__":
    main()
