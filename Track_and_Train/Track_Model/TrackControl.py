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
from schedule_manager import (
    ScheduleManager,
)  # Import ScheduleManager for automatic mode


class TrackControl:
    def _check_traffic_lights_ahead(self, train_id, train_info, line, track_data):
        """
        Check 3 blocks ahead for red traffic lights.
        Stop train if red light detected.
        Returns: True if red light detected (need to stop), False otherwise
        """
        logger = get_logger()
        current_block = train_info.get("current_block", 0)
        expected_path = train_info.get("expected_path", [])
        if not expected_path or current_block not in expected_path:
            return False  # Can't check without path
        try:
            current_idx = expected_path.index(current_block)
        except ValueError:
            return False
        # Check next 3 blocks ahead
        blocks_to_check = expected_path[current_idx + 1 : current_idx + 4]
        config = self.infrastructure[line]
        light_blocks = config["light_blocks"]
        line_prefix = "G" if line == "Green" else "R"
        lights = track_data.get(f"{line_prefix}-lights", [])
        for check_block in blocks_to_check:
            if check_block in light_blocks:
                light_idx = light_blocks.index(check_block)
                bit_idx = light_idx * 2  # Each light uses 2 bits
                if bit_idx + 1 >= len(lights):
                    continue  # Light data not available
                light_bits = [lights[bit_idx], lights[bit_idx + 1]]
                # 00 = Super Green, 01 = Green, 10 = Yellow, 11 = Red
                if light_bits == [1, 1]:  # Red light
                    if not train_info.get("red_light_stopped", False):
                        train_info["commanded_speed"] = 0
                        train_info["commanded_authority"] = 0
                        train_info["red_light_stopped"] = True
                        train_info["red_light_block"] = check_block
                        logger.warn(
                            "TRAFFIC_LIGHT",
                            f"Train {train_id} STOPPED: Red light at block {check_block}",
                            {
                                "train_id": train_id,
                                "line": line,
                                "current_block": current_block,
                                "red_light_block": check_block,
                                "blocks_ahead": check_block - current_block,
                            },
                        )
                    return True
                elif light_bits == [1, 0]:  # Yellow light
                    if not train_info.get("yellow_light_warned", False):
                        train_info["yellow_light_warned"] = True
                        logger.info(
                            "TRAFFIC_LIGHT",
                            f"Train {train_id}: Yellow light ahead at block {check_block}",
                            {
                                "train_id": train_id,
                                "current_block": current_block,
                                "yellow_light_block": check_block,
                            },
                        )
        # No red lights ahead - resume if previously stopped
        if train_info.get("red_light_stopped", False):
            train_info["red_light_stopped"] = False
            train_info["yellow_light_warned"] = False
            train_info.pop("red_light_block", None)
            logger.info(
                "TRAFFIC_LIGHT",
                f"Train {train_id} clear: No red lights within 3 blocks ahead",
                {
                    "train_id": train_id,
                    "current_block": current_block,
                },
            )
        return False

    def _check_train_separation(self, train_id, train_info, line, occupancy):
        """
        Check if another train is too close (within 1 block ahead).
        Maintains at least 1 empty block separation between trains.
        Returns: True if separation violated (need to stop), False otherwise
        """
        logger = get_logger()
        current_block = train_info.get("current_block", 0)
        expected_path = train_info.get("expected_path", [])

        if not expected_path or current_block not in expected_path:
            return False  # Can't check without path

        try:
            current_idx = expected_path.index(current_block)
        except ValueError:
            return False

        # Check next 2 blocks ahead (immediate next + 1 buffer)
        blocks_to_check = expected_path[current_idx + 1 : current_idx + 3]

        for check_block in blocks_to_check:
            if check_block - 1 < len(occupancy) and occupancy[check_block - 1] == 1:
                other_train_present = False

                for other_id, other_info in self.active_trains.items():
                    if other_id == train_id:
                        continue  # Skip self

                    if other_info.get("line") != line:
                        continue  # Different line

                    if other_info.get("current_block") == check_block:
                        other_train_present = True

                        # Stop this train
                        if not train_info.get("separation_stopped", False):
                            train_info["commanded_speed"] = 0
                            train_info["commanded_authority"] = 0
                            train_info["separation_stopped"] = True

                            logger.warn(
                                "SEPARATION",
                                f"Train {train_id} STOPPED: Train {other_id} too close at block {check_block}",
                                {
                                    "train_id": train_id,
                                    "other_train_id": other_id,
                                    "current_block": current_block,
                                    "blocked_by_block": check_block,
                                    "blocks_ahead": check_block - current_block,
                                },
                            )
                        return True

                if not other_train_present:
                    logger.debug(
                        "SEPARATION",
                        f"Train {train_id}: Block {check_block} occupied but no train identified",
                        {"train_id": train_id, "check_block": check_block},
                    )

        # No train ahead - resume if previously stopped
        if train_info.get("separation_stopped", False):
            train_info["separation_stopped"] = False

            # Restore speed and recalculate authority based on state
            state = train_info.get("state")

            if state == "En Route":
                # Restore scheduled speed
                scheduled_speed = train_info.get("scheduled_speed", 30)
                train_info["commanded_speed"] = scheduled_speed

                # Recalculate authority to next station
                current_leg_index = train_info.get("current_leg_index", 0)
                route = train_info.get("route", [])

                if route and current_leg_index < len(route):
                    next_station_block = route[current_leg_index]
                    complete_path = self._calculate_complete_block_path(
                        current_block, next_station_block, line
                    )

                    # Calculate authority
                    static_data = self._read_static_data()
                    if static_data and complete_path:
                        authority_meters = 0.0
                        line_data = static_data.get("static_data", {}).get(line, [])

                        try:
                            idx = complete_path.index(current_block)
                        except ValueError:
                            idx = 0

                        for block_num in complete_path[idx:]:
                            for block_info in line_data:
                                if int(block_info.get("Block Number", -1)) == block_num:
                                    authority_meters += float(
                                        block_info.get("Block Length (m)", 0)
                                    )
                                    break

                        authority = int(authority_meters * 1.09361)
                        train_info["commanded_authority"] = authority
                    else:
                        train_info["commanded_authority"] = 500  # Fallback

                logger.info(
                    "SEPARATION",
                    f"Train {train_id} RESUMING: path clear, speed={scheduled_speed:.2f} mph, authority={train_info.get('commanded_authority', 0):.0f} yds",
                    {
                        "train_id": train_id,
                        "current_block": current_block,
                        "resumed_speed": scheduled_speed,
                        "resumed_authority": train_info.get("commanded_authority", 0),
                    },
                )
            else:
                logger.info(
                    "SEPARATION",
                    f"Train {train_id} clear: No trains within 2 blocks ahead",
                    {
                        "train_id": train_id,
                        "current_block": current_block,
                    },
                )

        return False

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
                    77: {0: "77->78", 1: "77->101"},
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

        # CREATE SCHEDULE MANAGER BEFORE BUILDING UI
        self.schedule_manager = ScheduleManager(self)  # ← MOVED THIS HERE

        # Build UI in parent (now schedule_manager exists)
        self._build_ui()
        self._start_file_watcher()
        self._start_automatic_loop()

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
            for end_station in station_names:
                route = self._get_stations_on_path_to_destination(
                    line, end_station, station_names, stations
                )
                lookup[(line, "Yard", end_station)] = route

            # Add station-to-station routes
            for start_station in station_names:
                for end_station in station_names:
                    if start_station != end_station:
                        # Get full route from Yard to destination
                        full_route = self._get_stations_on_path_to_destination(
                            line, end_station, station_names, stations
                        )

                        # Trim route to start from start_station
                        route = self._trim_route_from_start_station(
                            start_station, end_station, full_route, stations
                        )

                        lookup[(line, start_station, end_station)] = route

        return lookup

    def _get_stations_on_path_to_destination(
        self, line, destination, station_names, stations
    ):
        """Determine which stations are visited on path from Yard to destination."""
        if line == "Green":
            dest_blocks = stations[destination]

            # For dual-platform stations, pick closer one based on origin (Yard = block 0)
            if isinstance(dest_blocks, list):
                if destination == "Glenbury":
                    # From Yard (0): exits at 63 → reaches 65 first
                    dest_block = 65
                elif destination == "Dormont":
                    # From Yard (0): exits at 63 → reaches 73 first
                    dest_block = 73
                elif destination == "Overbrook":
                    # Blocks 63-122: reach 123 first (main loop)
                    # All others: reach 57 first (return path)
                    dest_block = 123  # From Yard, always 123 first
                elif destination == "Inglewood":
                    # Blocks 63-131: reach 132 first (main loop)
                    # All others: reach 48 first (return path)
                    dest_block = 132  # From Yard, always 132 first
                elif destination == "Central":
                    # Blocks 63-140: reach 141 first (main loop)
                    # All others: reach 39 first (return path)
                    dest_block = 141  # From Yard, always 141 first
                else:
                    dest_block = dest_blocks[0]
            else:
                dest_block = dest_blocks

            # Station sequence in order from Yard
            before_77 = [
                ("Glenbury", 65),
                ("Dormont", 73),
                ("Mt. Lebanon", 77),
            ]

            poplar_spur = [
                ("Poplar", 88),
                ("Castle Shannon", 96),
            ]

            main_loop = [
                ("Dormont", 105),
                ("Glenbury", 114),
                ("Overbrook", 123),
                ("Inglewood", 132),
                ("Central", 141),
            ]

            return_path = [
                ("South Bank", 31),
                ("Whited", 22),
                ("Edgebrook", 9),
                ("Pioneer", 2),
            ]

            block_sequence = []

            for stn_name, stn_block in before_77:
                block_sequence.append(stn_block)
                if stn_block == dest_block:
                    return block_sequence

            if dest_block in [88, 96]:
                for stn_name, stn_block in poplar_spur:
                    block_sequence.append(stn_block)
                    if stn_block == dest_block:
                        return block_sequence
            else:
                for stn_name, stn_block in main_loop:
                    block_sequence.append(stn_block)
                    if stn_block == dest_block:
                        return block_sequence

                for stn_name, stn_block in return_path:
                    block_sequence.append(stn_block)
                    if stn_block == dest_block:
                        return block_sequence

            return block_sequence

        elif line == "Red":
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

            block_sequence = []
            for stn in ordered_stations:
                stn_blocks = stations.get(stn)
                if stn_blocks:
                    block = (
                        stn_blocks[0] if isinstance(stn_blocks, list) else stn_blocks
                    )
                    block_sequence.append(block)
                if stn == destination:
                    break

            return block_sequence

        return []

    def _build_route_lookup_via_id(self):
        """Build route lookup dictionary keyed by route_id for faster lookup"""
        lookup = {}
        route_id = 0

        for line in ["Green", "Red"]:
            stations = self.infrastructure[line]["stations"]
            station_names = list(stations.keys())

            # Yard-to-station routes
            for end_station in station_names:
                route = self._get_stations_on_path_to_destination(
                    line, end_station, station_names, stations
                )

                lookup[route_id] = {
                    "line": line,
                    "start_station": "Yard",
                    "end_station": end_station,
                    "route": route,
                }
                route_id += 1

            # Station-to-station routes
            for start_station in station_names:
                for end_station in station_names:
                    if start_station == end_station:
                        continue

                    # Get full path from Yard to destination
                    full_route = self._get_stations_on_path_to_destination(
                        line, end_station, station_names, stations
                    )

                    if line == "Green":
                        # Green Line: remove stations already passed
                        route = self._trim_route_from_start_station(
                            start_station, end_station, full_route, stations
                        )
                    else:
                        # Red Line: simple - just remove stations before start
                        start_blocks = stations[start_station]
                        start_block = (
                            start_blocks[0]
                            if isinstance(start_blocks, list)
                            else start_blocks
                        )

                        # Find start_block in route and trim
                        try:
                            start_idx = full_route.index(start_block)
                            route = full_route[start_idx:]
                        except ValueError:
                            route = full_route

                    lookup[route_id] = {
                        "line": line,
                        "start_station": start_station,
                        "end_station": end_station,
                        "route": route,
                    }
                    route_id += 1

        return lookup

    def _trim_route_from_start_station(
        self, start_station, end_station, full_route, stations
    ):
        """
        Trim route to start from start_station instead of Yard.
        Handles Green Line topology - only loop around if destination is behind you.
        """
        # Get start and end blocks
        start_blocks = stations[start_station]
        start_block = (
            start_blocks[0] if isinstance(start_blocks, list) else start_blocks
        )

        end_blocks = stations[end_station]
        end_block = end_blocks[0] if isinstance(end_blocks, list) else end_blocks

        # Check if start and end are both in the route
        try:
            start_idx = full_route.index(start_block)
            end_idx = full_route.index(end_block)
        except ValueError:
            # One of them not in route - return full route
            return full_route

        # If destination is AHEAD of us in the route, just go straight there
        if end_idx > start_idx:
            return full_route[start_idx : end_idx + 1]

        # Destination is BEHIND us - need to loop around

        # Special case: Poplar/Castle Shannon (dead-end spur)
        if start_station in ["Poplar", "Castle Shannon"]:
            # Must loop back via 100→85→77→101, then continue to destination
            # Remove [0, 65, 73] but keep 77 to loop back
            if 77 in full_route:
                idx_77 = full_route.index(77)
                return full_route[idx_77:]
            return full_route

        # For main loop stations [105, 114, 123, 132, 141]
        if start_block in [105, 114, 123, 132, 141]:
            if end_block in [31, 39, 48, 57]:
                # ...existing code for return path...
                route = []
                for block in [105, 114, 123, 132, 141, 150]:
                    if block >= start_block:
                        route.append(block)
                route.append(28)
                for block in range(27, end_block - 1, -1):
                    route.append(block)
                route.append(end_block)
                return route
            elif end_block in [22, 9, 2]:
                # ...existing code for up after 150->28...
                route = []
                for block in [105, 114, 123, 132, 141, 150]:
                    if block >= start_block:
                        route.append(block)
                route.append(28)
                for block in range(27, end_block - 1, -1):
                    route.append(block)
                route.append(end_block)
                return route
            else:
                # Destination is Glenbury/Dormont/Mt.Lebanon (63-77)
                # Need to go: current → 141 → 150 → 28 → 29 → ... → 62 → 63 → destination
                route = []
                for block in [105, 114, 123, 132, 141, 150]:
                    if block >= start_block:
                        route.append(block)
                route.append(28)
                route.extend(range(29, 63))  # 28 → 62
                route.extend(range(63, end_block + 1))  # 63 → destination
                logger = get_logger()
                logger.info(
                    "ROUTING",
                    f"Main loop to first section: {start_station} ({start_block}) → {end_station} ({end_block})",
                    {"route": route},
                )
                return route

        # For return path stations [31, 39, 48, 57]
        if start_block in [31, 39, 48, 57]:
            close_stations = [31, 39, 48, 57]

            # If destination is also on return path and ahead
            if end_block in close_stations:
                start_pos = close_stations.index(start_block)
                end_pos = close_stations.index(end_block)

                if end_pos > start_pos:
                    # Destination ahead - direct path
                    return close_stations[start_pos : end_pos + 1]

            # Destination behind or not on return path - prepend remaining + full route
            start_pos = close_stations.index(start_block)
            prefix = close_stations[start_pos:]
            return prefix + full_route

        # For Whited/Edgebrook/Pioneer [22, 9, 2]
        if start_block in [22, 9, 2]:
            # If destination is South Bank/Central/Inglewood/Overbrook (ahead on return path)
            if end_block in [31, 39, 48, 57]:
                # Direct path forward
                return list(range(start_block, end_block + 1))
            else:
                # Need to loop past Yard
                return full_route

        # Default: destination is ahead in route
        return full_route[start_idx : end_idx + 1]

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
        elif mode == "maintenance":
            self.maint_frame.tkraise()

    def _build_mode_frames(self):
        """Build frames for each mode"""
        container = tk.Frame(self.parent, bg="#2b2d31")
        container.grid(row=2, column=0, sticky="nsew", padx=5, pady=5)
        container.grid_rowconfigure(0, weight=1)
        container.grid_columnconfigure(0, weight=1)

        # Ensure all mode frames are initialized before switching
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

        # Default to automatic mode
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

        self.load_schedule_btn = tk.Button(
            frame,
            text="📋 LOAD SCHEDULE",
            font=("Segoe UI", 9, "bold"),
            bg="#5865f2",
            fg="white",
            width=15,
            relief="flat",
            cursor="hand2",
            command=self.schedule_manager.load_schedule_file,  # ← CHANGED
        )
        self.load_schedule_btn.pack(side="left", padx=5)

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
        self.schedule_manager.start()  # ← ADD THIS
        self.auto_start_btn.config(state="disabled")
        self.auto_stop_btn.config(state="normal")
        self.auto_status.config(text="🟢 Running")

    def _stop_automatic(self):
        """Stop automatic control"""
        self.automatic_running = False
        self.schedule_manager.stop()  # ← ADD THIS
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

            # Get route from CURRENT LOCATION to destination
            config = self.infrastructure[line]
            stations = config["stations"]

            # Determine starting station - use current station if train exists
            if train_id in self.active_trains:
                start_station = self.active_trains[train_id].get(
                    "current_station", "Yard"
                )
            else:
                start_station = "Yard"  # New train starts at Yard

            # Look up route
            route_key = (line, start_station, dest)
            route = self.route_lookup_via_station.get(route_key, [])

            if not route:
                logger = get_logger()
                logger.error(
                    "ROUTE",
                    f"No route found from {start_station} to {dest}",
                    {"start_station": start_station, "destination": dest, "line": line},
                )
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
        """Start automatic control loop in a background thread (UI updates remain on main thread)"""
        logger = get_logger()
        logger.info(
            "THREADING", "Starting automatic control cycle in background thread."
        )
        self._stop_event = threading.Event()
        self._auto_thread = threading.Thread(
            target=self._automatic_control_cycle_thread, daemon=True
        )
        self._auto_thread.start()

    def _automatic_control_cycle_thread(self):
        while not getattr(self, "_stop_event", threading.Event()).is_set():
            self._automatic_control_cycle()
            # Sleep for 500ms (cycle time)
            self._stop_event.wait(0.5)

    def _automatic_control_cycle(self):
        """Execute one cycle of automatic control with state machine (runs in background thread, UI updates scheduled on main thread)"""
        logger = get_logger()
        try:
            track_data = self._read_track_io()
            track_model_data = self._read_track_model()

            if track_data and track_model_data:
                # Process schedule (NEW LINE)
                self.schedule_manager.process_schedule_tick()  # ← ADD THIS

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

                # Schedule UI update on main thread
                self.parent.after(0, self._update_all_displays, track_data)
        except Exception as e:
            logger.error("THREADING", f"Exception in background control cycle: {e}")

    def _update_train_positions(self, occupancy, line):
        """Update train positions from occupancy array for specific line"""
        # Find all occupied blocks
        occupied_blocks = [idx for idx, occ in enumerate(occupancy) if occ == 1]
        if not occupied_blocks:
            return  # No trains on this line

        # Get trains on this line
        line_trains = {
            tid: info
            for tid, info in self.active_trains.items()
            if info.get("line") == line
        }
        if not line_trains:
            return  # No active trains for this line

        logger = get_logger()

        # Match each train to closest occupied block on their expected path
        assigned_blocks = set()

        for train_id, train_info in line_trains.items():
            current_block = train_info.get("current_block")
            expected_path = train_info.get("expected_path", [])

            best_match = None
            best_distance = float("inf")
            occ_idx_for_station = None

            for occ_idx in occupied_blocks:
                actual_block = occ_idx + 1  # Convert to 1-indexed

                if actual_block in assigned_blocks:
                    continue  # Already assigned to another train

                # Check if this block is on the expected path
                if expected_path and actual_block in expected_path:
                    # Find distance along path
                    try:
                        current_idx = (
                            expected_path.index(current_block)
                            if current_block in expected_path
                            else 0
                        )
                        actual_idx = expected_path.index(actual_block)
                        path_distance = abs(actual_idx - current_idx)
                    except ValueError:
                        path_distance = float("inf")
                else:
                    # Not on expected path - use Manhattan distance as fallback
                    path_distance = (
                        abs(actual_block - current_block)
                        if current_block
                        else float("inf")
                    )

                # Prefer blocks on expected path and closer to current position
                if path_distance < best_distance:
                    best_distance = path_distance
                    best_match = actual_block
                    occ_idx_for_station = occ_idx

            # Assign best match to this train
            if best_match is not None:
                old_block = train_info.get("current_block")
                train_info["current_block"] = best_match
                assigned_blocks.add(best_match)

                # Log block transitions
                if old_block is not None and old_block != best_match:
                    logger.info(
                        "TRAIN",
                        f"Train {train_id} BLOCK TRANSITION: {old_block} → {best_match}",
                        {
                            "train_id": train_id,
                            "old_block": old_block,
                            "new_block": best_match,
                            "state": train_info.get("state"),
                            "motion": train_info.get("motion_state", "Unknown"),
                        },
                    )

                # Path verification: check if train is on expected path
                expected_path = train_info.get("expected_path", [])
                if expected_path and best_match not in expected_path:
                    logger.warn(
                        "ROUTING",
                        f"Train {train_id} DEVIATED: expected path {expected_path}, actual block {best_match}",
                        {
                            "train_id": train_id,
                            "expected_path": expected_path,
                            "actual_block": best_match,
                        },
                    )

                # Check if at station
                config = self.infrastructure[line]
                stations = config["stations"]
                block_to_station = {}
                for station_name, blocks in stations.items():
                    if isinstance(blocks, list):
                        for block in blocks:
                            block_to_station[block] = station_name
                    else:
                        block_to_station[blocks] = station_name

                if (
                    occ_idx_for_station is not None
                    and (occ_idx_for_station + 1) in block_to_station
                ):
                    train_info["current_station"] = block_to_station[
                        occ_idx_for_station + 1
                    ]
            else:
                # No occupied block found for this train
                logger.warn(
                    "POSITION",
                    f"Train {train_id} has no matching occupied block",
                    {
                        "train_id": train_id,
                        "current_block": current_block,
                        "occupied_blocks": [idx + 1 for idx in occupied_blocks],
                        "assigned_blocks": list(assigned_blocks),
                    },
                )

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

        # SAFETY CHECKS (run for all states except Arrived/Dwelling/At Station)
        if state not in ["Arrived", "Dwelling", "At Station"]:
            occupancy = track_data.get(f"{line_prefix}-Occupancy", [])
            # Check train separation
            if self._check_train_separation(train_id, train_info, line, occupancy):
                return  # Train stopped for separation, skip state machine
            # Check traffic lights
            if self._check_traffic_lights_ahead(train_id, train_info, line, track_data):
                return  # Train stopped for red light, skip state machine

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
        line = train_info.get("line")

        # Calculate optimal speed based on arrival time and total distance
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

                # Calculate required speed accounting for acceleration/deceleration
                if time_available > 0:
                    # Physics constants
                    accel = 1.64  # ft/s²
                    decel = 3.94  # ft/s²

                    # Convert distance to feet
                    total_distance_ft = total_distance_yards * 3.0

                    # Solve for cruise speed assuming: accel phase + cruise phase + decel phase
                    # Total distance: d = (v²/2a) + v*t_cruise + (v²/2d)
                    # Total time: t = (v/a) + t_cruise + (v/d)
                    # Rearranging to solve for v (cruise velocity):
                    # d = v²(1/2a + 1/2d) + v*(t - v/a - v/d)
                    # d = v²(1/2a + 1/2d) + v*t - v²(1/a + 1/d)
                    # d = v*t + v²(1/2a + 1/2d - 1/a - 1/d)
                    # d = v*t - v²(1/2a + 1/2d)
                    # Rearranging: v²(1/2a + 1/2d) - v*t + d = 0
                    # Standard form: Av² + Bv + C = 0

                    A = 1 / (2 * accel) + 1 / (2 * decel)
                    B = -time_available
                    C = total_distance_ft

                    discriminant = B**2 - 4 * A * C

                    if discriminant >= 0:
                        # Solve quadratic for cruise velocity (ft/s)
                        cruise_velocity_fps = (-B - (discriminant**0.5)) / (2 * A)
                        optimal_speed = cruise_velocity_fps * 0.681818  # ft/s → mph

                        # Sanity check: speed must be positive and reasonable
                        if optimal_speed <= 0 or optimal_speed > 100:
                            optimal_speed = 30
                            logger = get_logger()
                            logger.warn(
                                "TRAIN",
                                f"Train {train_id} calculated speed out of range, using default 30 mph",
                                {
                                    "train_id": train_id,
                                    "calculated_speed": optimal_speed,
                                    "time_available": time_available,
                                    "distance_yards": total_distance_yards,
                                },
                            )
                    else:
                        # Not enough time - impossible schedule
                        optimal_speed = 30
                        logger = get_logger()
                        logger.warn(
                            "TRAIN",
                            f"Train {train_id} impossible schedule: not enough time",
                            {
                                "train_id": train_id,
                                "time_available": time_available,
                                "distance_yards": total_distance_yards,
                                "arrival_time": arrival_time_str,
                            },
                        )
                else:
                    optimal_speed = 30

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

        # Debug print: Route path for each station leg in the route
        prev_block = current_block
        for idx, station_block in enumerate(route):
            leg_path = self._calculate_complete_block_path(
                prev_block, station_block, line
            )
            print(
                f"[DEBUG] [ROUTE_PATH] Leg {idx+1}: {prev_block} → {station_block} for Train {train_id} (Line: {line}): {leg_path}"
            )
            prev_block = station_block

        # Sum up block lengths along the path (in meters, convert to yards)
        authority_meters = 0.0
        static_data = self._read_static_data()

        if static_data and complete_path:
            # Block 0 (yard) is not technically a block - fixed at 200 yards
            authority = 200.0  # Yard distance

            line_data = static_data.get("static_data", {}).get(line, [])
            for block_num in complete_path[1:-1]:  # Exclude last block (destination)
                # Find this block in static data
                for block_info in line_data:
                    if int(block_info.get("Block Number", -1)) == block_num:
                        block_length_m = float(block_info.get("Block Length (m)", 0))
                        authority_meters += block_length_m
                        break

            # Convert meters to yards and add to yard distance
            authority += authority_meters * 1.09361 + 10  # Extra 10 yards buffer
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
        num_stops = len(route) - 1  # Exclude starting point
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

        # Calculate and store expected path for this leg
        complete_path = self._calculate_complete_block_path(
            current_block, next_station_block, line
        )
        train_info["expected_path"] = complete_path

        logger.info(
            "DISPATCH",
            f"Train {train_id} expected path: {complete_path[0]}→{complete_path[-1]} ({len(complete_path)} blocks)",
            {
                "train_id": train_id,
                "path_start": complete_path[0],
                "path_end": complete_path[-1],
                "path_length": len(complete_path),
                "first_10_blocks": complete_path[:10],
            },
        )

        # Switch setting now handled dynamically in _set_switches_for_approaching_trains()
        # (called from PLC cycle, not from dispatch)

    def _set_switches_for_approaching_trains(self, track_data, line, line_prefix):
        """
        Dynamically set switches based on trains approaching them.
        Only sets switch if train is within 5 blocks of the switch.
        Priority given to closest train.
        """
        logger = get_logger()
        config = self.infrastructure[line]
        switch_blocks = config["switch_blocks"]
        switch_routes = config["switch_routes"]
        switches = track_data.get(f"{line_prefix}-switches", [])
        # Get all trains on this line
        line_trains = {
            tid: info
            for tid, info in self.active_trains.items()
            if info.get("line") == line
        }
        # For each switch, find closest approaching train
        for idx, switch_block in enumerate(switch_blocks):
            if idx >= len(switches):
                continue

            # SPECIAL CASE: Switch 63 (yard exit) for Green Line
            if line == "Green" and switch_block == 63:
                for train_id, train_info in line_trains.items():
                    current_block = train_info.get("current_block", 0)
                    expected_path = train_info.get("expected_path", [])
                    if current_block == 0 and expected_path and 63 in expected_path:
                        if switches[idx] != 1:
                            old_pos = switches[idx]
                            switches[idx] = 1
                            logger.info(
                                "SWITCH",
                                f"Green line block 63 switch: pos {old_pos} → 1 (Yard exit for Train {train_id})",
                                {
                                    "line": line,
                                    "block": switch_block,
                                    "train_id": train_id,
                                },
                            )
                        break
                continue  # Skip normal processing for switch 63

            closest_train = None
            min_distance = float("inf")
            desired_position = 0  # Default
            for train_id, train_info in line_trains.items():
                current_block = train_info.get("current_block", 0)
                expected_path = train_info.get("expected_path", [])
                if not expected_path or switch_block not in expected_path:
                    continue  # Switch not on this train's path
                try:
                    current_idx = (
                        expected_path.index(current_block)
                        if current_block in expected_path
                        else -1
                    )
                    switch_idx = expected_path.index(switch_block)
                except ValueError:
                    continue
                # Calculate distance along path
                if current_idx >= 0 and switch_idx > current_idx:
                    path_distance = switch_idx - current_idx
                    if path_distance <= 5 and path_distance < min_distance:
                        min_distance = path_distance
                        closest_train = train_id
                        # Determine desired position for this train
                        if line == "Green":
                            desired_position = self._determine_green_switch_position(
                                switch_block,
                                train_info.get("route", []),
                                current_block,
                                train_info.get("destination"),
                            )
                        else:  # Red line
                            desired_position = self._determine_red_switch_position(
                                switch_block,
                                train_info.get("route", []),
                                current_block,
                                train_info.get("destination"),
                            )
            # Set switch for closest approaching train
            if closest_train is not None and switches[idx] != desired_position:
                old_pos = switches[idx]
                switches[idx] = desired_position
                logger.info(
                    "SWITCH",
                    f"{line} line block {switch_block} switch: pos {old_pos} → {desired_position} (for Train {closest_train}, {min_distance} blocks away)",
                    {
                        "line": line,
                        "block": switch_block,
                        "old_position": old_pos,
                        "new_position": desired_position,
                        "train_id": closest_train,
                        "distance": min_distance,
                        "route_description": switch_routes[switch_block][
                            desired_position
                        ],
                    },
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
            # Log arrival at destination block
            logger = get_logger()
            logger.info(
                "ARRIVAL",
                f"Train {train_id} arrived at destination block {next_station_block}",
                {
                    "train_id": train_id,
                    "block": next_station_block,
                    "station": train_info.get("current_station", "Unknown"),
                    "destination": train_info.get("destination", "Unknown"),
                },
            )

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

            # Debug print: Route path for this leg after dwell
            print(
                f"[DEBUG] [ROUTE_PATH] Leg {current_leg_index+1}: {current_block} → {next_station_block} for Train {train_id} (Line: {line}): {complete_path}"
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

            # 1. Switch Control - DYNAMIC (proximity-based)
            self._set_switches_for_approaching_trains(track_data, line, line_prefix)

            # 2. Traffic Light Control
            self._control_traffic_lights(track_data, line, line_prefix, occupancy)

            # 3. Crossing Gate Control
            self._control_crossing_gates(track_data, line, line_prefix, occupancy)

            # 4. Failure Handling
            self._handle_failures_for_line(track_data, line, line_prefix, failures)

    def _determine_green_switch_position(
        self, switch_block, route, current_block, destination
    ):
        """Determine Green Line switch position based on route"""
        # Green Line switches and their routing logic:
        # 13: 0="13->12" (main), 1:="1->13" (yard entry)
        # 28: 0="28->29" (main), 1:="150->28" (loop back)
        # 57: 0="57->58" (main), 1:="57->Yard" (to yard)
        # 63: 0="63->64" (main), 1:="Yard->63" (from yard)
        # 77: 0="76->77" (main), 1:="77->101" (shortcut)
        # 85: 0="85->86" (main), 1:="100->85" (from shortcut)

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
            # Position 0: going to Poplar (88) or Castle Shannon (96)
            # Position 1: going to main loop (105+) or anything else
            if destination in ["Poplar", "Castle Shannon"]:
                return 0  # Dead-end spur
            else:
                return 1  # Main loop

        elif switch_block == 85:
            # Position 0: going to Poplar (86→88)
            # Position 1: coming from Castle Shannon (100→85)
            if current_block == 100 or current_block >= 96:
                return 1  # Coming from dead end, loop back
            return 0

        return 0  # Default to main line

    def _determine_red_switch_position(
        self, switch_block, route, current_block, destination
    ):
        """Determine Red Line switch position based on route"""
        # Red Line switches and their routing logic:
        # 9: 0="0->9" (from yard), 1:="9->0" (to yard)
        # 16: 0="15->16" (main), 1:="1->16" (from yard)
        # 27: 0="27->28" (main), 1:="27->76" (loop)
        # 33: 0="32->33" (main), 1:="33->72" (shortcut)
        # 38: 0="38->39" (main), 1:="38->71" (shortcut)
        # 44: 0="43->44" (main), 1:="44->67" (shortcut)
        # 52: 0="52->53" (main), 1:="52->66" (shortcut)

        if switch_block == 9:
            # Use pos 1 if going to yard
            if destination == "Yard" or (route and route[-1] == 0):
                return 1

        elif switch_block == 16:
            # Use pos 1 if coming from yard (blocks 1-15)

            if current_block < 16 and route and route[0] <= 16:
                return 1

        elif switch_block == 27:
            # Use pos 1 if route includes blocks  76+ (loop)
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
        """Handle failures: check 3 blocks ahead and stop if detected"""
        logger = get_logger()

        for train_id, train_info in list(self.active_trains.items()):
            if train_info.get("line") != line:
                continue

            current_block = train_info.get("current_block", 0)
            expected_path = train_info.get("expected_path", [])

            if not expected_path or current_block not in expected_path:
                continue  # Can't check ahead without path

            # Find current position in path
            try:
                current_idx = expected_path.index(current_block)
            except ValueError:
                continue

            # Check next 3 blocks in path
            blocks_to_check = expected_path[current_idx + 1 : current_idx + 4]

            failure_detected = False
            failure_info = None

            for i, block in enumerate(blocks_to_check):
                if block < len(failures) and failures[block] != 0:
                    failure_detected = True
                    failure_names = {
                        1: "Broken Rail",
                        2: "Power Failure",
                        3: "Circuit Failure",
                    }
                    failure_info = {
                        "block": block,
                        "type": failures[block],
                        "type_name": failure_names.get(failures[block], "Unknown"),
                        "distance": i + 1,  # Blocks ahead
                    }
                    break

            # Handle failure state
            if failure_detected:
                # Stop the train if not already stopped
                if not train_info.get("failure_stopped", False):
                    old_speed = train_info.get("commanded_speed", 0)
                    old_authority = train_info.get("commanded_authority", 0)

                    train_info["commanded_speed"] = 0
                    train_info["commanded_authority"] = 0
                    train_info["failure_stopped"] = True
                    train_info["failure_info"] = failure_info  # Store for logging

                    if old_speed > 0 or old_authority > 0:
                        logger.warn(
                            "FAILURE",
                            f"Train {train_id} STOPPED: {failure_info['type_name']} detected {failure_info['distance']} blocks ahead at block {failure_info['block']}",
                            {
                                "train_id": train_id,
                                "line": line,
                                "current_block": current_block,
                                "failure_block": failure_info["block"],
                                "failure_type": failure_info["type_name"],
                                "distance_blocks_ahead": failure_info["distance"],
                            },
                        )
            else:
                # No failure ahead - resume if previously stopped
                if train_info.get("failure_stopped", False):
                    train_info["failure_stopped"] = False

                    # Restore to appropriate state
                    if train_info.get("state") == "En Route":
                        # Restore scheduled speed and recalculate authority
                        scheduled_speed = train_info.get("scheduled_speed", 30)
                        train_info["commanded_speed"] = scheduled_speed
                        # Authority will be recalculated in next state machine cycle

                        logger.info(
                            "FAILURE",
                            f"Train {train_id} RESUMING: failure cleared",
                            {
                                "train_id": train_id,
                                "line": line,
                                "current_block": current_block,
                                "resumed_speed": scheduled_speed,
                            },
                        )

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
        Uses the existing station route logic and fills in blocks between stations.
        """
        # Get the station route (we already have the logic for this!)
        # First, find which stations these blocks belong to
        config = self.infrastructure[line]
        stations = config["stations"]

        # Find destination station for end_block
        destination_station = None
        for station_name, station_blocks in stations.items():
            if isinstance(station_blocks, list):
                if end_block in station_blocks:
                    destination_station = station_name
                    break
            else:
                if end_block == station_blocks:
                    destination_station = station_name
                    break

        if not destination_station:
            # Fallback: direct path
            return list(range(start_block, end_block + 1))

        # Get station route using our existing logic
        station_route = self._get_stations_on_path_to_destination(
            line, destination_station, list(stations.keys()), stations
        )

        if not station_route:
            return [start_block, end_block]

        # Now fill in ALL blocks between each station in the route
        complete_path = []

        if line == "Red":
            # Red Line: simple sequential
            if start_block == 0:
                complete_path = [0]
                for i in range(len(station_route) - 1):
                    start_station_block = 9 if i == 0 else station_route[i]
                    end_station_block = station_route[i + 1]
                    complete_path.extend(
                        range(start_station_block, end_station_block + 1)
                    )
            else:
                complete_path = list(range(start_block, end_block + 1))
            return complete_path

        elif line == "Green":
            # Green Line: use station route to determine path
            if start_block == 0:
                complete_path = [0]

                # Add blocks from yard exit (63) to first station
                complete_path.extend(range(63, station_route[0] + 1))

                # Fill in blocks between consecutive stations
                for i in range(len(station_route) - 1):
                    current_station = station_route[i]
                    next_station = station_route[i + 1]

                    # Determine how to connect these stations
                    path_segment = self._fill_blocks_between_stations(
                        current_station, next_station
                    )
                    # Skip first block (already in path)
                    complete_path.extend(path_segment[1:])

                return complete_path

            else:
                # Station-to-station: similar logic
                return self._calculate_green_line_station_to_station_path(
                    start_block, end_block
                )

        return [start_block, end_block]

    def _fill_blocks_between_stations(self, start_block, end_block):
        """
        Fill in all blocks between two blocks on Green Line.
        Handles switches and special topology.
        Works for both station blocks and arbitrary blocks.
        """
        from logger import get_logger

        logger = get_logger()

        logger.debug(
            "PATH",
            f"Calculating path from {start_block} to {end_block}",
            {"start": start_block, "end": end_block},
        )

        # 77 → 101+ (main loop via switch)
        if start_block == 77 and end_block >= 101:
            return [77, 101] + list(range(102, end_block + 1))

        # 77 → 78-100 (Poplar/Castle Shannon spur)
        if start_block == 77 and 78 <= end_block <= 100:
            return list(range(77, end_block + 1))

        # Both on Poplar/Castle Shannon spur (78-100) - SAME SPUR
        if 78 <= start_block <= 100 and 78 <= end_block <= 100:
            return list(range(start_block, end_block + 1))

        # From Poplar/Castle Shannon spur to main loop
        if 78 <= start_block <= 100 and end_block >= 101:
            path = list(range(start_block, 101))
            path.extend(range(100, 76, -1))
            path.extend([101] + list(range(102, end_block + 1)))
            return path

        # From Poplar/Castle Shannon spur to return path
        if 78 <= start_block <= 100 and end_block <= 62:
            path = list(range(start_block, 101))
            path.extend(range(100, 76, -1))
            path.extend([101] + list(range(102, 151)))
            if end_block >= 28:
                path.extend([28] + list(range(29, end_block + 1)))
            else:
                path.extend([28] + list(range(29, 63)) + list(range(1, end_block + 1)))
            return path

        # From main loop (101-150) to first section (63-77) - FULL LOOP, NO YARD
        if 101 <= start_block <= 150 and 63 <= end_block <= 77:
            path = list(range(start_block, 151))  # To 150
            path.extend([28])  # Switch at 150→28
            path.extend(range(29, 63))  # Down to 62
            path.extend(range(63, end_block + 1))  # 63→destination
            logger.info(
                "PATH",
                f"Main loop to first section: {start_block}→{end_block} via 150→28→63",
                {"path_length": len(path), "path": path},
            )
            return path

        # From main loop (101-150) to return path (28-62)
        if 101 <= start_block <= 150 and 28 <= end_block <= 62:
            path = list(range(start_block, 151))
            path.extend([28] + list(range(29, end_block + 1)))
            return path

        # From main loop to wrap section (1-27)
        if 101 <= start_block <= 150 and 1 <= end_block <= 27:
            path = list(range(start_block, 151))
            path.extend([28] + list(range(29, 63)) + list(range(1, end_block + 1)))
            return path

        # 150 → 28 (crossing switch 28)
        if start_block == 150 and end_block <= 62:
            if end_block >= 28:
                return [150, 28] + list(range(29, end_block + 1))
            else:
                return [150, 28] + list(range(29, 63)) + list(range(1, end_block + 1))

        # From return path to main sections (requires going through 63, not Yard!)
        if 1 <= start_block <= 62 and end_block >= 63:
            # Go sequential to 63, then continue
            path = list(range(start_block, 64))  # Up to 63
            path.extend(range(64, end_block + 1))  # Continue to destination
            return path

        # 9-13 → 1-2 (via switch at 13→1)
        if 9 <= start_block <= 13 and end_block <= 2:
            return list(range(start_block, 14)) + ([1, 2] if end_block == 2 else [1])

        # Both in same sequential section - blocks 63-77
        if 63 <= start_block <= 77 and 63 <= end_block <= 77:
            return list(range(start_block, end_block + 1))

        # Both in main loop (101-150)
        if 101 <= start_block <= 150 and 101 <= end_block <= 150:
            return list(range(start_block, end_block + 1))

        # Both in return path (28-62)
        if 28 <= start_block <= 62 and 28 <= end_block <= 62:
            if start_block < end_block:
                return list(range(start_block, end_block + 1))
            else:
                return list(range(start_block, end_block - 1, -1))

        # Both in wrap section (1-27)
        if 1 <= start_block <= 27 and 1 <= end_block <= 27:
            if start_block < end_block:
                return list(range(start_block, end_block + 1))
            else:
                return list(range(start_block, end_block - 1, -1))

        # If we reach here, path is not handled - THROW EXCEPTION
        logger.error(
            "PATH",
            f"UNHANDLED PATH: {start_block} → {end_block}",
            {"start": start_block, "end": end_block},
        )
        raise ValueError(
            f"Cannot calculate path from {start_block} to {end_block} on Green Line - unhandled case!"
        )

    def _calculate_green_line_station_to_station_path(self, start_block, end_block):
        """Calculate path between two blocks on Green Line using track topology.
        Handles all transitions using _fill_blocks_between_stations.
        """
        return self._fill_blocks_between_stations(start_block, end_block)

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
                    # 77: 0=to Poplar/Castle Shannon (78), 1=to main loop (101)
                    elif switch_block == 77:
                        switch_position = 0 if next_block == 78 else 1
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

                # Debug print: Switch assignment for each relevant switch
                print(
                    f"[DEBUG] [SWITCH_ASSIGN] Train: {train_id}, Line: {line}, Switch Block: {switch_block}, Position: {switch_position}, Prev Block: {prev_block}, Next Block: {next_block}, Path: {complete_path}"
                )

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
