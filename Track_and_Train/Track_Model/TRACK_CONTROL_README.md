# 📘 **TRACK CONTROL MODULE**

---

## **1. Overview**

Track Control serves as the central decision-making and coordination layer for the entire rail system. It processes train dispatch requests, calculates optimal routing paths through the network, manages switch configurations, enforces train separation rules, and coordinates all infrastructure commands. Track Control reads the current state of the track infrastructure from Track Model, determines required actions based on train positions and destinations, and writes command sequences to control switches, gates, and traffic signals.

This module operates in both manual and automatic modes. Manual mode allows operators to dispatch individual trains to specific destinations. Automatic mode runs a continuous control cycle that monitors all active trains, updates their positions, enforces safety constraints, manages station dwelling, and dynamically adjusts commands as conditions change.

---

## **2. Purpose & Capabilities**

### **Train Dispatch and Routing**

Track Control calculates complete routes from origin to destination for train dispatch operations. When a train is dispatched to a station like "Castle Shannon," Track Control determines the sequence of station blocks the train must visit: [65, 73, 77, 88, 96]. It then calculates the complete block-by-block path for each leg of the journey. For example, the leg from block 65 to block 73 expands to the path [65, 66, 67, 68, 69, 70, 71, 72, 73]. This complete path is used for switch configuration, authority calculation, and progress tracking.

The module calculates commanded speed and authority for each dispatch. Speed is determined by the travel time requirements to reach the destination on schedule. Authority (measured in yards) represents how far the train is permitted to travel, typically calculated as the distance to the next station. Track Control recalculates authority after each station stop to provide clearance to the next destination.

### **Switch Management**

Track Control manages all switch positions across the network to ensure trains follow their intended routes. Before a train reaches a switch block, Track Control analyzes which trains are approaching, determines their destinations, and sets the switch to the appropriate position. The module implements priority logic: trains closer to a switch (within 1 block) receive critical priority to prevent last-second switch changes. When multiple trains approach the same switch, the closest train's routing requirements take precedence.

Switch configuration considers the complete route topology. For Green Line switch 77, Track Control determines whether to route toward block 78 (Poplar spur for destinations like Poplar or Castle Shannon) or block 101 (main loop for destinations like Inglewood or Overbrook). The module validates switch settings against train routes and logs any deviations.

### **Train Separation Enforcement**

Track Control enforces a minimum separation of 1 empty block between trains traveling in the same direction. The separation check examines the 2 blocks ahead of each train's current position. If another train is detected within this range, Track Control immediately zeros the commanded speed and authority for the following train, bringing it to a stop. When the leading train advances and clears the separation zone, Track Control restores the stopped train's original commanded speed and authority, allowing it to resume movement.

### **Automatic State Machine Control**

Each active train operates under a state machine with five states: Undispatched, En Route, At Station, Dwelling, and Dormant. Track Control manages transitions between these states based on train position and timing. When a train reaches its next station block, it transitions to "At Station," then immediately to "Dwelling" with commanded speed and authority set to zero. After a 10-second dwell time, the train transitions back to "En Route" with new speed and authority calculated for the next leg. This cycle continues until the train reaches its final destination and enters the "Dormant" state.

### **Infrastructure Command Generation**

Track Control generates command arrays for switches, gates, and traffic lights, writing them to `track_io.json` for Track Model to execute. Switch commands are indexed by switch number (0-5 for Green Line switches at blocks 13, 28, 57, 63, 77, 86). Gate commands are indexed by crossing number (0-1 for Green Line crossings at blocks 19, 108). Traffic light commands use 2 bits per light to encode four states: Super Green (00), Green (01), Yellow (10), Red (11).

Track Control updates traffic lights based on train proximity. Blocks immediately behind an active train show Red to prevent following trains. Blocks further back show Yellow or Green. The lead train's path ahead shows Super Green. These light states provide visual indication of track availability and complement the train separation logic.

---

## **3. Inputs**

### **Track Configuration (Static JSON)**
- **File:** `Track_Model/track_model_static.json`
- **Contains:** Complete track layout including block numbers, lengths, speed limits, stations, switch configurations, crossing locations
- **Read:** At startup during initialization
- **Used for:** Route calculation, authority computation, switch topology understanding

### **Current Track State (Dynamic JSON)**
- **File:** `track_io.json`
- **Contains:** 
  - `G-Occupancy` / `R-Occupancy`: Binary arrays indicating occupied blocks
  - `G-Failures` / `R-Failures`: Failure state arrays (3 bits per block: power, circuit, broken)
  - Current switch positions
  - Current gate states
  - Current traffic light states
