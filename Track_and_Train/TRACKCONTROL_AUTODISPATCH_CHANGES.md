# TrackControl.py - Automatic Dispatch Enhancement Summary

## Changes Implemented

### 1. **Data Structures Added**

#### Route Lookup Dictionaries
- `route_lookup_via_station`: Dictionary keyed by `(line, start_station, end_station)` returning list of station blocks for the route
- `route_lookup_via_id`: Dictionary keyed by route_id for alternative lookup method
- Built automatically from existing `infrastructure` dict during initialization

#### Constants
- `DWELL_TIME = 10`: Station dwell time in seconds

#### Enhanced Train State Tracking
Each train in `active_trains` now includes:
- `route`: List of station blocks from start to destination
- `current_leg_index`: Which leg of the route (0 = first leg)
- `next_station_block`: Block number of next station to reach
- `dwell_start_time`: Timestamp when dwell started (None if not dwelling)
- `last_position_yds`: Last known position in yards (for authority tracking)

### 2. **File I/O Enhancements**

#### New Function: `_read_track_model()`
- Reads `track_model_Train_Model.json` to get actual train positions and motion states
- Used to detect:
  - Current position in yards (`position_yds`)
  - Motion state (`Stopped`, `Moving`, etc.)
  - Authority exhaustion (when train stops but not at station)

### 3. **Dispatch Logic Changes**

#### `_manual_dispatch()` - Now includes route planning
**Old behavior:**
- Set destination and basic state
- No route planning

**New behavior:**
- Look up complete route from start to destination using `route_lookup_via_station`
- Initialize all route tracking fields (`route`, `current_leg_index`, `next_station_block`)
- Set initial state to `"Dispatching"`

### 4. **Automatic Control Loop - State Machine**

#### `_automatic_control_cycle()` - Enhanced with state machine
**Old behavior:**
- Called `_route_all_trains()` which recalculated speed/authority every cycle
- Simple distance-based speed control

**New behavior:**
- Reads both `track_io.json` AND `track_model_Train_Model.json`
- Calls `_process_train_state_machine()` for each train
- Only updates commands when state transitions occur (not every cycle)
- Controls infrastructure (lights, gates) separately

#### New Function: `_process_train_state_machine()`
Routes each train through 4 states:

1. **Dispatching** → Calculate route speed, send first leg authority
2. **En Route** → Monitor for station arrival or authority exhaustion
3. **At Station** → Stop train, begin dwell timer
4. **Dwelling** → Wait 10 seconds, then dispatch next leg

### 5. **State Handler Functions**

#### `_handle_dispatching_state()`
- Calculates optimal speed (currently simplified to 30 mph)
- Calculates authority to FIRST station only (not final destination)
- Converts blocks to yards: `authority = blocks * 100`
- Sets switches for entire route
- Transitions to `"En Route"`

#### `_handle_enroute_state()`
**Station Arrival Detection:**
- Checks if `current_block == next_station_block`
- If yes: transition to `"At Station"`, start dwell timer

**Authority Exhaustion Detection:**
- Checks if `motion_state == "Stopped"` but train not at station
- If yes: resend authority for remaining distance to next station
- This handles case where authority runs out mid-leg

#### `_handle_at_station_state()`
- Sets speed/authority to 0
- Transitions immediately to `"Dwelling"`

#### `_handle_dwelling_state()`
- Monitors dwell time using `datetime.now() - dwell_start_time`
- After 10 seconds:
  - If at final destination: set state to `"Arrived"`, stop
  - Otherwise: increment `current_leg_index`, calculate next leg authority, transition to `"En Route"`

### 6. **Key Differences from Previous Implementation**

| Aspect | Old Implementation | New Implementation |
|--------|-------------------|-------------------|
| **Speed Calculation** | Recalculated every cycle based on distance | Calculated once at dispatch, maintained throughout |
| **Authority** | Set to full distance to destination | Set station-by-station (next station only) |
| **Station Detection** | Block occupancy only | Block occupancy + dwell timer |
| **Command Updates** | Every cycle (~200ms) | Only on state transitions |
| **Route Tracking** | Destination only | Full route with current leg index |
| **Dwell Time** | Not implemented | 10 second timer at each station |
| **Authority Management** | Single grant | Re-issued each leg + exhaustion handling |

### 7. **State Transition Diagram**

```
[Manual Dispatch]
       ↓
[Dispatching] ──→ Calculate speed & first leg authority
       ↓
[En Route] ──────→ Monitor position & authority
       ↓               ↓
       └────(arrived)→[At Station]
                       ↓
                  [Dwelling] ── 10 sec → (next leg?)
                       ↓               ↓
                    (yes)────→ [En Route] (next leg)
                       ↓
                    (no: final)
                       ↓
                  [Arrived]
```

### 8. **Authority Calculation**

**Formula:** `authority = abs(next_station_block - current_block) * 100`

**Example:**
- Current block: 5
- Next station block: 15
- Authority: `|15 - 5| * 100 = 1000 yards`

This gives the train just enough authority to reach the next station, ensuring it stops at each station for dwell time.

### 9. **Files Modified**

1. **TrackControl.py** (lines modified: ~150)
   - Added route lookup builders
   - Added `_read_track_model()`
   - Enhanced `_manual_dispatch()` with route planning
   - Replaced `_automatic_control_cycle()` with state machine version
   - Replaced `_route_all_trains()` / `_route_single_train()` with 4 state handlers
   - Kept `_set_switches_for_route()` and `_control_lights_for_line()` unchanged

### 10. **Testing Checklist**

- [ ] Dispatch train with destination
- [ ] Verify train stops at each intermediate station
- [ ] Verify 10 second dwell at each station
- [ ] Verify train resumes with same speed after dwell
- [ ] Verify authority is recalculated each leg
- [ ] Verify train stops at final destination
- [ ] Verify state displayed in UI matches internal state
- [ ] Test with multiple trains on same line
- [ ] Test with trains on different lines
- [ ] Test authority exhaustion mid-leg (train should receive more authority)

### 11. **Known Limitations**

1. Speed calculation is simplified (30 mph constant) - TODO: implement proper time-based calculation using arrival time
2. Authority-to-yards conversion uses approximate 100 yards/block - should be refined with actual block lengths
3. No failure handling in state machine yet - trains will stop if failure detected but won't reroute
4. Switch setting is done for entire route at dispatch - doesn't handle dynamic rerouting

### 12. **Future Enhancements**

1. Implement proper speed calculation based on arrival time, total distance, and number of dwells
2. Read actual block lengths from track data for precise authority calculation
3. Add failure handling: detect failures ahead and reroute or stop appropriately
4. Add dynamic switch management: set switches leg-by-leg instead of all at once
5. Add train scheduling: coordinate multiple trains to avoid conflicts
6. Add logging for state transitions using the new logger system
