# 📘 **TRAIN MANAGER MODULE**

---

## **1. Overview**

Train Manager serves as the interface layer between Track Control and Train Model, managing the lifecycle of train instances and facilitating communication between the control system and individual train simulations. It handles train creation, deletion, and state synchronization, ensuring that each train has a corresponding Train Model instance executing physics simulation and a corresponding entry in Track Control's active trains registry. Train Manager abstracts the complexity of managing multiple concurrent train simulations, providing a clean API for train operations while maintaining consistency across the system's JSON communication files.

This module operates as a coordination layer rather than implementing core functionality. Train Manager doesn't perform physics calculations or routing decisions—instead, it orchestrates the creation of Train Model instances when new trains are added, ensures proper initialization of train state in all communication files, and manages the cleanup process when trains are removed from service. Train Manager also provides utility functions for querying train status, verifying train existence, and handling edge cases like duplicate train IDs or invalid configurations.

---

## **2. Purpose & Capabilities**

### **Train Lifecycle Management**

Train Manager controls the complete lifecycle of trains from creation to deletion. When a new train is requested (typically from the UI or Track Control), Train Manager validates the request parameters (train ID, line assignment, initial position), checks for conflicts with existing trains (duplicate IDs), and coordinates the instantiation process. This involves creating a new Train Model instance with the specified parameters, initializing the train's entry in `track_model_Train_Model.json` with default state values, and notifying Track Control that a new train is available for dispatch.

The creation process ensures atomic initialization—either the train is fully created across all system components, or the creation fails cleanly without leaving partial state. Train Manager verifies that the Train Model instance starts successfully, that the JSON file entry is written correctly, and that Track Control acknowledges the new train. If any step fails, Train Manager performs rollback operations to maintain system consistency.

Deletion follows a similar coordinated approach. When a train is removed (either explicitly deleted or when it reaches a "dormant" state after completing all routes), Train Manager stops the Train Model's physics simulation thread, removes the train's entry from `track_model_Train_Model.json`, notifies Track Control to remove the train from its active trains registry, and deallocates system resources. Train Manager ensures trains cannot be deleted while actively moving or in critical states (like emergency braking), providing safety interlocks that prevent unsafe operations.

### **State Synchronization**

Train Manager maintains consistency between Train Model's internal state and the JSON representation that Track Control and other modules read. After each physics cycle in Train Model, Train Manager verifies that state updates are written to the JSON file correctly. If JSON write operations fail (due to file locks, disk errors, or corruption), Train Manager implements retry logic with exponential backoff, logging failures for debugging while preventing cascading errors.

The module also handles state recovery scenarios. If the system detects that a train's JSON entry is missing or corrupted (perhaps due to a crash or file system issue), Train Manager can reconstruct the entry from the Train Model's in-memory state. This recovery mechanism ensures that temporary file system issues don't permanently lose train state, allowing operations to continue with minimal disruption.

Train Manager monitors for state inconsistencies between different system components. For example, if Track Control believes Train 1 is at block 65 but Train Model reports block 63, Train Manager detects this mismatch and logs a warning. In severe cases (large position discrepancies that suggest data corruption), Train Manager can trigger a synchronization operation that forces all modules to re-read the authoritative state from Train Model.

### **Communication Facilitation**

Train Manager provides abstraction functions that simplify communication between Track Control and Train Model. Rather than Track Control directly manipulating JSON files, it can call Train Manager methods like `set_train_commands(train_id, speed, authority)`, which handles the JSON file access, proper indexing into command arrays, and verification that commands were written successfully. This abstraction reduces code duplication and centralizes error handling for file I/O operations.

The module also implements thread-safe access to shared JSON files. Since both Train Model (writing state) and Track Control (writing commands) may access `track_io.json` simultaneously, Train Manager provides locking mechanisms to prevent race conditions. When one module holds a write lock, other modules queue their operations, ensuring serialized access that prevents file corruption or data races.

Train Manager translates between different coordinate systems and units used by various modules. Train Model operates in SI units (meters, m/s) internally but writes position in yards to match Track Control's conventions. Train Manager handles these conversions transparently, allowing each module to work in its natural unit system while ensuring interoperability.

### **Train Query and Status Operations**

Train Manager provides a unified interface for querying train information across the system. Methods like `get_train_info(train_id)` retrieve complete train state (position, velocity, current block, motion state, passenger count) from the JSON files and return it as a structured dictionary. This allows UI components and logging systems to access train data without understanding the JSON file structure details.

