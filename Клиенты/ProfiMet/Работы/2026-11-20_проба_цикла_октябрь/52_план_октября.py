import sys, os
sys.stdout.reconfigure(encoding="utf-8")
root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(root, "Скрипты"))
import pandas as pd, yaml
from _config import client_stats_dir
path = client_stats_dir("ProfiMet").parent / "analysis_config.yaml"
cfg = yaml.safe_load(path.read_text(encoding="utf-8"))
from campaign_analyzer.sources import read_plan
for first in ("2026-10-01", "2026-11-01"):
    print(first, read_plan(cfg, pd.Timestamp(first)))
