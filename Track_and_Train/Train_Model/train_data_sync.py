import json
import os
from typing import Dict

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TRAIN_DATA_FILE = os.path.join(BASE_DIR, "train_data.json")
TRAIN_STATES_FILE = os.path.join(BASE_DIR, "../train_controller/data/train_states.json")


def _safe_read(path: str) -> Dict:
    try:
        with open(path, "r") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _safe_write(path: str, data: Dict):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=4)
    os.replace(tmp, path)


def sync_train_data():
    """
    Synchronize train_data.json inputs with per-train sections in train_states.json.
    Supports both legacy single-train (flat keys) and new multi-train train_{id} entries.
    Robust against malformed entries (e.g. train_# mapping to a scalar).
    """
    train_data = _safe_read(TRAIN_DATA_FILE)
    states = _safe_read(TRAIN_STATES_FILE)

    # Ensure top-level specs exist (do not overwrite existing)
    if "specs" not in train_data:
        train_data["specs"] = {
            "length_ft": 66.0,
            "width_ft": 10.0,
            "height_ft": 11.5,
            "mass_lbs": 90100,
            "max_power_hp": 169,
            "max_accel_ftps2": 1.64,
            "service_brake_ftps2": -3.94,
            "emergency_brake_ftps2": -8.86,
            "capacity": 222,
            "crew_count": 2,
        }

    # Detect multi-train format (only keep dict-valued train_* entries)
    multi_keys = [
        k for k, v in states.items() if k.startswith("train_") and isinstance(v, dict)
    ]

    if multi_keys:
        for k in multi_keys:
            s = states.get(k, {})
            if not isinstance(s, dict):
                continue  # skip malformed
            if k not in train_data:
                train_data[k] = {"inputs": {}, "outputs": {}}
            inputs = train_data[k].get("inputs", {})
            # Preserve existing passengers_boarding if already set
            passengers_boarding_existing = inputs.get("passengers_boarding", 0)
            inputs.update(
                {
                    "commanded speed": s.get("commanded_speed", 0.0),
                    "commanded authority": s.get("commanded_authority", 0.0),
                    "speed limit": s.get("speed_limit", 0.0),
                    "side_door": s.get("station_side", ""),
                    "current station": s.get("current_station", s.get("next_stop", "")),
                    "next station": s.get("next_stop", ""),
                    "passengers_boarding": passengers_boarding_existing,
                    "train_model_engine_failure": s.get(
                        "train_model_engine_failure", False
                    ),
                    "train_model_signal_failure": s.get(
                        "train_model_signal_failure", False
                    ),
                    "train_model_brake_failure": s.get(
                        "train_model_brake_failure", False
                    ),
                    "emergency_brake": s.get("emergency_brake", False),
                }
            )
            train_data[k]["inputs"] = inputs
    else:
        # Legacy single-train structure
        inputs = train_data.get("inputs", {})
        inputs.update(
            {
                "commanded speed": states.get("commanded_speed", 0.0),
                "commanded authority": states.get("commanded_authority", 0.0),
                "speed limit": states.get("speed_limit", 30.0),
                "side_door": states.get("station_side", "Right"),
                "current station": states.get(
                    "current_station", states.get("next_stop", "Unknown")
                ),
                "next station": states.get("next_stop", "Unknown"),
                "train_model_engine_failure": states.get(
                    "train_model_engine_failure", False
                ),
                "train_model_signal_failure": states.get(
                    "train_model_signal_failure", False
                ),
                "train_model_brake_failure": states.get(
                    "train_model_brake_failure", False
                ),
                "emergency_brake": states.get("emergency_brake", False),
            }
        )
        train_data["inputs"] = inputs

    _safe_write(TRAIN_DATA_FILE, train_data)


if __name__ == "__main__":
    sync_train_data()

{
    "templates": [
        {"id": 1, "speed": 0, "mass": 40000, "...": "..."},
        {"id": 2, "speed": 0, "mass": 42000, "...": "..."},
        {"id": 3, "...": "..."},
    ],
    "beacons": [{"block": 12, "data": "..."}, {"block": 13, "data": "..."}],
    "trainStates": {
        "train1": {"templateId": 1, "speed": 0, "mass": 40000, "...": "..."},
        "train2": {"templateId": 2, "speed": 0, "mass": 42000, "...": "..."},
    },
}