The module implements filtered queries for specific use cases. `get_all_active_trains(line)` returns a list of all trains currently operating on the specified line. `get_trains_in_state(motion_state)` returns trains matching a particular motion state (e.g., all trains currently in "Dwelling" state). These query functions support Track Control's decision-making processes and UI visualization requirements.

Train Manager also provides validation functions that other modules use to verify train operations. `is_train_valid(train_id)` checks whether a train ID corresponds to an existing, properly initialized train. `can_dispatch_train(train_id)` verifies that a train is in a state where dispatch is permitted (currently "Undispatched", not in failure mode, not already active). These validation functions prevent invalid operations and provide clear error messages when operations are rejected.

### **Error Handling and Recovery**

Train Manager implements comprehensive error handling for all train operations. When Train Model encounters a physics calculation error (such as numerical overflow or invalid state transitions), Train Manager catches the exception, logs detailed diagnostics including the train's state at the time of failure, and attempts recovery. For recoverable errors (like momentary file access failures), Train Manager retries the operation. For unrecoverable errors (like corrupted train state), Train Manager can forcibly stop the affected train and mark it as requiring manual intervention.

The module maintains an error history for each train, tracking failure events with timestamps and context. This history helps diagnose recurring issues (like a train that repeatedly experiences emergency brake activations) and provides data for system reliability analysis. Train Manager can also implement failure rate limiting—if a train experiences excessive failures within a short time window, Train Manager can automatically remove the train from service to prevent system instability.

Train Manager provides graceful degradation when system resources are constrained. If memory usage becomes excessive (from too many active trains or logging), Train Manager can temporarily disable detailed logging, reduce the physics simulation rate, or refuse new train creation requests until resources are available. This prevents complete system failure due to resource exhaustion.

---

## **3. Inputs**

### **Train Creation Requests**
- **Source:** UI/GUI train creation interface, Track Control initialization
- **Contains:**
  - Train ID (integer, must be unique)
  - Line assignment ("Red" or "Green")
  - Initial block (typically 0 for yard)
  - Number of cars (affects mass calculation)
  - Initial passenger count (default 0)
- **Received:** On-demand when user creates a new train
- **Used for:** Instantiating new Train Model instances, initializing state

### **Train Deletion Requests**
- **Source:** UI/GUI train removal interface, automatic cleanup after dormant state
- **Contains:**
  - Train ID to delete
  - Force deletion flag (override safety checks)
- **Received:** When user explicitly deletes train or train reaches final destination
- **Used for:** Stopping Train Model simulation, cleaning up state

### **Train State Queries**
- **Source:** Track Control, UI, logging systems
- **Contains:**
  - Train ID or filter criteria (line, motion state)
  - Requested fields (position, velocity, full state)
- **Received:** Continuously during operation
- **Used for:** Providing train information to requesting modules

### **Command Routing Requests**
- **Source:** Track Control
- **Contains:**
  - Train ID
  - Commanded speed (mph)
  - Commanded authority (yards)
- **Received:** Every control cycle for active trains
- **Used for:** Writing commands to appropriate JSON array indices for Train Model

### **Configuration Data**
- **Source:** System configuration file or defaults
- **Contains:**
  - Maximum number of trains allowed per line
  - JSON file paths for communication
  - Physics simulation update rate
  - Logging level and preferences
  - Thread pool size for concurrent train simulations
- **Read:** At Train Manager initialization
- **Used for:** Configuring system parameters and resource limits

---

## **4. Outputs**

### **Train State Initialization (JSON)**
- **File:** `track_model_Train_Model.json`
- **Contains:** For newly created train:
  - Complete state structure with default values:
    - `motion`: {current_motion: "Undispatched", position_yds: 0.0, ...}
    - `block`: {current_block: 0, commanded_speed: 0, ...}
    - `beacon`: {speed_limit: 0, current_station: "N/A", ...}
    - `systems`: {lights: false, doors_left: false, ...}
    - `passengers`: {current_passengers: 0, total_passengers_served: 0}
    - `failures`: {brake_failure: false, signal_pickup_failure: false, ...}
- **Written:** When train is created
- **Used by:** Train Model for state initialization, Track Control for train registration

