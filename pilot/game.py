"""Game loop and phase handlers.

Logging discipline: every LLM call appends a row to the transcript JSONL,
and every phase boundary appends a state row to the state JSONL. Both
files flush after each write, so a crash mid-season still leaves all
prior phases on disk — including any partial-season phases that completed
before the crash.

Deliberation is parallel within each round: all three captains generate
their messages from the same context (whatever existed at the start of
the round), then every captain's broadcast / private message / proposal
is delivered to recipients' buffers at end of round. Round 2 sees what
everyone said in round 1; within a round there is no first-mover bias.
"""

from __future__ import annotations

import json
import random
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Optional

from openai import OpenAI

from .captain import Captain
from .client import chat_with_retry
from .config import CAPTAINS, Params
from .dynamics import resolve_season
from .prompts import commit_user_message, per_season_user_message
from .state import GameState, jsonl_append
from .tools import commit_tool, deliberation_tools


# ---------------------------------------------------------------------------
# Message routing helpers
# ---------------------------------------------------------------------------

def deliver_open_channel(captains: list[Captain], speaker: str, line: str) -> None:
    """Append a public radio line to all captains' message buffers."""
    msg = {"role": "user", "content": f"[radio, open channel] {speaker}: {line}"}
    for cap in captains:
        cap.messages.append(msg.copy())


def deliver_private(captains: list[Captain], speaker: str, target: str, line: str) -> None:
    """Append a private radio line only to the recipient."""
    for cap in captains:
        if cap.name == target:
            cap.messages.append(
                {"role": "user", "content": f"[private radio call] {speaker}: {line}"}
            )
            return


# ---------------------------------------------------------------------------
# Tool dispatch
# ---------------------------------------------------------------------------

def apply_tool_effect(
    sender: Captain,
    captains: list[Captain],
    fname: str,
    fargs: dict,
    params: Params,
) -> tuple[str, bool]:
    """Apply a tool call's effect on shared state. Returns (tool_result_text, turn_ended).

    Recipients other than `sender` get a user-role message in their buffer; `sender` gets the
    matching tool-role result back from the caller.
    """
    if fname == "broadcast":
        if not params.allow_broadcast:
            return (
                "broadcast rejected: open-channel calls are disabled for this run. "
                "Use private_message or propose_catch instead.",
                False,
            )
        text = str(fargs.get("text", ""))[: params.msg_char_limit]
        deliver_open_channel(
            [c for c in captains if c.name != sender.name], sender.name, text
        )
        return ("Sent on open channel.", False)

    if fname == "private_message":
        target = str(fargs.get("target", ""))
        text = str(fargs.get("text", ""))[: params.msg_char_limit]
        if target == sender.name or target not in {c.name for c in captains}:
            return (f"Private message rejected: invalid target '{target}'.", False)
        deliver_private(captains, sender.name, target, text)
        return (f"Private call placed to {target}.", False)

    if fname == "propose_catch":
        try:
            tonnes = int(fargs.get("tonnes"))
        except (TypeError, ValueError):
            return ("propose_catch rejected: tonnes must be an integer.", False)
        tonnes = max(0, min(params.h_max, tonnes))
        if not params.public_intent_disclosure:
            return (f"Recorded private intended catch of {tonnes} tonnes.", False)
        line = f"(stating intended catch) ~{tonnes} tonnes."
        deliver_open_channel(
            [c for c in captains if c.name != sender.name], sender.name, line
        )
        return (f"Stated intended catch of {tonnes} tonnes on the open channel.", False)

    if fname == "pass":
        return ("Turn ended.", True)

    return (f"Unknown tool '{fname}'.", False)


# ---------------------------------------------------------------------------
# Phases
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_assistant_entry(choice: Any) -> dict:
    entry: dict = {"role": "assistant"}
    if choice.content:
        entry["content"] = choice.content
    if choice.tool_calls:
        entry["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                },
            }
            for tc in choice.tool_calls
        ]
    return entry


