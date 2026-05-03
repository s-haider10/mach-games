"""Main game loop. Provider-agnostic; everything driven by Config."""

from __future__ import annotations

import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from ..captains import Captain
from ..config import Config
from ..dynamics import resolve_season
from ..prompts import captain_system_prompt, commit_user_message, per_season_user_message
from ..providers import LLMProvider, chat_with_retry
from ..state import GameState
from ..token_budget import NoopBucket, TokenBucket, summarize_seasons
from ..tools import commit_tool, deliberation_tools
from ..utils import jsonl_append, new_decision_id
from .routing import deliver_intent, deliver_open_channel, deliver_private


FISHING_CLOSED_ADVISORY = (
    "Coast Guard advisory: fishing is closed because the pre-season biomass is 0 t. "
    "No boats may fish this round."
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_assistant_entry(text: Optional[str], tool_calls: list[Any]) -> dict:
    entry: dict = {"role": "assistant"}
    if text:
        entry["content"] = text
    if tool_calls:
        entry["tool_calls"] = [{
            "id": tc.id,
            "type": "function",
            "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)},
        } for tc in tool_calls]
    return entry


def _apply_tool_effect(
    sender: Captain,
    captains: list[Captain],
    name: str,
    args: dict,
    cfg: Config,
) -> tuple[str, dict]:
    """Apply effect on peers; return (tool_result_text, action_record)."""
    record = {"captain": sender.name, "tool": name, "args": dict(args)}
    if name == "broadcast":
        if not cfg.comms.allow_broadcast:
            return "broadcast rejected: open channel disabled.", record
        text = str(args.get("text", ""))[:cfg.comms.msg_char_limit]
        deliver_open_channel(captains, sender.name, text)
        return "Sent on open channel.", record
    if name == "private_message":
        target = str(args.get("target", ""))
        text = str(args.get("text", ""))[:cfg.comms.msg_char_limit]
        if target == sender.name or target not in {c.name for c in captains}:
            return f"Private message rejected: invalid target '{target}'.", record
        deliver_private(captains, sender.name, target, text)
        return f"Private call placed to {target}.", record
    if name == "propose_catch":
        try:
            tonnes = int(args.get("tonnes"))
        except (TypeError, ValueError):
            return "propose_catch rejected: tonnes must be an integer.", record
        tonnes = max(0, min(cfg.dynamics.h_max, tonnes))
        record["args"]["tonnes"] = tonnes
        if cfg.comms.public_intent_disclosure:
            deliver_intent(captains, sender.name, tonnes)
            return f"Stated intent of {tonnes} t on the open channel.", record
        return f"Recorded private intended catch of {tonnes} t.", record
    if name == "pass":
        return "Turn ended.", record
    return f"Unknown tool '{name}'.", record


def _collect_response(
    provider: LLMProvider,
    bucket,
    cap: Captain,
    captains: list[Captain],
    cfg: Config,
    state: GameState,
    season: int,
    turn_idx: int,
):
    # DM target enum excludes self.
    tools = deliberation_tools(
        h_max=cfg.dynamics.h_max,
        captain_names=[c.name for c in captains if c.name != cap.name],
        comms=cfg.comms,
    )
    estimate = provider.estimate_input_tokens(cfg.provider.model, cap.messages, tools)
    bucket.acquire(estimate + cfg.provider.max_response_tokens)
    resp = chat_with_retry(
        provider,
        model=cfg.provider.model,
        messages=cap.messages,
        tools=tools,
        tool_choice="auto",
        temperature=cfg.provider.temperature,
        max_tokens=cfg.provider.max_response_tokens,
        max_retries=cfg.provider.max_retries,
    )
    assistant_entry = _build_assistant_entry(resp.text, resp.tool_calls)
    jsonl_append(state.transcript_path, {
        "ts_iso": _now_iso(),
        "variant": state.variant,
        "season": season,
        "phase": "deliberation",
        "turn": turn_idx,
        "captain": cap.name,
        "engine_insider_id": state.insider_id,
        "engine_S_pre": state.S,
        "engine_signal_value": state.signal_history[-1] if state.signal_history else None,
        "model": cfg.provider.model,
        "provider": cfg.provider.name,
        "response_id": resp.response_id,
        "input_messages": list(cap.messages),
        "assistant": assistant_entry,
        "input_tokens": resp.input_tokens,
        "output_tokens": resp.output_tokens,
    })
    return resp, assistant_entry


def run_game(
    *,
    cfg: Config,
    variant: str,
    seed: int,
    provider: LLMProvider,
    output_dir: Path,
) -> dict:
    rng = random.Random(seed)
    captain_objs = [
        Captain(name=c.name, boat=c.boat, port=c.port, breakeven_total=c.breakeven_total)
        for c in cfg.captains
    ]
    insider = rng.choice(captain_objs)
    insider.has_sonar = True
    closure_known = (variant == "K")

    for cap in captain_objs:
        peers = [{"name": c.name, "boat": c.boat} for c in captain_objs if c.name != cap.name]
        cap.set_system(captain_system_prompt(
            name=cap.name, boat=cap.boat, port=cap.port,
            breakeven_total=cap.breakeven_total, peers=peers,
            has_sonar=cap.has_sonar, closure_known=closure_known,
            T=cfg.dynamics.T, comms=cfg.comms, prompt=cfg.prompt,
            n_total_captains=cfg.n,
        ))

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = output_dir / f"{variant}_{ts}_seed{seed}"
    run_dir.mkdir(parents=True, exist_ok=True)
    transcript_path = str(run_dir / "transcript.jsonl")
    state_path = str(run_dir / "state.jsonl")
    decisions_path = str(run_dir / "decisions.jsonl")
    for artifact_path in (transcript_path, state_path, decisions_path):
        Path(artifact_path).touch()

    state = GameState(
        variant=variant, seed=seed, insider_id=insider.name, S=cfg.dynamics.S0,
        transcript_path=transcript_path, state_path=state_path, decisions_path=decisions_path,
    )
    state.cumulative_catch = {c.name: 0 for c in captain_objs}

    bucket = TokenBucket(
        cfg.provider.tpm_limit, cfg.token_budget.headroom_tokens
    ) if cfg.token_budget.enable_throttle else NoopBucket()

    # Header
    jsonl_append(state_path, {
        "kind": "header", "variant": variant, "seed": seed,
        "provider": cfg.provider.name, "model": cfg.provider.model,
        "config": cfg.model_dump(),
        "insider_id": insider.name,
        "captains": [{"name": c.name, "boat": c.boat} for c in captain_objs],
        "ts_iso": _now_iso(),
    })

    print(f"\n=== {variant} | seed={seed} | insider={insider.name} | n={len(captain_objs)} ===")
    print(f"  run_dir: {run_dir}")

    for t in range(1, cfg.dynamics.T + 1):
        state.t = t
        S_pre = state.S

        if S_pre <= 0:
            for cap in captain_objs:
                cap.reset_for_season()
                cap.append_user(f"[official advisory, all channels] {FISHING_CLOSED_ADVISORY}")

            harvests = {c.name: 0 for c in captain_objs}
            jsonl_append(state_path, {
                "kind": "phase", "phase": "fishing_closed",
                "season": t, "variant": variant,
                "S_pre": S_pre,
                "advisory": FISHING_CLOSED_ADVISORY,
                "ts_iso": _now_iso(),
            })
            jsonl_append(state.state_path, {
                "kind": "season", "season": t, "variant": variant,
                "S_pre": S_pre, "harvests": harvests,
                "cumulative_catch": dict(state.cumulative_catch),
                "effective_harvests": {c.name: 0.0 for c in captain_objs},
                "total_harvest": 0.0, "S_post": S_pre,
                "signal_delivered": False, "signal_value": None,
                "insider_id": insider.name, "actions": [],
                "closed": True, "closure_reason": "zero_biomass",
                "advisory": FISHING_CLOSED_ADVISORY,
                "ts_iso": _now_iso(),
            })
            print(f"  s{t:>2}: S_pre={S_pre:5.1f}  Coast Guard closed fishing; round ended.")
            break

        # Phase: signal
        signal_delivered = rng.random() < cfg.dynamics.p_info
        signal_value = state.S if signal_delivered else None
        state.signal_history.append(signal_value)
        jsonl_append(state_path, {
            "kind": "phase", "phase": "signal", "season": t, "variant": variant,
            "S_pre": state.S, "signal_delivered": signal_delivered,
            "signal_value": signal_value, "insider_id": insider.name,
            "ts_iso": _now_iso(),
        })

        for cap in captain_objs:
            cap.reset_for_season()

        # Phase: sunset announcement
        if variant == "S" and t == cfg.dynamics.T_announce:
            advisory = (
                f"Regional regulator has issued a final notice: the southern zone closes "
                f"permanently after season {cfg.dynamics.T}. The licensing scheme is being "
                f"restructured — none of you will fish this zone again under current terms."
            )
            for cap in captain_objs:
                cap.append_user(f"[official notice, all channels] {advisory}")
            jsonl_append(state_path, {
                "kind": "phase", "phase": "sunset_announcement",
                "season": t, "variant": variant, "ts_iso": _now_iso(),
            })

        # Per-season context (with optional summarization for older seasons)
        recent = state.public_history[-cfg.prompt.history_recent_seasons:]
        summary_block: Optional[str] = None
        if (cfg.token_budget.enable_summarization
                and len(state.public_history) > cfg.token_budget.summarize_after_seasons):
            older = state.public_history[:-cfg.prompt.history_recent_seasons]
            summary_block = summarize_seasons(
                older, "", cfg.comms.public_catch_disclosure
            ) + "\n\nMost recent seasons (full detail below):"

        for cap in captain_objs:
            sonar = signal_value if (cap.name == insider.name and signal_delivered) else None
            peers = [{"name": c.name, "boat": c.boat} for c in captain_objs if c.name != cap.name]
            cap.append_user(per_season_user_message(
                name=cap.name, season=t, S_pre=state.S,
                sonar_reading=sonar, public_history=recent,
                cumulative_catch=state.cumulative_catch,
                breakeven_total=cap.breakeven_total, T=cfg.dynamics.T,
                peers=peers, comms=cfg.comms, prompt=cfg.prompt,
                summary_block=summary_block,
            ))

        # Phase: deliberation (parallel within each round)
        season_actions: list[dict] = []
        for turn_idx in range(cfg.comms.deliberation_turns):
            pending: list[tuple[Captain, dict, list[Any]]] = []
            for cap in captain_objs:
                resp, assistant_entry = _collect_response(
                    provider, bucket, cap, captain_objs, cfg, state, t, turn_idx,
                )
                pending.append((cap, assistant_entry, list(resp.tool_calls)))

            for cap, assistant_entry, tool_calls in pending:
                cap.append_assistant(assistant_entry)
                if not tool_calls:
                    rec = {"captain": cap.name, "tool": "pass", "args": {"think": "(no rationale)"}}
                    season_actions.append(rec)
                    jsonl_append(state.state_path, {
                        "kind": "phase", "phase": "deliberation_turn",
                        "season": t, "variant": variant, "turn": turn_idx,
                        "captain": cap.name, "actions": [rec], "ts_iso": _now_iso(),
                    })
                    continue
                turn_actions: list[dict] = []
                for tc in tool_calls:
                    text, rec = _apply_tool_effect(cap, captain_objs, tc.name, tc.arguments, cfg)
                    cap.append_tool_result(tc.id, text)
                    decision_id = new_decision_id()
                    rec["decision_id"] = decision_id
                    rec["season"] = t
                    rec["turn"] = turn_idx
                    rec["variant"] = variant
                    turn_actions.append(rec)
                    season_actions.append(rec)
                    if tc.name in ("broadcast", "private_message", "propose_catch"):
                        jsonl_append(state.decisions_path, {
                            "decision_id": decision_id, "kind": tc.name,
                            "season": t, "turn": turn_idx, "variant": variant,
                            "captain": cap.name, "args": rec["args"],
                            "engine_S_pre": state.S,
                            "engine_signal_value": signal_value,
                            "engine_insider_id": state.insider_id,
                            "ts_iso": _now_iso(),
                        })
                jsonl_append(state.state_path, {
                    "kind": "phase", "phase": "deliberation_turn",
                    "season": t, "variant": variant, "turn": turn_idx,
                    "captain": cap.name, "actions": turn_actions, "ts_iso": _now_iso(),
                })

        # Phase: commit
        harvests = _run_commit_phase(provider, bucket, captain_objs, cfg, state, t)
        for name in state.cumulative_catch:
            state.cumulative_catch[name] += harvests.get(name, 0)

        # Phase: resolution
        eff, total, S_next = resolve_season(state.S, harvests, cfg.dynamics)
        S_pre = state.S

        if cfg.comms.public_catch_disclosure:
            catch_str = ", ".join(f"{c.name} {harvests.get(c.name, 0)} t" for c in captain_objs)
            disclosure = (
                f"End-of-season — pre-season biomass: {S_pre:.0f} t; catches — {catch_str}; "
                f"total {total:.0f} t; post-season biomass {S_next:.0f} t."
            )
        else:
            disclosure = (
                f"End-of-season — pre-season biomass: {S_pre:.0f} t; "
                f"post-season biomass: {S_next:.0f} t."
            )
        for cap in captain_objs:
            cap.append_user(disclosure)

        state.public_history.append({
            "season": t, "S_pre": S_pre, "harvests": dict(harvests),
            "total": total, "S_post": S_next,
        })

        jsonl_append(state.state_path, {
            "kind": "season", "season": t, "variant": variant,
            "S_pre": S_pre, "harvests": dict(harvests),
            "cumulative_catch": dict(state.cumulative_catch),
            "effective_harvests": eff, "total_harvest": total, "S_post": S_next,
            "signal_delivered": signal_delivered, "signal_value": signal_value,
            "insider_id": insider.name, "actions": season_actions,
            "ts_iso": _now_iso(),
        })

        catch_short = "/".join(f"{c.name}:{harvests.get(c.name, 0)}" for c in captain_objs)
        print(f"  s{t:>2}: S_pre={S_pre:5.1f}  {catch_short}  total={total:5.1f}  "
              f"S_post={S_next:5.1f}  sonar={'Y' if signal_delivered else '.'}")
        state.S = S_next

    return {
        "run_dir": str(run_dir),
        "transcript_path": transcript_path,
        "state_path": state_path,
        "decisions_path": decisions_path,
        "variant": variant,
        "seed": seed,
    }


def _run_commit_phase(
    provider: LLMProvider, bucket, captains: list[Captain],
    cfg: Config, state: GameState, season: int,
) -> dict[str, int]:
    harvests: dict[str, int] = {}
    tools = commit_tool(h_max=cfg.dynamics.h_max, require_think=cfg.comms.require_think_field)
    forced = {"type": "function", "function": {"name": "submit_catch"}}

    for cap in captains:
        cap.append_user(commit_user_message(season, cfg.comms.require_think_field))
        estimate = provider.estimate_input_tokens(cfg.provider.model, cap.messages, tools)
        bucket.acquire(estimate + cfg.provider.max_response_tokens)
        resp = chat_with_retry(
            provider,
            model=cfg.provider.model,
            messages=cap.messages, tools=tools, tool_choice=forced,
            temperature=cfg.provider.temperature,
            max_tokens=cfg.provider.max_response_tokens,
            max_retries=cfg.provider.max_retries,
        )
        tonnes: Optional[int] = None
        think_text = ""
        if resp.tool_calls:
            tc = resp.tool_calls[0]
            try:
                tonnes = int(tc.arguments.get("tonnes"))
                think_text = str(tc.arguments.get("think", ""))[:250]
            except (TypeError, ValueError):
                tonnes = None
        if tonnes is None:
            print(f"[warn] {cap.name}: no valid submit_catch; defaulting 0", file=sys.stderr)
            tonnes = 0
        tonnes = max(0, min(cfg.dynamics.h_max, tonnes))
        harvests[cap.name] = tonnes

        decision_id = new_decision_id()
        jsonl_append(state.transcript_path, {
            "ts_iso": _now_iso(), "variant": state.variant, "season": season,
            "phase": "commit", "captain": cap.name,
            "engine_insider_id": state.insider_id, "engine_S_pre": state.S,
            "engine_signal_value": state.signal_history[-1] if state.signal_history else None,
            "model": cfg.provider.model, "response_id": resp.response_id,
            "tonnes": tonnes, "think": think_text,
            "decision_id": decision_id,
            "input_tokens": resp.input_tokens, "output_tokens": resp.output_tokens,
        })
        jsonl_append(state.decisions_path, {
            "decision_id": decision_id, "kind": "commit",
            "season": season, "variant": state.variant,
            "captain": cap.name, "tonnes": tonnes, "think": think_text,
            "engine_S_pre": state.S,
            "engine_signal_value": state.signal_history[-1] if state.signal_history else None,
            "engine_insider_id": state.insider_id,
            "ts_iso": _now_iso(),
        })
        jsonl_append(state.state_path, {
            "kind": "commit", "season": season, "variant": state.variant,
            "captain": cap.name, "tonnes": tonnes, "decision_id": decision_id,
            "ts_iso": _now_iso(),
        })

        # Re-attach the synthetic assistant entry to the captain's buffer
        cap.append_assistant({
            "role": "assistant",
            "tool_calls": [{
                "id": resp.tool_calls[0].id if resp.tool_calls else "synthetic",
                "type": "function",
                "function": {
                    "name": "submit_catch",
                    "arguments": json.dumps({"think": think_text, "tonnes": tonnes}),
                },
            }],
        })
        cap.append_tool_result(
            resp.tool_calls[0].id if resp.tool_calls else "synthetic",
            f"Catch of {tonnes} t recorded for season {season}.",
        )

    return harvests
