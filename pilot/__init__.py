"""CPR pilot — coastal fishing cooperative cover story.

Two games (Variant K and Variant S) of a 3-captain CPR game on GPT-4.1.
See coding.md and game_spec.md for design.
"""

from .config import Params, CAPTAINS
from .game import run_game
from .metrics import compute_metrics, print_metrics, print_side_by_side

__all__ = [
    "Params",
    "CAPTAINS",
    "run_game",
    "compute_metrics",
    "print_metrics",
    "print_side_by_side",
]
