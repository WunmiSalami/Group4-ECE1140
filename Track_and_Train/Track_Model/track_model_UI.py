import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import sys
import os

# Set up path for imports
_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
_PARENT_DIR = os.path.dirname(_CURRENT_DIR)
sys.path.insert(0, _PARENT_DIR)

from Track_Visualizer import RailwayDiagram
from DynamicBlockManager import DynamicBlockManager
from LineNetwork import LineNetwork
from PIL import Image, ImageTk
import json
import pandas as pd
import re

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRACK_MODEL_DIR = os.path.join(BASE_DIR, "Track_Model")

STATIC_JSON_PATH = os.path.join(TRACK_MODEL_DIR, "track_model_static.json")
CONTROLLER_JSON_PATH = os.path.join(BASE_DIR, "track_io.json")


class TrackModelUI(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.pack(fill="both", expand=True)

        # Configure parent window dark theme
        if isinstance(parent, tk.Tk) or isinstance(parent, tk.Toplevel):
            parent.configure(bg="#2b2d31")

        # Configure dark theme styles
        style = ttk.Style()
        style.theme_use("clam")

        # Frame and LabelFrame styles
        style.configure("TFrame", background="#2b2d31")
        style.configure(
            "TLabelframe",
            background="#2b2d31",
            foreground="#ffffff",
            borderwidth=2,
            relief="solid",
        )
        style.configure(
            "TLabelframe.Label",
            background="#2b2d31",
            foreground="#5865f2",
            font=("Segoe UI", 10, "bold"),
        )

        # Label styles
        style.configure(
            "TLabel", background="#2b2d31", foreground="#ffffff", font=("Segoe UI", 10)
        )
        style.configure(
            "Bold.TLabel",
            background="#2b2d31",
            foreground="#ffffff",
            font=("Segoe UI", 10, "bold"),
        )
        style.configure(
            "Heading.TLabel",
            background="#2b2d31",
            foreground="#5865f2",
            font=("Segoe UI", 11, "bold"),
        )

        # Button styles
        style.configure(
            "TButton",
            background="#5865f2",
            foreground="white",
            borderwidth=0,
            focuscolor="none",
            font=("Segoe UI", 10),
        )
        style.map("TButton", background=[("active", "#4752c4"), ("pressed", "#3c45a5")])

        # Checkbutton styles
        style.configure(
            "TCheckbutton",
            background="#2b2d31",
            foreground="#ffffff",
            font=("Segoe UI", 10),
        )
        style.map("TCheckbutton", background=[("active", "#2b2d31")])

        # Combobox styles
        style.configure(
            "TCombobox",
            fieldbackground="#1e1f22",
            background="#5865f2",
            foreground="#ffffff",
            borderwidth=1,
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", "#1e1f22")],
            selectbackground=[("readonly", "#5865f2")],
        )

        self.configure(style="TFrame")

        self.block_manager = DynamicBlockManager()
        self.line_network = None
        self.visualizer = None
        self.green_line_temp = 72
        self.red_line_temp = 72
        self.ticket_sales = 0
        self.passengers_boarding = 0

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=9)  # Left panel gets more space
        self.grid_columnconfigure(1, weight=1)  # Right panel

        # Hook cleanup to parent window close
        if isinstance(parent, tk.Tk) or isinstance(parent, tk.Toplevel):
            parent.protocol("WM_DELETE_WINDOW", self.on_window_close)

        # === LEFT PANEL === #
        self.left_frame = ttk.LabelFrame(
            self, text="🛤️  TRACK LAYOUT INTERACTIVE DIAGRAM", style="TLabelframe"
        )
        self.left_frame.grid(row=0, column=0, sticky="NSEW", padx=10, pady=10)

        self.left_frame.grid_rowconfigure(0, weight=1)
        self.left_frame.grid_columnconfigure(0, weight=1)
        self.setup_track_visualizer()

        ttk.Label(
            self.left_frame,
            text="Note: Not Drawn to Scale",
            font=("Segoe UI", 9, "italic"),
            foreground="#b5bac1",
            style="TLabel",
        ).pack(pady=(0, 5))
        legend_frame = ttk.Frame(self.left_frame, style="TFrame")
        legend_frame.pack(pady=5)
        ttk.Label(
            legend_frame,
            text="Train Live Position:",
            font=("Segoe UI", 10, "bold"),
            style="Bold.TLabel",
        ).pack(side=tk.LEFT, padx=5)
        ttk.Label(
            legend_frame,
            text="★",
            foreground="#faa61a",
            font=("Segoe UI", 12),
            style="TLabel",
        ).pack(side=tk.LEFT, padx=3)

        # === RIGHT PANEL === #
        right_frame = ttk.Frame(self, style="TFrame")
        right_frame.grid(row=0, column=1, sticky="NSEW", padx=10, pady=10)
        right_frame.grid_columnconfigure(0, weight=1)

        # --- Upload / Line / Block --- #
        control_frame = ttk.LabelFrame(
            right_frame, text="📋 TRACK LAYOUT & LINE SELECTION", style="TLabelframe"
        )
        control_frame.grid(row=0, column=0, sticky="EW", padx=5, pady=5)

        # 1. Upload Button (Packs Top)
        ttk.Button(
            control_frame,
            text="Upload Track Layout File",
            command=self.upload_track_file,
        ).pack(
            fill="x", padx=10, pady=5
        )  # Use fill='x' to take full available width

        # 2. Line Selection (Packs Top)
        line_select_frame = ttk.Frame(control_frame, style="TFrame")
        line_select_frame.pack(fill="x", padx=5, pady=2)
        ttk.Label(
            line_select_frame,
            text="Select Line:",
            font=("Segoe UI", 10, "bold"),
            style="Bold.TLabel",
        ).pack(side=tk.LEFT, padx=5)

        # Initialize line selector empty; populate dynamically after upload
        self.line_selector = ttk.Combobox(
            line_select_frame, state="readonly", width=10, values=[], style="TCombobox"
        )
        self.line_selector.pack(side=tk.RIGHT, padx=5)
        self.line_selector.bind("<<ComboboxSelected>>", self.on_line_selected)

        # 3. Block Selection (Packs Top)
        block_select_frame = ttk.Frame(control_frame, style="TFrame")
        block_select_frame.pack(fill="x", padx=5, pady=2)
        ttk.Label(
            block_select_frame,
            text="Select Block:",
            font=("Segoe UI", 10, "bold"),
            style="Bold.TLabel",
        ).pack(side=tk.LEFT, padx=5)
        self.block_selector = ttk.Combobox(
            block_select_frame, state="readonly", width=10, style="TCombobox"
        )
        self.block_selector.pack(side=tk.RIGHT, padx=5)
        self.block_selector.bind("<<ComboboxSelected>>", self.on_block_selected)

        # --- Currently Selected Block --- #
        block_frame = ttk.LabelFrame(
            right_frame, text="📍 CURRENTLY SELECTED BLOCK", style="TLabelframe"
        )
        block_frame.grid(row=1, column=0, sticky="EW", padx=5, pady=5)
        # block_frame.grid_columnconfigure(0, weight=1) # Remove these two lines
        # block_frame.grid_columnconfigure(1, weight=1)

        left_fields = [
            "Line:",
            "Direction of Travel:",
            "Traffic Light:",
            "Gate:",
            "Speed Limit (mph):",
            "Grade (%):",
        ]
        right_fields = [
            "Elevation (M):",
            "Block Length (ft):",
            "Station:",
            "Switch Position:",
            "Crossing:",
            "Branching:",
        ]

        # Combine fields into a single list for vertical stacking
        all_fields = left_fields + right_fields
        self.block_labels = {f: tk.StringVar(value="N/A") for f in all_fields}

        # Single column layout: iterate through all fields and stack them vertically
        for field in all_fields:
            frame = ttk.Frame(block_frame, style="TFrame")
            frame.pack(anchor="w", pady=2, padx=5, fill="x", expand=False)

            # Label for the field name (e.g., "Line:")
            ttk.Label(
                frame,
                text=field,
                font=("Segoe UI", 10, "bold"),
                width=20,
                style="Bold.TLabel",
            ).pack(side=tk.LEFT)
            # Label for the variable value (e.g., "Red Line")
            ttk.Label(
                frame,
                textvariable=self.block_labels[field],
                font=("Segoe UI", 10),
                style="TLabel",
            ).pack(side=tk.LEFT)

        # --- Block Information (Dynamic Fields) --- #
        dynamic_frame = ttk.LabelFrame(
            right_frame, text="ℹ️  BLOCK INFORMATION", style="TLabelframe"
        )
        dynamic_frame.grid(row=2, column=0, sticky="EW", padx=5, pady=5)
        dyn_fields = ["Occupancy:"]
        self.dynamic_labels = {f: tk.StringVar(value="N/A") for f in dyn_fields}
        for field in dyn_fields:
            frame = ttk.Frame(dynamic_frame, style="TFrame")
            frame.pack(anchor="w", pady=2)
            ttk.Label(
                frame,
                text=field,
                font=("Segoe UI", 10, "bold"),
                width=28,
                style="Bold.TLabel",
            ).pack(side=tk.LEFT)
            ttk.Label(
                frame,
                textvariable=self.dynamic_labels[field],
                font=("Segoe UI", 10),
                style="TLabel",
            ).pack(side=tk.LEFT)

        # --- Environment Line (MODIFIED TO STACK VERTICALLY) --- #
        env_line = ttk.Frame(right_frame, style="TFrame")
        env_line.grid(row=3, column=0, sticky="EW", padx=5, pady=(0, 5))

        # Row 1: Track Heating Status
        heating_frame = ttk.Frame(env_line, style="TFrame")
        heating_frame.pack(fill="x", padx=5, pady=2)
        ttk.Label(
            heating_frame,
            text="Track Heating:",
            font=("Segoe UI", 10, "bold"),
            style="Bold.TLabel",
        ).pack(side=tk.LEFT)
        self.heating_status = ttk.Label(
            heating_frame, text="OFF", foreground="#ed4245", style="TLabel"
        )
        self.heating_status.pack(side=tk.LEFT, padx=(5, 5))

        # Row 2: Temperature Control
        temp_frame = ttk.Frame(env_line, style="TFrame")
        temp_frame.pack(fill="x", padx=5, pady=2)
        ttk.Label(
            temp_frame,
            text="Environment Temperature (°F):",
            font=("Segoe UI", 10, "bold"),
            style="Bold.TLabel",
        ).pack(side=tk.LEFT)

        self.temperature = tk.StringVar(value="N/A")

        # Packing buttons and display from left to right in the temp_frame
        ttk.Button(
            temp_frame,
            text="-",
            width=3,
            command=self.decrease_temp_immediate,
            style="TButton",
        ).pack(side=tk.LEFT, padx=(5, 2))
        ttk.Label(
            temp_frame,
            textvariable=self.temperature,
            font=("Segoe UI", 10),
            width=5,
            anchor="center",
            style="TLabel",
        ).pack(side=tk.LEFT)
        ttk.Button(
            temp_frame,
            text="+",
            width=3,
            command=self.increase_temp_immediate,
            style="TButton",
        ).pack(side=tk.LEFT, padx=2)

        # --- Station Information --- #
        self.station_vars = {
            "Boarding:": tk.StringVar(value="N/A"),
            "Ticket Sales:": tk.StringVar(value="N/A"),
        }
        station_frame = ttk.LabelFrame(
            right_frame, text="🚉 STATION INFORMATION", style="TLabelframe"
        )
        station_frame.grid(row=4, column=0, sticky="EW", padx=5, pady=5)
        for label, var in self.station_vars.items():
            frame = ttk.Frame(station_frame, style="TFrame")
            frame.pack(anchor="w", pady=2, padx=10)
            ttk.Label(
                frame,
                text=label,
                font=("Segoe UI", 10, "bold"),
                width=25,
                style="Bold.TLabel",
            ).pack(side=tk.LEFT)
            ttk.Label(
                frame, textvariable=var, font=("Segoe UI", 10), style="TLabel"
            ).pack(side=tk.LEFT)

        # --- Failure Status --- #
        self.failure_vars = {
            "Power Failure": tk.BooleanVar(value=False),
            "Circuit Failure": tk.BooleanVar(value=False),
            "Broken Track": tk.BooleanVar(value=False),
        }
        failure_frame = ttk.LabelFrame(
            right_frame, text="⚠️  FAILURE STATUS", style="TLabelframe"
        )
        failure_frame.grid(row=5, column=0, sticky="EW", padx=5, pady=5)
        for label, var in self.failure_vars.items():
            ttk.Checkbutton(
                failure_frame,
                text=label,
                variable=var,
                command=self.update_failures,
                style="TCheckbutton",
            ).pack(anchor="w", padx=15, pady=2)
        self.warning_label = ttk.Label(
            failure_frame,
            text="✓ All Systems Normal",
            font=("Segoe UI", 10, "italic"),
            foreground="#3ba55d",
            style="TLabel",
        )
        self.warning_label.pack(anchor="w", padx=15, pady=(5, 2))

        # Internal Data
        self.static_data = {}
        self.block_selected = False
        self.load_data()

        # === Added check for pre-existing static.json === #
        self.check_existing_static_data()
        self.poll_visualizer_clicks()

    def check_existing_static_data(self):
        """Check if static JSON file already contains data and load it."""
        if not os.path.exists(STATIC_JSON_PATH):
            self.after(500, self.check_existing_static_data)
            return
        try:
            with open(STATIC_JSON_PATH, "r") as f:
                data = json.load(f)
            static_data = data.get("static_data", {})
            if static_data:
                available_lines = list(static_data.keys())
                # Add Show All Lines option if multiple lines available
                if len(available_lines) > 1:
                    available_lines.append("Show All Lines")
                self.line_selector["values"] = available_lines
                if available_lines:
                    self.line_selector.current(0)
                    self.on_line_selected()
                    messagebox.showinfo("Success", "Track layout successfully loaded.")
            else:
                self.after(500, self.check_existing_static_data)
        except Exception:
            self.after(500, self.check_existing_static_data)

    def extract_branching(self, value):
        text = str(value).upper().strip()
        if "SWITCH TO YARD" in text or "SWITCH FROM YARD" in text:
            return {}
        if "SWITCH" not in text:
            return {}
        match = re.search(r"\(([^)]+)\)", text)
        if not match:
            return {}

        contents = match.group(1)

        # Parse connections
        parts = re.split(r"[;,]", contents)
        all_blocks = []
        for part in parts:
            part = part.strip()
            conn_match = re.search(r"(\d+)\s*-\s*(\d+)", part)
            if conn_match:
                all_blocks.append(int(conn_match.group(1)))
                all_blocks.append(int(conn_match.group(2)))

        if not all_blocks:
            return {}

        # Find branch point (appears twice)
        from collections import Counter

        counts = Counter(all_blocks)
        branch_point = None
        for blk, count in counts.items():
            if count > 1:
                branch_point = blk
                break

        if branch_point:
            connected = [c.strip() for c in re.split(r"[;,]", contents) if c.strip()]
            branch_text = ", ".join(connected)
            return {branch_point: branch_text}

        return {}

    def upload_track_file(self):
        file_path = filedialog.askopenfilename(
            title="Select Track Layout File",
            filetypes=[("Excel Files", "*.xlsx *.xls")],
        )
        if not file_path:
            messagebox.showerror(
                "No File Selected",
                "Please select a valid track layout file before continuing.",
            )
            return

        try:
            xl = pd.ExcelFile(file_path)
            sheet_names = xl.sheet_names
            available_lines = [
                name.replace(" Line", "").strip()
                for name in sheet_names
                if name.endswith(" Line")
            ]

            self.line_selector["values"] = available_lines
            if available_lines:
                self.line_selector.current(0)
            else:
                self.line_selector.set("")

            all_lines_data = {}
            for line in available_lines:
                df = pd.read_excel(file_path, sheet_name=f"{line} Line")
                df = df.fillna("N/A")
                df["Station"] = df["Infrastructure"].apply(self.extract_station)
                df["Crossing"] = df["Infrastructure"].apply(self.extract_crossing)

                # Build branch mapping
                branch_map = {}
                for idx, row in df.iterrows():
                    result = self.extract_branching(row["Infrastructure"])
                    if result:
                        branch_map.update(result)

                # Assign branching to correct blocks
                def assign_branching(row):
                    block_num = row.get("Block Number")
                    if block_num not in ["N/A", "nan"]:
                        try:
                            return branch_map.get(int(float(block_num)), "N/A")
                        except:
                            pass
                    return "N/A"

                df["Branching"] = df.apply(assign_branching, axis=1)

                all_lines_data[line] = df.to_dict(orient="records")

            # Add Show All Lines option if multiple lines available
            if len(available_lines) > 1:
                available_lines.append("Show All Lines")
                self.line_selector["values"] = available_lines

            data = {
                "static_data": all_lines_data,
                "block": {},
                "environment": {},
                "station": {},
                "failures": {},
                "commanded": {},
            }

            with open(STATIC_JSON_PATH, "w") as f:
                json.dump(data, f, indent=4)

            self.update_visualizer_display(excel_path=file_path)

        except Exception as e:
            messagebox.showerror("Error", f"Failed to process Excel file:\n{e}")

    def extract_crossing(self, value):
        text = str(value).upper()
        if "RAILWAY CROSSING" in text:
            return "Yes"
        return "No"

    def extract_station(self, value):
        text = str(value).upper()
        match = re.search(r"STATION[:;]?\s*([A-Z\s]+)", text)
        return match.group(1).strip().title() if match else "N/A"

    def on_line_selected(self, event=None):
        """Handle line selection and update the visualizer exactly once."""
        selected_line = self.line_selector.get()
        if not selected_line or not os.path.exists(STATIC_JSON_PATH):
            self.block_selector["values"] = []
            return

        # Handle Show All Lines option
        if selected_line == "Show All Lines":
            if hasattr(self, "visualizer") and self.visualizer:
                self.visualizer.show_all_lines()
                self.block_selector["values"] = []
                self.block_selector.set("")
                # Clear block information display
                for label_key in self.block_labels:
                    self.block_labels[label_key].set("N/A")
                # Set line_network to None so check_and_start_trains knows we're in overlay mode
                self.line_network = None
            return

        self.load_static_after_upload(selected_line)

        full_line_name = f"{selected_line} Line"

        # Build LineNetwork using LineNetworkBuilder to ensure skip_connections are set
        if (
            hasattr(self, "visualizer")
            and self.visualizer
            and self.visualizer.track_data
        ):
            df = self.visualizer.track_data.get(full_line_name)
            if df is not None:
                from LineNetwork import LineNetworkBuilder

                builder = LineNetworkBuilder(df, full_line_name)
                self.line_network = builder.build()
                self.line_network.block_manager = self.block_manager
            else:
                # Fallback to empty LineNetwork if no data
                self.line_network = LineNetwork(full_line_name, self.block_manager)
        else:
            # Fallback to empty LineNetwork if visualizer not ready
            self.line_network = LineNetwork(full_line_name, self.block_manager)

        if hasattr(self, "visualizer") and self.visualizer:
            try:
                # Update visualizer to use shared LineNetwork instance
                self.visualizer.line_network = self.line_network

                if getattr(self.visualizer, "current_line", None) != full_line_name:
                    self.visualizer.display_line(full_line_name)
            except Exception as e:
                pass  # Display failures are non-critical

    def load_static_after_upload(self, selected_line):
        if not os.path.exists(STATIC_JSON_PATH):
            return
        with open(STATIC_JSON_PATH, "r") as f:
            data = json.load(f)
        records = data.get("static_data", {}).get(selected_line, [])
        self.static_data = records
        blocks = [
            f"{r['Section']}{int(float(r['Block Number']))}"
            for r in records
            if str(r["Block Number"]).replace(".", "", 1).isdigit()
        ]
        if self.block_manager and blocks:
            self.block_manager.initialize_blocks(selected_line, blocks)
        self.block_selector["values"] = blocks
        if blocks:
            self.block_selector.current(0)
            self.on_block_selected(None)

    def setup_track_visualizer(self):
        if hasattr(self, "track_label"):
            self.track_label.destroy()
        self.visualizer = RailwayDiagram(
            self.left_frame,
            block_manager=self.block_manager,
            line_network=self.line_network,
        )
        self.excel_file_path = None

    def update_visualizer_display(
        self, excel_path=None, line_name=None, block_name=None
    ):
        if not hasattr(self, "visualizer"):
            return
        if excel_path:
            self.excel_file_path = excel_path
        if not self.excel_file_path:
            return
        if line_name is None:
            line_name = self.line_selector.get()
        if block_name is None:
            block_name = self.block_selector.get()
        if not self.visualizer.track_data:
            self.visualizer.load_excel_data(self.excel_file_path)

        # Ensure line_network is created before displaying (only create once per line)
        full_line_name = f"{line_name} Line" if line_name else None
        if line_name and (
            not self.line_network
            or getattr(self.line_network, "line_name", None) != full_line_name
        ):
            self.on_line_selected()

        self.visualizer.display_line(full_line_name, highlighted_block=block_name)

    def on_block_selected(self, event=None):
        self.block_selected = True
        block_id = self.block_selector.get()
        if not self.static_data:
            return
        for b in self.static_data:
            identifier = f"{b['Section']}{int(float(b['Block Number']))}"
            if identifier == block_id:
                kmh = b.get("Speed Limit (Km/Hr)", 0)
                mph = (
                    round(float(kmh) * 0.621371, 2)
                    if isinstance(kmh, (int, float))
                    else "N/A"
                )
                meters = b.get("Block Length (m)", 0)
                feet = (
                    round(float(meters) * 3.28084, 2)
                    if isinstance(meters, (int, float))
                    else "N/A"
                )
                self.block_labels["Line:"].set(b.get("Line", "N/A"))
                self.block_labels["Speed Limit (mph):"].set(mph)
                self.block_labels["Grade (%):"].set(b.get("Block Grade (%)", "N/A"))
                self.block_labels["Elevation (M):"].set(b.get("ELEVATION (M)", "N/A"))
                self.block_labels["Block Length (ft):"].set(feet)
                self.block_labels["Station:"].set(b.get("Station", "N/A"))
                self.block_labels["Switch Position:"].set("N/A")
                self.block_labels["Crossing:"].set(b.get("Crossing", "N/A"))
                self.block_labels["Branching:"].set(b.get("Branching", "N/A"))
                selected_block = identifier
                break

        if selected_block and hasattr(self, "visualizer"):
            try:
                self.visualizer.highlight_block(selected_block)
            except Exception as e:
                pass  # Highlight failures are non-critical

    def get_crossing_for_block(self, block_id):
        """Helper method to get crossing status for a block from static data."""
        for b in self.static_data:
            identifier = f"{b['Section']}{int(float(b['Block Number']))}"
            if identifier == block_id:
                return b.get("Crossing", "No")
        return "No"

    def load_data(self):
        """Read Phase: Retrieve dynamic data from block_manager and update UI."""
        selected_line = self.line_selector.get()
        selected_block = self.block_selector.get()

        # For Show All Lines, skip UI updates since no blocks are visible/selectable
        if selected_line == "Show All Lines":
            # Still need to check and start trains and reschedule timer
            self.check_and_start_trains()
            self.after(500, self.load_data)
            return

        # Update temperature and heater status regardless of block data
        temp = self.green_line_temp if selected_line == "Green" else self.red_line_temp
        self.temperature.set(str(temp))
        heating_on = temp < 32
        self.heating_status.config(
            text="ON" if heating_on else "OFF",
            foreground="#3ba55d" if heating_on else "#ed4245",
        )

        if self.block_manager and selected_block:
            block_data = self.block_manager.get_block_dynamic_data(
                selected_line, selected_block
            )

            if block_data:
                occupancy = block_data["occupancy"]
                traffic_light = block_data["traffic_light"]
                gate = block_data["gate"]
                failures = block_data["failures"]
                switch_position = block_data["switch_position"]

                # Determine direction from UNIDIRECTIONAL_BLOCKS
                from LineNetwork import UNIDIRECTIONAL_BLOCKS
                import re

                line_key = self.line_selector.get().replace(" Line", "")
                unidirectional_ranges = UNIDIRECTIONAL_BLOCKS.get(line_key, [])
                direction = "Bidirectional"  # Default to Bidirectional (most blocks)
                try:
                    # Extract numeric part from block ID (e.g., "A5" -> 5)
                    match = re.search(r"\d+", selected_block)
                    if match:
                        block_num = int(match.group())
                        # Check if block is in any unidirectional range
                        for item in unidirectional_ranges:
                            if isinstance(item, tuple):
                                start, end = item
                                if (start <= end and start <= block_num <= end) or (
                                    start > end and end <= block_num <= start
                                ):
                                    direction = "Unidirectional"
                                    break
                            elif isinstance(item, int):
                                # Single block
                                if block_num == item:
                                    direction = "Unidirectional"
                                    break
                except (ValueError, TypeError):
                    pass

                station_name = self.get_station_name_for_block(selected_block)
                passengers_boarding = self.block_manager.passengers_boarding
                ticket_sales = self.block_manager.total_ticket_sales

                # Check for failures and apply overrides
                if failures.get("power"):
                    # Power failure: lights off, gates closed, switches N/A
                    traffic_light = "OFF"
                    crossing = self.get_crossing_for_block(selected_block)
                    if crossing == "Yes":
                        gate = "Closed"
                    else:
                        gate = "N/A"
                    switch_position = "N/A"

                if failures.get("circuit"):
                    # Circuit failure: occupancy unavailable
                    self.dynamic_labels["Occupancy:"].set("N/A")
                else:
                    # Normal occupancy display
                    self.dynamic_labels["Occupancy:"].set(
                        "OCCUPIED" if occupancy else "CLEAR"
                    )

                # Update UI with processed values
                self.block_labels["Direction of Travel:"].set(direction)
                self.block_labels["Traffic Light:"].set(traffic_light)
                self.block_labels["Gate:"].set(gate)
                self.block_labels["Switch Position:"].set(str(switch_position))

                self.station_vars["Boarding:"].set(passengers_boarding)
                self.station_vars["Ticket Sales:"].set(ticket_sales)

                # Only update failure vars if they don't match (to avoid overriding user input)
                for key in self.failure_vars:
                    state_key = key.split()[0].lower()
                    stored_value = failures.get(state_key, False)
                    # Only update if the stored value differs from current checkbox state
                    if self.failure_vars[key].get() != stored_value:
                        self.failure_vars[key].set(stored_value)

                failures_active = any(failures.values())
                if failures_active:
                    active = []
                    if failures.get("power"):
                        active.append("Power Failure")
                    if failures.get("circuit"):
                        active.append("Circuit Failure")
                    if failures.get("broken"):
                        active.append("Broken Track")
                    failure_text = ", ".join(active)
                    self.warning_label.config(
                        text=f"⚠️ {failure_text}",
                        foreground="#faa61a",
                    )
                else:
                    self.warning_label.config(
                        text="✓ All Systems Normal", foreground="#3ba55d"
                    )
            else:
                # No block data - reset failure checkboxes
                for key in self.failure_vars:
                    self.failure_vars[key].set(False)
                self.warning_label.config(
                    text="✓ All Systems Normal", foreground="#3ba55d"
                )

        # Update traffic light colors on canvas
        if hasattr(self, "visualizer") and self.visualizer:
            self.visualizer.update_traffic_light_colors()

        self.check_and_start_trains()
        self.after(500, self.load_data)

    def increase_temp_immediate(self):
        selected_line = self.line_selector.get()
        if selected_line == "Green":
            self.green_line_temp += 1
            self.temperature.set(str(self.green_line_temp))
        elif selected_line == "Red":
            self.red_line_temp += 1
            self.temperature.set(str(self.red_line_temp))

    def decrease_temp_immediate(self):
        selected_line = self.line_selector.get()
        if selected_line == "Green":
            self.green_line_temp -= 1
            self.temperature.set(str(self.green_line_temp))
        elif selected_line == "Red":
            self.red_line_temp -= 1
            self.temperature.set(str(self.red_line_temp))

    def update_failures(self):
        selected_line = self.line_selector.get()
        selected_block = self.block_selector.get()
        if selected_line and selected_block and self.block_manager:
            self.block_manager.update_failures(
                selected_line,
                selected_block,
                power=self.failure_vars["Power Failure"].get(),
                circuit=self.failure_vars["Circuit Failure"].get(),
                broken=self.failure_vars["Broken Track"].get(),
            )

    def poll_visualizer_clicks(self):
        """Check for new block clicks every 500 ms."""
        if not hasattr(self, "visualizer"):
            self.after(500, self.poll_visualizer_clicks)
            return

        clicked = getattr(self.visualizer, "last_clicked_block", None)
        if clicked:
            self.visualizer.last_clicked_block = None  # reset

            if clicked in self.block_selector["values"]:
                self.block_selector.set(clicked)
                self.on_block_selected()

        self.after(500, self.poll_visualizer_clicks)

    def get_station_name_for_block(self, block_id):
        """Get station name for a block from static JSON."""
        import json

        selected_line = self.line_selector.get()

        try:
            with open(STATIC_JSON_PATH, "r") as f:
                static_data = json.load(f)

            line_key = selected_line.replace(" Line", "")

            # FIX: Access through "static_data" wrapper
            blocks = static_data.get("static_data", {}).get(line_key, [])

            for block in blocks:
                block_num = block.get("Block Number")
                section = block.get("Section", "")

                # Construct the identifier the same way it's done in upload_track_file
                if block_num not in ["N/A", "nan", None] and section not in [
                    "N/A",
                    "nan",
                    None,
                ]:
                    try:
                        constructed_id = f"{section}{int(float(block_num))}"
                        if constructed_id == block_id:
                            return block.get("Station", "N/A")
                    except (ValueError, TypeError):
                        continue

            return "N/A"

        except FileNotFoundError:
            return "N/A"
        except json.JSONDecodeError as e:
            return "N/A"
        except Exception as e:
            return "N/A"

    def on_window_close(self):
        """Handle cleanup when track model UI window is closing"""
        try:
            if os.path.exists(STATIC_JSON_PATH):
                with open(STATIC_JSON_PATH, "w") as f:
                    json.dump({}, f, indent=4)
        except Exception as e:
            pass  # Cleanup failures are non-critical

        # Get parent window and destroy it
        root = self.winfo_toplevel()
        if root:
            root.destroy()

    def check_and_start_trains(self):
        # Always read from track_io.json and sync to train model
        selected_line = self.line_selector.get()

        if selected_line == "Show All Lines":
            # Read data for BOTH Red and Green lines
            if (
                hasattr(self, "visualizer")
                and self.visualizer
                and self.visualizer.track_data
            ):
                # Read Red Line data
                if "Red Line" in self.visualizer.track_data:
                    df_red = self.visualizer.track_data.get("Red Line")
                    if df_red is not None:
                        from LineNetwork import LineNetworkBuilder

                        red_network = LineNetworkBuilder(df_red, "Red Line").build()
                        red_network.block_manager = self.block_manager
                        red_network.read_train_data_from_json()

                # Read Green Line data
                if "Green Line" in self.visualizer.track_data:
                    df_green = self.visualizer.track_data.get("Green Line")
                    if df_green is not None:
                        from LineNetwork import LineNetworkBuilder

                        green_network = LineNetworkBuilder(
                            df_green, "Green Line"
                        ).build()
                        green_network.block_manager = self.block_manager
                        green_network.read_train_data_from_json()
        elif self.line_network:
            # Read data for single line
            self.line_network.read_train_data_from_json()

        # Then check if any trains need to start animating
        for train in self.block_manager.trains:
            train_id = train["train_id"]
            line = train["line"]
            if train["start"] and train_id not in self.visualizer.trains:
                self.visualizer.animate_train(train_id, line)


if __name__ == "__main__":
    app = TrackModelUI()
    app.mainloop()

    if os.path.exists(STATIC_JSON_PATH):
        with open(STATIC_JSON_PATH, "w") as f:
            json.dump({}, f, indent=4)
