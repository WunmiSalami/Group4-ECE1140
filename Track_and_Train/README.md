# 📘 **TRAIN CONTROL SYSTEM - INTEGRATION OVERVIEW**

---

## **1. System Purpose**

A distributed train control system managing multiple trains across Red and Green rail lines. The system coordinates train movement, track infrastructure, and safety through four modules that communicate via shared data.

---

## **2. Module Responsibilities**

### **Track Model**

**What it does:**
- Maintains the physical rail network infrastructure
- Manages track properties (grade, elevation, length, speed limits, crossings, beacons)
- Handles ticket sales and passenger waiting at stations
- Tracks which blocks are occupied by trains
- Controls switches, traffic lights, and railway crossing gates
- Simulates environmental conditions (temperature, track heaters)
- Reports track circuit signals
- Manages failure modes (broken rail, track circuit failure, power failure)

**Inputs:**
- Track layout file (Excel with block data, stations, switches, infrastructure)
- Switch position commands
- Traffic light commands
- Gate commands (for railway crossings)
- Train occupancy information

**Outputs:**
- Track properties for each block
- Beacon data (speed limits, station names, passengers boarding)
- Current switch positions
- Current traffic light states
- Current gate states
- Block occupancy status
- Track failure states
- Passenger boarding/disembarking counts

**Who it communicates with:**
- Sends beacon data and track state to Train Model
- Receives commands from Track Control
- Reports occupancy and failures to Track Control

---

### **Track Control**

**What it does:**
- Dispatches trains to destination stations with arrival times
- Calculates routes through the network
- Determines speed and authority for trains
- Commands switch positions for routing
- Sets traffic light colors based on train positions
- Monitors train occupancy across blocks
- Enforces train separation
- Manages railway crossing gates

**Inputs:**
- Track configuration (block properties, station locations, switch topology)
- Train dispatch requests (train ID, destination, arrival time)
- Block occupancy data
- Train positions and motion states
- Track failure information

**Outputs:**
- Speed commands for trains (mph)
- Authority commands for trains (yards - distance limit)
- Switch position commands
- Traffic light commands
- Railway crossing gate commands

**Who it communicates with:**
- Sends commands to Track Model (switches, lights, gates)
- Sends speed/authority commands to Train Model (via Train Manager)
- Receives train state from Train Model
- Receives occupancy and failures from Track Model

---

### **Train Model**

**What it does:**
- Simulates train physics (acceleration, braking, velocity, position)
- Calculates motion using Newton's laws from power commands
- Displays train properties (length, height, width, mass, acceleration, velocity)
- Tracks crew and passenger count
- Regulates internal train temperature
- Controls train lights and doors
- Processes beacon inputs (speed limits, stations, passengers)
- Handles emergency and service brakes
- Manages failure modes (engine failure, signal pickup failure, brake failure)

**Inputs:**
- Commanded speed (target velocity from Track Control)
- Commanded authority (distance limit from Track Control)
- Beacon data (speed limits, station information, passengers boarding)
- Track circuit signals
- Power commands

**Outputs:**
- Current position (yards)
- Current velocity and acceleration
- Motion state (Moving, Stopped, Braking, Undispatched)
- Current block number
- Train properties (mass, dimensions, speed)
- Passenger count (crew + passengers)
- Emergency brake status
- Service brake status
- Internal temperature
- Light and door states
- Failure states

**Who it communicates with:**
- Receives commands from Track Control (via Train Manager)
- Receives beacon data from Track Model
- Reports position and state to Track Control
- Reports occupancy to Track Model (via Track Control)

---

### **Train Manager**

**What it does:**
- Creates new train instances
- Deletes trains from the system
- Manages train lifecycle
- Routes commands between Track Control and Train Model
- Validates train operations
- Provides train status queries

**Inputs:**
- Train creation requests (train ID, line, initial block)
- Train deletion requests
- Command routing requests (train ID, speed, authority)
- Train status queries

**Outputs:**
- New train instances
- Train creation/deletion confirmations
- Train status information
- Routed commands to trains

**Who it communicates with:**
- Receives requests from Track Control
- Creates and manages Train Model instances
- Coordinates between Track Control and Train Model

---

## **3. System Data Flow**

### **Dispatching a Train**

1. **Create Train**
   - Operator requests train creation at Train Manager
   - Train Manager creates Train Model instance
   - Train Manager initializes train state

2. **Dispatch Train**
   - Operator selects destination at Track Control
   - Track Control calculates route through station blocks
   - Track Control calculates speed and authority
   - Track Control sends switch commands to Track Model
   - Track Control sends speed/authority to Train Model (via Train Manager)

3. **Train Movement**
   - Train Model simulates physics and updates position
   - Train Model reports position and state
   - Track Model updates block occupancy
   - Track Control monitors train position

4. **Block Transition**
   - Train Model crosses block boundary
   - Track Model clears old block occupancy, sets new block occupied
   - Track Model provides beacon data for new block
   - Train Model reads beacon (speed limit, station info, passengers)
   - Track Control detects block transition

5. **Station Arrival**
   - Train reaches station block
   - Track Control sets speed/authority to zero
   - Train Model stops train
   - Train Model processes passengers boarding (from beacon)
   - Track Control waits for dwell period
   - Track Control calculates next leg
   - Track Control issues new speed/authority
   - Train Model resumes movement

---

## **4. Communication Overview**

### **Track Control ↔ Track Model**
- Track Control sends: switch positions, traffic lights, gate commands
- Track Model sends: block occupancy, track failures, switch/light/gate states

### **Track Control ↔ Train Model** (via Train Manager)
- Track Control sends: commanded speed, commanded authority
- Train Model sends: position, velocity, motion state, current block

### **Track Model ↔ Train Model**
- Track Model sends: beacon data (speed limits, stations, passengers boarding)
- Train Model sends: block occupancy status (which block train is in)

### **Train Manager ↔ All Modules**
- Coordinates train creation/deletion
- Routes commands between Track Control and Train Model
- Provides train status queries

---

## **5. System Startup**

1. **Start Track Model**
   - Load track layout from Excel file
   - Parse block data, stations, switches, crossings
   - Initialize infrastructure (switches, gates, lights)
   - Set all blocks unoccupied

2. **Start Track Control**
   - Load track configuration
   - Build routing graphs for Red and Green lines
   - Start automatic control cycle

3. **Start Train Manager**
   - Initialize train management system
   - Ready to create trains

4. **System Ready**
   - All modules initialized
   - Ready to create trains and dispatch

---

## **6. Key Operations**

### **Create Train**
- Operator requests new train at Train Manager
- Train Manager instantiates Train Model
- Train is ready for dispatch

### **Dispatch Train**
- Operator provides destination and arrival time at Track Control
- Track Control calculates route and speed/authority
- Track Control configures switches
- Train begins moving

### **Monitor Train**
- Track Model reports which blocks are occupied
- Track Control tracks train positions
- Train Model reports velocity and motion state

### **Station Stop**
- Train arrives at station block
- Track Control commands stop
- Train Model processes passenger boarding
- After dwell period, Track Control dispatches to next station

### **Emergency Situations**
- Track failures detected by Track Model
- Train failures detected by Train Model
- Emergency brake activated
- Track Control responds with safety commands

---