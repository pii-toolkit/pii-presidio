"""LLM workflow: anonymize, hand to an LLM, deanonymize the response.

The LLM call is faked here so the example is offline. In a real pipeline,
swap ``fake_llm`` for an actual call (Anthropic, OpenAI, etc.). The same
Mapping handles both directions, so any token the LLM quotes back -- in any
order, in any sentence -- gets resolved to the original value.

Run:

    python examples/03_llm_workflow.py
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


def fake_llm(prompt: str) -> str:
    """Stand-in for an LLM call.

    The model echoes a structured reply that quotes the tokens in a different
    order than the prompt. This mirrors a realistic completion: the LLM sees
    only the anonymized text and weaves the tokens into its response.
    """
    # Minimal but realistic: the LLM produces a confirmation referencing every
    # token it received. In practice you'd do anything -- summarize, translate,
    # ask follow-ups -- the contract is just "tokens that come back get
    # replaced by their originals".
    #
    # Note: tokens use the underlying pii_core PIIType, not the Presidio
    # entity name. So a phone is [PL_PHONE_001], not [PHONE_NUMBER_001].
    # The Presidio entity name shows up only in analyzer results; once
    # tokenized, the country-specific PIIType is what's in the text.
    return (
        "Confirmed. I have received the inquiry from [PERSON_001].\n"
        "I will follow up at [EMAIL_001] regarding PESEL [PL_PESEL_001].\n"
        "If preferred, I can also call [PL_PHONE_001]."
    )


def main() -> None:
    user_text = (
        "Cześć, tu Anna Kowalska. Mój PESEL to 44051401359, "
        "email anna.kowalska@example.pl, telefon +48 600 123 456."
    )

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

    # Pre-seed the Mapping with the speaker's name so the LLM sees a token
    # for it. (Presidio's Polish NER doesn't recognise "Anna Kowalska" out of
    # the box; we add it explicitly. In production you'd plug a real PERSON
    # recognizer or pre-process names yourself.)
    name_token = mapping.token_for("Anna Kowalska", __import__("pii_core").PIIType.PERSON)

    results = analyzer.analyze(text=user_text, language="pl")
    anonymized = anonymizer.anonymize(
        text=user_text,
        analyzer_results=results,
        operators=reversible_operators(mapping),
    ).text

    # Substitute the name in the prompt manually since it's not in the
    # detector list.
    safe_prompt = anonymized.replace("Anna Kowalska", name_token)
    print("Prompt sent to LLM:")
    print(f"  {safe_prompt}")
    print()

    llm_reply = fake_llm(safe_prompt)
    print("LLM reply (still anonymized):")
    print("\n".join("  " + line for line in llm_reply.splitlines()))
    print()

    restored = Shield(mapping=mapping).deanonymize(llm_reply)
    print("Reply restored to the user:")
    print("\n".join("  " + line for line in restored.splitlines()))


if __name__ == "__main__":
    main()
