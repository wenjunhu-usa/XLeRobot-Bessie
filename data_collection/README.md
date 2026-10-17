# XLeRobot data collection

The web controller records model-neutral episodes into `../collected_data/raw`.
Each completed episode contains `left.mp4`, `right.mp4`, `frames.jsonl`, and
`episode.json`. State is measured joint position; action is the commanded joint
target. Both use the joint order stored in `episode.json`.

Export completed episodes to GR00T-compatible LeRobot v2:

```bash
./.venv/bin/python data_collection/export_lerobot_v2.py
```

The export includes `meta/modality.json`, so it can be used by GR00T. Keep the
raw directory as the source of truth when producing future LeRobot/SmolVLA
formats. Failed episodes remain in raw storage for analysis and are excluded
from export by default. Pass `--include-failures` only when a training recipe
explicitly uses failure demonstrations.
