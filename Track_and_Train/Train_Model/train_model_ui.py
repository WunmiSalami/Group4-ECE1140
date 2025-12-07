import os, json, time, tkinter as tk
from tkinter import ttk
import threading
import sys
import importlib, importlib.util

import os

BASE_DIR = os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))
)  # Track_and_Train
TRACK_MODEL_DIR = os.path.join(BASE_DIR, "Track_Model")
TRAIN_MODEL_DIR = os.path.join(BASE_DIR, "Train_Model")

# Track JSONs
STATIC_JSON_PATH = os.path.join(TRACK_MODEL_DIR, "track_model_static.json")
CONTROLLER_JSON_PATH = os.path.join(
    TRACK_MODEL_DIR, "track_model_Track_controller.json"
)

# Train JSONs
TRAIN_DATA_PATH = os.path.join(TRAIN_MODEL_DIR, "train_data.json")

# Import core logic
from train_model_core import (
    TRAIN_STATES_FILE,
    TRAIN_DATA_FILE,
    TRACK_INPUT_FILE,
    TrainModel,
    safe_read_json,
    safe_write_json,
    ensure_train_data,
    read_track_input,
    merge_inputs,
    update_track_motion,
    DEFAULT_SPECS,
    compute_passengers_disembarking,
)

os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Remove the direct "import requests" and use dynamic import instead
try:
    requests = (
        importlib.import_module("requests")
        if importlib.util.find_spec("requests")
        else None
    )
except Exception:
    requests = None