- **Read:** Every control cycle (continuously)
- **Used for:** Train position updates, routing decisions, failure avoidance, separation enforcement

### **Train Data (Dynamic JSON)**
- **File:** `track_model_Train_Model.json`
- **Contains:** For each train:
  - Current motion state (Moving, Stopped, Braking, Undispatched)
  - Position in yards within current block
  - Current block number
  - Commanded vs. actual speed
  - Emergency brake status
- **Read:** Every control cycle
- **Used for:** Position tracking, motion state monitoring, block transition detection

### **User Dispatch Commands**
- **Source:** GUI/Manual dispatch interface
- **Contains:**
  - Train ID
  - Destination station name
  - Line (Red or Green)
  - Requested arrival time
- **Received:** On-demand when operator dispatches a train
- **Used for:** Initiating train routes, calculating schedules

---

## **4. Outputs**

### **Train Commands (JSON)**
- **File:** `track_io.json`
- **Contains:**
  - `G-Train` / `R-Train` objects with:
    - `commanded speed`: Array of speed values (mph) indexed by train number
    - `commanded authority`: Array of authority values (yards) indexed by train number
- **Written:** Every control cycle after processing train states
- **Used by:** Train Model to control train acceleration and movement limits

### **Infrastructure Commands (JSON)**
- **File:** `track_io.json`
- **Contains:**
  - `G-switches` / `R-switches`: Array of switch positions (0 or 1) indexed by switch number
  - `G-gates` / `R-gates`: Array of gate commands (0=open, 1=closed) indexed by crossing number
  - `G-lights` / `R-lights`: Array of traffic light states (2 bits per light)
- **Written:** Every control cycle after processing train positions and routes
- **Used by:** Track Model to update infrastructure states

### **Train State Updates (JSON)**
- **File:** Internal to Track Control (active_trains dictionary)
- **Maintains:** For each active train:
  - Current state (Undispatched, En Route, At Station, Dwelling, Dormant)
  - Current block and previous block
  - Route (list of station blocks)
  - Expected path (complete block sequence)
  - Current leg index
  - Next station block
  - Dwell start time
  - Scheduled speed
  - Separation stopped flag
  - Saved commanded speed/authority (for separation recovery)
- **Updated:** Every control cycle
- **Used internally:** State machine transitions, routing decisions, separation logic

---

## **5. How to Use - Step-by-Step Walkthrough**

### **System Initialization**

Track Control begins by loading the static track configuration from `track_model_static.json`. This file contains the complete network topology for both Red and Green lines. Track Control parses block data including lengths (needed for authority calculations), speed limits (used as maximum safe speeds), station locations (route waypoints), and switch configurations (routing topology). This static data remains in memory throughout operation.

The module initializes the `active_trains` dictionary, which tracks all trains currently under Track Control's management. Initially empty, this dictionary is populated as trains are created and dispatched. Track Control also establishes connections to the dynamic JSON files (`track_io.json` and `track_model_Train_Model.json`) that provide real-time state information.

Track Control then starts the automatic control cycle thread. This background thread runs continuously, executing control logic at regular intervals (typically every 0.5-1.0 seconds). The automatic cycle handles train state transitions, position updates, separation enforcement, and command generation without requiring manual intervention.

### **Manual Train Dispatch Process**

Dispatching a train involves several coordinated steps. Consider dispatching Train 1 from the yard to Castle Shannon on the Green Line with a scheduled arrival time of 07:11.

Track Control receives the dispatch request with parameters: train_id=1, destination="Castle Shannon", line="Green", arrival_time="07:11". The module first calculates the station route by identifying all intermediate stations between the current position (yard, block 0) and the destination. For Castle Shannon, the route is [65, 73, 77, 88, 96], representing Glensbury, Dormont, Mt. Lebanon, Poplar, and Castle Shannon stations.

Track Control then calculates the complete block path for the first leg (yard to Glensbury). The path from block 0 to block 65 is [0, 63, 64, 65]. This path traverses through the yard exit (block 0), the yard exit switch (block 63), a transition block (64), and arrives at Glensbury station (block 65).

With the path determined, Track Control calculates the required speed to reach Glensbury on schedule. The calculation considers the total distance of the first leg (sum of block lengths along [0, 63, 64, 65]) and the time available until the scheduled arrival. If the scheduled arrival is 6 minutes away and the leg distance is 428 yards, the calculation yields a commanded speed of approximately 34.5 mph.

