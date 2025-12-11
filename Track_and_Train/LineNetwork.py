"""
Line Network - Defines train paths and topology for Red and Green lines
Knows how trains move through the network and provides visualization info
"""

import pandas as pd
import re
from typing import List, Dict, Tuple, Optional, Set
from dataclasses import dataclass
import json
import random
import os
import sys
from logger import get_logger

# Correct fixed paths for Track and Train JSONs
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))  # Track_and_Train
TRACK_MODEL_DIR = os.path.join(PROJECT_ROOT, "Track_Model")
TRAIN_MODEL_DIR = os.path.join(PROJECT_ROOT, "Train_Model")

# Add Track_Model to path for imports
sys.path.insert(0, TRACK_MODEL_DIR)

from DynamicBlockManager import DynamicBlockManager

# JSON paths
TRACK_STATIC_JSON = os.path.join(TRACK_MODEL_DIR, "track_model_static.json")
TRACK_CONTROLLER_JSON = os.path.join(PROJECT_ROOT, "track_io.json")
TRAIN_MODEL_JSON = os.path.join(PROJECT_ROOT, "track_model_Train_Model.json")


def parse_branching_connections(value: str) -> List[Tuple[int, int]]:
    """Parse SWITCH (A-B; C-D) format into connection pairs. Yard is represented as block 0."""
    text = str(value).upper().strip()
    if "SWITCH" not in text:
        return []

    m = re.search(r"\(([^)]+)\)", text)
    if not m:
        return []

    inside = m.group(1)
    connections = []

    parts = re.split(r"[;,]", inside)
    for part in parts:
        part = part.strip()
        # Handle "X-yard" format - yard is block 0
        yard_match = re.search(r"(\d+)\s*-\s*yard", part, re.IGNORECASE)
        if yard_match:
            block_num = int(yard_match.group(1))
            connections.append((block_num, 0))
            continue

        conn_match = re.search(r"(\d+)\s*-\s*(\d+)", part)
        if conn_match:
            from_block = int(conn_match.group(1))
            to_block = int(conn_match.group(2))
            connections.append((from_block, to_block))

    return connections


UNIDIRECTIONAL_BLOCKS = {
    "Green": [
        (30, 57),
        (63, 77),
        (101, 150),
        0,
    ],
    "Red": [
        (52, 66),
    ],
}


@dataclass
class Path:
    """Represents a train path through the network."""

    name: str
    blocks: List[int]

    def __repr__(self):
        return f"Path({self.name}: {len(self.blocks)} blocks)"


@dataclass
class BranchPoint:
    """A point where track splits."""

    block: int
    targets: List[int]

    def __repr__(self):
        return f"BranchPoint(block={self.block}, targets={self.targets})"


