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
sys.path.insert(0, TRACK_MODEL_DIR)
sys.path.insert(0, TRAIN_MODEL_DIR)

# Import modules
from track_model_UI import TrackModelUI
from train_manager import TrainManagerUI
from TrackControl import TrackControl


class MainUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Train & Track System")
        self.geometry("1800x1000")
        self.configure(bg="white")

        # Track visibility states
        self.track_visible = False
        self.train_manager_visible = False
        self.track_control_visible = False

        # Create button bar at top
        self.create_button_bar()

        # Create main content area
        self.content_frame = ttk.Frame(self)
        self.content_frame.pack(fill="both", expand=True, padx=5, pady=5)
        self.content_frame.grid_rowconfigure(0, weight=1)

        # Create frames for each panel
        self.track_container = ttk.Frame(self.content_frame)
        self.train_manager_container = ttk.Frame(self.content_frame)
        self.track_control_container = ttk.Frame(self.content_frame)

        # Initialize the UI components
        self.track_ui = TrackModelUI(self.track_container)
        self.train_manager_ui = None  # Will be created when toggled
        self.track_control_ui = None  # Will be created when toggled

    def create_button_bar(self):
        button_frame = ttk.Frame(self)
        button_frame.pack(fill="x", padx=5, pady=5)

        self.btn_track = ttk.Button(
            button_frame, text="Show Track Model", command=self.toggle_track
        )
        self.btn_track.pack(side="left", padx=5)

        self.btn_train_manager = ttk.Button(
            button_frame, text="Show Train Manager", command=self.toggle_train_manager
        )
        self.btn_train_manager.pack(side="left", padx=5)

        self.btn_track_control = ttk.Button(
            button_frame, text="Show Track Control", command=self.toggle_track_control
        )
        self.btn_track_control.pack(side="left", padx=5)

    def toggle_track(self):
        if self.track_visible:
            self.track_container.grid_forget()
            self.btn_track.config(text="Show Track Model")
            self.track_visible = False
        else:
            self.track_container.grid(row=0, column=0, sticky="nsew", padx=2, pady=2)
            self.btn_track.config(text="Hide Track Model")
            self.track_visible = True
        self.update_column_weights()

    def toggle_train_manager(self):
        if self.train_manager_visible:
            self.train_manager_container.grid_forget()
            self.btn_train_manager.config(text="Show Train Manager")
            self.train_manager_visible = False
        else:
            # Create TrainManagerUI if it doesn't exist yet
            if self.train_manager_ui is None:
                self.train_manager_ui = TrainManagerUI()

            self.train_manager_container.grid(
                row=0, column=1, sticky="nsew", padx=2, pady=2
            )
            self.train_manager_container.config(width=450)
            self.train_manager_container.grid_propagate(False)
            self.btn_train_manager.config(text="Hide Train Manager")
            self.train_manager_visible = True
        self.update_column_weights()

    def toggle_track_control(self):
        if self.track_control_visible:
            self.track_control_container.grid_forget()
            self.btn_track_control.config(text="Show Track Control")
            self.track_control_visible = False
        else:
            # Create TrackControl if it doesn't exist yet
            if self.track_control_ui is None:
                self.track_control_ui = TrackControl(self.track_control_container)

            self.track_control_container.grid(
                row=0, column=2, sticky="nsew", padx=2, pady=2
            )
            self.btn_track_control.config(text="Hide Track Control")
            self.track_control_visible = True
        self.update_column_weights()

    def update_column_weights(self):
        # Reset all weights
        for i in range(3):
            self.content_frame.grid_columnconfigure(i, weight=0)

        # Set weights for visible columns
        if self.track_visible:
            self.content_frame.grid_columnconfigure(0, weight=5)
        if self.train_manager_visible:
            self.content_frame.grid_columnconfigure(1, weight=0)
        if self.track_control_visible:
            self.content_frame.grid_columnconfigure(2, weight=3)


if __name__ == "__main__":
    app = MainUI()
    app.mainloop()
