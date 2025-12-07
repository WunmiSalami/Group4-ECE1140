import tkinter as tk
from tkinter import ttk
import sys
import os

MAIN_DIR = os.path.dirname(os.path.abspath(__file__))  # Track_and_Train
ROOT_DIR = os.path.dirname(MAIN_DIR)

# Get absolute paths
TRACK_MODEL_DIR = os.path.join(MAIN_DIR, "Track_Model")
TRAIN_MODEL_DIR = os.path.join(MAIN_DIR, "Train_Model")

# Add directories to path for imports BEFORE importing
sys.path.insert(0, MAIN_DIR)
sys.path.insert(0, TRACK_MODEL_DIR)
sys.path.insert(0, TRAIN_MODEL_DIR)

# Import modules
from track_model_UI import TrackModelUI
from train_manager import TrainManagerUI
from TrackControl import TrackControl


class MainUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Train & Track System - Launcher")
        self.geometry("400x200")
        self.configure(bg="white")

        # Component windows
        self.track_window = None
        self.train_manager_window = None
        self.track_control_window = None

        # Create button bar
        self.create_button_bar()

    def create_button_bar(self):
        button_frame = ttk.Frame(self)
        button_frame.pack(fill="both", expand=True, padx=20, pady=20)

        self.btn_track = ttk.Button(
            button_frame, text="Show Track Model", command=self.toggle_track
        )
        self.btn_track.pack(fill="x", pady=5)

        self.btn_train_manager = ttk.Button(
            button_frame, text="Show Train Manager", command=self.toggle_train_manager
        )
        self.btn_train_manager.pack(fill="x", pady=5)

        self.btn_track_control = ttk.Button(
            button_frame, text="Show Track Control", command=self.toggle_track_control
        )
        self.btn_track_control.pack(fill="x", pady=5)

    def toggle_track(self):
        if self.track_window is None:
            # Create window
            self.track_window = tk.Toplevel(self)
            self.track_window.title("Track Model")
            self.track_window.geometry("1200x800")
            self.track_window.protocol("WM_DELETE_WINDOW", self.hide_track)

            # Create UI inside window
            TrackModelUI(self.track_window)

            self.btn_track.config(text="Hide Track Model")
        else:
            # Toggle visibility
            if self.track_window.state() == "withdrawn":
                self.track_window.deiconify()
                self.btn_track.config(text="Hide Track Model")
            else:
                self.track_window.withdraw()
                self.btn_track.config(text="Show Track Model")

    def hide_track(self):
        if self.track_window:
            self.track_window.withdraw()
            self.btn_track.config(text="Show Track Model")

    def toggle_train_manager(self):
        if self.train_manager_window is None:
            # Create window
            self.train_manager_window = TrainManagerUI()
            self.train_manager_window.title("Train Manager")
            self.train_manager_window.protocol(
                "WM_DELETE_WINDOW", self.hide_train_manager
            )

            self.btn_train_manager.config(text="Hide Train Manager")
        else:
            # Toggle visibility
            if self.train_manager_window.state() == "withdrawn":
                self.train_manager_window.deiconify()
                self.btn_train_manager.config(text="Hide Train Manager")
            else:
                self.train_manager_window.withdraw()
                self.btn_train_manager.config(text="Show Train Manager")

    def hide_train_manager(self):
        if self.train_manager_window:
            self.train_manager_window.withdraw()
            self.btn_train_manager.config(text="Show Train Manager")

    def toggle_track_control(self):
        if self.track_control_window is None:
            # Create window
            self.track_control_window = tk.Toplevel(self)
            self.track_control_window.title("Track Control")
            self.track_control_window.geometry("1600x900")
            self.track_control_window.protocol(
                "WM_DELETE_WINDOW", self.hide_track_control
            )

            # Create UI inside window
            TrackControl(self.track_control_window)

            self.btn_track_control.config(text="Hide Track Control")
        else:
            # Toggle visibility
            if self.track_control_window.state() == "withdrawn":
                self.track_control_window.deiconify()
                self.btn_track_control.config(text="Hide Track Control")
            else:
                self.track_control_window.withdraw()
                self.btn_track_control.config(text="Show Track Control")

    def hide_track_control(self):
        if self.track_control_window:
            self.track_control_window.withdraw()
            self.btn_track_control.config(text="Show Track Control")


if __name__ == "__main__":
    app = MainUI()
    app.mainloop()