class LineNetwork:
    """Network for a specific line (Red or Green)."""

    def __init__(self, line_name: str, block_manager=None):
        self.logger = get_logger()
        self.line_name = line_name.replace(" Line", "")
        self.connections: Dict[int, List[int]] = {}  # block -> list of connected blocks
        self.branch_points: Dict[int, BranchPoint] = {}
        self.block_manager = block_manager
        self.additional_connections: List[Tuple[int, int]] = (
            []
        )  # non-sequential to draw
        self.skip_connections: List[Tuple[int, int]] = []  # exceptions not to draw
        self.all_blocks = []
        self.crossing_blocks = []
        self.red_line_trains = []
        self.green_line_trains = []
        self.total_ticket_sales = 0  # Cumulative ticket sales
        self.previous_train_motions = {}  # Track motion changes: {train_id: motion}
        self.train_current_stations = {}
        self.train_positions = {}
        self.previous_position_yds = (
            {}
        )  # Track previous position: {train_id: position_yds}
        self.yards_into_current_block = (
            {}
        )  # Track yards traveled in current block: {train_id: yards}

        self.read_train_data_from_json()

    def get_red_line_visualizer_info(
        self,
    ) -> Tuple[List[Tuple[int, int]], List[Tuple[int, int]]]:
        """Return (additional_connections, skip_connections) for red line."""
        return (self.additional_connections, self.skip_connections)

    def get_green_line_visualizer_info(
        self,
    ) -> Tuple[List[Tuple[int, int]], List[Tuple[int, int]]]:
        """Return (additional_connections, skip_connections) for green line."""
        return (self.additional_connections, self.skip_connections)

    def __repr__(self):
        return f"LineNetwork({self.line_name}: {len(self.connections)} blocks)"

    def read_train_data_from_json(self, json_path=TRACK_CONTROLLER_JSON):
        """Read train control data from JSON file."""
        try:
            with open(json_path, "r") as f:
                data = json.load(f)

            # Determine prefix based on line
            prefix = self.line_name[0]  # "G" for Green, "R" for Red

            # Parse arrays from JSON
            switches = data.get(f"{prefix}-switches", [])
            gates = data.get(f"{prefix}-gates", [])
            lights = data.get(f"{prefix}-lights", [])

            # Get commanded speeds and authorities from G-Train or R-Train
            train_data = data.get(f"{prefix}-Train", {})
            commanded_speeds = train_data.get("commanded speed", [])
            commanded_authorities = train_data.get("commanded authority", [])

            # Create data dict with only switches, gates, lights
            data_dict = {
                "switches": switches,
                "gates": gates,
                "lights": lights,
            }

            # Write parsed data to block manager
            self.write_to_block_manager(data_dict)

            # Write to Train Model JSON
            self.write_to_train_model_json(commanded_speeds, commanded_authorities)

        except Exception as e:
            self.logger.error("NETWORK", f"Error updating train model data: {e}")

    def write_to_train_model_json(self, commanded_speeds, commanded_authorities):
        import json
        import os
        import time

        json_path = TRAIN_MODEL_JSON
        logger = get_logger()
        max_retries = 3
        retry_delay = 0.05  # 50ms

        for attempt in range(max_retries):
            try:
                # Read with retry on corruption
                try:
                    with open(json_path, "r") as f:
                        train_model_data = json.load(f)
                except json.JSONDecodeError as e:
                    if attempt < max_retries - 1:
                        logger.warning(
                            "NETWORK",
                            f"JSON decode error on attempt {attempt + 1}, retrying: {e}",
                            {"attempt": attempt + 1, "error": str(e)},
                        )
                        time.sleep(retry_delay)
                        continue
                    else:
                        logger.error(
                            "NETWORK",
                            f"Failed to read JSON after {max_retries} attempts: {e}",
                            {"error": str(e)},
                        )
                        return

                # Process data (your existing logic)
                trains = []
                for i in range(len(commanded_speeds)):
                    train_key = f"{self.line_name[0]}_train_{i + 1}"
                    if train_key in train_model_data:
                        motion = train_model_data[train_key]["motion"]["current motion"]
                        pos = train_model_data[train_key]["motion"].get(
                            "position_yds", 0
                        )
                        trains.append({"train_id": i + 1, "motion": motion})

                        old_pos = self.train_positions.get(i + 1, 0)
                        self.train_positions[i + 1] = pos

                        train_model_data[train_key]["block"]["commanded speed"] = (
                            commanded_speeds[i]
                        )
                        train_model_data[train_key]["block"]["commanded authority"] = (
                            commanded_authorities[i]
                        )

                        if not hasattr(self, "yards_into_current_block"):
                            self.yards_into_current_block = {}
                        yards_in_block = self.yards_into_current_block.get(i + 1, 0)
                        train_model_data[train_key]["motion"][
                            "yards_into_current_block"
                        ] = yards_in_block

                        logger.info(
                            "TRAIN",
                            f"Train {i + 1} commands written to JSON: speed={commanded_speeds[i]:.2f} mph, authority={commanded_authorities[i]:.2f} yds",
                            {
                                "train_id": i + 1,
                                "line": self.line_name,
                                "commanded_speed": commanded_speeds[i],
                                "commanded_authority": commanded_authorities[i],
                                "train_key": train_key,
                            },
                        )

                # Update block manager
                if self.block_manager:
                    existing_train_ids = {
                        train["train_id"]: idx
                        for idx, train in enumerate(self.block_manager.trains)
                    }

                    for t in trains:
                        train_id = t["train_id"]
                        if train_id in existing_train_ids:
                            idx = existing_train_ids[train_id]
                            self.block_manager.trains[idx]["start"] = (
                                True if t["motion"].lower() == "moving" else False
                            )
                        else:
                            self.block_manager.trains.append(
                                {
                                    "train_id": train_id,
                                    "line": self.line_name,
                                    "start": (
                                        True
                                        if t["motion"].lower() == "moving"
                                        else False
                                    ),
                                }
                            )

                if self.line_name == "Green":
                    self.green_line_trains = trains
                else:
                    self.red_line_trains = trains

                # Write with atomic operation
                temp_path = json_path + ".tmp"
                with open(temp_path, "w") as f:
                    json.dump(train_model_data, f, indent=4)
                os.replace(temp_path, json_path)
                break  # Success

            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning(
                        "NETWORK",
                        f"Error on attempt {attempt + 1}, retrying: {e}",
                        {"attempt": attempt + 1, "error": str(e)},
                    )
                    time.sleep(retry_delay)
                else:
                    logger.error(
                        "NETWORK",
                        f"Error updating train model data after {max_retries} attempts: {e}",
                        {"error": str(e)},
                    )

    def write_to_block_manager(self, data: dict):
        """Parse raw JSON data and write to block manager."""
        if not self.block_manager:
            return

        # Load crossing blocks from static JSON
        self.load_crossing_blocks_from_static()

        # Load branch points from static JSON
        self.load_branch_points_from_static()

        self.load_all_blocks_from_static()

        # Extract raw arrays
        switches = data["switches"]
        gates = data["gates"]
        lights = data["lights"]

        # Parse switches using existing method
        switch_positions = self.process_switch_positions(switches)

        # Parse gates: map crossing_blocks to gate array
        gate_statuses = {}
        for i, block_num in enumerate(self.crossing_blocks):
            if i < len(gates):
                gate_statuses[block_num] = "Open" if gates[i] == 0 else "Closed"
        # Parse traffic lights for ALL blocks using existing method
        parsed_lights = []
        for block_num in self.all_blocks:
            light_status = self.parse_traffic_lights(block_num, lights)
            # Convert to int: Super Green=0, Green=1, Yellow=2, Red=3, N/A=-1
            if light_status == "Super Green":
                parsed_lights.append(0)
            elif light_status == "Green":
                parsed_lights.append(1)
            elif light_status == "Yellow":
                parsed_lights.append(2)
            elif light_status == "Red":
                parsed_lights.append(3)
            else:  # N/A for blocks without traffic lights
                parsed_lights.append(-1)

        # Write to block manager
        self.block_manager.write_inputs(
            self.line_name,
            switch_positions,
            gate_statuses,
            parsed_lights,
        )

    def process_switch_positions(self, switches: List[int]) -> Dict[int, int]:
        switch_positions = {}

        if self.line_name == "Green":
            # Green Line has 6 switches at blocks: 13, 28, 57, 63, 77, 86
            green_switch_blocks = [13, 28, 57, 63, 77, 86]

            for i, block_num in enumerate(green_switch_blocks):
                if i < len(switches) and block_num in self.branch_points:
                    switch_setting = switches[i]
                    targets = self.branch_points[block_num].targets
                    if 0 <= switch_setting < len(targets):
                        switch_positions[block_num] = targets[switch_setting]

        elif self.line_name == "Red":
            # Red Line has 7 switches at blocks: 9, 16, 27, 33, 38, 44, 52
            red_switch_blocks = [9, 16, 27, 33, 38, 44, 52]

            for i, block_num in enumerate(red_switch_blocks):
                if i < len(switches) and block_num in self.branch_points:
                    switch_setting = switches[i]
                    targets = self.branch_points[block_num].targets
                    if 0 <= switch_setting < len(targets):
                        switch_positions[block_num] = targets[switch_setting]

        return switch_positions

    def parse_traffic_lights(self, current_block: int, lights_array: List[int]) -> str:
        """
        Parse traffic light status for current block.
        Returns: "Super Green", "Green", "Yellow", "Red", or "N/A" (for blocks without traffic lights)
        """
        # Hard-coded blocks with traffic lights
        if self.line_name == "Green":
            traffic_light_blocks = [0, 3, 7, 29, 58, 62, 76, 86, 100, 101, 150, 151]
        elif self.line_name == "Red":
            traffic_light_blocks = [0, 8, 14, 26, 31, 37, 42, 51]
        else:
            traffic_light_blocks = []

        # If current block doesn't have a traffic light, return N/A
        if current_block not in traffic_light_blocks:
            return "N/A"

        # Find which traffic light index this is (0-11)
        traffic_light_index = traffic_light_blocks.index(current_block)

        # Calculate bit position (2 bits per light)
        bit_index = traffic_light_index * 2

        # Read 2 bits
        if bit_index + 1 < len(lights_array):
            bit1 = lights_array[bit_index]
            bit2 = lights_array[bit_index + 1]

            # Decode: 00=Super Green, 01=Green, 10=Yellow, 11=Red
            if bit1 == 0 and bit2 == 0:
                return "Super Green"
            elif bit1 == 0 and bit2 == 1:
                return "Green"
            elif bit1 == 1 and bit2 == 0:
                return "Yellow"
            elif bit1 == 1 and bit2 == 1:
                return "Red"

        # Default to N/A if parsing fails
        return "N/A"

    def _read_train_motion(self, train_id):
        """Read the current motion status of a train from track_model_Train_Model.json"""
        try:
            with open(TRAIN_MODEL_JSON, "r") as f:
                train_model_data = json.load(f)

            train_key = f"{self.line_name[0]}_train_{train_id}"
            if train_key in train_model_data:
                motion = train_model_data[train_key]["motion"].get(
                    "current motion", "stopped"
                )
                return motion.capitalize()  # Convert to "Stopped", "Moving", etc.
            return "Stopped"
        except Exception as e:
            return "Stopped"

    def get_next_block(self, train_id, current, previous=None):
        logger = get_logger()

        if not self.should_advance_block(train_id, current):
            return current

        # Read motion and handle stopped/undispatched (stays here)
        motion = self._read_train_motion(train_id)
        logger.debug(
            "POSITION",
            f"Train {train_id} Block {current}: motion state = {motion}",
            {
                "train_id": train_id,
                "line": self.line_name,
                "current_block": current,
                "motion": motion,
            },
        )

        if motion == "Stopped":
            logger.debug(
                "POSITION",
                f"Train {train_id} Block {current}: train stopped, staying in current block",
                {
                    "train_id": train_id,
                    "line": self.line_name,
                    "current_block": current,
                },
            )
            return current
        elif motion == "Undispatched":
            logger.debug(
                "POSITION",
                f"Train {train_id}: undispatched, returning to yard (block 0)",
                {"train_id": train_id, "line": self.line_name},
            )
            return 0

        # Route based on line
        if self.line_name == "Green":
            next_block = self._get_green_line_next_block(current, previous)
        elif self.line_name == "Red":
            next_block = self._get_red_line_next_block(current, previous)

        logger.info(
            "POSITION",
            f"Train {train_id}: BLOCK TRANSITION {current} → {next_block}",
            {
                "train_id": train_id,
                "line": self.line_name,
                "from_block": current,
                "to_block": next_block,
                "previous_block": previous,
            },
        )

        self._handle_station_arrival(next_block)
        self._finalize_block_transition(next_block, current, train_id)

        return next_block

    def get_station_name(self, block_num: int) -> str:
        """Get station name for a given block number from static JSON."""
        try:
            json_path = TRACK_STATIC_JSON
            with open(json_path, "r") as f:
                static_data = json.load(f)

            blocks = static_data.get("static_data", {}).get(self.line_name, [])
            for block in blocks:
                if block.get("Block Number") == block_num:
                    return block.get("Station", "N/A")
        except Exception as e:
            self.logger.error(
                "TRACK", f"Error finding station for block {block_num}: {e}"
            )

        return "N/A"

    def find_next_station(self, current_block, previous_block):
        """Search for next station based on direction of travel."""
        try:
            json_path = TRACK_STATIC_JSON
            with open(json_path, "r") as f:
                static_data = json.load(f)

            blocks = static_data.get("static_data", {}).get(self.line_name, [])

            # Find current block index
            current_idx = None
            for i, block in enumerate(blocks):
                if block.get("Block Number") == current_block:
                    current_idx = i
                    break

            if current_idx is None:
                return "N/A", "N/A"

            # Determine direction
            if previous_block is not None and current_block > previous_block:
                # Moving forward (counting up)
                for i in range(current_idx + 1, len(blocks)):
                    station = blocks[i].get("Station", "N/A")
                    if station != "N/A":
                        side_door = blocks[i].get("Station Side", "N/A")
                        return station, side_door
            else:
                # Moving backward (counting down)
                for i in range(current_idx - 1, -1, -1):
                    station = blocks[i].get("Station", "N/A")
                    if station != "N/A":
                        side_door = blocks[i].get("Station Side", "N/A")
                        return station, side_door

            return "N/A", "N/A"

        except Exception as e:
            return "N/A", "N/A"

    def write_beacon_data_to_train_model(
        self, next_block: int, train_id: int, previous_block: int
    ):
        """Write beacon data to Train Model JSON for a specific train."""
        try:
            # Check for circuit failure on this block FIRST
            block_id = None
            if self.block_manager:
                # Find the block_id string for this block number
                for bid in self.block_manager.line_states.get(self.line_name, {}):
                    block_num_str = "".join(filter(str.isdigit, bid))
                    if block_num_str and int(block_num_str) == next_block:
                        block_id = bid
                        break

                # Check if circuit failure exists
                if block_id:
                    failures = self.block_manager.line_states[self.line_name][block_id][
                        "failures"
                    ]
                    if failures.get("circuit"):
                        # Circuit failure - write all N/A beacon
                        beacon = {
                            "speed limit": 0,
                            "side_door": "N/A",
                            "current station": "N/A",
                            "next station": "N/A",
                            "passengers_boarding": 0,
                        }

                        # Write to Train Model JSON
                        json_path = TRAIN_MODEL_JSON
                        with open(json_path, "r") as f:
                            train_model_data = json.load(f)

                        train_key = f"{self.line_name[0]}_train_{train_id}"
                        if train_key in train_model_data:
                            train_model_data[train_key]["beacon"] = beacon

                        with open(json_path, "w") as f:
                            json.dump(train_model_data, f, indent=4)

                        return  # Exit early - don't process normal beacon data

        except Exception as e:
            self.logger.error("BEACON", f"Error processing beacon data: {e}")
        try:
            # Read static track data
            json_path = TRACK_STATIC_JSON
            with open(json_path, "r") as f:
                static_data = json.load(f)

            blocks = static_data.get("static_data", {}).get(self.line_name, [])

            # Find next_block in the list
            block_data = None
            for i, block in enumerate(blocks):
                if block.get("Block Number") == next_block:
                    block_data = block
                    break

            if not block_data:
                return

            # Extract beacon data
            speed_limit = block_data.get("Speed Limit (Km/Hr)", 0)

            # Current station - only update if we're AT a station
            station_at_block = block_data.get("Station", "N/A")
            if station_at_block != "N/A":
                # We're at a station - update it
                self.train_current_stations[train_id] = station_at_block
                side_door = block_data.get("Station Side", "N/A")
            else:
                # Not at a station - keep previous value
                side_door = "N/A"

            # Get current station (either just set, or previous)
            current_station = self.train_current_stations.get(train_id, "N/A")

            # Get next station using helper
            next_station, next_side_door = self.find_next_station(
                next_block, previous_block
            )

            # If we're not at a station, use next station's side door
            if station_at_block == "N/A" and next_side_door != "N/A":
                side_door = next_side_door

            # Get passengers_boarding from block_manager
            passengers_boarding = 0
            if self.block_manager and station_at_block != "N/A":
                passengers_boarding = self.block_manager.passengers_boarding

            # Create beacon dict
            beacon = {
                "speed limit": speed_limit,
                "side_door": side_door,
                "current station": current_station,
                "next station": next_station,
                "passengers_boarding": passengers_boarding,
            }

            # Write to Train Model JSON
            json_path = TRAIN_MODEL_JSON
            with open(json_path, "r") as f:
                train_model_data = json.load(f)

            train_key = f"{self.line_name[0]}_train_{train_id}"
            if train_key in train_model_data:
                train_model_data[train_key]["beacon"] = beacon

            with open(json_path, "w") as f:
                json.dump(train_model_data, f, indent=4)

            logger = get_logger()
            logger.debug(
                "BEACON",
                f"Train {train_id} beacon updated at block {next_block}",
                {
                    "train_id": train_id,
                    "line": self.line_name,
                    "block": next_block,
                    "current_station": current_station,
                    "next_station": next_station,
                    "speed_limit": speed_limit,
                    "passengers_boarding": passengers_boarding,
                },
            )

        except Exception as e:
            self.logger.error("TRACK", f"Error writing to track control: {e}")

    def update_block_occupancy(
        self, current_block: int, previous_block: Optional[int] = None
    ):
        """Update occupancy in block manager when train moves."""
        if not self.block_manager:
            return
        # Clear all blocks first
        for block_id in self.block_manager.line_states.get(self.line_name, {}):
            self.block_manager.line_states[self.line_name][block_id][
                "occupancy"
            ] = False

        # Set current block as occupied
        for block_id in self.block_manager.line_states.get(self.line_name, {}):
            try:
                block_num_str = "".join(filter(str.isdigit, block_id))
                if block_num_str and int(block_num_str) == current_block:
                    self.block_manager.line_states[self.line_name][block_id][
                        "occupancy"
                    ] = True
                    break
            except (ValueError, AttributeError):
                continue

    def write_occupancy_to_json(self, json_path=TRACK_CONTROLLER_JSON):
        if not self.block_manager:
            return

        try:
            with open(json_path, "r") as f:
                data = json.load(f)

            prefix = self.line_name[0]

            occupancy_array = []
            blocks = sorted(
                self.block_manager.line_states.get(self.line_name, {}).keys()
            )

            for block_id in blocks:
                occupancy = self.block_manager.line_states[self.line_name][block_id][
                    "occupancy"
                ]
                occupancy_array.append(1 if occupancy else 0)

            data[f"{prefix}-Occupancy"] = occupancy_array

            with open(json_path, "w") as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            logger = get_logger()
            logger.error("ERROR", f"Exception: {str(e)}", {"error": str(e)})

    def write_failures_to_json(self, json_path=TRACK_CONTROLLER_JSON):
        """Write failure data back to Track Controller JSON."""
        if not self.block_manager:
            return

        try:
            with open(json_path, "r") as f:
                data = json.load(f)

            prefix = self.line_name[0]

            failures_array = []
            blocks = sorted(
                self.block_manager.line_states.get(self.line_name, {}).keys()
            )

            for block_id in blocks:
                failures = self.block_manager.line_states[self.line_name][block_id][
                    "failures"
                ]
                failures_array.append(1 if failures["power"] else 0)
                failures_array.append(1 if failures["circuit"] else 0)
                failures_array.append(1 if failures["broken"] else 0)

            data[f"{prefix}-Failures"] = failures_array

            with open(json_path, "w") as f:
                json.dump(data, f, indent=4)

        except Exception as e:
            self.logger.error("TRACK", f"Error writing track IO data: {e}")

    def load_crossing_blocks_from_static(self):
        """Load crossing blocks from static JSON file."""
        try:
            json_path = TRACK_STATIC_JSON
            with open(json_path, "r") as f:
                static_data = json.load(f)

            blocks = static_data.get("static_data", {}).get(self.line_name, [])
            crossing_blocks = []

            for block in blocks:
                if block.get("Crossing") == "Yes":
                    block_num = block.get("Block Number")
                    if block_num not in ["N/A", "nan", None]:
                        try:
                            crossing_blocks.append(int(block_num))
                        except Exception as e:
                            self.logger.error(
                                "TRACK",
                                f"Error converting crossing block number {block_num}: {e}",
                            )

            self.crossing_blocks = sorted(crossing_blocks)
        except Exception as e:
            self.logger.error("TRACK", f"Error loading crossing blocks: {e}")

    def load_branch_points_from_static(self):
        """Load branch points from static JSON file."""
        try:
            json_path = TRACK_STATIC_JSON
            with open(json_path, "r") as f:
                static_data = json.load(f)

            blocks = static_data.get("static_data", {}).get(self.line_name, [])
            switch_data = {}

            logger = get_logger()
            logger.debug(
                "NETWORK",
                f"{self.line_name} Line loading branch points from static JSON",
                {"line": self.line_name, "total_blocks": len(blocks)},
            )

            for block in blocks:
                infra_text = str(block.get("Infrastructure", "")).upper()
                block_num = block.get("Block Number")

                if block_num not in ["N/A", "nan", None]:
                    block_num = int(block_num)
                    branch_conns = parse_branching_connections(infra_text)

                    if branch_conns:
                        from collections import Counter

                        all_blocks = []

                        for from_b, to_b in branch_conns:
                            all_blocks.append(from_b)
                            all_blocks.append(to_b)

                        block_counts = Counter(all_blocks)
                        branch_point = None

                        for blk, count in block_counts.items():
                            if count > 1:
                                branch_point = blk
                                break

                        if branch_point:
                            unique_blocks = sorted(list(set(all_blocks)))
                            targets = [b for b in unique_blocks if b != branch_point]
                            self.branch_points[branch_point] = BranchPoint(
                                block=branch_point, targets=targets
                            )
                            logger.debug(
                                "NETWORK",
                                f"{self.line_name} Line branch point loaded: block {branch_point} -> {targets}",
                                {
                                    "line": self.line_name,
                                    "block": branch_point,
                                    "targets": targets,
                                },
                            )

            # Hardcode switches that route to yard (block 0) and special 28 logic
            if self.line_name == "Green":
                if 57 not in self.branch_points:
                    self.branch_points[57] = BranchPoint(block=57, targets=[0, 58])
                if 63 not in self.branch_points:
                    self.branch_points[63] = BranchPoint(block=63, targets=[0, 64])
                # Special logic for 28: if coming from 150, branch (1) goes to 27
                if 28 in self.branch_points:
                    # Remove 29 from targets if present, add 27 for branch
                    targets = self.branch_points[28].targets
                    if 29 in targets:
                        targets.remove(29)
                    if 27 not in targets:
                        targets.append(27)
                    self.branch_points[28].targets = sorted(targets)
            elif self.line_name == "Red":
                if 9 not in self.branch_points:
                    self.branch_points[9] = BranchPoint(block=9, targets=[10, 0])

            logger.info(
                "NETWORK",
                f"{self.line_name} Line branch points loaded: {len(self.branch_points)} total",
                {
                    "line": self.line_name,
                    "branch_points": list(self.branch_points.keys()),
                },
            )
        except Exception as e:
            logger = get_logger()
            logger.warn(
                "NETWORK",
                f"{self.line_name} Line failed to load branch points: {str(e)}",
                {"line": self.line_name, "error": str(e)},
            )

    def load_all_blocks_from_static(self):
        """Load all blocks from static JSON file."""
        try:
            json_path = TRACK_STATIC_JSON
            with open(json_path, "r") as f:
                static_data = json.load(f)

            blocks = static_data.get("static_data", {}).get(self.line_name, [])
            all_blocks = []

            for block in blocks:
                block_num = block.get("Block Number")
                if block_num not in ["N/A", "nan", None]:
                    try:
                        all_blocks.append(int(block_num))
                    except Exception as e:
                        self.logger.error(
                            "TRACK", f"Error converting block number {block_num}: {e}"
                        )

            self.all_blocks = sorted(set(all_blocks))
        except Exception as e:
            self.logger.error("TRACK", f"Error loading all blocks: {e}")

    def should_advance_block(self, train_id: int, current_block: int) -> bool:
        """
        Determine if train has traveled enough yards to advance to next block.

        Args:
            train_id: Train identifier
            current_block: Current block number

        Returns:
            True if train should advance to next block, False otherwise
        """
        logger = get_logger()

        # Initialize train state if not exists
        if not hasattr(self, "previous_position_yds"):
            self.previous_position_yds = {}
        if not hasattr(self, "yards_into_current_block"):
            self.yards_into_current_block = {}

        # Initialize this train's state
        if train_id not in self.previous_position_yds:
            self.previous_position_yds[train_id] = 0
            logger.debug(
                "POSITION",
                f"Train {train_id} position tracking initialized",
                {"train_id": train_id, "line": self.line_name},
            )
        if train_id not in self.yards_into_current_block:
            self.yards_into_current_block[train_id] = 0

        # Read current position from train_positions (already populated by write_to_train_model_json)
        current_position_yds = self.train_positions.get(train_id, 0)

        # Detect backwards jump (position reset on new authority)
        if current_position_yds < self.previous_position_yds[train_id] - 50:
            # Position jumped backwards - sync previous to current to avoid negative delta
            logger.debug(
                "POSITION",
                f"Train {train_id} Block {current_block}: POSITION RESET DETECTED - syncing previous position",
                {
                    "train_id": train_id,
                    "line": self.line_name,
                    "current_block": current_block,
                    "old_previous_position": self.previous_position_yds[train_id],
                    "new_previous_position": current_position_yds,
                    "yards_in_block_preserved": self.yards_into_current_block[train_id],
                },
            )
            self.previous_position_yds[train_id] = current_position_yds

        # Calculate delta
        delta = current_position_yds - self.previous_position_yds[train_id]

        # Add delta to yards traveled in current block
        self.yards_into_current_block[train_id] += delta

        # Debug logging for position tracking (enable when debugging position issues)
        logger.debug(
            "POSITION",
            f"Train {train_id} Block {current_block}: pos={current_position_yds:.2f}yds, delta={delta:.2f}yds, block_traveled={self.yards_into_current_block[train_id]:.2f}yds",
            {
                "train_id": train_id,
                "line": self.line_name,
                "current_block": current_block,
                "position_yds": current_position_yds,
                "previous_position_yds": self.previous_position_yds[train_id],
                "delta_yds": delta,
                "yards_in_block": self.yards_into_current_block[train_id],
            },
        )

        # Get block length from static JSON
        try:
            with open(TRACK_STATIC_JSON, "r") as f:
                static_data = json.load(f)

            blocks = static_data.get("static_data", {}).get(self.line_name, [])
            block_length_yards = None

            # Special case: Block 0 (yard) is always 200 yards
            if current_block == 0:
                block_length_yards = 200.0
            else:
                for block in blocks:
                    if block.get("Block Number") == current_block:
                        length_m = block.get("Block Length (m)", 0)
                        if length_m not in ["N/A", "nan", None]:
                            # Convert meters to yards (1m = 1.09361 yards)
                            block_length_yards = float(length_m) * 1.09361
                        break

            if block_length_yards is None:
                # Cannot advance without block length data - error condition
                logger.error(
                    "POSITION",
                    f"Train {train_id} Block {current_block}: CRITICAL - block length data unavailable, cannot determine advancement",
                    {
                        "train_id": train_id,
                        "line": self.line_name,
                        "current_block": current_block,
                        "yards_in_block": self.yards_into_current_block[train_id],
                    },
                )
                self.previous_position_yds[train_id] = current_position_yds
                return False  # Stay in current block until data available

            # Check if enough yards traveled to advance
            if self.yards_into_current_block[train_id] >= block_length_yards:
                # Subtract block length and carry overflow
                self.yards_into_current_block[train_id] -= block_length_yards
                self.previous_position_yds[train_id] = current_position_yds

                logger.info(
                    "POSITION",
                    f"Train {train_id} Block {current_block}: ADVANCING to next block (traveled {self.yards_into_current_block[train_id] + block_length_yards:.2f}/{block_length_yards:.2f} yds)",
                    {
                        "train_id": train_id,
                        "line": self.line_name,
                        "current_block": current_block,
                        "block_length_yds": block_length_yards,
                        "yards_traveled": self.yards_into_current_block[train_id]
                        + block_length_yards,
                        "overflow_yds": self.yards_into_current_block[train_id],
                    },
                )
                return True
            else:
                # Not enough yards traveled, stay in current block
                self.previous_position_yds[train_id] = current_position_yds

                # Commented out - high-frequency position logging
                # logger.debug(
                #     "POSITION",
                #     f"Train {train_id} Block {current_block}: staying in block ({self.yards_into_current_block[train_id]:.2f}/{block_length_yards:.2f} yds)",
                #     {
                #         "train_id": train_id,
                #         "line": self.line_name,
                #         "current_block": current_block,
                #         "block_length_yds": block_length_yards,
                #         "yards_in_block": self.yards_into_current_block[train_id],
                #         "remaining_yds": block_length_yards
                #         - self.yards_into_current_block[train_id],
                #     },
                # )
                return False

        except Exception as e:
            logger = get_logger()
            logger.error(
                "ROUTING",
                f"Train {train_id} block advance check failed: {e}",
                {"train_id": train_id, "error": str(e)},
            )
            self.previous_position_yds[train_id] = current_position_yds
            return False  # Stay in current block on error - do not silently advance

    def _handle_station_arrival(self, next_block: int) -> None:
        """
        Check if next_block is a station and generate passengers boarding.

        Args:
            next_block: The block number train is moving to
        """
        # Check if next_block is a station and generate passengers boarding
        station_name = self.get_station_name(next_block)
        if station_name != "N/A":
            self.block_manager.passengers_boarding = random.randint(0, 200)
            self.block_manager.total_ticket_sales += (
                self.block_manager.passengers_boarding
            )

    def _finalize_block_transition(
        self, next_block: int, current: int, train_id: int
    ) -> None:
        self.update_block_occupancy(next_block, current)
        # Only send beacon at stations, not every block
        station_name = self.get_station_name(next_block)
        if station_name != "N/A":
            self.write_beacon_data_to_train_model(next_block, train_id, current)
        self.write_occupancy_to_json()
        self.write_failures_to_json()

    def _get_green_line_next_block(self, current: int, previous: Optional[int]) -> int:
        """
        Determine next block for Green Line based on current position and routing rules.

        Args:
            current: Current block number
            previous: Previous block number (or None)

        Returns:
            Next block number
        """
        logger = get_logger()
        logger.debug(
            "ROUTING",
            f"Green Line routing: current={current}, previous={previous}",
            {
                "line": self.line_name,
                "current_block": current,
                "previous_block": previous,
            },
        )

        # Green line switch routes - blocks can appear multiple times for different switch scenarios
        switch_routes = {
            13: {0: "13->12", 1: "13->14"},
            1: {
                0: "1->2",
                1: "1->13",
            },  # Block 1 check: if coming from 13, switch exists
            150: {1: "150->28"},  # Only one route
            57: {0: "57->58", 1: "57->0"},
            0: {1: "0->63"},  # Only one route
            77: {0: "77->78", 1: "77->101"},
            100: {1: "100->85"},  # Only one route
        }
        source_to_switch = {
            1: 13,  # Block 1 routes through switch 13
            150: 28,  # Block 150 routes through switch 28
            0: 63,  # Block 0 routes through switch 63
            100: 85,  # Block 100 routes through switch 85
        }

        # Check if current block is a switch block or routes through a switch
        if current in switch_routes:
            logger.debug(
                "ROUTING",
                f"Block {current} is in switch_routes",
                {
                    "current_block": current,
                    "in_source_to_switch": current in source_to_switch,
                },
            )

            # Check if this block routes through another switch
            if current in source_to_switch:
                switch_block = source_to_switch[current]
                switch_target = self.block_manager.get_switch_position(
                    self.line_name, switch_block
                )
                logger.debug(
                    "ROUTING",
                    f"Block {current} routes through switch {switch_block}, target={switch_target}",
                    {
                        "current_block": current,
                        "switch_block": switch_block,
                        "switch_target": switch_target,
                    },
                )
                if switch_target == switch_block + 1:
                    switch_target = switch_block
                    logger.debug(
                        "ROUTING",
                        f"Switch target adjusted to {switch_target}",
                        {"switch_target": switch_target},
                    )
            else:
                # This block is the actual switch
                switch_target = self.block_manager.get_switch_position(
                    self.line_name, current
                )
                logger.debug(
                    "ROUTING",
                    f"Block {current} is actual switch, target={switch_target}",
                    {"current_block": current, "switch_target": switch_target},
                )

            if switch_target != "N/A" and isinstance(switch_target, int):
                next_block = switch_target
                logger.info(
                    "ROUTING",
                    f"Using switch target: {current} → {next_block}",
                    {
                        "current_block": current,
                        "next_block": next_block,
                        "method": "switch_target",
                    },
                )
            else:
                # Fallback to backward/forward motion
                if previous is not None and previous == current + 1:
                    next_block = current - 1
                    logger.debug(
                        "ROUTING",
                        f"Fallback backward: {current} → {next_block}",
                        {
                            "current_block": current,
                            "next_block": next_block,
                            "previous": previous,
                        },
                    )
                elif previous is not None and previous == current - 1:
                    next_block = current + 1
                    logger.debug(
                        "ROUTING",
                        f"Fallback forward: {current} → {next_block}",
                        {
                            "current_block": current,
                            "next_block": next_block,
                            "previous": previous,
                        },
                    )
                else:
                    next_block = current
                    logger.warn(
                        "ROUTING",
                        f"Fallback staying at {current} (previous={previous})",
                        {
                            "current_block": current,
                            "next_block": next_block,
                            "previous": previous,
                        },
                    )
        else:
            logger.debug(
                "ROUTING",
                f"Block {current} NOT in switch_routes, using motion logic",
                {"current_block": current, "previous": previous},
            )

            # Use backward/forward motion logic
            if previous is not None and previous == current + 1:
                next_block = current - 1
                logger.debug(
                    "ROUTING",
                    f"Motion backward: {current} → {next_block}",
                    {
                        "current_block": current,
                        "next_block": next_block,
                        "previous": previous,
                    },
                )
            elif previous is not None and previous == current - 1:
                next_block = current + 1
                logger.debug(
                    "ROUTING",
                    f"Motion forward: {current} → {next_block}",
                    {
                        "current_block": current,
                        "next_block": next_block,
                        "previous": previous,
                    },
                )

            else:
                # Should never happen with proper hard-coding
                next_block = current + 1
                logger.warn(
                    "ROUTING",
                    f"DEFAULT CASE: {current} → {next_block} (previous={previous})",
                    {
                        "current_block": current,
                        "next_block": next_block,
                        "previous": previous,
                    },
                )

        # HARD RULE: Never return to previous block (physically impossible - train can't reverse)
        if previous is not None and next_block == previous:
            logger.warn(
                "ROUTING",
                f"HARD RULE VIOLATION: would return to previous {previous}, correcting",
                {
                    "current_block": current,
                    "next_block": next_block,
                    "previous": previous,
                },
            )

            # If we would go back to previous, try the opposite direction
            if previous == current + 1:
                next_block = current - 1
                logger.debug(
                    "ROUTING",
                    f"Corrected to backward: {current} → {next_block}",
                    {"current_block": current, "next_block": next_block},
                )
            elif previous == current - 1:
                next_block = current + 1
                logger.debug(
                    "ROUTING",
                    f"Corrected to forward: {current} → {next_block}",
                    {"current_block": current, "next_block": next_block},
                )
            else:
                # Stay put if no valid direction
                next_block = current
                logger.error(
                    "ROUTING",
                    f"Cannot correct, staying at {current}",
                    {
                        "current_block": current,
                        "next_block": next_block,
                        "previous": previous,
                    },
                )

        logger.info(
            "ROUTING",
            f"Green Line final routing decision: {current} → {next_block}",
            {"current_block": current, "next_block": next_block, "previous": previous},
        )

        return next_block

    def _get_red_line_next_block(self, current: int, previous: Optional[int]) -> int:
        """
        Determine next block for Red Line based on current position and routing rules.

        Args:
            current: Current block number
            previous: Previous block number (or None)

        Returns:
            Next block number
        """
        # Red line switch routes - blocks can appear multiple times for different switch scenarios
        switch_routes = {
            0: {0: "0->9"},  # Block 0 (yard) exits to block 9
            9: {0: "9->10", 1: "9->0"},  # Block 9: straight to 10 or branch to yard
            1: {0: "1->2", 1: "1->16"},  # Block 1: two routes
            16: {0: "16->17", 1: "16->1"},  # Block 16 switch
            27: {0: "27->28", 1: "27->76"},
            33: {0: "33->34", 1: "33->72"},
            38: {0: "38->39", 1: "38->71"},
            44: {0: "44->45", 1: "44->67"},
            52: {0: "52->53", 1: "52->66"},
        }

        source_to_switch = {
            0: 9,  # Block 0 (yard) routes through switch 9
            1: 16,  # Block 1 routes through switch 16
        }

        # Check if current block is a switch block or routes through a switch
        if current in switch_routes:
            # Check if this block routes through another switch
            if current in source_to_switch:
                switch_block = source_to_switch[current]
                switch_target = self.block_manager.get_switch_position(
                    self.line_name, switch_block
                )
            else:
                # This block is the actual switch
                switch_target = self.block_manager.get_switch_position(
                    self.line_name, current
                )

            if switch_target != "N/A" and isinstance(switch_target, int):
                next_block = switch_target
            else:
                # Fallback to backward/forward motion
                if previous is not None and previous == current + 1:
                    next_block = current - 1
                elif previous is not None and previous == current - 1:
                    next_block = current + 1
                else:
                    next_block = current + 1
        else:
            # Use backward/forward motion logic
            if previous is not None and previous == current + 1:
                next_block = current - 1
            elif previous is not None and previous == current - 1:
                next_block = current + 1
            else:
                # Should never happen with proper hard-coding
                next_block = current + 1

        # HARD RULE: Never return to previous block (physically impossible - train can't reverse)
        if previous is not None and next_block == previous:
            # If we would go back to previous, try the opposite direction
            if previous == current + 1:
                next_block = current - 1
            elif previous == current - 1:
                next_block = current + 1
            else:
                # Stay put if no valid direction
                next_block = current

        return next_block