class TrainModelUI(ttk.Frame):
    def __init__(self, parent, train_id=None, server_url=None):
        super().__init__(parent)
        self.pack(fill="both", expand=True)

        # Configure narrower window
        self.config(width=350)
        self.pack_propagate(False)

        self.train_id = train_id
        self.server_url = server_url
        self.train_data_path = TRAIN_DATA_FILE

        style = ttk.Style(self)
        try:
            style.theme_use("vista")
        except Exception:
            style.theme_use("clam")
        style.configure("Header.TLabelframe", font=("Segoe UI", 10, "bold"))
        style.configure("Data.TLabel", font=("Consolas", 9))
        style.configure("Status.On.TLabel", foreground="#0a7d12")
        style.configure("Status.Off.TLabel", foreground="#b00")

        td = ensure_train_data(self.train_data_path)
        if self.train_id is not None and f"train_{self.train_id}" in td:
            self.specs = td[f"train_{self.train_id}"].get(
                "specs", td.get("specs", DEFAULT_SPECS)
            )
        else:
            self.specs = td.get("specs", DEFAULT_SPECS)

        self.model = TrainModel(self.specs)
        self._last_disembark_state = {"station": None, "count": 0}
        self._last_beacon_inputs = {}
        self._stop_event = threading.Event()
        self._last_mtimes = {"track": 0.0, "ctrl": 0.0, "train_data": 0.0}
        threading.Thread(target=self._watch_files, daemon=True).start()

        # Single column layout
        main_container = ttk.Frame(self)
        main_container.pack(fill="both", expand=True, padx=6, pady=6)

        # Build panels vertically
        self.create_info_panel(main_container)
        self.create_doors_panel(main_container)
        self.create_specs_panel(main_container)
        self.create_failure_panel(main_container)
        self.create_announcements_panel(main_container)

        self.update_loop()

    def create_info_panel(self, parent):
        frame = ttk.LabelFrame(parent, text="Dynamics", style="Header.TLabelframe")
        frame.pack(fill="x", padx=4, pady=4)

        self.info_labels = {}
        fields = [
            "Velocity (mph)",
            "Acceleration (ft/s²)",
            "Position (yds)",
            "Authority Remaining (yds)",
            "Current Station",
            "Next Station",
            "Speed Limit (mph)",
        ]
        for i, key in enumerate(fields):
            row_frame = ttk.Frame(frame)
            row_frame.pack(fill="x", padx=8, pady=2)

            ttk.Label(row_frame, text=key + ":", style="Data.TLabel", width=25).pack(
                side="left"
            )
            lbl = ttk.Label(row_frame, text="--", style="Data.TLabel")
            lbl.pack(side="left", padx=4)
            self.info_labels[key] = lbl

    def create_doors_panel(self, parent):
        frame = ttk.LabelFrame(parent, text="Doors", style="Header.TLabelframe")
        frame.pack(fill="x", padx=4, pady=4)

        self.env_labels = {}
        for key in ["Left Door", "Right Door"]:
            row_frame = ttk.Frame(frame)
            row_frame.pack(fill="x", padx=8, pady=2)

            ttk.Label(row_frame, text=key + ":", style="Data.TLabel", width=25).pack(
                side="left"
            )
            lbl = ttk.Label(row_frame, text="--", style="Data.TLabel")
            lbl.pack(side="left", padx=4)
            self.env_labels[key] = lbl

    def create_specs_panel(self, parent):
        frame = ttk.LabelFrame(parent, text="Specs", style="Header.TLabelframe")
        frame.pack(fill="x", padx=4, pady=4)

        # Only show capacity and crew_count
        ttk.Label(
            frame,
            text=f"Capacity: {self.specs.get('capacity', 222)}",
            style="Data.TLabel",
        ).pack(anchor="w", padx=8, pady=2)

        ttk.Label(
            frame,
            text=f"Crew Count: {self.specs.get('crew_count', 2)}",
            style="Data.TLabel",
        ).pack(anchor="w", padx=8, pady=2)

    def create_failure_panel(self, parent):
        frame = ttk.LabelFrame(parent, text="Failures", style="Header.TLabelframe")
        frame.pack(fill="x", padx=4, pady=4)

        self.fail_labels = {}
        failures = [
            ("Engine Failure", self.toggle_engine_failure),
            ("Brake Failure", self.toggle_brake_failure),
            ("Signal Failure", self.toggle_signal_failure),
            ("Emergency Brake", self.toggle_emergency_brake),
        ]

        for key, command in failures:
            row_frame = ttk.Frame(frame)
            row_frame.pack(fill="x", padx=6, pady=2)

            ttk.Label(row_frame, text=key + ":", style="Data.TLabel", width=18).pack(
                side="left"
            )
            lbl = ttk.Label(row_frame, text="Off", style="Status.Off.TLabel", width=5)
            lbl.pack(side="left", padx=4)
            self.fail_labels[key] = lbl

            ttk.Button(row_frame, text="Toggle", command=command, width=8).pack(
                side="right", padx=4
            )

    def create_announcements_panel(self, parent):
        frame = ttk.LabelFrame(parent, text="Announcements", style="Header.TLabelframe")
        frame.pack(fill="both", expand=True, padx=4, pady=4)

        self.announcement_box = tk.Text(
            frame, height=4, wrap="word", state="disabled", bg="white"
        )
        self.announcement_box.pack(fill="both", expand=True, padx=6, pady=6)

    # === Flag toggles (unchanged semantics) ===
    def toggle_emergency_brake(self):
        self._toggle_flag("emergency_brake")

    def toggle_engine_failure(self):
        self._toggle_flag("engine_failure")

    def toggle_brake_failure(self):
        self._toggle_flag("brake_failure")

    def toggle_signal_failure(self):
        self._toggle_flag("signal_failure")

    def _toggle_flag(self, flag_name: str):
        flag_map = {
            "engine_failure": "train_model_engine_failure",
            "brake_failure": "train_model_brake_failure",
            "signal_failure": "train_model_signal_failure",
        }
        if flag_name == "emergency_brake":
            all_states = safe_read_json(TRAIN_STATES_FILE)
            if self.train_id is None:
                current = bool(all_states.get(flag_name, False))
                all_states[flag_name] = not current
                new_val = all_states[flag_name]
            else:
                key = f"train_{self.train_id}"
                sect = all_states.get(key, {})
                current = bool(sect.get(flag_name, False))
                sect[flag_name] = not current
                all_states[key] = sect
                new_val = sect[flag_name]
            safe_write_json(TRAIN_STATES_FILE, all_states)
        else:
            train_data = safe_read_json(self.train_data_path)
            if not isinstance(train_data, dict):
                train_data = {}
            mapped_flag = flag_map.get(flag_name, flag_name)
            if self.train_id is None:
                if "inputs" not in train_data:
                    train_data["inputs"] = {}
                inputs = train_data["inputs"]
                current = bool(inputs.get(mapped_flag, False))
                inputs[mapped_flag] = not current
                new_val = inputs[mapped_flag]
            else:
                key = f"train_{self.train_id}"
                if key not in train_data:
                    train_data[key] = {}
                sect = train_data[key]
                if "inputs" not in sect:
                    sect["inputs"] = {}
                inputs = sect["inputs"]
                current = bool(inputs.get(mapped_flag, False))
                inputs[mapped_flag] = not current
                sect["inputs"] = inputs
                train_data[key] = sect
                new_val = inputs[mapped_flag]
            safe_write_json(self.train_data_path, train_data)

        key_map = {
            "engine_failure": "Engine Failure",
            "brake_failure": "Brake Failure",
            "signal_failure": "Signal Failure",
            "emergency_brake": "Emergency Brake",
        }
        ui_key = key_map.get(flag_name)
        if ui_key and ui_key in self.fail_labels:
            self.fail_labels[ui_key].config(
                text="On" if new_val else "Off",
                style="Status.On.TLabel" if new_val else "Status.Off.TLabel",
            )
        self.after(50, lambda: self._run_cycle(schedule=False))

    # === Controller state IO ===
    def get_train_state(self):
        all_states = safe_read_json(TRAIN_STATES_FILE)
        if self.train_id is None:
            return all_states
        return all_states.get(f"train_{self.train_id}", {})

    def update_train_state(self, updates: dict):
        # Remote mode: only if requests is available
        if self.server_url and self.train_id is not None and requests is not None:
            try:
                response = requests.post(
                    f"{self.server_url}/api/train/{self.train_id}/state",
                    json=updates,
                    timeout=2.0,
                )
                if response.status_code != 200:
                    print(
                        f"[Train Model] Server update returned {response.status_code}"
                    )
            except Exception as e:
                print(f"[Train Model] Error updating state on server: {e}")
            return

        # Local mode: write to file
        all_states = safe_read_json(TRAIN_STATES_FILE)
        if self.train_id is None:
            all_states.update(updates)
        else:
            key = f"train_{self.train_id}"
            cur = all_states.get(key, {})
            cur.update(updates)
            all_states[key] = cur
        safe_write_json(TRAIN_STATES_FILE, all_states)

    def write_train_data(self, specs, inputs, td_inputs):
        data = safe_read_json(self.train_data_path)
        if not isinstance(data, dict):
            data = {}
        data.setdefault("specs", data.get("specs", self.specs))
        data.setdefault("inputs", data.get("inputs", {}))
        data.setdefault("outputs", data.get("outputs", {}))
        outputs = {
            "velocity_mph": self.model.velocity_mph,
            "acceleration_ftps2": self.model.acceleration_ftps2,
            "position_yds": self.model.position_yds,
            "authority_yds": self.model.authority_yds,
        }
        if self.train_id is None:
            current_inputs = data.get("inputs", {})
            for flag in [
                "train_model_engine_failure",
                "train_model_signal_failure",
                "train_model_brake_failure",
            ]:
                if flag in current_inputs:
                    td_inputs[flag] = current_inputs[flag]
            data["specs"] = specs
            data["inputs"] = td_inputs
            data["outputs"] = outputs
        else:
            key = f"train_{self.train_id}"
            if key not in data:
                data[key] = {}
            current_inputs = data.get(key, {}).get("inputs", {})
            for flag in [
                "train_model_engine_failure",
                "train_model_signal_failure",
                "train_model_brake_failure",
            ]:
                if flag in current_inputs:
                    td_inputs[flag] = current_inputs[flag]
            data[key]["specs"] = specs
            data[key]["inputs"] = td_inputs
            data[key]["outputs"] = outputs
        safe_write_json(self.train_data_path, data)

    def update_loop(self):
        self._run_cycle(schedule=True)

    def _run_cycle(self, schedule: bool):
        td = ensure_train_data(self.train_data_path)
        ctrl = self.get_train_state()
        idx = max(((self.train_id or 1) - 1), 0)
        track_in = read_track_input(idx)

        if self.train_id is not None and f"train_{self.train_id}" in td:
            td_inputs_check = td[f"train_{self.train_id}"].get("inputs", {})
        else:
            td_inputs_check = td.get("inputs", {})

        signal_failure_active = td_inputs_check.get("train_model_signal_failure", False)
        beacon_read_blocked = False

        beacon_source = {}
        for k in [
            "speed limit",
            "side_door",
            "current station",
            "next station",
            "passengers_boarding",
        ]:
            if k in track_in:
                beacon_source[k] = track_in[k]
            elif k in td_inputs_check:
                beacon_source[k] = td_inputs_check[k]

        if signal_failure_active:
            beacon_changed = any(
                k in beacon_source
                and k in self._last_beacon_inputs
                and beacon_source[k] != self._last_beacon_inputs[k]
                for k in ["speed limit", "side_door", "current station", "next station"]
            )
            if beacon_changed:
                beacon_read_blocked = True
                for k in [
                    "speed limit",
                    "side_door",
                    "current station",
                    "next station",
                    "passengers_boarding",
                ]:
                    if k in self._last_beacon_inputs:
                        track_in[k] = self._last_beacon_inputs[k]
            else:
                for k in [
                    "speed limit",
                    "side_door",
                    "current station",
                    "next station",
                    "passengers_boarding",
                ]:
                    if k in beacon_source:
                        self._last_beacon_inputs[k] = beacon_source[k]
        else:
            for k in [
                "speed limit",
                "side_door",
                "current station",
                "next station",
                "passengers_boarding",
            ]:
                if k in beacon_source:
                    self._last_beacon_inputs[k] = beacon_source[k]

        if self.train_id is not None and f"train_{self.train_id}" in td:
            td_section = td[f"train_{self.train_id}"]
            td_inputs = td_section.get("inputs", td.get("inputs", {}))
            specs_for_write = td_section.get("specs", td.get("specs", DEFAULT_SPECS))
        else:
            td_inputs = td.get("inputs", {})
            specs_for_write = td.get("specs", DEFAULT_SPECS)

        onboard_fallback = td_inputs.get("passengers_onboard", 0)
        merged_inputs = merge_inputs(td_inputs, track_in, ctrl, onboard_fallback)

        outputs = self.model.update(
            commanded_speed=merged_inputs.get("commanded speed", 0.0),
            commanded_authority=merged_inputs.get("commanded authority", 0.0),
            speed_limit=merged_inputs.get("speed limit", 0.0),
            current_station=merged_inputs.get("current station", ""),
            next_station=merged_inputs.get("next station", ""),
            side_door=merged_inputs.get("side_door", ""),
            power_command=ctrl.get("power_command", 0.0),
            emergency_brake=ctrl.get("emergency_brake", False),
            service_brake=ctrl.get("service_brake", False),
            engine_failure=merged_inputs.get("train_model_engine_failure", False),
            brake_failure=merged_inputs.get("train_model_brake_failure", False),
            left_door=ctrl.get("left_door", False),
            right_door=ctrl.get("right_door", False),
            driver_velocity=ctrl.get("driver_velocity", 0.0),
        )

        passengers_onboard = int(merged_inputs.get("passengers_onboard", 0))
        disembarking, self._last_disembark_state = compute_passengers_disembarking(
            self._last_disembark_state,
            outputs["station_name"],
            outputs["velocity_mph"],
            passengers_onboard,
            self.model.crew_count,
        )

        update_track_motion(
            idx,
            outputs["acceleration_ftps2"],
            outputs["velocity_mph"],
        )

        self.write_train_data(specs_for_write, merged_inputs, td_inputs)

        remaining_authority = outputs["authority_yds"]

        if signal_failure_active and self._last_beacon_inputs:
            controller_updates = {
                "train_velocity": outputs["velocity_mph"],
                "commanded_authority": remaining_authority,
                "current_station": self._last_beacon_inputs.get("current station", ""),
                "next_stop": self._last_beacon_inputs.get("next station", ""),
                "station_side": self._last_beacon_inputs.get("side_door", ""),
                "beacon_read_blocked": beacon_read_blocked,
            }
        else:
            controller_updates = {
                "train_velocity": outputs["velocity_mph"],
                "commanded_authority": remaining_authority,
                "current_station": merged_inputs.get("current station", ""),
                "next_stop": merged_inputs.get("next station", ""),
                "station_side": merged_inputs.get("side_door", ""),
                "beacon_read_blocked": beacon_read_blocked,
            }
        self.update_train_state(controller_updates)

        self._update_ui(outputs, ctrl, merged_inputs, disembarking)
        if schedule:
            self.after(int(self.model.dt * 1000), self.update_loop)

    def _update_ui(self, outputs, ctrl, merged_inputs, disembarking):
        self.info_labels["Velocity (mph)"].config(text=f"{outputs['velocity_mph']:.2f}")
        self.info_labels["Acceleration (ft/s²)"].config(
            text=f"{outputs['acceleration_ftps2']:.2f}"
        )
        self.info_labels["Position (yds)"].config(text=f"{outputs['position_yds']:.1f}")
        self.info_labels["Authority Remaining (yds)"].config(
            text=f"{outputs['authority_yds']:.1f}"
        )
        self.info_labels["Current Station"].config(
            text=f"{outputs['station_name'] or ''}"
        )
        self.info_labels["Next Station"].config(text=f"{outputs['next_station'] or ''}")
        self.info_labels["Speed Limit (mph)"].config(
            text=f"{merged_inputs.get('speed limit', 0.0):.0f}"
        )

        def door_style(open_):
            return "Status.On.TLabel" if open_ else "Status.Off.TLabel"

        self.env_labels["Left Door"].config(
            text="Open" if outputs["left_door_open"] else "Closed",
            style=door_style(outputs["left_door_open"]),
        )
        self.env_labels["Right Door"].config(
            text="Open" if outputs["right_door_open"] else "Closed",
            style=door_style(outputs["right_door_open"]),
        )

        def set_flag(lbl_key, on):
            self.fail_labels[lbl_key].config(
                text="On" if on else "Off",
                style="Status.On.TLabel" if on else "Status.Off.TLabel",
            )

        set_flag(
            "Engine Failure",
            bool(merged_inputs.get("train_model_engine_failure", False)),
        )
        set_flag(
            "Brake Failure", bool(merged_inputs.get("train_model_brake_failure", False))
        )
        set_flag(
            "Signal Failure",
            bool(merged_inputs.get("train_model_signal_failure", False)),
        )
        set_flag("Emergency Brake", bool(ctrl.get("emergency_brake", False)))

        try:
            self.announcement_box.config(state="normal")
            self.announcement_box.delete("1.0", "end")
            announcement = ctrl.get("announcement", "")
            if announcement:
                self.announcement_box.insert("1.0", announcement)
            else:
                self.announcement_box.insert(
                    "1.0", f"Running\nDisembark: {disembarking}"
                )
            self.announcement_box.config(state="disabled")
        except Exception:
            pass

    def _watch_files(self):
        paths = {
            "track": os.path.abspath(TRACK_INPUT_FILE),
            "ctrl": os.path.abspath(TRAIN_STATES_FILE),
            "train_data": os.path.abspath(self.train_data_path),
        }
        while not self._stop_event.is_set():
            try:
                changed = False
                for key, p in paths.items():
                    mt = os.path.getmtime(p) if os.path.exists(p) else 0.0
                    if mt != self._last_mtimes.get(key, 0.0):
                        self._last_mtimes[key] = mt
                        changed = True
                if changed:
                    self.after(1, lambda: self._run_cycle(schedule=False))
            except Exception:
                pass
            time.sleep(0.2)

    def on_close(self):
        self._stop_event.set()
        self.destroy()
