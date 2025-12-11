import csv
import os
import re
from datetime import datetime
from tkinter import filedialog
import sys

# Add parent directory to path for logger import
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parent_dir)
from logger import get_logger


class ScheduleManager:
    """
    Handles automatic train scheduling by loading CSV files and dispatching trains
    at scheduled times using the existing manual dispatch infrastructure.
    """

    def __init__(self, track_control):
        """
        Initialize the schedule manager.

        Args:
            track_control: Reference to the TrackControl instance
        """
        self.track_control = track_control
        self.active_schedule = []
        self.schedule_index = 0
        self.schedule_loaded = False
        self.running = False

    def load_schedule_file(self):
        """
        Open file dialog, load and validate CSV schedule file.
        Populates self.active_schedule with parsed entries.
        """
        logger = get_logger()

        # Open file dialog
        csv_path = filedialog.askopenfilename(
            title="Select Schedule CSV",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )

        if not csv_path:
            logger.info("SCHEDULE", "Schedule load cancelled by user", {})
            return False

        # Validate the schedule
        if not self.validate_schedule_csv(csv_path):
            logger.error(
                "SCHEDULE",
                f"Schedule validation failed: {csv_path}",
                {"file": csv_path},
            )
            return False

        # Parse CSV and load into memory
        self.active_schedule = []

        with open(csv_path, newline="") as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                self.active_schedule.append(
                    {
                        "train_id": int(row["train_id"]),
                        "line": row["line"],
                        "destination_station": row["destination_station"],
                        "dispatch_time": row["dispatch_time"],
                        "arrival_time": row["arrival_time"],
                    }
                )

        self.schedule_index = 0
        self.schedule_loaded = True

        logger.info(
            "SCHEDULE",
            f"Schedule loaded successfully: {len(self.active_schedule)} entries from {csv_path}",
            {"file": csv_path, "entry_count": len(self.active_schedule)},
        )

        # Update UI status if available
        if hasattr(self.track_control, "auto_status"):
            self.track_control.auto_status.config(
                text=f"📋 Schedule Loaded ({len(self.active_schedule)} entries)"
            )

        return True

    def validate_schedule_csv(self, csv_path):
        """
        Validate CSV schedule file for errors.
        Checks: line names, station names, time formats, time logic, train sequencing.

        Args:
            csv_path: Path to CSV file

        Returns:
            bool: True if valid (or minor errors), False if critical errors
        """
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

        # Get valid stations from track_control infrastructure
        valid_stations_dict = self.track_control.infrastructure

        with open(csv_path, newline="") as csvfile:
            reader = csv.DictReader(csvfile)
            for row_number, row in enumerate(reader, 1):
                train_id = row["train_id"]
                line = row["line"]
                destination = row["destination_station"]
                dispatch_time = row["dispatch_time"]
                arrival_time = row["arrival_time"]

                # Track first appearance of each train
                if train_id not in trains_first_seen:
                    trains_first_seen[train_id] = row_number
                    logger.info(
                        "SCHEDULE",
                        f"Train {train_id} first seen at row {row_number}, will dispatch from Yard",
                        {"train_id": train_id, "row": row_number},
                    )

                # Validate line
                if line not in ["Green", "Red"]:
                    logger.error(
                        "SCHEDULE",
                        f"Row {row_number}: Invalid line '{line}', must be 'Green' or 'Red'",
                        {"row": row_number, "line": line},
                    )
                    error_count += 1

                # Validate station exists on line
                valid_stations = valid_stations_dict.get(line, {}).get("stations", {})
                if destination not in valid_stations:
                    logger.error(
                        "SCHEDULE",
                        f"Row {row_number}: Invalid station '{destination}' for {line} Line",
                        {"row": row_number, "station": destination, "line": line},
                    )
                    error_count += 1

                # Validate time formats
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

                # Validate time logic
                if valid_time_format(dispatch_time) and valid_time_format(arrival_time):
                    # Dispatch must be before arrival
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

                    # Dispatch must not be in the past
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

                    # Must have at least 1 minute between dispatch and arrival
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

                    # Train can't dispatch before it arrives from previous leg
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

        # Return validation result
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

    def process_schedule_tick(self):
        """
        Called every 200ms by TrackControl automatic cycle.
        Checks if it's time to dispatch the next scheduled train.
        Calls the existing manual_dispatch method to dispatch trains.
        """
        # Don't process if not running or no schedule loaded
        if not self.running or not self.schedule_loaded:
            return

        # Check if schedule complete
        if self.schedule_index >= len(self.active_schedule):
            return

        logger = get_logger()
        current_time = datetime.now().strftime("%H:%M")
        current_entry = self.active_schedule[self.schedule_index]

        train_id = current_entry["train_id"]
        dispatch_time = current_entry["dispatch_time"]

        # Check if it's time to dispatch
        if current_time >= dispatch_time:
            # Check if train already exists
            if train_id in self.track_control.active_trains:
                train_state = self.track_control.active_trains[train_id].get(
                    "state", None
                )

                # Only dispatch if train is ready (arrived at previous destination)
                if train_state == "Arrived":
                    origin = self.track_control.active_trains[train_id].get(
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

                    # Call manual dispatch using schedule entry data
                    self._dispatch_from_schedule(current_entry)
                    self.schedule_index += 1

                elif train_state == "Dwelling":
                    logger.debug(
                        "SCHEDULE",
                        f"Train {train_id} still dwelling, waiting to dispatch next leg",
                        {"train_id": train_id},
                    )
                else:
                    # Train is "En Route" or "At Station" or "Dispatching"
                    # Wait for it to complete current leg
                    pass
            else:
                # First dispatch - train doesn't exist yet
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

                # Call manual dispatch using schedule entry data
                self._dispatch_from_schedule(current_entry)
                self.schedule_index += 1

    def _dispatch_from_schedule(self, schedule_entry):
        """
        Dispatch a train using schedule entry by calling the existing manual dispatch logic.
        This mimics filling out the manual UI and clicking dispatch.

        Args:
            schedule_entry: Dict with train_id, line, destination_station, arrival_time
        """
        train_id = schedule_entry["train_id"]
        line = schedule_entry["line"]
        destination = schedule_entry["destination_station"]
        arrival_time = schedule_entry["arrival_time"]

        # Get route using existing infrastructure
        config = self.track_control.infrastructure[line]
        stations = config["stations"]

        route_key = (line, "Yard", destination)
        route = self.track_control.route_lookup_via_station.get(route_key, [])

        if not route:
            logger = get_logger()
            logger.error(
                "SCHEDULE",
                f"No valid route found for Train {train_id} to {destination} on {line} Line",
                {"train_id": train_id, "line": line, "destination": destination},
            )
            return

        logger = get_logger()
        logger.info(
            "ROUTE",
            f"Train {train_id} route to {destination}: {route}, first station block: {route[0] if route else 'NONE'}",
            {
                "train_id": train_id,
                "destination": destination,
                "route": route,
                "first_station": route[0] if route else None,
            },
        )

        # Create or update train in active_trains (same as manual dispatch)
        if train_id not in self.track_control.active_trains:
            self.track_control.active_trains[train_id] = {
                "line": line,
                "destination": destination,
                "current_block": 0,
                "commanded_speed": 0,
                "commanded_authority": 0,
                "state": "Dispatching",
                "current_station": "Yard",
                "arrival_time": arrival_time,
                "route": route,
                "current_leg_index": 0,
                "next_station_block": route[0] if route else 0,
                "dwell_start_time": None,
                "last_position_yds": 0.0,
            }
        else:
            # Update for next leg
            self.track_control.active_trains[train_id]["line"] = line
            self.track_control.active_trains[train_id]["destination"] = destination
            self.track_control.active_trains[train_id]["current_block"] = 0
            self.track_control.active_trains[train_id]["commanded_speed"] = 0
            self.track_control.active_trains[train_id]["commanded_authority"] = 0
            self.track_control.active_trains[train_id]["state"] = "Dispatching"
            self.track_control.active_trains[train_id]["arrival_time"] = arrival_time
            self.track_control.active_trains[train_id]["route"] = route
            self.track_control.active_trains[train_id]["next_station_block"] = (
                route[0] if route else 0
            )
            self.track_control.active_trains[train_id]["dwell_start_time"] = None
            self.track_control.active_trains[train_id]["last_position_yds"] = 0.0

        # Update CTC data (same as manual dispatch)
        ctc_data = self.track_control._read_ctc_data()
        if ctc_data:
            train_key = f"Train {train_id}"
            if train_key in ctc_data.get("Dispatcher", {}).get("Trains", {}):
                ctc_data["Dispatcher"]["Trains"][train_key]["Line"] = line
                ctc_data["Dispatcher"]["Trains"][train_key][
                    "Station Destination"
                ] = destination
                ctc_data["Dispatcher"]["Trains"][train_key][
                    "Arrival Time"
                ] = arrival_time
                ctc_data["Dispatcher"]["Trains"][train_key]["State"] = "Dispatching"
                ctc_data["Dispatcher"]["Trains"][train_key]["Speed"] = "Calculating..."
                self.track_control._write_ctc_data(ctc_data)

        logger.info(
            "TRAIN",
            f"Schedule dispatch: Train {train_id} to {destination} on {line} Line, arrival {arrival_time}",
            {
                "train_id": train_id,
                "line": line,
                "destination": destination,
                "arrival_time": arrival_time,
                "route_stations": len(route),
            },
        )

    def start(self):
        """Start processing the schedule"""
        self.running = True

    def stop(self):
        """Stop processing the schedule"""
        self.running = False

    def reset(self):
        """Reset schedule to beginning"""
        self.schedule_index = 0
