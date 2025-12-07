"""Train Manager Module - Consolidated Version

This module manages multiple trains, where each train consists of:
- One TrainModel instance (physics simulation)
- One train_controller instance (control logic)
- UI windows for both

All state management, controller logic, and UI are consolidated in this single file.

Author: Consolidated from multiple modules
"""

import os
import sys
import json
import time
import tkinter as tk
from tkinter import ttk
import threading
from typing import Dict, Optional

# Add paths for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(current_dir)
sys.path.append(parent_dir)

# Import TrainModel components
train_model_dir = os.path.join(parent_dir, "Train_Model")
sys.path.append(train_model_dir)

# Global file lock for thread-safe JSON access
_file_lock = threading.Lock()


# ============================================================================
# STATE MANAGEMENT (from train_controller_api)
# ============================================================================


def safe_read_json(path: str) -> dict:
    """Safely read JSON file with error handling."""
    try:
        with open(path, "r") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def safe_write_json(path: str, data: dict):
    """Safely write JSON file with error handling."""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(f"Error writing JSON to {path}: {e}")


# ============================================================================
# CONTROLLER CLASSES (from train_controller_sw_ui)
# ============================================================================


class beacon:
    """Beacon information for station announcements."""

    def __init__(self, next_stop: str = "", station_side: str = ""):
        self.next_stop = next_stop
        self.station_side = station_side

    def update_from_state(self, state: dict) -> None:
        self.next_stop = state.get("next_stop", "")
        self.station_side = state.get("station_side", "")


class commanded_speed_authority:
    """Commanded speed and authority from wayside/CTC."""

    def __init__(self, commanded_speed: int = 0, commanded_authority: int = 0):
        self.commanded_speed = commanded_speed
        self.commanded_authority = commanded_authority

    def update_from_state(self, state: dict) -> None:
        self.commanded_speed = int(state.get("commanded_speed", 0))
        self.commanded_authority = int(state.get("commanded_authority", 0))