class LineNetworkBuilder:
    """Builds network for Red and Green lines."""

    def __init__(self, df: pd.DataFrame, line_name: str):
        self.df = df
        self.line_name = line_name
        self.network = LineNetwork(line_name)
        self.all_blocks = []
        self.switch_data = {}

    def build(self) -> LineNetwork:
        """Build the network."""

        self._parse_blocks()

        if self.line_name == "Red Line":
            self._build_red_line()
        elif self.line_name == "Green Line":
            self._build_green_line()

        return self.network

    def _parse_blocks(self):
        """Get all blocks sequentially."""
        for idx, row in self.df.iterrows():
            block_num = row.get("Block Number", "N/A")
            if block_num != "N/A" and str(block_num) != "nan":
                try:
                    self.all_blocks.append(int(block_num))
                except Exception as e:
                    self.logger.error(
                        "TRACK",
                        f"Error converting block number {block_num} in builder: {e}",
                    )
        self.all_blocks = sorted(set(self.all_blocks))
        self.network.all_blocks = self.all_blocks

    def _build_red_line(self):
        """Build Red Line with hard-coded rules."""
        forbidden = {(66, 67), (67, 66), (71, 72), (72, 71)}

        for block in self.all_blocks:
            self.network.connections[block] = []

        for block in self.all_blocks:
            if block - 1 in self.all_blocks:
                if (block - 1, block) not in forbidden:
                    self.network.connections[block].append(block - 1)

            if block + 1 in self.all_blocks:
                if (block, block + 1) not in forbidden:
                    self.network.connections[block].append(block + 1)

        for block in self.switch_data:
            branch_targets = []
            for target in self.switch_data[block]:
                if target != block and abs(target - block) > 1:
                    if (block, target) not in forbidden and (
                        target,
                        block,
                    ) not in forbidden:
                        if target not in self.network.connections[block]:
                            self.network.connections[block].append(target)
                        if block not in self.network.connections[target]:
                            self.network.connections[target].append(block)

                        branch_targets.append(target)

                        conn = (min(block, target), max(block, target))
                        if conn not in self.network.additional_connections:
                            self.network.additional_connections.append(conn)

            if branch_targets:
                self.network.branch_points[block] = BranchPoint(
                    block=block, targets=branch_targets
                )

        self.network.skip_connections = [(66, 67), (71, 72)]

    def _build_green_line(self):
        """Build Green Line with hard-coded rules."""
        forbidden = {(100, 101)}

        for block in self.all_blocks:
            self.network.connections[block] = []

        for block in self.all_blocks:
            if block - 1 in self.all_blocks:
                if (block - 1, block) not in forbidden:
                    self.network.connections[block].append(block - 1)

            if block + 1 in self.all_blocks:
                if (block, block + 1) not in forbidden:
                    self.network.connections[block].append(block + 1)

        for block in self.switch_data:
            branch_targets = []
            for target in self.switch_data[block]:
                if target != block and abs(target - block) > 1:
                    if (block, target) not in forbidden and (
                        target,
                        block,
                    ) not in forbidden:
                        if target not in self.network.connections[block]:
                            self.network.connections[block].append(target)
                        if block not in self.network.connections[target]:
                            self.network.connections[target].append(block)

                        branch_targets.append(target)

                        conn = (min(block, target), max(block, target))
                        if conn not in self.network.additional_connections:
                            self.network.additional_connections.append(conn)

            if branch_targets:
                self.network.branch_points[block] = BranchPoint(
                    block=block, targets=branch_targets
                )

        self.network.skip_connections = [(100, 101)]


def main():
    """Test the network by loading data from an Excel file."""
    excel_file_path = "Track Layout & Vehicle Data vF5.xlsx"

    try:
        df = pd.read_excel(excel_file_path, sheet_name="Green Line")
    except FileNotFoundError:
        return

    builder = LineNetworkBuilder(df, "Green Line")
    network = builder.build()

    # Set the block manager (no parameters required)
    network.block_manager = DynamicBlockManager()

    current = 0
    previous = None

    for i in range(200):
        next_block = network.get_next_block(1, current, previous)

        if next_block == current:
            break

        previous = current
        current = next_block


if __name__ == "__main__":
    main()