### **Command Array Updates (JSON)**
- **File:** `track_io.json`
- **Contains:**
  - Updated `G-Train` / `R-Train` command arrays:
    - `commanded speed`: Array with speed value at index corresponding to train number
    - `commanded authority`: Array with authority value at index corresponding to train number
- **Written:** When Track Control sends commands through Train Manager
- **Used by:** Train Model to read commanded values

### **Train Status Reports**
- **Format:** Python dictionary or JSON response
- **Contains:**
  - Train ID
  - Current state summary:
    - Line and current block
    - Motion state and velocity
    - Position and authority status
    - Passenger count
    - Active failures (if any)
- **Returned:** In response to query requests
- **Used by:** Calling modules (UI, Track Control) for status display

### **Operation Confirmations**
- **Format:** Boolean success/failure with error message
- **Contains:**
  - Operation result (success: True/False)
  - Error message or details (if failed)
  - Affected train ID
- **Returned:** After create/delete/command operations
- **Used by:** Calling modules to verify operations completed

### **Event Logs**
- **File:** `logs/train_manager_YYYYMMDD_HHMMSS.log`
- **Contains:**
  - Train creation/deletion events
  - State synchronization operations
  - Error conditions and recovery attempts
  - Resource utilization warnings
- **Written:** Continuously during operation
- **Used for:** Debugging, system monitoring, audit trail

---

## **5. How to Use - Step-by-Step Walkthrough**

### **System Initialization**

Train Manager initializes during system startup, preparing the infrastructure for train management operations. The module begins by loading configuration parameters from the system configuration file. These parameters include the maximum number of trains allowed per line (typically 10-20), the paths to JSON communication files (`track_io.json`, `track_model_Train_Model.json`), and resource limits like maximum memory usage and thread pool size.

Train Manager establishes connections to the JSON files, verifying they exist and are accessible. If the JSON files don't exist (fresh system startup), Train Manager creates them with initial empty structures. If the files exist but contain data from a previous session, Train Manager can optionally clear the old data or attempt to recover the previous state (useful for system restart after crashes).

The module initializes internal data structures: a registry dictionary that maps train IDs to their corresponding Train Model instances, a lock manager for thread-safe JSON file access, and an event queue for asynchronous operations. Train Manager also starts a background thread that periodically checks for orphaned state (train entries in JSON files without corresponding Train Model instances) and performs cleanup.

Train Manager registers itself with Track Control and other modules, providing callback functions they can use to request train operations. This registration establishes the communication channels used throughout system operation. Train Manager logs: `"Train Manager initialized: max_trains=20, ready for train creation"`.

### **Creating a New Train**

Train creation begins when a user clicks "Create Train" in the UI or when Track Control requests a new train instance. The request specifies the train ID (e.g., 1), line assignment ("Green"), initial block (0), and optionally the number of cars (default 4) and initial passenger count (default 0).

Train Manager first validates the request parameters. It checks whether the train ID is already in use by querying the internal train registry. If train ID 1 already exists, Train Manager rejects the request with error message: `"Train ID 1 already exists on Green Line"`. It verifies the line assignment is valid ("Red" or "Green"). It checks whether the maximum number of trains for this line has been reached. If all validations pass, Train Manager proceeds with creation.

Train Manager allocates a new Train Model instance, passing the validated parameters to the Train Model constructor: `train_model = TrainModel(train_id=1, line="Green", initial_block=0, num_cars=4)`. The Train Model initializes its physics parameters (mass = 163,600 kg for 4 empty cars, maximum power = 480 kW, brake deceleration rates) and sets initial state values (position = 0.0, velocity = 0.0, motion = "Undispatched").

Train Manager now initializes the train's entry in `track_model_Train_Model.json`. It acquires a write lock on the JSON file to prevent concurrent access conflicts. Train Manager reads the current file contents, adds a new entry with key `"G_train_1"` (for Green Line, Train 1), and populates it with the Train Model's initial state. The entry includes all state objects (motion, block, beacon, systems, passengers, failures) with their default values. Train Manager writes the updated JSON file and releases the lock.

Train Manager verifies the Train Model instance started successfully by checking that its physics simulation thread is running. It confirms the JSON entry was written correctly by re-reading the file and verifying the train's data is present and valid. If both verifications pass, Train Manager adds the train to its internal registry: `train_registry[1] = train_model`.

