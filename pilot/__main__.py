if __package__ in (None, ""):
    # Invoked as a path (`python pilot/__main__.py` or `uv run pilot/__main__.py`).
    # Re-route through the package so relative imports resolve.
    import os
    import runpy
    import sys

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    runpy.run_module("pilot", run_name="__main__")
else:
    from .cli import main

    if __name__ == "__main__":
        main()