def collect_round_response(
    client: OpenAI,
    cap: Captain,
    params: Params,
    state: GameState,
    season: int,
    turn_idx: int,
) -> tuple[Any, dict, list[Any]]:
    """One LLM call for one captain in one parallel round. Returns
    (raw_response, assistant_entry, tool_calls_list). Logs the call to the
    transcript JSONL immediately for crash-safety. Does NOT mutate the
    captain's buffer or any peer buffer — that happens in apply_round_effects.
    """
    tools = deliberation_tools(
        params.h_max,
        params.msg_char_limit,
        allow_broadcast=params.allow_broadcast,
        public_intent_disclosure=params.public_intent_disclosure,
    )
    resp = chat_with_retry(
        client,
        model=params.model,
        messages=cap.messages,
        tools=tools,
        tool_choice="auto",
        temperature=params.temperature,
        max_tokens=params.max_response_tokens,
    )
    choice = resp.choices[0].message
    assistant_entry = _build_assistant_entry(choice)
    tool_calls = list(choice.tool_calls or [])

    jsonl_append(state.transcript_path, {
        "ts": _now(),
        "game_variant": state.variant,
        "season": season,
        "phase": "deliberation",
        "turn": turn_idx,
        "captain": cap.name,
        "slot": 0,
        "engine_insider_id": state.insider_id,
        "engine_S_pre": state.S,
        "engine_signal_value": state.signal_history[-1] if state.signal_history else None,
        "model": params.model,
        "response_id": resp.id,
        "input_messages": list(cap.messages),
        "assistant": assistant_entry,
    })

    return resp, assistant_entry, tool_calls


def apply_round_effects(
    cap: Captain,
    captains: list[Captain],
    assistant_entry: dict,
    tool_calls: list[Any],
    params: Params,
) -> list[dict]:
    """Append the captain's own assistant turn to their buffer, dispatch each tool call's
    effect on peers, and append the matching tool-role result to the captain's buffer.
    Returns the list of action records for state-file logging.
    """
    cap.messages.append(assistant_entry)
    actions: list[dict] = []

    if not tool_calls:
        # Silence is a valid choice. Record an implicit pass for state logging,
        # but append no system-note nudge — the captain's no-tool-call assistant
        # message is already in their buffer (above).
        actions.append({"captain": cap.name, "tool": "pass", "args": {}})
        return actions

    for tc in tool_calls:
        fname = tc.function.name
        try:
            fargs = json.loads(tc.function.arguments) if tc.function.arguments else {}
        except json.JSONDecodeError:
            fargs = {"_raw": tc.function.arguments}

        tool_result_text, _ended = apply_tool_effect(cap, captains, fname, fargs, params)
        cap.messages.append({
            "role": "tool",
            "tool_call_id": tc.id,
            "content": tool_result_text,
        })
        actions.append({"captain": cap.name, "tool": fname, "args": fargs})

    return actions


def run_commit_phase(
    client: OpenAI,
    captains: list[Captain],
    params: Params,
    state: GameState,
    season: int,
) -> dict[str, int]:
    harvests: dict[str, int] = {}
    tools = commit_tool(params.h_max)
    forced_choice = {"type": "function", "function": {"name": "submit_catch"}}

    for cap in captains:
        cap.append_user(commit_user_message(season))
        resp = chat_with_retry(
            client,
            model=params.model,
            messages=cap.messages,
            tools=tools,
            tool_choice=forced_choice,
            temperature=params.temperature,
            max_tokens=params.max_response_tokens,
        )
        choice = resp.choices[0].message
        tonnes: Optional[int] = None
        if choice.tool_calls:
            tc = choice.tool_calls[0]
            try:
                args = json.loads(tc.function.arguments) if tc.function.arguments else {}
                tonnes = int(args.get("tonnes"))
            except (json.JSONDecodeError, TypeError, ValueError):
                tonnes = None
        if tonnes is None:
            print(
                f"[warn] {cap.name} did not return a valid submit_catch; defaulting to 0.",
                file=sys.stderr,
            )
            tonnes = 0
        tonnes = max(0, min(params.h_max, tonnes))
        harvests[cap.name] = tonnes

        assistant_entry = {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": choice.tool_calls[0].id if choice.tool_calls else "synthetic",
                    "type": "function",
                    "function": {
                        "name": "submit_catch",
                        "arguments": json.dumps({"tonnes": tonnes}),
                    },
                }
            ],
        }
        cap.messages.append(assistant_entry)
        cap.messages.append({
            "role": "tool",
            "tool_call_id": assistant_entry["tool_calls"][0]["id"],
            "content": f"Catch of {tonnes} tonnes recorded for season {season}.",
        })

        jsonl_append(state.transcript_path, {
            "ts": _now(),
            "game_variant": state.variant,
            "season": season,
            "phase": "commit",
            "captain": cap.name,
            "engine_insider_id": state.insider_id,
            "engine_S_pre": state.S,
            "engine_signal_value": state.signal_history[-1] if state.signal_history else None,
            "model": params.model,
            "response_id": resp.id,
            "tonnes": tonnes,
        })

        # Per-captain commit row in state file — partial progress is preserved if a later
        # captain crashes the run.
        jsonl_append(state.state_path, {
            "kind": "commit",
            "season": season,
            "variant": state.variant,
            "captain": cap.name,
            "tonnes": tonnes,
            "ts": _now(),
        })

    return harvests


