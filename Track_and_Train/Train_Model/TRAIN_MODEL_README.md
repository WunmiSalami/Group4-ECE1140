```markdown
# 📘 **TRAIN MODEL MODULE**

---

## **1. Overview**

Train Model simulates the physical behavior and dynamics of individual trains operating on the rail network. It implements realistic physics for acceleration, braking, velocity, and position tracking based on commanded inputs from Track Control. Train Model receives commanded speed and authority values, calculates the train's motion using kinematic equations that account for mass, friction, and grade, and continuously updates the train's position along the track. The module enforces physical constraints such as maximum acceleration rates, emergency braking capabilities, and authority limits that prevent trains from exceeding their permitted travel distance.

Train Model operates independently for each train instance, maintaining separate state for motion parameters, position tracking, and failure conditions. It reads beacon data from Track Model to obtain current block information (speed limits, station locations, side door configuration), processes passenger boarding events at stations, and reports all state changes back through JSON interfaces for Track Control coordination and UI visualization.

---

## **2. Purpose & Capabilities**

### **Physics Simulation**

Train Model implements a complete physics engine that calculates train motion based on fundamental kinematic principles. The simulation accounts for the train's mass (approximately 40,900 kg per car), applies forces including motor power and friction, and integrates acceleration to determine velocity changes over time. The physics loop executes at regular intervals (typically 100ms), computing the train's acceleration based on the difference between commanded speed and current speed, then updating velocity and position accordingly.

The module handles multiple motion states: Moving (actively accelerating or maintaining speed), Braking (decelerating toward zero or lower speed), Stopped (velocity = 0), and Undispatched (not yet active). Grade compensation adjusts acceleration calculations when trains traverse inclined or declined track sections. For example, a train climbing a 2% grade experiences additional gravitational resistance that reduces effective acceleration, while a train descending benefits from gravitational assistance.

Emergency braking receives special treatment. When the emergency brake is activated (either by the operator or automatically due to failures), Train Model applies maximum deceleration of -1.2 m/s² regardless of commanded speed. The train continues decelerating until velocity reaches zero, at which point the motion state transitions to Stopped. Emergency braking takes precedence over all other commands and cannot be overridden until the emergency condition is cleared.

### **Position Tracking**

Train Model maintains precise position information for each train using a dual-coordinate system. The absolute position measures total distance traveled in yards from the initial dispatch point. The relative position tracks yards traveled within the current block, resetting to zero each time the train enters a new block. This dual tracking enables accurate block transition detection and authority enforcement.

Position updates occur every physics cycle by integrating velocity over the timestep. If a train travels at 40 mph (58.67 ft/s or 19.56 yards/s) for 0.1 seconds, the position advances by approximately 1.956 yards. Train Model accumulates these incremental position changes, maintaining sub-yard precision to ensure smooth motion and accurate station stopping.

The module detects block boundaries by comparing the relative position (yards into current block) against the block's total length. When the relative position exceeds the block length, Train Model recognizes a block transition has occurred. It carries forward any overflow distance (the amount by which position exceeded the block length) into the next block's relative position, ensuring continuous motion without position jumps. Block transition information is written to the train state JSON, allowing Track Control and Line Network to update routing and occupancy.

### **Authority Enforcement**

Authority represents the distance (in yards) a train is permitted to travel from its current position. Train Model strictly enforces this limit to prevent trains from exceeding their cleared path. The module continuously compares the train's absolute position against the initial position plus authority. As the train approaches the authority limit (within approximately 50 yards), Train Model begins automatic braking to ensure the train stops before violating the boundary.

Authority enforcement operates independently of commanded speed. Even if Track Control commands a high speed, Train Model will brake the train if approaching the authority limit. When a train stops due to authority exhaustion, the motion state transitions to Stopped and velocity reduces to zero. The train remains stopped until Track Control issues a new authority value, which typically occurs after station dwelling or when separation clears.

When Track Control updates authority (such as after a station stop), Train Model preserves the train's current position within the block. The new authority value establishes a fresh travel limit from the current position. For example, if a train stops at block 65 after traveling 11.08 yards into the block, and Track Control issues a new authority of 1202 yards, the train can now travel an additional 1202 yards from its current position at 11.08 yards into block 65.

### **Beacon Data Processing**

Beacons provide trains with critical information about the track ahead as they enter new blocks. Train Model reads beacon data from the train state JSON file, which is populated by Line Network when block transitions occur. Beacon data includes the current block's speed limit (maximum safe speed in km/hr), the side door configuration for the next station (Left, Right, or N/A), the current station name (if at a station block), the next station name along the route, and the number of passengers waiting to board.

When a train enters a station block (indicated by beacon data showing a station name), Train Model processes the passenger boarding event. It reads the `passengers_boarding` value from the beacon and adds this to the train's total passenger count. The module calculates the additional mass from passengers (assuming approximately 75 kg per passenger) and updates the train's total mass accordingly. This mass change affects subsequent acceleration calculations, making heavily loaded trains accelerate more slowly than empty trains.

Speed limit enforcement uses beacon data to ensure trains do not exceed safe speeds for each block. If the beacon indicates a speed limit of 40 km/hr (approximately 24.85 mph) and the commanded speed is 30 mph, Train Model limits the train's velocity to 24.85 mph. This override prevents Track Control commands from causing unsafe speeds due to track conditions, tight curves, or station approach zones.

### **Failure Mode Handling**

Train Model responds to three categories of failures: train-level failures (brake failure, signal pickup failure, engine failure) and track-level failures (power failure, circuit failure, broken rail). When any failure is active, Train Model takes immediate protective action.

Brake failure disables the train's normal braking system, leaving only the emergency brake operational. If brake failure occurs while the train is moving, Train Model automatically activates the emergency brake to bring the train to a controlled stop using the independent emergency braking system.

Signal pickup failure prevents the train from receiving commanded speed and authority values from Track Control. Train Model treats this as a loss of control communication and immediately activates the emergency brake. The train decelerates to a stop and remains stopped until the signal pickup failure is cleared and valid commands are restored.

Engine failure removes the train's ability to accelerate. If engine failure occurs, Train Model sets commanded speed to zero and allows the train to coast to a stop through friction and any grade effects. The emergency brake is not automatically applied for engine failure, as the failure itself does not represent an immediate safety threat (unlike brake or signal failures).

Power failure at the track level (reported through beacon data or failure arrays) also triggers protective action. Train Model detects power failures in the current block and automatically stops the train, as electric trains cannot operate without track power. Circuit failure indicates a problem with the track's train detection system, which may affect signaling and routing. Train Model continues to operate but logs the circuit failure condition. Broken rail represents a severe track condition that could cause derailment. Train Model immediately activates the emergency brake and brings the train to a stop when entering a block with broken rail.

---

## **3. Inputs**

### **Train Commands (JSON)**
- **File:** `track_io.json`
- **Contains:**
  - `G-Train` / `R-Train` objects with:
    - `commanded speed`: Speed value in mph for this train (indexed by train number)
    - `commanded authority`: Authority value in yards for this train (indexed by train number)
- **Read:** Every physics cycle (typically every 100ms)
- **Used for:** Target speed for acceleration/braking calculations, travel distance limit enforcement

### **Beacon Data (JSON)**
- **File:** `track_model_Train_Model.json`
- **Contains:** For each train:
  - `beacon` object with:
    - `speed limit`: Maximum safe speed for current block (km/hr)
    - `side_door`: Door side for next station (Left, Right, N/A)
    - `current station`: Name of station at current block (or N/A)
    - `next station`: Name of next station along route
    - `passengers_boarding`: Number of passengers boarding at current station
- **Read:** When entering new blocks (block transitions)
- **Used for:** Speed limit enforcement, passenger loading, station information display, door control

### **Track Failures (JSON)**
- **File:** `track_io.json`
- **Contains:**
  - `G-Failures` / `R-Failures`: Array with 3 bits per block:
    - Bit 0: Power failure (1 = failure, 0 = normal)
    - Bit 1: Circuit failure (1 = failure, 0 = normal)
    - Bit 2: Broken rail (1 = failure, 0 = normal)
- **Read:** Every physics cycle
- **Used for:** Detecting track failures in current block, triggering emergency stops

### **Train Failures (Internal State)**
- **Source:** Failure injection interface or GUI commands
- **Contains:**
  - Brake failure flag (boolean)
  - Signal pickup failure flag (boolean)
  - Engine failure flag (boolean)
- **Set:** When failures are injected for testing or simulation
- **Used for:** Simulating train system failures, triggering protective responses

### **Initial Train Configuration**
- **Source:** Train creation command from Track Control
- **Contains:**
  - Train ID
  - Line assignment (Red or Green)
  - Initial position (typically yard, block 0)
  - Train mass (base mass + number of cars)
  - Maximum power output
  - Maximum service brake deceleration
  - Emergency brake deceleration
- **Received:** Once at train creation
- **Used for:** Initializing physics parameters, setting up train instance

---

## **4. Outputs**

### **Train Motion State (JSON)**
- **File:** `track_model_Train_Model.json`
- **Contains:** For each train:
  - `motion` object with:
    - `current motion`: Motion state (Moving, Stopped, Braking, Undispatched)
    - `position_yds`: Absolute position in yards from dispatch point
    - `yards_into_current_block`: Relative position within current block
    - `velocity`: Current speed in m/s
    - `acceleration`: Current acceleration in m/s²
- **Written:** Every physics cycle after motion calculations
- **Used by:** Track Control for position tracking, Line Network for block transitions, UI for visualization

### **Train Block Information (JSON)**
- **File:** `track_model_Train_Model.json`
- **Contains:** For each train:
  - `block` object with:
    - `current block`: Block number where train is currently located
    - `commanded speed`: Last commanded speed received (mph)
    - `commanded authority`: Last commanded authority received (yards)
    - `actual speed`: Train's actual current speed (mph)
- **Written:** Every physics cycle
- **Used by:** Track Control for state monitoring, UI for displaying train status

### **Train Systems State (JSON)**
- **File:** `track_model_Train_Model.json`
- **Contains:** For each train:
  - `systems` object with:
    - `lights`: Interior and exterior light states (boolean)
    - `doors_left`: Left doors open status (boolean)
    - `doors_right`: Right doors open status (boolean)
    - `temperature`: Cabin temperature (°C)
    - `emergency_brake`: Emergency brake activated status (boolean)
- **Written:** When system states change (doors, lights, temperature, brake)
- **Used by:** UI for system status display, Track Control for emergency brake detection

### **Passenger Information (JSON)**
- **File:** `track_model_Train_Model.json`
- **Contains:** For each train:
  - `passengers` object with:
    - `current_passengers`: Number of passengers currently on train
    - `total_passengers_served`: Cumulative count of all passengers who have boarded
- **Written:** After passenger boarding events at stations
- **Used by:** UI for passenger count display, system analytics

### **Failure States (JSON)**
- **File:** `track_model_Train_Model.json`
- **Contains:** For each train:
  - `failures` object with:
    - `brake_failure`: Brake system failure status (boolean)
    - `signal_pickup_failure`: Signal reception failure status (boolean)
    - `engine_failure`: Engine system failure status (boolean)
- **Written:** When failures are injected or cleared
- **Used by:** Track Control for operational decisions, UI for failure indication

---

## **5. How to Use - Step-by-Step Walkthrough**

### **Train Creation and Initialization**

Train Model begins with train creation, typically initiated by Track Control when a new train is added to the system. The creation process specifies the train's ID, line assignment (Red or Green), and initial position (usually block 0, the yard). Train Model allocates a new train instance and initializes all state variables.

The physics parameters are set based on the train configuration. A standard train consists of multiple cars, each with a base mass of approximately 40,900 kg. For a 4-car train, the empty mass totals 163,600 kg. Train Model sets the maximum power output (typically 480 kW for the combined consist), maximum service brake deceleration (-1.2 m/s²), and emergency brake deceleration (-2.73 m/s²). These parameters remain constant throughout the train's operation, though the effective mass increases as passengers board.

Initial state values are established: `current_block = 0`, `position_yds = 0.0`, `velocity = 0.0`, `acceleration = 0.0`, `current_motion = "Undispatched"`. The train is now ready to receive dispatch commands from Track Control. Train Model writes this initial state to `track_model_Train_Model.json`, creating the train's entry in the JSON file with all state fields populated.

### **Receiving Dispatch Commands**

When Track Control dispatches the train, it writes commanded speed and authority values to `track_io.json`. For example, dispatching Train 1 to Glensbury might set `commanded_speed[0] = 34.5` mph and `commanded_authority[0] = 428` yards. Train Model's physics loop detects these new command values on its next cycle.

Train Model reads the commands from the JSON file and updates its internal target values. The `commanded_speed` becomes the target velocity the train will accelerate toward. The `commanded_authority` establishes the position limit: the train cannot travel beyond `current_position + 428` yards. Train Model logs the command receipt: `"Position preserved on new authority: 428 yds (yards_in_block: 0.00)"`.

The motion state transitions from "Undispatched" to "Moving". Train Model now begins executing the physics simulation to accelerate the train from rest toward the commanded speed of 34.5 mph (15.43 m/s). The train's position tracking initializes with `yards_into_current_block = 0.0`, ready to track motion through block 0.

### **Physics Simulation Loop**

The physics loop executes continuously at 10 Hz (every 100ms). Each iteration performs a sequence of calculations to update the train's motion state.

**Step 1: Read Current Commands**

Train Model reads the latest `commanded_speed` and `commanded_authority` values from `track_io.json`. These values may have been updated by Track Control based on changing conditions (separation, failures, new authority after station stops). Train Model also checks for any failure conditions, both train-level failures from its internal state and track-level failures from the failures array.

**Step 2: Calculate Target Acceleration**

Train Model computes the required acceleration to reach the commanded speed. The calculation uses a proportional control law: `acceleration = K * (commanded_speed - current_velocity)`, where K is a gain constant that determines how aggressively the train accelerates. A typical value of K = 0.5 provides smooth acceleration without overshooting the target speed.

If the commanded speed is 15.43 m/s and the current velocity is 5.0 m/s, the velocity error is 10.43 m/s. With K = 0.5, the target acceleration is 5.22 m/s². However, Train Model limits this acceleration to the maximum allowed by the train's power and mass. For a 163,600 kg train with 480 kW power, the maximum acceleration is approximately 2.93 m/s² on level track. Train Model clamps the calculated acceleration to this maximum.

**Step 3: Apply Grade Compensation**

Train Model reads the current block's grade from the track configuration. If the train is on a 2% incline, gravity produces a component opposing motion: `a_gravity = -g * sin(grade) = -9.81 * sin(atan(0.02)) ≈ -0.196 m/s²`. This gravitational acceleration is subtracted from the motor acceleration: `effective_acceleration = motor_acceleration + gravity_acceleration = 2.93 - 0.196 = 2.73 m/s²`.

Conversely, on a 2% decline, gravity assists motion: `a_gravity = +0.196 m/s²`, yielding `effective_acceleration = 2.93 + 0.196 = 3.13 m/s²`. Train Model applies this grade-compensated acceleration to the velocity update.

**Step 4: Update Velocity**

Train Model integrates acceleration over the timestep to update velocity: `new_velocity = current_velocity + acceleration * timestep`. With an effective acceleration of 2.73 m/s² over 0.1 seconds, velocity increases by 0.273 m/s. If the current velocity was 5.0 m/s, the new velocity becomes 5.273 m/s.

Train Model enforces several velocity constraints. Velocity cannot exceed the commanded speed (the train doesn't overshoot the target). Velocity cannot exceed the beacon speed limit for the current block. Velocity cannot be negative (trains don't reverse). If any constraint is violated, Train Model clamps the velocity to the permitted range.

**Step 5: Check Authority Limit**

Train Model calculates the remaining authority: `remaining_authority = (initial_position + commanded_authority) - current_position`. If the train started at position 0 with authority 428 yards and has traveled to position 200 yards, remaining authority is 428 - 200 = 228 yards.

When remaining authority drops below approximately 50 yards, Train Model initiates automatic braking regardless of commanded speed. The train begins decelerating at the service brake rate (-1.2 m/s²) to ensure it stops before violating the authority limit. If remaining authority reaches zero, Train Model forces velocity to zero and transitions the motion state to "Stopped", logging: `"Train stopped: authority exhausted"`.

**Step 6: Update Position**

Train Model integrates velocity over the timestep to update position: `new_position = current_position + velocity * timestep`. If velocity is 5.273 m/s and the timestep is 0.1 seconds, position advances by 0.527 meters (0.576 yards). The absolute position increases from 200.0 to 200.576 yards, and the relative position (yards into current block) increases by the same amount.

**Step 7: Check Block Boundaries**

Train Model compares the relative position against the current block's length. If the train is in block 63 (length 109.36 yards) and the relative position reaches 115.5 yards, the train has exceeded the block boundary by 6.14 yards. Train Model detects this overflow, logs: `"Train 1 Block 63: ADVANCING to next block (traveled 115.5/109.36 yds)"`, and prepares for block transition.

Train Model reads the train's motion state from the JSON file. If the motion is "Stopped" or "Undispatched", no block transition occurs (the train doesn't advance while stationary). If the motion is "Moving" or "Braking", Train Model calculates which block comes next using the Line Network's routing logic (based on switch positions and train direction). The overflow yards (6.14 yards) carry forward into the next block: `yards_into_current_block = 6.14` for the new block.

**Step 8: Process Beacon Data**

Upon entering a new block, Train Model reads the beacon data from the JSON file. The beacon provides the speed limit for this block (e.g., 55 km/hr = 34.18 mph). If the current commanded speed exceeds this limit, Train Model overrides it: `effective_commanded_speed = min(commanded_speed, beacon_speed_limit)`. The train will not accelerate beyond 34.18 mph even if Track Control commanded 40 mph.

If the beacon indicates a station (`current_station = "Glenbury"`), Train Model processes passenger boarding. The beacon's `passengers_boarding` value (e.g., 150 passengers) is added to the train's passenger count. The train's mass increases by `150 * 75 kg = 11,250 kg`. Train Model recalculates the maximum acceleration based on the new mass: with increased mass, maximum acceleration decreases slightly (from 2.93 m/s² to approximately 2.63 m/s² for a 163,600 kg train now weighing 174,850 kg). This makes the loaded train accelerate more slowly when departing the station.

**Step 9: Write Updated State**

Train Model writes all updated values to `track_model_Train_Model.json`. The motion object receives new values for `position_yds`, `yards_into_current_block`, `velocity`, and `acceleration`. The block object updates `current_block` if a transition occurred. The passengers object updates `current_passengers` if boarding occurred. These updates make the train's current state visible to Track Control and other modules.

**Step 10: Log Position (Optional)**

For debugging and analysis, Train Model logs detailed position information at regular intervals. These logs show the train's progression through blocks: `"Train 1 Block 63: pos=115.5yds, delta=0.576yds, block_traveled=115.5yds"`. The `delta` value shows the position change since the last log entry, while `block_traveled` shows total distance traveled within the current block. These logs help diagnose position tracking issues and verify physics calculations.

**Step 11: Sleep and Repeat**

Train Model sleeps for the remainder of the 100ms cycle, then repeats from Step 1. This continuous loop maintains real-time physics simulation for as long as the train remains active.

### **Handling Station Stops**

When a train approaches a station, Track Control commands it to stop by setting `commanded_speed = 0` and `commanded_authority` to a value that places the authority limit at the station block. Train Model's physics simulation responds by decelerating the train.

As the train slows, Train Model calculates braking deceleration: the difference between commanded speed (0) and current velocity (e.g., 15 m/s) produces a large negative acceleration. The proportional control multiplies this error by the gain: `acceleration = 0.5 * (0 - 15) = -7.5 m/s²`. However, this exceeds the service brake limit, so Train Model clamps it to -1.2 m/s², the maximum safe deceleration rate.

The train decelerates at -1.2 m/s² until velocity reaches zero. During deceleration, Train Model continues updating position based on the decreasing velocity. When velocity drops below 0.1 m/s, Train Model snaps it to exactly zero and transitions the motion state to "Stopped". The train is now stationary at the station block.

Track Control detects the train has stopped at the station (by reading the "Stopped" motion state and verifying the current block matches the station block). Track Control transitions the train's control state to "Dwelling" and starts a 10-second timer. During this dwell period, Train Model maintains zero velocity and does not update position. The train remains stopped while passengers board.

After the dwell timer expires, Track Control issues new commands: `commanded_speed = 34.5` mph (the scheduled speed for the next leg) and `commanded_authority = 1202` yards (distance to the next station). Train Model reads these commands and begins accelerating from rest toward the new commanded speed. The motion state transitions from "Stopped" back to "Moving", and the train departs the station.

### **Emergency Braking**

Emergency braking is triggered by several conditions: operator activation (emergency brake button pressed), train failures (brake failure, signal pickup failure), or track failures (broken rail detected). When any emergency condition activates, Train Model takes immediate action.

Train Model sets a boolean flag `emergency_brake_active = True` and writes this to the systems object in the JSON file. The physics simulation immediately overrides all normal acceleration calculations and applies maximum emergency deceleration: `acceleration = -2.73 m/s²`, regardless of commanded speed or service brake limits.

The train decelerates at this emergency rate until velocity reaches zero. Emergency braking produces a shorter stopping distance than service braking due to the higher deceleration rate. For example, a train traveling at 15 m/s (33.55 mph) requires approximately 5.5 seconds and 41 meters (45 yards) to stop under emergency braking, compared to 12.5 seconds and 94 meters (103 yards) for service braking.

Once stopped, the train remains stopped with `current_motion = "Stopped"` and `velocity = 0.0`. The emergency brake flag stays active until the emergency condition is cleared. If the operator clears the emergency brake, or if the failure causing automatic emergency braking is resolved, Train Model clears the `emergency_brake_active` flag. However, the train does not automatically resume motion. Track Control must issue new commanded speed and authority values to restart the train.

Train Model logs emergency brake activations: `"Emergency brake activated: brake failure detected"` or `"Emergency brake activated: broken rail in block 77"`. These logs provide a record of safety events for analysis and debugging.

### **Failure Response**

Train Model implements specific responses for each type of failure:

**Brake Failure:**
When brake failure is injected, Train Model immediately activates the emergency brake. Normal service braking is disabled (acceleration cannot be set to negative values for controlled deceleration). Only the emergency brake system remains operational. If the train is moving when brake failure occurs, the emergency brake brings it to a stop. Once stopped, the train cannot move until the brake failure is cleared and Track Control provides new commands.

**Signal Pickup Failure:**
Signal pickup failure simulates loss of communication between the train and Track Control. Train Model can no longer read commanded speed and authority values from the JSON file (or treats them as zero/invalid). The train immediately activates the emergency brake and decelerates to a stop. It remains stopped until the signal pickup failure is cleared and valid commands are restored. This failure mode ensures trains don't continue operating without proper control signals.

**Engine Failure:**
Engine failure removes the train's ability to generate positive acceleration. The maximum power output is set to zero, which limits maximum acceleration to 0 m/s². If the train is moving when engine failure occurs, it cannot maintain speed or accelerate. The train coasts, decelerating due to friction and grade effects. On level track, friction alone produces approximately -0.1 m/s² deceleration, so the train gradually slows to a stop over time. Train Model does not automatically apply the emergency brake for engine failure, as the coasting deceleration provides a safe stop. However, if the train is on a downgrade, gravity may cause it to continue rolling. Track Control should detect the engine failure and command the service brake to bring the train to a controlled stop.

**Track Failures (Power/Circuit/Broken):**
Train Model reads the track failure array to detect failures in the current block. Power failure indicates no electrical power is available on the track. Train Model immediately sets commanded speed to zero and applies service braking to stop the train safely. Circuit failure indicates a problem with track detection sensors but doesn't affect train operation directly. Train Model logs the circuit failure but continues normal operation. Broken rail represents a severe track defect. Train Model immediately activates the emergency brake to prevent potential derailment. The train stops as quickly as possible and remains stopped until the broken rail is repaired (failure cleared).

---

## **6. Module Interface**

### **Key Classes**

**TrainModel:**
- Main physics simulation class for a single train
- Methods:
  - `__init__(train_id, line, initial_block)`: Initialize train instance
  - `update_physics(timestep)`: Execute one physics simulation step
  - `set_commanded_speed(speed_mph)`: Update target speed from Track Control
  - `set_commanded_authority(authority_yards)`: Update travel limit
  - `activate_emergency_brake()`: Trigger emergency braking
  - `inject_failure(failure_type)`: Simulate train system failure
  - `clear_failure(failure_type)`: Resolve train system failure
  - `read_beacon_data()`: Process beacon information from track
  - `calculate_acceleration(target_velocity, current_velocity, grade)`: Compute acceleration
  - `update_velocity(acceleration, timestep)`: Integrate acceleration to velocity
  - `update_position(velocity, timestep)`: Integrate velocity to position
  - `check_block_boundary()`: Detect when train crosses into next block
  - `write_state_to_json()`: Output current train state

**Physics Parameters:**
- `mass`: Total train mass including passengers (kg)
- `max_power`: Maximum motor power output (kW)
- `max_acceleration`: Maximum achievable acceleration (m/s²)
- `service_brake_deceleration`: Normal braking rate (m/s²)
- `emergency_brake_deceleration`: Emergency braking rate (m/s²)
- `friction_coefficient`: Rolling friction coefficient
- `frontal_area`: Train frontal area for air resistance (m²)

**State Variables:**
- `position_yds`: Absolute position from dispatch (yards)
- `yards_into_current_block`: Position within current block (yards)
- `velocity`: Current speed (m/s)
- `acceleration`: Current acceleration (m/s²)
- `current_block`: Block number where train is located
- `current_motion`: Motion state string (Moving, Stopped, Braking, Undispatched)
- `emergency_brake_active`: Emergency brake status (boolean)

### **Main Entry Points**

**Train Creation:**
```python
train = TrainModel(train_id=1, line="Green", initial_block=0)
train.set_physics_parameters(mass=163600, max_power=480000, max_accel=2.93)
```

**Physics Loop (called continuously):**
```python
while train_active:
    train.update_physics(timestep=0.1)  # 100ms timestep
    time.sleep(0.1)