Train Manager notifies Track Control that a new train is available by calling Track Control's callback function or writing a notification to a shared communication channel. Track Control receives the notification and adds Train 1 to its `active_trains` dictionary with initial state "Undispatched".

Train Manager logs the successful creation: `"Train 1 created successfully on Green Line at block 0"`. The train is now ready to be dispatched by Track Control. Train Manager returns a success response to the requesting module: `{"success": True, "train_id": 1, "message": "Train created successfully"}`.

### **Routing Commands to Train Model**

When Track Control needs to send commands to a train, it calls Train Manager's command routing function rather than directly manipulating JSON files. Consider Track Control dispatching Train 1 with commanded speed 34.5 mph and authority 428 yards.

Track Control calls: `train_manager.set_train_commands(train_id=1, speed=34.5, authority=428)`. Train Manager receives this request and begins processing.

Train Manager first validates that Train 1 exists by checking the internal registry. If the train doesn't exist, Train Manager returns an error: `{"success": False, "error": "Train 1 not found"}`. Assuming the train exists, Train Manager proceeds.

Train Manager determines which array index corresponds to Train 1. For Green Line trains, the index is simply `train_id - 1` (Train 1 uses index 0, Train 2 uses index 1, etc.). For Red Line trains, a similar indexing scheme applies but in separate arrays.

Train Manager acquires a write lock on `track_io.json` to ensure exclusive access. It reads the current file contents, locates the `"G-Train"` object, and updates the command arrays: `data["G-Train"]["commanded speed"][0] = 34.5` and `data["G-Train"]["commanded authority"][0] = 428`. Train Manager writes the updated JSON file and releases the lock.

Train Manager implements retry logic in case the write operation fails (due to temporary file lock conflicts or disk errors). If the first write attempt fails, Train Manager waits 50ms and retries. It attempts up to 3 retries before declaring the operation failed. Most write operations succeed on the first attempt, but the retry logic provides resilience against transient failures.

After successfully writing the commands, Train Manager verifies them by re-reading the JSON file and confirming the values were written correctly: `assert data["G-Train"]["commanded speed"][0] == 34.5`. This verification catches rare cases where file writes appear successful but data is corrupted.

Train Manager logs the command write: `"Commands written for Train 1: speed=34.5 mph, authority=428 yds"`. It returns a success response to Track Control: `{"success": True, "train_id": 1}`. Train Model will read these commands on its next physics cycle and begin accelerating toward the commanded speed.

### **Querying Train Status**

Track Control needs to check Train 1's current status to determine if it has reached its destination. It calls Train Manager's query function: `train_info = train_manager.get_train_info(train_id=1)`.

Train Manager validates that Train 1 exists in the registry. Assuming it exists, Train Manager reads the train's state from `track_model_Train_Model.json`. It acquires a read lock on the JSON file (allowing concurrent reads but blocking writes), reads the file contents, and extracts the `"G_train_1"` entry.

Train Manager parses the JSON data into a structured dictionary, converting data types as needed (JSON strings to Python strings, JSON numbers to floats/ints). It constructs a comprehensive train information dictionary:
```python
train_info = {
    "train_id": 1,
    "line": "Green",
    "current_block": 65,
    "previous_block": 64,
    "motion_state": "Stopped",
    "position_yds": 428.72,
    "yards_into_current_block": 11.08,
    "velocity_ms": 0.0,
    "acceleration_ms2": 0.0,
    "commanded_speed_mph": 0.0,
    "commanded_authority_yds": 0.0,
    "actual_speed_mph": 0.0,
    "current_passengers": 150,
    "emergency_brake_active": False,
    "active_failures": []  # Empty list if no failures
}
```

Train Manager returns this dictionary to Track Control. Track Control uses the information to determine that Train 1 has stopped at block 65 (Glensbury station) and can proceed with the dwelling state transition.

For bulk queries, Train Manager provides functions like `get_all_trains_on_line(line="Green")`, which returns a list of train information dictionaries for all Green Line trains. This allows Track Control to efficiently check the status of all active trains without individual queries for each train.

### **Handling State Synchronization**

Train Manager continuously monitors for state consistency issues between Train Model's in-memory state and the JSON file representation. This monitoring runs in a background thread that periodically (every 1-2 seconds) performs verification checks.

The verification process reads each train's state from both the Train Model instance (via internal API calls) and the JSON file. It compares key values: current block, position, velocity, motion state. If the values match within acceptable tolerances (position within 1 yard, velocity within 0.1 m/s), the state is considered synchronized.

