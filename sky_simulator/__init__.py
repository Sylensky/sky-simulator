"""
Night Sky Simulator
A Python GUI application that simulates the night sky using real astronomical data.
"""

__version__ = "1.0.0"
__author__ = "OG Star Tracker Project"

import os


def main():
    """Run the Night Sky Simulator application."""
    import tkinter as tk
    from pathlib import Path
    from .ui.main_window import MainWindow
    
    # Check for debug/hot reload mode
    debug_mode = os.environ.get('SKY_DEBUG', '').lower() in ('1', 'true', 'yes')
    
    root = tk.Tk()
    
    # Find catalogs path - try multiple locations
    possible_paths = [
        Path(__file__).parent.parent / "catalogues",  # testing/catalogues (unlikely)
        Path(__file__).parent.parent.parent / "catalogues",  # firmware/catalogues
        Path.cwd() / "catalogues",  # Current directory
        Path("/app/catalogues"),  # Docker mount point
    ]
    
    catalogs_path = None
    for path in possible_paths:
        if path.exists():
            catalogs_path = path
            break
    
    app = MainWindow(root, catalogs_path, debug_mode=debug_mode)
    app.run()


__all__ = ["main"]