```

**Command Updates:**
```python
train.set_commanded_speed(speed_mph=34.5)
train.set_commanded_authority(authority_yards=428)
```

**Emergency Operations:**
```python
train.activate_emergency_brake()
train.inject_failure("brake_failure")
train.clear_failure("brake_failure")
```

### **Called by Other Modules**

**Track Control calls (indirectly via JSON):**
- Writes commanded speed/authority to `track_io.json`
- Reads train motion state from `track_model_Train_Model.json`
- Monitors emergency brake status

**Line Network calls:**
- `check_block_boundary()`: Determines when block transitions occur
- Provides next block number based on routing

**UI calls:**
- Reads full train state from `track_model_Train_Model.json` for display
- May send failure injection commands for testing

---

## **7. Logging**

### **Physics and Motion Logs**

**Position Tracking:**
- `[POSITION] Train 1 position tracking initialized`
- `[POSITION] Train 1 Block 63: pos=115.5yds, delta=0.576yds, block_traveled=115.5yds`
- `[POSITION] Train 1 Block 63: ADVANCING to next block (traveled 115.5/109.36 yds)`

**Position Reset Detection:**
- `[POSITION] Train 1 Block 65: POSITION RESET DETECTED - syncing previous position`
- Logged when: New authority issued causes position value to jump (after station stops)

**Motion State:**
- `[POSITION] Train 1 Block 63: motion state = Moving`
- `[POSITION] Train 1 Block 64: motion state = Braking`
- `[POSITION] Train 1 Block 65: motion state = Stopped`

### **Command and Authority Logs**

**Command Receipt:**
- `[TRAIN_MODEL] Position preserved on new authority: 428 yds (yards_in_block: 0.00)`
- `[TRAIN_MODEL] Position preserved on new authority: 1202 yds (yards_in_block: 11.08)`
- Logged when: Track Control updates commanded authority

**Command Zeroing:**
- `[TRAIN_MODEL] Zeroing command: speed=0, authority=0`
- `[TRAIN_MODEL] Zeroing command: speed=22.4, authority=0`
- Logged when: Commands are set to zero (station stops, separation, failures)

### **Beacon and Station Logs**

**Beacon Processing:**
- `[BEACON] Train 1 beacon updated at block 65`
- `[BEACON] Train 1 speed limit enforced: 55 km/hr (34.18 mph)`
- `[BEACON] Train 1 passengers boarding: 150 passengers at Glenbury`

**Station Events:**
- `[STATION] Train 1 arrived at Glenbury station`
- `[STATION] Train 1 doors opened: Right side`
- `[STATION] Train 1 doors closed, ready to depart`

### **Failure and Emergency Logs**

**Emergency Brake:**
- `[EMERGENCY] Train 1 emergency brake activated`
- `[EMERGENCY] Train 1 emergency brake cleared`
- `[EMERGENCY] Train 1 emergency stop: authority exhausted`



### Failure and Physics Calculation Logs

**Failure Events:**
- `[FAILURE] Train 1 signal pickup failure detected`
- `[FAILURE] Train 1 engine failure cleared`
- `[FAILURE] Train 1 stopped: power failure in block 88`
- `[FAILURE] Train 1 emergency brake: broken rail in block 77`

**Physics Calculation Logs (Debug Level):**

*Acceleration:*
- `[PHYSICS] Train 1 calculated acceleration: 2.73 m/s² (grade compensated)`
- `[PHYSICS] Train 1 acceleration limited to max: 2.93 m/s²`

*Velocity:*
- `[PHYSICS] Train 1 velocity updated: 5.00 → 5.27 m/s`
- `[PHYSICS] Train 1 velocity clamped to speed limit: 15.43 m/s`

*Position:*
- `[PHYSICS] Train 1 position updated: 200.0 → 200.576 yards`

### Log File Location

File: logs/train_model_YYYYMMDD_HHMMSS.log
Format: [YYYY-MM-DD HH:MM:SS.mmm] [LEVEL] [CATEGORY] Message
Debug logs: Detailed physics calculations (disabled in production for performance)
Info logs: State changes, commands, beacons, stations
Warning logs: Constraint violations, unexpected conditions
Error logs: Calculation errors, file I/O failures

## 8. Dependencies

### Other Modules
- Track Control: Provides commanded speed/authority via track_io.json
- Track Model: Provides beacon data and track failures via JSON
- Line Network: Provides block routing information for transitions

### External Libraries
- json: Reading commanded values, writing train state
- math: Trigonometric functions for grade calculations, kinematic equations
- time: Timestep timing for physics loop
- logging: Structured log output

### File Dependencies
Required during operation:
- track_io.json: Command input (commanded speed/authority), failure input (track failures)
- track_model_Train_Model.json: State output (motion, position, systems), beacon input
Optional:
- track_model_static.json: Block lengths and grades for physics calculations (can be cached)

## 9. Architecture Diagram
```
┌────────────────────────────────────────────────────────────────┐
│                      TRAIN MODEL MODULE                        │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  INPUT: Commands (track_io.json)                              │
│  ┌──────────────────────┐                                     │
│  │ Command Reader       │                                     │
│  │ - Commanded speed    │                                     │
│  │ - Commanded authority│                                     │
│  │ - Track failures     │                                     │
│  └──────────┬───────────┘                                     │
│             │                                                  │
│             ↓                                                  │
│  ┌──────────────────────────────────────────────────┐        │
│  │         Physics Simulation Engine                 │        │
│  ├──────────────────────────────────────────────────┤        │
│  │                                                   │        │
│  │  ┌────────────────┐      ┌──────────────────┐   │        │
│  │  │ Acceleration   │─────→│ Velocity Update  │   │        │
│  │  │ Calculator     │      │ - Integration    │   │        │
│  │  │ - PID control  │      │ - Speed limits   │   │        │
│  │  │ - Grade comp   │      │ - Constraints    │   │        │
│  │  │ - Mass effects │      └────────┬─────────┘   │        │
│  │  └────────────────┘               │             │        │
│  │                                    ↓             │        │
│  │  ┌────────────────┐      ┌──────────────────┐   │        │
│  │  │ Authority      │◄─────│ Position Update  │   │        │
│  │  │ Enforcement    │      │ - Integration    │   │        │
│  │  │ - Limit check  │      │ - Block tracking │   │        │
│  │  │ - Auto brake   │      │ - Overflow calc  │   │        │
│  │  └────────────────┘      └────────┬─────────┘   │        │
│  │                                    │             │        │
│  │  ┌────────────────┐               │             │        │
│  │  │ Emergency      │               │             │        │
│  │  │ Brake Logic    │◄──────────────┘             │        │
│  │  │ - Failure check│                             │        │
│  │  │ - Max decel    │                             │        │
│  │  └────────────────┘                             │        │
│  │                                                   │        │
│  └──────────────────────────────────────────────────┘        │
│             │                                                  │
│             ↓                                                  │
│  ┌──────────────────────┐      ┌──────────────────┐          │
│  │ Block Boundary       │─────→│ Beacon Processor │          │
│  │ Detection            │      │ - Speed limits   │          │
│  │ - Length comparison  │      │ - Station info   │          │
│  │ - Overflow tracking  │      │ - Passengers     │          │
│  └──────────────────────┘      └──────────────────┘          │
│                                                                │
│  INPUT: Beacon Data (track_model_Train_Model.json)            │
│  ┌──────────────────────┐                                     │
│  │ Beacon Reader        │                                     │
│  │ - Speed limit        │                                     │
│  │ - Station data       │                                     │
│  │ - Passenger count    │                                     │
│  └──────────────────────┘                                     │
│                                                                │
│             ↓                                                  │
│  OUTPUT: Train State (track_model_Train_Model.json)           │
│  ┌──────────────────────┐                                     │
│  │ State Writer         │                                     │
│  │ - Motion state       │                                     │
│  │ - Position data      │                                     │
│  │ - Velocity/accel     │                                     │
│  │ - System status      │                                     │
│  │ - Passenger count    │                                     │
│  └──────────────────────┘                                     │
│                                                                │
└────────────────────────────────────────────────────────────────┘
Data Flow:

Command Reader → Acceleration Calculator (commanded speed sets target)
Acceleration Calculator → Velocity Update (acceleration integrated)
Velocity Update → Position Update (velocity integrated)
Position Update → Block Boundary Detection (check if crossed block)
Block Boundary Detection → Beacon Processor (read new block data)
Beacon Processor → Acceleration Calculator (speed limit feedback)
Authority Enforcement → Velocity Update (auto brake if authority exhausted)
Emergency Brake Logic → Velocity Update (override for failures)
State Writer → JSON output (all state variables)