If Train Manager detects a mismatch—for example, Train Model reports current_block=65 but the JSON file shows current_block=63—it logs a warning: `"State mismatch detected for Train 1: Train Model block=65, JSON block=63"`. For minor discrepancies (1-2 block difference, small position errors), Train Manager triggers a synchronization operation that forces Train Model to write its current state to the JSON file, overwriting the inconsistent values.

For severe discrepancies (position differs by more than 100 yards, block differs by more than 5 blocks), Train Manager escalates the issue. It logs an error: `"Critical state inconsistency for Train 1, possible data corruption"`. It may automatically stop the train to prevent unsafe operation until the inconsistency is resolved. Train Manager notifies the operator through the UI that manual intervention is required.

Train Manager also detects orphaned state—JSON entries for trains that don't have corresponding Train Model instances. This can occur if a Train Model crashes or is improperly deleted. Train Manager's cleanup thread identifies these orphaned entries and removes them from the JSON file, logging: `"Removed orphaned state for Train 3"`.

### **Deleting a Train**

Train deletion occurs when a train reaches its final destination and enters dormant state, or when an operator explicitly requests deletion. Consider Train 1 completing its route to Castle Shannon and transitioning to dormant.

Track Control detects Train 1 is dormant and calls Train Manager's deletion function: `train_manager.delete_train(train_id=1)`. Train Manager receives the deletion request and begins the cleanup process.

Train Manager first validates that the train can be safely deleted. It checks the train's current motion state—trains actively moving cannot be deleted unless the force flag is set. For Train 1 in dormant state, deletion is permitted. If the train were still moving, Train Manager would reject the request: `{"success": False, "error": "Cannot delete Train 1: train is currently moving"}`.

Train Manager retrieves the Train Model instance from its registry: `train_model = train_registry[1]`. It calls the Train Model's shutdown method: `train_model.stop_physics_simulation()`. This method signals the physics simulation thread to terminate, waits for the thread to complete (up to 5 seconds timeout), and deallocates the Train Model's internal resources.

Train Manager removes the train's entry from `track_model_Train_Model.json`. It acquires a write lock, reads the file, deletes the `"G_train_1"` entry, writes the updated file, and releases the lock. Train Manager also clears the train's command entries in `track_io.json` by setting the corresponding array indices to zero values.

Train Manager removes the train from its internal registry: `del train_registry[1]`. It notifies Track Control that Train 1 has been deleted by calling Track Control's callback or sending a notification. Track Control removes Train 1 from its `active_trains` dictionary.

Train Manager logs the deletion: `"Train 1 deleted successfully"`. It returns a success response: `{"success": True, "train_id": 1, "message": "Train deleted"}`. The train no longer exists in the system—all state has been cleaned up, and the train ID is available for reuse if another train is created.

### **Error Recovery Example**

Train Manager's error recovery mechanisms activate when Train Model encounters issues during operation. Consider a scenario where Train 1's physics simulation throws an exception due to a calculation error (perhaps a division by zero from unexpected input values).

Train Model's physics thread catches the exception and logs: `"Physics calculation error for Train 1: division by zero"`. The exception propagates to Train Manager through an error callback mechanism. Train Manager receives the error notification with context about what operation failed.

Train Manager examines the error details. For a physics calculation error, the likely cause is corrupted state values (invalid velocity, NaN position, etc.). Train Manager logs: `"Train 1 physics error, attempting recovery"`.

Train Manager's recovery procedure begins by stopping Train 1's physics simulation to prevent further errors. It reads Train 1's state from the JSON file to determine if the file data is also corrupted. If the JSON state appears valid (position, velocity are finite numbers in reasonable ranges), Train Manager attempts to reload Train 1 by creating a fresh Train Model instance with the JSON state values. This effectively resets the Train Model's internal state to match the last known good JSON state.

If the JSON state is also corrupted (position = NaN, velocity = infinity), Train Manager cannot recover automatically. It marks Train 1 as requiring manual intervention, stops the train completely (sets commanded speed and authority to zero), and logs: `"Train 1 critical error: state corruption detected, manual intervention required"`. Train Manager notifies the operator through the UI with an alert message explaining the situation.

