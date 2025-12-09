# Manual Dispatch Process Documentation

## Overview
The Manual Dispatch system in TrackControl allows operators to manually dispatch trains from the Yard to specific destinations with arrival times. The system integrates with the automatic control state machine for route execution.

---

## User Interface Elements

### Dispatch Form (Top Row)
Located in the Manual Control panel:

| Field | Type | Purpose | Example |
|-------|------|---------|---------|
| **Train** | Dropdown | Select train ID (1-5) | "Train 1" |
| **Line** | Dropdown | Select line (Green/Red) | "Green" |
| **Destination** | Dropdown | Select station name | "Castle Shannon" |
| **Arrival Time** | Text Entry | Target arrival time | "14:30" |
| **DISPATCH Button** | Button | Execute dispatch | Click to dispatch |

### Manual Command Form (Bottom Row)
For sending direct commands to already-dispatched trains:

| Field | Type | Purpose |
|-------|------|---------|
| **Train** | Dropdown | Select train ID |
| **Speed** | Text Entry | Set speed (mph) |
| **Auth** | Text Entry | Set authority (yards) |
| **SEND CMD Button** | Button | Send command |

---

## Current Implementation Analysis

### ✅ What Works Correctly

1. **Route Building** (`_manual_dispatch()` lines 1008-1056)
   - ✅ Extracts train ID from dropdown selection
   - ✅ Gets line and destination from form
   - ✅ Looks up route using `route_lookup_via_station` dictionary
   - ✅ Builds complete ordered route: `[Yard → Pioneer → Edgebrook → ... → Destination]`
   - ✅ Creates entry in `self.active_trains[train_id]` with all required fields:
     - `line`, `destination`, `current_block`, `commanded_speed`, `commanded_authority`
     - `state`, `current_station`, `arrival_time`, `route`
     - `current_leg_index`, `next_station_block`, `dwell_start_time`, `last_position_yds`

2. **CTC Data Update** (lines 1049-1055)
   - ✅ Reads ctc_data.json
   - ✅ Updates dispatcher information:
     - Line, Station Destination, Arrival Time, State="Dispatching"
   - ✅ Writes back to ctc_data.json

3. **State Machine Integration** (`_handle_dispatching_state()` lines 1212-1244)
   - ✅ Calculates authority to first station (blocks × 100 yards)
   - ✅ Sets initial commanded_speed and commanded_authority
   - ✅ Transitions state from "Dispatching" → "En Route"
   - ✅ Initializes route tracking variables

4. **Station-by-Station Routing**
   - ✅ `current_leg_index` tracks progress through route
   - ✅ `next_station_block` identifies next waypoint
   - ✅ State machine handles: Dispatching → En Route → At Station → Dwelling → (repeat)

---

## ⚠️ Issues Identified

### 1. **CRITICAL: Speed Calculation NOT Implemented**
**Location:** `_handle_dispatching_state()` line 1220

**Current Code:**
```python
# Parse arrival time and calculate speed (simplified - assume 30 mph for now)
optimal_speed = 30
```

**Issue:** Speed is hard-coded to 30 mph regardless of:
- Arrival time input
- Total distance to destination
- Number of intermediate stations
- Required dwell times

**Expected Behavior:**
```python
# Calculate optimal speed based on arrival time and total distance
arrival_time_str = train_info.get("arrival_time", "")
if arrival_time_str:
    # Parse time (e.g., "14:30" → datetime)
    # Calculate total distance (sum of blocks in route × block_length)
    # Calculate total dwell time (number_of_stations × DWELL_TIME)
    # Calculate required speed: distance / (time_available - dwell_time)
    optimal_speed = calculated_value
else:
    optimal_speed = 30  # Default if no arrival time
```

**Impact:**
- Trains may arrive early or late regardless of scheduled arrival time
- CTC scheduling logic is non-functional
- No time-based optimization

---

### 2. **MISSING: Total Dwell Time Calculation**

