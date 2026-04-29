"""End-to-end Presidio pipeline tests.

Skipped automatically if the Polish spaCy model isn't installed locally;
CI installs it explicitly. Without the model, ``AnalyzerEngine`` cannot
build a Polish pipeline, so the recognizer logic can be exercised
elsewhere (see test_recognizers.py and test_operator.py).
"""

from __future__ import annotations

import pytest
from pii_veil import Mapping, Shield

spacy = pytest.importorskip("spacy")
try:
    spacy.load("pl_core_news_sm")
except OSError:
    pytest.skip(
        "Polish spaCy model 'pl_core_news_sm' not installed; "
        "run `python -m spacy download pl_core_news_sm`",
        allow_module_level=True,
    )

from presidio_analyzer import AnalyzerEngine, RecognizerRegistry  # noqa: E402
from presidio_analyzer.nlp_engine import NlpEngineProvider  # noqa: E402
from presidio_anonymizer import AnonymizerEngine  # noqa: E402

from pii_presidio import (  # noqa: E402
    ReversibleReplaceOperator,
    get_recognizers,
    reversible_operators,
)


@pytest.fixture(scope="module")
def analyzer() -> AnalyzerEngine:
    nlp_engine = NlpEngineProvider(
        nlp_configuration={
            "nlp_engine_name": "spacy",
            "models": [{"lang_code": "pl", "model_name": "pl_core_news_sm"}],
        }
    ).create_engine()
    registry = RecognizerRegistry(supported_languages=["pl"])
    for r in get_recognizers(["pl"]):
        registry.add_recognizer(r)
    return AnalyzerEngine(
        registry=registry,
        nlp_engine=nlp_engine,
        supported_languages=["pl"],
    )


@pytest.fixture(scope="module")
def anonymizer() -> AnonymizerEngine:
    engine = AnonymizerEngine()
    engine.add_anonymizer(ReversibleReplaceOperator)
    return engine


class TestPresidioPipeline:
    def test_detects_polish_pesel_with_checksum(self, analyzer: AnalyzerEngine) -> None:
        results = analyzer.analyze(text="Mój PESEL to 44051401359.", language="pl")
        assert any(r.entity_type == "PL_PESEL" for r in results)

    def test_rejects_pesel_with_bad_checksum(self, analyzer: AnalyzerEngine) -> None:
        results = analyzer.analyze(text="Number 44051401358 is not a PESEL.", language="pl")
        # 44051401358 fails the PESEL weighted checksum, so PL_PESEL must
        # not appear in the results.
        assert not any(r.entity_type == "PL_PESEL" for r in results)

    def test_finds_email_and_credit_card_in_polish_text(self, analyzer: AnalyzerEngine) -> None:
        text = "Kontakt: jan@example.pl, karta 4532015112830366."
        results = analyzer.analyze(text=text, language="pl")
        types = {r.entity_type for r in results}
        assert "EMAIL_ADDRESS" in types
        assert "CREDIT_CARD" in types

    def test_round_trip_via_pii_veil_shield(
        self, analyzer: AnalyzerEngine, anonymizer: AnonymizerEngine
    ) -> None:
        text = "PESEL 44051401359, NIP 5260001246, email jan@example.pl."
        analyzer_results = analyzer.analyze(text=text, language="pl")
        mapping = Mapping()
        result = anonymizer.anonymize(
            text=text,
            analyzer_results=analyzer_results,
            operators=reversible_operators(mapping),
        )
        # Tokens replaced; original values gone.
        assert "44051401359" not in result.text
        assert "5260001246" not in result.text
        assert "jan@example.pl" not in result.text
        # Shield deanonymize restores the original.
        restored = Shield(mapping=mapping).deanonymize(result.text)
        assert restored == text
