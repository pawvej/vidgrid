"""Enable `python3 -m vidgrid` as a fallback when the console script is
not on PATH."""

from vidgrid.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
