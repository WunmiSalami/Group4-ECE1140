# 📦 **INSTALLATION GUIDE**
## Train & Track Control System

---

## **Prerequisites**

Before running the system, ensure you have the following installed:

### **Required Software**
- **Python 3.8 or higher**
- **pip** (Python package installer)

### **Required Python Libraries**
Install all dependencies using pip:

```bash
pip install tkinter pandas openpyxl
```

**Library breakdown:**
- `tkinter` - GUI framework (usually included with Python)
- `pandas` - Data processing for track layout
- `openpyxl` - Excel file reading for track configuration

---

## **Installation Steps**

### **Step 1: Extract the System Files**

1. Extract the provided `.zip` file to your desired location
2. Navigate to the extracted folder structure:

```
Track_and_Train/
├── Combined_ui.py          # Main launcher
├── Track_Model/
│   ├── track_model_UI.py
│   ├── TrackControl.py
│   ├── Track Layout & Vehicle Data vF5.xlsx
│   └── ...
├── Train_Model/
│   ├── train_manager.py
│   ├── train_model_core.py
│   └── ...
├── track_io.json
├── ctc_data.json
└── track_model_Train_Model.json
```

![System Directory Structure](docs/images/directory_structure.png)

---

### **Step 2: Verify File Structure**

Ensure the following critical files are present:

**Root Directory (`Track_and_Train/`):**
- `Combined_ui.py` - System launcher
- `track_io.json` - Track control I/O data
- `ctc_data.json` - CTC office data
- `track_model_Train_Model.json` - Track/Train communication data

**Track_Model Directory:**
- `track_model_UI.py` - Track Model interface
- `TrackControl.py` - Track Control logic
- `Track Layout & Vehicle Data vF5.xlsx` - Track configuration (REQUIRED)

**Train_Model Directory:**
- `train_manager.py` - Train Manager
- `train_model_core.py` - Train physics simulation
- `train_data.json` - Train state data

---

### **Step 3: Launch the System**

1. Open a terminal/command prompt
2. Navigate to the `Track_and_Train/` directory:

```bash
cd path/to/Track_and_Train
```

3. Run the launcher:

```bash
python Combined_ui.py
```

![Launcher Command](docs/images/launch_command.png)

---

## **System Startup**

### **Main Launcher Window**

Upon successful launch, you will see the **Central Control Launcher**:

![Main Launcher](docs/images/main_launcher.png)

The launcher provides three module buttons:

1. **🛤️ Track Model** - Opens the track infrastructure interface
2. **🚂 Train Manager** - Opens the train creation and management interface
3. **🎛️ Track Control** - Opens the dispatching and routing control interface

---

### **Starting Each Module**

**Click each button to launch the corresponding module:**

#### **1. Track Model**
- **Purpose:** Manage track infrastructure, load track layout, view track state
- **Window Size:** 1200x800
- Click "Track Model" button to open
- First-time launch will load `Track Layout & Vehicle Data vF5.xlsx`

![Track Model Interface](docs/images/track_model_ui.png)

---

#### **2. Train Manager**
- **Purpose:** Create new trains, delete trains, manage train fleet
- **Window Size:** Auto-sized
- Click "Train Manager" button to open
- Creates new train instances with unique IDs

![Train Manager Interface](docs/images/train_manager_ui.png)

---

#### **3. Track Control**
- **Purpose:** Dispatch trains, set routes, monitor occupancy, control switches
- **Window Size:** 1600x900
- Click "Track Control" button to open
- Requires Track Model to be running for full functionality

![Track Control Interface](docs/images/track_control_ui.png)

---

## **Configuration**

### **Track Layout File**

The system requires the Excel track layout file located at:
```
Track_Model/Track Layout & Vehicle Data vF5.xlsx
```

**This file contains:**
- Block data (grade, elevation, length, speed limits)
- Station locations and names
- Switch configurations
- Infrastructure positions (crossings, beacons, heaters)

**⚠️ IMPORTANT:** Do not modify this file unless you understand the track layout structure.

---

### **JSON Data Files**

The system uses three JSON files for inter-module communication:

**1. `track_io.json`**
- Stores Track Control commands (switches, lights, gates, speed/authority)
- Updated by Track Control, read by Track Model

**2. `track_model_Train_Model.json`**
- Stores train data (position, velocity, beacon info)
- Updated by Train Model, read by Track Model

**3. `ctc_data.json`**
- Stores dispatch information and system state
- Updated by Track Control

**⚠️ These files are automatically created/reset on system startup. Do not manually edit.**

---

## **Verifying Installation**

### **Successful Startup Checklist**

✅ **Main Launcher opens without errors**
- You see "TRAIN & TRACK SYSTEM" header
- Three module buttons are visible and clickable

✅ **Track Model loads track data**
- Green Line and Red Line appear on track diagram
- Station list populates
- No "file not found" errors

✅ **Train Manager opens**
- "Create Train" interface appears
- Train dropdown shows "No trains created"

✅ **Track Control opens**
- Track visualization loads
- Block occupancy table shows all blocks
- Switch/light controls are visible

![System Running](docs/images/system_running.png)

---

## **Typical Workflow After Installation**

1. **Start Combined_ui.py**
2. **Open Track Model first** - Loads track infrastructure
3. **Open Train Manager** - Create train(s)
4. **Open Track Control** - Dispatch trains to destinations
5. **Monitor all three windows** as trains move through the system

---

## **Troubleshooting**

### **Common Issues**

**Problem: "ModuleNotFoundError: No module named 'pandas'"**
- **Solution:** Install missing library: `pip install pandas`

**Problem: "FileNotFoundError: Track Layout & Vehicle Data vF5.xlsx not found"**
- **Solution:** Ensure Excel file is in `Track_Model/` directory with exact name

**Problem: Launcher opens but buttons don't work**
- **Solution:** Check terminal for error messages, ensure all Python files are present

**Problem: JSON file errors on startup**
- **Solution:** Delete all `.json` files in root directory, they will regenerate on next launch

**Problem: "Permission denied" on JSON files**
- **Solution:** Close all system windows and restart, ensure no other programs are accessing the files

---

## **System Requirements**

**Minimum:**
- Windows 10 or higher
- Python 3.8+
- 4GB RAM
- 100MB disk space

**Recommended:**
- Windows 11
- Python 3.10+
- 8GB RAM
- Dual monitor setup for viewing multiple modules

---

## **Uninstallation**

To remove the system:
1. Close all module windows
2. Delete the `Track_and_Train/` folder
3. (Optional) Uninstall Python libraries: `pip uninstall pandas openpyxl`

---

## **Additional Notes**

- **Logs:** System logs are stored in `logs/` directory
- **Closing:** Always close via the launcher's X button for proper cleanup
- **Multiple Instances:** Do not run multiple instances of `Combined_ui.py` simultaneously
- **File Paths:** System uses relative paths - always run from `Track_and_Train/` directory

---

## **Support**

For issues or questions:
- Check the main `README.md` for system architecture details
- Review module-specific READMEs in `Track_Model/` and `Train_Model/` directories
- Consult system logs in `logs/` directory for error details

---

**Installation complete!**