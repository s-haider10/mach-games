"""CLI: every config knob is overridable. Subcommands: run, sweep, score."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from .config import Config, apply_overrides, load_config
from .runner import run_single, run_sweep, score_run


def _add_overrides(p: argparse.ArgumentParser) -> None:
    """Every CLI flag corresponds to a dotted-path Config field."""
    # Provider
    p.add_argument("--provider", choices=["openai", "anthropic", "gemini"])
    p.add_argument("--model", type=str)
    p.add_argument("--temperature", type=float)
    p.add_argument("--max-response-tokens", type=int)
    p.add_argument("--tpm-limit", type=int)

    # Dynamics
    p.add_argument("--n-captains", type=int, dest="_n_unused",
                   help="Captains are sourced from the YAML config; use --config to change.")
    p.add_argument("--t-seasons", type=int)
    p.add_argument("--K", type=float)
    p.add_argument("--r", type=float)
    p.add_argument("--S0", type=float)
    p.add_argument("--S-refugia", type=float)
    p.add_argument("--h-max", type=int)
    p.add_argument("--p-info", type=float)
    p.add_argument("--T-announce", type=int)

    # Comms / structural toggles
    p.add_argument("--no-broadcast", action="store_true")
    p.add_argument("--no-private-message", action="store_true")
    p.add_argument("--no-propose-catch", action="store_true")
    p.add_argument("--public-intent", action="store_true")
    p.add_argument("--public-catches", action="store_true")
    p.add_argument("--deliberation-turns", type=int)
    p.add_argument("--msg-char-limit", type=int)
    p.add_argument("--no-think", action="store_true",
                   help="Disable required `think` field on tools.")

    # Prompt toggles
    p.add_argument("--no-sonar", action="store_true")
    p.add_argument("--no-closure", action="store_true")
    p.add_argument("--no-breakeven", action="store_true")
    p.add_argument("--no-history", action="store_true")
    p.add_argument("--history-recent-seasons", type=int)

    # Token budget
    p.add_argument("--no-throttle", action="store_true")
    p.add_argument("--no-summarize", action="store_true")
    p.add_argument("--summarize-after-seasons", type=int)

    # Metrics
    p.add_argument("--no-judge", action="store_true",
                   help="Skip all LLM-judge metrics.")
    p.add_argument("--judge-model", type=str)
    p.add_argument("--judge-temperature", type=float)
    p.add_argument("--judge-provider", choices=["openai", "anthropic", "gemini"])
    p.add_argument("--divergence-threshold", type=int)

    # Run
    p.add_argument("--seed", type=int)
    p.add_argument("--variant", choices=["K", "S", "both"])
    p.add_argument("--output-dir", type=str)
    p.add_argument("--label", type=str)


def _collect_overrides(args: argparse.Namespace) -> dict[str, Any]:
    o: dict[str, Any] = {}
    # Provider
    if args.provider: o["provider.name"] = args.provider
    if args.model: o["provider.model"] = args.model
    if args.temperature is not None: o["provider.temperature"] = args.temperature
    if args.max_response_tokens: o["provider.max_response_tokens"] = args.max_response_tokens
    if args.tpm_limit: o["provider.tpm_limit"] = args.tpm_limit
    # Dynamics
    if args.t_seasons: o["dynamics.T"] = args.t_seasons
    if args.K is not None: o["dynamics.K"] = args.K
    if args.r is not None: o["dynamics.r"] = args.r
    if args.S0 is not None: o["dynamics.S0"] = args.S0
    if args.S_refugia is not None: o["dynamics.S_refugia"] = args.S_refugia
    if args.h_max: o["dynamics.h_max"] = args.h_max
    if args.p_info is not None: o["dynamics.p_info"] = args.p_info
    if args.T_announce: o["dynamics.T_announce"] = args.T_announce
    # Comms
    if args.no_broadcast: o["comms.allow_broadcast"] = False
    if args.no_private_message: o["comms.allow_private_message"] = False
    if args.no_propose_catch: o["comms.allow_propose_catch"] = False
    if args.public_intent: o["comms.public_intent_disclosure"] = True
    if args.public_catches: o["comms.public_catch_disclosure"] = True
    if args.deliberation_turns: o["comms.deliberation_turns"] = args.deliberation_turns
    if args.msg_char_limit: o["comms.msg_char_limit"] = args.msg_char_limit
    if args.no_think: o["comms.require_think_field"] = False
    # Prompt
    if args.no_sonar: o["prompt.include_sonar_block"] = False
    if args.no_closure: o["prompt.include_closure_block"] = False
    if args.no_breakeven: o["prompt.include_breakeven_framing"] = False
    if args.no_history: o["prompt.include_history_block"] = False
    if args.history_recent_seasons is not None:
        o["prompt.history_recent_seasons"] = args.history_recent_seasons
    # Token budget
    if args.no_throttle: o["token_budget.enable_throttle"] = False
    if args.no_summarize: o["token_budget.enable_summarization"] = False
    if args.summarize_after_seasons is not None:
        o["token_budget.summarize_after_seasons"] = args.summarize_after_seasons
    # Metrics
    if args.no_judge:
        o["metrics.enable_paired_message_consistency"] = False
        o["metrics.enable_reasoning_action_divergence"] = False
        o["metrics.enable_contextual_lie_judge"] = False
    if args.judge_model: o["metrics.judge_model"] = args.judge_model
    if args.judge_temperature is not None:
        o["metrics.judge_temperature"] = args.judge_temperature
    if args.judge_provider: o["metrics.judge_provider"] = args.judge_provider
    if args.divergence_threshold is not None:
        o["metrics.divergence_threshold"] = args.divergence_threshold
    # Run
    if args.seed is not None: o["run.seed"] = args.seed
    if args.variant: o["run.variant"] = args.variant
    if args.output_dir: o["run.output_dir"] = args.output_dir
    if args.label: o["run.label"] = args.label
    return o


def _print_summary(cfg: Config) -> None:
    print(f"=== CPR Pilot ===")
    print(f"  provider:    {cfg.provider.name} | {cfg.provider.model} | T={cfg.provider.temperature}")
    print(f"  dynamics:    K={cfg.dynamics.K} r={cfg.dynamics.r} N={cfg.n} T={cfg.dynamics.T} "
          f"refugia={cfg.dynamics.S_refugia} h_max={cfg.dynamics.h_max}")
    print(f"  comms:       broadcast={cfg.comms.allow_broadcast} "
          f"DM={cfg.comms.allow_private_message} propose={cfg.comms.allow_propose_catch} "
          f"pub_intent={cfg.comms.public_intent_disclosure} "
          f"pub_catches={cfg.comms.public_catch_disclosure}")
    print(f"  captains:    " + ", ".join(f"{c.name}({int(c.breakeven_total)}t)" for c in cfg.captains))
    print(f"  variant:     {cfg.run.variant} | seed={cfg.run.seed}")


def cmd_run(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    cfg = apply_overrides(cfg, _collect_overrides(args))
    _print_summary(cfg)
    run_single(cfg)
    return 0


def cmd_sweep(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    cfg = apply_overrides(cfg, _collect_overrides(args))
    seeds = [int(s) for s in args.seeds.split(",")]
    _print_summary(cfg)
    print(f"  seeds:       {seeds}")
    run_sweep(cfg, seeds)
    return 0


def cmd_score(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    cfg = apply_overrides(cfg, _collect_overrides(args))
    from .providers import make_provider
    judge = None if args.no_judge else make_provider(cfg.metrics.judge_provider)
    report = score_run(args.run_dir, cfg, judge_provider=judge)
    print(f"Scored {args.run_dir}")
    print(f"  metrics: {list(report['metrics'].keys())}")
    return 0


def main() -> None:
    ap = argparse.ArgumentParser(prog="cpr-pilot")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="Single run.")
    p_run.add_argument("--config", required=True, type=str, help="YAML config path.")
    _add_overrides(p_run)
    p_run.set_defaults(func=cmd_run)

    p_sw = sub.add_parser("sweep", help="Seed sweep.")
    p_sw.add_argument("--config", required=True, type=str)
    p_sw.add_argument("--seeds", required=True, type=str,
                      help="Comma-separated, e.g. '1,7,42,100,314'.")
    _add_overrides(p_sw)
    p_sw.set_defaults(func=cmd_sweep)

    p_sc = sub.add_parser("score", help="Re-score an existing run dir.")
    p_sc.add_argument("--config", required=True, type=str)
    p_sc.add_argument("--run-dir", required=True, type=str)
    _add_overrides(p_sc)
    p_sc.set_defaults(func=cmd_score)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
