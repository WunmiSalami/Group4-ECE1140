import tkinter as tk
import json
import os
import sys
import threading
from datetime import datetime
from tkinter import filedialog, ttk
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Add parent directory to path for logger import
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parent_dir)
from logger import get_logger


class TrackControl:
    def validate_schedule_csv(self, csv_path):
        import csv
        import re

        logger = get_logger()
        error_count = 0
        trains_first_seen = {}
        previous_times_per_train = {}
        current_time = datetime.now().strftime("%H:%M")

        def valid_time_format(t):
            return bool(re.match(r"^\d{2}:\d{2}$", t))

        def time_to_minutes(t):
            h, m = map(int, t.split(":"))
            return h * 60 + m

        valid_stations_dict = (
            self.infrastructure if hasattr(self, "infrastructure") else {}
        )

        with open(csv_path, newline="") as csvfile:
            reader = csv.DictReader(csvfile)
            for row_number, row in enumerate(reader, 1):
                train_id = row["train_id"]
                line = row["line"]
                destination = row["destination_station"]
                dispatch_time = row["dispatch_time"]
                arrival_time = row["arrival_time"]

                if train_id not in trains_first_seen:
                    trains_first_seen[train_id] = row_number
                    logger.info(
                        "SCHEDULE",
                        f"Train {train_id} first seen at row {row_number}, will dispatch from Yard",
                        {"train_id": train_id, "row": row_number},
                    )

                if line not in ["Green", "Red"]:
                    logger.error(
                        "SCHEDULE",
                        f"Row {row_number}: Invalid line '{line}', must be 'Green' or 'Red'",
                        {"row": row_number, "line": line},
                    )
                    error_count += 1

                valid_stations = (
                    valid_stations_dict.get(line, {}).get("stations", {})
                    if valid_stations_dict
                    else {}
                )
                if destination not in valid_stations:
                    logger.error(
                        "SCHEDULE",
                        f"Row {row_number}: Invalid station '{destination}' for {line} Line",
                        {"row": row_number, "station": destination, "line": line},
                    )
                    error_count += 1

                if not valid_time_format(dispatch_time):
                    logger.error(
                        "SCHEDULE",
                        f"Row {row_number}: Invalid dispatch_time format '{dispatch_time}', must be HH:MM",
                        {"row": row_number, "dispatch_time": dispatch_time},
                    )
                    error_count += 1
                if not valid_time_format(arrival_time):
                    logger.error(
                        "SCHEDULE",
                        f"Row {row_number}: Invalid arrival_time format '{arrival_time}', must be HH:MM",
                        {"row": row_number, "arrival_time": arrival_time},
                    )
                    error_count += 1

                if valid_time_format(dispatch_time) and valid_time_format(arrival_time):
                    if dispatch_time >= arrival_time:
                        logger.error(
                            "SCHEDULE",
                            f"Row {row_number}: dispatch_time {dispatch_time} must be before arrival_time {arrival_time}",
                            {
                                "row": row_number,
                                "dispatch_time": dispatch_time,
                                "arrival_time": arrival_time,
                            },
                        )
                        error_count += 1

                    if dispatch_time < current_time:
                        logger.error(
                            "SCHEDULE",
                            f"Row {row_number}: dispatch_time {dispatch_time} is in the past (current time: {current_time})",
                            {
                                "row": row_number,
                                "dispatch_time": dispatch_time,
                                "current_time": current_time,
                            },
                        )
                        error_count += 1

                    time_difference = time_to_minutes(arrival_time) - time_to_minutes(
                        dispatch_time
                    )
                    if time_difference < 1:
                        logger.error(
                            "SCHEDULE",
                            f"Row {row_number}: Impossible schedule - only {time_difference} minutes between dispatch and arrival",
                            {
                                "row": row_number,
                                "dispatch_time": dispatch_time,
                                "arrival_time": arrival_time,
                                "diff": time_difference,
                            },
                        )
                        error_count += 1

                    if train_id in previous_times_per_train:
                        previous_arrival = previous_times_per_train[train_id]
                        if dispatch_time < previous_arrival:
                            logger.error(
                                "SCHEDULE",
                                f"Row {row_number}: Train {train_id} dispatch_time {dispatch_time} is before previous arrival_time {previous_arrival}",
                                {
                                    "row": row_number,
                                    "train_id": train_id,
                                    "dispatch_time": dispatch_time,
                                    "previous_arrival": previous_arrival,
                                },
                            )
                            error_count += 1
                    previous_times_per_train[train_id] = arrival_time

        total_rows = row_number if "row_number" in locals() else 0
        if error_count > 10:
            logger.critical(
                "SCHEDULE",
                f"Schedule validation failed with {error_count} errors - rejecting file",
                {"error_count": error_count},
            )
            return False
        elif error_count > 0:
            logger.warning(
                "SCHEDULE",
                f"Schedule has {error_count} errors but proceeding",
                {"error_count": error_count},
            )
            return True
        else:
            logger.info(
                "SCHEDULE",
                f"Schedule validation passed - {total_rows} entries loaded",
                {"total_rows": total_rows},
            )
            return True

    def __init__(self, parent):
        self.parent = parent

        # Configure parent background
        self.parent.configure(bg="#2b2d31")

        # Set up paths
        CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
        PARENT_DIR = os.path.dirname(CURRENT_DIR)

        # File paths
        self.track_io_file = os.path.join(PARENT_DIR, "track_io.json")
        self.ctc_data_file = os.path.join(PARENT_DIR, "ctc_data.json")
        self.track_model_file = os.path.join(PARENT_DIR, "track_model_Train_Model.json")

        # Current selected line
        self.selected_line = "Green"

        # Dwell time constant (seconds)
        self.DWELL_TIME = 10

        # Infrastructure control thresholds
        self.LIGHT_DISTANCE_RED = 1  # Blocks - train within 1 block: Red
        self.LIGHT_DISTANCE_YELLOW = 3  # Blocks - train within 3 blocks: Yellow
        self.LIGHT_DISTANCE_GREEN = 5  # Blocks - train within 5 blocks: Green
        self.GATE_CLOSE_DISTANCE = 5  # Blocks - close gate when train within 5 blocks
        self.GATE_OPEN_DELAY = (
            3  # Seconds - delay before opening gate after train passes
        )
        self.FAILURE_STOP_DISTANCE = 10  # Blocks - stop if failure within 10 blocks

        # Gate state tracking
        self.gate_timers = {}  # {(line, block): last_train_pass_time}

        # PLC cycle tracking
        self.plc_cycle_count = 0

        # Track infrastructure configuration
        self.infrastructure = {
            "Green": {
                "switch_blocks": [13, 28, 57, 63, 77, 85],
                "light_blocks": [0, 3, 7, 29, 58, 62, 76, 86, 100, 101, 150, 151],
                "gate_blocks": [19, 108],
                "total_blocks": 150,
                "switch_routes": {
                    13: {0: "13->12", 1: "1->13"},
                    28: {0: "28->29", 1: "150->28"},
                    57: {0: "57->58", 1: "57->Yard"},
                    63: {0: "63->64", 1: "Yard->63"},
                    77: {0: "76->77", 1: "77->101"},
                    85: {0: "85->86", 1: "100->85"},
                },
                "stations": {
                    "Pioneer": [2],
                    "Edgebrook": [9],
                    "Whited": [22],
                    "South Bank": [31],
                    "Central": [39, 141],
                    "Inglewood": [48, 132],
                    "Overbrook": [57, 123],
                    "Glenbury": [65, 114],
                    "Dormont": [73, 105],
                    "Mt. Lebanon": [77],
                    "Poplar": [88],
                    "Castle Shannon": [96],
                },
            },
            "Red": {
                "switch_blocks": [9, 16, 27, 33, 38, 44, 52],
                "light_blocks": [0, 8, 14, 26, 31, 37, 42, 51],
                "gate_blocks": [11, 47],
                "total_blocks": 76,
                "switch_routes": {
                    9: {0: "0->9", 1: "9->0 (Yard)"},
                    16: {0: "15->16", 1: "1->16"},
                    27: {0: "27->28", 1: "27->76"},
                    33: {0: "32->33", 1: "33->72"},
                    38: {0: "38->39", 1: "38->71"},
                    44: {0: "43->44", 1: "44->67"},
                    52: {0: "52->53", 1: "52->66"},
                },
                "stations": {
                    "Shadyside": [7],
                    "Herron Ave": [16],
                    "Swissville": [21],
                    "Penn Station": [25],
                    "Steel Plaza": [35],
                    "First Ave": [45],
                    "Station Square": [48],
                    "South Hills": [60],
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

        # Build route lookup dictionaries (AFTER infrastructure is defined)
        self.route_lookup_via_station = self._build_route_lookup_via_station()
        self.route_lookup_via_id = self._build_route_lookup_via_id()

        # Active trains tracking with enhanced state
        self.active_trains = (
            {}
        )  # Will include: line, destination, current_block, current_station, commanded_speed, commanded_authority, state, arrival_time, route, current_leg_index, next_station_block, dwell_start_time, last_position_yds

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

    def process_schedule(self):
        """
        Called every 200ms in automatic cycle to process train schedule.
        Dispatches trains according to schedule timing and state.
        """
        logger = get_logger()
        # Don't process if schedule not loaded or auto mode not running
        if not hasattr(self, "schedule_loaded") or not self.schedule_loaded:
            return
        if not hasattr(self, "automatic_running") or not self.automatic_running:
            return

        # Get current simulation time (HH:MM)
        current_time = datetime.now().strftime("%H:%M")

        # Look at current entry in schedule
        if not hasattr(self, "active_schedule") or not self.active_schedule:
            return
        if not hasattr(self, "schedule_index"):
            self.schedule_index = 0
        if self.schedule_index >= len(self.active_schedule):
            return
        current_entry = self.active_schedule[self.schedule_index]

        train_id = current_entry["train_id"]
        dispatch_time = current_entry["dispatch_time"]

        # Check if it's time to dispatch
        if current_time >= dispatch_time:
            # Check if this train already exists
            if train_id in self.active_trains:
                train_state = self.active_trains[train_id].get("state", None)
                # Only dispatch if train is ready (finished previous leg)
                if train_state == "Arrived":
                    origin = self.active_trains[train_id].get(
                        "current_station", "Unknown"
                    )
                    destination = current_entry.get("destination_station", "Unknown")
                    logger.info(
                        "SCHEDULE",
                        f"Dispatching Train {train_id} from {origin} to {destination}",
                        {
                            "train_id": train_id,
                            "origin": origin,
                            "destination": destination,
                        },
                    )
                    self.dispatch_train_from_schedule(current_entry)
                    self.schedule_index += 1
                elif train_state == "Dwelling":
                    logger.debug(
                        "SCHEDULE",
                        f"Train {train_id} still dwelling, waiting to dispatch next leg",
                        {"train_id": train_id},
                    )
                    return
                else:
                    # Train is "En Route" or "At Station" or "Dispatching"
                    return
            else:
                # Train doesn't exist - this is first dispatch from Yard
                destination = current_entry.get("destination_station", "Unknown")
                logger.info(
                    "SCHEDULE",
                    f"Dispatching NEW Train {train_id} from Yard to {destination}",
                    {
                        "train_id": train_id,
                        "origin": "Yard",
                        "destination": destination,
                    },
                )
                self.dispatch_train_from_schedule(current_entry)
                self.schedule_index += 1
        else:
            # Not time yet - do nothing
            return

    def _get_line_config(self, line=None):
        """Get configuration for specified line (or current selected line)"""
        line = line or self.selected_line
        return self.infrastructure[line]

    def _build_route_lookup_via_station(self):
        """Build route lookup dictionary keyed by (line, start_station, end_station)"""
        lookup = {}
        for line in ["Green", "Red"]:
            stations = self.infrastructure[line]["stations"]
            station_names = list(stations.keys())

            # Add routes from Yard to all stations
            # Route should include ALL intermediate station blocks on the path
            for end_station in station_names:
                # Build complete route: get block numbers for path from Yard to destination
                # This returns the actual block numbers with correct platforms
                route = self._get_stations_on_path_to_destination(
                    line, end_station, station_names, stations
                )

                lookup[(line, "Yard", end_station)] = route

            for i, start_station in enumerate(station_names):
                for j, end_station in enumerate(station_names):
                    if i != j:
                        # Build route as list of station blocks
                        route = []
                        if i < j:  # Forward route
                            route = [
                                (
                                    stations[station_names[k]][0]
                                    if isinstance(stations[station_names[k]], list)
                                    else stations[station_names[k]]
                                )
                                for k in range(i, j + 1)
                            ]
                        else:  # Reverse route
                            route = [
                                (
                                    stations[station_names[k]][0]
                                    if isinstance(stations[station_names[k]], list)
                                    else stations[station_names[k]]
                                )
                                for k in range(i, j - 1, -1)
                            ]

                        lookup[(line, start_station, end_station)] = route

        return lookup

    def _get_stations_on_path_to_destination(
        self, line, destination, station_names, stations
    ):
        """Determine which stations are visited on path from Yard to destination.
        Uses track topology knowledge to build correct station sequence.
        """
        if line == "Green":
            # Green Line topology:
            # Yard exits at block 63
            # Path to Pioneer (block 2): 0→63→...→150→28→...→2
            # Passes through: Glenbury(65), Dormont(73), Mt.Lebanon(77), Poplar(88), Castle Shannon(96),
            #                 then loops: Dormont(105), Glenbury(114), Overbrook(123), Inglewood(132),
            #                 Central(141), South Bank(31), Whited(22), Edgebrook(9), Pioneer(2)

            dest_blocks = stations[destination]
            # For dual-platform stations, determine which platform based on location
            if isinstance(dest_blocks, list):
                if len(dest_blocks) == 1:
                    # Single platform station wrapped in list
                    dest_block = dest_blocks[0]
                else:
                    # Dual-platform station - check if either block is on direct path (63-150)
                    if dest_blocks[0] >= 63 and dest_blocks[0] <= 150:
                        dest_block = dest_blocks[
                            0
                        ]  # Use outbound platform on direct path
                    elif dest_blocks[1] >= 63 and dest_blocks[1] <= 150:
                        dest_block = dest_blocks[
                            1
                        ]  # Use outbound platform on direct path
                    else:
                        # Both blocks on loop - use first block (outbound/primary platform)
                        # Trains complete full loop and arrive at outbound platform
                        dest_block = dest_blocks[0]
            else:
                dest_block = dest_blocks

            # Green Line path with correct platform selection
            # Direct path stations (blocks 63-150) with their blocks
            direct_path_sequence = [
                ("Glenbury", 65),  # Outbound platform
                ("Dormont", 73),  # Outbound platform
                ("Mt. Lebanon", 77),
                ("Poplar", 88),
                ("Castle Shannon", 96),
            ]

            # Loop path stations (accessed via 150→28, blocks decrease then wrap)
            # Use INBOUND platforms for dual-platform stations
            loop_path_sequence = [
                ("Dormont", 105),  # Inbound platform (NOT 73)
                ("Glenbury", 114),  # Inbound platform (NOT 65)
                ("Overbrook", 123),  # Inbound platform
                ("Inglewood", 132),  # Inbound platform
                ("Central", 141),  # Inbound platform
                ("South Bank", 31),
                ("Central", 39),  # Outbound platform
                ("Inglewood", 48),  # Outbound platform
                ("Overbrook", 57),  # Outbound platform
            ]

            station_sequence = []
            block_sequence = []
            if dest_block >= 63 and dest_block <= 150:
                # Destination on direct path - include only stations up to destination
                for stn_name, stn_block in direct_path_sequence:
                    if stn_block <= dest_block:
                        station_sequence.append(stn_name)
                        block_sequence.append(stn_block)
                    if stn_name == destination:
                        break
            else:
                # Destination on loop - include all direct path + loop stations up to destination
                for stn, stn_block in direct_path_sequence:
                    station_sequence.append(stn)
                    block_sequence.append(stn_block)
                for stn_name, stn_block in loop_path_sequence:
                    station_sequence.append(stn_name)
                    block_sequence.append(stn_block)
                    if stn_name == destination and stn_block == dest_block:
                        break
            logger = get_logger()
            logger.debug(
                "ROUTE_PATH",
                f"Route to {destination} (Green Line): stations={station_sequence}, blocks={block_sequence}",
                {
                    "destination": destination,
                    "station_sequence": station_sequence,
                    "block_sequence": block_sequence,
                },
            )
            return block_sequence

        elif line == "Red":
            # Red Line: all stations in order from yard
            # Yard exits at block 9, all stations are sequential
            dest_blocks = stations[destination]
            dest_block = (
                dest_blocks[0] if isinstance(dest_blocks, list) else dest_blocks
            )

            ordered_stations = [
                "Shadyside",
                "Herron Ave",
                "Swissville",
                "Penn Station",
                "Steel Plaza",
                "First Ave",
                "Station Square",
                "South Hills",
            ]

            station_sequence = []
            block_sequence = []
            for stn in ordered_stations:
                stn_blocks = stations.get(stn)
                if stn_blocks:
                    block = (
                        stn_blocks[0] if isinstance(stn_blocks, list) else stn_blocks
                    )
                    station_sequence.append(stn)
                    block_sequence.append(block)
                if stn == destination:
                    break
            logger = get_logger()
            logger.debug(
                "ROUTE_PATH",
                f"Route to {destination} (Red Line): stations={station_sequence}, blocks={block_sequence}",
                {
                    "destination": destination,
                    "station_sequence": station_sequence,
                    "block_sequence": block_sequence,
                },
            )
            return block_sequence

        # Fallback: return destination block
        dest_blocks = stations.get(destination, [])
        return (
            [dest_blocks[0] if isinstance(dest_blocks, list) else dest_blocks]
            if dest_blocks
            else []
        )

    def _build_route_lookup_via_id(self):
        """Build route lookup dictionary keyed by route_id for faster lookup"""
        lookup = {}
        route_id = 0
        for line in ["Green", "Red"]:
            stations = self.infrastructure[line]["stations"]
            station_names = list(stations.keys())

            for i, start_station in enumerate(station_names):
                for j, end_station in enumerate(station_names):
                    if i != j:
                        route = []
                        if i < j:
                            route = [
                                (
                                    stations[station_names[k]][0]
                                    if isinstance(stations[station_names[k]], list)
                                    else stations[station_names[k]]
                                )
                                for k in range(i, j + 1)
                            ]
                        else:
                            route = [
                                (
                                    stations[station_names[k]][0]
                                    if isinstance(stations[station_names[k]], list)
                                    else stations[station_names[k]]
                                )
                                for k in range(i, j - 1, -1)
                            ]

                        lookup[route_id] = {
                            "line": line,
                            "start_station": start_station,
                            "end_station": end_station,
                            "route": route,
                        }
                        route_id += 1

        return lookup

    def _ensure_json_files(self):
        """Initialize JSON files with proper structure"""
        track_default = {
            "G-switches": [0] * 6,
            "G-gates": [1] * 2,
            "G-lights": [0, 1]
            * 12,  # 2 bits per light: 00=Super Green, 01=Green, 10=Yellow, 11=Red (24 elements)
            "G-Occupancy": [0] * 151,
            "G-Failures": [0] * 151,
            "G-Train": {"commanded speed": [], "commanded authority": []},
            "R-switches": [0] * 7,  # 7 switches for Red Line
            "R-gates": [1] * 2,
            "R-lights": [0, 1]
            * 8,  # 2 bits per light: 00=Super Green, 01=Green, 10=Yellow, 11=Red (16 elements)
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
        frame = tk.Frame(self.parent, bg="#1e1f22")
        frame.grid(row=0, column=0, sticky="ew", padx=5, pady=5)

        # DateTime on left
        self.date_label = tk.Label(
            frame, font=("Segoe UI", 12, "bold"), bg="#1e1f22", fg="#ffffff"
        )
        self.date_label.pack(side="left", padx=5)
        self.time_label = tk.Label(
            frame, font=("Segoe UI", 12, "bold"), bg="#1e1f22", fg="#00d9ff"
        )
        self.time_label.pack(side="left", padx=5)

        # Line selector on right
        tk.Label(
            frame,
            text="Line:",
            font=("Segoe UI", 11, "bold"),
            bg="#1e1f22",
            fg="#ffffff",
        ).pack(side="right", padx=5)

        style = ttk.Style()
        style.configure(
            "TrackControl.TCombobox",
            fieldbackground="#313338",
            background="#313338",
            foreground="#ffffff",
            borderwidth=0,
        )

        self.line_selector = ttk.Combobox(
            frame,
            values=["Green", "Red"],
            font=("Segoe UI", 11),
            width=10,
            state="readonly",
            style="TrackControl.TCombobox",
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
        frame = tk.Frame(self.parent, bg="#2b2d31")
        frame.grid(row=1, column=0, sticky="ew", padx=5, pady=5)
        frame.grid_columnconfigure((0, 1, 2), weight=1)

        self.auto_btn = tk.Button(
            frame,
            text="🤖 Automatic",
            command=lambda: self._switch_mode("automatic"),
            bg="#5865f2",
            fg="white",
            font=("Segoe UI", 10, "bold"),
            height=2,
            relief="flat",
            cursor="hand2",
        )
        self.manual_btn = tk.Button(
            frame,
            text="🎮 Manual",
            command=lambda: self._switch_mode("manual"),
            bg="#313338",
            fg="white",
            font=("Segoe UI", 10, "bold"),
            height=2,
            relief="flat",
            cursor="hand2",
        )
        self.maint_btn = tk.Button(
            frame,
            text="🔧 Maintenance",
            command=lambda: self._switch_mode("maintenance"),
            bg="#313338",
            fg="white",
            font=("Segoe UI", 10, "bold"),
            height=2,
            relief="flat",
            cursor="hand2",
        )

        self.auto_btn.grid(row=0, column=0, padx=2, sticky="ew")
        self.manual_btn.grid(row=0, column=1, padx=2, sticky="ew")
        self.maint_btn.grid(row=0, column=2, padx=2, sticky="ew")

    def _switch_mode(self, mode):
        """Switch between modes"""
        self.current_mode = mode

        self.auto_btn.config(bg="#5865f2" if mode == "automatic" else "#313338")
        self.manual_btn.config(bg="#5865f2" if mode == "manual" else "#313338")
        self.maint_btn.config(bg="#5865f2" if mode == "maintenance" else "#313338")

        if mode == "automatic":
            self.auto_frame.tkraise()
        elif mode == "manual":
            self.manual_frame.tkraise()
        else:
            self.maint_frame.tkraise()

    def _build_mode_frames(self):
        """Build frames for each mode"""
        container = tk.Frame(self.parent, bg="#2b2d31")
        container.grid(row=2, column=0, sticky="nsew", padx=5, pady=5)
        container.grid_rowconfigure(0, weight=1)
        container.grid_columnconfigure(0, weight=1)

        self.auto_frame = tk.Frame(container, bg="#313338", height=100)
        self.auto_frame.grid(row=0, column=0, sticky="nsew")
        self.auto_frame.grid_propagate(False)
        self._build_automatic_ui()

        self.manual_frame = tk.Frame(container, bg="#313338", height=100)
        self.manual_frame.grid(row=0, column=0, sticky="nsew")
        self.manual_frame.grid_propagate(False)
        self._build_manual_ui()

        self.maint_frame = tk.Frame(container, bg="#313338", height=100)
        self.maint_frame.grid(row=0, column=0, sticky="nsew")
        self.maint_frame.grid_propagate(False)
        self._build_maintenance_ui()

        self.auto_frame.tkraise()

    def _build_automatic_ui(self):
        """Automatic mode UI - compact"""
        frame = tk.Frame(self.auto_frame, bg="#313338")
        frame.pack(fill="x", padx=10, pady=10)

        tk.Label(
            frame,
            text="🤖 Auto Mode",
            font=("Segoe UI", 11, "bold"),
            bg="#313338",
            fg="#ffffff",
        ).pack(side="left", padx=5)

        self.auto_start_btn = tk.Button(
            frame,
            text="▶️ START",
            font=("Segoe UI", 9, "bold"),
            bg="#3ba55d",
            fg="white",
            width=12,
            relief="flat",
            cursor="hand2",
            command=self._start_automatic,
        )
        self.auto_start_btn.pack(side="left", padx=5)

        self.auto_stop_btn = tk.Button(
            frame,
            text="⏹️ STOP",
            font=("Segoe UI", 9, "bold"),
            bg="#ed4245",
            fg="white",
            width=12,
            state="disabled",
            relief="flat",
            cursor="hand2",
            command=self._stop_automatic,
        )
        self.auto_stop_btn.pack(side="left", padx=5)

        self.auto_status = tk.Label(
            frame, text="💤 Idle", font=("Segoe UI", 10), bg="#313338", fg="#b5bac1"
        )
        self.auto_status.pack(side="left", padx=10)

    def _build_manual_ui(self):
        """Manual mode UI - compact"""
        top = tk.Frame(self.manual_frame, bg="#313338")
        top.pack(fill="x", padx=10, pady=5)

        tk.Label(
            top,
            text="🚂 Train:",
            font=("Segoe UI", 9, "bold"),
            bg="#313338",
            fg="#ffffff",
        ).grid(row=0, column=0, padx=2)
        self.manual_train_box = ttk.Combobox(
            top,
            values=[f"Train {i}" for i in range(1, 6)],
            font=("Segoe UI", 9),
            width=8,
            style="TrackControl.TCombobox",
        )
        self.manual_train_box.grid(row=0, column=1, padx=2)

        tk.Label(
            top, text="Line:", font=("Segoe UI", 9, "bold"), bg="#313338", fg="#ffffff"
        ).grid(row=0, column=2, padx=2)
        self.manual_line_box = ttk.Combobox(
            top,
            values=["Green", "Red"],
            font=("Segoe UI", 9),
            width=8,
            style="TrackControl.TCombobox",
        )
        self.manual_line_box.grid(row=0, column=3, padx=2)
        self.manual_line_box.bind("<<ComboboxSelected>>", self._on_manual_line_changed)

        tk.Label(
            top,
            text="🎯 Dest:",
            font=("Segoe UI", 9, "bold"),
            bg="#313338",
            fg="#ffffff",
        ).grid(row=0, column=4, padx=2)
        self.manual_dest_box = ttk.Combobox(
            top,
            values=[],
            font=("Segoe UI", 9),
            width=12,
            style="TrackControl.TCombobox",
        )
        self.manual_dest_box.grid(row=0, column=5, padx=2)

        tk.Label(
            top,
            text="⏰ Arrival:",
            font=("Segoe UI", 9, "bold"),
            bg="#313338",
            fg="#ffffff",
        ).grid(row=0, column=6, padx=2)
        self.manual_time_entry = tk.Entry(
            top,
            font=("Segoe UI", 9),
            width=8,
            bg="#1e1f22",
            fg="#ffffff",
            insertbackground="#ffffff",
            relief="flat",
        )
        self.manual_time_entry.grid(row=0, column=7, padx=2)

        tk.Button(
            top,
            text="🚀 DISPATCH",
            font=("Segoe UI", 9, "bold"),
            bg="#5865f2",
            fg="white",
            relief="flat",
            cursor="hand2",
            command=self._manual_dispatch,
        ).grid(row=0, column=8, padx=5)

    def _on_manual_line_changed(self, event=None):
        """Update destination dropdown when line changes in manual mode"""
        line = self.manual_line_box.get()
        if line:
            stations = list(self.infrastructure[line]["stations"].keys())
            self.manual_dest_box.config(values=stations)
            self.manual_dest_box.set("")

    def _build_maintenance_ui(self):
        """Maintenance mode UI - compact"""
        frame = tk.Frame(self.maint_frame, bg="#313338")
        frame.pack(fill="x", padx=10, pady=10)

        # Switch control
        tk.Label(
            frame,
            text="🔀 Switch:",
            font=("Segoe UI", 9, "bold"),
            bg="#313338",
            fg="#ffffff",
        ).grid(row=0, column=0, padx=2)
        self.maint_switch_box = ttk.Combobox(
            frame,
            values=[],
            font=("Segoe UI", 9),
            width=10,
            style="TrackControl.TCombobox",
        )
        self.maint_switch_box.grid(row=0, column=1, padx=2)

        self.maint_switch_state = ttk.Combobox(
            frame,
            values=["Pos 0", "Pos 1"],
            font=("Segoe UI", 9),
            width=8,
            style="TrackControl.TCombobox",
        )
        self.maint_switch_state.grid(row=0, column=2, padx=2)

        tk.Button(
            frame,
            text="✅ SET",
            font=("Segoe UI", 9, "bold"),
            bg="#5865f2",
            fg="white",
            relief="flat",
            cursor="hand2",
            command=self._maint_set_switch,
        ).grid(row=0, column=3, padx=5)

        # Failure control
        tk.Label(
            frame,
            text="⚠️ Block:",
            font=("Segoe UI", 9, "bold"),
            bg="#313338",
            fg="#ffffff",
        ).grid(row=0, column=4, padx=(20, 2))
        self.maint_block_entry = tk.Entry(
            frame,
            font=("Segoe UI", 9),
            width=6,
            bg="#1e1f22",
            fg="#ffffff",
            insertbackground="#ffffff",
            relief="flat",
        )
        self.maint_block_entry.grid(row=0, column=5, padx=2)

        self.maint_failure_type = ttk.Combobox(
            frame,
            values=["None", "Broken", "Power", "Circuit"],
            font=("Segoe UI", 9),
            width=10,
            style="TrackControl.TCombobox",
        )
        self.maint_failure_type.grid(row=0, column=6, padx=2)

        tk.Button(
            frame,
            text="✅ SET",
            font=("Segoe UI", 9, "bold"),
            bg="#faa61a",
            fg="white",
            relief="flat",
            cursor="hand2",
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
        throughput_frame = tk.Frame(self.parent, bg="#1e1f22", height=30)
        throughput_frame.grid(row=3, column=0, sticky="ew", padx=5, pady=5)
        throughput_frame.grid_propagate(False)

        tk.Label(
            throughput_frame,
            text="📊 Throughput:",
            font=("Segoe UI", 10, "bold"),
            bg="#1e1f22",
            fg="#ffffff",
        ).pack(side="left", padx=5)
        self.throughput_green_label = tk.Label(
            throughput_frame,
            text="🟢 Green: 0 pass/hr",
            font=("Segoe UI", 9),
            bg="#1e1f22",
            fg="#3ba55d",
        )
        self.throughput_green_label.pack(side="left", padx=10)
        self.throughput_red_label = tk.Label(
            throughput_frame,
            text="🔴 Red: 0 pass/hr",
            font=("Segoe UI", 9),
            bg="#1e1f22",
            fg="#ed4245",
        )
        self.throughput_red_label.pack(side="left", padx=10)

        # Main bottom area
        bottom = tk.Frame(self.parent, bg="#2b2d31")
        bottom.grid(row=5, column=0, sticky="nsew", padx=5, pady=5)
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
        frame = tk.Frame(parent, bg="#2b2d31")
        frame.grid(row=0, column=0, sticky="nsew", padx=2)
        frame.grid_rowconfigure(1, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        tk.Label(
            frame,
            text="🚂 Active Trains",
            font=("Segoe UI", 11, "bold"),
            bg="#2b2d31",
            fg="#ffffff",
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

        style = ttk.Style()
        style.configure(
            "TrackControl.Treeview",
            background="#313338",
            fieldbackground="#313338",
            foreground="#ffffff",
            borderwidth=0,
        )
        style.configure(
            "TrackControl.Treeview.Heading",
            background="#1e1f22",
            foreground="#ffffff",
            borderwidth=0,
        )
        style.map("TrackControl.Treeview", background=[("selected", "#5865f2")])

        self.trains_table = ttk.Treeview(
            frame,
            columns=columns,
            show="headings",
            height=10,
            style="TrackControl.Treeview",
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
        frame = tk.Frame(parent, bg="#2b2d31")
        frame.grid(row=0, column=1, sticky="nsew", padx=2)
        frame.grid_rowconfigure(1, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        tk.Label(
            frame,
            text="🛤️ All Blocks",
            font=("Segoe UI", 11, "bold"),
            bg="#2b2d31",
            fg="#ffffff",
        ).grid(row=0, column=0, sticky="w", pady=2)

        columns = ("Block", "Occ", "Switch", "Light", "Gate", "Failure")
        self.blocks_table = ttk.Treeview(
            frame,
            columns=columns,
            show="headings",
            height=10,
            style="TrackControl.Treeview",
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
        frame = tk.Frame(parent, bg="#2b2d31")
        frame.grid(row=0, column=2, sticky="nsew", padx=2)
        frame.grid_rowconfigure((0, 1, 2), weight=1)
        frame.grid_columnconfigure(0, weight=1)

        # Selected block detail
        style = ttk.Style()
        style.configure(
            "TrackControl.TLabelframe",
            background="#2b2d31",
            foreground="#5865f2",
            borderwidth=2,
        )
        style.configure(
            "TrackControl.TLabelframe.Label",
            foreground="#5865f2",
            font=("Segoe UI", 10, "bold"),
            background="#2b2d31",
        )

        detail_frame = ttk.LabelFrame(
            frame, text="📍 Selected Block", style="TrackControl.TLabelframe"
        )
        detail_frame.grid(row=0, column=0, sticky="nsew", pady=2)

        self.selected_block_label = tk.Label(
            detail_frame,
            text="No block selected",
            font=("Segoe UI", 9),
            bg="#313338",
            fg="#b5bac1",
            justify="left",
        )
        self.selected_block_label.pack(fill="both", expand=True, padx=5, pady=5)

        # Lights table
        lights_frame = tk.Frame(frame, bg="#2b2d31")
        lights_frame.grid(row=1, column=0, sticky="nsew", pady=2)
        lights_frame.grid_rowconfigure(1, weight=1)
        lights_frame.grid_columnconfigure(0, weight=1)

        tk.Label(
            lights_frame,
            text="🚦 Traffic Lights",
            font=("Segoe UI", 10, "bold"),
            bg="#2b2d31",
            fg="#ffffff",
        ).grid(row=0, column=0, sticky="w")

        cols = ("Block", "Status")
        self.lights_table = ttk.Treeview(
            lights_frame,
            columns=cols,
            show="headings",
            height=4,
            style="TrackControl.Treeview",
        )
        for col in cols:
            self.lights_table.heading(col, text=col)
            self.lights_table.column(col, anchor="center", width=60)
        self.lights_table.grid(row=1, column=0, sticky="nsew")

        # Gates table
        gates_frame = tk.Frame(frame, bg="#2b2d31")
        gates_frame.grid(row=2, column=0, sticky="nsew", pady=2)
        gates_frame.grid_rowconfigure(1, weight=1)
        gates_frame.grid_columnconfigure(0, weight=1)

        tk.Label(
            gates_frame,
            text="🚧 Crossing Gates",
            font=("Segoe UI", 10, "bold"),
            bg="#2b2d31",
            fg="#ffffff",
        ).grid(row=0, column=0, sticky="w")

        self.gates_table = ttk.Treeview(
            gates_frame,
            columns=cols,
            show="headings",
            height=2,
            style="TrackControl.Treeview",
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

    def _read_track_model(self):
        """Read track model file for train positions and states"""
        try:
            with open(self.track_model_file, "r") as f:
                return json.load(f)
        except:
            return None

    def _read_static_data(self):
        """Read track model static data file"""
        try:
            static_file = os.path.join(
                os.path.dirname(self.track_io_file),
                "Track_Model",
                "track_model_static.json",
            )
            with open(static_file, "r") as f:
                data = json.load(f)
                return data
        except Exception as e:
            logger = get_logger()
            logger.error(
                "STATIC_DATA",
                f"Failed to read static data: {str(e)}",
                {
                    "file": static_file if "static_file" in locals() else "unknown",
                    "error": str(e),
                },
            )
            return None

    # ============ MODE HANDLERS ============

    def _start_automatic(self):
        """Start automatic control"""
        self.automatic_running = True
        self.auto_start_btn.config(state="disabled")
        self.auto_stop_btn.config(state="normal")
        self.auto_status.config(text="🟢 Running")

    def _stop_automatic(self):
        """Stop automatic control"""
        self.automatic_running = False
        self.auto_start_btn.config(state="normal")
        self.auto_stop_btn.config(state="disabled")
        self.auto_status.config(text="🔴 Stopped")

    def _manual_dispatch(self):
        """Dispatch train in manual mode with route planning"""
        train = self.manual_train_box.get()
        line = self.manual_line_box.get()
        dest = self.manual_dest_box.get()
        arrival = self.manual_time_entry.get()

        if train and line and dest:
            train_id = int(train.split()[-1])

            # Get route from Yard to destination
            config = self.infrastructure[line]
            stations = config["stations"]

            # Starting from Yard (block 0)
            start_station = "Yard"

            # Look up route
            route_key = (line, start_station, dest)
            route = self.route_lookup_via_station.get(route_key, [])

            if not route:
                return  # Invalid route

            # Log the route for debugging
            logger = get_logger()
            logger.info(
                "ROUTE",
                f"Train {train_id} route to {dest}: {route}, first station block: {route[0] if route else 'NONE'}",
                {
                    "train_id": train_id,
                    "destination": dest,
                    "route": route,
                    "first_station": route[0] if route else None,
                },
            )

            if train_id not in self.active_trains:
                self.active_trains[train_id] = {
                    "line": line,
                    "destination": dest,
                    "current_block": 0,
                    "commanded_speed": 0,
                    "commanded_authority": 0,
                    "state": "Dispatching",
                    "current_station": "Yard",
                    "arrival_time": arrival,
                    "route": route,
                    "current_leg_index": 0,
                    "next_station_block": route[0] if route else 0,
                    "dwell_start_time": None,
                    "last_position_yds": 0.0,
                }
            else:
                # Update all fields except current_station and current_leg_index
                self.active_trains[train_id]["line"] = line
                self.active_trains[train_id]["destination"] = dest
                self.active_trains[train_id]["current_block"] = 0
                self.active_trains[train_id]["commanded_speed"] = 0
                self.active_trains[train_id]["commanded_authority"] = 0
                self.active_trains[train_id]["state"] = "Dispatching"
                # self.active_trains[train_id]["current_station"] = (do not update)
                self.active_trains[train_id]["arrival_time"] = arrival
                self.active_trains[train_id]["route"] = route
                # self.active_trains[train_id]["current_leg_index"] = (do not update)
                self.active_trains[train_id]["next_station_block"] = (
                    route[0] if route else 0
                )
                self.active_trains[train_id]["dwell_start_time"] = None
                self.active_trains[train_id]["last_position_yds"] = 0.0

            # Update CTC data
            ctc_data = self._read_ctc_data()
            if ctc_data:
                ctc_data["Dispatcher"]["Trains"][train]["Line"] = line
                ctc_data["Dispatcher"]["Trains"][train]["Station Destination"] = dest
                ctc_data["Dispatcher"]["Trains"][train]["Arrival Time"] = arrival
                ctc_data["Dispatcher"]["Trains"][train]["State"] = "Dispatching"
                # Speed will be calculated by state machine in next automatic cycle
                ctc_data["Dispatcher"]["Trains"][train]["Speed"] = "Calculating..."
                self._write_ctc_data(ctc_data)

            # Log manual dispatch
            logger = get_logger()
            logger.info(
                "TRAIN",
                f"Manual dispatch: Train {train_id} to {dest} on {line} Line, arrival {arrival}",
                {
                    "train_id": train_id,
                    "line": line,
                    "destination": dest,
                    "arrival_time": arrival,
                    "route_stations": len(route),
                },
            )

            # Train will be processed by automatic control cycle
            # No need to manually call state machine - it runs automatically

    def dispatch_train_from_schedule(self, schedule_entry):
        """
        Dispatch train using schedule entry data (automatic mode).
        Only updates necessary fields for existing trains.
        """
        logger = get_logger()
        train_id = schedule_entry["train_id"]
        line = schedule_entry["line"]
        destination = schedule_entry["destination_station"]
        arrival_time = schedule_entry["arrival_time"]

        # Determine origin
        if train_id in self.active_trains:
            origin = self.active_trains[train_id].get("current_station", "Yard")
        else:
            origin = "Yard"

        # Look up route (origin → destination)
        route_key = (line, origin, destination)
        route = self.route_lookup_via_station.get(route_key, [])

        # Log dispatch
        logger.info(
            "TRAIN",
            f"Train {train_id}: {origin} → {destination}, arrival {arrival_time}",
            {
                "train_id": train_id,
                "origin": origin,
                "destination": destination,
                "arrival_time": arrival_time,
                "route_stations": len(route),
            },
        )

        if train_id not in self.active_trains:
            self.active_trains[train_id] = {
                "line": line,
                "destination": destination,
                "current_block": 0,
                "commanded_speed": 0,
                "commanded_authority": 0,
                "state": "Dispatching",
                "current_station": origin,
                "arrival_time": arrival_time,
                "route": route,
                "current_leg_index": 0,
                "next_station_block": route[0] if route else 0,
                "dwell_start_time": None,
                "last_position_yds": 0.0,
            }
        else:
            # Only update necessary fields
            self.active_trains[train_id]["destination"] = destination
            self.active_trains[train_id]["arrival_time"] = arrival_time
            self.active_trains[train_id]["route"] = route
            self.active_trains[train_id]["state"] = "Dispatching"
            self.active_trains[train_id]["next_station_block"] = (
                route[0] if route else 0
            )
        # Do not overwrite current_block, dwell_start_time, current_station, current_leg_index, last_position_yds

        # Update CTC data
        ctc_data = self._read_ctc_data()
        train_name = f"Train {train_id}"
        if (
            ctc_data
            and "Dispatcher" in ctc_data
            and "Trains" in ctc_data["Dispatcher"]
            and train_name in ctc_data["Dispatcher"]["Trains"]
        ):
            ctc_data["Dispatcher"]["Trains"][train_name]["Line"] = line
            ctc_data["Dispatcher"]["Trains"][train_name][
                "Station Destination"
            ] = destination
            ctc_data["Dispatcher"]["Trains"][train_name]["Arrival Time"] = arrival_time
            ctc_data["Dispatcher"]["Trains"][train_name]["State"] = "Dispatching"
            ctc_data["Dispatcher"]["Trains"][train_name]["Speed"] = "Calculating..."
            self._write_ctc_data(ctc_data)

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
        """Execute one cycle of automatic control with state machine"""
        track_data = self._read_track_io()
        track_model_data = self._read_track_model()

        if track_data and track_model_data:
            # Update train positions from occupancy for each line
            for line in ["Green", "Red"]:
                line_prefix = "G" if line == "Green" else "R"
                occupancy = track_data.get(f"{line_prefix}-Occupancy", [])
                self._update_train_positions(occupancy, line)

            # Process all active trains through state machine (regardless of manual/automatic mode)
            # Manual vs Automatic only affects HOW trains are dispatched, not how they're controlled
            for train_id, train_info in list(self.active_trains.items()):
                self._process_train_state_machine(
                    train_id, train_info, track_data, track_model_data
                )

            # Execute PLC cycle for infrastructure control (switches, lights, gates)
            self._execute_plc_cycle(track_data, track_model_data)

            # Write track_io with PLC updates (switches, lights, gates)
            self._write_track_io(track_data)

            # Write train commands (reads track_io, adds commands, writes back)
            self._write_train_commands()

            self.plc_cycle_count += 1

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
                actual_block = occupied_blocks[i] + 1
                old_block = train_info.get("current_block")
                train_info["current_block"] = actual_block

                # Log block transitions
                if old_block is not None and old_block != actual_block:
                    logger = get_logger()
                    logger.info(
                        "TRAIN",
                        f"Train {train_id} BLOCK TRANSITION: {old_block} → {actual_block}",
                        {
                            "train_id": train_id,
                            "old_block": old_block,
                            "new_block": actual_block,
                            "state": train_info.get("state"),
                            "motion": train_info.get("motion_state", "Unknown"),
                        },
                    )

                # Path verification: check if train is on expected path
                expected_path = train_info.get("expected_path", [])
                if expected_path and actual_block not in expected_path:
                    logger = get_logger()
                    logger.warn(
                        "ROUTING",
                        f"Train {train_id} DEVIATED: expected path {expected_path}, actual block {actual_block}",
                        {
                            "train_id": train_id,
                            "expected_path": expected_path,
                            "actual_block": actual_block,
                        },
                    )

                # Check if at station
                config = self.infrastructure[line]
                stations = config["stations"]
                # Handle list format: create mapping for all blocks
                block_to_station = {}
                for station_name, blocks in stations.items():
                    if isinstance(blocks, list):
                        for block in blocks:
                            block_to_station[block] = station_name
                    else:
                        block_to_station[blocks] = station_name

                if occupied_blocks[i] in block_to_station:
                    train_info["current_station"] = block_to_station[occupied_blocks[i]]

    def _process_train_state_machine(
        self, train_id, train_info, track_data, track_model_data
    ):
        """Process train through state machine: Dispatching -> En Route -> At Station -> Dwelling"""
        state = train_info.get("state", "Idle")
        line = train_info.get("line")
        line_prefix = "G" if line == "Green" else "R"

        # Get train data from track model
        train_key = f"{line_prefix}_train_{train_id}"
        train_model_info = track_model_data.get(train_key, {})
        block_info = train_model_info.get("block", {})

        current_position_yds = float(block_info.get("position", 0.0) or 0.0)
        motion_state = block_info.get("motion", "Stopped")

        # State machine transitions
        if state == "Dispatching":
            self._handle_dispatching_state(
                train_id, train_info, track_data, line_prefix
            )

        elif state == "En Route":
            self._handle_enroute_state(
                train_id,
                train_info,
                track_data,
                track_model_data,
                current_position_yds,
                motion_state,
                line_prefix,
            )

        elif state == "At Station":
            self._handle_at_station_state(train_id, train_info, track_data, line_prefix)

        elif state == "Dwelling":
            self._handle_dwelling_state(train_id, train_info, track_data, line_prefix)

    def _handle_dispatching_state(self, train_id, train_info, track_data, line_prefix):
        """Initial dispatch: calculate route speed and send first leg authority"""
        route = train_info.get("route", [])
        if not route:
            return

        # Get line info needed for calculations
        line = train_info.get(
            "line"
        )  # Calculate optimal speed based on arrival time and total distance
        arrival_time_str = train_info.get("arrival_time", "")
        if arrival_time_str:
            from datetime import datetime, timedelta

            try:
                # Parse arrival time (HH:MM format)
                hour, minute = map(int, arrival_time_str.split(":"))
                now = datetime.now()
                arrival = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

                # If arrival time is in the past, assume next day
                if arrival < now:
                    arrival += timedelta(days=1)

                # Calculate available time in seconds
                time_available = (arrival - now).total_seconds()

                # Calculate total route distance using actual block lengths from static data
                complete_path = self._expand_route_to_complete_path(route, line)
                total_distance_meters = 0.0
                static_data = self._read_static_data()

                if static_data and complete_path:
                    # Block 0 (yard) is not technically a block - fixed at 200 yards
                    total_distance_yards = 200.0  # Yard distance

                    line_data = static_data.get("static_data", {}).get(line, [])
                    for block_num in complete_path[1:]:
                        for block_info in line_data:
                            if int(block_info.get("Block Number", -1)) == block_num:
                                total_distance_meters += float(
                                    block_info.get("Block Length (m)", 0)
                                )
                                break
                    total_distance_yards += total_distance_meters * 1.09361
                else:
                    # No fallback - abort dispatch if static data unavailable
                    logger = get_logger()
                    logger.error(
                        "DISPATCH",
                        f"Train {train_id} dispatch failed: cannot calculate distance without static data",
                        {"train_id": train_id, "line": line},
                    )
                    return  # Abort dispatch

                # Calculate total dwell time (all intermediate stops)
                num_stops = len(route) - 1  # Exclude starting point
                total_dwell_seconds = num_stops * self.DWELL_TIME

                # Calculate travel time (exclude dwell time)
                travel_time_seconds = time_available - total_dwell_seconds

                if travel_time_seconds > 0:
                    # Calculate required speed (yards/sec → mph)
                    # 1 yard/sec = 2.045 mph
                    speed_yards_per_sec = total_distance_yards / travel_time_seconds
                    optimal_speed = speed_yards_per_sec * 2.045
                    # Note: Speed limits enforced per-block by train model via beacon data
                else:
                    # Impossible schedule (not enough time)
                    optimal_speed = 30
                    # Log warning but don't fail - let train model handle speed limits

                    logger = get_logger()
                    logger.warn(
                        "TRAIN",
                        f"Train {train_id} impossible schedule: arrival time too soon",
                        {
                            "train_id": train_id,
                            "time_available": time_available,
                            "dwell_time_needed": total_dwell_seconds,
                            "arrival_time": arrival_time_str,
                        },
                    )

            except Exception as e:
                # Parsing error or calculation issue
                optimal_speed = 30
                logger = get_logger()
                import traceback

                logger.warn(
                    "TRAIN",
                    f"Train {train_id} speed calculation failed, using default 30 mph: {str(e)}",
                    {
                        "train_id": train_id,
                        "error": str(e),
                        "traceback": traceback.format_exc(),
                        "arrival_time": arrival_time_str,
                    },
                )
        else:
            optimal_speed = 30

        # Calculate authority to first station using actual block lengths from static data
        current_block = train_info.get("current_block", 0)
        next_station_block = route[0]
        complete_path = self._calculate_complete_block_path(
            current_block, next_station_block, line
        )

        # Sum up block lengths along the path (in meters, convert to yards)
        authority_meters = 0.0
        static_data = self._read_static_data()

        if static_data and complete_path:
            # Block 0 (yard) is not technically a block - fixed at 200 yards
            authority = 200.0  # Yard distance in yards

            line_data = static_data.get("static_data", {}).get(line, [])
            for block_num in complete_path[1:-1]:  # Exclude last block (destination)
                # Find this block in static data
                for block_info in line_data:
                    if int(block_info.get("Block Number", -1)) == block_num:
                        block_length_m = float(block_info.get("Block Length (m)", 0))
                        authority_meters += block_length_m
                        break

            # Convert meters to yards and add to yard distance, then add 50 yard buffer
            authority += authority_meters * 1.09361 + 50.0
        else:
            # No fallback - log error if static data unavailable
            logger = get_logger()
            logger.error(
                "AUTHORITY",
                f"Train {train_id} dispatch failed: cannot calculate authority without static data",
                {"train_id": train_id, "line": line, "destination": next_station_block},
            )
            return  # Abort dispatch

        train_info["commanded_speed"] = optimal_speed
        train_info["commanded_authority"] = int(authority)
        train_info["state"] = "En Route"
        train_info["current_leg_index"] = 0
        train_info["next_station_block"] = next_station_block
        train_info["last_position_yds"] = 0.0
        train_info["scheduled_speed"] = (
            optimal_speed  # Store for resumption after dwelling
        )

        # Log initial dispatch authority and speed
        logger = get_logger()
        logger.info(
            "AUTHORITY",
            f"Train {train_id} INITIAL DISPATCH: speed={optimal_speed:.2f} mph, authority={int(authority)} yds",
            {
                "train_id": train_id,
                "commanded_speed_mph": round(optimal_speed, 2),
                "commanded_authority_yds": int(authority),
                "destination_block": next_station_block,
                "complete_path": complete_path,
            },
        )

        # Update CTC data with calculated speed
        ctc_data = self._read_ctc_data()
        if ctc_data:
            train_key = f"Train {train_id}"
            if train_key in ctc_data.get("Dispatcher", {}).get("Trains", {}):
                ctc_data["Dispatcher"]["Trains"][train_key][
                    "Speed"
                ] = f"{optimal_speed:.1f} mph"
                self._write_ctc_data(ctc_data)

        # Log dispatch with calculated speed
        logger = get_logger()
        logger.info(
            "TRAIN",
            f"Train {train_id} dispatched: {optimal_speed:.1f} mph to reach {train_info.get('destination')} by {arrival_time_str if arrival_time_str else 'N/A'}",
            {
                "train_id": train_id,
                "line": train_info.get("line"),
                "destination": train_info.get("destination"),
                "calculated_speed_mph": round(optimal_speed, 1),
                "arrival_time": arrival_time_str if arrival_time_str else "N/A",
                "route_length_blocks": len(route),
                "total_dwell_seconds": (
                    num_stops * self.DWELL_TIME if arrival_time_str else 0
                ),
            },
        )

        # Set switches for route
        self._set_switches_for_route(
            track_data, current_block, route, train_info.get("line"), line_prefix
        )

    def _handle_enroute_state(
        self,
        train_id,
        train_info,
        track_data,
        track_model_data,
        current_position_yds,
        motion_state,
        line_prefix,
    ):
        """Train is moving: check for station arrival or authority exhaustion"""
        current_block = train_info.get("current_block", 0)
        next_station_block = train_info.get("next_station_block", 0)

        # Check if reached next station (exact match only, no overshoot)
        if current_block == next_station_block:
            train_info["state"] = "At Station"
            train_info["dwell_start_time"] = datetime.now()

            # Update current station
            line = train_info.get("line")
            config = self.infrastructure[line]
            stations = config["stations"]
            # Handle list format: create mapping for all blocks
            block_to_station = {}
            for station_name, blocks in stations.items():
                if isinstance(blocks, list):
                    for block in blocks:
                        block_to_station[block] = station_name
                else:
                    block_to_station[blocks] = station_name
            if next_station_block in block_to_station:
                train_info["current_station"] = block_to_station[next_station_block]

                logger = get_logger()
                logger.info(
                    "TRAIN",
                    f"Train {train_id} arrived at {block_to_station[next_station_block]}",
                    {
                        "train_id": train_id,
                        "line": line,
                        "station": block_to_station[next_station_block],
                        "block": next_station_block,
                    },
                )
            return

    def _handle_at_station_state(self, train_id, train_info, track_data, line_prefix):
        """Train arrived at station: begin dwelling"""
        train_info["state"] = "Dwelling"
        train_info["commanded_speed"] = 0
        train_info["commanded_authority"] = 0

        logger = get_logger()
        logger.info(
            "TRAIN",
            f"Train {train_id} DWELLING at {train_info.get('current_station', 'Unknown')} for {self.DWELL_TIME}s",
            {
                "train_id": train_id,
                "station": train_info.get("current_station"),
                "dwell_time_s": self.DWELL_TIME,
                "current_block": train_info.get("current_block"),
            },
        )

    def _handle_dwelling_state(self, train_id, train_info, track_data, line_prefix):
        """Train dwelling at station: wait 10 seconds then dispatch next leg"""
        dwell_start = train_info.get("dwell_start_time")
        if not dwell_start:
            logger = get_logger()
            logger.error(
                "TRAIN",
                f"Train {train_id} in Dwelling state but no dwell_start_time set!",
                {"train_id": train_id, "state": train_info.get("state")},
            )
            return

        dwell_elapsed = (datetime.now() - dwell_start).total_seconds()

        if dwell_elapsed >= self.DWELL_TIME:
            # Dwell complete - dispatch next leg
            route = train_info.get("route", [])
            current_leg_index = train_info.get("current_leg_index", 0)

            # Check if at final destination
            if current_leg_index >= len(route) - 1:
                train_info["state"] = "Arrived"
                train_info["commanded_speed"] = 0
                train_info["commanded_authority"] = 0
                return

            # Move to next leg
            current_leg_index += 1
            next_station_block = route[current_leg_index]
            current_block = train_info.get("current_block", 0)

            # Calculate authority using actual block lengths (INCLUDE current block)
            line = train_info.get("line")
            complete_path = self._calculate_complete_block_path(
                current_block, next_station_block, line
            )

            authority_meters = 0.0
            static_data = self._read_static_data()
            if static_data and complete_path:
                # Block 0 (yard) is not technically a block - fixed at 200 yards
                authority = 0.0
                if current_block == 0:
                    authority = 200.0  # Yard distance

                line_data = static_data.get("static_data", {}).get(line, [])
                # Find index of current_block in complete_path
                try:
                    idx = complete_path.index(current_block)
                except ValueError:
                    idx = 0  # fallback: start at beginning
                # Sum all blocks from current_block onward (including current_block)
                for block_num in complete_path[idx:]:
                    for block_info in line_data:
                        if int(block_info.get("Block Number", -1)) == block_num:
                            authority_meters += float(
                                block_info.get("Block Length (m)", 0)
                            )
                            break
                authority += int(authority_meters * 1.09361)
            else:
                logger = get_logger()
                logger.error(
                    "AUTHORITY",
                    f"Train {train_id} next leg dispatch failed: static data unavailable",
                    {"train_id": train_id, "line": line, "leg": current_leg_index},
                )
                return  # Cannot proceed to next leg without static data

            train_info["current_leg_index"] = current_leg_index
            train_info["next_station_block"] = next_station_block
            train_info["commanded_authority"] = authority
            train_info["expected_path"] = complete_path  # Update path for next leg
            # Restore scheduled speed (calculated at initial dispatch)
            scheduled_speed = train_info.get("scheduled_speed", 30)
            train_info["commanded_speed"] = scheduled_speed
            train_info["state"] = "En Route"
            train_info["dwell_start_time"] = None

            logger = get_logger()
            logger.info(
                "TRAIN",
                f"Train {train_id} RESUMING after dwell: speed={scheduled_speed:.2f} mph, authority={authority:.0f} yds",
                {
                    "train_id": train_id,
                    "speed": scheduled_speed,
                    "authority": authority,
                    "current_block": current_block,
                    "next_station_block": next_station_block,
                    "leg": current_leg_index,
                },
            )

    # ============ PLC INFRASTRUCTURE CONTROL ============

    def _execute_plc_cycle(self, track_data, track_model_data):
        """Execute one PLC cycle: switches, lights, gates, failure handling"""
        for line in ["Green", "Red"]:
            line_prefix = "G" if line == "Green" else "R"

            # Get inputs: occupancy, failures, train positions
            occupancy = track_data.get(f"{line_prefix}-Occupancy", [])
            failures = track_data.get(f"{line_prefix}-Failures", [])

            # 1. Switch Control
            self._control_switches_for_line(track_data, line, line_prefix)

            # 2. Traffic Light Control
            self._control_traffic_lights(track_data, line, line_prefix, occupancy)

            # 3. Crossing Gate Control
            self._control_crossing_gates(track_data, line, line_prefix, occupancy)

            # 4. Failure Handling
            self._handle_failures_for_line(track_data, line, line_prefix, failures)

    def _control_switches_for_line(self, track_data, line, line_prefix):
        """Set switches based on active train routes (block-based, train-centric)"""
        config = self.infrastructure[line]
        switch_blocks = config["switch_blocks"]
        switch_routes = config["switch_routes"]
        switches = track_data.get(f"{line_prefix}-switches", [])

        logger = get_logger()

        # Get all trains on this line
        line_trains = {
            tid: info
            for tid, info in self.active_trains.items()
            if info.get("line") == line
        }

        # Iterate through trains, not switches
        for train_id, train_info in line_trains.items():
            current_block = train_info.get("current_block", 0)
            route = train_info.get("route", [])
            expected_path = train_info.get("expected_path", [])

            # If no expected_path, skip this train
            if not expected_path:
                continue

            # Find where train is in the path
            try:
                current_index = expected_path.index(current_block)
            except ValueError:
                logger.error(
                    "SWITCH",
                    f"Train {train_id} at block {current_block} not in expected_path",
                )
                continue

            # Find the next block train will enter
            if current_index + 1 >= len(expected_path):
                continue  # At end of path
            next_block = expected_path[current_index + 1]

            # Check if next_block is a switch
            if next_block not in switch_blocks:
                continue

            # Get the block after the switch
            if current_index + 2 >= len(expected_path):
                continue  # No block after switch
            block_after_switch = expected_path[current_index + 2]

            # Find which switch index this is
            try:
                switch_index = switch_blocks.index(next_block)
            except ValueError:
                continue  # Should not happen

            # Determine which position leads to block_after_switch
            if line == "Green":
                desired_position = self._determine_green_switch_position(
                    next_block,
                    route,
                    current_block,
                    train_info.get("destination"),
                )
            else:
                desired_position = self._determine_red_switch_position(
                    next_block,
                    route,
                    current_block,
                    train_info.get("destination"),
                )

            # Set switch to desired position if different
            if switches[switch_index] != desired_position:
                old_pos = switches[switch_index]
                switches[switch_index] = desired_position
                logger.info(
                    "SWITCH",
                    f"Train {train_id} approaching block {next_block}: switch {old_pos} → {desired_position}",
                    {
                        "train_id": train_id,
                        "line": line,
                        "switch_block": next_block,
                        "current_block": current_block,
                        "next_block": next_block,
                        "block_after_switch": block_after_switch,
                        "old_position": old_pos,
                        "new_position": desired_position,
                        "route_description": switch_routes[next_block][
                            desired_position
                        ],
                    },
                )

    def _determine_green_switch_position(
        self, switch_block, route, current_block, destination
    ):
        """Determine Green Line switch position based on route"""
        # Green Line switches and their routing logic:
        # 13: 0="13->12" (main), 1="1->13" (yard entry)
        # 28: 0="28->29" (main), 1="150->28" (loop back)
        # 57: 0="57->58" (main), 1="57->Yard" (to yard)
        # 63: 0="63->64" (main), 1="Yard->63" (from yard)
        # 77: 0="76->77" (main), 1="77->101" (shortcut)
        # 85: 0="85->86" (main), 1="100->85" (from shortcut)

        if switch_block == 13:
            # Use pos 1 if route includes blocks < 13 (coming from yard)
            if any(b < 13 for b in route):
                return 1

        elif switch_block == 28:
            # Use pos 1 if route includes blocks > 100 (loop back)
            if any(b > 100 for b in route):
                return 1

        elif switch_block == 57:
            # Use pos 1 if destination is yard or route ends before 58
            if destination == "Yard" or (route and route[-1] < 58):
                return 1

        elif switch_block == 63:
            # Use pos 1 if coming from yard (current position is yard block 0)
            if current_block == 0:
                return 1

        elif switch_block == 77:
            # Use pos 1 if route includes blocks in 101-150 range (shortcut)
            if any(101 <= b <= 150 for b in route):
                return 1

        elif switch_block == 85:
            # Use pos 1 if coming from blocks 100+ (from shortcut)
            if current_block >= 100 or any(b >= 100 for b in route[: len(route) // 2]):
                return 1

        return 0  # Default to main line

    def _determine_red_switch_position(
        self, switch_block, route, current_block, destination
    ):
        """Determine Red Line switch position based on route"""
        # Red Line switches and their routing logic:
        # 9: 0="0->9" (from yard), 1="9->0" (to yard)
        # 16: 0="15->16" (main), 1="1->16" (from yard)
        # 27: 0="27->28" (main), 1="27->76" (loop)
        # 33: 0="32->33" (main), 1="33->72" (shortcut)
        # 38: 0="38->39" (main), 1:="38->71" (shortcut)
        # 44: 0="43->44" (main), 1="44->67" (shortcut)
        # 52: 0="52->53" (main), 1="52->66" (shortcut)

        if switch_block == 9:
            # Use pos 1 if going to yard
            if destination == "Yard" or (route and route[-1] == 0):
                return 1

        elif switch_block == 16:
            # Use pos 1 if coming from yard (blocks 1-15)
            if current_block < 16 and route and route[0] <= 16:
                return 1

        elif switch_block == 27:
            # Use pos 1 if route includes blocks 76+ (loop)
            if any(b >= 76 for b in route):
                return 1

        elif switch_block in [33, 38, 44, 52]:
            # Use pos 1 if route uses return path (blocks 66-76)
            if any(66 <= b <= 76 for b in route):
                return 1

        return 0  # Default to main line

    def _control_traffic_lights(self, track_data, line, line_prefix, occupancy):
        """Control traffic lights based on train proximity and occupancy ahead"""
        config = self.infrastructure[line]
        light_blocks = config["light_blocks"]
        lights = track_data.get(f"{line_prefix}-lights", [])

        logger = get_logger()
        light_code_map = {
            "Super Green": [0, 0],  # 00
            "Green": [0, 1],  # 01
            "Yellow": [1, 0],  # 10
            "Red": [1, 1],  # 11
        }

        # For logging old state
        def decode_light(light):
            if light == [0, 0]:
                return "Super Green"
            if light == [0, 1]:
                return "Green"
            if light == [1, 0]:
                return "Yellow"
            if light == [1, 1]:
                return "Red"
            return "Unknown"

        for idx, light_block in enumerate(light_blocks):
            bit_idx = idx * 2  # Each light uses 2 elements
            if bit_idx + 1 >= len(lights):
                continue

            # Find closest train to this light
            min_distance = float("inf")
            closest_train_ahead = False

            for train_id, train_info in self.active_trains.items():
                if train_info.get("line") != line:
                    continue

                train_block = train_info.get("current_block", 0)
                distance = train_block - light_block

                # Only consider trains ahead of the light
                if distance >= 0 and distance < min_distance:
                    min_distance = distance
                    closest_train_ahead = True

            # Determine light state based on distance
            old_light = [lights[bit_idx], lights[bit_idx + 1]]
            new_light_state = "Green"  # Default

            if closest_train_ahead:
                if min_distance <= self.LIGHT_DISTANCE_RED:
                    new_light_state = "Red"
                elif min_distance <= self.LIGHT_DISTANCE_YELLOW:
                    new_light_state = "Yellow"
                elif min_distance <= self.LIGHT_DISTANCE_GREEN:
                    new_light_state = "Green"
                else:
                    new_light_state = "Super Green"
            else:
                # No trains ahead - check occupancy ahead
                blocks_ahead_occupied = 0
                for check_block in range(
                    light_block + 1, min(light_block + 4, len(occupancy))
                ):
                    if occupancy[check_block] == 1:
                        blocks_ahead_occupied += 1

                if blocks_ahead_occupied >= 2:
                    new_light_state = "Red"
                elif blocks_ahead_occupied == 1:
                    new_light_state = "Yellow"
                else:
                    new_light_state = "Super Green"

            new_light = light_code_map[new_light_state]

            # Update if changed
            if old_light != new_light:
                lights[bit_idx] = new_light[0]
                lights[bit_idx + 1] = new_light[1]
                old_state = decode_light(old_light)
                logger.debug(
                    "LIGHT",
                    f"{line} line block {light_block} light: {old_state} → {new_light_state}",
                    {
                        "line": line,
                        "block": light_block,
                        "old_state": old_state,
                        "new_state": new_light_state,
                        "min_train_distance": (
                            min_distance if closest_train_ahead else None
                        ),
                    },
                )

    def _control_crossing_gates(self, track_data, line, line_prefix, occupancy):
        """Control crossing gates based on train proximity"""
        config = self.infrastructure[line]
        gate_blocks = config["gate_blocks"]
        gates = track_data.get(f"{line_prefix}-gates", [])

        logger = get_logger()

        for idx, gate_block in enumerate(gate_blocks):
            if idx >= len(gates):
                continue

            # Find trains near this crossing
            train_approaching = False
            train_at_crossing = False

            for train_id, train_info in self.active_trains.items():
                if train_info.get("line") != line:
                    continue

                train_block = train_info.get("current_block", 0)
                distance = abs(gate_block - train_block)

                if train_block == gate_block:
                    train_at_crossing = True
                elif distance <= self.GATE_CLOSE_DISTANCE:
                    train_approaching = True

            old_gate = gates[idx]
            new_gate = old_gate

            # Gate control logic
            if train_at_crossing or train_approaching:
                new_gate = 0  # Close gate (down)
                # Record time for delay
                if (line, gate_block) not in self.gate_timers:
                    self.gate_timers[(line, gate_block)] = datetime.now()
            else:
                # Check if enough time has passed since train cleared
                if (line, gate_block) in self.gate_timers:
                    elapsed = (
                        datetime.now() - self.gate_timers[(line, gate_block)]
                    ).total_seconds()
                    if elapsed >= self.GATE_OPEN_DELAY:
                        new_gate = 1  # Open gate (up)
                        del self.gate_timers[(line, gate_block)]
                else:
                    new_gate = 1  # Open gate (up)

            # Update if changed
            if old_gate != new_gate:
                gates[idx] = new_gate
                old_state = "Up" if old_gate == 1 else "Down"
                new_state = "Up" if new_gate == 1 else "Down"
                logger.info(
                    "GATE",
                    f"{line} line block {gate_block} crossing gate: {old_state} → {new_state}",
                    {
                        "line": line,
                        "block": gate_block,
                        "old_state": old_state,
                        "new_state": new_state,
                        "reason": (
                            "train_present"
                            if (train_at_crossing or train_approaching)
                            else "delay_complete"
                        ),
                    },
                )

    def _handle_failures_for_line(self, track_data, line, line_prefix, failures):
        """Handle failures: stop trains, adjust authority, attempt rerouting"""
        logger = get_logger()

        for train_id, train_info in list(self.active_trains.items()):
            if train_info.get("line") != line:
                continue

            current_block = train_info.get("current_block", 0)
            route = train_info.get("route", [])

            # Check for failures ahead on route
            failure_blocks = []
            for block in route:
                if block < len(failures) and failures[block] != 0:
                    failure_blocks.append((block, failures[block]))

            if not failure_blocks:
                continue

            # Find closest failure
            closest_failure = None
            min_distance = float("inf")

            for fail_block, fail_type in failure_blocks:
                distance = abs(fail_block - current_block)
                if distance < min_distance:
                    min_distance = distance
                    closest_failure = (fail_block, fail_type)

            if closest_failure and min_distance <= self.FAILURE_STOP_DISTANCE:
                fail_block, fail_type = closest_failure
                failure_names = {0: "None", 1: "Broken Rail", 2: "Power", 3: "Circuit"}

                # Stop the train
                old_speed = train_info.get("commanded_speed", 0)
                old_authority = train_info.get("commanded_authority", 0)

                train_info["commanded_speed"] = 0
                train_info["commanded_authority"] = 0
                train_info["state"] = (
                    f"Stopped - {failure_names.get(fail_type, 'Unknown')} Failure"
                )

                if old_speed > 0 or old_authority > 0:
                    logger.warn(
                        "FAILURE",
                        f"Train {train_id} stopped due to {failure_names.get(fail_type)} at block {fail_block}",
                        {
                            "train_id": train_id,
                            "line": line,
                            "current_block": current_block,
                            "failure_block": fail_block,
                            "failure_type": failure_names.get(fail_type),
                            "distance_to_failure": min_distance,
                            "old_speed": old_speed,
                            "old_authority": old_authority,
                        },
                    )

                # TODO: Attempt rerouting using alternate switches
                # This would require path-finding algorithm to find alternate route

    def _expand_route_to_complete_path(self, route, line):
        """
        Expand a route (list of station blocks) to complete block-by-block path.

        Args:
            route: List of station block numbers (e.g., [65, 73, 77])
            line: Line name (e.g., "Green")

        Returns:
            Complete list of all blocks from yard through entire route
        """
        if not route:
            return [0]

        # Start from yard (block 0)
        complete_path = [0]

        # Build path by connecting consecutive station blocks
        for i in range(len(route)):
            if i == 0:
                # Connect yard (0) to first station
                start = 0
            else:
                # Connect previous station to current station
                start = route[i - 1]

            end = route[i]

            # Calculate path segment between start and end
            segment = self._calculate_complete_block_path(start, end, line)

            # Append segment (skip first block if not first segment to avoid duplicates)
            if i == 0:
                complete_path.extend(segment[1:])  # Skip yard block (already in path)
            else:
                complete_path.extend(segment[1:])  # Skip start block (already in path)

        return complete_path

    def _calculate_complete_block_path(self, start_block, end_block, line):
        """
        Calculate complete block-by-block path between two blocks.
        Handles yard-to-station and station-to-station paths dynamically.
        """
        # Handle yard-to-station paths dynamically
        if start_block == 0:
            if line == "Green":
                # Green Line: Yard exits at block 63
                if end_block >= 63 and end_block <= 150:
                    # Direct path: 0 → 63 → 64 → ... → end_block
                    return [0] + list(range(63, end_block + 1))
                else:
                    # Loop path: 0 → 63 → ... → 150 → 28 → ... → end_block
                    path = [0] + list(range(63, 151))  # 0 to 150
                    if end_block >= 28:
                        # End block in range 28-62
                        path.extend(range(28, end_block + 1))
                    else:
                        # End block in range 1-27 (wraps around)
                        path.extend(range(28, 63))  # 28 to 62
                        path.extend(range(1, end_block + 1))  # 1 to end_block
                    return path
            elif line == "Red":
                # Red Line: Yard exits at block 9
                # Direct path: 0 → 9 → 10 → ... → end_block
                return [0] + list(range(9, end_block + 1))

        # For Green Line station-to-station paths, use topology knowledge
        if line == "Green" and start_block != 0:
            return self._calculate_green_line_station_to_station_path(
                start_block, end_block
            )

        # For Red Line or simple sequential paths
        if line == "Red":
            path = [start_block]
            current = start_block
            while current != end_block:
                if current < end_block:
                    current += 1
                else:
                    current -= 1  # FIXED: was current += 1 in both branches
                path.append(current)
                if len(path) > 200:
                    break
            return path

        # Fallback for unknown cases
        return [start_block, end_block]

    def _calculate_green_line_station_to_station_path(self, start_block, end_block):
        """Calculate path between two blocks on Green Line using track topology.
        Handles non-sequential transitions like 150→28 via switch.
        """
        # Green Line topology:
        # Direct section: 63-150 (continuous)
        # Loop section: 28-62 then 1-2 (with switch at 150→28 and wrapping)

        # Special case: crossing switch 28 (block 150 to block 28)
        if start_block == 150 and end_block <= 62:
            # Path goes through switch: 150 → 28 → 29 → ... → end_block
            if end_block >= 28:
                return [150, 28] + list(range(29, end_block + 1))
            else:
                # Wraps around: 150 → 28 → ... → 62 → 1 → ... → end_block
                return [150, 28] + list(range(29, 63)) + list(range(1, end_block + 1))

        # Both blocks in direct section (63-150)
        if (
            start_block >= 63
            and end_block >= 63
            and start_block <= 150
            and end_block <= 150
        ):
            if start_block < end_block:
                return list(range(start_block, end_block + 1))
            else:
                return list(range(start_block, end_block - 1, -1))

        # Both blocks in loop section (28-62 or 1-2)
        if start_block <= 62 and end_block <= 62:
            if start_block < end_block:
                return list(range(start_block, end_block + 1))
            else:
                return list(range(start_block, end_block - 1, -1))

        # Start in loop, end in direct: need to go through yard
        if start_block <= 62 and end_block >= 63:
            # This shouldn't happen in normal operation
            # Trains don't reverse from loop to direct path
            return [start_block, end_block]  # Fallback

        # Start in direct, end in loop: continue forward through 150→28
        if start_block >= 63 and start_block <= 150 and end_block <= 62:
            if end_block >= 28:
                # Destination is in 28-62 range
                return (
                    list(range(start_block, 151))
                    + [28]
                    + list(range(29, end_block + 1))
                )
            else:
                # Destination is in 1-2 range (wraps around)
                return (
                    list(range(start_block, 151))
                    + [28]
                    + list(range(29, 63))
                    + list(range(1, end_block + 1))
                )

        # Fallback for unexpected cases
        return [start_block, end_block]

    def _set_switches_for_route(
        self, track_data, current_block, route, line, line_prefix
    ):
        """Set switches to route train through the specified route (list of station blocks)"""
        config = self.infrastructure[line]
        switch_blocks = config["switch_blocks"]

        # Calculate complete block-by-block path to first station in route
        if not route:
            return

        destination_block = route[0]  # Next station
        complete_path = self._calculate_complete_block_path(
            current_block, destination_block, line
        )

        # Store expected path for verification
        train_id = None
        for tid, info in self.active_trains.items():
            if info.get("line") == line and info.get("current_block") == current_block:
                train_id = tid
                break

        if train_id:
            self.active_trains[train_id]["expected_path"] = complete_path

        # For each switch, check if it's in the path and which direction is needed
        for idx, switch_block in enumerate(switch_blocks):
            switch_position = 0  # Default: straight

            # Only set switch if it's in the path
            if switch_block in complete_path:
                switch_idx = complete_path.index(switch_block)
                prev_block = complete_path[switch_idx - 1] if switch_idx > 0 else None
                next_block = (
                    complete_path[switch_idx + 1]
                    if switch_idx + 1 < len(complete_path)
                    else None
                )

                # Hardcoded switch logic for Green Line
                if line == "Green":
                    # 13: 0=straight to 12, 1=branch to 1
                    if switch_block == 13:
                        switch_position = 0 if next_block == 12 else 1
                    # 28: 0=straight to 29, 1=branch to 150
                    elif switch_block == 28:
                        # If coming from 150 to 28, branch (1) should go to 27
                        if prev_block == 150:
                            switch_position = 1 if next_block == 27 else 0
                        else:
                            switch_position = 0 if next_block == 29 else 1
                    # 57: 0=straight to 58, 1=branch to Yard
                    elif switch_block == 57:
                        switch_position = 0 if next_block == 58 else 1
                    # 63: 0=straight to 64, 1=branch from Yard
                    elif switch_block == 63:
                        switch_position = 0 if prev_block == 62 else 1
                    # 77: 0=straight to 76, 1=branch to 101
                    elif switch_block == 77:
                        switch_position = 0 if next_block == 76 else 1
                    # 85: 0=straight to 86, 1=branch to 100
                    elif switch_block == 85:
                        switch_position = 0 if next_block == 86 else 1

                # Hardcoded switch logic for Red Line
                elif line == "Red":
                    # 9: 0=to 10, 1=to Yard
                    if switch_block == 9:
                        switch_position = 0 if next_block == 10 else 1
                    # 16: 0=straight to 15, 1=branch to 1
                    elif switch_block == 16:
                        switch_position = 0 if prev_block == 15 else 1
                    # 27: 0=straight to 28, 1=branch to 76
                    elif switch_block == 27:
                        switch_position = 0 if next_block == 28 else 1
                    # 33: 0=straight to 32, 1=branch to 72
                    elif switch_block == 33:
                        switch_position = 0 if prev_block == 32 else 1
                    # 38: 0=straight to 39, 1=branch to 71
                    elif switch_block == 38:
                        switch_position = 0 if next_block == 39 else 1
                    # 44: 0=straight to 43, 1=branch to 67
                    elif switch_block == 44:
                        switch_position = 0 if prev_block == 43 else 1
                    # 52: 0=straight to 53, 1=branch to 66
                    elif switch_block == 52:
                        switch_position = 0 if next_block == 53 else 1

            track_data[f"{line_prefix}-switches"][idx] = switch_position

    def _write_train_commands(self):
        """Write commanded speeds/authorities to track I/O for all lines"""
        data = self._read_track_io()
        if not data:
            return

        # Commented out - high-frequency debug logging
        # logger = get_logger()
        # logger.debug(
        #     "TRAIN",
        #     f"_write_train_commands called. Active trains: {list(self.active_trains.keys())}",
        #     {"active_trains": len(self.active_trains)},
        # )

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

        # Commented out - high-frequency debug logging
        # logger.debug(
        #     "TRAIN",
        #     f"Green trains: {list(green_trains.keys())}, Red trains: {list(red_trains.keys())}",
        #     {"green_count": len(green_trains), "red_count": len(red_trains)},
        # )

        # Green line commands
        g_speeds = []
        g_authorities = []
        for train_id in sorted(green_trains.keys()):
            train_info = green_trains[train_id]
            speed = train_info.get("commanded_speed", 0)
            authority = train_info.get("commanded_authority", 0)
            g_speeds.append(speed)
            g_authorities.append(authority)

            # Commented out - high-frequency debug logging
            # if speed > 0 or authority > 0:
            #     logger = get_logger()
            #     logger.debug(
            #         "TRAIN",
            #         f"Writing commands for Train {train_id}: speed={speed}, authority={authority}",
            #         {"train_id": train_id, "speed": speed, "authority": authority},
            #     )

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

        # Log non-zero commands for visibility
        logger = get_logger()
        for train_id in sorted(green_trains.keys()):
            speed = green_trains[train_id].get("commanded_speed", 0)
            authority = green_trains[train_id].get("commanded_authority", 0)
            if speed > 0 or authority > 0:
                logger.info(
                    "TRAIN",
                    f"Train {train_id} commands written: speed={speed:.2f} mph, authority={authority:.0f} yds",
                    {"train_id": train_id, "speed": speed, "authority": authority},
                )
        for train_id in sorted(red_trains.keys()):
            speed = red_trains[train_id].get("commanded_speed", 0)
            authority = red_trains[train_id].get("commanded_authority", 0)
            if speed > 0 or authority > 0:
                logger.info(
                    "TRAIN",
                    f"Train {train_id} commands written: speed={speed:.2f} mph, authority={authority:.0f} yds",
                    {"train_id": train_id, "speed": speed, "authority": authority},
                )

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
        """Update throughput display using actual boarding data"""
        track_model_data = self._read_track_model()

        green_passengers = 0
        red_passengers = 0

        if track_model_data:
            # Sum passengers from all trains on each line
            for train_id, train_info in self.active_trains.items():
                line = train_info.get("line")
                line_prefix = "G" if line == "Green" else "R"
                train_key = f"{line_prefix}_train_{train_id}"

                if train_key in track_model_data:
                    beacon_data = track_model_data[train_key].get("beacon", {})
                    passengers = beacon_data.get("passengers_boarding", 0)

                    if line == "Green":
                        green_passengers += passengers
                    else:
                        red_passengers += passengers

        self.throughput_green = green_passengers
        self.throughput_red = red_passengers

        self.throughput_green_label.config(
            text=f"🟢 Green: {self.throughput_green} passengers"
        )
        self.throughput_red_label.config(
            text=f"🔴 Red: {self.throughput_red} passengers"
        )

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
