"""
Centralized logging system for Train Track Control System
Logs to both file and optionally to console with deduplication
"""

import json
import os
from datetime import datetime
from threading import Lock
from collections import deque


class TrainLogger:
    """Thread-safe logger with deduplication for train system"""

    def __init__(self, log_dir="logs", max_log_size_mb=10):
        self.log_dir = log_dir
        self.max_log_size = max_log_size_mb * 1024 * 1024  # Convert to bytes
        self.lock = Lock()

        # Deduplication: track last N messages to avoid repeats
        self.recent_messages = deque(maxlen=50)
        self.repeat_count = {}

        # Ensure log directory exists
        os.makedirs(self.log_dir, exist_ok=True)

        # Delete old log files (keep only current session)
        self._cleanup_old_logs()

        # Create log file with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = os.path.join(self.log_dir, f"train_system_{timestamp}.log")
        self.json_log_file = os.path.join(
            self.log_dir, f"train_system_{timestamp}.json"
        )

        # Initialize JSON log structure
        self.json_logs = {"session_start": datetime.now().isoformat(), "events": []}

        # Write initial log entry
        self._write_to_file(f"{'='*80}\n")
        self._write_to_file(f"Train Track Control System - Log Started\n")
        self._write_to_file(f"Session: {timestamp}\n")
        self._write_to_file(f"{'='*80}\n\n")

    def _cleanup_old_logs(self):
        """Delete all existing log files in log directory"""
        try:
            for filename in os.listdir(self.log_dir):
                if filename.startswith("train_system_") and (
                    filename.endswith(".log") or filename.endswith(".json")
                ):
                    file_path = os.path.join(self.log_dir, filename)
                    try:
                        os.remove(file_path)
                    except Exception:
                        pass  # Ignore errors (file might be in use)
        except Exception:
            pass  # Ignore if directory doesn't exist

    def _write_to_file(self, message):
        """Write message to log file"""
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(message)
            self._check_log_rotation()
        except Exception as e:
            print(f"[Logger Error] Could not write to log: {e}")

    def _write_json_log(self, event):
        """Write event to JSON log file"""
        try:
            self.json_logs["events"].append(event)

            # Write entire JSON structure (keep last 1000 events)
            if len(self.json_logs["events"]) > 1000:
                self.json_logs["events"] = self.json_logs["events"][-1000:]

            with open(self.json_log_file, "w", encoding="utf-8") as f:
                json.dump(self.json_logs, f, indent=2)
        except Exception as e:
            print(f"[Logger Error] Could not write JSON log: {e}")

    def _check_log_rotation(self):
        """Rotate log file if it exceeds max size"""
        try:
            if os.path.getsize(self.log_file) > self.max_log_size:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                new_log = os.path.join(self.log_dir, f"train_system_{timestamp}.log")
                self.log_file = new_log
                self._write_to_file(f"{'='*80}\n")
                self._write_to_file(f"Log rotated at {timestamp}\n")
                self._write_to_file(f"{'='*80}\n\n")
        except Exception as e:
            print(f"Error rotating log: {e}")

    def _is_duplicate(self, message):
        """Check if message is a recent duplicate"""
        if message in self.recent_messages:
            # Increment repeat count
            self.repeat_count[message] = self.repeat_count.get(message, 0) + 1
            return True
        else:
            # Reset repeat count and add to recent
            if message in self.repeat_count:
                count = self.repeat_count[message]
                del self.repeat_count[message]
                if count > 1:
                    # Log that we suppressed duplicates
                    summary = f"    [Previous message repeated {count} times]\n"
                    self._write_to_file(summary)

            self.recent_messages.append(message)
            return False

    def log(self, level, category, message, data=None):
        """
        Log a message with level, category, and optional data

        Args:
            level: DEBUG, INFO, WARN, ERROR
            category: TRAIN, TRACK, SWITCH, LIGHT, GATE, FAILURE, POSITION, NETWORK, etc.
            message: Human-readable message
            data: Optional dictionary of additional data
        """
        with self.lock:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

            # Format log message
            log_msg = f"{message}"

            # Check for duplicates
            if self._is_duplicate(log_msg):
                return  # Skip duplicate

            # Write to text log
            formatted_msg = f"[{timestamp}] [{level:5s}] [{category:10s}] {message}\n"
            self._write_to_file(formatted_msg)

            # Write to JSON log
            json_event = {
                "timestamp": timestamp,
                "level": level,
                "category": category,
                "message": message,
            }
            if data:
                json_event["data"] = data

            self._write_json_log(json_event)

    def debug(self, category, message, data=None):
        """Log debug message"""
        self.log("DEBUG", category, message, data)

    def info(self, category, message, data=None):
        """Log info message"""
        self.log("INFO", category, message, data)

    def warn(self, category, message, data=None):
        """Log warning message"""
        self.log("WARN", category, message, data)

    def error(self, category, message, data=None):
        """Log error message"""
        self.log("ERROR", category, message, data)

    def close(self):
        """Close logger and write final summary"""
        with self.lock:
            self._write_to_file(f"\n{'='*80}\n")
            self._write_to_file(f"Log Session Ended: {datetime.now().isoformat()}\n")
            self._write_to_file(f"{'='*80}\n")

            self.json_logs["session_end"] = datetime.now().isoformat()
            with open(self.json_log_file, "w", encoding="utf-8") as f:
                json.dump(self.json_logs, f, indent=2)


# Global logger instance
_global_logger = None


def get_logger():
    """Get or create global logger instance"""
    global _global_logger
    if _global_logger is None:
        # Use absolute path to logs directory in Track_and_Train folder
        script_dir = os.path.dirname(os.path.abspath(__file__))
        logs_dir = os.path.join(script_dir, "logs")
        _global_logger = TrainLogger(log_dir=logs_dir)
    return _global_logger


def close_logger():
    """Close global logger"""
    global _global_logger
    if _global_logger:
        _global_logger.close()
        _global_logger = None
