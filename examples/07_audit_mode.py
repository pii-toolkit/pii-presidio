"""Audit / compliance mode: detect PII, emit a JSON report, never modify the source.

Use this when the goal is finding sensitive data (data-discovery, compliance
checks, pre-migration scans) -- not anonymizing it. The output is a JSON list
of detected entities with their location, type, and detector confidence.
Pipe it into a SIEM, attach it to a ticket, or diff it across runs.

Run:

    python examples/07_audit_mode.py
"""

from __future__ import annotations

import json
from collections import Counter

from presidio_analyzer import AnalyzerEngine, RecognizerRegistry
from presidio_analyzer.nlp_engine import NlpEngineProvider

from pii_presidio import get_recognizers


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

    analyzer = AnalyzerEngine(
        registry=registry,
        nlp_engine=nlp_engine,
        supported_languages=["pl"],
    )

    # Realistic chunk of a customer interaction log.
    text = (
        "[2026-04-29 10:14] Wiadomość od użytkownika: Cześć, mój PESEL to "
        "44051401359, NIP firmy 526-000-12-46. Przelewy idą na "
        "PL61109010140000071219812874. Dla pewności proszę o kontakt: "
        "jan.kowalski@example.pl albo +48 600 123 456. Karta firmowa: "
        "4532-0151-1283-0366."
    )

    # Reject low-confidence matches -- common audit policy: report only
    # high-signal hits, ignore the long tail of regex-only matches that need
    # human review elsewhere.
    min_score = 0.4
    results = analyzer.analyze(text=text, language="pl", score_threshold=min_score)

    # Build a structured report. Don't include the raw value in production
    # audits unless the report is going somewhere the value is allowed to
    # exist; the offset+length are usually enough.
    report = []
    for r in sorted(results, key=lambda x: x.start):
        report.append(
            {
                "entity_type": r.entity_type,
                "start": r.start,
                "end": r.end,
                "score": round(r.score, 2),
                "value_preview": text[r.start : r.end],
                "detector": (
                    r.recognition_metadata.get("recognizer_name")
                    if r.recognition_metadata
                    else None
                ),
            }
        )

    print("Compliance report:")
    print(json.dumps(report, ensure_ascii=False, indent=2))

    # Aggregate summary -- how many of each entity type were found.
    counts = Counter(item["entity_type"] for item in report)
    print("\nSummary:")
    for entity, n in counts.most_common():
        print(f"  {entity:15s} {n}")

    print(f"\n{len(report)} findings above score >= {min_score}.")


if __name__ == "__main__":
    main()