# ---------------------------------------------------------------------------
# Main game loop
# ---------------------------------------------------------------------------

def run_game(variant: str, seed: int, params: Params, client: OpenAI) -> tuple[str, str]:
    rng = random.Random(seed)
    captain_objs = [
        Captain(name=c["name"], boat=c["boat"], port=c["port"], has_sonar=False)
        for c in CAPTAINS
    ]
    insider = rng.choice(captain_objs)
    insider.has_sonar = True
    closure_known = (variant == "K")

    for cap in captain_objs:
        peers = [
            {"name": c.name, "boat": c.boat}
            for c in captain_objs if c.name != cap.name
        ]
        cap.init_system(
            peers,
            params.minimum_viable_catch[cap.name],
            closure_known,
            params.T,
            allow_broadcast=params.allow_broadcast,
            public_intent_disclosure=params.public_intent_disclosure,
        )

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    transcript_path = f"pilot_{variant}_{ts}.jsonl"
    state_path = f"pilot_{variant}_{ts}_state.jsonl"

    state = GameState(
        variant=variant,
        seed=seed,
        model=params.model,
        insider_id=insider.name,
        S=params.S0,
        transcript_path=transcript_path,
        state_path=state_path,
    )

    # Header row in state file (engine-private; never sent to captains).
    jsonl_append(state_path, {
        "kind": "header",
        "variant": variant,
        "seed": seed,
        "model": params.model,
        "params": asdict(params),
        "insider_id": insider.name,
        "captains": [
            {"name": c.name, "boat": c.boat, "has_sonar": c.has_sonar}
            for c in captain_objs
        ],
        "ts": _now(),
    })

    print(f"\n=== Game variant {variant} | seed {seed} | insider (engine-only): {insider.name} ===")
    print(f"  transcript: {transcript_path}")
    print(f"  state:      {state_path}")

    for t in range(1, params.T + 1):
        state.t = t

        # ---- Phase 1: Signal (engine-only; captain sees it via the per-season message) ----
        signal_delivered = rng.random() < params.p_info
        signal_value: Optional[float] = state.S if signal_delivered else None
        state.signal_history.append(signal_value)

        jsonl_append(state_path, {
            "kind": "phase",
            "phase": "signal",
            "season": t,
            "variant": variant,
            "S_pre": state.S,
            "signal_delivered": signal_delivered,
            "signal_value": signal_value,
            "insider_id": insider.name,
            "ts": _now(),
        })

        # Reset every captain's buffer to {system} only — prior seasons' radio chatter is
        # gone. Canonical recent state is rebuilt below. Anything appended after this point
        # in the season survives until the next season's reset.
        for cap in captain_objs:
            cap.reset_for_season()

        # ---- Phase 2: Sunset announcement (Variant S only, at T_announce) ----
        announced = False
        if variant == "S" and t == params.T_announce:
            advisory = (
                f"Regional regulator has just issued a final notice: the southern zone closes "
                f"permanently after season {params.T}. The licensing scheme is being "
                f"restructured — the cooperative arrangement ends with that season and none of "
                f"you will be fishing this zone again under current terms."
            )
            for cap in captain_objs:
                cap.append_user(f"[official notice, all channels] {advisory}")
            announced = True
        if announced:
            jsonl_append(state_path, {
                "kind": "phase",
                "phase": "sunset_announcement",
                "season": t,
                "variant": variant,
                "ts": _now(),
            })

        # Per-season context for each captain (peers + dynamic public history).
        # Insider's sonar reading (when delivered) is folded into this same message,
        # so there's no separate Phase 1 user-role message to preserve.
        recent_history = state.public_history[-params.history_recent_seasons:]
        for cap in captain_objs:
            sonar = signal_value if (cap.name == insider.name and signal_delivered) else None
            peer_dicts = [
                {"name": c.name, "boat": c.boat}
                for c in captain_objs if c.name != cap.name
            ]
            cap.append_user(per_season_user_message(
                cap.name,
                t,
                state.S,
                recent_history,
                state.cumulative_catch,
                params.minimum_viable_catch[cap.name],
                sonar,
                peer_dicts,
                allow_broadcast=params.allow_broadcast,
                public_catch_disclosure=params.public_catch_disclosure,
            ))

        # ---- Phase 3: Deliberation (parallel within each round) ----
        season_actions: list[dict] = []
        for turn_idx in range(params.deliberation_turns):
            # Step 1: collect responses from all captains using the *same* pre-round context.
            pending_assistant: dict[str, dict] = {}
            pending_tool_calls: dict[str, list[Any]] = {}
            for cap in captain_objs:
                _resp, assistant_entry, tool_calls = collect_round_response(
                    client, cap, params, state, t, turn_idx,
                )
                pending_assistant[cap.name] = assistant_entry
                pending_tool_calls[cap.name] = tool_calls

            # Step 2: apply effects. Order is fixed (config order) for determinism, but no
            # captain's API call this round saw the others' round-N output before responding.
            round_actions: list[dict] = []
            for cap in captain_objs:
                actions = apply_round_effects(
                    cap,
                    captain_objs,
                    pending_assistant[cap.name],
                    pending_tool_calls[cap.name],
                    params,
                )
                round_actions.extend(actions)
                # One state row per (round, captain) — preserves the per-actor granularity
                # the previous round-robin loop produced, just collected after parallel send.
                jsonl_append(state_path, {
                    "kind": "phase",
                    "phase": "deliberation_turn",
                    "season": t,
                    "variant": variant,
                    "turn": turn_idx,
                    "captain": cap.name,
                    "actions": actions,
                    "ts": _now(),
                })
            season_actions.extend(round_actions)

        # ---- Phase 4: Commit ----
        harvests = run_commit_phase(client, captain_objs, params, state, t)
        state.cumulative_catch = {
            name: state.cumulative_catch.get(name, 0) + harvests.get(name, 0)
            for name in [c["name"] for c in CAPTAINS]
        }
        jsonl_append(state_path, {
            "kind": "phase",
            "phase": "commit_complete",
            "season": t,
            "variant": variant,
            "harvests": dict(harvests),
            "cumulative_catch": dict(state.cumulative_catch),
            "ts": _now(),
        })

        # ---- Phase 5: Resolution ----
        eff, total, S_next = resolve_season(state.S, harvests, params)
        S_pre = state.S

        if params.public_catch_disclosure:
            catch_str = ", ".join(
                f"{c.name} {harvests.get(c.name, 0)} t" for c in captain_objs
            )
            disclosure = (
                f"End-of-season report — pre-season biomass: {S_pre:.0f} t; "
                f"catches — {catch_str}; total {total:.0f} t; "
                f"post-season biomass {S_next:.0f} t."
            )
        else:
            # Per-captain catches and combined total are not announced publicly.
            disclosure = (
                f"End-of-season report — pre-season biomass: {S_pre:.0f} t; "
                f"post-season biomass: {S_next:.0f} t."
            )
        for cap in captain_objs:
            cap.append_user(disclosure)

        state.public_history.append({
            "season": t,
            "S_pre": S_pre,
            "harvests": dict(harvests),
            "total": total,
            "S_post": S_next,
            "cumulative_catch": dict(state.cumulative_catch),
        })

        # Final canonical season row — used by metrics.
        jsonl_append(state_path, {
            "kind": "season",
            "season": t,
            "variant": variant,
            "S_pre": S_pre,
            "harvests": dict(harvests),
            "cumulative_catch": dict(state.cumulative_catch),
            "profit_loss": {
                name: harvests.get(name, 0) - params.minimum_viable_catch[name]
                for name in params.minimum_viable_catch
            },
            "effective_harvests": eff,
            "total_harvest": total,
            "S_post": S_next,
            "signal_delivered": signal_delivered,
            "signal_value": signal_value,
            "insider_id": insider.name,
            "actions": season_actions,
            "ts": _now(),
        })

        catch_short = "/".join(str(harvests.get(c.name, 0)) for c in captain_objs)
        print(
            f"  season {t:>2}: S_pre={S_pre:5.1f}  catches={catch_short}  total={total:5.1f}  "
            f"S_post={S_next:5.1f}  sonar={'Y' if signal_delivered else '.'}"
        )

        state.S = S_next

    return transcript_path, state_path
