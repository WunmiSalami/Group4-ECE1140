# Train System Logging Implementation

## Overview
Comprehensive logging system implemented to track all critical events in the train control system. Logs are written to both human-readable text files and structured JSON files with automatic deduplication to prevent repetitive log spam.

## Log File Location
All logs are stored in: `Track_and_Train/logs/`
- **Text log**: `train_system_YYYYMMDD_HHMMSS.log` (human-readable)
- **JSON log**: `train_system_YYYYMMDD_HHMMSS.json` (structured data)

## Features

### 1. Deduplication System
- Tracks last 50 unique messages
- Prevents "infinite loop" logs (same message repeated many times)
- Counts repeats and outputs summary: `[Previous message repeated N times]`
- Example: If position updates with same values 100 times, only logged once + repeat count

### 2. Log Levels
- **DEBUG**: Detailed information (position tracking, beacon updates)
- **INFO**: General system events (train created, switch changed, brake released)
- **WARN**: Warning events (emergency brake activated, failures)
- **ERROR**: Critical errors (not currently used, reserved for future)

### 3. Log Categories
Each log entry is categorized for easy filtering:
- **POSITION**: Train position updates (block, yards, delta)
- **TRAIN**: Train lifecycle (creation, removal)
- **BRAKE**: Brake operations (service brake, emergency brake)
- **BEACON**: Beacon data transmissions to trains
- **SWITCH**: Switch position changes
- **LIGHT**: Traffic light state changes
- **GATE**: Crossing gate operations
- **FAILURE**: Track failures (power, circuit, broken rail)
- **NETWORK**: System-level events

### 4. Thread Safety
All logging operations are protected with threading locks to prevent race conditions when multiple components log simultaneously.

### 5. Log Rotation
When a log file exceeds 10MB, a new timestamped log file is automatically created.

## What Gets Logged

### Train Operations
✅ Train creation with specifications
✅ Train removal
✅ Service brake activation/release
✅ Emergency brake activation/release (with position)

### Position Tracking
✅ Train position in yards (block, position, delta, total traveled)
✅ Automatically deduplicated to avoid spam

### Infrastructure Changes
✅ Switch position changes (line, block, old→new position)
✅ Traffic light state changes (Super Green, Green, Yellow, Red)
✅ Crossing gate operations (open/closed)

### Beacon System
✅ Beacon data updates (station info, speed limits, passengers)

### Failures
✅ Power failures (activation + clear)
✅ Circuit failures (activation + clear)
✅ Broken rail failures (activation + clear)

## Log Format Examples

### Text Log Example
```
[2024-01-15 14:23:45] [INFO] [TRAIN] Train 1 created successfully
[2024-01-15 14:23:46] [DEBUG] [POSITION] Train 1 Block 5: pos=12.45yds, delta=2.30yds, block_traveled=12.45yds
[2024-01-15 14:23:50] [INFO] [SWITCH] Green line block 10 switch changed to position 1
[2024-01-15 14:23:52] [WARN] [BRAKE] Train 1 EMERGENCY brake ACTIVATED
[2024-01-15 14:24:00] [WARN] [FAILURE] Green line G_Block_15 POWER failure activated
[Previous message repeated 3 times]
```

### JSON Log Example
```json
{
  "session_start": "2024-01-15T14:23:45.123456",
  "events": [
    {
      "timestamp": "2024-01-15 14:23:45",
      "level": "INFO",
      "category": "TRAIN",
      "message": "Train 1 created successfully",
      "data": {
        "train_id": 1,
        "has_ui": true,
        "specs": { ... }
      }
    },
    {
      "timestamp": "2024-01-15 14:23:46",
      "level": "DEBUG",
      "category": "POSITION",
      "message": "Train 1 Block 5: pos=12.45yds, delta=2.30yds...",
      "data": {
        "train_id": 1,
        "line": "Green",
        "current_block": 5,
        "position_yds": 12.45,
        "delta_yds": 2.30,
        "yards_in_block": 12.45
      }
    }
  ],
  "session_end": "2024-01-15 15:30:00.123456"
}
```

## Modified Files

1. **logger.py** (NEW)
   - Complete logging system with all features

2. **LineNetwork.py**
   - Position tracking converted to logger.debug()
   - Beacon updates logged with station/speed info

3. **train_manager.py**
   - Train creation logged
   - Train removal logged
   - Service brake operations logged
   - Emergency brake operations logged

4. **DynamicBlockManager.py**
   - Switch position changes logged
   - Traffic light changes logged
   - Crossing gate changes logged
   - All failure types logged (activate + clear)

5. **Combined_ui.py**
   - Logger cleanup on application exit

## Usage

The logger runs automatically - no manual intervention needed. All system events are logged transparently.

To analyze logs:
- **Text logs**: Open `.log` file in any text editor
- **JSON logs**: Parse `.json` file for programmatic analysis, data visualization, or debugging

## Benefits

1. **No Console Spam**: All debug output moved to files
2. **Organized**: Events categorized by type and severity
3. **Searchable**: Easy to find specific trains, blocks, or event types
4. **Deduplication**: No repetitive "infinite loop" logs
5. **Persistent**: Logs survive application restarts
6. **Structured**: JSON format enables automated analysis
7. **Complete**: Captures all critical system events
