"""
The JSON Schema handed to providers' structured-output features so
Section 9.3's "OUTPUT FORMAT (strict JSON)" is enforced by the provider
rather than merely requested in prose.

Constraints this schema respects (both Anthropic structured outputs and
OpenAI json_schema mode impose them):
- every object sets `additionalProperties: false` and lists `required`
- no recursion, no numeric `minimum`/`maximum`, no string length bounds
  (numeric range enforcement therefore lives in
  contracts.InternalEvaluation's clamping validator instead, which is where
  Section 12.8 wants it anyway — server-side, not provider-trusted)
- nullability is expressed as a `type` union, since `anyOf` + `null` is the
  portable spelling across both providers
"""

TURN_DECISION_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": ["decision", "utterance", "internal_evaluation"],
    "properties": {
        "decision": {
            "type": "string",
            "enum": ["next_question", "followup", "skip"],
            "description": "next_question to move on, followup to probe deeper, skip if the candidate clearly passed.",
        },
        "utterance": {
            "type": "string",
            "description": "Exactly what the interviewer says next, in natural spoken English.",
        },
        "internal_evaluation": {
            "type": ["object", "null"],
            "additionalProperties": False,
            "required": ["relevance_score", "completeness_score", "reasoning"],
            "description": "Null when decision is 'skip'. Never shown to the candidate.",
            "properties": {
                "relevance_score": {
                    "type": ["integer", "null"],
                    "description": "0-10. Does the answer address what was asked?",
                },
                "completeness_score": {
                    "type": ["integer", "null"],
                    "description": "0-10. Are the key expected elements present?",
                },
                "reasoning": {
                    "type": ["string", "null"],
                    "description": "Brief internal note. Never shown to the candidate.",
                },
            },
        },
    },
}

OPENING_QUESTION_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": ["decision", "utterance", "internal_evaluation"],
    "properties": {
        "decision": {"type": "string", "enum": ["next_question"]},
        "utterance": {"type": "string", "description": "The opening question, in natural spoken English."},
        "internal_evaluation": {
            "type": "null",
            "description": "Always null — there is no answer to evaluate on the opening turn.",
        },
    },
}