For recoverable errors (temporary file access failures, transient calculation errors), Train Manager implements automatic retry with exponential backoff. If an operation fails, Train Manager waits 50ms and retries. If it fails again, it waits 100ms. After 5 failed attempts with increasing delays, Train Manager declares the operation unrecoverable and alerts the operator.

Train Manager maintains an error history for each train, recording timestamps and error types. If Train 1 experiences more than 10 errors within a 60-second window, Train Manager recognizes this as a systematic failure rather than isolated incidents. It automatically removes Train 1 from service, logs: `"Train 1 removed due to excessive failures (10 errors in 60 seconds)"`, and prevents the train from being reused until the underlying issue is diagnosed.

---

## **6. Module Interface**

### **Key Classes**

**TrainManager:**
- Main coordinator class managing all train instances
- Methods:
  - `__init__(config)`: Initialize Train Manager with configuration
  - `create_train(train_id, line, initial_block, num_cars)`: Create new train
  - `delete_train(train_id, force)`: Remove train from system
  - `get_train_info(train_id)`: Query comprehensive train status
  - `get_all_trains_on_line(line)`: Get list of all trains on specified line
  - `get_trains_in_state(motion_state)`: Filter trains by motion state
  - `set_train_commands(train_id, speed, authority)`: Write commands to JSON
  - `is_train_valid(train_id)`: Check if train exists and is properly initialized
  - `can_dispatch_train(train_id)`: Verify train is dispatchable
  - `synchronize_train_state(train_id)`: Force state sync between Train Model and JSON
  - `get_train_count(line)`: Get number of active trains on line

**TrainRegistry:**
- Internal registry mapping train IDs to Train Model instances
- Data structure: Dictionary {train_id: TrainModel instance}
- Provides fast lookup for train operations
- Automatically cleaned up when trains are deleted

**JSONFileManager:**
- Handles thread-safe access to shared JSON files
- Methods:
  - `acquire_read_lock(file_path)`: Get shared read access
  - `acquire_write_lock(file_path)`: Get exclusive write access
  - `release_lock(file_path)`: Release held lock
  - `read_json(file_path)`: Read with automatic locking
  - `write_json(file_path, data)`: Write with automatic locking and retry
- Implements timeout and retry logic for lock acquisition

**StateValidator:**
- Validates train state consistency
- Methods:
  - `validate_train_state(train_state)`: Check state values are valid
  - `compare_states(state1, state2)`: Detect mismatches
  - `is_state_corrupted(train_state)`: Identify corrupted data (NaN, infinity, etc.)
- Returns validation results with specific error descriptions

### **Main Entry Points**

**Initialization:**
```python
train_manager = TrainManager(config={
    "max_trains_per_line": 20,
    "json_files": {
        "train_model": "track_model_Train_Model.json",
        "track_io": "track_io.json"
    },
    "logging_level": "INFO"
})
```

**Train Operations:**
```python
# Create train
result = train_manager.create_train(
    train_id=1,
    line="Green",
    initial_block=0,
    num_cars=4
)

# Send commands
train_manager.set_train_commands(
    train_id=1,
    speed=34.5,
    authority=428
)

# Query status
info = train_manager.get_train_info(train_id=1)

# Delete train
train_manager.delete_train(train_id=1, force=False)
```

**Bulk Operations:**
```python
# Get all Green Line trains
green_trains = train_manager.get_all_trains_on_line(line="Green")

# Find all dwelling trains
dwelling_trains = train_manager.get_trains_in_state(motion_state="Stopped")

# Get train count
count = train_manager.get_train_count(line="Green")
```

### **Called by Other Modules**

**Track Control calls:**
- `create_train()`: When operator creates new train
- `set_train_commands()`: Every control cycle for active trains
- `get_train_info()`: To check train status for state transitions
- `get_all_trains_on_line()`: To iterate over all trains in control cycle
- `can_dispatch_train()`: Before attempting dispatch

**UI calls:**
- `create_train()`: From train creation interface
- `delete_train()`: From train deletion interface
- `get_train_info()`: To display train details
- `get_all_trains_on_line()`: To populate train list views

**Train Model calls (callbacks):**
- Error notifications when physics simulation fails
- State update confirmations after writing to JSON

---

## **7. Logging**

### **Train Lifecycle Logs**

