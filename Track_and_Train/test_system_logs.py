"""
System Log Testing Script
Parses log files to verify expected vs actual behavior
Reports errors and deviations from expected operation
"""

import os
import re
from datetime import datetime
from typing import List, Dict, Tuple
import json


class LogTestResult:
    """Store test results for a single test case"""

    def __init__(self, test_name: str):
        self.test_name = test_name
        self.passed = True
        self.errors = []
        self.warnings = []
        self.info = []

    def add_error(self, message: str):
        self.errors.append(message)
        self.passed = False

    def add_warning(self, message: str):
        self.warnings.append(message)

    def add_info(self, message: str):
        self.info.append(message)


class SystemLogTester:
    """Parse and validate system logs against expected behavior"""

    def __init__(self, log_directory: str = "logs"):
        self.log_directory = log_directory
        self.log_entries = []
        self.test_results = []

    def parse_log_file(self, filename: str) -> List[Dict]:
        """
        Parse log file into structured entries

        Expected log format:
        YYYY-MM-DD HH:MM:SS - MODULE - LEVEL - Message
        """
        entries = []
        log_path = os.path.join(self.log_directory, filename)

        if not os.path.exists(log_path):
            print(f"ERROR: Log file not found: {log_path}")
            return entries

        try:
            with open(log_path, "r") as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue

                    # Parse log entry
                    # Expected format: 2025-12-11 14:23:45 - TrackModel - INFO - Message
                    match = re.match(
                        r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:\.\d+)?)\s*-\s*(\w+)\s*-\s*(\w+)\s*-\s*(.*)",
                        line,
                    )

                    if match:
                        timestamp_str, module, level, message = match.groups()
                        try:
                            # Handle both formats: with and without microseconds
                            if "." in timestamp_str:
                                timestamp = datetime.strptime(
                                    timestamp_str, "%Y-%m-%d %H:%M:%S.%f"
                                )
                            else:
                                timestamp = datetime.strptime(
                                    timestamp_str, "%Y-%m-%d %H:%M:%S"
                                )
                        except ValueError:
                            timestamp = None

                        entries.append(
                            {
                                "timestamp": timestamp,
                                "module": module,
                                "level": level,
                                "message": message,
                                "line_num": line_num,
                                "raw": line,
                            }
                        )
                    else:
                        # Could be a continuation line or malformed
                        if entries:
                            # Append to previous message
                            entries[-1]["message"] += " " + line

        except Exception as e:
            print(f"ERROR: Failed to parse log file {filename}: {e}")

        return entries

    def load_all_logs(self):
        """Load all log files from logs directory"""
        if not os.path.exists(self.log_directory):
            print(f"ERROR: Log directory not found: {self.log_directory}")
            return

        log_files = [f for f in os.listdir(self.log_directory) if f.endswith(".log")]

        for log_file in sorted(log_files):
            entries = self.parse_log_file(log_file)
            self.log_entries.extend(entries)

        # Sort by timestamp
        self.log_entries.sort(
            key=lambda x: x["timestamp"] if x["timestamp"] else datetime.min
        )

        print(f"Loaded {len(self.log_entries)} log entries from {len(log_files)} files")

    def test_no_critical_errors(self) -> LogTestResult:
        """Test: System should have no ERROR or CRITICAL level logs"""
        result = LogTestResult("No Critical Errors")

        errors = [e for e in self.log_entries if e["level"] in ["ERROR", "CRITICAL"]]

        if errors:
            result.add_error(f"Found {len(errors)} ERROR/CRITICAL log entries")
            for error in errors[:5]:  # Show first 5
                result.add_error(f"  Line {error['line_num']}: {error['message']}")
            if len(errors) > 5:
                result.add_error(f"  ... and {len(errors) - 5} more errors")
        else:
            result.add_info("No ERROR or CRITICAL log entries found")

        return result

    def test_train_dispatch_sequence(self) -> LogTestResult:
        """Test: Train dispatch should follow proper sequence"""
        result = LogTestResult("Train Dispatch Sequence")

        # Expected sequence:
        # 1. Train creation
        # 2. Route calculation
        # 3. Speed/authority assignment
        # 4. Train starts moving

        dispatch_patterns = {
            "create": r"[Cc]reate.*[Tt]rain",
            "route": r"[Rr]oute|[Pp]ath|[Cc]alculate",
            "speed_auth": r"[Ss]peed.*[Aa]uthority|[Cc]ommand",
            "moving": r"[Mm]oving|[Ss]tarted|[Dd]ispatched",
        }

        train_ids = set()

        for entry in self.log_entries:
            # Extract train IDs
            train_match = re.search(r"[Tt]rain[_\s]?(\d+)", entry["message"])
            if train_match:
                train_ids.add(train_match.group(1))

        result.add_info(f"Found {len(train_ids)} unique trains in logs")

        for train_id in train_ids:
            # Check sequence for each train
            train_entries = [
                e
                for e in self.log_entries
                if f"train_{train_id}" in e["message"].lower()
                or f"train {train_id}" in e["message"].lower()
            ]

            if len(train_entries) == 0:
                result.add_warning(f"Train {train_id}: No log entries found")
                continue

            # Verify sequence
            sequence_found = []
            for pattern_name, pattern in dispatch_patterns.items():
                for entry in train_entries:
                    if re.search(pattern, entry["message"], re.IGNORECASE):
                        sequence_found.append(pattern_name)
                        break

            if "create" not in sequence_found:
                result.add_warning(f"Train {train_id}: No creation event found")

            if "moving" in sequence_found and "speed_auth" not in sequence_found:
                result.add_error(
                    f"Train {train_id}: Started moving without speed/authority"
                )

        return result

    def test_block_occupancy_consistency(self) -> LogTestResult:
        """Test: Block occupancy should be consistent (no overlaps)"""
        result = LogTestResult("Block Occupancy Consistency")

        # Track which blocks are occupied at any time
        block_occupancy = {}  # block_num: train_id

        for entry in self.log_entries:
            # Look for occupancy changes
            occupy_match = re.search(
                r"[Bb]lock[_\s]?(\d+).*[Oo]ccupied.*[Tt]rain[_\s]?(\d+)",
                entry["message"],
            )
            clear_match = re.search(
                r"[Bb]lock[_\s]?(\d+).*[Cc]leared|[Uu]noccupied", entry["message"]
            )

            if occupy_match:
                block_num = occupy_match.group(1)
                train_id = occupy_match.group(2)

                if block_num in block_occupancy:
                    result.add_error(
                        f"Block {block_num} collision: Train {train_id} entering "
                        f"while Train {block_occupancy[block_num]} still present "
                        f"(Line {entry['line_num']})"
                    )
                else:
                    block_occupancy[block_num] = train_id

            if clear_match:
                block_num = clear_match.group(1)
                if block_num in block_occupancy:
                    del block_occupancy[block_num]

        if not result.errors:
            result.add_info("No block occupancy conflicts detected")

        return result

    def test_speed_authority_limits(self) -> LogTestResult:
        """Test: Trains should not exceed speed limits or authority"""
        result = LogTestResult("Speed and Authority Limits")

        violations = []

        for entry in self.log_entries:
            # Check for speed limit violations
            speed_violation = re.search(
                r"[Ss]peed.*exceed|[Oo]verspeed|[Ss]peed.*violation",
                entry["message"],
                re.IGNORECASE,
            )

            if speed_violation:
                violations.append(
                    f"Speed violation at line {entry['line_num']}: {entry['message']}"
                )

            # Check for authority violations
            auth_violation = re.search(
                r"[Aa]uthority.*exceed|[Aa]uthority.*violation|[Bb]eyond.*authority",
                entry["message"],
                re.IGNORECASE,
            )

            if auth_violation:
                violations.append(
                    f"Authority violation at line {entry['line_num']}: {entry['message']}"
                )

        if violations:
            result.add_error(f"Found {len(violations)} speed/authority violations")
            for v in violations[:5]:
                result.add_error(f"  {v}")
            if len(violations) > 5:
                result.add_error(f"  ... and {len(violations) - 5} more violations")
        else:
            result.add_info("No speed or authority violations detected")

        return result

    def test_emergency_brake_response(self) -> LogTestResult:
        """Test: Emergency brake should trigger immediate stop"""
        result = LogTestResult("Emergency Brake Response")

        emergency_events = []

        for i, entry in enumerate(self.log_entries):
            # Find emergency brake events
            if re.search(
                r"[Ee]mergency.*[Bb]rake|[Ee]mergency.*stop", entry["message"]
            ):
                train_match = re.search(r"[Tt]rain[_\s]?(\d+)", entry["message"])
                train_id = train_match.group(1) if train_match else "Unknown"

                emergency_events.append(
                    {"train_id": train_id, "timestamp": entry["timestamp"], "index": i}
                )

        result.add_info(f"Found {len(emergency_events)} emergency brake events")

        for event in emergency_events:
            # Check next few log entries for speed = 0
            found_stop = False
            for j in range(
                event["index"] + 1, min(event["index"] + 10, len(self.log_entries))
            ):
                next_entry = self.log_entries[j]

                # Check if same train
                if event["train_id"] in next_entry["message"]:
                    if re.search(r"[Ss]peed.*0|[Ss]topped", next_entry["message"]):
                        found_stop = True
                        break

            if not found_stop:
                result.add_warning(
                    f"Train {event['train_id']}: No confirmation of stop after emergency brake"
                )

        return result

    def test_station_stop_sequence(self) -> LogTestResult:
        """Test: Trains should stop at stations and handle passengers"""
        result = LogTestResult("Station Stop Sequence")

        station_stops = []

        for entry in self.log_entries:
            # Find station arrival events
            if re.search(r"[Aa]rriv.*[Ss]tation|[Ss]tation.*[Ss]top", entry["message"]):
                train_match = re.search(r"[Tt]rain[_\s]?(\d+)", entry["message"])
                station_match = re.search(
                    r"[Ss]tation[:\s]+([A-Za-z\s]+)", entry["message"]
                )

                train_id = train_match.group(1) if train_match else "Unknown"
                station = station_match.group(1).strip() if station_match else "Unknown"

                station_stops.append(
                    {
                        "train_id": train_id,
                        "station": station,
                        "timestamp": entry["timestamp"],
                    }
                )

        result.add_info(f"Found {len(station_stops)} station stops")

        # Check for passenger boarding/disembarking events
        passenger_events = [
            e
            for e in self.log_entries
            if re.search(r"[Pp]assenger|[Bb]oard|[Dd]isembark", e["message"])
        ]

        result.add_info(f"Found {len(passenger_events)} passenger-related events")

        if len(station_stops) > 0 and len(passenger_events) == 0:
            result.add_warning(
                "Trains stopped at stations but no passenger events logged"
            )

        return result

    def run_all_tests(self):
        """Run all test cases and generate report"""
        print("\n" + "=" * 70)
        print("SYSTEM LOG TEST REPORT")
        print("=" * 70)
        print(f"Test Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Log Directory: {self.log_directory}")
        print(f"Total Log Entries: {len(self.log_entries)}")
        print("=" * 70 + "\n")

        # Run all tests
        tests = [
            self.test_no_critical_errors(),
            self.test_train_dispatch_sequence(),
            self.test_block_occupancy_consistency(),
            self.test_speed_authority_limits(),
            self.test_emergency_brake_response(),
            self.test_station_stop_sequence(),
        ]

        self.test_results = tests

        # Print results
        passed_count = sum(1 for t in tests if t.passed)
        failed_count = len(tests) - passed_count

        for test in tests:
            status = "✓ PASS" if test.passed else "✗ FAIL"
            print(f"{status} - {test.test_name}")

            # Print errors
            for error in test.errors:
                print(f"    ERROR: {error}")

            # Print warnings
            for warning in test.warnings:
                print(f"    WARNING: {warning}")

            # Print info
            if test.passed:
                for info in test.info:
                    print(f"    INFO: {info}")

            print()

        # Summary
        print("=" * 70)
        print(
            f"SUMMARY: {passed_count}/{len(tests)} tests passed, {failed_count} failed"
        )
        print("=" * 70)

        return passed_count == len(tests)

    def generate_json_report(self, output_file: str = "test_results.json"):
        """Generate JSON report of test results"""
        report = {
            "test_date": datetime.now().isoformat(),
            "log_directory": self.log_directory,
            "total_entries": len(self.log_entries),
            "tests": [],
        }

        for test in self.test_results:
            report["tests"].append(
                {
                    "name": test.test_name,
                    "passed": test.passed,
                    "errors": test.errors,
                    "warnings": test.warnings,
                    "info": test.info,
                }
            )

        with open(output_file, "w") as f:
            json.dump(report, f, indent=2)

        print(f"\nJSON report saved to: {output_file}")


def main():
    """Main entry point"""
    # Initialize tester
    tester = SystemLogTester(log_directory="logs")

    # Load logs
    print("Loading log files...")
    tester.load_all_logs()

    if len(tester.log_entries) == 0:
        print(
            "ERROR: No log entries found. Ensure logs directory exists and contains .log files"
        )
        return

    # Run tests
    all_passed = tester.run_all_tests()

    # Generate JSON report
    tester.generate_json_report()

    # Exit code
    exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
