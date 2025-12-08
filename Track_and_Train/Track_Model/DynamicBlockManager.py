import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from logger import get_logger


class DynamicBlockManager:
    def __init__(self):
        self.line_states = {"Green": {}, "Red": {}}
        self.passengers_boarding = 0
        self.total_ticket_sales = 0
        self.trains = []

    def initialize_blocks(self, line_name, block_ids):
        """Create empty storage for blocks."""
        # Define which blocks have traffic lights
        traffic_light_blocks = {
            "Green": [0, 3, 7, 29, 58, 62, 76, 86, 100, 101, 150, 151],
            "Red": [0, 8, 14, 26, 31, 37, 42, 51],
        }

        light_blocks = traffic_light_blocks.get(line_name, [])

        for block_id in block_ids:
            # Extract numeric block number
            block_num = int("".join(filter(str.isdigit, str(block_id))))
            # Initialize light to -1 (N/A) for non-light blocks, 0 (Super Green) for light blocks
            initial_light = 0 if block_num in light_blocks else -1

            self.line_states[line_name][block_id] = {
                "failures": {"power": False, "circuit": False, "broken": False},
                "occupancy": False,
                "light": initial_light,
                "gate": "N/A",
                "switch_position": "N/A",
            }

    def write_inputs(self, line_name, switches, gates, lights):
        """Write arrays from JSON to storage."""
        if line_name not in self.line_states or not self.line_states[line_name]:
            return
        blocks = self.line_states[line_name].keys()

        # Define which blocks have traffic lights
        traffic_light_blocks = {
            "Green": [0, 3, 7, 29, 58, 62, 76, 86, 100, 101, 150, 151],
            "Red": [0, 8, 14, 26, 31, 37, 42, 51],
        }
        light_blocks = traffic_light_blocks.get(line_name, [])

        logger = get_logger()
        light_map = {0: "Super Green", 1: "Green", 2: "Yellow", 3: "Red", -1: "N/A"}

        for idx, block_id in enumerate(blocks):
            # Extract numeric block number
            block_num = int("".join(filter(str.isdigit, block_id)))

            # Only update light value if this block has a traffic light
            if block_num in light_blocks and idx < len(lights):
                old_light = self.line_states[line_name][block_id]["light"]
                new_light = lights[idx]
                self.line_states[line_name][block_id]["light"] = new_light

                if old_light != new_light and old_light != -1:
                    logger.debug(
                        "LIGHT",
                        f"{line_name} line block {block_num} traffic light: {light_map.get(old_light)} → {light_map.get(new_light)}",
                        {
                            "line": line_name,
                            "block": block_num,
                            "old_state": light_map.get(old_light),
                            "new_state": light_map.get(new_light),
                        },
                    )

            if block_num in gates:
                old_gate = self.line_states[line_name][block_id]["gate"]
                new_gate = gates[block_num]
                self.line_states[line_name][block_id]["gate"] = new_gate

                if old_gate != new_gate and old_gate != "N/A":
                    logger.info(
                        "GATE",
                        f"{line_name} line block {block_num} crossing gate: {old_gate} → {new_gate}",
                        {
                            "line": line_name,
                            "block": block_num,
                            "old_state": old_gate,
                            "new_state": new_gate,
                        },
                    )

            if block_num in switches:
                old_position = self.line_states[line_name][block_id]["switch_position"]
                new_position = switches[block_num]
                self.line_states[line_name][block_id]["switch_position"] = new_position

                if old_position != new_position and old_position != "N/A":
                    logger = get_logger()
                    logger.info(
                        "SWITCH",
                        f"{line_name} line block {block_num} switch changed to position {new_position}",
                        {
                            "line": line_name,
                            "block": block_num,
                            "old_position": old_position,
                            "new_position": new_position,
                        },
                    )

    def update_failures(self, line_name, block_id, power, circuit, broken):
        """Write failures."""
        old_failures = self.line_states[line_name][block_id]["failures"].copy()
        self.line_states[line_name][block_id]["failures"]["power"] = power
        self.line_states[line_name][block_id]["failures"]["circuit"] = circuit
        self.line_states[line_name][block_id]["failures"]["broken"] = broken

        logger = get_logger()

        # Log new failures
        if power and not old_failures["power"]:
            logger.warn(
                "FAILURE",
                f"{line_name} line {block_id} POWER failure activated",
                {"line": line_name, "block": block_id, "failure_type": "power"},
            )
        if circuit and not old_failures["circuit"]:
            logger.warn(
                "FAILURE",
                f"{line_name} line {block_id} CIRCUIT failure activated",
                {"line": line_name, "block": block_id, "failure_type": "circuit"},
            )
        if broken and not old_failures["broken"]:
            logger.warn(
                "FAILURE",
                f"{line_name} line {block_id} BROKEN RAIL failure activated",
                {"line": line_name, "block": block_id, "failure_type": "broken_rail"},
            )

        # Log cleared failures
        if not power and old_failures["power"]:
            logger.info(
                "FAILURE",
                f"{line_name} line {block_id} power failure cleared",
                {"line": line_name, "block": block_id, "failure_type": "power"},
            )
        if not circuit and old_failures["circuit"]:
            logger.info(
                "FAILURE",
                f"{line_name} line {block_id} circuit failure cleared",
                {"line": line_name, "block": block_id, "failure_type": "circuit"},
            )
        if not broken and old_failures["broken"]:
            logger.info(
                "FAILURE",
                f"{line_name} line {block_id} broken rail failure cleared",
                {"line": line_name, "block": block_id, "failure_type": "broken_rail"},
            )

    def get_block_dynamic_data(self, line_name, block_id):
        """Read data."""
        if block_id not in self.line_states[line_name]:
            return None

        state = self.line_states[line_name][block_id]
        light_map = {0: "Super Green", 1: "Green", 2: "Yellow", 3: "Red", -1: "N/A"}

        return {
            "occupancy": state["occupancy"],
            "traffic_light": light_map.get(state["light"], "N/A"),
            "gate": state["gate"],
            "failures": state["failures"],
            "switch_position": state["switch_position"],
        }

    def get_switch_position(self, line_name, block):
        # If the caller gives a number, convert it to the actual stored key
        if isinstance(block, int):
            for block_id in self.line_states[line_name]:
                # Extract only digits from stored block_id
                digits = "".join(filter(str.isdigit, str(block_id)))
                if digits and int(digits) == block:
                    block = block_id
                    break

        # If still not found, return None
        if block not in self.line_states[line_name]:
            return None

        return self.line_states[line_name][block]["switch_position"]
