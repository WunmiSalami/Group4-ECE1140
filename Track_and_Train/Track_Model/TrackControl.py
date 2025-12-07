import tkinter as tk
import json
import os
import threading
from datetime import datetime
from tkinter import filedialog, ttk
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler


class TrackControl:
    def __init__(self, parent):
        self.parent = parent

        # File paths
        self.track_io_file = "track_io.json"
        self.ctc_data_file = "ctc_data.json"

        # Current selected line
        self.selected_line = "Green"

        # Track infrastructure configuration
        self.infrastructure = {
            "Green": {
                "switch_blocks": [13, 28, 57, 63, 77, 85],
                "light_blocks": [0, 3, 7, 29, 58, 62, 76, 86, 100, 101, 150, 151],
                "gate_blocks": [19, 108],
                "total_blocks": 150,
                "switch_routes": {
                    13: {0: "13->14", 1: "13->1"},
                    28: {0: "28->29", 1: "28->150"},
                    57: {0: "57->58", 1: "57->Yard"},
                    63: {0: "63->64", 1: "63->Yard"},
                    77: {0: "77->78", 1: "77->101"},
                    85: {0: "85->86", 1: "85->100"},
                },
                "stations": {
                    "Pioneer": 3,
                    "Edgebrook": 7,
                    "Whited": 16,
                    "South Bank": 21,
                    "Central": 31,
                    "Inglewood": 39,
                    "Overbrook": 48,
                    "Glenbury": 57,
                    "Dormont": 65,
                    "Mt. Lebanon": 73,
                    "Poplar": 88,
                    "Castle Shannon": 96,
                },
            },
            "Red": {
                "switch_blocks": [9, 16, 27, 33, 38, 44, 52],
                "light_blocks": [0, 8, 14, 26, 31, 37, 42, 51],
                "gate_blocks": [11, 47],
                "total_blocks": 76,
                "switch_routes": {
                    9: {0: "9->10", 1: "9->0 (Yard)"},
                    16: {0: "15->16", 1: "16->1"},
                    27: {0: "27->28", 1: "27->76"},
                    33: {0: "32->33", 1: "33->72"},
                    38: {0: "38->39", 1: "38->71"},
                    44: {0: "43->44", 1: "44->67"},
                    52: {0: "52->53", 1: "52->66"},
                },
                "stations": {
                    "Shadyside": 16,
                    "Herron Ave": 20,
                    "Swissville": 24,
                    "Penn Station": 28,
                    "Steel Plaza": 32,
                    "First Ave": 36,
                    "Station Square": 40,
                    "South Hills": 48,
                },
            },
        }

        # Light state meanings
        self.light_states = {
            "00": "Super Green",
            "01": "Green",
            "10": "Yellow",
            "11": "Red",
        }

        # Active trains tracking
        self.active_trains = {}

        # Mode state
        self.current_mode = "automatic"
        self.automatic_running = False

        # Selected block for detail view
        self.selected_block = None

        # Throughput tracking
        self.throughput_green = 0
        self.throughput_red = 0

        # Initialize JSON files
        self._ensure_json_files()

        # Build UI in parent
        self._build_ui()
        self._start_file_watcher()
        self._start_automatic_loop()

    def _get_line_config(self, line=None):
        """Get configuration for specified line (or current selected line)"""
        line = line or self.selected_line
        return self.infrastructure[line]

    def _ensure_json_files(self):
        """Initialize JSON files with proper structure"""
        track_default = {
            "G-switches": [0] * 6,
            "G-gates": [1] * 2,
            "G-lights": ["01"] * 12,
            "G-Occupancy": [0] * 151,
            "G-Failures": [0] * 151,
            "G-Train": {"commanded speed": [], "commanded authority": []},
            "R-switches": [0] * 7,  # 7 switches for Red Line
            "R-gates": [1] * 2,
            "R-lights": ["01"] * 8,
            "R-Occupancy": [0] * 77,
            "R-Failures": [0] * 77,
            "R-Train": {"commanded speed": [], "commanded authority": []},
        }

        if not os.path.exists(self.track_io_file):
            with open(self.track_io_file, "w") as f:
                json.dump(track_default, f, indent=4)

        ctc_default = {
            "Dispatcher": {
                "Trains": {
                    f"Train {i}": {
                        "Line": "",
                        "Suggested Speed": "",
                        "Authority": "",
                        "Station Destination": "",
                        "Arrival Time": "",
                        "Position": "",
                        "State": "",
                        "Current Station": "",
                    }
                    for i in range(1, 6)
                }
            }
        }

        if not os.path.exists(self.ctc_data_file):
            with open(self.ctc_data_file, "w") as f:
                json.dump(ctc_default, f, indent=4)

    def _build_ui(self):
        """Build complete UI"""
        self.parent.grid_rowconfigure(5, weight=1)
        self.parent.grid_columnconfigure(0, weight=1)

        self._build_datetime_and_line_selector()
        self._build_mode_buttons()
        self._build_mode_frames()
        self._build_bottom_section()

    def _build_datetime_and_line_selector(self):
        """Top datetime display with line selector"""
        frame = tk.Frame(self.parent, bg="white")
        frame.grid(row=0, column=0, sticky="ew", padx=5, pady=2)

        # DateTime on left
        self.date_label = tk.Label(frame, font=("Arial", 12, "bold"), bg="white")
        self.date_label.pack(side="left")
        self.time_label = tk.Label(frame, font=("Arial", 12, "bold"), bg="white")
        self.time_label.pack(side="left")

        # Line selector on right
        tk.Label(frame, text="Line:", font=("Arial", 11, "bold"), bg="white").pack(
            side="right", padx=5
        )
        self.line_selector = ttk.Combobox(
            frame,
            values=["Green", "Red"],
            font=("Arial", 11),
            width=10,
            state="readonly",
        )
        self.line_selector.set("Green")
        self.line_selector.pack(side="right", padx=5)
        self.line_selector.bind("<<ComboboxSelected>>", self._on_line_changed)

        self._update_datetime()

    def _on_line_changed(self, event=None):
        """Handle line selection change"""
        self.selected_line = self.line_selector.get()
        self._populate_all_blocks()
        track_data = self._read_track_io()
        if track_data:
            self._update_all_displays(track_data)

    def _update_datetime(self):
        now = datetime.now()
        self.date_label.config(text=now.date())
        self.time_label.config(text=f"      {now.strftime('%H:%M:%S')}")
        self.parent.after(1000, self._update_datetime)

    def _build_mode_buttons(self):
        """Mode selection buttons"""
        frame = tk.Frame(self.parent, bg="white")
        frame.grid(row=1, column=0, sticky="ew", padx=5, pady=2)
        frame.grid_columnconfigure((0, 1, 2), weight=1)

        self.auto_btn = tk.Button(
            frame,
            text="Automatic",
            command=lambda: self._switch_mode("automatic"),
            bg="lightgray",
            font=("Arial", 10, "bold"),
            height=1,
        )
        self.manual_btn = tk.Button(
            frame,
            text="Manual",
            command=lambda: self._switch_mode("manual"),
            bg="white",
            font=("Arial", 10, "bold"),
            height=1,
        )
        self.maint_btn = tk.Button(
            frame,
            text="Maintenance",
            command=lambda: self._switch_mode("maintenance"),
            bg="white",
            font=("Arial", 10, "bold"),
            height=1,
        )

        self.auto_btn.grid(row=0, column=0, padx=2, sticky="ew")
        self.manual_btn.grid(row=0, column=1, padx=2, sticky="ew")
        self.maint_btn.grid(row=0, column=2, padx=2, sticky="ew")

    def _switch_mode(self, mode):
        """Switch between modes"""
        self.current_mode = mode

        self.auto_btn.config(bg="lightgray" if mode == "automatic" else "white")
        self.manual_btn.config(bg="lightgray" if mode == "manual" else "white")
        self.maint_btn.config(bg="lightgray" if mode == "maintenance" else "white")

        if mode == "automatic":
            self.auto_frame.tkraise()
        elif mode == "manual":
            self.manual_frame.tkraise()
        else:
            self.maint_frame.tkraise()

    def _build_mode_frames(self):
        """Build frames for each mode"""
        container = tk.Frame(self.parent, bg="white")
        container.grid(row=2, column=0, sticky="nsew", padx=5, pady=2)
        container.grid_rowconfigure(0, weight=1)
        container.grid_columnconfigure(0, weight=1)

        self.auto_frame = tk.Frame(container, bg="lightblue", height=100)
        self.auto_frame.grid(row=0, column=0, sticky="nsew")
        self.auto_frame.grid_propagate(False)
        self._build_automatic_ui()

        self.manual_frame = tk.Frame(container, bg="lightgreen", height=100)
        self.manual_frame.grid(row=0, column=0, sticky="nsew")
        self.manual_frame.grid_propagate(False)
        self._build_manual_ui()

        self.maint_frame = tk.Frame(container, bg="lightyellow", height=100)
        self.maint_frame.grid(row=0, column=0, sticky="nsew")
        self.maint_frame.grid_propagate(False)
        self._build_maintenance_ui()

        self.auto_frame.tkraise()

    def _build_automatic_ui(self):
        """Automatic mode UI - compact"""
        frame = tk.Frame(self.auto_frame, bg="lightblue")
        frame.pack(fill="x", padx=5, pady=5)

        tk.Label(
            frame, text="Auto Mode", font=("Arial", 11, "bold"), bg="lightblue"
        ).pack(side="left", padx=5)

        self.auto_start_btn = tk.Button(
            frame,
            text="START",
            font=("Arial", 9, "bold"),
            bg="green",
            fg="white",
            width=10,
            command=self._start_automatic,
        )
        self.auto_start_btn.pack(side="left", padx=5)

        self.auto_stop_btn = tk.Button(
            frame,
            text="STOP",
            font=("Arial", 9, "bold"),
            bg="red",
            fg="white",
            width=10,
            state="disabled",
            command=self._stop_automatic,
        )
        self.auto_stop_btn.pack(side="left", padx=5)

        self.auto_status = tk.Label(
            frame, text="Idle", font=("Arial", 10), bg="lightblue"
        )
        self.auto_status.pack(side="left", padx=10)

    def _build_manual_ui(self):
        """Manual mode UI - compact"""
        top = tk.Frame(self.manual_frame, bg="lightgreen")
        top.pack(fill="x", padx=5, pady=2)

        tk.Label(top, text="Train:", font=("Arial", 9, "bold"), bg="lightgreen").grid(
            row=0, column=0, padx=2
        )
        self.manual_train_box = ttk.Combobox(
            top, values=[f"Train {i}" for i in range(1, 6)], font=("Arial", 9), width=8
        )
        self.manual_train_box.grid(row=0, column=1, padx=2)

        tk.Label(top, text="Line:", font=("Arial", 9, "bold"), bg="lightgreen").grid(
            row=0, column=2, padx=2
        )
        self.manual_line_box = ttk.Combobox(
            top, values=["Green", "Red"], font=("Arial", 9), width=8
        )
        self.manual_line_box.grid(row=0, column=3, padx=2)
        self.manual_line_box.bind("<<ComboboxSelected>>", self._on_manual_line_changed)

        tk.Label(top, text="Dest:", font=("Arial", 9, "bold"), bg="lightgreen").grid(
            row=0, column=4, padx=2
        )
        self.manual_dest_box = ttk.Combobox(top, values=[], font=("Arial", 9), width=12)
        self.manual_dest_box.grid(row=0, column=5, padx=2)

        tk.Label(top, text="Arrival:", font=("Arial", 9, "bold"), bg="lightgreen").grid(
            row=0, column=6, padx=2
        )
        self.manual_time_entry = tk.Entry(top, font=("Arial", 9), width=8)
        self.manual_time_entry.grid(row=0, column=7, padx=2)

        tk.Button(
            top,
            text="DISPATCH",
            font=("Arial", 9, "bold"),
            bg="blue",
            fg="white",
            command=self._manual_dispatch,
        ).grid(row=0, column=8, padx=5)

        bottom = tk.Frame(self.manual_frame, bg="lightgreen")
        bottom.pack(fill="x", padx=5, pady=2)

        tk.Label(
            bottom, text="Train:", font=("Arial", 9, "bold"), bg="lightgreen"
        ).grid(row=0, column=0, padx=2)
        self.manual_cmd_train_box = ttk.Combobox(
            bottom,
            values=[f"Train {i}" for i in range(1, 6)],
            font=("Arial", 9),
            width=8,
        )
        self.manual_cmd_train_box.grid(row=0, column=1, padx=2)

        tk.Label(
            bottom, text="Speed:", font=("Arial", 9, "bold"), bg="lightgreen"
        ).grid(row=0, column=2, padx=2)
        self.manual_speed_entry = tk.Entry(bottom, font=("Arial", 9), width=8)
        self.manual_speed_entry.grid(row=0, column=3, padx=2)

        tk.Label(bottom, text="Auth:", font=("Arial", 9, "bold"), bg="lightgreen").grid(
            row=0, column=4, padx=2
        )
        self.manual_auth_entry = tk.Entry(bottom, font=("Arial", 9), width=8)
        self.manual_auth_entry.grid(row=0, column=5, padx=2)

        tk.Button(
            bottom,
            text="SEND CMD",
            font=("Arial", 9, "bold"),
            bg="darkgreen",
            fg="white",
            command=self._manual_send_command,
        ).grid(row=0, column=6, padx=5)

    def _on_manual_line_changed(self, event=None):
        """Update destination dropdown when line changes in manual mode"""
        line = self.manual_line_box.get()
        if line:
            stations = list(self.infrastructure[line]["stations"].keys())
            self.manual_dest_box.config(values=stations)
            self.manual_dest_box.set("")

    def _build_maintenance_ui(self):
        """Maintenance mode UI - compact"""
        frame = tk.Frame(self.maint_frame, bg="lightyellow")
        frame.pack(fill="x", padx=5, pady=5)

        # Switch control
        tk.Label(
            frame, text="Switch:", font=("Arial", 9, "bold"), bg="lightyellow"
        ).grid(row=0, column=0, padx=2)
        self.maint_switch_box = ttk.Combobox(
            frame, values=[], font=("Arial", 9), width=10
        )
        self.maint_switch_box.grid(row=0, column=1, padx=2)

        self.maint_switch_state = ttk.Combobox(
            frame, values=["Pos 0", "Pos 1"], font=("Arial", 9), width=8
        )
        self.maint_switch_state.grid(row=0, column=2, padx=2)

        tk.Button(
            frame, text="SET", font=("Arial", 9, "bold"), command=self._maint_set_switch
        ).grid(row=0, column=3, padx=5)

        # Failure control
        tk.Label(
            frame, text="Block:", font=("Arial", 9, "bold"), bg="lightyellow"
        ).grid(row=0, column=4, padx=(20, 2))
        self.maint_block_entry = tk.Entry(frame, font=("Arial", 9), width=6)
        self.maint_block_entry.grid(row=0, column=5, padx=2)

        self.maint_failure_type = ttk.Combobox(
            frame,
            values=["None", "Broken", "Power", "Circuit"],
            font=("Arial", 9),
            width=10,
        )
        self.maint_failure_type.grid(row=0, column=6, padx=2)

        tk.Button(
            frame,
            text="SET",
            font=("Arial", 9, "bold"),
            command=self._maint_set_failure,
        ).grid(row=0, column=7, padx=5)

        # Update switch dropdown based on current line
        self._update_maint_switches()

    def _update_maint_switches(self):
        """Update maintenance switch dropdown based on selected line"""
        config = self._get_line_config()
        switch_blocks = config["switch_blocks"]
        self.maint_switch_box.config(values=[f"Block {b}" for b in switch_blocks])

    def _build_bottom_section(self):
        """Build comprehensive bottom display"""
        # Throughput bar
        throughput_frame = tk.Frame(self.parent, bg="white", height=25)
        throughput_frame.grid(row=3, column=0, sticky="ew", padx=5, pady=2)
        throughput_frame.grid_propagate(False)

        tk.Label(
            throughput_frame, text="Throughput:", font=("Arial", 10, "bold"), bg="white"
        ).pack(side="left", padx=5)
        self.throughput_green_label = tk.Label(
            throughput_frame, text="Green: 0 pass/hr", font=("Arial", 9), bg="white"
        )
        self.throughput_green_label.pack(side="left", padx=10)
        self.throughput_red_label = tk.Label(
            throughput_frame, text="Red: 0 pass/hr", font=("Arial", 9), bg="white"
        )
        self.throughput_red_label.pack(side="left", padx=10)

        # Main bottom area
        bottom = tk.Frame(self.parent, bg="white")
        bottom.grid(row=5, column=0, sticky="nsew", padx=5, pady=2)
        bottom.grid_rowconfigure(0, weight=1)
        bottom.grid_columnconfigure((0, 1, 2), weight=1)

        # Left: Active Trains
        self._build_active_trains(bottom)

        # Middle: All Blocks
        self._build_all_blocks(bottom)

        # Right: Details & Infrastructure
        self._build_right_panel(bottom)

    def _build_active_trains(self, parent):
        """Active trains table"""
        frame = tk.Frame(parent, bg="white")
        frame.grid(row=0, column=0, sticky="nsew", padx=2)
        frame.grid_rowconfigure(1, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        tk.Label(
            frame, text="Active Trains", font=("Arial", 11, "bold"), bg="white"
        ).grid(row=0, column=0, sticky="w", pady=2)

        columns = (
            "Train",
            "Line",
            "Block",
            "Dest",
            "Speed",
            "Auth",
            "State",
            "Cur Stn",
            "Arr Time",
        )
        self.trains_table = ttk.Treeview(
            frame, columns=columns, show="headings", height=10
        )

        widths = [50, 50, 45, 80, 50, 45, 60, 80, 70]
        for col, width in zip(columns, widths):
            self.trains_table.heading(col, text=col)
            self.trains_table.column(col, anchor="center", width=width)

        self.trains_table.grid(row=1, column=0, sticky="nsew")

        scroll = ttk.Scrollbar(
            frame, orient="vertical", command=self.trains_table.yview
        )
        scroll.grid(row=1, column=1, sticky="ns")
        self.trains_table.configure(yscrollcommand=scroll.set)

    def _build_all_blocks(self, parent):
        """All blocks scrollable table"""
        frame = tk.Frame(parent, bg="white")
        frame.grid(row=0, column=1, sticky="nsew", padx=2)
        frame.grid_rowconfigure(1, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        tk.Label(frame, text="All Blocks", font=("Arial", 11, "bold"), bg="white").grid(
            row=0, column=0, sticky="w", pady=2
        )

        columns = ("Block", "Occ", "Switch", "Light", "Gate", "Failure")
        self.blocks_table = ttk.Treeview(
            frame, columns=columns, show="headings", height=10
        )

        widths = [50, 40, 80, 80, 50, 70]
        for col, width in zip(columns, widths):
            self.blocks_table.heading(col, text=col)
            self.blocks_table.column(col, anchor="center", width=width)

        self.blocks_table.grid(row=1, column=0, sticky="nsew")
        self.blocks_table.bind("<<TreeviewSelect>>", self._on_block_select)

        scroll = ttk.Scrollbar(
            frame, orient="vertical", command=self.blocks_table.yview
        )
        scroll.grid(row=1, column=1, sticky="ns")
        self.blocks_table.configure(yscrollcommand=scroll.set)

        self._populate_all_blocks()

    def _build_right_panel(self, parent):
        """Right panel: selected block + lights + gates"""
        frame = tk.Frame(parent, bg="white")
        frame.grid(row=0, column=2, sticky="nsew", padx=2)
        frame.grid_rowconfigure((0, 1, 2), weight=1)
        frame.grid_columnconfigure(0, weight=1)

        # Selected block detail
        detail_frame = tk.LabelFrame(
            frame, text="Selected Block", font=("Arial", 10, "bold"), bg="white"
        )
        detail_frame.grid(row=0, column=0, sticky="nsew", pady=2)

        self.selected_block_label = tk.Label(
            detail_frame,
            text="No block selected",
            font=("Arial", 9),
            bg="white",
            justify="left",
        )
        self.selected_block_label.pack(fill="both", expand=True, padx=5, pady=5)

        # Lights table
        lights_frame = tk.Frame(frame, bg="white")
        lights_frame.grid(row=1, column=0, sticky="nsew", pady=2)
        lights_frame.grid_rowconfigure(1, weight=1)
        lights_frame.grid_columnconfigure(0, weight=1)

        tk.Label(
            lights_frame, text="Traffic Lights", font=("Arial", 10, "bold"), bg="white"
        ).grid(row=0, column=0, sticky="w")

        cols = ("Block", "Status")
        self.lights_table = ttk.Treeview(
            lights_frame, columns=cols, show="headings", height=4
        )
        for col in cols:
            self.lights_table.heading(col, text=col)
            self.lights_table.column(col, anchor="center", width=60)
        self.lights_table.grid(row=1, column=0, sticky="nsew")

        # Gates table
        gates_frame = tk.Frame(frame, bg="white")
        gates_frame.grid(row=2, column=0, sticky="nsew", pady=2)
        gates_frame.grid_rowconfigure(1, weight=1)
        gates_frame.grid_columnconfigure(0, weight=1)

        tk.Label(
            gates_frame, text="Crossing Gates", font=("Arial", 10, "bold"), bg="white"
        ).grid(row=0, column=0, sticky="w")

        self.gates_table = ttk.Treeview(
            gates_frame, columns=cols, show="headings", height=2
        )
        for col in cols:
            self.gates_table.heading(col, text=col)
            self.gates_table.column(col, anchor="center", width=60)
        self.gates_table.grid(row=1, column=0, sticky="nsew")

    def _populate_all_blocks(self):
        """Populate all blocks table with blocks from selected line"""
        # Clear existing
        for item in self.blocks_table.get_children():
            self.blocks_table.delete(item)

        config = self._get_line_config()
        total_blocks = config["total_blocks"]

        for block in range(total_blocks + 1):
            self.blocks_table.insert(
                "", "end", values=(block, "0", "-", "-", "-", "None")
            )

    def _on_block_select(self, event):
        """Handle block selection"""
        selection = self.blocks_table.selection()
        if selection:
            item = self.blocks_table.item(selection[0])
            self.selected_block = int(item["values"][0])
            self._update_selected_block_detail()

    # ============ FILE OPERATIONS ============

    def _read_track_io(self):
        """Read from track I/O file"""
        try:
            with open(self.track_io_file, "r") as f:
                return json.load(f)
        except:
            return None

    def _write_track_io(self, data):
        """Write to track I/O file"""
        with open(self.track_io_file, "w") as f:
            json.dump(data, f, indent=4)

    def _read_ctc_data(self):
        """Read CTC data file"""
        try:
            with open(self.ctc_data_file, "r") as f:
                return json.load(f)
        except:
            return None

    def _write_ctc_data(self, data):
        """Write CTC data file"""
        with open(self.ctc_data_file, "w") as f:
            json.dump(data, f, indent=4)

    # ============ MODE HANDLERS ============

    def _start_automatic(self):
        """Start automatic control"""
        self.automatic_running = True
        self.auto_start_btn.config(state="disabled")
        self.auto_stop_btn.config(state="normal")
        self.auto_status.config(text="Running")

    def _stop_automatic(self):
        """Stop automatic control"""
        self.automatic_running = False
        self.auto_start_btn.config(state="normal")
        self.auto_stop_btn.config(state="disabled")
        self.auto_status.config(text="Stopped")

    def _manual_dispatch(self):
        """Dispatch train in manual mode"""
        train = self.manual_train_box.get()
        line = self.manual_line_box.get()
        dest = self.manual_dest_box.get()
        arrival = self.manual_time_entry.get()

        if train and line and dest:
            train_id = int(train.split()[-1])
            self.active_trains[train_id] = {
                "line": line,
                "destination": dest,
                "current_block": 0,
                "commanded_speed": 0,
                "commanded_authority": 0,
                "state": "Dispatched",
                "current_station": "Yard",
                "arrival_time": arrival,
            }

            # Update CTC data
            ctc_data = self._read_ctc_data()
            if ctc_data:
                ctc_data["Dispatcher"]["Trains"][train]["Line"] = line
                ctc_data["Dispatcher"]["Trains"][train]["Station Destination"] = dest
                ctc_data["Dispatcher"]["Trains"][train]["Arrival Time"] = arrival
                ctc_data["Dispatcher"]["Trains"][train]["State"] = "Dispatched"
                self._write_ctc_data(ctc_data)

    def _manual_send_command(self):
        """Send manual command to train"""
        train = self.manual_cmd_train_box.get()
        speed = self.manual_speed_entry.get()
        authority = self.manual_auth_entry.get()

        if train and speed and authority:
            train_id = int(train.split()[-1])
            if train_id in self.active_trains:
                self.active_trains[train_id]["commanded_speed"] = int(speed)
                self.active_trains[train_id]["commanded_authority"] = int(authority)
                self._write_train_commands()

    def _maint_set_switch(self):
        """Set switch position"""
        switch_str = self.maint_switch_box.get()
        state_str = self.maint_switch_state.get()

        if switch_str and state_str:
            block = int(switch_str.split()[-1])
            state = 0 if "0" in state_str else 1

            data = self._read_track_io()
            if data:
                config = self._get_line_config()
                switch_blocks = config["switch_blocks"]
                idx = switch_blocks.index(block)

                line_prefix = "G" if self.selected_line == "Green" else "R"
                data[f"{line_prefix}-switches"][idx] = state
                self._write_track_io(data)

    def _maint_set_failure(self):
        """Set block failure"""
        block_str = self.maint_block_entry.get()
        failure_str = self.maint_failure_type.get()

        if block_str and failure_str:
            block = int(block_str)
            failure_map = {"None": 0, "Broken": 1, "Power": 2, "Circuit": 3}
            failure = failure_map.get(failure_str, 0)

            data = self._read_track_io()
            if data:
                line_prefix = "G" if self.selected_line == "Green" else "R"
                data[f"{line_prefix}-Failures"][block] = failure
                self._write_track_io(data)

    # ============ AUTOMATIC CONTROL LOOP ============

    def _start_automatic_loop(self):
        """Start automatic control loop"""
        self._automatic_control_cycle()

    def _automatic_control_cycle(self):
        """Execute one cycle of automatic control"""
        track_data = self._read_track_io()
        if track_data:
            # Update train positions from occupancy for each line
            for line in ["Green", "Red"]:
                line_prefix = "G" if line == "Green" else "R"
                occupancy = track_data.get(f"{line_prefix}-Occupancy", [])
                self._update_train_positions(occupancy, line)

            if self.automatic_running:
                # Route trains and control infrastructure
                self._route_all_trains(track_data)
                self._write_train_commands()
                self._write_track_io(track_data)

            # Update all displays
            self._update_all_displays(track_data)

        self.parent.after(200, self._automatic_control_cycle)

    def _update_train_positions(self, occupancy, line):
        """Update train positions from occupancy array for specific line"""
        # Find all occupied blocks
        occupied_blocks = [idx for idx, occ in enumerate(occupancy) if occ == 1]

        # Get trains on this line sorted by train_id
        line_trains = sorted(
            [
                (tid, info)
                for tid, info in self.active_trains.items()
                if info.get("line") == line
            ],
            key=lambda x: x[0],
        )

        # Assign occupied blocks to trains in order
        for i, (train_id, train_info) in enumerate(line_trains):
            if i < len(occupied_blocks):
                train_info["current_block"] = occupied_blocks[i]

                # Check if at station
                config = self.infrastructure[line]
                stations = config["stations"]
                block_to_station = {v: k for k, v in stations.items()}

                if occupied_blocks[i] in block_to_station:
                    train_info["current_station"] = block_to_station[occupied_blocks[i]]

    def _route_all_trains(self, track_data):
        """Route all trains on all lines"""
        for train_id, train_info in self.active_trains.items():
            line = train_info.get("line")
            if not line:
                continue

            line_prefix = "G" if line == "Green" else "R"
            failures = track_data.get(f"{line_prefix}-Failures", [])

            self._route_single_train(
                train_id, train_info, track_data, failures, line, line_prefix
            )

    def _route_single_train(
        self, train_id, train_info, track_data, failures, line, line_prefix
    ):
        """Route a single train"""
        current_block = train_info.get("current_block", 0)
        dest = train_info.get("destination")

        config = self.infrastructure[line]
        stations = config["stations"]

        if dest and dest in stations:
            dest_block = stations[dest]

            # Check for failures ahead
            failure_ahead = False
            for block in range(current_block, min(current_block + 10, len(failures))):
                if failures[block] != 0:
                    failure_ahead = True
                    break

            if failure_ahead:
                train_info["commanded_speed"] = 0
                train_info["commanded_authority"] = 0
                train_info["state"] = "Stopped - Failure"
            else:
                # Set appropriate speed and authority
                distance_to_dest = abs(dest_block - current_block)
                if distance_to_dest > 10:
                    train_info["commanded_speed"] = 40
                    train_info["commanded_authority"] = 20
                    train_info["state"] = "Running"
                elif distance_to_dest > 3:
                    train_info["commanded_speed"] = 25
                    train_info["commanded_authority"] = 10
                    train_info["state"] = "Approaching"
                elif distance_to_dest > 0:
                    train_info["commanded_speed"] = 10
                    train_info["commanded_authority"] = 5
                    train_info["state"] = "Slowing"
                else:
                    train_info["commanded_speed"] = 0
                    train_info["commanded_authority"] = 0
                    train_info["state"] = "Arrived"

            # Set switches for routing
            self._set_switches_for_route(
                track_data, current_block, dest_block, line, line_prefix
            )

            # Control lights
            self._control_lights_for_line(track_data, line, line_prefix)

    def _set_switches_for_route(
        self, track_data, current_block, dest_block, line, line_prefix
    ):
        """Set switches to route train to destination"""
        config = self.infrastructure[line]
        switch_blocks = config["switch_blocks"]

        # Simple routing logic - set switches based on direction
        for idx, switch_block in enumerate(switch_blocks):
            if current_block < switch_block < dest_block:
                # Forward routing
                track_data[f"{line_prefix}-switches"][idx] = 0
            elif current_block > switch_block > dest_block:
                # Reverse routing
                track_data[f"{line_prefix}-switches"][idx] = 1

    def _control_lights_for_line(self, track_data, line, line_prefix):
        """Control traffic lights for specific line based on train positions"""
        config = self.infrastructure[line]
        light_blocks = config["light_blocks"]
        lights = track_data.get(f"{line_prefix}-lights", [])

        for idx, light_block in enumerate(light_blocks):
            if idx >= len(lights):
                continue

            # Check if any train on this line is near this light
            train_nearby = False
            for train_id, train_info in self.active_trains.items():
                if train_info.get("line") != line:
                    continue

                train_block = train_info.get("current_block", 0)
                distance = abs(light_block - train_block)

                if distance < 3:
                    train_nearby = True
                    if distance < 1:
                        lights[idx] = "11"  # Red - train at light
                    elif distance < 2:
                        lights[idx] = "10"  # Yellow - train approaching
                    else:
                        lights[idx] = "01"  # Green - train nearby
                    break

            if not train_nearby:
                lights[idx] = "01"  # Green - no trains

        track_data[f"{line_prefix}-lights"] = lights

    def _write_train_commands(self):
        """Write commanded speeds/authorities to track I/O for all lines"""
        data = self._read_track_io()
        if not data:
            return

        # Separate trains by line
        green_trains = {
            tid: info
            for tid, info in self.active_trains.items()
            if info.get("line") == "Green"
        }
        red_trains = {
            tid: info
            for tid, info in self.active_trains.items()
            if info.get("line") == "Red"
        }

        # Green line commands
        g_speeds = []
        g_authorities = []
        for train_id in sorted(green_trains.keys()):
            train_info = green_trains[train_id]
            g_speeds.append(train_info.get("commanded_speed", 0))
            g_authorities.append(train_info.get("commanded_authority", 0))

        data["G-Train"]["commanded speed"] = g_speeds
        data["G-Train"]["commanded authority"] = g_authorities

        # Red line commands
        r_speeds = []
        r_authorities = []
        for train_id in sorted(red_trains.keys()):
            train_info = red_trains[train_id]
            r_speeds.append(train_info.get("commanded_speed", 0))
            r_authorities.append(train_info.get("commanded_authority", 0))

        data["R-Train"]["commanded speed"] = r_speeds
        data["R-Train"]["commanded authority"] = r_authorities

        self._write_track_io(data)

    # ============ DISPLAY UPDATES ============

    def _update_all_displays(self, track_data):
        """Update all tables and displays"""
        self._update_active_trains_display()
        self._update_all_blocks_display(track_data)
        self._update_lights_display(track_data)
        self._update_gates_display(track_data)
        self._update_throughput()
        if self.selected_block is not None:
            self._update_selected_block_detail()

    def _update_active_trains_display(self):
        """Update active trains table"""
        for item in self.trains_table.get_children():
            self.trains_table.delete(item)

        for train_id, info in self.active_trains.items():
            self.trains_table.insert(
                "",
                "end",
                values=(
                    f"Train {train_id}",
                    info.get("line", "N/A"),
                    info.get("current_block", "N/A"),
                    info.get("destination", "N/A"),
                    info.get("commanded_speed", 0),
                    info.get("commanded_authority", 0),
                    info.get("state", "Unknown"),
                    info.get("current_station", "N/A"),
                    info.get("arrival_time", "N/A"),
                ),
            )

    def _update_all_blocks_display(self, track_data):
        """Update all blocks table for selected line"""
        line_prefix = "G" if self.selected_line == "Green" else "R"
        config = self._get_line_config()

        occupancy = track_data.get(f"{line_prefix}-Occupancy", [])
        failures = track_data.get(f"{line_prefix}-Failures", [])
        switches = track_data.get(f"{line_prefix}-switches", [])
        lights = track_data.get(f"{line_prefix}-lights", [])
        gates = track_data.get(f"{line_prefix}-gates", [])

        switch_blocks = config["switch_blocks"]
        light_blocks = config["light_blocks"]
        gate_blocks = config["gate_blocks"]
        switch_routes = config["switch_routes"]

        for item in self.blocks_table.get_children():
            block = int(self.blocks_table.item(item)["values"][0])

            # Occupancy
            occ = occupancy[block] if block < len(occupancy) else 0

            # Switch
            if block in switch_blocks:
                idx = switch_blocks.index(block)
                if idx < len(switches):
                    switch_state = switch_routes[block][switches[idx]]
                else:
                    switch_state = "-"
            else:
                switch_state = "-"

            # Light
            if block in light_blocks:
                idx = light_blocks.index(block)
                if idx < len(lights):
                    light_state = self.light_states.get(lights[idx], "-")
                else:
                    light_state = "-"
            else:
                light_state = "-"

            # Gate
            if block in gate_blocks:
                idx = gate_blocks.index(block)
                if idx < len(gates):
                    gate_state = "Up" if gates[idx] == 1 else "Down"
                else:
                    gate_state = "-"
            else:
                gate_state = "-"

            # Failure
            fail = failures[block] if block < len(failures) else 0
            failure_names = ["None", "Broken", "Power", "Circuit"]
            failure_state = failure_names[fail] if fail < len(failure_names) else "None"

            self.blocks_table.item(
                item,
                values=(
                    block,
                    occ,
                    switch_state,
                    light_state,
                    gate_state,
                    failure_state,
                ),
            )

    def _update_lights_display(self, track_data):
        """Update lights table for selected line"""
        for item in self.lights_table.get_children():
            self.lights_table.delete(item)

        line_prefix = "G" if self.selected_line == "Green" else "R"
        config = self._get_line_config()
        light_blocks = config["light_blocks"]
        lights = track_data.get(f"{line_prefix}-lights", [])

        for idx, block in enumerate(light_blocks):
            if idx < len(lights):
                state = self.light_states.get(lights[idx], "Unknown")
                self.lights_table.insert("", "end", values=(block, state))

    def _update_gates_display(self, track_data):
        """Update gates table for selected line"""
        for item in self.gates_table.get_children():
            self.gates_table.delete(item)

        line_prefix = "G" if self.selected_line == "Green" else "R"
        config = self._get_line_config()
        gate_blocks = config["gate_blocks"]
        gates = track_data.get(f"{line_prefix}-gates", [])

        for idx, block in enumerate(gate_blocks):
            if idx < len(gates):
                state = "Up" if gates[idx] == 1 else "Down"
                self.gates_table.insert("", "end", values=(block, state))

    def _update_throughput(self):
        """Update throughput display"""
        # Count trains per line
        green_count = sum(
            1 for t in self.active_trains.values() if t.get("line") == "Green"
        )
        red_count = sum(
            1 for t in self.active_trains.values() if t.get("line") == "Red"
        )

        self.throughput_green = green_count * 50
        self.throughput_red = red_count * 50

        self.throughput_green_label.config(
            text=f"Green: {self.throughput_green} pass/hr"
        )
        self.throughput_red_label.config(text=f"Red: {self.throughput_red} pass/hr")

    def _update_selected_block_detail(self):
        """Update selected block detail view"""
        if self.selected_block is None:
            return

        track_data = self._read_track_io()
        if not track_data:
            return

        line_prefix = "G" if self.selected_line == "Green" else "R"
        config = self._get_line_config()

        block = self.selected_block
        occupancy = track_data.get(f"{line_prefix}-Occupancy", [])
        failures = track_data.get(f"{line_prefix}-Failures", [])
        switches = track_data.get(f"{line_prefix}-switches", [])
        lights = track_data.get(f"{line_prefix}-lights", [])
        gates = track_data.get(f"{line_prefix}-gates", [])

        switch_blocks = config["switch_blocks"]
        light_blocks = config["light_blocks"]
        gate_blocks = config["gate_blocks"]
        switch_routes = config["switch_routes"]
        stations = config["stations"]
        block_to_station = {v: k for k, v in stations.items()}

        detail_text = f"Block: {block}\n"
        detail_text += f"Line: {self.selected_line}\n"
        detail_text += f"Occupied: {'Yes' if occupancy[block] == 1 else 'No'}\n"

        if block in switch_blocks:
            idx = switch_blocks.index(block)
            if idx < len(switches):
                detail_text += f"Switch: {switch_routes[block][switches[idx]]}\n"

        if block in light_blocks:
            idx = light_blocks.index(block)
            if idx < len(lights):
                detail_text += f"Light: {self.light_states.get(lights[idx], 'N/A')}\n"

        if block in gate_blocks:
            idx = gate_blocks.index(block)
            if idx < len(gates):
                detail_text += f"Gate: {'Up' if gates[idx] == 1 else 'Down'}\n"

        fail = failures[block] if block < len(failures) else 0
        failure_names = ["None", "Broken Track", "Power Failure", "Circuit Failure"]
        detail_text += (
            f"Failure: {failure_names[fail] if fail < len(failure_names) else 'None'}\n"
        )

        if block in block_to_station:
            detail_text += f"Station: {block_to_station[block]}\n"

        self.selected_block_label.config(text=detail_text)

    # ============ FILE WATCHER ============

    def _start_file_watcher(self):
        """Monitor track I/O file for changes"""

        class Handler(FileSystemEventHandler):
            def __init__(self, controller):
                self.controller = controller

            def on_modified(self, event):
                if event.src_path.endswith("track_io.json"):
                    track_data = self.controller._read_track_io()
                    if track_data:
                        self.controller.parent.after(
                            100, self.controller._update_all_displays, track_data
                        )

        self.event_handler = Handler(self)
        self.observer = Observer()
        self.observer.schedule(
            self.event_handler,
            path=os.path.dirname(self.track_io_file) or ".",
            recursive=False,
        )
        threading.Thread(target=self.observer.start, daemon=True).start()


# For standalone testing
if __name__ == "__main__":
    root = tk.Tk()
    root.title("Track Control - Standalone Test")
    root.geometry("1600x900")

    control = TrackControl(root)

    root.mainloop()
