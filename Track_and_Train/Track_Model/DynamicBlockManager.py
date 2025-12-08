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

        for idx, block_id in enumerate(blocks):
            # Extract numeric block number
            block_num = int("".join(filter(str.isdigit, block_id)))

            # Only update light value if this block has a traffic light
            if block_num in light_blocks and idx < len(lights):
                self.line_states[line_name][block_id]["light"] = lights[idx]

            if block_num in gates:
                self.line_states[line_name][block_id]["gate"] = gates[block_num]

            if block_num in switches:
                self.line_states[line_name][block_id]["switch_position"] = switches[
                    block_num
                ]

    def update_failures(self, line_name, block_id, power, circuit, broken):
        """Write failures."""
        self.line_states[line_name][block_id]["failures"]["power"] = power
        self.line_states[line_name][block_id]["failures"]["circuit"] = circuit
        self.line_states[line_name][block_id]["failures"]["broken"] = broken

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
