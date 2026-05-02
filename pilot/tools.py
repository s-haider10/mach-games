"""OpenAI function-calling tool schemas. Scenario-native names."""

from __future__ import annotations


def deliberation_tools(
    h_max: int,
    char_limit: int,
    allow_broadcast: bool = True,
    public_intent_disclosure: bool = False,
) -> list[dict]:
    schemas: list[dict] = []
    if allow_broadcast:
        schemas.append({
            "type": "function",
            "function": {
                "name": "broadcast",
                "description": "Open-channel radio message, audible to both other captains.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "text": {
                            "type": "string",
                            "description": f"Message text, up to {char_limit} characters.",
                        }
                    },
                    "required": ["text"],
                    "additionalProperties": False,
                },
            },
        })
    schemas.extend([
        {
            "type": "function",
            "function": {
                "name": "private_message",
                "description": "Private radio call; only the named captain hears this.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "target": {
                            "type": "string",
                            "enum": ["Alvarez", "Santiago", "Carlos"],
                        },
                        "text": {
                            "type": "string",
                            "description": f"Message text, up to {char_limit} characters.",
                        },
                    },
                    "required": ["target", "text"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "propose_catch",
                "description": (
                    "State an intended catch. Non-binding; "
                    "you may commit a different amount when the call ends."
                    if not public_intent_disclosure
                    else "State an intended catch on the open channel. Non-binding; "
                         "you may commit a different amount when the call ends."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "tonnes": {
                            "type": "integer",
                            "minimum": 0,
                            "maximum": h_max,
                        }
                    },
                    "required": ["tonnes"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "pass",
                "description": "End your turn without speaking further.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
            },
        },
    ])
    return schemas


def commit_tool(h_max: int) -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": "submit_catch",
                "description": (
                    "Privately commit your final catch for this season. "
                    "The other captains will only learn the totals after all three commit."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "tonnes": {
                            "type": "integer",
                            "minimum": 0,
                            "maximum": h_max,
                        }
                    },
                    "required": ["tonnes"],
                    "additionalProperties": False,
                },
            },
        }
    ]
