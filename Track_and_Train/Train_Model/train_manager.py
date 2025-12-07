"""Train Manager Module - Consolidated Version

Manages multiple trains with TrainModel and train_controller instances.
All state management, controller logic, and UI consolidated in one file.
"""

import os
import sys
import json
import time
import tkinter as tk
from tkinter import ttk
import threading

# Paths
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
train_model_dir = os.path.join(parent_dir, "Train_Model")
sys.path.extend([current_dir, parent_dir, train_model_dir])

_file_lock = threading.Lock()


def safe_read_json(path: str) -> dict:
    try:
        with open(path, "r") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def safe_write_json(path: str, data: dict):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(f"Error writing JSON: {e}")


class beacon:
    def __init__(self, next_stop: str = "", station_side: str = ""):
        self.next_stop = next_stop
        self.station_side = station_side

    def update_from_state(self, state: dict):
        self.next_stop = state.get("next_stop", "")
        self.station_side = state.get("station_side", "")


class commanded_speed_authority:
    def __init__(self, commanded_speed: int = 0, commanded_authority: int = 0):
        self.commanded_speed = commanded_speed
        self.commanded_authority = commanded_authority

    def update_from_state(self, state: dict):
        self.commanded_speed = int(state.get("commanded_speed", 0))
        self.commanded_authority = int(state.get("commanded_authority", 0))


class vital_train_controls:
    def __init__(
        self,
        kp=0.0,
        ki=0.0,
        train_velocity=0.0,
        driver_velocity=0.0,
        emergency_brake=False,
        service_brake=False,
        power_command=0.0,
        commanded_authority=0.0,
        speed_limit=0.0,
    ):
        self.kp = kp
        self.ki = ki
        self.train_velocity = train_velocity
        self.driver_velocity = driver_velocity
        self.emergency_brake = emergency_brake
        self.service_brake = service_brake
        self.power_command = power_command
        self.commanded_authority = commanded_authority
        self.speed_limit = speed_limit

    def calculate_power_command(self, accumulated_error, last_update_time):
        speed_error = self.driver_velocity - self.train_velocity
        if speed_error <= 0.01:
            return (0.0, 0.0, time.time())

        current_time = time.time()
        dt = max(0.001, min(current_time - last_update_time, 1.0))

        new_accumulated_error = accumulated_error + speed_error * dt
        max_integral = 120000 / self.ki if self.ki != 0 else 0
        new_accumulated_error = max(
            -max_integral, min(max_integral, new_accumulated_error)
        )

        proportional = self.kp * speed_error
        integral = self.ki * new_accumulated_error
        power = max(0, min(proportional + integral, 120000))

        if power == 120000 and integral > 0:
            new_accumulated_error = (
                (120000 - proportional) / self.ki if self.ki != 0 else 0
            )
        elif power == 0 and integral < 0:
            new_accumulated_error = -proportional / self.ki if self.ki != 0 else 0

        return (power, new_accumulated_error, current_time)


class vital_validator_first_check:
    def validate(self, v):
        if v.speed_limit > 0 and v.train_velocity > v.speed_limit:
            return False
        if v.power_command < 0 or v.power_command > 120000:
            return False
        if v.service_brake and v.emergency_brake:
            return False
        if v.commanded_authority <= 0 and v.power_command > 0:
            return False
        return True


class vital_validator_second_check:
    def validate(self, v):
        if v.speed_limit > 0 and v.train_velocity > v.speed_limit * 1.02:
            return False
        if v.service_brake and v.emergency_brake:
            return False
        return v.commanded_authority > 0 or v.power_command == 0


