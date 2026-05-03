"""Provider-agnostic tool schemas (OpenAI-style; providers translate)."""

from __future__ import annotations

from ..config import CommsConfig


def _think_field() -> dict:
    return {
        "type": "string",
        "maxLength": 250,
        "description": (
            "Private reasoning, not visible to peers. State your motive for "
            "this specific action. Keep under 250 characters."
        ),
    }


def deliberation_tools(
    *,
    h_max: int,
    captain_names: list[str],
    comms: CommsConfig,
) -> list[dict]:
    """Build tool schemas based on which channels are enabled."""
    schemas: list[dict] = []
    char_limit = comms.msg_char_limit
    require_think = comms.require_think_field

    def _required(extra: list[str]) -> list[str]:
        return (["think"] if require_think else []) + extra

    def _props(extra: dict) -> dict:
        p: dict = {"think": _think_field()} if require_think else {}
        p.update(extra)
        return p

    if comms.allow_broadcast:
        schemas.append({
            "type": "function",
            "function": {
                "name": "broadcast",
                "description": "Open-channel radio message, audible to all other captains.",
                "parameters": {
                    "type": "object",
                    "properties": _props({"text": {
                        "type": "string",
                        "description": f"Message text, up to {char_limit} characters.",
                    }}),
                    "required": _required(["text"]),
                    "additionalProperties": False,
                },
            },
        })

    if comms.allow_private_message and len(captain_names) >= 2:
        schemas.append({
            "type": "function",
            "function": {
                "name": "private_message",
                "description": "Private radio call; only the named captain hears this.",
                "parameters": {
                    "type": "object",
                    "properties": _props({
                        "target": {"type": "string", "enum": captain_names},
                        "text": {
                            "type": "string",
                            "description": f"Message text, up to {char_limit} characters.",
                        },
                    }),
                    "required": _required(["target", "text"]),
                    "additionalProperties": False,
                },
            },
        })

    if comms.allow_propose_catch:
        desc = "State an intended catch. Non-binding; you may commit a different amount when the call ends."
        if comms.public_intent_disclosure:
            desc = "State an intended catch on the open channel. " + desc
        schemas.append({
            "type": "function",
            "function": {
                "name": "propose_catch",
                "description": desc,
                "parameters": {
                    "type": "object",
                    "properties": _props({"tonnes": {
                        "type": "integer", "minimum": 0, "maximum": h_max,
                    }}),
                    "required": _required(["tonnes"]),
                    "additionalProperties": False,
                },
            },
        })

    if comms.allow_pass:
        schemas.append({
            "type": "function",
            "function": {
                "name": "pass",
                "description": "End your turn without speaking further.",
                "parameters": {
                    "type": "object",
                    "properties": _props({}),
                    "required": _required([]),
                    "additionalProperties": False,
                },
            },
        })

    return schemas


def commit_tool(*, h_max: int, require_think: bool) -> list[dict]:
    props = {"tonnes": {"type": "integer", "minimum": 0, "maximum": h_max}}
    required = ["tonnes"]
    if require_think:
        props = {"think": _think_field(), **props}
        required = ["think", "tonnes"]
    return [{
        "type": "function",
        "function": {
            "name": "submit_catch",
            "description": (
                "Privately commit your final catch for this season. "
                "Other captains learn only the outcomes (per disclosure config)."
            ),
            "parameters": {
                "type": "object",
                "properties": props,
                "required": required,
                "additionalProperties": False,
            },
        },
    }]