**Issue:** Dwell time at stations is not factored into speed calculations

**Required Logic:**
```python
# Count intermediate stations (exclude Yard and final destination)
num_intermediate_stops = len(route) - 1  # All stations except starting point
total_dwell_time_seconds = num_intermediate_stops * self.DWELL_TIME
```

**Impact:**
- Speed calculations (when implemented) will be inaccurate
- Trains won't arrive at scheduled times

---

### 3. **INCOMPLETE: CTC Data Speed Not Written**

**Location:** `_manual_dispatch()` lines 1049-1055

**Current Code:**
```python
ctc_data["Dispatcher"]["Trains"][train]["Line"] = line
ctc_data["Dispatcher"]["Trains"][train]["Station Destination"] = dest
ctc_data["Dispatcher"]["Trains"][train]["Arrival Time"] = arrival
ctc_data["Dispatcher"]["Trains"][train]["State"] = "Dispatching"
# Missing: Speed field
```

**Issue:** Calculated speed is never written to ctc_data.json

**Should Add:**
```python
ctc_data["Dispatcher"]["Trains"][train]["Speed"] = optimal_speed
```

---

### 4. **MISSING: Distance Calculation Utilities**

**Issue:** No helper method to calculate total route distance

**Required Implementation:**
```python
def _calculate_route_distance(self, route, line):
    """Calculate total distance in yards for a route"""
    total_distance = 0
    for i in range(len(route) - 1):
        block_from = route[i]
        block_to = route[i + 1]
        # Assume average block length or look up from infrastructure
        total_distance += abs(block_to - block_from) * 100  # yards per block
    return total_distance
```

---

### 5. **MISSING: Time Parsing Utilities**

**Issue:** No helper method to parse arrival time strings

**Required Implementation:**
```python
def _parse_arrival_time(self, time_str):
    """Parse arrival time string (HH:MM) to datetime"""
    from datetime import datetime
    try:
        hour, minute = map(int, time_str.split(":"))
        now = datetime.now()
        arrival = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        
        # If arrival time is in the past, assume next day
        if arrival < now:
            arrival += timedelta(days=1)
        
        return arrival
    except:
        return None
```

---

## Required Fixes

### Priority 1: Implement Speed Calculation

**File:** `TrackControl.py`  
**Method:** `_handle_dispatching_state()`  
**Lines:** 1217-1222

Replace the hard-coded speed with actual calculation:

```python
def _handle_dispatching_state(self, train_id, train_info, track_data, line_prefix):
    """Initial dispatch: calculate route speed and send first leg authority"""
    route = train_info.get("route", [])
    if not route:
        return

    # Calculate optimal speed based on arrival time and total distance
    arrival_time_str = train_info.get("arrival_time", "")
    if arrival_time_str:
        from datetime import datetime, timedelta
        
        # Parse arrival time
        try:
            hour, minute = map(int, arrival_time_str.split(":"))
            now = datetime.now()
            arrival = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if arrival < now:
                arrival += timedelta(days=1)
            
            # Calculate available time in seconds
            time_available = (arrival - now).total_seconds()
            
            # Calculate total route distance (yards)
            total_distance_yards = sum(abs(route[i+1] - route[i]) * 100 
                                      for i in range(len(route) - 1))
            
            # Calculate total dwell time (all intermediate stops)
            num_stops = len(route) - 1  # Exclude starting point
            total_dwell_seconds = num_stops * self.DWELL_TIME
            
            # Calculate travel time (exclude dwell time)
            travel_time_seconds = time_available - total_dwell_seconds
            
            if travel_time_seconds > 0:
                # Calculate required speed (yards/sec → mph)
                speed_yards_per_sec = total_distance_yards / travel_time_seconds
                optimal_speed = speed_yards_per_sec * 2.045  # Convert to mph
                
                # Clamp to safe limits (e.g., 10-70 mph)
                optimal_speed = max(10, min(70, optimal_speed))
            else:
                optimal_speed = 30  # Impossible schedule, use default
                
        except Exception as e:
            optimal_speed = 30  # Parsing error, use default
    else:
        optimal_speed = 30  # No arrival time provided

    # Calculate authority to first station
    current_block = train_info.get("current_block", 0)
    next_station_block = route[0]
    authority = abs(next_station_block - current_block) * 100

    train_info["commanded_speed"] = optimal_speed
    train_info["commanded_authority"] = authority
    train_info["state"] = "En Route"
    train_info["current_leg_index"] = 0
    train_info["next_station_block"] = next_station_block
    train_info["last_position_yds"] = 0.0

    # Log dispatch with calculated speed
    logger = get_logger()
    logger.info(
        "TRAIN",
        f"Train {train_id} dispatched: {optimal_speed:.1f} mph to reach {train_info.get('destination')} by {arrival_time_str}",
        {
            "train_id": train_id,
            "line": train_info.get("line"),
            "destination": train_info.get("destination"),
            "calculated_speed_mph": round(optimal_speed, 1),
            "arrival_time": arrival_time_str,
            "route_length_blocks": len(route),
        },
    )

    # Set switches for route
    self._set_switches_for_route(
        track_data, current_block, route[-1], train_info.get("line"), line_prefix
    )
```