Authority is calculated as the total distance from the current position to the next station block. For the first leg, authority equals the sum of block lengths: block 0 (200 yards) + block 63 (109.36 yards) + block 64 (109.36 yards) + block 65 (218.72 yards, but only count up to the station) ≈ 428 yards. This authority value limits how far the train can travel before requiring a new authorization.

Track Control now configures switches along the planned route. For the path [0, 63, 64, 65], switch 63 (the yard exit switch) must be set to route toward block 64 (the main line). Track Control writes to the `G-switches` array in `track_io.json`, setting switch index 3 (corresponding to switch block 63) to position 1 (which routes to block 64). Track Model reads this command and physically sets the switch.

Track Control writes the train commands to `track_io.json`. In the `G-Train` object, it sets `commanded speed[0] = 34.5` and `commanded authority[0] = 428` (index 0 corresponds to Train 1). Train Model reads these commands and begins accelerating the train toward the commanded speed, respecting the authority limit.

Track Control updates the train's internal state. Train 1's state transitions from "Undispatched" to "En Route". The module records:
- `state = "En Route"`
- `route = [65, 73, 77, 88, 96]`
- `expected_path = [0, 63, 64, 65]`
- `current_leg_index = 0`
- `next_station_block = 65`
- `scheduled_speed = 34.5`
- `current_block = 0`

Track Control logs the dispatch: `"Train 1 dispatched: 34.5 mph to reach Castle Shannon by 07:11"`. The dispatch process is complete, and Train 1 begins moving under automatic control.

### **Automatic Control Cycle Operation**

The automatic control cycle executes continuously while trains are active. Each cycle performs a sequence of operations to maintain safe, coordinated train movement.

**Step 1: Read Current State**

The cycle begins by reading `track_io.json` to obtain current infrastructure states (switch positions, gate states, traffic lights) and occupancy data (which blocks contain trains). It also reads `track_model_Train_Model.json` to get each train's motion state (Moving, Stopped, Braking), current position in yards, and actual speed.

**Step 2: Update Train Positions**

Track Control matches trains to their current blocks using occupancy data. When the occupancy array shows block 63 is occupied and Train 1 was previously in block 0, Track Control detects a block transition. It updates Train 1's `current_block = 63` and `previous_block = 0`. The module logs: `"Train 1 BLOCK TRANSITION: 0 → 63"`.

Track Control verifies the train is following its expected path. If the train's actual block (63) matches the expected path [0, 63, 64, 65], the transition is valid. If the train deviates from the expected path, Track Control logs a warning: `"Train 1 DEVIATED: expected path [0, 63, 64, 65], actual block X"`.

**Step 3: Process State Machines**

Track Control evaluates each train's state machine and performs appropriate actions.

For a train in "En Route" state, Track Control checks if the current block matches the next station block. If Train 1 has reached block 65 (Glensbury), the train transitions to "At Station" state. Track Control logs: `"Train 1 arrived at Glenbury"`.

When a train enters "At Station" state, it immediately transitions to "Dwelling". Track Control sets commanded speed and authority to zero, bringing the train to a stop. It records the current time as `dwell_start_time` and sets a 10-second dwell period. The module logs: `"Train 1 DWELLING at Glenbury for 10s"`.

During "Dwelling" state, Track Control monitors elapsed time. When 10 seconds have passed, the train transitions back to "En Route". Track Control calculates the path for the next leg (Glensbury to Dormont, blocks 65 to 73), computes new speed and authority values, and writes updated commands. It logs: `"Train 1 RESUMING after dwell: speed=34.5 mph, authority=1202 yds"`.

**Step 4: Enforce Train Separation**

For each train in "En Route" state, Track Control examines the 2 blocks ahead along the train's expected path. If Train 2 is in block 63 and its expected path is [63, 64, 65, ...], Track Control checks blocks 64 and 65 for other trains.

If Train 1 is detected in block 65 (within 2 blocks ahead), Track Control immediately stops Train 2. It saves the current commanded speed and authority values (`saved_commanded_speed = 22.4`, `saved_commanded_authority = 428`), then zeros the active commands (`commanded_speed = 0`, `commanded_authority = 0`). It sets a flag `separation_stopped = True` and logs: `"Train 2 STOPPED: Train 1 too close at block 65"`.

