"""Isolated private-package entry. Never import project code from the working directory."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / "app"))
from experiment_lab.cli import main

raise SystemExit(main())