**Creation:**
- `[TRAIN_MANAGER] Train 1 creation requested: line=Green, block=0`
- `[TRAIN_MANAGER] Train 1 created successfully on Green Line at block 0`
- `[TRAIN_MANAGER] Train 1 registered in train registry`

**Deletion:**
- `[TRAIN_MANAGER] Train 1 deletion requested`
- `[TRAIN_MANAGER] Train 1 physics simulation stopped`
- `[TRAIN_MANAGER] Train 1 deleted successfully`

**Creation Failures:**
- `[TRAIN_MANAGER] Train creation failed: Train ID 1 already exists`
- `[TRAIN_MANAGER] Train creation failed: Maximum trains reached for Green Line (20)`
- `[TRAIN_MANAGER] Train creation failed: Invalid line specification 'Blue'`

### **Command Routing Logs**

**Successful Commands:**
- `[TRAIN_MANAGER] Commands written for Train 1: speed=34.5 mph, authority=428 yds`
- `[TRAIN_MANAGER] Commands updated for Train 2: speed=0.0 mph, authority=0 yds`

**Command Failures:**
- `[TRAIN_MANAGER] Command write failed for Train 1: JSON file locked (retry 1/3)`
- `[TRAIN_MANAGER] Command write failed for Train 1: Train not found`

### **State Synchronization Logs**

**Sync Operations:**
- `[TRAIN_MANAGER] State synchronization initiated for Train 1`
- `[TRAIN_MANAGER] State synchronized successfully for Train 1`

**Consistency Checks:**
- `[TRAIN_MANAGER] State mismatch detected for Train 1: Train Model block=65, JSON block=63`
- `[TRAIN_MANAGER] Critical state inconsistency for Train 1: position differs by 150 yards`

**Cleanup:**
- `[TRAIN_MANAGER] Orphaned state detected for Train 3, removing from JSON`
- `[TRAIN_MANAGER] Cleanup completed: 1 orphaned entry removed`

### **Error and Recovery Logs**

**Error Detection:**
- `[TRAIN_MANAGER] Train 1 physics error received: division by zero`
- `[TRAIN_MANAGER] Train 1 JSON write error: disk full`

**Recovery Attempts:**
- `[TRAIN_MANAGER] Train 1 recovery initiated: reloading from JSON state`
- `[TRAIN_MANAGER] Train 1 recovery successful: physics simulation restarted`
- `[TRAIN_MANAGER] Train 1 recovery failed: state corruption detected`

**Manual Intervention:**
- `[TRAIN_MANAGER] Train 1 requires manual intervention: unrecoverable state corruption`
- `[TRAIN_MANAGER] Train 1 removed from service: excessive failures (10 errors in 60s)`

### **Query Logs (Debug Level)**

**Individual Queries:**
- `[TRAIN_MANAGER] Train info requested for Train 1`
- `[TRAIN_MANAGER] Train info returned: block=65, state=Stopped, passengers=150`

**Bulk Queries:**
- `[TRAIN_MANAGER] All trains requested for Green Line: 3 trains found`
- `[TRAIN_MANAGER] Trains in state 'Dwelling': Train 1, Train 3`

### **Resource Monitoring**

**Resource Warnings:**
- `[TRAIN_MANAGER] High memory usage: 85% of limit`
- `[TRAIN_MANAGER] JSON file lock contention detected: 10 pending operations`

**Resource Limits:**
- `[TRAIN_MANAGER] Train creation rejected: system at maximum capacity`
- `[TRAIN_MANAGER] Reduced logging enabled: memory pressure detected`

### **Log File Location**
- **File:** `logs/train_manager_YYYYMMDD_HHMMSS.log`
- **Format:** `[YYYY-MM-DD HH:MM:SS.mmm] [LEVEL] [TRAIN_MANAGER] Message`
- **Rotation:** Daily rotation with 30-day retention
- **Size limit:** 100MB per log file

---

## **8. Dependencies**

### **Other Modules**

### **External Libraries**
**time:** Retry delays, timeout implementations
**logging:** Structured log output
**copy:** Deep copying train state for validation comparisons

### File Dependencies
**Required during operation:**
- track_model_Train_Model.json: Train state storage (read/write)
- track_io.json: Command storage (read/write)

**Optional:**
- train_manager_config.json: Configuration parameters (can use defaults if missing)


