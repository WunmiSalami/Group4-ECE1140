# 📘 TRACK MODEL README

---

## 1. Overview

The Track Model represents the physical rail infrastructure of the train system. It maintains the complete state of all track blocks, switches, crossings, and infrastructure on both the Red and Green lines. Think of it as the "ground truth" for what's physically happening on the tracks—where trains are located, which switches are set to which positions, whether track blocks have failures, and the status of all crossing gates and traffic lights.

The Track Model acts as the passive infrastructure layer that responds to commands from Track Control and provides track state information to all other modules. It doesn't make decisions about train movement or routing—it simply maintains and reports the current physical state of the track network.

---

## 2. Purpose & Capabilities

### What can you use Track Model for?

**Track State Management:**
- Tracks the state of every block on the Red and Green lines: occupancy, failures, switch position, gate status, and traffic light state.

**Infrastructure Simulation:**
- Simulates real rail infrastructure behavior. Validates and applies switch changes, manages crossing gates, and maintains failure states.

**Data Provider:**
- Serves as the source of truth for all modules querying track state: Train Model, Track Control, and UI.

---

## 3. Inputs

### Static Track Configuration (Excel File)
- **File:** `Track Layout & Vehicle Data vF5.xlsx`
- **Sheets:** "Red Line" and "Green Line"
- **Contains:** Block numbers, lengths, speed limits, station locations, switch configs, crossings, infrastructure types, elevation, grades.
- **When loaded:** At startup, once
- **Format:** Excel spreadsheet
- **Used for:** Building the internal track network model

### Real-Time Commands (JSON File)
- **File:** `track_io.json`
- **Source:** Track Control
- **Contains:**
  - Switch positions (`G-switches` / `R-switches`)
  - Gate commands (`G-gates` / `R-gates`)
  - Traffic light states (`G-lights` / `R-lights`)
- **When read:** Continuously
- **Format:** JSON arrays
- **Used for:** Applying Track Control commands

### Train Occupancy (from Train Model via Track Control)
- **File:** `track_io.json` (G-Occupancy / R-Occupancy)
- **Contains:** Binary array for block occupancy
- **When read:** Continuously
- **Used for:** Tracking train positions

---

## 4. Outputs

### Track State (JSON File)
- **File:** `track_model_output.json` (example)
- **Contains:** State of every block, gate, light, failures, topology
- **When written:** After each update
- **Format:** JSON
- **Used by:** Track Control, UI

### Occupancy Updates (JSON File)
- **File:** `track_io.json` (G-Occupancy / R-Occupancy)
- **Contains:** Updated occupancy after train movement
- **When written:** After train moves
- **Used by:** Track Control

### Failure States (JSON File)
- **File:** `track_io.json` (G-Failures / R-Failures)
- **Contains:** Three bits per block: [power, circuit, broken rail]
- **When written:** When failures are injected/cleared
- **Used by:** Track Control, Train Model

---

## 5. How to Use - Step-by-Step Walkthrough

### Starting Up the Track Model

- On launch, Track Model reads the Excel file to learn the track layout.
- Discovers all blocks, switches, stations, crossings, and builds network topology.
- Initializes all blocks: unoccupied, no failures, switches default, gates open, lights Super Green.

### Normal Operation - Processing Commands

- Monitors `track_io.json` for commands from Track Control.
- Applies switch, gate, and light commands to infrastructure.
- Logs all changes for traceability.

### Handling Train Movement

- Receives occupancy updates from Train Model via Track Control.
- Updates block occupancy and writes new state to output files.
- May update traffic lights in response to train movement.

### Managing Crossing Gates

- Closes gates when trains approach crossings, opens after safe passage.
- Logs all gate state changes.

### Simulating Track Failures

- Maintains failure states for blocks (power, circuit, rail).
- Updates failure arrays in JSON files and logs all changes.
- Clears failures when commanded.

---

## 6. Module Interface

### Key Classes

**LineNetwork:**
- Represents a single line (Red or Green)
- Manages block connections, topology, switch logic, train positions
- Methods: `get_next_block()`, `update_block_occupancy()`, `load_branch_points_from_static()`

**DynamicBlockManager:**
- Manages state of all blocks
- Stores occupancy, failures, switch positions, gates
- Query interface for other modules
- Methods: `write_inputs()`, `get_switch_position()`, `inject_failure()`, `clear_failure()`

**LineNetworkBuilder:**
- Constructs LineNetwork from Excel
- Parses configuration, identifies switches, stations, crossings
- Used during initialization

### Main Entry Points

**Initialization:**
```python
network = LineNetwork("Green", block_manager)
network.load_all_blocks_from_static()
network.load_branch_points_from_static()
network.load_crossing_blocks_from_static()
```