### Priority 2: Update CTC Data with Speed

**File:** `TrackControl.py`  
**Method:** `_manual_dispatch()`  
**Lines:** 1049-1055

Add speed field to CTC data update (after implementing speed calculation in _handle_dispatching_state, you'll need to calculate it in _manual_dispatch as well):

```python
# Update CTC data
ctc_data = self._read_ctc_data()
if ctc_data:
    ctc_data["Dispatcher"]["Trains"][train]["Line"] = line
    ctc_data["Dispatcher"]["Trains"][train]["Station Destination"] = dest
    ctc_data["Dispatcher"]["Trains"][train]["Arrival Time"] = arrival
    ctc_data["Dispatcher"]["Trains"][train]["State"] = "Dispatching"
    
    # Calculate and store speed (duplicate logic or call helper)
    # For now, mark as TBD until automatic cycle calculates it
    ctc_data["Dispatcher"]["Trains"][train]["Speed"] = "TBD"
    
    self._write_ctc_data(ctc_data)
```

---

## Testing Checklist

### Test Case 1: Basic Dispatch
- [ ] Fill form: Train 1, Green Line, Castle Shannon, 14:30
- [ ] Click DISPATCH
- [ ] Verify train appears in Active Trains table
- [ ] Verify state = "Dispatching" initially
- [ ] Verify state transitions to "En Route" after automatic cycle

### Test Case 2: Speed Calculation
- [ ] Dispatch train with 30-minute arrival window
- [ ] Verify calculated speed is reasonable (not 30 mph default)
- [ ] Check log for "dispatched: X.X mph" message
- [ ] Verify speed considers dwell times

### Test Case 3: Route Execution
- [ ] Dispatch train to multi-stop destination
- [ ] Verify train stops at each intermediate station
- [ ] Verify 10-second dwell time at each station
- [ ] Verify state cycles: En Route → At Station → Dwelling → En Route

### Test Case 4: CTC Data Integration
- [ ] Dispatch train
- [ ] Check ctc_data.json contains:
  - Line, Destination, Arrival Time, State, Speed
- [ ] Verify speed field is populated (not "TBD")

---

## Data Flow Diagram

```
USER INPUT (Form)
    │
    ├─ Train: "Train 1"
    ├─ Line: "Green"
    ├─ Destination: "Castle Shannon"
    └─ Arrival Time: "14:30"
    │
    ↓
[_manual_dispatch()]
    │
    ├─ Extract train_id = 1
    ├─ Lookup route: route_lookup_via_station[(Green, Yard, Castle Shannon)]
    │  → Returns: [3, 7, 16, 21, 31, 39, 48, 57, 65, 73, 88, 96]
    │
    ├─ Create active_trains[1] entry:
    │  └─ { line, destination, current_block=0, commanded_speed=0,
    │       commanded_authority=0, state="Dispatching", current_station="Yard",
    │       arrival_time="14:30", route=[3,7,16,...,96], current_leg_index=0,
    │       next_station_block=3, dwell_start_time=None, last_position_yds=0.0 }
    │
    └─ Update ctc_data.json:
       └─ Trains["Train 1"] = { Line, Destination, Arrival Time, State, Speed }
    │
    ↓
[_automatic_control_cycle()] - 200ms intervals
    │
    ↓
[_process_train_state_machine(train_id=1, ...)]
    │
    └─ state="Dispatching"
       │
       ↓
   [_handle_dispatching_state()]
       │
       ├─ Parse arrival_time "14:30" → datetime
       ├─ Calculate time_available = arrival - now
       ├─ Calculate total_distance = Σ(route distances)
       ├─ Calculate total_dwell_time = (num_stations - 1) × 10 sec
       ├─ Calculate travel_time = time_available - total_dwell_time
       ├─ Calculate optimal_speed = distance / travel_time (convert to mph)
       │
       ├─ Set commanded_speed = optimal_speed
       ├─ Set commanded_authority = distance_to_first_station
       ├─ Set state = "En Route"
       └─ Set switches for route
       │
       ↓
   [_write_train_commands()]
       │
       └─ Writes to track_io.json:
          - G-Train or R-Train
          - commanded speed, commanded authority
       │
       ↓
   TRAIN MODEL reads track_io.json
       │
       └─ Train begins moving toward first station
```

---

## Summary

### What's Working:
✅ Route building and lookup  
✅ State machine integration  
✅ Station-by-station routing  
✅ Dwell time handling  
✅ CTC data structure  

### What Needs Fixing:
❌ Speed calculation (hard-coded to 30 mph)  
❌ Dwell time consideration in speed calc  
❌ Speed field in CTC data  
❌ Time parsing utilities  
❌ Distance calculation helpers  

### Implementation Priority:
1. **HIGH**: Implement actual speed calculation based on arrival time
2. **HIGH**: Add speed to CTC data write
3. **MEDIUM**: Add helper methods for time/distance calculations
4. **LOW**: Enhanced error handling for invalid inputs

---

## Implementation Status

### ✅ FIXED (December 8, 2025)

**1. Speed Calculation** - `_handle_dispatching_state()` lines 1217-1298
- ✅ Parses arrival time (HH:MM format)
- ✅ Calculates time available until arrival
- ✅ Calculates total route distance (sum of block distances × 100 yards)
- ✅ Accounts for dwell time at all intermediate stations (num_stops × 10 seconds)
- ✅ Calculates optimal speed: distance / (time - dwell_time), converts to mph
- ✅ Clamps speed to safe limits (10-70 mph)
- ✅ Handles parsing errors and impossible schedules (defaults to 30 mph)
- ✅ Logs calculated speed with full context

**2. CTC Data Speed Update** - `_handle_dispatching_state()` lines 1300-1306
- ✅ Updates ctc_data.json with calculated speed after dispatch
- ✅ Writes speed as "{speed} mph" format

**3. Manual Dispatch Logging** - `_manual_dispatch()` lines 1057-1069
- ✅ Logs manual dispatch with train, destination, line, arrival time
- ✅ CTC data initially marked as "Calculating..." until state machine runs

**Formula Used:**
```
total_distance_yards = Σ(|route[i+1] - route[i]| × 100)
total_dwell_seconds = (num_stations - 1) × 10
travel_time_seconds = (arrival_time - now) - total_dwell_seconds
optimal_speed_mph = (total_distance_yards / travel_time_seconds) × 2.045
clamped_speed = max(10, min(70, optimal_speed_mph))
```

---

**Document Version:** 2.0  
**Last Updated:** December 8, 2025  
**Status:** ✅ IMPLEMENTED - Ready for Testing
