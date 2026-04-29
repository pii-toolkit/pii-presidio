# pii-presidio

Microsoft Presidio plugin: multi-language PII recognizers with reversible anonymization, built on [`pii-core`](https://github.com/pii-toolkit/pii-core) and [`pii-veil`](https://github.com/pii-toolkit/pii-veil).

## Install

```bash
pip install pii-presidio
python -m spacy download pl_core_news_sm   # required for Polish NLP analysis
```

`pii-presidio` pulls in `presidio-analyzer`, `presidio-anonymizer`, `pii-core`, and `pii-veil`. spaCy itself comes via Presidio; the Polish language model has to be downloaded separately (Presidio's standard pattern).

## Recognizers

```python
from pii_presidio import get_recognizers
from presidio_analyzer import AnalyzerEngine, RecognizerRegistry
from presidio_analyzer.nlp_engine import NlpEngineProvider

nlp_engine = NlpEngineProvider(nlp_configuration={
    "nlp_engine_name": "spacy",
    "models": [{"lang_code": "pl", "model_name": "pl_core_news_sm"}],
}).create_engine()

registry = RecognizerRegistry(supported_languages=["pl"])
for r in get_recognizers(["pl"]):
    registry.add_recognizer(r)

analyzer = AnalyzerEngine(registry=registry, nlp_engine=nlp_engine, supported_languages=["pl"])
results = analyzer.analyze(text="PESEL 44051401359, email jan@example.pl", language="pl")
```

Each `pii_core` detector becomes one `PatternRecognizer`. Confidence scores are 0.85 for checksum-validated detectors (PESEL, NIP, REGON, IBAN, credit card) and 0.4 for regex-only ones (ID card, passport, phone, email). Per-detector context words are pre-set to common Polish keywords; pass your own via `PiiCoreRecognizer(detector, context=[...])` if you need different boosts.

KRS and postal-code detectors are excluded by default (their raw regexes match ordinary 10-digit and `XX-XXX` strings); enable them with `include_opt_in=True` and pair with strict context filtering.

## Reversible anonymization

```python
from pii_veil import Mapping, Shield
from pii_presidio import ReversibleReplaceOperator, reversible_operators
from presidio_anonymizer import AnonymizerEngine

mapping = Mapping()
engine = AnonymizerEngine()
engine.add_anonymizer(ReversibleReplaceOperator)

result = engine.anonymize(
    text="PESEL 44051401359, email jan@example.pl",
    analyzer_results=results,
    operators=reversible_operators(mapping),
)
# result.text -> "PESEL [PL_PESEL_001], email [EMAIL_001]"

# Send result.text to an LLM, get a response back, then:
restored = Shield(mapping=mapping).deanonymize(llm_response_text)
```

The `Mapping` is the round-trip handle. It uses the same JSON format as standalone `pii-veil`, so you can interleave the two -- anonymize via Presidio, deanonymize via `Shield`, or vice versa.

## Entity name mapping

| `pii_core.PIIType` | Presidio entity name |
|---|---|
| `PL_PESEL`, `PL_NIP`, `PL_REGON`, `PL_ID_CARD`, `PL_PASSPORT`, `PL_KRS`, `PL_POSTAL_CODE` | same string (country-prefixed) |
| `PL_PHONE` | `PHONE_NUMBER` |
| `PL_IBAN` | `IBAN_CODE` |
| `EMAIL` | `EMAIL_ADDRESS` |
| `CREDIT_CARD` | `CREDIT_CARD` |

Cross-language types use Presidio's standard names so existing pipelines that filter `entities=["EMAIL_ADDRESS"]` pick our recognizers up unchanged.

## Sibling packages

- [`pii-core`](https://github.com/pii-toolkit/pii-core) -- multi-language detection primitives this plugin reuses.
- [`pii-veil`](https://github.com/pii-toolkit/pii-veil) -- non-Presidio reversible anonymization with the same `Mapping` format.

## License

Apache-2.0. See `LICENSE`.
