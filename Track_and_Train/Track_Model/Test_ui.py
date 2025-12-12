"""
TRACK MODEL TEST UI - ENHANCED WITH LINE-SPECIFIC CONTROLS
WRITE to track_io.json: switches, gates, lights, commanded speed/authority
READ from track_model_Train_Model.json: motion, position, beacon, failures
"""

import tkinter as tk
from tkinter import ttk, scrolledtext
import json
import os
from datetime import datetime
from train import Train
import subprocess
import sys


class TrackModelTestUI:
    def _check_traffic_light_ahead(self, train_id, line, current_block):
        """Check traffic light in next block and return action needed"""
        try:
            with open(self.track_io_file, "r") as f:
                data = json.load(f)
            prefix = "G" if line == "Green" else "R"
            lights_array = data.get(f"{prefix}-lights", [])
            # Get next block (just 1 block ahead)
            next_blocks = self._get_next_blocks_with_switches(current_block, line, 1)
            if not next_blocks:
                return None  # No action needed
            next_block = next_blocks[0]
            # Check if next block has a traffic light
            if line == "Green":
                traffic_light_blocks = [0, 3, 7, 29, 58, 62, 76, 86, 100, 101, 150, 151]
            else:
                traffic_light_blocks = [0, 8, 14, 26, 31, 37, 42, 51]
            if next_block not in traffic_light_blocks:
                return None  # No traffic light at next block
            # Find traffic light index
            traffic_light_index = traffic_light_blocks.index(next_block)
            bit_index = traffic_light_index * 2
            # Read 2 bits
            if bit_index + 1 < len(lights_array):
                bit1 = lights_array[bit_index]
                bit2 = lights_array[bit_index + 1]
                # Decode: 00=Super Green, 01=Green, 10=Yellow, 11=Red
                if bit1 == 1 and bit2 == 1:
                    return "RED"  # STOP
                elif bit1 == 1 and bit2 == 0:
                    return "YELLOW"  # SLOW DOWN
            return None  # Green or Super Green - no action
        except Exception as e:
            self._print(f"❌ Error checking traffic light: {e}", "#ed4245")
            return None

    def _handle_red_light(self, train_id, line):
        """Stop train immediately for RED light"""
        try:
            prefix = "G" if line == "Green" else "R"
            train_key = f"{prefix}_train_{train_id}"
            array_idx = (train_id - 1) if line == "Green" else (train_id - 4)
            with open(self.track_io_file, "r") as f:
                data = json.load(f)
            # Save original speed if not already saved
            if train_key not in self.saved_authorities:
                current_speed = (
                    data.get(f"{prefix}-Train", {}).get("commanded speed", [])[
                        array_idx
                    ]
                    if array_idx
                    < len(data.get(f"{prefix}-Train", {}).get("commanded speed", []))
                    else 0
                )
                current_auth = (
                    data.get(f"{prefix}-Train", {}).get("commanded authority", [])[
                        array_idx
                    ]
                    if array_idx
                    < len(
                        data.get(f"{prefix}-Train", {}).get("commanded authority", [])
                    )
                    else 0
                )
                self.saved_authorities[train_key] = current_auth
            # Set speed and authority to 0
            if f"{prefix}-Train" not in data:
                data[f"{prefix}-Train"] = {
                    "commanded speed": [],
                    "commanded authority": [],
                }
            while len(data[f"{prefix}-Train"]["commanded speed"]) <= array_idx:
                data[f"{prefix}-Train"]["commanded speed"].append(0)
            while len(data[f"{prefix}-Train"]["commanded authority"]) <= array_idx:
                data[f"{prefix}-Train"]["commanded authority"].append(0)
            data[f"{prefix}-Train"]["commanded speed"][array_idx] = 0
            data[f"{prefix}-Train"]["commanded authority"][array_idx] = 0
            with open(self.track_io_file, "w") as f:
                json.dump(data, f, indent=4)
            self.authority_zeroed[train_key] = True
            self._print(f"🚦 RED LIGHT! Train {train_id} STOPPED", "#ed4245")
        except Exception as e:
            self._print(f"❌ Error stopping for red light: {e}", "#ed4245")

    def _handle_yellow_light(self, train_id, line):
        """Slow down train for YELLOW light"""
        try:
            prefix = "G" if line == "Green" else "R"
            array_idx = (train_id - 1) if line == "Green" else (train_id - 4)
            with open(self.track_io_file, "r") as f:
                data = json.load(f)
            if f"{prefix}-Train" not in data:
                return
            current_speed = (
                data[f"{prefix}-Train"]["commanded speed"][array_idx]
                if array_idx < len(data[f"{prefix}-Train"]["commanded speed"])
                else 0
            )
            # Reduce speed to half
            new_speed = current_speed / 2.0
            data[f"{prefix}-Train"]["commanded speed"][array_idx] = new_speed
            with open(self.track_io_file, "w") as f:
                json.dump(data, f, indent=4)
            self._print(
                f"🚦 YELLOW LIGHT! Train {train_id} slowing to {new_speed:.1f} mph",
                "#faa61a",
            )
        except Exception as e:
            self._print(f"❌ Error slowing for yellow light: {e}", "#ed4245")

        def _check_red_light_ahead(self, train_id, line, current_block):
            """Check if there's a RED light in the next block ahead"""
            try:
                with open(self.track_io_file, "r") as f:
                    data = json.load(f)
                prefix = "G" if line == "Green" else "R"
                lights_array = data.get(f"{prefix}-lights", [])
                # Get next block (just 1 block ahead)
                next_blocks = self._get_next_blocks_with_switches(
                    current_block, line, 1
                )
                if not next_blocks:
                    return False
                next_block = next_blocks[0]
                # Check if next block has a traffic light
                if line == "Green":
                    traffic_light_blocks = [
                        0,
                        3,
                        7,
                        29,
                        58,
                        62,
                        76,
                        86,
                        100,
                        101,
                        150,
                        151,
                    ]
                else:
                    traffic_light_blocks = [0, 8, 14, 26, 31, 37, 42, 51]
                if next_block not in traffic_light_blocks:
                    return False  # No traffic light at next block
                # Find traffic light index
                traffic_light_index = traffic_light_blocks.index(next_block)
                bit_index = traffic_light_index * 2
                # Read 2 bits
                if bit_index + 1 < len(lights_array):
                    bit1 = lights_array[bit_index]
                    bit2 = lights_array[bit_index + 1]
                    # Check if RED (11)
                    if bit1 == 1 and bit2 == 1:
                        return True  # RED LIGHT!
                return False
            except Exception as e:
                self._print(f"❌ Error checking red light: {e}", "#ed4245")
                return False

    def _get_failure_index(self, block_num):
        """Get the failure array index for a given block number (with +1 offset)"""
        return (block_num - 1) * 3

    def __init__(self, root):
        self.root = root
        self.root.title("🚂 TRACK MODEL TEST - ENHANCED")
        self.root.geometry("1600x1000")
        self.root.configure(bg="#2b2d31")

        # Files (use absolute paths)
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.track_io_file = os.path.join(base_dir, "..", "track_io.json")
        self.train_model_file = os.path.join(
            base_dir, "..", "track_model_Train_Model.json"
        )

        # === Traffic light handling state ===
        # Add to __init__ after self.authority_zeroed = {}
        self.saved_speeds = (
            {}
        )  # Store original speeds before red/yellow light: {train_key: speed_value}
        self.speed_reduced = (
            {}
        )  # Track which trains have reduced speed: {train_key: "RED" or "YELLOW"}

        # === Zero out all failures and occupancy at program start ===
        try:
            if os.path.exists(self.track_io_file):
                with open(self.track_io_file, "r") as f:
                    data = json.load(f)
            else:
                data = {}
            # Zero out failures and occupancy for both lines (assuming 152 blocks max)
            for prefix in ["G", "R"]:
                # Failures: 3 bits per block
                arr_len_fail = len(data.get(f"{prefix}-Failures", []))
                if arr_len_fail < 1:
                    arr_len_fail = 456
                data[f"{prefix}-Failures"] = [0] * arr_len_fail
                # Occupancy: 1 bit per block
                arr_len_occ = len(data.get(f"{prefix}-Occupancy", []))
                if arr_len_occ < 1:
                    arr_len_occ = 152
                data[f"{prefix}-Occupancy"] = [0] * arr_len_occ
            with open(self.track_io_file, "w") as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            print(f"❌ Error zeroing failures/occupancy at startup: {e}")

        # === Failure handling state ===
        # Store original authority before zeroing: {train_key: authority_value}
        self.saved_authorities = {}
        # Track which trains have zeroed authority: {train_key: True/False}
        self.authority_zeroed = {}

        # === Green Line topology exceptions (non-sequential blocks) ===
        self.GREEN_EXCEPTIONS = {
            100: 85,  # 100 → 85 (not 101)
            150: 28,  # 150 → 28 (reverse direction)
            # Switches handled by branch points
        }

        # === Red Line topology exceptions ===
        self.RED_EXCEPTIONS = {
            # Red line is mostly sequential, switches handled separately
        }

        # === Store current switch state ===
        self.current_switch_settings = {
            "Green": {},  # {block_num: target_block}
            "Red": {},
        }

        # === Track last known block for each train (for occupancy assignment) ===
        self.train_last_known_blocks = {
            "G_train_1": 0,
            "G_train_2": 0,
            "G_train_3": 0,
            "R_train_4": 0,
            "R_train_5": 0,
        }

        # Initialize train physics engines
        self.trains = {}
        for i in range(1, 4):  # Green Line trains 1, 2, 3
            train = Train(i, "Green", self.train_model_file)
            train.start()
            self.trains[f"G_train_{i}"] = train

        for i in range(4, 6):  # Red Line trains 4, 5
            train = Train(i, "Red", self.train_model_file)
            train.start()
            self.trains[f"R_train_{i}"] = train

        # Save reference to all train objects
        self.train_objects = list(self.trains.values())

        # Line-specific configurations
        self.GREEN_SWITCHES = [
            {"block": 13, "label": "S0: Block 13", "targets": ["12", "14"]},
            {"block": 28, "label": "S1: Block 28", "targets": ["29", "27"]},
            {"block": 57, "label": "S2: Block 57", "targets": ["58", "Yard"]},
            {"block": 63, "label": "S3: Block 63", "targets": ["64", "Yard"]},
            {"block": 77, "label": "S4: Block 77", "targets": ["78", "101"]},
            {"block": 86, "label": "S5: Block 86", "targets": ["85", "87"]},
        ]

        self.RED_SWITCHES = [
            {"block": 9, "label": "S0: Block 9", "targets": ["10", "Yard"]},
            {"block": 16, "label": "S1: Block 16", "targets": ["17", "1"]},
            {"block": 27, "label": "S2: Block 27", "targets": ["28", "76"]},
            {"block": 33, "label": "S3: Block 33", "targets": ["34", "72"]},
            {"block": 38, "label": "S4: Block 38", "targets": ["39", "71"]},
            {"block": 44, "label": "S5: Block 44", "targets": ["45", "67"]},
            {"block": 52, "label": "S6: Block 52", "targets": ["53", "66"]},
        ]

        self.GREEN_LIGHTS = [
            {"block": 0, "label": "Yard"},
            {"block": 3, "label": "Block 3"},
            {"block": 7, "label": "Block 7"},
            {"block": 29, "label": "Block 29"},
            {"block": 58, "label": "Block 58"},
            {"block": 62, "label": "Block 62"},
            {"block": 76, "label": "Block 76"},
            {"block": 86, "label": "Block 86"},
            {"block": 100, "label": "Block 100"},
            {"block": 101, "label": "Block 101"},
            {"block": 150, "label": "Block 150"},
            {"block": 151, "label": "Block 151"},
        ]

        self.RED_LIGHTS = [
            {"block": 0, "label": "Yard"},
            {"block": 8, "label": "Block 8"},
            {"block": 14, "label": "Block 14"},
            {"block": 26, "label": "Block 26"},
            {"block": 31, "label": "Block 31"},
            {"block": 37, "label": "Block 37"},
            {"block": 42, "label": "Block 42"},
            {"block": 51, "label": "Block 51"},
        ]

        self.GREEN_CROSSINGS = [19, 57]
        self.RED_CROSSINGS = [47]

        self.LIGHT_OPTIONS = [
            ("Super Green", "#00ff00"),
            ("Green", "#3ba55d"),
            ("Yellow", "#faa61a"),
            ("Red", "#ed4245"),
        ]

        # Build UI
        self._build_ui()

        # Start monitoring outputs
        self._monitor_outputs()

        # Launch Track Model UI (after console is initialized)
        self._launch_track_model_ui()

    def _update_train_blocks_from_occupancy(self, line):
        """
        Read occupancy array and assign occupied blocks to trains based on proximity.
        Updates train_last_known_blocks for the given line.
        """
        try:
            with open(self.track_io_file, "r") as f:
                data = json.load(f)
            prefix = "G" if line == "Green" else "R"
            occupancy_array = data.get(f"{prefix}-Occupancy", [])
            # Find all occupied blocks
            occupied_blocks = []
            for block_num, occupied in enumerate(occupancy_array):
                if occupied == 1:
                    occupied_blocks.append(block_num)
            if not occupied_blocks:
                return  # No trains on track
            # Get trains for this line
            if line == "Green":
                train_keys = ["G_train_1", "G_train_2", "G_train_3"]
            else:
                train_keys = ["R_train_4", "R_train_5"]
            # Assign each occupied block to nearest train based on last known position
            for block_num in occupied_blocks:
                closest_train = None
                min_distance = float("inf")
                for train_key in train_keys:
                    last_block = self.train_last_known_blocks.get(train_key, 0)
                    distance = abs(block_num - last_block)
                    if distance < min_distance:
                        min_distance = distance
                        closest_train = train_key
                # Update closest train's position
                if closest_train:
                    self.train_last_known_blocks[closest_train] = block_num
        except Exception as e:
            pass

    def _launch_track_model_ui(self):
        """Launch Track Model UI in separate process"""
        try:
            # Get path to Track Model UI
            track_model_ui_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "Track_Model",
                "Track_Model_UI.py",
            )
            if os.path.exists(track_model_ui_path):
                # Launch in separate process
                subprocess.Popen([sys.executable, track_model_ui_path])
                self._print("🚂 Track Model UI launched", "#5865f2")
            else:
                self._print(
                    f"⚠️ Track Model UI not found at: {track_model_ui_path}", "#faa61a"
                )
        except Exception as e:
            self._print(f"❌ Failed to launch Track Model UI: {e}", "#ed4245")

    def cleanup(self):
        """Stop all trains and clear all inputs before closing"""
        # Clear failure handling state
        self.saved_authorities.clear()
        self.authority_zeroed.clear()

        for train in self.trains.values():
            train.stop()

        # Clear all train, switch, gate, and light inputs in track_io.json
        try:
            # Clear track_io.json
            if os.path.exists(self.track_io_file):
                with open(self.track_io_file, "r") as f:
                    data = json.load(f)
            else:
                data = {}

            for prefix in ["G", "R"]:
                data[f"{prefix}-Train"] = {
                    "commanded speed": [0, 0, 0],
                    "commanded authority": [0, 0, 0],
                }
                data[f"{prefix}-switches"] = [0] * 7
                data[f"{prefix}-gates"] = [1] * 2
                data[f"{prefix}-lights"] = [0, 1] * 8

            with open(self.track_io_file, "w") as f:
                json.dump(data, f, indent=4)

            # Clear commanded speed/authority and position in track_model_Train_Model.json
            if os.path.exists(self.train_model_file):
                with open(self.train_model_file, "r") as f:
                    model_data = json.load(f)
                for train_key, train_val in model_data.items():
                    if "block" in train_val:
                        train_val["block"]["commanded speed"] = 0
                        train_val["block"]["commanded authority"] = 0
                    if "motion" in train_val:
                        train_val["motion"]["position_yds"] = 0.0
                        if "yards_into_current_block" in train_val["motion"]:
                            train_val["motion"]["yards_into_current_block"] = 0.0
                with open(self.train_model_file, "w") as f:
                    json.dump(model_data, f, indent=4)
            # Also clear static.json (track_model_static.json)
            static_json_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "..",
                "track_model_static.json",
            )
            try:
                with open(static_json_path, "w") as f:
                    json.dump({}, f, indent=4)
            except Exception as e:
                self._print(f"❌ ERROR clearing static.json on close: {e}", "#ed4245")
        except Exception as e:
            self._print(f"❌ ERROR clearing inputs on close: {e}", "#ed4245")

    def _build_ui(self):
        """Build interface"""
        # Header
        header = tk.Frame(self.root, bg="#1e1f22", height=60)
        header.pack(fill="x", padx=10, pady=10)
        header.pack_propagate(False)

        tk.Label(
            header,
            text="🚂 TRACK MODEL TEST - ENHANCED WITH LINE-SPECIFIC CONTROLS",
            font=("Segoe UI", 16, "bold"),
            bg="#1e1f22",
            fg="#5865f2",
        ).pack(pady=5)

        # Main container
        main = tk.Frame(self.root, bg="#2b2d31")
        main.pack(fill="both", expand=True, padx=10, pady=5)
        main.grid_columnconfigure(0, weight=1)
        main.grid_columnconfigure(1, weight=1)
        main.grid_rowconfigure(0, weight=1)

        # Left: INPUTS
        self._build_inputs(main)

        # Right: OUTPUTS
        self._build_outputs(main)

        # Bottom: Console Log
        self._build_console(main)

    def _build_inputs(self, parent):
        """Build input controls"""
        left = tk.LabelFrame(
            parent,
            text="📤 INPUTS → track_io.json (WRITE)",
            font=("Segoe UI", 12, "bold"),
            bg="#313338",
            fg="#ffffff",
            relief="solid",
            bd=2,
        )
        left.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)

        # Scrollable frame
        canvas = tk.Canvas(left, bg="#313338", highlightthickness=0)
        scrollbar = tk.Scrollbar(left, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg="#313338")

        scrollable_frame.bind(
            "<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True, padx=5, pady=5)
        scrollbar.pack(side="right", fill="y")

        # Speed & Pause controls
        control_frame = tk.Frame(scrollable_frame, bg="#313338")
        control_frame.pack(fill="x", padx=10, pady=10)

        tk.Label(
            control_frame,
            text="Simulation Speed:",
            font=("Segoe UI", 11, "bold"),
            bg="#313338",
            fg="#ffffff",
        ).pack(side="left", padx=5)

        self.speed_var = tk.StringVar(value="1x")
        for speed in ["1x", "5x", "10x"]:
            tk.Radiobutton(
                control_frame,
                text=speed,
                variable=self.speed_var,
                value=speed,
                font=("Segoe UI", 10),
                bg="#313338",
                fg="#ffffff",
                selectcolor="#5865f2",
                activebackground="#313338",
                command=self._change_speed,
            ).pack(side="left", padx=5)

        self.pause_btn = tk.Button(
            control_frame,
            text="⏸️ PAUSE",
            font=("Segoe UI", 10, "bold"),
            bg="#faa61a",
            fg="white",
            command=self._toggle_pause,
            cursor="hand2",
            relief="flat",
            width=10,
        )
        self.pause_btn.pack(side="left", padx=10)
        self.is_paused = False

        # Train Selection
        train_frame = tk.Frame(scrollable_frame, bg="#313338")
        train_frame.pack(fill="x", padx=10, pady=10)

        tk.Label(
            train_frame,
            text="Train:",
            font=("Segoe UI", 11, "bold"),
            bg="#313338",
            fg="#ffffff",
        ).pack(side="left", padx=5)

        self.train_var = tk.StringVar(value="1")
        for i in range(1, 6):
            tk.Radiobutton(
                train_frame,
                text=f"Train {i}",
                variable=self.train_var,
                value=str(i),
                font=("Segoe UI", 10),
                bg="#313338",
                fg="#ffffff",
                selectcolor="#5865f2",
                activebackground="#313338",
                activeforeground="#ffffff",
            ).pack(side="left", padx=5)

        # Line Selection
        line_frame = tk.Frame(scrollable_frame, bg="#313338")
        line_frame.pack(fill="x", padx=10, pady=5)

        tk.Label(
            line_frame,
            text="Line:",
            font=("Segoe UI", 11, "bold"),
            bg="#313338",
            fg="#ffffff",
        ).pack(side="left", padx=5)

        self.line_var = tk.StringVar(value="Green")
        tk.Radiobutton(
            line_frame,
            text="Green Line",
            variable=self.line_var,
            value="Green",
            font=("Segoe UI", 10),
            bg="#313338",
            fg="#ffffff",
            selectcolor="#3ba55d",
            activebackground="#313338",
            command=self._on_line_change,
        ).pack(side="left", padx=5)

        tk.Radiobutton(
            line_frame,
            text="Red Line",
            variable=self.line_var,
            value="Red",
            font=("Segoe UI", 10),
            bg="#313338",
            fg="#ffffff",
            selectcolor="#ed4245",
            activebackground="#313338",
            command=self._on_line_change,
        ).pack(side="left", padx=5)

        # Separator
        tk.Frame(scrollable_frame, bg="#5865f2", height=2).pack(
            fill="x", padx=10, pady=10
        )

        # Commanded Speed
        speed_frame = tk.Frame(scrollable_frame, bg="#313338")
        speed_frame.pack(fill="x", padx=10, pady=10)

        tk.Label(
            speed_frame,
            text="Commanded Speed (mph):",
            font=("Segoe UI", 11, "bold"),
            bg="#313338",
            fg="#ffffff",
            width=25,
            anchor="w",
        ).pack(side="left")

        self.speed_entry = tk.Entry(
            speed_frame,
            font=("Segoe UI", 14, "bold"),
            width=10,
            bg="#1e1f22",
            fg="#00d9ff",
            insertbackground="#00d9ff",
        )
        self.speed_entry.insert(0, "0")
        self.speed_entry.pack(side="left", padx=5)

        # Commanded Authority
        auth_frame = tk.Frame(scrollable_frame, bg="#313338")
        auth_frame.pack(fill="x", padx=10, pady=10)

        tk.Label(
            auth_frame,
            text="Commanded Authority (yds):",
            font=("Segoe UI", 11, "bold"),
            bg="#313338",
            fg="#ffffff",
            width=25,
            anchor="w",
        ).pack(side="left")

        self.auth_entry = tk.Entry(
            auth_frame,
            font=("Segoe UI", 14, "bold"),
            width=10,
            bg="#1e1f22",
            fg="#00d9ff",
            insertbackground="#00d9ff",
        )
        self.auth_entry.insert(0, "0")
        self.auth_entry.pack(side="left", padx=5)

        # Separator
        tk.Frame(scrollable_frame, bg="#5865f2", height=2).pack(
            fill="x", padx=10, pady=15
        )

        # Container for switches (will be rebuilt on line change)
        self.switches_container = tk.Frame(scrollable_frame, bg="#313338")
        self.switches_container.pack(fill="x", padx=10, pady=5)

        # Container for lights (will be rebuilt on line change)
        self.lights_container = tk.Frame(scrollable_frame, bg="#313338")
        self.lights_container.pack(fill="x", padx=10, pady=5)

        # Container for gates (will be rebuilt on line change)
        self.gates_container = tk.Frame(scrollable_frame, bg="#313338")
        self.gates_container.pack(fill="x", padx=10, pady=5)

        # Build initial controls
        self._rebuild_line_controls()

        # Separator
        tk.Frame(scrollable_frame, bg="#5865f2", height=2).pack(
            fill="x", padx=10, pady=15
        )

        # DISPATCH BUTTON
        tk.Button(
            scrollable_frame,
            text="🚀 SEND ALL INPUTS TO TRACK MODEL",
            font=("Segoe UI", 14, "bold"),
            bg="#3ba55d",
            fg="white",
            command=self._send_inputs,
            cursor="hand2",
            relief="flat",
            height=2,
        ).pack(fill="x", padx=10, pady=10)

        # Quick actions
        btn_frame = tk.Frame(scrollable_frame, bg="#313338")
        btn_frame.pack(fill="x", padx=10, pady=5)

        tk.Button(
            btn_frame,
            text="⏹️ STOP (Speed=0, Auth=0)",
            font=("Segoe UI", 10, "bold"),
            bg="#ed4245",
            fg="white",
            command=self._stop_train,
            cursor="hand2",
            relief="flat",
        ).pack(side="left", fill="x", expand=True, padx=2)

        tk.Button(
            btn_frame,
            text="🔄 RESET ALL",
            font=("Segoe UI", 10, "bold"),
            bg="#faa61a",
            fg="white",
            command=self._reset_inputs,
            cursor="hand2",
            relief="flat",
        ).pack(side="left", fill="x", expand=True, padx=2)

    def _change_speed(self):
        speed_str = self.speed_var.get()
        multiplier = float(speed_str.replace("x", ""))
        for train in self.train_objects:
            train.set_speed_multiplier(multiplier)
        self._print(f"⚡ Simulation speed set to {speed_str}", "#faa61a")

    def _toggle_pause(self):
        self.is_paused = not self.is_paused
        if self.is_paused:
            for train in self.train_objects:
                train.pause()
            self.pause_btn.config(text="▶️ RESUME", bg="#3ba55d")
            self._print("⏸️ Simulation PAUSED", "#faa61a")
        else:
            for train in self.train_objects:
                train.resume()
            self.pause_btn.config(text="⏸️ PAUSE", bg="#faa61a")
            self._print("▶️ Simulation RESUMED", "#3ba55d")

    def _on_line_change(self):
        """Called when line selection changes"""
        self._print(f"📍 Switched to {self.line_var.get()} Line", "#5865f2")
        self._rebuild_line_controls()

    def _rebuild_line_controls(self):
        """Rebuild switches, lights, and gates based on selected line"""
        # Clear existing controls
        for widget in self.switches_container.winfo_children():
            widget.destroy()
        for widget in self.lights_container.winfo_children():
            widget.destroy()
        for widget in self.gates_container.winfo_children():
            widget.destroy()

        line = self.line_var.get()

        # Build SWITCHES
        tk.Label(
            self.switches_container,
            text=f"🔀 SWITCHES ({line} Line has {len(self.GREEN_SWITCHES if line == 'Green' else self.RED_SWITCHES)})",
            font=("Segoe UI", 11, "bold"),
            bg="#313338",
            fg="#5865f2",
        ).pack(pady=5)

        switch_grid = tk.Frame(self.switches_container, bg="#313338")
        switch_grid.pack(fill="x", pady=5)

        switches = self.GREEN_SWITCHES if line == "Green" else self.RED_SWITCHES
        self.switch_vars = []

        for i, sw in enumerate(switches):
            frame = tk.Frame(switch_grid, bg="#1e1f22", relief="solid", bd=1)
            frame.grid(row=i // 2, column=i % 2, padx=5, pady=5, sticky="ew")

            tk.Label(
                frame,
                text=sw["label"],
                font=("Segoe UI", 9),
                bg="#1e1f22",
                fg="#b5bac1",
            ).pack(anchor="w", padx=5, pady=2)

            var = tk.StringVar(value="0")
            combo = ttk.Combobox(
                frame,
                textvariable=var,
                values=[f"→ {target}" for target in sw["targets"]],
                state="readonly",
                width=15,
                font=("Segoe UI", 9),
            )
            combo.current(0)
            combo.pack(padx=5, pady=5, fill="x")
            self.switch_vars.append(var)

        switch_grid.columnconfigure(0, weight=1)
        switch_grid.columnconfigure(1, weight=1)

        # Separator
        tk.Frame(self.switches_container, bg="#5865f2", height=2).pack(
            fill="x", pady=10
        )

        # Build TRAFFIC LIGHTS
        tk.Label(
            self.lights_container,
            text=f"🚦 TRAFFIC LIGHTS ({line} Line has {len(self.GREEN_LIGHTS if line == 'Green' else self.RED_LIGHTS)})",
            font=("Segoe UI", 11, "bold"),
            bg="#313338",
            fg="#5865f2",
        ).pack(pady=5)

        lights_grid = tk.Frame(self.lights_container, bg="#313338")
        lights_grid.pack(fill="x", pady=5)

        lights = self.GREEN_LIGHTS if line == "Green" else self.RED_LIGHTS
        self.light_vars = []

        for i, light in enumerate(lights):
            frame = tk.Frame(lights_grid, bg="#1e1f22", relief="solid", bd=1)
            frame.grid(row=i // 2, column=i % 2, padx=5, pady=5, sticky="ew")

            tk.Label(
                frame,
                text=light["label"],
                font=("Segoe UI", 9),
                bg="#1e1f22",
                fg="#b5bac1",
            ).pack(anchor="w", padx=5, pady=2)

            var = tk.StringVar(value="Green")
            combo = ttk.Combobox(
                frame,
                textvariable=var,
                values=[opt[0] for opt in self.LIGHT_OPTIONS],
                state="readonly",
                width=15,
                font=("Segoe UI", 9),
            )
            combo.current(1)  # Default to Green
            combo.pack(padx=5, pady=5, fill="x")
            self.light_vars.append(var)

        lights_grid.columnconfigure(0, weight=1)
        lights_grid.columnconfigure(1, weight=1)

        # Separator
        tk.Frame(self.lights_container, bg="#5865f2", height=2).pack(fill="x", pady=10)

        # Build CROSSING GATES
        crossings = self.GREEN_CROSSINGS if line == "Green" else self.RED_CROSSINGS

        tk.Label(
            self.gates_container,
            text=f"🚧 CROSSING GATES (0=Down, 1=Up)",
            font=("Segoe UI", 11, "bold"),
            bg="#313338",
            fg="#5865f2",
        ).pack(pady=5)

        gates_grid = tk.Frame(self.gates_container, bg="#313338")
        gates_grid.pack(fill="x", pady=5)

        self.gate_vars = []

        for i, block in enumerate(crossings):
            frame = tk.Frame(gates_grid, bg="#1e1f22", relief="solid", bd=1)
            frame.grid(row=0, column=i, padx=5, pady=5, sticky="ew")

            tk.Label(
                frame,
                text=f"Block {block}",
                font=("Segoe UI", 9),
                bg="#1e1f22",
                fg="#b5bac1",
            ).pack(anchor="w", padx=5, pady=2)

            var = tk.StringVar(value="Up (Open)")
            combo = ttk.Combobox(
                frame,
                textvariable=var,
                values=["Down (Closed)", "Up (Open)"],
                state="readonly",
                width=15,
                font=("Segoe UI", 9),
            )
            combo.current(1)  # Default to Up
            combo.pack(padx=5, pady=5, fill="x")
            self.gate_vars.append(var)

        for i in range(len(crossings)):
            gates_grid.columnconfigure(i, weight=1)

        # Initialize switch settings to default (first target)
        switches = self.GREEN_SWITCHES if line == "Green" else self.RED_SWITCHES
        for sw in switches:
            # Default to first target
            default_target = sw["targets"][0]
            if default_target == "Yard":
                default_target = 0
            else:
                default_target = int(default_target)
            self.current_switch_settings[line][sw["block"]] = default_target

    def _build_outputs(self, parent):
        """Build output display"""
        right = tk.LabelFrame(
            parent,
            text="📥 OUTPUTS ← track_model_Train_Model.json (READ ONLY)",
            font=("Segoe UI", 12, "bold"),
            bg="#313338",
            fg="#ffffff",
            relief="solid",
            bd=2,
        )
        right.grid(row=0, column=1, sticky="nsew", padx=5, pady=5)

        # Output labels
        self.output_labels = {}

        outputs = [
            ("Current Motion:", "motion"),
            ("Position (yards):", "position"),
            ("Commanded Speed (mph):", "cmd_speed"),
            ("Commanded Authority (yds):", "cmd_auth"),
            ("", ""),
            ("Beacon - Speed Limit (km/h):", "beacon_limit"),
            ("Beacon - Side Door:", "beacon_door"),
            ("Beacon - Current Station:", "beacon_curr"),
            ("Beacon - Next Station:", "beacon_next"),
            ("Beacon - Passengers:", "beacon_pass"),
            ("", ""),
            ("Failures Detected:", "failures"),
        ]

        for label_text, key in outputs:
            if not label_text:
                tk.Frame(right, bg="#5865f2", height=2).pack(fill="x", padx=10, pady=10)
                continue

            frame = tk.Frame(right, bg="#313338")
            frame.pack(fill="x", padx=10, pady=8)

            tk.Label(
                frame,
                text=label_text,
                font=("Segoe UI", 10, "bold"),
                bg="#313338",
                fg="#ffffff",
                width=28,
                anchor="w",
            ).pack(side="left")

            label = tk.Label(
                frame,
                text="N/A",
                font=("Segoe UI", 12, "bold"),
                bg="#1e1f22",
                fg="#00d9ff",
                width=18,
                anchor="w",
                relief="solid",
                bd=1,
            )
            label.pack(side="left", padx=5, fill="x", expand=True)

            self.output_labels[key] = label

    def _build_console(self, parent):
        """Build console log"""
        console_frame = tk.LabelFrame(
            parent,
            text="📋 CONSOLE LOG (All Actions & Events)",
            font=("Segoe UI", 11, "bold"),
            bg="#313338",
            fg="#ffffff",
            relief="solid",
            bd=2,
        )
        console_frame.grid(row=1, column=0, columnspan=2, sticky="ew", padx=5, pady=5)

        self.console = scrolledtext.ScrolledText(
            console_frame,
            height=12,
            bg="#0d0e0f",
            fg="#00ff00",
            font=("Consolas", 9),
            wrap="word",
        )
        self.console.pack(fill="both", expand=True, padx=5, pady=5)

        self._print("🟢 Track Model Test UI initialized")
        self._print(f"📁 Writing inputs to: {self.track_io_file}")
        self._print(f"📁 Reading outputs from: {self.train_model_file}")
        self._print("")
        self._print("ℹ️  Enhanced with line-specific switch, light, and gate controls")

    def _print(self, message, color=None):
        """Print to console with timestamp"""
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        line = f"[{timestamp}] {message}\n"

        if color:
            tag = f"color_{color}"
            self.console.tag_config(tag, foreground=color)
            self.console.insert("end", line, tag)
        else:
            self.console.insert("end", line)

        self.console.see("end")

    def _send_inputs(self):
        """Write all inputs to track_io.json"""
        try:
            train_id = int(self.train_var.get())
            line = self.line_var.get()
            speed = float(self.speed_entry.get())
            authority = float(self.auth_entry.get())
            with open(self.track_io_file, "r") as f:
                data = json.load(f)
            prefix = "G" if line == "Green" else "R"

            # === COMMANDED SPEED & AUTHORITY ===
            if line == "Green":
                array_idx = train_id - 1
            else:
                array_idx = train_id - 4

            if f"{prefix}-Train" not in data:
                data[f"{prefix}-Train"] = {
                    "commanded speed": [],
                    "commanded authority": [],
                }

            while len(data[f"{prefix}-Train"]["commanded speed"]) <= array_idx:
                data[f"{prefix}-Train"]["commanded speed"].append(0)
            while len(data[f"{prefix}-Train"]["commanded authority"]) <= array_idx:
                data[f"{prefix}-Train"]["commanded authority"].append(0)

            data[f"{prefix}-Train"]["commanded speed"][array_idx] = speed
            data[f"{prefix}-Train"]["commanded authority"][array_idx] = authority

            # === SWITCHES - STORE LOCALLY ===
            switches = []
            switch_blocks = (
                self.GREEN_SWITCHES if line == "Green" else self.RED_SWITCHES
            )
            for i, sw in enumerate(switch_blocks):
                if i < len(self.switch_vars):
                    var_value = self.switch_vars[i].get()
                    # Parse target from "→ target" format
                    if "→" in var_value:
                        target_str = var_value.split("→")[1].strip()
                        # Convert "Yard" to 0
                        if target_str.lower() == "yard":
                            target = 0
                        else:
                            target = int(target_str)
                        # STORE the switch setting locally
                        self.current_switch_settings[line][sw["block"]] = target
                        # Fix: compare int to int for switch_pos
                        first_target_str = sw["targets"][0]
                        if first_target_str.lower() == "yard":
                            first_target = 0
                        else:
                            first_target = int(first_target_str)
                        switch_pos = 0 if target == first_target else 1
                        switches.append(switch_pos)
            data[f"{prefix}-switches"] = switches

            # === GATES ===
            gates = []
            for var in self.gate_vars:
                val = var.get()
                gates.append(0 if "Down" in val else 1)

            data[f"{prefix}-gates"] = gates

            # === LIGHTS ===
            lights_array = []
            for var in self.light_vars:
                val = var.get()
                if val == "Super Green":
                    lights_array.extend([0, 0])
                elif val == "Green":
                    lights_array.extend([0, 1])
                elif val == "Yellow":
                    lights_array.extend([1, 0])
                elif val == "Red":
                    lights_array.extend([1, 1])

            data[f"{prefix}-lights"] = lights_array

            # Write back to file
            with open(self.track_io_file, "w") as f:
                json.dump(data, f, indent=4)

            self._print(f"✅ INPUTS SENT TO TRACK MODEL:", "#3ba55d")
            self._print(
                f"   Train {train_id} ({line} Line): Speed={speed} mph, Authority={authority} yds"
            )
            self._print(f"   Switches: {switches}")
            self._print(f"   Gates: {gates}")
            self._print(
                f"   Lights: {lights_array[:16]}... ({len(lights_array)} bits total)"
            )
            self._print("")

        except Exception as e:
            self._print(f"❌ ERROR sending inputs: {e}", "#ed4245")

    def _stop_train(self):
        """Stop train by setting speed/authority to 0"""
        self.speed_entry.delete(0, "end")
        self.speed_entry.insert(0, "0")
        self.auth_entry.delete(0, "end")
        self.auth_entry.insert(0, "0")
        self._send_inputs()
        self._print(f"⏹️ STOP command sent", "#ed4245")

    def _reset_inputs(self):
        """Reset all inputs"""
        self.speed_entry.delete(0, "end")
        self.speed_entry.insert(0, "0")
        self.auth_entry.delete(0, "end")
        self.auth_entry.insert(0, "0")
        self._rebuild_line_controls()
        self._print("🔄 All inputs reset", "#faa61a")

    def _get_next_blocks(self, current_block, line, num_blocks=2):
        """Get next N blocks ahead based on topology (ignores switch positions)"""
        next_blocks = []
        block = current_block
        for _ in range(num_blocks):
            exceptions = (
                self.GREEN_EXCEPTIONS if line == "Green" else self.RED_EXCEPTIONS
            )
            if block in exceptions:
                block = exceptions[block]
            else:
                block = block + 1
            next_blocks.append(block)
        return next_blocks

    def _get_next_blocks_with_switches(
        self, current_block, line, previous_block=None, num_blocks=2
    ):
        """Get next blocks based on switches WE set (stored locally) AND direction"""
        switch_settings = self.current_switch_settings.get(line, {})
        next_blocks = []
        block = current_block
        prev = previous_block
        for _ in range(num_blocks):
            if line == "Green":
                next_block = self._get_green_line_next_block_logic(block, prev)
            else:
                next_block = self._get_red_line_next_block_logic(block, prev)
            next_blocks.append(next_block)
            prev = block
            block = next_block
        return next_blocks

    # Example placeholder for routing logic (replace with your actual logic)
    def _get_green_line_next_block_logic(self, current, previous):
        # TODO: Implement actual routing logic using current and previous
        # For now, fallback to switch or +1
        switch_settings = self.current_switch_settings.get("Green", {})
        if current in switch_settings:
            return switch_settings[current]
        return current + 1

    def _get_red_line_next_block_logic(self, current, previous):
        # TODO: Implement actual routing logic using current and previous
        switch_settings = self.current_switch_settings.get("Red", {})
        if current in switch_settings:
            return switch_settings[current]
        return current + 1

    def _check_failures_ahead(self, train_id, line, current_block):
        """Check if there are failures in next 2 blocks"""
        try:
            with open(self.track_io_file, "r") as f:
                data = json.load(f)
            prefix = "G" if line == "Green" else "R"
            failures_array = data.get(f"{prefix}-Failures", [])
            # DEBUG
            print(
                f"🔍 Checking failures for Train {train_id}, current block {current_block}"
            )
            train_key = f"{line[0]}_train_{train_id}"
            previous_block = self.train_last_known_blocks.get(train_key, None)
            next_blocks = self._get_next_blocks_with_switches(
                current_block, line, previous_block, 2
            )
            # print(f"🔍 Next blocks to check: {next_blocks}")
            for block_num in next_blocks:
                idx = self._get_failure_index(block_num)
                if idx + 2 < len(failures_array):
                    failure_bits = failures_array[idx : idx + 3]
                    # print(f"🔍 Block {block_num} (idx {idx}): bits={failure_bits}")
                    if any(failure_bits):
                        # print(f"🔍 FAILURE FOUND in block {block_num}!")
                        return True
            # print(f"🔍 No failures detected")
            return False
        except Exception as e:
            self._print(f"🔍 CHECK FAILURE ERROR: {e}", "#ed4245")
            return False

    def _handle_red_light(self, train_id, line):
        """Stop train immediately for RED light (speed only, not authority)"""
        try:
            prefix = "G" if line == "Green" else "R"
            train_key = f"{prefix}_train_{train_id}"
            array_idx = (train_id - 1) if line == "Green" else (train_id - 4)
            # Only act if not already stopped for red light
            if self.speed_reduced.get(train_key) == "RED":
                return  # Already stopped for red light
            with open(self.track_io_file, "r") as f:
                data = json.load(f)
            # Save original speed
            current_speed = (
                data.get(f"{prefix}-Train", {}).get("commanded speed", [])[array_idx]
                if array_idx
                < len(data.get(f"{prefix}-Train", {}).get("commanded speed", []))
                else 0
            )
            self.saved_speeds[train_key] = current_speed
            # Set speed to 0 ONLY (not authority!)
            if f"{prefix}-Train" not in data:
                data[f"{prefix}-Train"] = {
                    "commanded speed": [],
                    "commanded authority": [],
                }
            while len(data[f"{prefix}-Train"]["commanded speed"]) <= array_idx:
                data[f"{prefix}-Train"]["commanded speed"].append(0)
            data[f"{prefix}-Train"]["commanded speed"][array_idx] = 0
            with open(self.track_io_file, "w") as f:
                json.dump(data, f, indent=4)
            self.speed_reduced[train_key] = "RED"
            self._print(f"🚦 RED LIGHT! Train {train_id} STOPPED (speed=0)", "#ed4245")
        except Exception as e:
            self._print(f"❌ Error stopping for red light: {e}", "#ed4245")

    def _handle_yellow_light(self, train_id, line):
        """Slow down train for YELLOW light"""
        try:
            prefix = "G" if line == "Green" else "R"
            train_key = f"{prefix}_train_{train_id}"
            array_idx = (train_id - 1) if line == "Green" else (train_id - 4)
            # Only act if not already slowed
            if self.speed_reduced.get(train_key) == "YELLOW":
                return  # Already slowed for yellow
            with open(self.track_io_file, "r") as f:
                data = json.load(f)
            if f"{prefix}-Train" not in data:
                return
            current_speed = (
                data[f"{prefix}-Train"]["commanded speed"][array_idx]
                if array_idx < len(data[f"{prefix}-Train"]["commanded speed"])
                else 0
            )
            # Save original speed and reduce to half
            self.saved_speeds[train_key] = current_speed
            new_speed = current_speed / 2.0
            data[f"{prefix}-Train"]["commanded speed"][array_idx] = new_speed
            with open(self.track_io_file, "w") as f:
                json.dump(data, f, indent=4)
            self.speed_reduced[train_key] = "YELLOW"
            self._print(
                f"🚦 YELLOW LIGHT! Train {train_id} slowing to {new_speed:.1f} mph",
                "#faa61a",
            )
        except Exception as e:
            self._print(f"❌ Error slowing for yellow light: {e}", "#ed4245")

    def _restore_speed_after_light(self, train_id, line):
        """Restore original speed when light clears (GREEN or Super GREEN)"""
        try:
            prefix = "G" if line == "Green" else "R"
            train_key = f"{prefix}_train_{train_id}"
            array_idx = (train_id - 1) if line == "Green" else (train_id - 4)
            if train_key not in self.saved_speeds:
                return  # No saved speed to restore
            with open(self.track_io_file, "r") as f:
                data = json.load(f)
            restored_speed = self.saved_speeds[train_key]
            if f"{prefix}-Train" not in data:
                data[f"{prefix}-Train"] = {
                    "commanded speed": [],
                    "commanded authority": [],
                }
            while len(data[f"{prefix}-Train"]["commanded speed"]) <= array_idx:
                data[f"{prefix}-Train"]["commanded speed"].append(0)
            data[f"{prefix}-Train"]["commanded speed"][array_idx] = restored_speed
            with open(self.track_io_file, "w") as f:
                json.dump(data, f, indent=4)
            del self.saved_speeds[train_key]
            del self.speed_reduced[train_key]
            self._print(
                f"✅ Light CLEARED! Train {train_id} speed restored to {restored_speed:.1f} mph",
                "#3ba55d",
            )
        except Exception as e:
            self._print(f"❌ Error restoring speed: {e}", "#ed4245")
            while len(data[f"{prefix}-Train"]["commanded authority"]) <= array_idx:
                data[f"{prefix}-Train"]["commanded authority"].append(0)
            restored_auth = self.saved_authorities[train_key]
            data[f"{prefix}-Train"]["commanded authority"][array_idx] = restored_auth
            with open(self.track_io_file, "w") as f:
                json.dump(data, f, indent=4)
            del self.saved_authorities[train_key]
            self.authority_zeroed[train_key] = False
            self._print(
                f"✅ Authority RESTORED to {restored_auth} yds for Train {train_id} (failure cleared)",
                "#3ba55d",
            )
            # print(f"🔍 RESTORE: Authority restored successfully!", "#3ba55d")
        except Exception as e:
            self._print(f"❌ Error restoring authority: {e}", "#ed4245")

    def _monitor_outputs(self):
        """Monitor outputs from track_model_Train_Model.json"""
        try:
            train_id = int(self.train_var.get())
            line = self.line_var.get()

            # Update all train blocks from occupancy first
            self._update_train_blocks_from_occupancy(line)

            if os.path.exists(self.train_model_file):
                with open(self.train_model_file, "r") as f:
                    data = json.load(f)

                prefix = "G" if line == "Green" else "R"
                train_key = f"{prefix}_train_{train_id}"

                if train_key in data:
                    train_data = data[train_key]

                    motion = train_data.get("motion", {})
                    block = train_data.get("block", {})
                    beacon = train_data.get("beacon", {})

                    self.output_labels["motion"].config(
                        text=motion.get("current motion", "N/A").upper()
                    )
                    self.output_labels["position"].config(
                        text=f"{motion.get('position_yds', 0):.2f}"
                    )
                    self.output_labels["cmd_speed"].config(
                        text=f"{block.get('commanded speed', 0):.2f}"
                    )
                    self.output_labels["cmd_auth"].config(
                        text=f"{block.get('commanded authority', 0):.2f}"
                    )

                    # Beacon field mapping: UI key -> beacon dict key, formatter
                    beacon_fields = {
                        "beacon_limit": ("speed limit", lambda v: f"{v:.1f}"),
                        "beacon_door": ("side_door", str),
                        "beacon_curr": ("current station", str),
                        "beacon_next": ("next station", str),
                        "beacon_pass": ("passengers_boarding", lambda v: str(v)),
                    }
                    for label_key, (beacon_key, formatter) in beacon_fields.items():
                        value = beacon.get(
                            beacon_key,
                            (
                                "N/A"
                                if label_key != "beacon_limit"
                                and label_key != "beacon_pass"
                                else 0
                            ),
                        )
                        try:
                            self.output_labels[label_key].config(text=formatter(value))
                        except Exception:
                            self.output_labels[label_key].config(text="N/A")

                    if os.path.exists(self.track_io_file):
                        with open(self.track_io_file, "r") as f:
                            io_data = json.load(f)

                        failures_array = io_data.get(f"{prefix}-Failures", [])
                        active_failures = []
                        # Use unified failure index logic for display
                        for block_num in range(len(failures_array) // 3):
                            idx = self._get_failure_index(block_num)
                            if idx + 2 < len(failures_array):
                                if failures_array[idx] != 0:
                                    active_failures.append(f"Block {block_num} Power")
                                if failures_array[idx + 1] != 0:
                                    active_failures.append(f"Block {block_num} Circuit")
                                if failures_array[idx + 2] != 0:
                                    active_failures.append(f"Block {block_num} Broken")

                        if active_failures:
                            self.output_labels["failures"].config(
                                text=", ".join(active_failures[:3]), fg="#ed4245"
                            )
                        else:
                            self.output_labels["failures"].config(
                                text="None", fg="#3ba55d"
                            )

                    motion_state = motion.get("current motion", "").lower()
                    if motion_state == "moving":
                        self.output_labels["motion"].config(fg="#3ba55d")
                    elif motion_state == "stopped":
                        self.output_labels["motion"].config(fg="#ed4245")
                    else:
                        self.output_labels["motion"].config(fg="#faa61a")

                    # Use assigned block from occupancy proximity logic
                    current_block = self.train_last_known_blocks.get(train_key, 0)
                    failure_detected = self._check_failures_ahead(
                        train_id, line, current_block
                    )
                    is_zeroed = self.authority_zeroed.get(train_key, False)
                    # Check traffic light ahead
                    light_status = self._check_traffic_light_ahead(
                        train_id, line, current_block
                    )
                    prefix = "G" if line == "Green" else "R"
                    train_key = f"{prefix}_train_{train_id}"
                    is_speed_reduced = self.speed_reduced.get(train_key, None)
                    if light_status == "RED" and is_speed_reduced != "RED":
                        self._handle_red_light(train_id, line)
                    elif light_status == "YELLOW" and is_speed_reduced != "YELLOW":
                        self._handle_yellow_light(train_id, line)
                    elif light_status is None and is_speed_reduced:
                        # Light cleared (GREEN or Super GREEN) - restore speed
                        self._restore_speed_after_light(train_id, line)
                    # DEBUG PRINTS
                    print(
                        f"🔍 Train {train_id}: current_block={current_block}, failure={failure_detected}, zeroed={is_zeroed}"
                    )
                    if failure_detected and not is_zeroed:
                        # print(f"🔍 Entering ZERO branch")
                        self._zero_authority_for_failure(train_id, line)
                    elif not failure_detected and is_zeroed:
                        # print(f"🔍 Entering RESTORE branch")
                        self._restore_authority_after_failure(train_id, line)

        except Exception as e:
            self._print(f"🔍 MONITOR ERROR: {e}", "#ed4245")

        self.root.after(100, self._monitor_outputs)


if __name__ == "__main__":
    root = tk.Tk()
    app = TrackModelTestUI(root)

    # Cleanup on window close

    def on_closing():
        app.cleanup()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()