class vital_train_controls:
    """Vital train controls for safety-critical operations."""

    def __init__(
        self,
        kp: float = 0.0,
        ki: float = 0.0,
        train_velocity: float = 0.0,
        driver_velocity: float = 0.0,
        emergency_brake: bool = False,
        service_brake: bool = False,
        power_command: float = 0.0,
        commanded_authority: float = 0.0,
        speed_limit: float = 0.0,
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

    def calculate_power_command(
        self, accumulated_error: float, last_update_time: float
    ) -> tuple:
        """Calculate power command using PI control."""
        speed_error = self.driver_velocity - self.train_velocity

        if speed_error <= 0.01:
            return (0.0, 0.0, time.time())

        current_time = time.time()
        dt = current_time - last_update_time
        dt = max(0.001, min(dt, 1.0))

        new_accumulated_error = accumulated_error + speed_error * dt
        max_integral = 120000 / self.ki if self.ki != 0 else 0
        new_accumulated_error = max(
            -max_integral, min(max_integral, new_accumulated_error)
        )

        proportional = self.kp * speed_error
        integral = self.ki * new_accumulated_error
        power = proportional + integral
        power = max(0, min(power, 120000))

        if power == 120000 and integral > 0:
            new_accumulated_error = (
                (120000 - proportional) / self.ki if self.ki != 0 else 0
            )
        elif power == 0 and integral < 0:
            new_accumulated_error = -proportional / self.ki if self.ki != 0 else 0

        return (power, new_accumulated_error, current_time)


class vital_validator_first_check:
    """First validator for vital train controls."""

    def validate(self, v: vital_train_controls) -> bool:
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
    """Second validator with margins."""

    def validate(self, v: vital_train_controls) -> bool:
        if v.speed_limit > 0:
            safe_speed = v.speed_limit * 1.02
            if v.train_velocity > safe_speed:
                return False
        if v.service_brake and v.emergency_brake:
            return False
        if v.commanded_authority > 0 or v.power_command == 0:
            return True
        else:
            return False


class train_controller:
    """Train controller logic and calculations."""

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

    def get_state(self) -> dict:
        """Get train state from JSON."""
        with _file_lock:
            all_states = safe_read_json(self.state_file)
            train_key = f"train_{self.train_id}"
            return all_states.get(train_key, {})

    def update_state(self, updates: dict) -> None:
        """Update train state in JSON."""
        with _file_lock:
            all_states = safe_read_json(self.state_file)
            train_key = f"train_{self.train_id}"
            if train_key not in all_states:
                all_states[train_key] = {}
            all_states[train_key].update(updates)
            safe_write_json(self.state_file, all_states)

    def update_from_train_model(self) -> None:
        """Update beacon and commanded speed/authority from state."""
        state = self.get_state()
        self.beacon_info.update_from_state(state)
        self.cmd_speed_auth.update_from_state(state)

    def vital_control_check_and_update(self, changes: dict) -> bool:
        """Run validators and apply changes if accepted."""
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

    def calculate_power_command(self, state: dict) -> float:
        """Calculate power command using vital controls."""
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
    """Train controller user interface."""

    def __init__(self, train_id: int, state_file: str):
        super().__init__()

        self.train_id = train_id
        self.state_file = state_file
        self.controller = train_controller(train_id, state_file)

        self._last_beacon_for_announcement = None

        self.title(f"Train {train_id} - Train Controller")
        self.geometry("1200x800")
        self.configure(bg="lightgray")

        self.active_color = "#ff4444"
        self.normal_color = "lightgray"

        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=3)
        self.grid_rowconfigure(1, weight=2)
        self.grid_rowconfigure(2, weight=1)

        self.top_frame = ttk.Frame(self)
        self.top_frame.grid(
            row=0, column=0, columnspan=2, sticky="nsew", padx=10, pady=5
        )
        self.top_frame.grid_columnconfigure(0, weight=1)
        self.top_frame.grid_columnconfigure(1, weight=1)

        self.control_frame = ttk.Frame(self)
        self.control_frame.grid(
            row=1, column=0, columnspan=2, sticky="nsew", padx=10, pady=5
        )

        self.engineering_frame = ttk.Frame(self)
        self.engineering_frame.grid(
            row=2, column=0, columnspan=2, sticky="nsew", padx=10, pady=5
        )

        self.create_speed_section()
        self.create_info_table()
        self.create_control_section()
        self.create_engineering_panel()

        self.update_interval = 500
        self.periodic_update()

    def create_speed_section(self):
        """Create speed control section."""
        speed_frame = ttk.LabelFrame(self.top_frame, text="Speed Control")
        speed_frame.grid(row=0, column=0, padx=10, pady=5, sticky="nsew")

        speed_display_frame = ttk.Frame(speed_frame)
        speed_display_frame.pack(expand=True, fill="both", pady=20)

        ttk.Label(speed_display_frame, text="Current Speed", font=("Arial", 14)).pack()
        self.speed_display = ttk.Label(
            speed_display_frame, text="0 MPH", font=("Arial", 36, "bold")
        )
        self.speed_display.pack(pady=10)

        set_speed_frame = ttk.Frame(speed_frame)
        set_speed_frame.pack(fill="x", padx=20, pady=10)

        ttk.Label(set_speed_frame, text="Set Driver Speed (mph):").pack()

        input_frame = ttk.Frame(set_speed_frame)
        input_frame.pack(pady=5)

        self.speed_entry = ttk.Entry(input_frame, width=10, font=("Arial", 14))
        self.speed_entry.pack(side="left", padx=5)
        self.speed_entry.insert(0, "0")
        self.speed_entry.bind("<Return>", lambda e: self.set_driver_speed())

        self.set_speed_btn = ttk.Button(
            input_frame, text="Set Speed", command=self.set_driver_speed
        )
        self.set_speed_btn.pack(side="left", padx=5)

        self.set_speed_label = ttk.Label(
            set_speed_frame, text="Current Set: 0 MPH", font=("Arial", 12, "bold")
        )
        self.set_speed_label.pack(pady=5)

    def create_info_table(self):
        """Create information table."""
        table_frame = ttk.LabelFrame(self.top_frame, text="Train Information")
        table_frame.grid(row=0, column=1, padx=10, pady=5, sticky="nsew")

        self.info_table = ttk.Treeview(
            table_frame, columns=("Name", "Value", "Unit"), show="headings", height=10
        )
        self.info_table.heading("Name", text="Parameter")
        self.info_table.heading("Value", text="Value")
        self.info_table.heading("Unit", text="Unit")

        self.info_table.column("Name", width=200)
        self.info_table.column("Value", width=150)
        self.info_table.column("Unit", width=100)

        self.info_table.insert(
            "", "end", "commanded_speed", values=("Commanded Speed", "0", "mph")
        )
        self.info_table.insert(
            "", "end", "speed_limit", values=("Speed Limit", "0", "mph")
        )
        self.info_table.insert(
            "", "end", "authority", values=("Commanded Authority", "0", "yds")
        )
        self.info_table.insert(
            "", "end", "current_station", values=("Current Station", "--", "")
        )
        self.info_table.insert("", "end", "next_stop", values=("Next Stop", "--", ""))
        self.info_table.insert("", "end", "power", values=("Power Command", "0", "W"))
        self.info_table.insert(
            "", "end", "station_side", values=("Station Side", "--", "")
        )

        self.info_table.pack(padx=5, pady=5, expand=True, fill="both")

    def create_control_section(self):
        """Create control buttons."""
        controls_label_frame = ttk.LabelFrame(self.control_frame, text="Train Controls")
        controls_label_frame.pack(fill="both", expand=True, padx=10, pady=5)

        button_frame = ttk.Frame(controls_label_frame)
        button_frame.pack(expand=True, fill="both", padx=5, pady=5)

        for i in range(2):
            button_frame.grid_rowconfigure(i, weight=1)
        for i in range(4):
            button_frame.grid_columnconfigure(i, weight=1)

        button_width = 15
        button_height = 2
        padding = 5

        self.service_brake_btn = tk.Button(
            button_frame,
            text="Service Brake",
            command=self.toggle_service_brake,
            bg=self.normal_color,
            width=button_width,
            height=button_height,
        )
        self.service_brake_btn.grid(row=0, column=0, padx=padding, pady=padding)

        self.emergency_brake_btn = tk.Button(
            button_frame,
            text="Emergency Brake",
            command=self.emergency_brake,
            bg=self.normal_color,
            width=button_width,
            height=button_height,
        )
        self.emergency_brake_btn.grid(row=0, column=1, padx=padding, pady=padding)

        self.manual_mode_btn = tk.Button(
            button_frame,
            text="Manual Mode",
            command=self.toggle_manual_mode,
            bg=self.normal_color,
            width=button_width,
            height=button_height,
        )
        self.manual_mode_btn.grid(row=0, column=2, padx=padding, pady=padding)

    def create_engineering_panel(self):
        """Create engineering panel."""
        eng_frame = ttk.LabelFrame(self.engineering_frame, text="Engineering Panel")
        eng_frame.pack(fill="x", expand=True, padx=10, pady=5)

        ttk.Label(eng_frame, text="Kp:").grid(row=0, column=0, padx=5, pady=5)
        self.kp_entry = ttk.Entry(eng_frame)
        self.kp_entry.grid(row=0, column=1, padx=5, pady=5)
        self.kp_entry.insert(0, "1500.0")

        ttk.Label(eng_frame, text="Ki:").grid(row=0, column=2, padx=5, pady=5)
        self.ki_entry = ttk.Entry(eng_frame)
        self.ki_entry.grid(row=0, column=3, padx=5, pady=5)
        self.ki_entry.insert(0, "50.0")

        self.lock_btn = ttk.Button(
            eng_frame, text="Lock Values", command=self.lock_engineering_values
        )
        self.lock_btn.grid(row=0, column=4, padx=20, pady=5)

    def periodic_update(self):
        """Update display periodically."""
        try:
            self.controller.update_from_train_model()
            current_state = self.controller.get_state()

            manual_mode = current_state.get("manual_mode", False)

            if not manual_mode:
                if current_state["driver_velocity"] != current_state["commanded_speed"]:
                    self.controller.update_state(
                        {"driver_velocity": current_state["commanded_speed"]}
                    )
                    current_state = self.controller.get_state()

            if (
                current_state["emergency_brake"]
                and current_state["train_velocity"] == 0.0
            ):
                self.controller.vital_control_check_and_update(
                    {"emergency_brake": False}
                )
                current_state = self.controller.get_state()

            if (
                not current_state["emergency_brake"]
                and current_state["service_brake"] == 0
            ):
                power = self.controller.calculate_power_command(current_state)
                if power != current_state["power_command"]:
                    self.controller.vital_control_check_and_update(
                        {"power_command": power}
                    )
            else:
                self.controller._accumulated_error = 0
                self.controller.vital_control_check_and_update(
                    {"power_command": 0, "driver_velocity": 0}
                )

            self.speed_display.config(text=f"{current_state['train_velocity']:.1f} MPH")
            self.info_table.set(
                "commanded_speed",
                column="Value",
                value=f"{current_state['commanded_speed']:.1f}",
            )
            self.info_table.set(
                "speed_limit",
                column="Value",
                value=f"{current_state['speed_limit']:.1f}",
            )
            self.info_table.set(
                "authority",
                column="Value",
                value=f"{current_state['commanded_authority']:.1f}",
            )
            self.info_table.set(
                "current_station",
                column="Value",
                value=current_state.get("current_station", "--"),
            )
            self.info_table.set(
                "next_stop", column="Value", value=current_state["next_stop"]
            )
            self.info_table.set(
                "power", column="Value", value=f"{current_state['power_command']:.1f}"
            )
            self.info_table.set(
                "station_side", column="Value", value=current_state["station_side"]
            )

            self.set_speed_label.config(
                text=f"Current Set: {current_state['driver_velocity']:.1f} MPH"
            )

            if self.speed_entry.focus_get() != self.speed_entry:
                try:
                    current_entry = self.speed_entry.get()
                    if float(current_entry) != current_state["driver_velocity"]:
                        self.speed_entry.delete(0, tk.END)
                        self.speed_entry.insert(
                            0, f"{current_state['driver_velocity']:.1f}"
                        )
                except ValueError:
                    self.speed_entry.delete(0, tk.END)
                    self.speed_entry.insert(
                        0, f"{current_state['driver_velocity']:.1f}"
                    )

            self.update_button_states(current_state)

        except Exception as e:
            print(f"Update error: {e}")
        finally:
            self.after(self.update_interval, self.periodic_update)

    def update_button_states(self, state):
        """Update button colors."""
        self.service_brake_btn.configure(
            bg=self.active_color if state["service_brake"] > 0 else self.normal_color
        )
        self.emergency_brake_btn.configure(
            bg=self.active_color if state["emergency_brake"] else self.normal_color
        )
        self.manual_mode_btn.configure(
            bg=self.active_color if state["manual_mode"] else self.normal_color
        )

    def set_driver_speed(self):
        """Set driver speed from input."""
        try:
            desired_speed = float(self.speed_entry.get())
            state = self.controller.get_state()
            commanded_speed = self.controller.cmd_speed_auth.commanded_speed
            speed_limit = state["speed_limit"]

            if state.get("manual_mode", False) or commanded_speed == 0:
                max_allowed_speed = speed_limit if speed_limit > 0 else 100
            else:
                max_allowed_speed = (
                    min(commanded_speed, speed_limit)
                    if speed_limit > 0
                    else commanded_speed
                )

            new_speed = max(0, min(max_allowed_speed, desired_speed))

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

    def toggle_manual_mode(self):
        """Toggle manual mode."""
        state = self.controller.get_state()
        self.controller.update_state(
            {"manual_mode": not state.get("manual_mode", False)}
        )

    def toggle_service_brake(self):
        """Toggle service brake."""
        state = self.controller.get_state()
        activate = state["service_brake"] == 0
        self.controller.vital_control_check_and_update(
            {
                "service_brake": activate,
                "power_command": 0 if activate else state["power_command"],
            }
        )

    def emergency_brake(self):
        """Toggle emergency brake."""
        state = self.controller.get_state()
        activate = not state.get("emergency_brake", False)
        self.controller.vital_control_check_and_update(
            {
                "emergency_brake": activate,
                "driver_velocity": 0 if activate else state["driver_velocity"],
                "power_command": 0 if activate else state["power_command"],
            }
        )

    def lock_engineering_values(self):
        """Lock Kp and Ki values."""
        try:
            kp = float(self.kp_entry.get())
            ki = float(self.ki_entry.get())

            self.controller.update_state(
                {"kp": kp, "ki": ki, "engineering_panel_locked": True}
            )

            self.kp_entry.configure(state="disabled")
            self.ki_entry.configure(state="disabled")
            self.lock_btn.configure(state="disabled")

        except ValueError:
            pass