class train_controller:
    def __init__(self, train_id: int, state_file: str):
        self.train_id = train_id
        self.state_file = state_file
        self._accumulated_error = 0.0
        self._last_update_time = time.time()
        self.beacon_info = beacon()
        self.cmd_speed_auth = commanded_speed_authority()
        self.validators = [
            vital_validator_first_check(),
            vital_validator_second_check(),
        ]

    def get_state(self):
        with _file_lock:
            all_states = safe_read_json(self.state_file)
            return all_states.get(f"train_{self.train_id}", {})

    def update_state(self, updates: dict):
        with _file_lock:
            all_states = safe_read_json(self.state_file)
            train_key = f"train_{self.train_id}"
            if train_key not in all_states:
                all_states[train_key] = {}
            all_states[train_key].update(updates)
            safe_write_json(self.state_file, all_states)

    def update_from_train_model(self):
        track_model_file = os.path.join(parent_dir, "track_model_Train_Model.json")
        track_data = safe_read_json(track_model_file)
        train_key = f"G_train_{self.train_id}"

        if train_key in track_data:
            block = track_data[train_key].get("block", {})
            beacon = track_data[train_key].get("beacon", {})

            self.update_state(
                {
                    "commanded_speed": float(block.get("commanded speed", 0.0) or 0.0),
                    "commanded_authority": float(
                        block.get("commanded authority", 0.0) or 0.0
                    ),
                    "speed_limit": float(beacon.get("speed limit", 0.0) or 0.0),
                    "next_stop": beacon.get("next station", "") or "",
                    "station_side": beacon.get("side_door", "") or "",
                }
            )

        state = self.get_state()
        self.beacon_info.update_from_state(state)
        self.cmd_speed_auth.update_from_state(state)

    def vital_control_check_and_update(self, changes: dict):
        state = self.get_state().copy()
        candidate = vital_train_controls(
            kp=changes.get("kp", state.get("kp", 0.0)),
            ki=changes.get("ki", state.get("ki", 0.0)),
            train_velocity=changes.get(
                "train_velocity", state.get("train_velocity", 0.0)
            ),
            driver_velocity=changes.get(
                "driver_velocity", state.get("driver_velocity", 0.0)
            ),
            emergency_brake=changes.get(
                "emergency_brake", state.get("emergency_brake", False)
            ),
            service_brake=changes.get("service_brake", state.get("service_brake", 0)),
            power_command=changes.get("power_command", state.get("power_command", 0.0)),
            commanded_authority=changes.get(
                "commanded_authority", state.get("commanded_authority", 0.0)
            ),
            speed_limit=changes.get("speed_limit", state.get("speed_limit", 0.0)),
        )

        for validator in self.validators:
            if not validator.validate(candidate):
                return False

        self.update_state(changes)
        return True

    def calculate_power_command(self, state: dict):
        controls = vital_train_controls(
            kp=state["kp"],
            ki=state["ki"],
            train_velocity=state["train_velocity"],
            driver_velocity=state["driver_velocity"],
            emergency_brake=state["emergency_brake"],
            service_brake=state["service_brake"],
            power_command=state["power_command"],
            commanded_authority=state["commanded_authority"],
            speed_limit=state["speed_limit"],
        )

        power, new_error, new_time = controls.calculate_power_command(
            self._accumulated_error, self._last_update_time
        )

        self._accumulated_error = new_error
        self._last_update_time = new_time
        return power