## 9. Architecture Diagram
```
┌────────────────────────────────────────────────────────────────┐
│                     TRAIN MANAGER MODULE                       │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  ┌──────────────────────────────────────────────────────┐    │
│  │               Train Registry                          │    │
│  │  {train_id: TrainModel instance mapping}             │    │
│  └────────────────────┬─────────────────────────────────┘    │
│                       │                                        │
│                       ↓                                        │
│  ┌──────────────────────────────────────────────────────┐    │
│  │           Train Lifecycle Manager                     │    │
│  ├──────────────────────────────────────────────────────┤    │
│  │                                                       │    │
│  │  ┌─────────────┐         ┌──────────────────────┐   │    │
│  │  │ Create      │────────→│ Initialize TrainModel│   │    │
│  │  │ Train       │         │ - Physics params     │   │    │
│  │  │ - Validate  │         │ - Start simulation   │   │    │
│  │  │ - Allocate  │         └──────────┬───────────┘   │    │
│  │  └─────────────┘                    │               │    │
│  │                                     ↓               │    │
│  │  ┌─────────────┐         ┌──────────────────────┐   │    │
│  │  │ Delete      │────────→│ Stop TrainModel      │   │    │
│  │  │ Train       │         │ - End simulation     │   │    │
│  │  │ - Validate  │         │ - Cleanup state      │   │    │
│  │  │ - Notify    │         └──────────────────────┘   │    │
│  │  └─────────────┘                                    │    │
│  │                                                       │    │
│  └───────────────────────────────────────────────────────┘    │
│                                                                │
│  ┌──────────────────────────────────────────────────────┐    │
│  │         Communication Facilitator                     │    │
│  ├──────────────────────────────────────────────────────┤    │
│  │                                                       │    │
│  │  ┌─────────────────┐      ┌──────────────────────┐  │    │
│  │  │ Command Router  │─────→│ JSON File Manager    │  │    │
│  │  │ - Speed/auth    │      │ - Thread-safe access│  │    │
│  │  │ - Array indexing│      │ - Lock management    │  │    │
│  │  └─────────────────┘      │ - Retry logic        │  │    │
│  │                            └──────────┬───────────┘  │    │
│  │  ┌─────────────────┐                 │              │    │
│  │  │ State Query     │◄────────────────┘              │    │
│  │  │ - Get info      │                                │    │
│  │  │ - List trains   │                                │    │
│  │  │ - Filter by     │                                │    │
│  │  └─────────────────┘                                │    │
│  │                                                       │    │
│  └───────────────────────────────────────────────────────┘    │
│                                                                │
│  ┌──────────────────────────────────────────────────────┐    │
│  │         State Synchronization Monitor                 │    │
│  ├──────────────────────────────────────────────────────┤    │
│  │                                                       │    │
│  │  ┌─────────────────┐      ┌──────────────────────┐  │    │
│  │  │ Consistency     │─────→│ State Validator      │  │    │
│  │  │ Checker         │      │ - Compare states     │  │    │
│  │  │ - Periodic scan │      │ - Detect corruption  │  │    │
│  │  └─────────────────┘      └──────────┬───────────┘  │    │
│  │                                       │              │    │
│  │                                       ↓              │    │
│  │  ┌─────────────────┐      ┌──────────────────────┐  │    │
│  │  │ Orphan Cleanup  │◄─────│ Recovery Handler     │  │    │
│  │  │ - Remove stale  │      │ - Sync operations    │  │    │
│  │  │ - Prune entries │      │ - Error recovery     │  │    │
│  │  └─────────────────┘      └──────────────────────┘  │    │
│  │                                                       │    │
│  └───────────────────────────────────────────────────────┘    │
│                                                                │
│  INPUT/OUTPUT: JSON Files                                     │
│  ┌────────────────────────┐   ┌────────────────────────┐    │
│  │ track_io.json          │   │track_model_Train_Model │    │
│  │ - Command arrays       │   │        .json           │    │
│  │ - Indexed by train ID  │   │ - Train state entries  │    │
│  └────────────────────────┘   └────────────────────────┘    │
│                                                                │
└────────────────────────────────────────────────────────────────┘
Data Flow:

Track Control → Command Router → JSON File Manager → track_io.json
State Query → JSON File Manager → track_model_Train_Model.json → Response
Create Train → Initialize TrainModel → JSON File Manager → Write state
Consistency Checker → State Validator → Recovery Handler (if mismatch)
Train Model error → Error callback → Recovery Handler → Sync/Stop
```