On subsequent cycles, Track Control continues checking separation. When Train 1 advances beyond block 66 (clearing the 2-block zone ahead of Train 2), Track Control detects the separation has cleared. It restores Train 2's saved commands (`commanded_speed = 22.4`, `commanded_authority = 428`), clears the `separation_stopped` flag, and logs: `"Train 2 RESUMING: path clear, restored speed=22.4 mph, authority=428 yds"`.

**Step 5: Configure Switches**

Track Control scans all switch blocks to determine if any trains are approaching. For each switch, it identifies trains within 5 blocks whose expected paths include that switch. Among these trains, the closest train's routing requirements determine the switch position.

If Train 1 is 3 blocks from switch 77 and Train 2 is 5 blocks from switch 77, Train 1 takes priority. Track Control examines Train 1's destination (Castle Shannon). Since Castle Shannon requires the Poplar spur, Track Control sets switch 77 to position 0 (routing toward block 78). The module writes to `G-switches` array and logs: `"Green line block 77 switch: pos 0 → 0 (Poplar spur for Train 1)"`.

**Step 6: Update Traffic Lights**

Track Control sets traffic lights based on train positions and separation zones. Blocks occupied by trains show Red. Blocks 1-2 positions behind trains show Yellow. Blocks 3+ positions behind show Green. Blocks ahead of trains (in their direction of travel) show Super Green.

If Train 1 occupies block 76, Track Control sets block 76's traffic light to Red, blocks 74-75 to Yellow, and blocks 73 and earlier to Green. Blocks 77+ ahead of Train 1 show Super Green. These light states are written to the `G-lights` array in `track_io.json`.

**Step 7: Write Commands**

Track Control writes all updated commands to `track_io.json`. The `G-Train` object receives updated commanded speed and authority arrays. The `G-switches`, `G-gates`, and `G-lights` arrays receive updated infrastructure commands. Train Model reads these commands and executes the corresponding actions (train acceleration, switch movements, light changes).

**Step 8: Repeat**

The automatic control cycle sleeps briefly (typically 0.5-1.0 seconds), then repeats from Step 1. This continuous loop maintains real-time control over all active trains and infrastructure.

### **Handling Multiple Trains**

When multiple trains operate simultaneously, Track Control manages their interactions through separation enforcement and switch arbitration.

Consider two trains: Train 1 is en route to Castle Shannon (Poplar spur) and Train 2 is en route to Inglewood (main loop). Both trains must pass through switch 77, but they require different switch positions.

Track Control monitors both trains' positions relative to switch 77. When Train 1 is 2 blocks away and Train 2 is 6 blocks away, Train 1 receives priority. Track Control sets switch 77 to position 0 (Poplar spur) to accommodate Train 1's route. The module logs: `"Green line block 77 switch set for Train 1 (2 blocks away)"`.

As Train 1 passes through switch 77 and continues toward the Poplar spur, Train 2 advances closer to the switch (now 3 blocks away). Once Train 1 has cleared the switch area, Track Control recalculates switch priority. Train 2 now has priority, and Track Control sets switch 77 to position 1 (main loop). The module logs: `"Green line block 77 switch set for Train 2 (3 blocks away)"`.

If Train 2 were to catch up to Train 1 before Train 1 reaches the switch, separation enforcement would stop Train 2. Track Control would detect Train 1 within 2 blocks ahead of Train 2 and zero Train 2's commands until separation is restored.

---

## **6. Module Interface**

### **Key Classes**

**TrackControl:**
- Main control class managing all trains and infrastructure
- Methods:
  - `dispatch_train(train_id, destination, line, arrival_time)`: Initiate train dispatch
  - `_automatic_control_cycle()`: Main control loop (runs in background thread)
  - `_update_train_positions(line_trains, occupancy, line)`: Detect block transitions
  - `_handle_state_machines(line_trains, line)`: Process train state transitions
  - `_check_train_separation(train_id, train_info, line, occupancy)`: Enforce separation
  - `_set_switches_for_approaching_trains(line, line_trains)`: Configure switch positions
  - `_calculate_route(origin, destination, line)`: Determine station route
  - `_calculate_complete_block_path(start, end, line)`: Expand to full block path
  - `_write_train_commands()`: Write speed/authority to track_io.json

**Route Calculation:**
- `_calculate_route()`: Returns list of station blocks from origin to destination
- `_calculate_complete_block_path()`: Returns list of all blocks between two points
- Uses Dijkstra's algorithm to find shortest path through network graph

**Switch Management:**
- `_determine_green_switch_position()`: Determine Green Line switch settings based on destination
- `_determine_red_switch_position()`: Determine Red Line switch settings based on destination
- Implements priority logic for multiple approaching trains

