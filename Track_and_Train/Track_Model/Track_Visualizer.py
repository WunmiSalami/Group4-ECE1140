"""
Railway Track Visualizer - VISUALIZATION ONLY
Uses skeleton paths from TrackDiagramParser
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import pandas as pd
import re
from typing import List, Tuple, Dict
from PIL import Image, ImageTk
import time
import os
import sys

VISUALIZER_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(VISUALIZER_DIR)

# Add parent directory to path for imports
sys.path.insert(0, PARENT_DIR)

# Import network builder and parser
from LineNetwork import LineNetworkBuilder
from TrackDiagramParser import TrackDiagramParser


def extract_station(value: str) -> str:
    """Extract station name from Infrastructure column."""
    text = str(value).upper()
    m = re.search(r"STATION[:;]?\s*([A-Z\s]+)", text)
    return m.group(1).strip().title() if m else "N/A"


def extract_crossing(value: str) -> str:
    """Check if this is a railway crossing."""
    return "Yes" if "RAILWAY CROSSING" in str(value).upper() else "No"


def parse_branching_connections(value: str) -> List[Tuple[int, int]]:
    """Parse SWITCH (A-B; C-D) format into connection pairs."""
    text = str(value).upper().strip()
    if "SWITCH TO YARD" in text or "SWITCH FROM YARD" in text:
        return []
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
        conn_match = re.search(r"(\d+)\s*-\s*(\d+)", part)
        if conn_match:
            from_block = int(conn_match.group(1))
            to_block = int(conn_match.group(2))
            connections.append((from_block, to_block))

    return connections


def parse_excel(filepath: str) -> dict:
    """Load Excel file and prepare data for each line."""
    xl = pd.ExcelFile(filepath)
    track_data = {}

    for sheet_name in xl.sheet_names:
        if not sheet_name.endswith("Line"):
            continue

        df = pd.read_excel(filepath, sheet_name=sheet_name)
        df = df.fillna("N/A")

        # Add visualization columns
        if "Infrastructure" in df.columns:
            df["Station"] = df["Infrastructure"].apply(extract_station)
            df["Crossing"] = df["Infrastructure"].apply(extract_crossing)
            df["BranchConnections"] = df["Infrastructure"].apply(
                parse_branching_connections
            )
        else:
            df["BranchConnections"] = [[] for _ in range(len(df))]

        # Create Block labels (Section + Block Number)
        if "Section" in df.columns and "Block Number" in df.columns:
            df["Block"] = df.apply(
                lambda row: (
                    str(row["Section"]).strip() + str(int(float(row["Block Number"])))
                    if str(row["Section"]) not in ["N/A", "nan"]
                    and str(row["Block Number"]) not in ["N/A", "nan"]
                    else "N/A"
                ),
                axis=1,
            )
        else:
            df["Block"] = "N/A"

        track_data[sheet_name] = df

    return track_data


class RailwayDiagram:
    """Railway track visualization using skeleton paths."""

    def __init__(self, parent, block_manager=None, line_network=None):
        """
        Initialize visualizer in embedded mode only.

        Args:
            parent: Parent tkinter widget
            block_manager: Reference to DynamicBlockManager
        """
        self.parent = parent
        self.root = parent.winfo_toplevel()
        self.block_manager = block_manager

        self.trains = {}
        self.train_icons = {}

        self.last_clicked_block = None
        self.track_data = {}
        self.parser = None
        self.line_network = line_network
        self.line_colors = {
            "Red Line": "#DC143C",
            "Green Line": "#228B22",
        }
        self.all_positions_green = {}
        self.all_positions_red = {}
        self.show_blocks = True
        self.show_stations = True

        # Variables still used internally
        self.blocks_var = tk.BooleanVar(value=True)
        self.stations_var = tk.BooleanVar(value=True)
        self.line_var = tk.StringVar()

        self.setup_ui()
        print(f"[Visualizer] LineNetwork connected: {self.line_network is not None}")

    def setup_ui(self):
        """Setup user interface for embedded mode."""

        # CANVAS WITH SCROLLBARS
        canvas_frame = ttk.Frame(self.parent)
        canvas_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.canvas = tk.Canvas(
            canvas_frame, bg="white", highlightthickness=1, highlightbackground="gray"
        )

        h_scrollbar = ttk.Scrollbar(
            canvas_frame, orient=tk.HORIZONTAL, command=self.canvas.xview
        )
        v_scrollbar = ttk.Scrollbar(
            canvas_frame, orient=tk.VERTICAL, command=self.canvas.yview
        )

        self.canvas.configure(
            xscrollcommand=h_scrollbar.set, yscrollcommand=v_scrollbar.set
        )

        h_scrollbar.pack(side=tk.BOTTOM, fill=tk.X)
        v_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # EVENT BINDINGS
        self.canvas.bind("<Button-1>", self.on_canvas_click)
        self.canvas.bind("<Motion>", self.on_canvas_hover)

        # INITIALIZE STATE
        self.hover_id = None
        self.elements = []
        self.current_line = None
        self.highlighted_block = None

    def load_excel_data(self, filepath: str):
        """Load Excel file without showing dialog."""
        try:
            self.track_data = parse_excel(filepath)
            self.parser = TrackDiagramParser(os.path.join(VISUALIZER_DIR, "track.png"))
            self.parser.parse()
        except Exception as e:
            print(f"Error loading Excel: {e}")

    def show_all_lines(self):
        """Show overview of all lines."""
        if not self.track_data:
            messagebox.showwarning("No Data", "Please load an Excel file first.")
            return
        self.current_line = None
        self.draw_all_lines()

    def draw_single_line_red(self, line_name: str):
        """Draw railway line using skeleton paths from parser."""
        self.canvas.delete("all")
        self.elements = []

        if not self.parser:
            messagebox.showwarning("No Parser", "Parser not initialized!")
            return

        df = self.track_data[line_name]
        color = self.line_colors.get(line_name, "#000000")

        # Get connection info from LineNetwork
        additional_connections = []
        skip_connections = []
        if self.line_network and line_name == "Red Line":
            additional_connections, skip_connections = (
                self.line_network.get_red_line_visualizer_info()
            )

        # Convert skip_connections from block numbers to section letters
        skip_sections = set()
        for block1, block2 in skip_connections:
            # Find sections for these blocks
            section1 = None
            section2 = None
            for idx, row in df.iterrows():
                if row.get("Block Number") == block1:
                    section1 = str(row.get("Section", "")).strip()
                if row.get("Block Number") == block2:
                    section2 = str(row.get("Section", "")).strip()
            if section1 and section2:
                skip_sections.add((section1, section2))

        # Group blocks by section
        section_blocks = {}
        for idx, row in df.iterrows():
            section = str(row.get("Section", "")).strip()
            if section and section != "N/A" and section != "nan":
                if section not in section_blocks:
                    section_blocks[section] = []
                section_blocks[section].append(
                    {
                        "idx": idx,
                        "block_num": (
                            int(row.get("Block Number", 0))
                            if row.get("Block Number") != "N/A"
                            else 0
                        ),
                        "block_name": row.get("Block", "N/A"),
                        "station": row.get("Station", "N/A"),
                        "crossing": row.get("Crossing", "No"),
                    }
                )

        # Calculate scaling factor
        block_spacing = 25  # Fixed spacing between blocks
        worst_ratio = 1.0

        for section, blocks in section_blocks.items():
            skeleton = self.parser.get_section_path_red(section)
            if skeleton and blocks:
                num_blocks = len(blocks)
                skeleton_length = len(skeleton)
                required_space = num_blocks * block_spacing

                if skeleton_length > 0:
                    ratio = required_space / skeleton_length
                    worst_ratio = max(worst_ratio, ratio)

        # Add some padding
        scale_factor = worst_ratio * 1.2

        # Size reduction factor
        size_reduction = 0.5

        self.all_positions_red = {}
        section_order = sorted(section_blocks.keys())

        # Draw each section with smooth curves
        for idx, section in enumerate(section_order):
            skeleton = self.parser.get_section_path_red(section)
            if not skeleton:
                continue

            blocks = section_blocks[section]
            if not blocks:
                continue

            # If there's a next section, orient skeleton based on closest distance
            if idx + 1 < len(section_order):
                next_section = section_order[idx + 1]
                next_skeleton = self.parser.get_section_path_red(next_section)

                if next_skeleton:
                    # Find minimum distance between any pixel in current and next section
                    min_dist = float("inf")
                    closest_curr_idx = 0

                    for i, curr_pixel in enumerate(skeleton):
                        for next_pixel in next_skeleton:
                            dist = (
                                (curr_pixel[0] - next_pixel[0]) ** 2
                                + (curr_pixel[1] - next_pixel[1]) ** 2
                            ) ** 0.5
                            if dist < min_dist:
                                min_dist = dist
                                closest_curr_idx = i

                    # If closest pixel is in first half, reverse skeleton
                    if closest_curr_idx < len(skeleton) / 2:
                        skeleton = skeleton[::-1]

            # Sample skeleton points for smoothing (every 5th pixel)
            sampled_skeleton = [skeleton[i] for i in range(0, len(skeleton), 5)]
            if len(skeleton) > 0 and skeleton[-1] not in sampled_skeleton:
                sampled_skeleton.append(skeleton[-1])

            # Scale skeleton points with size reduction
            scaled_skeleton = [
                (
                    int(x * scale_factor * size_reduction),
                    int(y * scale_factor * size_reduction),
                )
                for x, y in sampled_skeleton
            ]

            num_blocks = len(blocks)
            skeleton_len = len(scaled_skeleton)

            if skeleton_len < 2:
                continue

            # Distribute blocks evenly along skeleton
            for i, block in enumerate(blocks):
                # Calculate position along skeleton
                if num_blocks == 1:
                    t = 0.5
                else:
                    t = i / (num_blocks - 1)

                idx_pos = int(t * (skeleton_len - 1))
                idx_pos = min(idx_pos, skeleton_len - 1)

                x, y = scaled_skeleton[idx_pos]

                # Calculate perpendicular offset for label
                # Get direction vector from nearby points
                if idx_pos > 0 and idx_pos < len(scaled_skeleton) - 1:
                    # Use points before and after for better direction
                    dx = (
                        scaled_skeleton[idx_pos + 1][0]
                        - scaled_skeleton[idx_pos - 1][0]
                    )
                    dy = (
                        scaled_skeleton[idx_pos + 1][1]
                        - scaled_skeleton[idx_pos - 1][1]
                    )
                elif idx_pos > 0:
                    dx = scaled_skeleton[idx_pos][0] - scaled_skeleton[idx_pos - 1][0]
                    dy = scaled_skeleton[idx_pos][1] - scaled_skeleton[idx_pos - 1][1]
                else:
                    dx = scaled_skeleton[idx_pos + 1][0] - scaled_skeleton[idx_pos][0]
                    dy = scaled_skeleton[idx_pos + 1][1] - scaled_skeleton[idx_pos][1]

                # Perpendicular vector (rotated 90 degrees) - REVERSED for outside placement
                length = (dx**2 + dy**2) ** 0.5
                if length > 0:
                    perp_x = dy / length  # Flipped sign
                    perp_y = -dx / length  # Flipped sign
                else:
                    perp_x, perp_y = 0, 1

                # Offset distance
                offset_dist = 30
                label_x = x + perp_x * offset_dist
                label_y = y + perp_y * offset_dist

                self.all_positions_red[block["block_num"]] = (x, y)

                # Draw block label
                if self.blocks_var.get():
                    # Check if this block is a branch point
                    is_branch = (
                        self.line_network
                        and block["block_num"] in self.line_network.branch_points
                    )
                    label_color = "blue" if is_branch else "#333"

                    block_id = self.canvas.create_text(
                        label_x,
                        label_y,
                        text=block["block_name"],
                        font=("Arial", 8, "bold" if is_branch else "normal"),
                        fill=label_color,
                        tags="block_label",
                    )

                    self.elements.append(
                        {
                            "id": block_id,
                            "type": "block",
                            "data": {
                                "block_num": block["block_num"],
                                "block_name": block["block_name"],
                            },
                        }
                    )

                # Draw station
                if self.stations_var.get() and block["station"] != "N/A":
                    if block["crossing"] == "Yes":
                        size = 10
                        pts = [x, y - size, x + size, y, x, y + size, x - size, y]
                        marker_id = self.canvas.create_polygon(
                            pts, fill="red", outline="darkred", width=2, tags="station"
                        )
                    else:
                        size = 8
                        marker_id = self.canvas.create_oval(
                            x - size,
                            y - size,
                            x + size,
                            y + size,
                            fill=color,
                            outline="black",
                            width=2,
                            tags="station",
                        )

                    # Station name with perpendicular offset
                    station_offset = 80
                    station_x = x + perp_x * station_offset
                    station_y = y + perp_y * station_offset

                    name_id = self.canvas.create_text(
                        station_x,
                        station_y,
                        text=block["station"],
                        font=("Arial", 8, "bold"),
                        anchor="center",
                        tags="station_name",
                        width=300,  # Prevent vertical text wrapping
                    )

                    # Create background box for station name
                    bbox = self.canvas.bbox(name_id)
                    if bbox:
                        padding = 2
                        box_id = self.canvas.create_rectangle(
                            bbox[0] - padding,
                            bbox[1] - padding,
                            bbox[2] + padding,
                            bbox[3] + padding,
                            fill="white",
                            outline="gray",
                            width=1,
                            tags="station_box",
                        )
                        # Move text in front of box
                        self.canvas.tag_raise(name_id, box_id)

                    data = {"station": block["station"], "block": block["block_name"]}
                    self.elements.append(
                        {"id": marker_id, "type": "station", "data": data}
                    )
                    self.elements.append(
                        {"id": name_id, "type": "station", "data": data}
                    )

            # Draw smooth skeleton path
            if len(scaled_skeleton) >= 2:
                flat_points = []
                for x, y in scaled_skeleton:
                    flat_points.extend([x, y])

                self.canvas.create_line(
                    flat_points,
                    fill=color,
                    width=5,
                    smooth=True,
                    splinesteps=24,
                    tags="track",
                )

        # Draw smooth arrows between sections
        for i in range(len(section_order) - 1):
            curr_section = section_order[i]
            next_section = section_order[i + 1]

            # Skip if in skip list
            if (curr_section, next_section) in skip_sections:
                continue

            curr_blocks = section_blocks[curr_section]
            next_blocks = section_blocks[next_section]

            if curr_blocks and next_blocks:
                last_block = curr_blocks[-1]
                first_block = next_blocks[0]

                if (
                    last_block["block_num"] in self.all_positions_red
                    and first_block["block_num"] in self.all_positions_red
                ):
                    x1, y1 = self.all_positions_red[last_block["block_num"]]
                    x2, y2 = self.all_positions_red[first_block["block_num"]]

                    # Draw smooth connecting arrow with midpoint
                    mid_x = (x1 + x2) / 2
                    mid_y = (y1 + y2) / 2

                    self.canvas.create_line(
                        x1,
                        y1,
                        mid_x,
                        mid_y,
                        x2,
                        y2,
                        fill=color,
                        width=5,
                        smooth=True,
                        arrow=tk.LAST,
                        arrowshape=(12, 15, 6),
                        splinesteps=24,
                        tags="connector",
                    )

        # Draw additional branch connections
        for block1, block2 in additional_connections:
            # Find the skeleton pixels for both blocks
            block1_pixels = []
            block2_pixels = []

            for section, blocks in section_blocks.items():
                for block in blocks:
                    if block["block_num"] == block1:
                        # Get skeleton for this section
                        skeleton = self.parser.get_section_path_red(section)
                        if skeleton:
                            # Scale these pixels same way
                            block1_pixels = [
                                (
                                    int(x * scale_factor * size_reduction),
                                    int(y * scale_factor * size_reduction),
                                )
                                for x, y in skeleton
                            ]
                    if block["block_num"] == block2:
                        skeleton = self.parser.get_section_path_red(section)
                        if skeleton:
                            block2_pixels = [
                                (
                                    int(x * scale_factor * size_reduction),
                                    int(y * scale_factor * size_reduction),
                                )
                                for x, y in skeleton
                            ]

            if block1_pixels and block2_pixels:
                # Find closest pair of pixels between the two blocks
                min_dist = float("inf")
                closest_p1 = block1_pixels[0]
                closest_p2 = block2_pixels[0]

                for p1 in block1_pixels:
                    for p2 in block2_pixels:
                        dist = ((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2) ** 0.5
                        if dist < min_dist:
                            min_dist = dist
                            closest_p1 = p1
                            closest_p2 = p2

                x1, y1 = closest_p1
                x2, y2 = closest_p2

                mid_x = (x1 + x2) / 2
                mid_y = (y1 + y2) / 2

                self.canvas.create_line(
                    x1,
                    y1,
                    mid_x,
                    mid_y,
                    x2,
                    y2,
                    fill=color,
                    width=5,
                    smooth=True,
                    arrow=tk.LAST,
                    arrowshape=(12, 15, 6),
                    splinesteps=24,
                    tags="branch_connector",
                )
        yard_position = self.draw_yard(line_name, scale_factor, size_reduction)
        if yard_position:
            # Store yard position as block 0
            self.all_positions_green[0] = yard_position

        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        # Update info
        station_count = len(
            [r for _, r in df.iterrows() if r.get("Station", "N/A") != "N/A"]
        )

        info = f"{line_name}\n"
        info += f"• Sections: {len(section_blocks)}\n"
        info += f"• Scale: {scale_factor:.2f}x\n"
        info += f"• Total blocks: {sum(len(blocks) for blocks in section_blocks.values())}\n"
        info += f"• Stations: {station_count}"

    def draw_single_line_green(self, line_name: str):
        """Draw railway line using skeleton paths from parser."""
        self.canvas.delete("all")
        self.elements = []

        if not self.parser:
            messagebox.showwarning("No Parser", "Parser not initialized!")
            return

        df = self.track_data[line_name]
        color = self.line_colors.get(line_name, "#000000")

        # Get connection info from LineNetwork
        additional_connections = []
        skip_connections = []
        if self.line_network and line_name == "Green Line":
            additional_connections, skip_connections = (
                self.line_network.get_green_line_visualizer_info()
            )

        # Convert skip_connections from block numbers to section letters
        skip_sections = set()
        for block1, block2 in skip_connections:
            # Find sections for these blocks
            section1 = None
            section2 = None
            for idx, row in df.iterrows():
                if row.get("Block Number") == block1:
                    section1 = str(row.get("Section", "")).strip()
                if row.get("Block Number") == block2:
                    section2 = str(row.get("Section", "")).strip()
            if section1 and section2:
                skip_sections.add((section1, section2))

        # Group blocks by section
        section_blocks = {}
        for idx, row in df.iterrows():
            section = str(row.get("Section", "")).strip()
            if section and section != "N/A" and section != "nan":
                if section not in section_blocks:
                    section_blocks[section] = []
                section_blocks[section].append(
                    {
                        "idx": idx,
                        "block_num": (
                            int(row.get("Block Number", 0))
                            if row.get("Block Number") != "N/A"
                            else 0
                        ),
                        "block_name": row.get("Block", "N/A"),
                        "station": row.get("Station", "N/A"),
                        "crossing": row.get("Crossing", "No"),
                    }
                )

        # Calculate scaling factor
        block_spacing = 25  # Fixed spacing between blocks
        worst_ratio = 1.0

        for section, blocks in section_blocks.items():
            skeleton = self.parser.get_section_path_green(section)
            if skeleton and blocks:
                num_blocks = len(blocks)
                skeleton_length = len(skeleton)
                required_space = num_blocks * block_spacing

                if skeleton_length > 0:
                    ratio = required_space / skeleton_length
                    worst_ratio = max(worst_ratio, ratio)

        # Add some padding
        scale_factor = worst_ratio * 1.2

        # Size reduction factor
        size_reduction = 0.5

        self.all_positions_green = {}
        section_order = sorted(section_blocks.keys())

        # Draw each section with smooth curves
        for idx, section in enumerate(section_order):
            skeleton = self.parser.get_section_path_green(section)
            if not skeleton:
                continue

            blocks = section_blocks[section]
            if not blocks:
                continue

            # If there's a next section, orient skeleton based on closest distance
            if idx + 1 < len(section_order):
                next_section = section_order[idx + 1]
                next_skeleton = self.parser.get_section_path_green(next_section)

                if next_skeleton:
                    # Find minimum distance between any pixel in current and next section
                    min_dist = float("inf")
                    closest_curr_idx = 0

                    for i, curr_pixel in enumerate(skeleton):
                        for next_pixel in next_skeleton:
                            dist = (
                                (curr_pixel[0] - next_pixel[0]) ** 2
                                + (curr_pixel[1] - next_pixel[1]) ** 2
                            ) ** 0.5
                            if dist < min_dist:
                                min_dist = dist
                                closest_curr_idx = i

                    # If closest pixel is in first half, reverse skeleton
                    if closest_curr_idx < len(skeleton) / 2:
                        skeleton = skeleton[::-1]

            # Sample skeleton points for smoothing (every 5th pixel)
            sampled_skeleton = [skeleton[i] for i in range(0, len(skeleton), 5)]
            if len(skeleton) > 0 and skeleton[-1] not in sampled_skeleton:
                sampled_skeleton.append(skeleton[-1])

            # Scale skeleton points with size reduction
            scaled_skeleton = [
                (
                    int(x * scale_factor * size_reduction),
                    int(y * scale_factor * size_reduction),
                )
                for x, y in sampled_skeleton
            ]

            num_blocks = len(blocks)
            skeleton_len = len(scaled_skeleton)

            if skeleton_len < 2:
                continue

            # Distribute blocks evenly along skeleton
            for i, block in enumerate(blocks):
                # Calculate position along skeleton
                if num_blocks == 1:
                    t = 0.5
                else:
                    t = i / (num_blocks - 1)

                idx_pos = int(t * (skeleton_len - 1))
                idx_pos = min(idx_pos, skeleton_len - 1)

                x, y = scaled_skeleton[idx_pos]

                # Calculate perpendicular offset for label
                # Get direction vector from nearby points
                if idx_pos > 0 and idx_pos < len(scaled_skeleton) - 1:
                    # Use points before and after for better direction
                    dx = (
                        scaled_skeleton[idx_pos + 1][0]
                        - scaled_skeleton[idx_pos - 1][0]
                    )
                    dy = (
                        scaled_skeleton[idx_pos + 1][1]
                        - scaled_skeleton[idx_pos - 1][1]
                    )
                elif idx_pos > 0:
                    dx = scaled_skeleton[idx_pos][0] - scaled_skeleton[idx_pos - 1][0]
                    dy = scaled_skeleton[idx_pos][1] - scaled_skeleton[idx_pos - 1][1]
                else:
                    dx = scaled_skeleton[idx_pos + 1][0] - scaled_skeleton[idx_pos][0]
                    dy = scaled_skeleton[idx_pos + 1][1] - scaled_skeleton[idx_pos][1]

                # Perpendicular vector (rotated 90 degrees) - REVERSED for outside placement
                length = (dx**2 + dy**2) ** 0.5
                if length > 0:
                    perp_x = dy / length  # Flipped sign
                    perp_y = -dx / length  # Flipped sign
                else:
                    perp_x, perp_y = 0, 1

                # Offset distance
                offset_dist = 30
                label_x = x + perp_x * offset_dist
                label_y = y + perp_y * offset_dist

                self.all_positions_green[block["block_num"]] = (x, y)

                # Draw block label
                if self.blocks_var.get():
                    # Check if this block is a branch point
                    is_branch = (
                        self.line_network
                        and block["block_num"] in self.line_network.branch_points
                    )
                    label_color = "blue" if is_branch else "#333"

                    block_id = self.canvas.create_text(
                        label_x,
                        label_y,
                        text=block["block_name"],
                        font=("Arial", 8, "bold" if is_branch else "normal"),
                        fill=label_color,
                        tags="block_label",
                    )

                    self.elements.append(
                        {
                            "id": block_id,
                            "type": "block",
                            "data": {
                                "block_num": block["block_num"],
                                "block_name": block["block_name"],
                            },
                        }
                    )

                # Draw station
                if self.stations_var.get() and block["station"] != "N/A":
                    if block["crossing"] == "Yes":
                        size = 10
                        pts = [x, y - size, x + size, y, x, y + size, x - size, y]
                        marker_id = self.canvas.create_polygon(
                            pts, fill="red", outline="darkred", width=2, tags="station"
                        )
                    else:
                        size = 8
                        marker_id = self.canvas.create_oval(
                            x - size,
                            y - size,
                            x + size,
                            y + size,
                            fill=color,
                            outline="black",
                            width=2,
                            tags="station",
                        )

                    # Station name with perpendicular offset
                    station_offset = 80
                    station_x = x + perp_x * station_offset
                    station_y = y + perp_y * station_offset

                    name_id = self.canvas.create_text(
                        station_x,
                        station_y,
                        text=block["station"],
                        font=("Arial", 8, "bold"),
                        anchor="center",
                        tags="station_name",
                        width=300,  # Prevent vertical text wrapping
                    )

                    # Create background box for station name
                    bbox = self.canvas.bbox(name_id)
                    if bbox:
                        padding = 2
                        box_id = self.canvas.create_rectangle(
                            bbox[0] - padding,
                            bbox[1] - padding,
                            bbox[2] + padding,
                            bbox[3] + padding,
                            fill="white",
                            outline="gray",
                            width=1,
                            tags="station_box",
                        )
                        # Move text in front of box
                        self.canvas.tag_raise(name_id, box_id)

                    data = {"station": block["station"], "block": block["block_name"]}
                    self.elements.append(
                        {"id": marker_id, "type": "station", "data": data}
                    )
                    self.elements.append(
                        {"id": name_id, "type": "station", "data": data}
                    )

            # Draw smooth skeleton path
            if len(scaled_skeleton) >= 2:
                flat_points = []
                for x, y in scaled_skeleton:
                    flat_points.extend([x, y])

                self.canvas.create_line(
                    flat_points,
                    fill=color,
                    width=5,
                    smooth=True,
                    splinesteps=24,
                    tags="track",
                )

        # Draw smooth arrows between sections
        for i in range(len(section_order) - 1):
            curr_section = section_order[i]
            next_section = section_order[i + 1]

            # Skip if in skip list
            if (curr_section, next_section) in skip_sections:
                continue

            curr_blocks = section_blocks[curr_section]
            next_blocks = section_blocks[next_section]

            if curr_blocks and next_blocks:
                last_block = curr_blocks[-1]
                first_block = next_blocks[0]

                if (
                    last_block["block_num"] in self.all_positions_green
                    and first_block["block_num"] in self.all_positions_green
                ):
                    x1, y1 = self.all_positions_green[last_block["block_num"]]
                    x2, y2 = self.all_positions_green[first_block["block_num"]]

                    # Draw smooth connecting arrow with midpoint
                    mid_x = (x1 + x2) / 2
                    mid_y = (y1 + y2) / 2

                    self.canvas.create_line(
                        x1,
                        y1,
                        mid_x,
                        mid_y,
                        x2,
                        y2,
                        fill=color,
                        width=5,
                        smooth=True,
                        arrow=tk.LAST,
                        arrowshape=(12, 15, 6),
                        splinesteps=24,
                        tags="connector",
                    )

        # Draw additional branch connections
        for block1, block2 in additional_connections:
            # Find the skeleton pixels for both blocks
            block1_pixels = []
            block2_pixels = []

            for section, blocks in section_blocks.items():
                for block in blocks:
                    if block["block_num"] == block1:
                        # Get skeleton for this section
                        skeleton = self.parser.get_section_path_green(section)
                        if skeleton:
                            # Scale these pixels same way
                            block1_pixels = [
                                (
                                    int(x * scale_factor * size_reduction),
                                    int(y * scale_factor * size_reduction),
                                )
                                for x, y in skeleton
                            ]
                    if block["block_num"] == block2:
                        skeleton = self.parser.get_section_path_green(section)
                        if skeleton:
                            block2_pixels = [
                                (
                                    int(x * scale_factor * size_reduction),
                                    int(y * scale_factor * size_reduction),
                                )
                                for x, y in skeleton
                            ]

            if block1_pixels and block2_pixels:
                # Find closest pair of pixels between the two blocks
                min_dist = float("inf")
                closest_p1 = block1_pixels[0]
                closest_p2 = block2_pixels[0]

                for p1 in block1_pixels:
                    for p2 in block2_pixels:
                        dist = ((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2) ** 0.5
                        if dist < min_dist:
                            min_dist = dist
                            closest_p1 = p1
                            closest_p2 = p2

                x1, y1 = closest_p1
                x2, y2 = closest_p2

                mid_x = (x1 + x2) / 2
                mid_y = (y1 + y2) / 2

                self.canvas.create_line(
                    x1,
                    y1,
                    mid_x,
                    mid_y,
                    x2,
                    y2,
                    fill=color,
                    width=5,
                    smooth=True,
                    arrow=tk.LAST,
                    arrowshape=(12, 15, 6),
                    splinesteps=24,
                    tags="branch_connector",
                )
        yard_position = self.draw_yard(line_name, scale_factor, size_reduction)
        if yard_position:
            # Store yard position as block 0
            self.all_positions_green[0] = yard_position

        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

        # Update info
        station_count = len(
            [r for _, r in df.iterrows() if r.get("Station", "N/A") != "N/A"]
        )

        info = f"{line_name}\n"
        info += f"• Sections: {len(section_blocks)}\n"
        info += f"• Scale: {scale_factor:.2f}x\n"
        info += f"• Total blocks: {sum(len(blocks) for blocks in section_blocks.values())}\n"
        info += f"• Stations: {station_count}"

    def draw_all_lines(self):
        """Draw simple overview of all lines."""
        self.canvas.delete("all")
        self.elements = []

        line_names = list(self.track_data.keys())
        spacing_y = 200

        for line_idx, line_name in enumerate(line_names):
            df = self.track_data[line_name]
            color = self.line_colors.get(line_name, "#000000")
            base_y = 150 + line_idx * spacing_y

            # Line label
            self.canvas.create_text(
                50,
                base_y,
                text=line_name,
                font=("Arial", 11, "bold"),
                fill=color,
                anchor="w",
            )

            # Simple track
            blocks = [
                (row.get("Block", "N/A"), row.get("Station", "N/A"))
                for _, row in df.iterrows()
                if row.get("Block", "N/A") != "N/A"
                or row.get("Station", "N/A") != "N/A"
            ]

            for i, (block, station) in enumerate(blocks):
                x, y = 200 + i * 60, base_y

                if i < len(blocks) - 1:
                    self.canvas.create_line(
                        x, y, x + 60, y, fill=color, width=3, arrow=tk.LAST
                    )

                if station != "N/A":
                    self.canvas.create_oval(
                        x - 6, y - 6, x + 6, y + 6, fill=color, outline="black", width=2
                    )

        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def on_canvas_click(self, event):
        """Handle canvas click events."""
        x, y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        items = self.canvas.find_overlapping(x - 15, y - 15, x + 15, y + 15)

        for item in items:
            for element in self.elements:
                if element["id"] == item and element["type"] == "block":
                    self.last_clicked_block = element["data"]["block_name"]
                    return

    def on_canvas_hover(self, event):
        """Handle hover events."""
        x, y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)

        if self.hover_id:
            try:
                if "station" in self.canvas.gettags(self.hover_id):
                    self.canvas.itemconfig(self.hover_id, width=2)
            except:
                pass
            self.hover_id = None

        self.canvas.delete("tooltip")
        items = self.canvas.find_overlapping(x - 10, y - 10, x + 10, y + 10)

        for item in items:
            for element in self.elements:
                if element["id"] == item:
                    if element["type"] == "station":
                        self.canvas.itemconfig(item, width=30)
                        self.hover_id = item
                        self.root.config(cursor="hand2")
                        self.show_tooltip(x, y, element["data"]["station"])
                        return
                    elif element["type"] == "block":
                        self.root.config(cursor="hand2")
                        self.show_tooltip(x, y, element["data"]["block_name"])
                        return

        self.root.config(cursor="")

    def show_tooltip(self, x, y, text):
        """Show hover tooltip."""
        width = len(text) * 8 + 20
        self.canvas.create_rectangle(
            x + 15,
            y - 30,
            x + 15 + width,
            y - 5,
            fill="#FFFACD",
            outline="#333",
            width=2,
            tags="tooltip",
        )
        self.canvas.create_text(
            x + 15 + width // 2,
            y - 17,
            text=text,
            font=("Arial", 10, "bold"),
            tags="tooltip",
        )

    def display_line(self, line_name: str, highlighted_block=None):
        """
        Display specified line without user interaction.

        Args:
            line_name: Name of line to display (e.g., "Red Line", "Green Line")
            highlighted_block: Optional block name to highlight (e.g., "A5")
        """
        if line_name not in self.track_data:
            print(f"Line '{line_name}' not found in data")
            return

        self.current_line = line_name
        self.highlighted_block = highlighted_block

        # Build LineNetwork
        df = self.track_data[line_name]
        from LineNetwork import LineNetworkBuilder

        builder = LineNetworkBuilder(df, line_name)
        self.line_network = builder.build()
        self.line_network.block_manager = self.block_manager

        # Draw based on line type
        if line_name == "Red Line":
            self.draw_single_line_red(line_name)
        elif line_name == "Green Line":
            self.draw_single_line_green(line_name)
        else:
            print(f"Visualization for {line_name} not yet implemented")

        # Highlight selected block if specified
        if highlighted_block:
            self.highlight_block(highlighted_block)

    def highlight_block(self, block_name: str):
        """Ensure only one block is highlighted at a time."""
        # Determine correct base color for this line
        base_color = self.line_colors.get(self.current_line, "#333")

        # Clear *all* blocks, not just the last one
        for element in self.elements:
            if element["type"] == "block":
                try:
                    self.canvas.itemconfig(
                        element["id"], fill=base_color, font=("Arial", 8)
                    )
                except Exception:
                    pass

        # Highlight the selected block
        for element in self.elements:
            if (
                element["type"] == "block"
                and element["data"]["block_name"] == block_name
            ):
                self.canvas.itemconfig(
                    element["id"], fill="yellow", font=("Arial", 10, "bold")
                )
                ##bbox = self.canvas.bbox(element["id"])
                ##if bbox:
                ##self.canvas.see(element["id"])
                self.highlighted_block_id = element["id"]
                break

    def draw_yard(self, line_name: str, scale_factor: float, size_reduction: float):
        """Draw the yard section on the track."""

        if line_name == "Red Line":
            skeleton = self.parser.get_section_path_red("YARD")
        elif line_name == "Green Line":
            skeleton = self.parser.get_section_path_green("YARD")
        else:
            return

        if not skeleton:
            return

        color = self.line_colors.get(line_name, "#228B22")

        # Draw each pixel as a small circle instead of a line
        for x, y in skeleton:
            scaled_x = int(x * scale_factor * size_reduction)
            scaled_y = int(y * scale_factor * size_reduction)
            self.canvas.create_oval(
                scaled_x - 2,
                scaled_y - 2,
                scaled_x + 2,
                scaled_y + 2,
                fill=color,
                outline="",
                tags="yard_track",
            )

        # Add YARD label at center
        xs = [int(x * scale_factor * size_reduction) for x, y in skeleton]
        ys = [int(y * scale_factor * size_reduction) for x, y in skeleton]
        center_x = sum(xs) // len(xs)
        center_y = sum(ys) // len(ys)

        self.canvas.create_text(
            center_x,
            center_y,
            text="YARD",
            font=("Arial", 10, "bold"),
            fill="purple",
            tags="yard_label",
        )

        # Return the center position
        return (center_x, center_y)

    def animate_train(self, train_id, line):
        """Initialize and start train animation from yard (block 0)."""
        # Skip if the train already exists
        if train_id in self.trains:
            return

        try:
            from PIL import Image, ImageTk

            # Load and resize train image - NO COLORING
            train_image = Image.open("train.png").convert("RGBA")
            train_image = train_image.resize((30, 30), Image.Resampling.LANCZOS)

            photo = ImageTk.PhotoImage(train_image)

            if not hasattr(self, "train_photos"):
                self.train_photos = {}
            self.train_photos[train_id] = photo

        except Exception as e:
            print(f"Error loading train image: {e}")
            photo = None

        # Determine which position dictionary to use
        if line == "Green" or line == "Green Line":
            positions = self.all_positions_green
        elif line == "Red" or line == "Red Line":
            positions = self.all_positions_red
        else:
            print(f"Unknown line: {line}")
            return

        # ALWAYS START AT YARD (block 0)
        starting_block = 0

        self.trains[train_id] = {
            "line": line,
            "previous_block": None,
            "current_block": starting_block,
        }

        # Get yard position from stored positions
        if starting_block in positions:
            x, y = positions[starting_block]
            print(f"Train {train_id} starting at yard position: ({x}, {y})")
        else:
            x, y = 50, 50
            print(f"WARNING: Yard position not found for {line}! Using default.")

        # Draw the train icon
        if photo:
            icon_id = self.canvas.create_image(
                x, y, image=photo, tags=f"train_{train_id}"
            )
        else:
            # Fallback to star if image fails - use same color for all
            icon_id = self.canvas.create_text(
                x,
                y,
                text="★",
                font=("Segoe UI", 20),
                fill="gold",  # Single color for all trains
                tags=f"train_{train_id}",
            )

        self.train_icons[train_id] = icon_id

        self.canvas.tag_bind(
            icon_id, "<Enter>", lambda event, t=train_id: self.show_train_info(event, t)
        )
        self.canvas.tag_bind(icon_id, "<Leave>", lambda event: self.hide_train_info())

        print(f"Train {train_id} created at yard (block {starting_block})")
        self.animate_train_step(train_id)

    def animate_train_step(self, train_id):
        """Move the specified train to its next block."""
        if not self.line_network or train_id not in self.trains:
            return

        train = self.trains[train_id]
        current_block = train["current_block"]
        previous_block = train["previous_block"]

        # Get next block from the Line Network
        next_block = self.line_network.get_next_block(
            train_id, current_block, previous_block
        )

        # Determine which position dictionary to use
        line = train["line"]
        if line == "Green" or line == "Green Line":
            positions = self.all_positions_green
        elif line == "Red" or line == "Red Line":
            positions = self.all_positions_red
        else:
            print(f"Unknown line: {line}")
            return

        # Get position for next block - handle case where block position doesn't exist
        if next_block in positions:
            x, y = positions[next_block]
        else:
            print(f"Warning: Block {next_block} not found in positions for {line}")
            # Keep at current position
            if current_block in positions:
                x, y = positions[current_block]
            else:
                x, y = 100, 100

        # Move the train icon
        if train_id in self.train_icons:
            self.canvas.coords(self.train_icons[train_id], x, y)

        # Highlight the current block
        block_name = None
        if self.current_line and self.current_line in self.track_data:
            df = self.track_data[self.current_line]
            for _, row in df.iterrows():
                if row.get("Block Number") == next_block:
                    section = str(row.get("Section", "")).strip()
                    block_name = f"{section}{next_block}"
                    break

        if block_name:
            self.highlight_block(block_name)

        # Update train position in memory
        train["previous_block"] = current_block
        train["current_block"] = next_block

        # Schedule next animation step (repeat every 1 second)
        self.root.after(1000, lambda: self.animate_train_step(train_id))

    def show_train_info(self, event, train_id):
        train = self.trains[train_id]
        info = f"Train {train_id} | Line: {train['line']} | Block: {train['current_block']}"
        self.hover_label = tk.Label(self.root, text=info, bg="yellow")
        self.hover_label.place(x=event.x_root + 10, y=event.y_root + 10)

    def hide_train_info(self):
        """Hide train info tooltip on mouse leave."""
        if hasattr(self, "hover_label") and self.hover_label:
            self.hover_label.destroy()
            self.hover_label = None