**Update Cycle:**
```python
network.read_train_data_from_json()
network.write_occupancy_to_json()
network.write_failures_to_json()
```

### Called by Other Modules

**Track Control calls:**
- `network.get_station_name(block_num)`
- `network.get_next_block(train_id, current, previous)`
- `block_manager.get_switch_position(line, block)`
- `block_manager.inject_failure(line, block, failure_type)`

**Train Model calls:**
- Reads block states from Track Model outputs (via JSON)

---

## 7. Logging

### What does Track Model log?

**Initialization Logs:**
- `[NETWORK] Red Line loading branch points from static JSON`
- `[NETWORK] Green Line branch point loaded: block 77 -> [76, 101]`
- `[NETWORK] Green Line branch points loaded: 6 total`

**Switch Changes:**
- `[SWITCH] Green line block 63 switch changed to position 64`
- `[SWITCH] Green line block 77 switch: pos 0 → 1`

**Gate Operations:**
- `[GATE] Green line block 19 crossing gate: Down → Up`
- `[GATE] Green line block 19 crossing gate: Open → Closed`

**Traffic Light Changes:**
- `[LIGHT] Green line block 76 light: Super Green → Red`
- `[LIGHT] Green line block 62 traffic light: Red → Yellow`

**Block State Updates:**
- `[TRACK] Block 65 occupancy updated: false → true`
- `[TRACK] Block 88 power failure activated`
- `[TRACK] Block 88 circuit failure cleared`

**Errors and Warnings:**
- `[TRACK] Error loading crossing blocks: {error message}`
- `[TRACK] Error writing track IO data: {error message}`

### Log File Location
- **File:** `logs/track_control_YYYYMMDD_HHMMSS.log`
- **Format:** `[YYYY-MM-DD HH:MM:SS.mmm] [LEVEL] [CATEGORY] Message`

### How to Read Logs
- Search for `[SWITCH]` for switch changes
- Search for `[TRACK]` with "occupancy" for train movement
- Search for `[TRACK]` with "failure" for failure simulation

---

## 8. Dependencies

### Other Modules
- **Track Control:** Provides commands via `track_io.json`, reads track state
- **Train Model:** Provides train position updates (via Track Control)
- **UI:** Reads track state for visualization

### External Libraries
- **pandas:** For reading Excel files
- **json:** For reading/writing JSON
- **logging:** For structured log output

### File Dependencies
- **Required at startup:**
  - `Track Layout & Vehicle Data vF5.xlsx`
- **Required during operation:**
  - `track_io.json`
- **Optional:**
  - `track_model_static.json`

---

## 9. Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    TRACK MODEL MODULE                       │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  INPUT: Excel File                                          │
│  ┌─────────────────────┐                                    │
│  │ Excel Loader        │                                    │
│  │ - Read track layout │                                    │
│  │ - Parse blocks      │                                    │
│  │ - Extract switches  │                                    │
│  └──────────┬──────────┘                                    │
│             │                                               │
│             ↓                                               │
│  ┌─────────────────────┐        ┌────────────────────┐    │
│  │ LineNetworkBuilder  │───────→│  LineNetwork       │    │
│  │ - Build topology    │        │  - Red Line        │    │
│  │ - Identify branches │        │  - Green Line      │    │
│  └─────────────────────┘        │  - Block graph     │    │
│                                  │  - Switch routes   │    │
│                                  └─────────┬──────────┘    │
│                                            │               │
│  INPUT: track_io.json                      ↓               │
│  ┌─────────────────────┐        ┌────────────────────┐    │
│  │ JSON Reader         │───────→│ DynamicBlockManager│    │
│  │ - Read switches     │        │                    │    │
│  │ - Read gates        │        │ Per-Block State:   │    │
│  │ - Read lights       │        │  • Occupancy       │    │
│  │ - Read occupancy    │        │  • Switch position │    │
│  └─────────────────────┘        │  • Gate status     │    │
│                                  │  • Failures        │    │
│                                  │  • Traffic lights  │    │
│                                  └─────────┬──────────┘    │
│                                            │               │
│                                            ↓               │
│  OUTPUT: track_io.json                                     │
│  ┌─────────────────────┐        ┌────────────────────┐    │
│  │ State Writer        │←───────│ State Updater      │    │
│  │ - Write occupancy   │        │ - Apply commands   │    │
│  │ - Write failures    │        │ - Update states    │    │
│  │ - Update outputs    │        │ - Validate changes │    │
│  └─────────────────────┘        └────────────────────┘    │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**Data Flow:**
1. Excel file → LineNetworkBuilder → Creates LineNetwork topology
2. track_io.json → JSON Reader → Reads commands
3. Commands → DynamicBlockManager → Updates block states
4. Updated states → State Writer → Writes back to track_io.json

---