### **Main Entry Points**

**Initialization:**
```python
track_control = TrackControl()
track_control.start_automatic_control()  # Begin background control cycle
```

**Train Dispatch:**
```python
track_control.dispatch_train(
    train_id=1,
    destination="Castle Shannon",
    line="Green",
    arrival_time="07:05"
)
```

**Emergency Stop (if needed):**
```python
track_control.emergency_stop_train(train_id=1)
```

### **Called by Other Modules**

**UI/GUI calls:**
- `dispatch_train()`: When operator dispatches a train
- `get_active_trains()`: To display current train status
- `get_train_info(train_id)`: To show specific train details

**Internal calls (from automatic cycle):**
- Reads Track Model state via `track_io.json`
- Writes commands to Train Model via `track_io.json`
- Updates internal train state dictionary

---

## **7. Logging**

### **Dispatch and Routing Logs**

**Route Calculation:**
- `[ROUTE] Train 1 route to Castle Shannon: [65, 73, 77, 88, 96], first station block: 65`
- `[PATH] Calculating path from 65 to 73`
- `[ROUTE_PATH] Leg 2: 65 → 73 for Train 1 (Line: Green): [65, 66, 67, 68, 69, 70, 71, 72, 73]`

**Dispatch Actions:**
- `[TRAIN] Manual dispatch: Train 1 to Castle Shannon on Green Line, arrival 07:05`
- `[AUTHORITY] Train 1 INITIAL DISPATCH: speed=34.53 mph, authority=428 yds`
- `[TRAIN] Train 1 dispatched: 34.5 mph to reach Castle Shannon by 07:05`
- `[DISPATCH] Train 1 expected path: 0→65 (4 blocks)`

### **Position and Movement Logs**

**Block Transitions:**
- `[TRAIN] Train 1 BLOCK TRANSITION: 0 → 63`
- `[TRAIN] Train 2 BLOCK TRANSITION: 63 → 64`

**Arrival and Dwelling:**
- `[ARRIVAL] Train 1 arrived at destination block 65`
- `[TRAIN] Train 1 arrived at Glenbury`
- `[TRAIN] Train 1 DWELLING at Glenbury for 10s`
- `[TRAIN] Train 1 RESUMING after dwell: speed=34.53 mph, authority=1202 yds`

**Route Deviations:**
- `[ROUTING] Train 1 DEVIATED: expected path [77, 101, 102, 103, 104, 105], actual block 78`

### **Separation and Safety Logs**

**Separation Enforcement:**
- `[SEPARATION] Train 2 STOPPED: Train 1 too close at block 65`
- `[SEPARATION] Train 2 RESUMING: path clear, restored speed=22.4 mph, authority=428 yds`
- `[SEPARATION] Train 2 clear: No trains within 2 blocks ahead`

**Traffic Lights:**
- `[TRAFFIC_LIGHT] Train 2: Yellow light ahead at block 76`
- `[TRAFFIC_LIGHT] Train 2 clear: No red lights within 3 blocks ahead`

### **Switch and Infrastructure Logs**

**Switch Operations:**
- `[SWITCH] Green line block 63 switch: pos 0 → 1 (Yard exit for Train 1)`
- `[SWITCH] Green line block 77 switch set for Train 1 (2 blocks away)`
- `[SWITCH] Green line block 63 switch changed to position 64`

**Light Changes:**
- `[LIGHT] Green line block 76 light: Super Green → Red`
- `[LIGHT] Green line block 62 light: Red → Yellow`

### **Command Writing:**
- `[TRAIN] Train 1 commands written: speed=34.53 mph, authority=428 yds`
- `[TRAIN] Train 1 commands written to JSON: speed=34.53 mph, authority=428.00 yds`

### **Errors and Warnings**

**Position Warnings:**
- `[POSITION] Train 2 has no matching occupied block`

**Threading Errors:**
- `[THREADING] Exception in background control cycle: {error message}`

**Data Errors:**
- `[ERROR] Failed to read track state: {error message}`

### **Log File Location**
- **File:** `logs/track_control_YYYYMMDD_HHMMSS.log`
- **Format:** `[YYYY-MM-DD HH:MM:SS.mmm] [LEVEL] [CATEGORY] Message`
- **Includes:** Context dictionaries with detailed parameters for debugging

---

## **8. Dependencies**