# ============================================================================
# TRAIN MANAGER
# ============================================================================


class TrainPair:
    """Represents a paired TrainModel and train_controller instance with UIs."""

    def __init__(
        self, train_id: int, model, controller=None, model_ui=None, controller_ui=None
    ):
        self.train_id = train_id
        self.model = model
        self.controller = controller
        self.model_ui = model_ui
        self.controller_ui = controller_ui


class TrainManager:
    """Manages multiple trains (TrainModel + train_controller pairs)."""

    def __init__(self, state_file: str = None):
        self.trains = {}
        self.next_train_id = 1

        if state_file is None:
            data_dir = os.path.join(current_dir, "data")
            os.makedirs(data_dir, exist_ok=True)
            self.state_file = os.path.join(data_dir, "train_states.json")
        else:
            self.state_file = state_file

        self.train_data_file = os.path.join(train_model_dir, "train_data.json")
        self.track_model_file = os.path.join(
            train_model_dir, "track_model_Train_Model.json"
        )

        self._initialize_state_file()

    def _initialize_state_file(self):
        """Initialize train_states.json if it doesn't exist."""
        if not os.path.exists(self.state_file):
            safe_write_json(self.state_file, {})

    def add_train(self, train_specs: dict = None, create_uis: bool = True) -> int:
        """Add a new train with software controller."""
        try:
            from train_model_core import TrainModel
            from train_model_ui import TrainModelUI
        except ImportError:
            import importlib.util

            core_spec = importlib.util.spec_from_file_location(
                "train_model_core", os.path.join(train_model_dir, "train_model_core.py")
            )
            core_module = importlib.util.module_from_spec(core_spec)
            core_spec.loader.exec_module(core_module)
            ui_spec = importlib.util.spec_from_file_location(
                "train_model_ui", os.path.join(train_model_dir, "train_model_ui.py")
            )
            ui_module = importlib.util.module_from_spec(ui_spec)
            ui_spec.loader.exec_module(ui_module)
            TrainModel = core_module.TrainModel
            TrainModelUI = ui_module.TrainModelUI

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
            controller_ui.geometry(f"1200x800+{x_offset + 360}+{y_offset}")

            controller = controller_ui.controller

            print(f"Train {train_id} UIs created")

        train_pair = TrainPair(train_id, model, controller, model_ui, controller_ui)
        self.trains[train_id] = train_pair

        self._initialize_train_state(train_id)

        try:
            self._initialize_train_data_entry(train_id, index=train_id - 1)
        except Exception as e:
            print(
                f"Warning: failed to initialize train_data.json for train {train_id}: {e}"
            )

        print(f"Train {train_id} created successfully")
        return train_id

    def _initialize_train_state(self, train_id: int):
        """Initialize state for a train."""
        all_states = safe_read_json(self.state_file)
        train_key = f"train_{train_id}"

        track = safe_read_json(self.track_model_file)
        block = {}
        beacon = {}

        if isinstance(track, dict) and track:
            keys = sorted([k for k in track.keys() if "_train_" in k])
            idx = max(0, train_id - 1)
            if keys:
                entry = track.get(keys[idx if idx < len(keys) else 0], {})
                if isinstance(entry, dict):
                    block = (
                        entry.get("block", {})
                        if isinstance(entry.get("block", {}), dict)
                        else {}
                    )
                    beacon = (
                        entry.get("beacon", {})
                        if isinstance(entry.get("beacon", {}), dict)
                        else {}
                    )

        commanded_speed = float(block.get("commanded speed", 0.0) or 0.0)
        commanded_authority = float(block.get("commanded authority", 0.0) or 0.0)
        speed_limit = float(beacon.get("speed limit", 0.0) or 0.0)
        next_stop = beacon.get("next station", "") or ""
        station_side = beacon.get("side_door", "") or ""

        all_states[train_key] = {
            "train_id": train_id,
            "commanded_speed": commanded_speed,
            "commanded_authority": commanded_authority,
            "speed_limit": speed_limit,
            "train_velocity": 0.0,
            "next_stop": next_stop,
            "station_side": station_side,
            "manual_mode": False,
            "driver_velocity": 0.0,
            "service_brake": False,
            "emergency_brake": False,
            "kp": 1500.0,
            "ki": 50.0,
            "engineering_panel_locked": False,
            "power_command": 0.0,
            "current_station": next_stop,
        }

        safe_write_json(self.state_file, all_states)

    def _initialize_train_data_entry(self, train_id: int, index: int):
        """Initialize train_data.json entry for this train."""
        track = safe_read_json(self.track_model_file)
        train_data = safe_read_json(self.train_data_file)

        block = {}
        beacon = {}
        if isinstance(track, dict) and track:
            keys = sorted([k for k in track.keys() if "_train_" in k])
            idx = index if 0 <= index < len(keys) else 0
            if keys:
                entry = track.get(keys[idx], {})
                if isinstance(entry, dict):
                    block = (
                        entry.get("block", {})
                        if isinstance(entry.get("block", {}), dict)
                        else {}
                    )
                    beacon = (
                        entry.get("beacon", {})
                        if isinstance(entry.get("beacon", {}), dict)
                        else {}
                    )

        cmd_speed = float(block.get("commanded speed", 0.0) or 0.0)
        cmd_auth = float(block.get("commanded authority", 0.0) or 0.0)
        speed_lim = float(beacon.get("speed limit", 0.0) or 0.0)

        inputs = {
            "commanded speed": cmd_speed,
            "commanded authority": cmd_auth,
            "speed limit": speed_lim,
            "current station": beacon.get("current station", "") or "",
            "next station": beacon.get("next station", "") or "",
            "side_door": beacon.get("side_door", "") or "",
            "passengers_boarding": int(beacon.get("passengers_boarding", 0) or 0),
            "train_model_engine_failure": False,
            "train_model_signal_failure": False,
            "train_model_brake_failure": False,
            "emergency_brake": False,
            "passengers_onboard": 0,
        }

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

        train_key = f"train_{train_id}"
        train_data[train_key] = {
            "inputs": inputs,
            "outputs": {
                "velocity_mph": 0.0,
                "acceleration_ftps2": 0.0,
                "position_yds": 0.0,
                "authority_yds": float(inputs["commanded authority"]),
                "station_name": inputs["current station"],
                "next_station": inputs["next station"],
                "left_door_open": False,
                "right_door_open": False,
                "door_side": inputs["side_door"],
                "passengers_onboard": 0,
                "passengers_boarding": inputs["passengers_boarding"],
                "passengers_disembarking": 0,
            },
        }

        safe_write_json(self.train_data_file, train_data)

    def remove_train(self, train_id: int) -> bool:
        """Remove a train."""
        if train_id not in self.trains:
            return False

        train_pair = self.trains[train_id]
        if train_pair.model_ui:
            try:
                train_pair.model_ui.master.destroy()
            except:
                pass
        if train_pair.controller_ui:
            try:
                train_pair.controller_ui.destroy()
            except:
                pass

        del self.trains[train_id]

        all_states = safe_read_json(self.state_file)
        train_key = f"train_{train_id}"
        if train_key in all_states:
            del all_states[train_key]
        safe_write_json(self.state_file, all_states)

        print(f"Train {train_id} removed")
        return True

    def get_train(self, train_id: int) -> TrainPair:
        """Get train by ID."""
        return self.trains.get(train_id, None)

    def get_all_train_ids(self) -> list:
        """Get all train IDs."""
        return list(self.trains.keys())

    def get_train_count(self) -> int:
        """Get number of trains."""
        return len(self.trains)


