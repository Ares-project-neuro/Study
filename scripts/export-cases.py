"""Refresh the static demo catalog after editing the Python teaching dossiers."""
import json
import sys
from pathlib import Path
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
from app.cases import templates, ACTIONS, RUBRIC, THRESHOLDS
from app.main import case_options

with (root/'browser/cases.json').open('w', encoding='utf-8') as file:
    json.dump({'templates': templates(), 'actions': ACTIONS, 'rubric': RUBRIC,
               'thresholds': THRESHOLDS, 'scoring': case_options()['scoring']}, file, ensure_ascii=False, indent=2)