class train_controller_ui(tk.Toplevel):
    def __init__(self, train_id: int, state_file: str):
        super().__init__()
        self.train_id = train_id
        self.state_file = state_file
        self.controller = train_controller(train_id, state_file)

        self.title(f"Train {train_id} - Controller")
        self.geometry("550x450")
        self.configure(bg="lightgray")

        self.active_color = "#ff4444"
        self.normal_color = "lightgray"

        main_frame = ttk.Frame(self)
        main_frame.pack(fill="both", expand=True, padx=5, pady=5)

        self.create_speed_section(main_frame)
        self.create_info_table(main_frame)
        self.create_control_section(main_frame)

        self.update_interval = 500
        self.periodic_update()

    def create_speed_section(self, parent):
        speed_frame = ttk.LabelFrame(parent, text="Speed Control")
        speed_frame.pack(fill="x", padx=5, pady=5)

        display_frame = ttk.Frame(speed_frame)
        display_frame.pack(fill="x", pady=5)
        ttk.Label(display_frame, text="Current:", font=("Arial", 10)).pack(
            side="left", padx=5
        )
        self.speed_display = ttk.Label(
            display_frame, text="0 MPH", font=("Arial", 14, "bold")
        )
        self.speed_display.pack(side="left", padx=5)

        input_frame = ttk.Frame(speed_frame)
        input_frame.pack(fill="x", pady=5)
        ttk.Label(input_frame, text="Set Speed:", font=("Arial", 10)).pack(
            side="left", padx=5
        )
        self.speed_entry = ttk.Entry(input_frame, width=8, font=("Arial", 12))
        self.speed_entry.pack(side="left", padx=5)
        self.speed_entry.insert(0, "0")
        self.speed_entry.bind("<Return>", lambda e: self.set_driver_speed())
        ttk.Button(
            input_frame, text="Set", command=self.set_driver_speed, width=6
        ).pack(side="left", padx=5)

        self.set_speed_label = ttk.Label(
            speed_frame, text="Set: 0 MPH", font=("Arial", 10)
        )
        self.set_speed_label.pack(pady=2)

    def create_info_table(self, parent):
        table_frame = ttk.LabelFrame(parent, text="Train Information")
        table_frame.pack(fill="both", expand=True, padx=5, pady=5)

        self.info_table = ttk.Treeview(
            table_frame, columns=("Name", "Value"), show="headings", height=6
        )
        self.info_table.heading("Name", text="Parameter")
        self.info_table.heading("Value", text="Value")
        self.info_table.column("Name", width=180)
        self.info_table.column("Value", width=120)

        self.info_table.insert(
            "", "end", "commanded_speed", values=("Commanded Speed", "0 mph")
        )
        self.info_table.insert(
            "", "end", "speed_limit", values=("Speed Limit", "0 mph")
        )
        self.info_table.insert("", "end", "authority", values=("Authority", "0 yds"))
        self.info_table.insert("", "end", "next_stop", values=("Next Stop", "--"))
        self.info_table.insert("", "end", "power", values=("Power Command", "0 W"))
        self.info_table.insert("", "end", "station_side", values=("Door Side", "--"))

        self.info_table.pack(padx=5, pady=5, fill="both", expand=True)

    def create_control_section(self, parent):
        controls_frame = ttk.LabelFrame(parent, text="Controls")
        controls_frame.pack(fill="x", padx=5, pady=5)

        button_frame = ttk.Frame(controls_frame)
        button_frame.pack(padx=10, pady=10)

        self.service_brake_btn = tk.Button(
            button_frame,
            text="Service Brake",
            command=self.toggle_service_brake,
            bg=self.normal_color,
            width=14,
            height=1,
        )
        self.service_brake_btn.grid(row=0, column=0, padx=3, pady=3)

        self.emergency_brake_btn = tk.Button(
            button_frame,
            text="Emergency Brake",
            command=self.emergency_brake,
            bg=self.normal_color,
            width=14,
            height=1,
        )
        self.emergency_brake_btn.grid(row=0, column=1, padx=3, pady=3)

    def periodic_update(self):
        try:
            # Check if window still exists before updating
            if not self.winfo_exists():
                return

            self.controller.update_from_train_model()
            state = self.controller.get_state()

            if not state.get("manual_mode", False):
                if state["driver_velocity"] != state["commanded_speed"]:
                    self.controller.update_state(
                        {"driver_velocity": state["commanded_speed"]}
                    )
                    state = self.controller.get_state()

            if state["emergency_brake"] and state["train_velocity"] == 0.0:
                self.controller.vital_control_check_and_update(
                    {"emergency_brake": False}
                )
                state = self.controller.get_state()

            if not state["emergency_brake"] and state["service_brake"] == 0:
                power = self.controller.calculate_power_command(state)
                if power != state["power_command"]:
                    self.controller.vital_control_check_and_update(
                        {"power_command": power}
                    )
            else:
                self.controller._accumulated_error = 0
                self.controller.vital_control_check_and_update(
                    {"power_command": 0, "driver_velocity": 0}
                )

            self.speed_display.config(text=f"{state['train_velocity']:.1f} MPH")
            try:
                self.info_table.set(
                    "commanded_speed",
                    column="Value",
                    value=f"{state['commanded_speed']:.1f} mph",
                )
                self.info_table.set(
                    "speed_limit",
                    column="Value",
                    value=f"{state['speed_limit']:.1f} mph",
                )
                self.info_table.set(
                    "authority",
                    column="Value",
                    value=f"{state['commanded_authority']:.1f} yds",
                )
                self.info_table.set(
                    "next_stop", column="Value", value=state["next_stop"]
                )
                self.info_table.set(
                    "power", column="Value", value=f"{state['power_command']:.1f} W"
                )
                self.info_table.set(
                    "station_side", column="Value", value=state["station_side"]
                )
            except Exception:
                pass  # Table may be destroyed

            self.set_speed_label.config(text=f"Set: {state['driver_velocity']:.1f} MPH")

            if self.speed_entry.focus_get() != self.speed_entry:
                try:
                    if float(self.speed_entry.get()) != state["driver_velocity"]:
                        self.speed_entry.delete(0, tk.END)
                        self.speed_entry.insert(0, f"{state['driver_velocity']:.1f}")
                except (ValueError, tk.TclError):
                    try:
                        self.speed_entry.delete(0, tk.END)
                        self.speed_entry.insert(0, f"{state['driver_velocity']:.1f}")
                    except tk.TclError:
                        pass  # Entry widget may be destroyed

            try:
                self.update_button_states(state)
            except tk.TclError:
                pass  # Button may be destroyed
        except Exception as e:
            print(f"Update error: {e}")
        finally:
            self.after(self.update_interval, self.periodic_update)

    def update_button_states(self, state):
        self.service_brake_btn.configure(
            bg=self.active_color if state["service_brake"] > 0 else self.normal_color
        )
        self.emergency_brake_btn.configure(
            bg=self.active_color if state["emergency_brake"] else self.normal_color
        )

    def set_driver_speed(self):
        try:
            desired_speed = float(self.speed_entry.get())
            state = self.controller.get_state()
            commanded_speed = self.controller.cmd_speed_auth.commanded_speed
            speed_limit = state["speed_limit"]

            if state.get("manual_mode", False) or commanded_speed == 0:
                max_allowed = speed_limit if speed_limit > 0 else 100
            else:
                max_allowed = (
                    min(commanded_speed, speed_limit)
                    if speed_limit > 0
                    else commanded_speed
                )

            new_speed = max(0, min(max_allowed, desired_speed))
            state_copy = state.copy()
            state_copy["driver_velocity"] = new_speed
            power = self.controller.calculate_power_command(state_copy)

            self.controller.vital_control_check_and_update(
                {"driver_velocity": new_speed, "power_command": power}
            )
            self.speed_entry.delete(0, tk.END)
            self.speed_entry.insert(0, f"{new_speed:.1f}")
        except ValueError:
            state = self.controller.get_state()
            self.speed_entry.delete(0, tk.END)
            self.speed_entry.insert(0, f"{state['driver_velocity']:.1f}")

    def toggle_service_brake(self):
        state = self.controller.get_state()
        activate = state["service_brake"] == 0
        self.controller.vital_control_check_and_update(
            {
                "service_brake": activate,
                "power_command": 0 if activate else state["power_command"],
            }
        )

    def emergency_brake(self):
        state = self.controller.get_state()
        activate = not state.get("emergency_brake", False)
        self.controller.vital_control_check_and_update(
            {
                "emergency_brake": activate,
                "driver_velocity": 0 if activate else state["driver_velocity"],
                "power_command": 0 if activate else state["power_command"],
            }
        )


