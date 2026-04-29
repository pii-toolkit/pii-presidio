"""Sanitize JSON tool-call arguments before they reach the LLM, deanonymize before execution.

Agent flow: a user request lands as JSON like
``{"tool": "send_email", "args": {"to": "anna@example.pl", "body": "..."}}``.
The model never needs the real email or PESEL to plan; it only needs to
reason about which tool to call. We tokenize the args before the model sees
them, the model reasons over tokens, the resulting tool call comes back with
tokens still in place, and we deanonymize *only* the final args before the
tool actually runs.

The eval / trace store keeps the tokenized version, which is exactly what
you want -- traces are auditable but contain no real PII.

Run:

    python examples/10_agent_tool_calls.py
"""

from __future__ import annotations

import json
import re
from typing import Any

from pii_veil import Mapping, Shield
from presidio_analyzer import AnalyzerEngine, RecognizerRegistry
from presidio_analyzer.nlp_engine import NlpEngineProvider
from presidio_anonymizer import AnonymizerEngine

from pii_presidio import (
    ReversibleReplaceOperator,
    get_recognizers,
    reversible_operators,
)

_TOKEN_RE = re.compile(r"\[[A-Z_]+_\d+\]")


def anonymize_string(
    text: str, analyzer: AnalyzerEngine, anonymizer: AnonymizerEngine, mapping: Mapping
) -> str:
    """Tokenize a single string field via the existing pipeline."""
    if not text:
        return text
    results = analyzer.analyze(text=text, language="pl")
    if not results:
        return text
    return anonymizer.anonymize(
        text=text,
        analyzer_results=results,
        operators=reversible_operators(mapping),
    ).text


def anonymize_json(
    payload: Any,
    analyzer: AnalyzerEngine,
    anonymizer: AnonymizerEngine,
    mapping: Mapping,
) -> Any:
    """Walk a JSON-shaped value; anonymize every string leaf."""
    if isinstance(payload, str):
        return anonymize_string(payload, analyzer, anonymizer, mapping)
    if isinstance(payload, dict):
        return {k: anonymize_json(v, analyzer, anonymizer, mapping) for k, v in payload.items()}
    if isinstance(payload, list):
        return [anonymize_json(v, analyzer, anonymizer, mapping) for v in payload]
    return payload


def deanonymize_json(payload: Any, mapping: Mapping) -> Any:
    """Inverse of anonymize_json -- swap tokens back to original values."""
    shield = Shield(mapping=mapping)
    if isinstance(payload, str):
        return shield.deanonymize(payload) if _TOKEN_RE.search(payload) else payload
    if isinstance(payload, dict):
        return {k: deanonymize_json(v, mapping) for k, v in payload.items()}
    if isinstance(payload, list):
        return [deanonymize_json(v, mapping) for v in payload]
    return payload


def fake_agent(tool_call: dict[str, Any]) -> dict[str, Any]:
    """Pretend the LLM agent reasoned over the tokenized payload and emitted a refined call."""
    # Realistic shape: the LLM keeps the structure, optionally rewords the body
    # while preserving tokens, and returns a tool_call to actually execute.
    body = tool_call["args"]["body"]
    return {
        "tool": tool_call["tool"],
        "args": {
            "to": tool_call["args"]["to"],
            "subject": "Re: Twoje zgłoszenie",
            "body": f"Dzień dobry, {body} Pozdrawiam, dział obsługi.",
        },
    }


def execute_tool(tool_call: dict[str, Any]) -> None:
    """Stand-in for the side-effecting tool. In production this hits SMTP / API / DB."""
    print(f"  -> EXECUTE {tool_call['tool']}:")
    print(json.dumps(tool_call["args"], ensure_ascii=False, indent=4))


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

    mapping = Mapping()

    raw_call = {
        "tool": "send_email",
        "args": {
            "to": "jan.kowalski@example.pl",
            "subject": "Potwierdzenie",
            "body": (
                "Potwierdzamy aktualizację PESEL 44051401359 oraz konta "
                "PL61109010140000071219812874."
            ),
        },
    }
    print("Raw tool call from upstream code:")
    print(json.dumps(raw_call, ensure_ascii=False, indent=2))

    safe_call = anonymize_json(raw_call, analyzer, anonymizer, mapping)
    print("\nTokenized call sent to the LLM agent (also what gets logged for evals):")
    print(json.dumps(safe_call, ensure_ascii=False, indent=2))

    refined = fake_agent(safe_call)
    print("\nAgent's refined tool call (tokens preserved):")
    print(json.dumps(refined, ensure_ascii=False, indent=2))

    final = deanonymize_json(refined, mapping)
    print("\nDeanonymized just before execution:")
    execute_tool(final)


if __name__ == "__main__":
    main()
