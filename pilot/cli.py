"""Entry point: `python -m pilot` or `python pilot.py`."""

from __future__ import annotations

import argparse
import random

from .client import make_client
from .config import Params
from .game import run_game
from .metrics import compute_metrics, print_metrics, print_side_by_side


def main() -> None:
    ap = argparse.ArgumentParser(description="CPR pilot — coastal fishing cooperative.")
    ap.add_argument("--variant", choices=["K", "S", "both"], default="both")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--model", type=str, default="gpt-4.1")
    # Public-channel comms toggle. Default mirrors Params.allow_broadcast=True.
    ap.add_argument(
        "--no-broadcast",
        action="store_true",
        help="Drop the open-channel `broadcast` tool. Captains can still privately "
             "DM one peer or state an intended catch on the open channel; only the "
             "free-form public radio is removed.",
    )
    ap.add_argument(
        "--no-public-catches",
        action="store_true",
        help="Hide per-captain catches and the combined total from the end-of-season "
             "disclosure and the public-history block. Captains see only S_pre and S_post. "
             "Engine state still records every catch for metrics + dynamics.",
    )
    ap.add_argument(
        "--public-intents",
        action="store_true",
        help="Make propose_catch intended catches audible to the other captains. By default, "
             "intended catches are engine-private and only logged for state/metrics.",
    )
    args = ap.parse_args()

    seed = args.seed if args.seed is not None else random.randint(1, 10_000_000)
    params = Params(
        model=args.model,
        allow_broadcast=not args.no_broadcast,
        public_catch_disclosure=not args.no_public_catches,
        public_intent_disclosure=args.public_intents,
    )
    print(
        f"Pilot run | model={params.model} | seed={seed} | variant={args.variant} | "
        f"broadcast={'on' if params.allow_broadcast else 'off'} | "
        f"public_catches={'on' if params.public_catch_disclosure else 'off'} | "
        f"public_intents={'on' if params.public_intent_disclosure else 'off'}"
    )

    client = make_client()

    runs: list[tuple[str, str, str]] = []
    if args.variant in ("K", "both"):
        tp, sp = run_game("K", seed, params, client)
        runs.append(("K", tp, sp))
    if args.variant in ("S", "both"):
        # Different seed for the S game so insider draw / signal draw differ; recorded separately.
        seed_S = seed + 1
        tp, sp = run_game("S", seed_S, params, client)
        runs.append(("S", tp, sp))

    metrics_by_variant: dict[str, dict] = {}
    for variant, tp, sp in runs:
        judge_client = client if params.use_judge_llm else None
        m = compute_metrics(tp, sp, params, client=judge_client)
        metrics_by_variant[variant] = m
        print_metrics(m)

    if "K" in metrics_by_variant and "S" in metrics_by_variant:
        print_side_by_side(metrics_by_variant["K"], metrics_by_variant["S"])
