"""
run_all.py: runs the whole pipeline, start to finish.

    1. generate_data.py     synthetic data  -> data/*.csv
    2. load_database.py     CSVs            -> data/scorecard.db
    3. calculate_metrics.py SQL metrics     -> views + output/metrics/*.csv
    4. write_summary.py     findings        -> output/findings_summary.md
    5. build_dashboard.py   dashboard       -> output/dashboard.html

Run from the project folder:   python run_all.py
Then open output/dashboard.html in a browser.
"""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STEPS = ["generate_data", "load_database", "calculate_metrics", "write_summary", "build_dashboard"]

for number, name in enumerate(STEPS, start=1):
    print(f"\n=== Step {number} of {len(STEPS)}: {name}.py ===")
    spec = importlib.util.spec_from_file_location(name, ROOT / "src" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.main()

print(f"\nDone. Open {ROOT / 'output' / 'dashboard.html'} in a browser.")
