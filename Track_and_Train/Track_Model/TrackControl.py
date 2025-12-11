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

    def dispatch_train_from_schedule(self, schedule_entry):
        """
        Dispatches a train based on a schedule entry.
        """
        # Extract schedule details
        train_id = schedule_entry["train_id"]
        line = schedule_entry["line"]
        destination = schedule_entry["destination"]
        dispatch_time = schedule_entry["dispatch_time"]
        arrival_time = schedule_entry["arrival_time"]

        # Check if the train already exists in active_trains
        if train_id in self.active_trains:
            train = self.active_trains[train_id]
            if train["state"] == "Arrived":
                # Update train for the next leg
                train.update(
                    {
                        "line": line,
                        "destination": destination,
                        "dispatch_time": dispatch_time,
                        "arrival_time": arrival_time,
                        "state": "Dispatching",
                    }
                )
                logger = get_logger()
                logger.info(
                    "DISPATCH",
                    f"Train {train_id} updated for next leg.",
                    {"train_id": train_id},
                )
        else:
            # Create a new train entry from the Yard
            self.active_trains[train_id] = {
                "line": line,
                "destination": destination,
                "dispatch_time": dispatch_time,
                "arrival_time": arrival_time,
                "state": "Dispatching",
            }
            logger = get_logger()
            logger.info(
                "DISPATCH",
                f"Train {train_id} dispatched from Yard.",
                {"train_id": train_id},
            )

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

        self.load_schedule_btn = tk.Button(
            frame, text="📋 LOAD SCHEDULE", command=self._load_schedule_file
        )
        self.load_schedule_btn.pack(side="left", padx=5)

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
        Dispatches a train based on a schedule entry.
        """
        # Extract schedule details
        train_id = schedule_entry["train_id"]
        line = schedule_entry["line"]
        destination = schedule_entry["destination"]
        dispatch_time = schedule_entry["dispatch_time"]
        arrival_time = schedule_entry["arrival_time"]

        # Check if the train already exists in active_trains
        if train_id in self.active_trains:
            train = self.active_trains[train_id]
            if train["state"] == "Arrived":
                # Update train for the next leg
                train.update(
                    {
                        "line": line,
                        "destination": destination,
                        "dispatch_time": dispatch_time,
                        "arrival_time": arrival_time,
                        "state": "Dispatching",
                    }
                )
                logger = get_logger()
                logger.info(
                    "DISPATCH",
                    f"Train {train_id} updated for next leg.",
                    {"train_id": train_id},
                )
        else:
            # Create a new train entry from the Yard
            self.active_trains[train_id] = {
                "line": line,
                "destination": destination,
                "dispatch_time": dispatch_time,
                "arrival_time": arrival_time,
                "state": "Dispatching",
            }
            logger = get_logger()
            logger.info(
                "DISPATCH",
                f"Train {train_id} dispatched from Yard.",
                {"train_id": train_id},
            )

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

        self.load_schedule_btn = tk.Button(
            frame, text="📋 LOAD SCHEDULE", command=self._load_schedule_file
        )
        self.load_schedule_btn.pack(side="left", padx=5)

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