class TrainPair:
    def __init__(
        self, train_id, model, controller=None, model_ui=None, controller_ui=None
    ):
        self.train_id = train_id
        self.model = model
        self.controller = controller
        self.model_ui = model_ui
        self.controller_ui = controller_ui

    def show_windows(self):
        if self.model_ui and hasattr(self.model_ui, "master"):
            self.model_ui.master.deiconify()
        if self.controller_ui:
            self.controller_ui.deiconify()

    def hide_windows(self):
        if self.model_ui and hasattr(self.model_ui, "master"):
            self.model_ui.master.withdraw()
        if self.controller_ui:
            self.controller_ui.withdraw()


class TrainManager:
    def __init__(self, state_file=None):
        self.trains = {}
        self.next_train_id = 1

        if state_file is None:
            data_dir = os.path.join(current_dir, "data")
            os.makedirs(data_dir, exist_ok=True)
            self.state_file = os.path.join(data_dir, "train_states.json")
        else:
            self.state_file = state_file

        self.train_data_file = os.path.join(train_model_dir, "train_data.json")
        self.track_model_file = os.path.join(parent_dir, "track_model_Train_Model.json")

        if not os.path.exists(self.state_file):
            safe_write_json(self.state_file, {})

    def add_train(self, train_specs=None, create_uis=True):
        try:
            from train_model_core import TrainModel
            from train_model_ui import TrainModelUI
        except ImportError:
            import importlib.util

            spec = importlib.util.spec_from_file_location(
                "train_model_core", os.path.join(train_model_dir, "train_model_core.py")
            )
            core = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(core)
            spec2 = importlib.util.spec_from_file_location(
                "train_model_ui", os.path.join(train_model_dir, "train_model_ui.py")
            )
            ui_mod = importlib.util.module_from_spec(spec2)
            spec2.loader.exec_module(ui_mod)
            TrainModel = core.TrainModel
            TrainModelUI = ui_mod.TrainModelUI

        train_id = self.next_train_id
        self.next_train_id += 1

        if train_specs is None:
            train_specs = {
                "length_ft": 66.0,
                "width_ft": 10.0,
                "height_ft": 11.5,
                "mass_lbs": 90100,
                "max_power_hp": 161,
                "max_accel_ftps2": 1.64,
                "service_brake_ftps2": -3.94,
                "emergency_brake_ftps2": -8.86,
                "capacity": 222,
                "crew_count": 2,
            }

        model = TrainModel(train_specs)
        model_ui = None
        controller_ui = None
        controller = None

        if create_uis:
            model_ui_window = tk.Toplevel()
            model_ui_window.title(f"Train {train_id} - Train Model")
            model_ui = TrainModelUI(model_ui_window, train_id=train_id)

            x_offset = 50 + (train_id - 1) * 60
            y_offset = 50 + (train_id - 1) * 60
            model_ui_window.geometry(f"350x700+{x_offset}+{y_offset}")

            controller_ui = train_controller_ui(train_id, self.state_file)
            controller_ui.geometry(f"550x450+{x_offset + 360}+{y_offset}")
            controller = controller_ui.controller

        train_pair = TrainPair(train_id, model, controller, model_ui, controller_ui)
        self.trains[train_id] = train_pair

        self._initialize_train_state(train_id)
        self._initialize_train_data_entry(train_id, train_id - 1)

        print(f"Train {train_id} created")
        return train_id

    def _initialize_train_state(self, train_id):
        all_states = safe_read_json(self.state_file)
        track = safe_read_json(self.track_model_file)

        block, beacon = {}, {}
        if isinstance(track, dict) and track:
            keys = sorted([k for k in track.keys() if "_train_" in k])
            if keys:
                entry = track.get(keys[max(0, min(train_id - 1, len(keys) - 1))], {})
                if isinstance(entry, dict):
                    block = (
                        entry.get("block", {})
                        if isinstance(entry.get("block"), dict)
                        else {}
                    )
                    beacon = (
                        entry.get("beacon", {})
                        if isinstance(entry.get("beacon"), dict)
                        else {}
                    )

        all_states[f"train_{train_id}"] = {
            "train_id": train_id,
            "commanded_speed": float(block.get("commanded speed", 0.0) or 0.0),
            "commanded_authority": float(block.get("commanded authority", 0.0) or 0.0),
            "speed_limit": float(beacon.get("speed limit", 0.0) or 0.0),
            "train_velocity": 0.0,
            "next_stop": beacon.get("next station", "") or "",
            "station_side": beacon.get("side_door", "") or "",
            "manual_mode": False,
            "driver_velocity": 0.0,
            "service_brake": False,
            "emergency_brake": False,
            "kp": 1500.0,
            "ki": 50.0,
            "power_command": 0.0,
            "current_station": beacon.get("next station", "") or "",
        }
        safe_write_json(self.state_file, all_states)

    def _initialize_train_data_entry(self, train_id, index):
        track = safe_read_json(self.track_model_file)
        train_data = safe_read_json(self.train_data_file)

        block, beacon = {}, {}
        if isinstance(track, dict) and track:
            keys = sorted([k for k in track.keys() if "_train_" in k])
            if keys:
                entry = track.get(keys[max(0, min(index, len(keys) - 1))], {})
                if isinstance(entry, dict):
                    block = (
                        entry.get("block", {})
                        if isinstance(entry.get("block"), dict)
                        else {}
                    )
                    beacon = (
                        entry.get("beacon", {})
                        if isinstance(entry.get("beacon"), dict)
                        else {}
                    )

        if "specs" not in train_data:
            train_data["specs"] = {
                "length_ft": 66.0,
                "width_ft": 10.0,
                "height_ft": 11.5,
                "mass_lbs": 90100,
                "max_power_hp": 161,
                "max_accel_ftps2": 1.64,
                "service_brake_ftps2": -3.94,
                "emergency_brake_ftps2": -8.86,
                "capacity": 222,
                "crew_count": 2,
            }

        train_data[f"train_{train_id}"] = {
            "inputs": {
                "commanded speed": float(block.get("commanded speed", 0.0) or 0.0),
                "commanded authority": float(
                    block.get("commanded authority", 0.0) or 0.0
                ),
                "speed limit": float(beacon.get("speed limit", 0.0) or 0.0),
                "current station": beacon.get("current station", "") or "",
                "next station": beacon.get("next station", "") or "",
                "side_door": beacon.get("side_door", "") or "",
                "passengers_boarding": int(beacon.get("passengers_boarding", 0) or 0),
                "train_model_engine_failure": False,
                "train_model_signal_failure": False,
                "train_model_brake_failure": False,
                "emergency_brake": False,
                "passengers_onboard": 0,
            },
            "outputs": {
                "velocity_mph": 0.0,
                "acceleration_ftps2": 0.0,
                "position_yds": 0.0,
                "authority_yds": float(block.get("commanded authority", 0.0) or 0.0),
                "station_name": beacon.get("current station", "") or "",
                "next_station": beacon.get("next station", "") or "",
                "left_door_open": False,
                "right_door_open": False,
                "door_side": beacon.get("side_door", "") or "",
                "passengers_onboard": 0,
                "passengers_boarding": int(beacon.get("passengers_boarding", 0) or 0),
                "passengers_disembarking": 0,
            },
        }
        safe_write_json(self.train_data_file, train_data)

    def remove_train(self, train_id):
        if train_id not in self.trains:
            return False

        train = self.trains[train_id]
        if train.model_ui:
            try:
                train.model_ui.master.destroy()
            except:
                pass
        if train.controller_ui:
            try:
                train.controller_ui.destroy()
            except:
                pass

        del self.trains[train_id]

        all_states = safe_read_json(self.state_file)
        if f"train_{train_id}" in all_states:
            del all_states[f"train_{train_id}"]
        safe_write_json(self.state_file, all_states)

        print(f"Train {train_id} removed")
        return True

    def get_train(self, train_id):
        return self.trains.get(train_id)

    def get_all_train_ids(self):
        return list(self.trains.keys())

    def get_train_count(self):
        return len(self.trains)


class TrainManagerUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Train Manager")
        self.geometry("400x600+50+50")

        self.manager = TrainManager()
        self.visibility_buttons = {}
        self.selected_train_id = None

        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        self.create_header()
        self.create_train_list()
        self.create_control_buttons()
        self.create_status_bar()
        self.update_train_list()

        self.after(2000, self._poll_wrapper)

    def create_header(self):
        header = tk.Frame(self, bg="#2c3e50", height=80)
        header.grid(row=0, column=0, sticky="EW")
        header.columnconfigure(0, weight=1)

        tk.Label(
            header,
            text="Train Manager",
            font=("Arial", 18, "bold"),
            bg="#2c3e50",
            fg="white",
        ).grid(row=0, column=0, pady=(10, 0))
        tk.Label(
            header,
            text="Multi-Train System Control",
            font=("Arial", 10),
            bg="#2c3e50",
            fg="#bdc3c7",
        ).grid(row=1, column=0, pady=(0, 10))

    def create_train_list(self):
        list_frame = tk.LabelFrame(
            self, text="Active Trains", font=("Arial", 11, "bold")
        )
        list_frame.grid(row=1, column=0, sticky="NSEW", padx=10, pady=10)
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)

        canvas = tk.Canvas(list_frame)
        scrollbar = tk.Scrollbar(list_frame, orient="vertical", command=canvas.yview)
        self.train_items_frame = ttk.Frame(canvas)

        self.train_items_frame.bind(
            "<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=self.train_items_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True, padx=5, pady=5)
        scrollbar.pack(side="right", fill="y")

    def create_control_buttons(self):
        button_frame = tk.Frame(self)
        button_frame.grid(row=2, column=0, sticky="EW", padx=10, pady=(0, 10))
        button_frame.columnconfigure(0, weight=1)

        tk.Button(
            button_frame,
            text="➕ Add New Train",
            font=("Arial", 12, "bold"),
            bg="#27ae60",
            fg="white",
            command=self.add_train,
            height=2,
            cursor="hand2",
        ).grid(row=0, column=0, columnspan=2, sticky="EW", pady=(0, 10))

        tk.Button(
            button_frame,
            text="Remove Selected",
            font=("Arial", 10),
            bg="#e74c3c",
            fg="white",
            command=self.remove_selected_train,
            cursor="hand2",
        ).grid(row=1, column=0, sticky="EW")

    def create_status_bar(self):
        status_frame = tk.Frame(self, bg="#34495e", height=30)
        status_frame.grid(row=3, column=0, sticky="EW")

        self.status_label = tk.Label(
            status_frame,
            text="Ready - No trains active",
            font=("Arial", 9),
            bg="#34495e",
            fg="white",
            anchor="w",
        )
        self.status_label.pack(side="left", padx=10, pady=5)

    def add_train(self):
        try:
            train_id = self.manager.add_train(create_uis=True)
            self.update_train_list()
            self.update_status(f"Train {train_id} added")
        except Exception as e:
            self.update_status(f"Error: {e}")
            print(f"Error adding train: {e}")

    def remove_selected_train(self):
        if self.selected_train_id is None:
            self.update_status("No train selected")
            return

        try:
            if self.manager.remove_train(self.selected_train_id):
                self.update_train_list()
                self.update_status(f"Train {self.selected_train_id} removed")
                self.selected_train_id = None
        except Exception as e:
            self.update_status(f"Error: {e}")

    def update_train_list(self):
        for widget in self.train_items_frame.winfo_children():
            widget.destroy()

        self.visibility_buttons.clear()
        train_ids = self.manager.get_all_train_ids()

        if not train_ids:
            ttk.Label(
                self.train_items_frame,
                text="No trains active",
                font=("Arial", 10, "italic"),
            ).pack(pady=10)
        else:
            for train_id in train_ids:
                train_frame = ttk.Frame(self.train_items_frame)
                train_frame.pack(fill="x", padx=5, pady=3)

                ttk.Radiobutton(
                    train_frame,
                    text=f"Train {train_id}",
                    value=train_id,
                    command=lambda tid=train_id: self.select_train(tid),
                ).pack(side="left", padx=5)

                btn = ttk.Button(
                    train_frame,
                    text="Hide",
                    width=8,
                    command=lambda tid=train_id: self.toggle_train_visibility(tid),
                )
                btn.pack(side="right", padx=2)

                self.visibility_buttons[train_id] = btn

        count = self.manager.get_train_count()
        if count == 0:
            self.update_status("Ready - No trains active")
        else:
            self.update_status(f"Managing {count} train(s)")

    def select_train(self, train_id):
        self.selected_train_id = train_id

    def toggle_train_visibility(self, train_id):
        train = self.manager.get_train(train_id)
        if not train:
            return

        btn = self.visibility_buttons.get(train_id)
        if not btn:
            return

        if train.controller_ui and train.controller_ui.state() == "normal":
            train.hide_windows()
            btn.config(text="Show")
        else:
            train.show_windows()
            btn.config(text="Hide")

    def update_status(self, message):
        self.status_label.config(text=message)

    def _poll_track_model_for_new_trains(self):
        """Poll track_model_Train_Model.json for new trains dispatched by TrackControl."""
        try:
            track_model_data = safe_read_json(self.track_model_file)

            if not isinstance(track_model_data, dict):
                self.after(1000, self._poll_track_model_for_new_trains)
                return

            # Find all train keys (G_train_* or R_train_*)
            train_keys = [k for k in track_model_data.keys() if "_train_" in k]

            for train_key in train_keys:
                train_data = track_model_data[train_key]
                if not isinstance(train_data, dict):
                    continue

                # Extract train_id from key (e.g., "G_train_3" -> 3)
                try:
                    train_id = int(train_key.split("_train_")[-1])
                except (ValueError, IndexError):
                    continue

                # Check if train has non-zero commanded speed or authority
                block = train_data.get("block", {})
                if not isinstance(block, dict):
                    continue

                commanded_speed = float(block.get("commanded speed", 0) or 0)
                commanded_authority = float(block.get("commanded authority", 0) or 0)

                # If train is dispatched (has commands) but doesn't exist locally, create it
                if (
                    commanded_speed > 0 or commanded_authority > 0
                ) and train_id not in self.trains:
                    print(f"Auto-creating Train {train_id} from TrackControl dispatch")

                    # Sync next_train_id to avoid conflicts
                    if train_id >= self.next_train_id:
                        self.next_train_id = train_id + 1

                    # Add the train with the specific train_id
                    self._add_train_with_id(train_id)

        except Exception as e:
            print(f"Error polling track model: {e}")
        finally:
            self.after(1000, self._poll_track_model_for_new_trains)

    def _add_train_with_id(self, train_id):
        """Add a train with a specific ID (used by polling mechanism)."""
        try:
            from train_model_core import TrainModel
            from train_model_ui import TrainModelUI
        except ImportError:
            import importlib.util

            spec = importlib.util.spec_from_file_location(
                "train_model_core", os.path.join(train_model_dir, "train_model_core.py")
            )
            core = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(core)
            spec2 = importlib.util.spec_from_file_location(
                "train_model_ui", os.path.join(train_model_dir, "train_model_ui.py")
            )
            ui_mod = importlib.util.module_from_spec(spec2)
            spec2.loader.exec_module(ui_mod)
            TrainModel = core.TrainModel
            TrainModelUI = ui_mod.TrainModelUI

        train_specs = {
            "length_ft": 66.0,
            "width_ft": 10.0,
            "height_ft": 11.5,
            "mass_lbs": 90100,
            "max_power_hp": 161,
            "max_accel_ftps2": 1.64,
            "service_brake_ftps2": -3.94,
            "emergency_brake_ftps2": -8.86,
            "capacity": 222,
            "crew_count": 2,
        }

        model = TrainModel(train_specs)

        model_ui_window = tk.Toplevel()
        model_ui_window.title(f"Train {train_id} - Train Model")
        model_ui = TrainModelUI(model_ui_window, train_id=train_id)

        x_offset = 50 + (train_id - 1) * 60
        y_offset = 50 + (train_id - 1) * 60
        model_ui_window.geometry(f"350x700+{x_offset}+{y_offset}")

        controller_ui = train_controller_ui(train_id, self.state_file)
        controller_ui.geometry(f"550x450+{x_offset + 360}+{y_offset}")
        controller = controller_ui.controller

        train_pair = TrainPair(train_id, model, controller, model_ui, controller_ui)
        self.trains[train_id] = train_pair

        self._initialize_train_state(train_id)
        self._initialize_train_data_entry(train_id, train_id - 1)

        print(f"Train {train_id} auto-created from dispatch")


if __name__ == "__main__":
    app = TrainManagerUI()
    app.mainloop()