### **Other Modules**
- **Track Model:** Provides track state via `track_io.json`, executes infrastructure commands
- **Train Model:** Provides train motion/position via `track_model_Train_Model.json`, executes movement commands
- **Line Network:** Used for routing calculations and switch topology understanding

### **External Libraries**
- **json:** Reading/writing JSON communication files
- **threading:** Background automatic control cycle
- **time:** Timing for dwell periods, control cycle delays
- **datetime:** Scheduling and arrival time calculations
- **logging:** Structured log output

### **File Dependencies**

**Required at startup:**
- `Track_Model/track_model_static.json`: Static track configuration

**Required during operation:**
- `track_io.json`: Bidirectional command/state communication
- `track_model_Train_Model.json`: Train state information

**Written during operation:**
- `track_io.json`: Updated with train commands and infrastructure settings
- `logs/track_control_YYYYMMDD_HHMMSS.log`: Operational logs

---

## **9. Architecture Diagram**
```
┌──────────────────────────────────────────────────────────────────┐
│                      TRACK CONTROL MODULE                        │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  INPUT: Static Track Data                                       │
│  ┌────────────────────────┐                                     │
│  │ Configuration Loader   │                                     │
│  │ - track_model_static   │                                     │
│  │ - Block topology       │                                     │
│  │ - Station locations    │                                     │
│  └───────────┬────────────┘                                     │
│              │                                                   │
│              ↓                                                   │
│  ┌────────────────────────┐         ┌─────────────────────┐    │
│  │ Route Calculator       │────────→│ Path Planner        │    │
│  │ - Station routing      │         │ - Dijkstra algorithm│    │
│  │ - Leg expansion        │         │ - Complete paths    │    │
│  └────────────────────────┘         └─────────────────────┘    │
│                                                                  │
│  INPUT: Real-Time State (track_io.json, Train_Model.json)       │
│  ┌────────────────────────┐                                     │
│  │ State Reader           │                                     │
│  │ - Occupancy data       │                                     │
│  │ - Train positions      │                                     │
│  │ - Switch states        │                                     │
│  │ - Failure states       │                                     │
│  └───────────┬────────────┘                                     │
│              │                                                   │
│              ↓                                                   │
│  ┌────────────────────────────────────────────────────────┐    │
│  │         Automatic Control Cycle (Background Thread)    │    │
│  ├────────────────────────────────────────────────────────┤    │
│  │                                                        │    │
│  │  ┌──────────────────┐      ┌──────────────────────┐  │    │
│  │  │ Position Tracker │─────→│ Train State Machine │  │    │
│  │  │ - Block updates  │      │ - Undispatched      │  │    │
│  │  │ - Transitions    │      │ - En Route          │  │    │
│  │  └──────────────────┘      │ - At Station        │  │    │
│  │                             │ - Dwelling          │  │    │
│  │                             │ - Dormant           │  │    │
│  │                             └──────────┬───────────┘  │    │
│  │                                        │              │    │
│  │  ┌──────────────────┐      ┌──────────▼───────────┐  │    │
│  │  │ Separation Logic │◄─────│ Command Calculator   │  │    │
│  │  │ - 2-block ahead  │      │ - Speed calculation  │  │    │
│  │  │ - Save/restore   │      │ - Authority calc     │  │    │
│  │  └──────────────────┘      └──────────┬───────────┘  │    │
│  │                                        │              │    │
│  │  ┌──────────────────┐      ┌──────────▼───────────┐  │    │
│  │  │ Switch Manager   │◄─────│ Light Controller     │  │    │
│  │  │ - Priority logic │      │ - Red behind trains  │  │    │
│  │  │ - Route config   │      │ - Super Green ahead  │  │    │
│  │  └──────────────────┘      └──────────────────────┘  │    │
│  │                                                        │    │
│  └────────────────────────────────────────────────────────┘    │
│                              │                                  │
│                              ↓                                  │
│  OUTPUT: Commands (track_io.json)                               │
│  ┌────────────────────────┐                                     │
│  │ Command Writer         │                                     │
│  │ - Train speed/authority│                                     │
│  │ - Switch positions     │                                     │
│  │ - Gate commands        │                                     │
│  │ - Traffic lights       │                                     │
│  └────────────────────────┘                                     │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

**Control Flow:**
1. Configuration Loader → Route Calculator → Path Planner (startup)
2. State Reader → Position Tracker → State Machine (every cycle)
3. State Machine → Command Calculator → Separation Logic (every cycle)
4. Switch Manager + Light Controller → Command Writer (every cycle)
5. Command Writer → track_io.json → Track Model + Train Model