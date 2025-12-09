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
        self.geometry("380x480")
        self.configure(bg="#2b2d31")
        self.resizable(False, False)

        # Configure dark theme styles
        style = ttk.Style()
        style.theme_use("clam")

        # Button style
        style.configure(
            "Launcher.TButton",
            background="#5865f2",
            foreground="white",
            borderwidth=0,
            focuscolor="none",
            font=("Segoe UI", 11, "bold"),
            padding=15,
        )
        style.map(
            "Launcher.TButton",
            background=[("active", "#4752c4"), ("pressed", "#3c45a5")],
        )

        # Component windows
        self.track_window = None
        self.train_manager_window = None
        self.track_control_window = None

        # Create button bar
        self.create_button_bar()

        # Set cleanup handler on close
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    def create_button_bar(self):
        # Header
        header_frame = tk.Frame(self, bg="#1e1f22", height=100)
        header_frame.pack(fill="x", padx=0, pady=0)
        header_frame.pack_propagate(False)

        tk.Label(
            header_frame,
            text="🚆 TRAIN & TRACK SYSTEM",
            font=("Segoe UI", 16, "bold"),
            bg="#1e1f22",
            fg="#ffffff",
        ).pack(pady=(25, 5))

        tk.Label(
            header_frame,
            text="Central Control Launcher",
            font=("Segoe UI", 9),
            bg="#1e1f22",
            fg="#b5bac1",
        ).pack()

        # Buttons container with border
        button_container = tk.Frame(self, bg="#2b2d31")
        button_container.pack(fill="both", expand=True, padx=20, pady=20)

        self.btn_track = ttk.Button(
            button_container,
            text="🛤️  Track Model",
            command=self.toggle_track,
            style="Launcher.TButton",
        )
        self.btn_track.pack(fill="x", pady=(0, 12))

        self.btn_train_manager = ttk.Button(
            button_container,
            text="🚂  Train Manager",
            command=self.toggle_train_manager,
            style="Launcher.TButton",
        )
        self.btn_train_manager.pack(fill="x", pady=(0, 12))

        self.btn_track_control = ttk.Button(
            button_container,
            text="🎛️  Track Control",
            command=self.toggle_track_control,
            style="Launcher.TButton",
        )
        self.btn_track_control.pack(fill="x", pady=(0, 0))

        # Footer
        footer = tk.Label(
            self,
            text="Select a module to begin",
            font=("Segoe UI", 8),
            bg="#2b2d31",
            fg="#6d6f78",
        )
        footer.pack(side="bottom", pady=(0, 10))

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

    def on_closing(self):
        """Handle cleanup when main window is closing"""
        # Reset all JSON files before exiting
        try:
            from train_manager import TrainManager

            TrainManager.cleanup_all_files()
        except Exception as e:
            print(f"Error during cleanup: {e}")

        # Close logger
        try:
            from logger import close_logger

            close_logger()
        except Exception as e:
            print(f"Error closing logger: {e}")

        # Close any open child windows
        if self.track_window:
            self.track_window.destroy()
        if self.train_manager_window:
            self.train_manager_window.destroy()
        if self.track_control_window:
            self.track_control_window.destroy()

        self.destroy()


if __name__ == "__main__":
    app = MainUI()
    app.mainloop()
