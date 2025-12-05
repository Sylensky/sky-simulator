#!/usr/bin/env python3
"""
Night Sky Simulator - Entry Point

A Python GUI application that simulates the night sky using real astronomical data.
Run this script directly or use: python -m sky_simulator
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from sky_simulator import main

if __name__ == "__main__":
    main()
