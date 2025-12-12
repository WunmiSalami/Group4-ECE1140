"""
Train Physics Engine - Simple Physics Class
NO UI - Instantiated by test UI
WRITES: motion section in track_model_Train_Model.json
READS: block section (commanded speed/authority) from track_model_Train_Model.json
"""

import json
import time
import threading


class Train:
    """Individual train with simple physics simulation"""

    # Physics constants
    MAX_ACCELERATION_FTPS2 = 1.64  # ft/s^2
    SERVICE_BRAKE_FTPS2 = -3.94  # ft/s^2
    EMERGENCY_BRAKE_FTPS2 = -8.86  # ft/s^2

    def __init__(self, train_id: int, line: str, json_path: str):
        """
        Initialize train

        Args:
            train_id: Train number (1-5)
            line: "Green" or "Red"
            json_path: Path to track_model_Train_Model.json
        """
        self.train_id = train_id
        self.line = line
        self.json_path = json_path

        # Train key in JSON (e.g., "G_train_1")
        prefix = "G" if line == "Green" else "R"
        self.train_key = f"{prefix}_train_{train_id}"

        # Physics state
        self.velocity_mph = 0.0  # mph
        self.acceleration_ftps2 = 0.0  # ft/s^2
        self.position_yds = 0.0  # yards (cumulative distance traveled)
        self.motion_state = "stopped"  # "stopped", "moving", "braking"

        # Command inputs (read from JSON)
        self.commanded_speed_mph = 0.0
        self.commanded_authority_yds = 0.0
        self.last_commanded_authority = 0.0

        # Control flags
        self.running = False
        self.paused = False
        self.speed_multiplier = 1.0
        self.update_thread = None
        self.dt = 0.5  # Time step in seconds

    def start(self):
        """Start physics simulation"""
        if self.running:
            return

        self.running = True
        self.update_thread = threading.Thread(target=self._update_loop, daemon=True)
        self.update_thread.start()

    def stop(self):
        """Stop physics simulation"""
        self.running = False
        if self.update_thread:
            self.update_thread.join(timeout=1.0)

    def pause(self):
        self.paused = True

    def resume(self):
        self.paused = False

    def set_speed_multiplier(self, multiplier: float):
        self.speed_multiplier = max(0.1, min(100.0, multiplier))

    def _update_loop(self):
        """Main physics update loop"""
        while self.running:
            if not self.paused:
                self._read_commands()
                self._update_physics()
                self._write_motion()
            time.sleep(self.dt / self.speed_multiplier)

    def _read_commands(self):
        """Read commanded speed and authority from JSON block section"""
        try:
            with open(self.json_path, "r") as f:
                data = json.load(f)

            if self.train_key in data:
                block = data[self.train_key].get("block", {})
                self.commanded_speed_mph = float(block.get("commanded speed", 0.0))
                self.commanded_authority_yds = float(
                    block.get("commanded authority", 0.0)
                )

        except Exception:
            pass

    def _update_physics(self):
        """Update train physics"""

        # Check for new authority - only reset position on FIRST dispatch
        current_authority = self.commanded_authority_yds

        # Track authority changes (but don't reset position anymore)
        self.last_commanded_authority = current_authority

        # Determine acceleration
        if self.commanded_authority_yds <= 0:
            self.acceleration_ftps2 = self.EMERGENCY_BRAKE_FTPS2
            self.motion_state = "stopped"
        elif self.commanded_speed_mph <= 0:
            self.acceleration_ftps2 = self.SERVICE_BRAKE_FTPS2
            self.motion_state = "braking" if self.velocity_mph > 0.01 else "stopped"
        else:
            speed_error = self.commanded_speed_mph - self.velocity_mph

            if abs(speed_error) < 0.1:
                self.acceleration_ftps2 = 0.0
                self.motion_state = "moving"
            elif speed_error > 0:
                self.acceleration_ftps2 = self.MAX_ACCELERATION_FTPS2
                self.motion_state = "moving"
            else:
                self.acceleration_ftps2 = self.SERVICE_BRAKE_FTPS2
                self.motion_state = "braking"

        # Update velocity
        self.velocity_mph = max(
            0.0, self.velocity_mph + self.acceleration_ftps2 * self.dt * 0.681818
        )

        # Update position
        self.position_yds += (self.velocity_mph / 0.681818) * self.dt / 3.0

        # Check authority limit
        authority_remaining = self.commanded_authority_yds - self.position_yds
        if authority_remaining <= 0 and self.velocity_mph > 0:
            self.position_yds = self.commanded_authority_yds
            self.velocity_mph = 0.0
            self.acceleration_ftps2 = 0.0
            self.motion_state = "stopped"

        # Final state check
        if self.velocity_mph <= 0.01:
            self.motion_state = "stopped"
            self.velocity_mph = 0.0

    def _write_motion(self):
        """Write motion data to JSON (only motion section), with file locking to prevent corruption."""
        import sys

        max_retries = 3
        msvcrt = None
        fcntl = None
        if sys.platform == "win32":
            import msvcrt as _msvcrt

            msvcrt = _msvcrt
        else:
            import fcntl as _fcntl

            fcntl = _fcntl
        for attempt in range(max_retries):
            try:
                lock_type = "msvcrt" if msvcrt else "fcntl"
                with open(self.json_path, "r+") as f:
                    # Acquire lock
                    if lock_type == "msvcrt":
                        msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 1)
                    else:
                        fcntl.flock(f, fcntl.LOCK_EX)

                    try:
                        data = json.load(f)
                        f.seek(0)
                        f.truncate()

                        # Write only current motion and position_yds
                        if self.train_key in data:
                            if "motion" not in data[self.train_key]:
                                data[self.train_key]["motion"] = {}
                            data[self.train_key]["motion"][
                                "current motion"
                            ] = self.motion_state
                            data[self.train_key]["motion"]["position_yds"] = round(
                                self.position_yds, 2
                            )

                        # Write back
                        json.dump(data, f, indent=4)
                        f.flush()
                    finally:
                        # Release lock
                        if lock_type == "msvcrt":
                            f.seek(0)
                            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
                        else:
                            fcntl.flock(f, fcntl.LOCK_UN)
                break  # Success
            except json.JSONDecodeError:
                if attempt < max_retries - 1:
                    import time

                    time.sleep(0.05)  # Wait 50ms and retry
                    continue
            except Exception:
                break  # Give up on other errors
