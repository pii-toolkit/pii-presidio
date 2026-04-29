# pii-presidio examples

Runnable scripts demonstrating common use cases. Each script is self-contained.

## Setup

```bash
pip install pii-presidio
python -m spacy download pl_core_news_sm
```

## Scripts

| File | Demonstrates |
|---|---|
| [`01_basic_round_trip.py`](01_basic_round_trip.py) | Analyze, anonymize, deanonymize a Polish document end-to-end. |
| [`02_persisted_mapping.py`](02_persisted_mapping.py) | Save the `Mapping` to JSON and restore it in a "different process" before deanonymizing. The realistic shape of an LLM-pipeline gateway. |
| [`03_llm_workflow.py`](03_llm_workflow.py) | Full anonymize -> LLM -> deanonymize loop with a stand-in LLM that quotes tokens back in a different order. |
| [`04_advanced_recognizers.py`](04_advanced_recognizers.py) | Opt-in detectors (KRS, postal code), custom context words, mixing our recognizers with Presidio's built-ins. |
| [`05_custom_detector.py`](05_custom_detector.py) | Plug a custom `RegexDetector` (internal customer ID) into the same pipeline. |
| [`06_batch_processing.py`](06_batch_processing.py) | Anonymize a folder of documents into one shared `Mapping` so the same person gets the same token everywhere. |
| [`07_audit_mode.py`](07_audit_mode.py) | Detect-only / compliance scan: emit a JSON findings report without modifying the source. |
| [`08_multilingual.py`](08_multilingual.py) | Single Presidio pipeline handling both Polish and English documents (needs both spaCy models). |
| [`09_rag_pipeline.py`](09_rag_pipeline.py) | RAG with redaction at three points: ingest (vector store sees tokens), prompt (LLM sees tokens), answer (deanonymize for the end user). |
| [`10_agent_tool_calls.py`](10_agent_tool_calls.py) | Sanitize JSON tool-call arguments; LLM and trace store see tokens, only the final tool execution sees real values. |
| [`11_dataframe_round_trip.py`](11_dataframe_round_trip.py) | Reversible anonymization of a Pandas DataFrame mixing typed columns (PESEL, IBAN, email) with free-text notes. Requires `pip install pandas`. |
| [`12_dsar_redaction.py`](12_dsar_redaction.py) | GDPR Art. 15 response builder: subject's PII stays visible, third parties tokenized. Two artifacts (internal review + external delivery) from one source. |
| [`13_polish_kyc_document.py`](13_polish_kyc_document.py) | End-to-end Polish KYC document: PESEL + ID card + NIP + REGON + KRS + IBAN, with a deliberately bad-checksum PESEL that must be rejected. |

## Running

```bash
python examples/01_basic_round_trip.py
python examples/02_persisted_mapping.py
python examples/03_llm_workflow.py
python examples/04_advanced_recognizers.py
python examples/05_custom_detector.py
python examples/06_batch_processing.py
python examples/07_audit_mode.py
python examples/08_multilingual.py    # also needs `python -m spacy download en_core_web_sm`
python examples/09_rag_pipeline.py
python examples/10_agent_tool_calls.py
python examples/11_dataframe_round_trip.py    # needs `pip install pandas`
python examples/12_dsar_redaction.py
python examples/13_polish_kyc_document.py
```

Each prints what it's doing; the basic round-trip script asserts the result matches the original at the end.
