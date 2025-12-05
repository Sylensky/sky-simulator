# Night Sky Simulator

A Python GUI application that simulates the night sky using real astronomical data from NGC and BSC5 catalogs.

## Features

### Core Features
- **Real Astronomical Data**: Uses NGC2000 catalog (deep sky objects) and BSC5 (bright stars)
- **RA/DEC Coordinates**: All calculations use proper astronomical coordinates (J2000 epoch)
- **Optics Simulation**: Calculate FOV based on focal length and sensor size
- **Interactive Controls**: 
  - Search for objects by name (NGC7000, Andromeda, etc.)
  - Manual RA/DEC coordinate entry
  - Adjustable focal length and sensor presets
  - Magnitude limiting slider
- **Distance Measurement**: Calculate angular distances between points
- **Object Information**: Click on objects to see detailed information

### Advanced Features
- **Alt-Az Coordinate Mode**: Realistic horizon-based view showing sky as seen from observer location
  - Polaris appears at correct altitude based on observer latitude
  - Proper orientation (up=zenith, correct east/west)
  - Free-form dragging in Alt-Az space
- **Earth Rotation Simulation**: 
  - Real-time sidereal tracking at 15.041 arcsec/sec
  - Adjustable speed multipliers (0.5x to 1000x)
  - Observer location settings with presets
  - Drift rate display in arcseconds and pixels
- **Time Control**:
  - Clickable time overlay with adjustment dialog
  - UTC and local time display
  - Local Sidereal Time (LST) calculation
  - Timezone automatically calculated from longitude
- **Enhanced Grid Display**:
  - Color-coded RA (green) and DEC (red) lines
  - Stereographic projection for proper polar convergence
  - Celestial pole markers (NCP/SCP)
  - Celestial equator highlighting

### Mount Testing Features
- **Target Marker**: Set GoTo target coordinates with offset distance display
- **Camera FOV Overlay**: Yellow rectangle showing your camera's field of view
- **Enhanced Reticle**: Three styles (crosshair, circle, target) for centering verification
- **Coordinate Readout**: Live RA/DEC display at cursor position
- **Star Brightness Control**: Adjustable brightness (0.5x to 3x) for better camera visibility
- **Wide Context View**: Simulator automatically shows 2.5x wider view than camera FOV

## Installation

### Using Docker (Recommended)

```bash
# Build the image
docker build -t sky-simulator .

# Run with X11 forwarding (Linux)
docker run -it --rm \
    -e DISPLAY=$DISPLAY \
    -v /tmp/.X11-unix:/tmp/.X11-unix \
    sky-simulator

# Run with X11 forwarding (Windows with VcXsrv)
docker run -it --rm \
    -e DISPLAY=host.docker.internal:0 \
    sky-simulator
```

### Using Docker Compose

```bash
# Linux with X11
docker compose up sky-simulator

# Windows with VcXsrv
docker compose --profile windows up sky-simulator-windows

# WSL2 with WSLg (Wayland)
docker compose --profile wsl2 up sky-simulator-wsl2
```

### WSL2 with Wayland (WSLg)

WSL2 with WSLg provides native GUI support through Wayland. The application supports this environment:

```bash
# Using docker compose (recommended for WSL2)
docker compose --profile wsl2 up sky-simulator-wsl2

# Or manually with docker run
docker run -it --rm \
    -e DISPLAY=$DISPLAY \
    -e WAYLAND_DISPLAY=$WAYLAND_DISPLAY \
    -e XDG_RUNTIME_DIR=/mnt/wslg/runtime-dir \
    -e GDK_BACKEND=x11 \
    -v /tmp/.X11-unix:/tmp/.X11-unix \
    -v /mnt/wslg:/mnt/wslg \
    --network host \
    sky-simulator
```

**Note**: WSLg uses XWayland for X11 applications like tkinter. The `GDK_BACKEND=x11` ensures compatibility.

### Running Locally

```bash
# Install dependencies (only tkinter required, usually comes with Python)
pip install -r requirements.txt

# Run the application
python run_sky_simulator.py

# Or as a module
python -m sky_simulator
```

## Usage

### Target Selection

1. Enter an object ID in the "Object ID" field (e.g., `NGC7000`, `NGC224`, `ALPHERATZ`)
2. Click "Go to Target" or press Enter
3. The view will center on the object and show its information

### Manual Navigation

1. Enter RA in hours (0-24) and DEC in degrees (-90 to +90)
2. Click "Go to RA/DEC" to center on those coordinates

### Optics Settings

- **Focal Length**: Adjust from 10mm to 2000mm (or use mouse wheel to zoom)
- **Sensor Presets**: Select from common sensor sizes
- **Custom Size**: Enter custom sensor dimensions

### Display Options

- **Magnitude Limit**: Filter objects by brightness
- **Show Labels**: Toggle object name labels
- **Show Stars/DSOs**: Filter object types
- **Equatorial Grid**: Toggle coordinate grid overlay
- **Diffraction Spikes**: Configure star appearance (4, 6, or 8 spikes)

### Distance Measurement

1. Click "Start Measuring"
2. Click on the sky to place measurement points
3. The angular distance is displayed in degrees, arcminutes, and arcseconds
4. Click "Clear Points" to reset

### Earth Rotation Simulation

1. Set your observer location (latitude/longitude) or choose a preset
2. Enable "Simulate Rotation" checkbox
3. Adjust speed multiplier for faster motion
4. View real-time drift rates and Local Sidereal Time
5. Click on time display to adjust date/time

### Mount Testing (GoTo Verification)

1. **Setup Camera FOV**:
   - Set your lens focal length in "Optics" section
   - Enable "Show Camera FOV Rectangle" in "Mount Testing"
   - Yellow rectangle shows what your camera sees
2. **Set Target Marker**:
   - Enter target RA/DEC or click "Use Center"
   - Click "Set Target" to place green marker
   - Marker shows exact offset distance from center
3. **Test GoTo**:
   - Command your mount to GoTo the same coordinates
   - Point your camera/lens at the monitor
   - Verify target marker appears centered in your camera view
   - Offset display shows GoTo accuracy

## Coordinate System

The application uses the J2000 epoch equatorial coordinate system:

- **Right Ascension (RA)**: 0-24 hours, increases eastward
- **Declination (DEC)**: -90° to +90°, positive is north

## Object Types

| Symbol | Type | Color |
|--------|------|-------|
| ● | Star | White |
| ⬭ | Galaxy | Red |
| ▢ | Nebula | Green |
| ◯ | Open Cluster | Blue |
| ⊕ | Globular Cluster | Yellow |
| ⊙ | Planetary Nebula | Purple |

## Project Structure

```
sky_simulator/
├── __init__.py
├── __main__.py
├── catalogs/
│   ├── __init__.py
│   └── catalog_loader.py
├── models/
│   ├── __init__.py
│   └── celestial_objects.py
├── ui/
│   ├── __init__.py
│   ├── control_panel.py
│   ├── main_window.py
│   └── sky_canvas.py
└── utils/
    ├── __init__.py
    ├── coordinates.py
    └── fov_calculator.py
```
