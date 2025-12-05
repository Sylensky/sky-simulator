"""
Main entry point for the Night Sky Simulator application.
"""

import tkinter as tk
from pathlib import Path


def main():
    """Run the Night Sky Simulator application."""
    from .ui.main_window import MainWindow
    
    root = tk.Tk()
    
    # Find catalogs path
    catalogs_path = Path(__file__).parent.parent / "catalogues"
    
    app = MainWindow(root, catalogs_path)
    app.run()


if __name__ == "__main__":
    main()