class TrainManagerUI(tk.Tk):
    """UI for managing multiple trains."""

    def __init__(self):
        super().__init__()

        self.title("Train Manager - System Control")
        self.geometry("400x600+50+50")

        self.manager = TrainManager()

        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        self.create_header()
        self.create_train_list()
        self.create_control_buttons()
        self.create_status_bar()

        self.update_train_list()

    def create_header(self):
        """Create header."""
        header_frame = tk.Frame(self, bg="#2c3e50", height=80)
        header_frame.grid(row=0, column=0, sticky="EW")
        header_frame.columnconfigure(0, weight=1)

        title = tk.Label(
            header_frame,
            text="Train Manager",
            font=("Arial", 18, "bold"),
            bg="#2c3e50",
            fg="white",
        )
        title.grid(row=0, column=0, pady=(10, 0))

        subtitle = tk.Label(
            header_frame,
            text="Multi-Train System Control",
            font=("Arial", 10),
            bg="#2c3e50",
            fg="#bdc3c7",
        )
        subtitle.grid(row=1, column=0, pady=(0, 10))

    def create_train_list(self):
        """Create train list."""
        list_frame = tk.LabelFrame(
            self, text="Active Trains", font=("Arial", 11, "bold")
        )
        list_frame.grid(row=1, column=0, sticky="NSEW", padx=10, pady=10)
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)

        scrollbar = tk.Scrollbar(list_frame)
        scrollbar.grid(row=0, column=1, sticky="NS")

        self.train_listbox = tk.Listbox(
            list_frame,
            font=("Courier", 10),
            yscrollcommand=scrollbar.set,
            selectmode=tk.SINGLE,
            height=15,
        )
        self.train_listbox.grid(row=0, column=0, sticky="NSEW", padx=5, pady=5)
        scrollbar.config(command=self.train_listbox.yview)

    def create_control_buttons(self):
        """Create control buttons."""
        button_frame = tk.Frame(self)
        button_frame.grid(row=2, column=0, sticky="EW", padx=10, pady=(0, 10))
        button_frame.columnconfigure(0, weight=1)
        button_frame.columnconfigure(1, weight=1)

        self.add_button = tk.Button(
            button_frame,
            text="➕ Add New Train",
            font=("Arial", 12, "bold"),
            bg="#27ae60",
            fg="white",
            command=self.add_train,
            height=2,
            cursor="hand2",
        )
        self.add_button.grid(row=0, column=0, columnspan=2, sticky="EW", pady=(0, 10))

        self.remove_button = tk.Button(
            button_frame,
            text="Remove Selected",
            font=("Arial", 10),
            bg="#e74c3c",
            fg="white",
            command=self.remove_selected_train,
            cursor="hand2",
        )
        self.remove_button.grid(row=1, column=0, sticky="EW", padx=(0, 5))

    def create_status_bar(self):
        """Create status bar."""
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
        """Add new train."""
        try:
            train_id = self.manager.add_train(create_uis=True)
            self.update_train_list()
            self.update_status(f"Train {train_id} added")
        except Exception as e:
            self.update_status(f"Error: {e}")

    def remove_selected_train(self):
        """Remove selected train."""
        selection = self.train_listbox.curselection()
        if not selection:
            return

        selected_text = self.train_listbox.get(selection[0])
        try:
            train_id = int(selected_text.split()[1])
            if self.manager.remove_train(train_id):
                self.update_train_list()
                self.update_status(f"Train {train_id} removed")
        except Exception as e:
            self.update_status(f"Error: {e}")

    def update_train_list(self):
        """Update train list."""
        self.train_listbox.delete(0, tk.END)

        train_ids = self.manager.get_all_train_ids()
        if not train_ids:
            self.train_listbox.insert(tk.END, "  No trains active")
        else:
            for train_id in train_ids:
                self.train_listbox.insert(tk.END, f"Train {train_id} - Active")

        count = self.manager.get_train_count()
        if count == 0:
            self.update_status("Ready - No trains active")
        else:
            self.update_status(f"Managing {count} train(s)")

    def update_status(self, message: str):
        """Update status bar."""
        self.status_label.config(text=message)


if __name__ == "__main__":
    app = TrainManagerUI()
    app.mainloop()
