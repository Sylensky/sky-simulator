"""
Control panel UI component for the sky simulator.
Provides controls for target selection, optics, display options, and measurements.
"""

import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional, Dict, Any
import re

from ..models.celestial_objects import SENSOR_PRESETS, CelestialObject
from ..utils.coordinates import CoordinateUtils


class ControlPanel:
    """
    Control panel widget providing all user controls.
    
    Sections:
    - Target selection (object search, manual RA/DEC)
    - Optics settings (focal length, sensor size)
    - Display options (magnitude limit, labels, filters)
    - Distance measurement tools
    - Object information display
    """
    
    def __init__(self, parent: tk.Widget):
        """Initialize the control panel"""
        self.parent = parent
        
        # Callbacks
        self.on_goto_target: Optional[Callable[[str], None]] = None
        self.on_goto_coords: Optional[Callable[[float, float], None]] = None
        self.on_optics_change: Optional[Callable[[float, float, float], None]] = None
        self.on_display_change: Optional[Callable[[], None]] = None
        self.on_measure_toggle: Optional[Callable[[bool], None]] = None
        self.on_clear_measure: Optional[Callable[[], None]] = None
        
        # Create outer frame container
        self.frame = ttk.LabelFrame(parent, text="Controls", width=300)
        self.frame.pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=5)
        self.frame.pack_propagate(False)
        
        # Create canvas for scrolling
        self._canvas = tk.Canvas(self.frame, highlightthickness=0, width=280)
        self._scrollbar = ttk.Scrollbar(self.frame, orient=tk.VERTICAL, command=self._canvas.yview)
        
        # Create inner frame for all controls
        self._inner_frame = ttk.Frame(self._canvas)
        
        # Configure canvas scrolling
        self._canvas_window = self._canvas.create_window((0, 0), window=self._inner_frame, anchor=tk.NW)
        self._canvas.configure(yscrollcommand=self._scrollbar.set)
        
        # Pack scrollbar and canvas
        self._scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self._canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Bind events for scrolling
        self._inner_frame.bind('<Configure>', self._on_frame_configure)
        self._canvas.bind('<Configure>', self._on_canvas_configure)
        
        # Enable mouse wheel scrolling
        self._canvas.bind('<Enter>', self._bind_mousewheel)
        self._canvas.bind('<Leave>', self._unbind_mousewheel)
        
        # Build UI sections (now using self._inner_frame as parent)
        self._build_target_section()
        self._build_optics_section()
        self._build_display_section()
        self._build_rotation_section()
        self._build_testing_section()  # New testing jig section
        self._build_measurement_section()
        self._build_info_section()
    
    def _on_frame_configure(self, event=None):
        """Update scroll region when inner frame size changes"""
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))
    
    def _on_canvas_configure(self, event=None):
        """Update inner frame width when canvas is resized"""
        self._canvas.itemconfig(self._canvas_window, width=event.width)
    
    def _bind_mousewheel(self, event=None):
        """Bind mouse wheel when cursor enters the canvas"""
        self._canvas.bind_all('<MouseWheel>', self._on_mousewheel)
        self._canvas.bind_all('<Button-4>', self._on_mousewheel)  # Linux scroll up
        self._canvas.bind_all('<Button-5>', self._on_mousewheel)  # Linux scroll down
    
    def _unbind_mousewheel(self, event=None):
        """Unbind mouse wheel when cursor leaves the canvas"""
        self._canvas.unbind_all('<MouseWheel>')
        self._canvas.unbind_all('<Button-4>')
        self._canvas.unbind_all('<Button-5>')
    
    def _on_mousewheel(self, event):
        """Handle mouse wheel scrolling"""
        if event.num == 4:  # Linux scroll up
            self._canvas.yview_scroll(-1, "units")
        elif event.num == 5:  # Linux scroll down
            self._canvas.yview_scroll(1, "units")
        else:  # Windows/Mac
            self._canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
    
    def _build_target_section(self):
        """Build target selection controls"""
        target_frame = ttk.LabelFrame(self._inner_frame, text="Target")
        target_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # Object ID entry
        ttk.Label(target_frame, text="Object ID:").pack(anchor=tk.W, padx=5)
        self.target_var = tk.StringVar(value="NGC7000")
        self.target_entry = ttk.Entry(target_frame, textvariable=self.target_var)
        self.target_entry.pack(fill=tk.X, padx=5, pady=2)
        self.target_entry.bind('<Return>', lambda e: self._on_goto_target())
        
        ttk.Button(target_frame, text="Go to Target",
                  command=self._on_goto_target).pack(fill=tk.X, padx=5, pady=2)
        
        # Manual RA/DEC
        ttk.Label(target_frame, text="Manual RA (h m s or decimal):").pack(anchor=tk.W, padx=5, pady=(10, 0))
        self.ra_var = tk.StringVar(value="20h 58m 48.0s")
        ttk.Entry(target_frame, textvariable=self.ra_var).pack(fill=tk.X, padx=5, pady=2)
        
        ttk.Label(target_frame, text="Manual DEC (d m s or decimal):").pack(anchor=tk.W, padx=5)
        self.dec_var = tk.StringVar(value="+44° 19' 48.0\"")
        ttk.Entry(target_frame, textvariable=self.dec_var).pack(fill=tk.X, padx=5, pady=2)
        
        ttk.Button(target_frame, text="Go to RA/DEC",
                  command=self._on_goto_coords).pack(fill=tk.X, padx=5, pady=2)
    
    def _build_optics_section(self):
        """Build optics controls"""
        optics_frame = ttk.LabelFrame(self._inner_frame, text="Optics")
        optics_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # Focal length
        ttk.Label(optics_frame, text="Focal Length (mm):").pack(anchor=tk.W, padx=5)
        self.focal_var = tk.StringVar(value="200")
        ttk.Entry(optics_frame, textvariable=self.focal_var).pack(fill=tk.X, padx=5, pady=2)
        
        self.focal_scale = ttk.Scale(optics_frame, from_=10, to=2000,
                                     orient=tk.HORIZONTAL,
                                     command=self._on_focal_scale)
        self.focal_scale.set(200)
        self.focal_scale.pack(fill=tk.X, padx=5, pady=2)
        
        # Sensor preset
        ttk.Label(optics_frame, text="Sensor Preset:").pack(anchor=tk.W, padx=5, pady=(10, 0))
        self.sensor_preset_var = tk.StringVar(value="Full Frame (36x24mm)")
        sensor_combo = ttk.Combobox(optics_frame, textvariable=self.sensor_preset_var,
                                    values=list(SENSOR_PRESETS.keys()))
        sensor_combo.pack(fill=tk.X, padx=5, pady=2)
        sensor_combo.bind('<<ComboboxSelected>>', self._on_sensor_preset)
        
        # Custom sensor size
        sensor_custom = ttk.Frame(optics_frame)
        sensor_custom.pack(fill=tk.X, padx=5, pady=2)
        
        ttk.Label(sensor_custom, text="W:").pack(side=tk.LEFT)
        self.sensor_w_var = tk.StringVar(value="36.0")
        ttk.Entry(sensor_custom, textvariable=self.sensor_w_var, width=8).pack(side=tk.LEFT, padx=2)
        
        ttk.Label(sensor_custom, text="H:").pack(side=tk.LEFT, padx=(10, 0))
        self.sensor_h_var = tk.StringVar(value="24.0")
        ttk.Entry(sensor_custom, textvariable=self.sensor_h_var, width=8).pack(side=tk.LEFT, padx=2)
    
    def _build_display_section(self):
        """Build display options"""
        display_frame = ttk.LabelFrame(self._inner_frame, text="Display")
        display_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # Magnitude limit
        ttk.Label(display_frame, text="Magnitude Limit:").pack(anchor=tk.W, padx=5)
        self.mag_var = tk.StringVar(value="8.0")
        ttk.Entry(display_frame, textvariable=self.mag_var, width=10).pack(anchor=tk.W, padx=5, pady=2)
        
        self.mag_scale = ttk.Scale(display_frame, from_=1, to=12,
                                   orient=tk.HORIZONTAL,
                                   command=self._on_mag_scale)
        self.mag_scale.set(8)
        self.mag_scale.pack(fill=tk.X, padx=5, pady=2)
        
        # Checkboxes
        self.show_labels_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(display_frame, text="Show Object Labels",
                       variable=self.show_labels_var,
                       command=self._on_display_change).pack(anchor=tk.W, padx=5)
        
        self.show_stars_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(display_frame, text="Show Stars",
                       variable=self.show_stars_var,
                       command=self._on_display_change).pack(anchor=tk.W, padx=5)
        
        self.show_dso_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(display_frame, text="Show DSOs",
                       variable=self.show_dso_var,
                       command=self._on_display_change).pack(anchor=tk.W, padx=5)
        
        self.show_grid_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(display_frame, text="Equatorial Grid",
                       variable=self.show_grid_var,
                       command=self._on_display_change).pack(anchor=tk.W, padx=5)
        
        # Star appearance options
        ttk.Separator(display_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=5, pady=5)
        ttk.Label(display_frame, text="Star Appearance:").pack(anchor=tk.W, padx=5)
        
        self.show_spikes_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(display_frame, text="Diffraction Spikes",
                       variable=self.show_spikes_var,
                       command=self._on_display_change).pack(anchor=tk.W, padx=5)
        
        # Spike count
        spike_frame = ttk.Frame(display_frame)
        spike_frame.pack(fill=tk.X, padx=5, pady=2)
        ttk.Label(spike_frame, text="Spikes:").pack(side=tk.LEFT)
        self.spike_count_var = tk.StringVar(value="4")
        spike_combo = ttk.Combobox(spike_frame, textvariable=self.spike_count_var,
                                   values=["4", "6", "8"], width=5)
        spike_combo.pack(side=tk.LEFT, padx=5)
        spike_combo.bind('<<ComboboxSelected>>', lambda e: self._on_display_change())
        
        ttk.Label(spike_frame, text="Angle:").pack(side=tk.LEFT, padx=(10, 0))
        self.spike_angle_var = tk.StringVar(value="45")
        angle_combo = ttk.Combobox(spike_frame, textvariable=self.spike_angle_var,
                                   values=["0", "45", "30", "60"], width=5)
        angle_combo.pack(side=tk.LEFT, padx=5)
        angle_combo.bind('<<ComboboxSelected>>', lambda e: self._on_display_change())
    
    def _build_rotation_section(self):
        """Build Earth rotation simulation controls"""
        rotation_frame = ttk.LabelFrame(self._inner_frame, text="Earth Rotation")
        rotation_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # Observer location
        ttk.Label(rotation_frame, text="Observer Location:").pack(anchor=tk.W, padx=5)
        
        # Location preset
        self.location_preset_var = tk.StringVar(value="Custom")
        location_presets = [
            "Custom",
            "Greenwich, UK (51.5°N, 0°)",
            "New York, USA (40.7°N, 74°W)",
            "Los Angeles, USA (34.1°N, 118°W)",
            "Sydney, Australia (33.9°S, 151°E)",
            "Tokyo, Japan (35.7°N, 140°E)",
            "Cape Town, SA (33.9°S, 18°E)",
            "Reykjavik, Iceland (64.1°N, 22°W)",
            "Equator (0°, 0°)",
        ]
        location_combo = ttk.Combobox(rotation_frame, textvariable=self.location_preset_var,
                                      values=location_presets, width=22)
        location_combo.pack(fill=tk.X, padx=5, pady=2)
        location_combo.bind('<<ComboboxSelected>>', self._on_location_preset)
        
        # Latitude/Longitude entries
        loc_frame = ttk.Frame(rotation_frame)
        loc_frame.pack(fill=tk.X, padx=5, pady=2)
        
        ttk.Label(loc_frame, text="Lat:").pack(side=tk.LEFT)
        self.latitude_var = tk.StringVar(value="51.5")  # Default: Greenwich
        ttk.Entry(loc_frame, textvariable=self.latitude_var, width=8).pack(side=tk.LEFT, padx=2)
        
        ttk.Label(loc_frame, text="Lon:").pack(side=tk.LEFT, padx=(5, 0))
        self.longitude_var = tk.StringVar(value="0.0")
        ttk.Entry(loc_frame, textvariable=self.longitude_var, width=8).pack(side=tk.LEFT, padx=2)
        
        # Enable/disable rotation
        self.rotation_enabled_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(rotation_frame, text="Simulate Rotation",
                       variable=self.rotation_enabled_var,
                       command=self._on_rotation_toggle).pack(anchor=tk.W, padx=5, pady=(5, 0))
        
        # Tracking mode
        mode_frame = ttk.Frame(rotation_frame)
        mode_frame.pack(fill=tk.X, padx=5, pady=(5, 0))
        ttk.Label(mode_frame, text="Mode:").pack(side=tk.LEFT)
        self.tracking_mode_var = tk.StringVar(value="Field Rotation")
        mode_combo = ttk.Combobox(mode_frame, textvariable=self.tracking_mode_var,
                                 values=["Field Rotation", "Equatorial (Tracked)", "RA Drift"],
                                 width=24, state="readonly")
        mode_combo.pack(side=tk.LEFT, padx=5)
        mode_combo.bind('<<ComboboxSelected>>', lambda e: self._on_tracking_mode_change())
        
        # Reverse direction
        self.rotation_reverse_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(rotation_frame, text="Reverse Direction",
                       variable=self.rotation_reverse_var,
                       command=self._on_rotation_reverse_change).pack(anchor=tk.W, padx=5, pady=(2, 0))
        
        # Speed multiplier
        speed_frame = ttk.Frame(rotation_frame)
        speed_frame.pack(fill=tk.X, padx=5, pady=2)
        ttk.Label(speed_frame, text="Speed:").pack(side=tk.LEFT)
        self.rotation_speed_var = tk.StringVar(value="1x")
        speed_combo = ttk.Combobox(speed_frame, textvariable=self.rotation_speed_var,
                                   values=["0.5x", "1x", "2x", "5x", "10x", "30x", "60x", "100x", "500x", "1000x"],
                                   width=6)
        speed_combo.pack(side=tk.LEFT, padx=5)
        speed_combo.bind('<<ComboboxSelected>>', lambda e: self._on_rotation_speed_change())
        
        # Drift info display
        self.drift_label = ttk.Label(rotation_frame, text="Drift: -- \"/sec")
        self.drift_label.pack(anchor=tk.W, padx=5, pady=2)
        
        # Callbacks
        self.on_rotation_toggle: Optional[Callable[[bool], None]] = None
        self.on_rotation_speed_change: Optional[Callable[[float], None]] = None
        self.on_location_change: Optional[Callable[[float, float], None]] = None
    
    def _build_testing_section(self):
        """Build mount testing jig controls"""
        test_frame = ttk.LabelFrame(self._inner_frame, text="Mount Testing")
        test_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # Target Marker section
        ttk.Label(test_frame, text="GoTo Target Marker:", font=('Arial', 9, 'bold')).pack(anchor=tk.W, padx=5, pady=(5, 2))
        
        # Target RA/DEC entry
        target_coords = ttk.Frame(test_frame)
        target_coords.pack(fill=tk.X, padx=5, pady=2)
        
        ttk.Label(target_coords, text="RA:").pack(side=tk.LEFT)
        self.target_ra_var = tk.StringVar(value="0h 0m 0s")
        ttk.Entry(target_coords, textvariable=self.target_ra_var, width=12).pack(side=tk.LEFT, padx=2)
        
        ttk.Label(target_coords, text="DEC:").pack(side=tk.LEFT, padx=(5, 0))
        self.target_dec_var = tk.StringVar(value="+0° 0' 0\"")
        ttk.Entry(target_coords, textvariable=self.target_dec_var, width=12).pack(side=tk.LEFT, padx=2)
        
        # Set/Clear target buttons
        target_btns = ttk.Frame(test_frame)
        target_btns.pack(fill=tk.X, padx=5, pady=2)
        ttk.Button(target_btns, text="Set Target", command=self._on_set_target).pack(side=tk.LEFT, padx=2)
        ttk.Button(target_btns, text="Clear Target", command=self._on_clear_target).pack(side=tk.LEFT, padx=2)
        ttk.Button(target_btns, text="Use Center", command=self._on_use_center_as_target).pack(side=tk.LEFT, padx=2)
        
        # Separator before polar alignment section
        ttk.Separator(test_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=5, pady=5)
        
        # Polar Alignment section
        ttk.Label(test_frame, text="Polar Alignment:", font=('Arial', 9, 'bold')).pack(anchor=tk.W, padx=5, pady=(0, 2))
        
        # Camera angle input
        camera_angle_frame = ttk.Frame(test_frame)
        camera_angle_frame.pack(fill=tk.X, padx=5, pady=2)
        ttk.Label(camera_angle_frame, text="Camera Angle:").pack(side=tk.LEFT)
        self.camera_angle_var = tk.DoubleVar(value=63.0)
        camera_angle_spin = ttk.Spinbox(camera_angle_frame, from_=0, to=90, increment=1,
                                       textvariable=self.camera_angle_var, width=8)
        camera_angle_spin.pack(side=tk.LEFT, padx=2)
        ttk.Label(camera_angle_frame, text="° from pole").pack(side=tk.LEFT, padx=2)
        
        # Monitor size configuration
        monitor_frame = ttk.Frame(test_frame)
        monitor_frame.pack(fill=tk.X, padx=5, pady=2)
        ttk.Label(monitor_frame, text="Monitor Size:").pack(side=tk.LEFT)
        self.monitor_size_var = tk.StringVar(value="27\"")
        monitor_combo = ttk.Combobox(monitor_frame, textvariable=self.monitor_size_var,
                                    values=["24\"", "27\"", "32\"", "34\"", "43\""],
                                    width=8, state="readonly")
        monitor_combo.pack(side=tk.LEFT, padx=2)
        monitor_combo.bind('<<ComboboxSelected>>', lambda e: self._on_monitor_size_change())
        
        # Viewing distance input
        distance_frame = ttk.Frame(test_frame)
        distance_frame.pack(fill=tk.X, padx=5, pady=2)
        ttk.Label(distance_frame, text="View Distance:").pack(side=tk.LEFT)
        self.viewing_distance_var = tk.DoubleVar(value=270.0)
        distance_spin = ttk.Spinbox(distance_frame, from_=30, to=500, increment=10,
                                   textvariable=self.viewing_distance_var, width=8)
        distance_spin.pack(side=tk.LEFT, padx=2)
        ttk.Label(distance_frame, text="cm").pack(side=tk.LEFT, padx=2)
        distance_spin.bind('<Return>', lambda e: self._on_viewing_distance_change())
        distance_spin.bind('<FocusOut>', lambda e: self._on_viewing_distance_change())
        
        # Quick navigation
        nav_btns = ttk.Frame(test_frame)
        nav_btns.pack(fill=tk.X, padx=5, pady=2)
        ttk.Button(nav_btns, text="Go to Pole", command=self._on_goto_pole, width=12).pack(side=tk.LEFT, padx=2)
        ttk.Button(nav_btns, text="Pole in Corner", command=self._on_pole_in_corner, width=12).pack(side=tk.LEFT, padx=2)
        
        # Reticle style
        ttk.Separator(test_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=5, pady=5)
        ttk.Label(test_frame, text="Reticle Style:", font=('Arial', 9, 'bold')).pack(anchor=tk.W, padx=5, pady=(0, 2))
        
        reticle_frame = ttk.Frame(test_frame)
        reticle_frame.pack(fill=tk.X, padx=5, pady=2)
        
        self.show_reticle_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(reticle_frame, text="Show", variable=self.show_reticle_var,
                       command=self._on_testing_change).pack(side=tk.LEFT)
        
        self.reticle_style_var = tk.StringVar(value="crosshair")
        reticle_combo = ttk.Combobox(reticle_frame, textvariable=self.reticle_style_var,
                                     values=["crosshair", "circle", "target"], width=10)
        reticle_combo.pack(side=tk.LEFT, padx=5)
        reticle_combo.bind('<<ComboboxSelected>>', lambda e: self._on_testing_change())
        
        # Camera FOV Rectangle - uses current optics settings
        ttk.Separator(test_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=5, pady=5)
        ttk.Label(test_frame, text="Camera FOV Overlay:", font=('Arial', 9, 'bold')).pack(anchor=tk.W, padx=5, pady=(0, 2))
        
        self.show_fov_rect_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(test_frame, text="Show Camera FOV Rectangle",
                       variable=self.show_fov_rect_var,
                       command=self._on_testing_change).pack(anchor=tk.W, padx=5)
        
        # FOV info label (calculated from optics)
        self.fov_info_label = ttk.Label(test_frame, text="FOV: (uses Optics settings)", font=('Arial', 8))
        self.fov_info_label.pack(anchor=tk.W, padx=5, pady=2)
        
        # Cursor coords display
        ttk.Separator(test_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=5, pady=5)
        self.show_cursor_coords_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(test_frame, text="Show Cursor Coordinates",
                       variable=self.show_cursor_coords_var,
                       command=self._on_testing_change).pack(anchor=tk.W, padx=5)
        
        # Star brightness
        ttk.Separator(test_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=5, pady=5)
        ttk.Label(test_frame, text="Star Brightness:", font=('Arial', 9, 'bold')).pack(anchor=tk.W, padx=5, pady=(0, 2))
        
        self.brightness_var = tk.DoubleVar(value=1.0)
        brightness_scale = ttk.Scale(test_frame, from_=0.5, to=3.0,
                                     variable=self.brightness_var,
                                     orient=tk.HORIZONTAL,
                                     command=lambda v: self._on_testing_change())
        brightness_scale.pack(fill=tk.X, padx=5, pady=2)
        
        # Callbacks for testing features
        self.on_testing_change: Optional[Callable[[], None]] = None
        self.on_set_target: Optional[Callable[[float, float, str], None]] = None
        self.on_clear_target: Optional[Callable[[], None]] = None
        self.on_use_center_as_target: Optional[Callable[[], None]] = None
    
    def _on_location_preset(self, event=None):
        """Handle location preset selection"""
        preset = self.location_preset_var.get()
        locations = {
            "Greenwich, UK (51.5°N, 0°)": (51.5, 0.0),
            "New York, USA (40.7°N, 74°W)": (40.7, -74.0),
            "Los Angeles, USA (34.1°N, 118°W)": (34.1, -118.2),
            "Sydney, Australia (33.9°S, 151°E)": (-33.9, 151.2),
            "Tokyo, Japan (35.7°N, 140°E)": (35.7, 139.7),
            "Cape Town, SA (33.9°S, 18°E)": (-33.9, 18.4),
            "Reykjavik, Iceland (64.1°N, 22°W)": (64.1, -21.9),
            "Equator (0°, 0°)": (0.0, 0.0),
        }
        if preset in locations:
            lat, lon = locations[preset]
            self.latitude_var.set(str(lat))
            self.longitude_var.set(str(lon))
            if self.on_location_change:
                self.on_location_change(lat, lon)

    def _build_measurement_section(self):
        """Build distance measurement controls"""
        measure_frame = ttk.LabelFrame(self._inner_frame, text="Distance Measurement")
        measure_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.measure_btn = ttk.Button(measure_frame, text="Start Measuring",
                                      command=self._on_toggle_measure)
        self.measure_btn.pack(fill=tk.X, padx=5, pady=2)
        
        ttk.Button(measure_frame, text="Clear Points",
                  command=self._on_clear_measure).pack(fill=tk.X, padx=5, pady=2)
        
        self.distance_label = ttk.Label(measure_frame, text="Click on sky to measure")
        self.distance_label.pack(anchor=tk.W, padx=5, pady=5)
        
        self._measuring = False
    
        # Apply All Settings button (at end of measurement section, before info)
        ttk.Button(self._inner_frame, text="Apply All Settings",
                  command=self._on_apply_optics).pack(fill=tk.X, padx=5, pady=10)
    
    def _build_info_section(self):
        """Build object information display"""
        info_frame = ttk.LabelFrame(self._inner_frame, text="Object Info")
        info_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.info_text = tk.Text(info_frame, height=10, width=30, state=tk.DISABLED)
        self.info_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
    
    # Public methods
    def get_target(self) -> str:
        """Get current target name"""
        return self.target_var.get().strip().upper()
    
    def get_coords(self) -> tuple:
        """Get manual RA/DEC coordinates, parsing from h m s or decimal format"""
        ra = self._parse_ra(self.ra_var.get())
        dec = self._parse_dec(self.dec_var.get())
        return ra, dec
    
    def _parse_ra(self, ra_str: str) -> Optional[float]:
        """
        Parse RA from various formats to decimal hours.
        
        Supports:
        - Decimal: "20.98"
        - HMS: "20h 58m 48.0s" or "20h58m48s" or "20:58:48"
        """
        ra_str = ra_str.strip()
        
        # Try decimal first
        try:
            return float(ra_str)
        except ValueError:
            pass
        
        # Try HMS format: "20h 58m 48.0s" or "20h58m48s"
        hms_pattern = r'(\d+)\s*h\s*(\d+)\s*m\s*([\d.]+)\s*s?'
        match = re.match(hms_pattern, ra_str, re.IGNORECASE)
        if match:
            h, m, s = match.groups()
            return float(h) + float(m) / 60.0 + float(s) / 3600.0
        
        # Try colon format: "20:58:48"
        colon_pattern = r'(\d+):(\d+):([\d.]+)'
        match = re.match(colon_pattern, ra_str)
        if match:
            h, m, s = match.groups()
            return float(h) + float(m) / 60.0 + float(s) / 3600.0
        
        return None
    
    def _parse_dec(self, dec_str: str) -> Optional[float]:
        """
        Parse DEC from various formats to decimal degrees.
        
        Supports:
        - Decimal: "44.33" or "+44.33" or "-44.33"
        - DMS: "+44° 19' 48.0\"" or "44d 19m 48s" or "44:19:48"
        """
        dec_str = dec_str.strip()
        
        # Try decimal first
        try:
            return float(dec_str)
        except ValueError:
            pass
        
        # Determine sign
        sign = 1
        if dec_str.startswith('-'):
            sign = -1
            dec_str = dec_str[1:]
        elif dec_str.startswith('+'):
            dec_str = dec_str[1:]
        
        # Try DMS format: "44° 19' 48.0"" or "44°19'48""
        dms_pattern = r'(\d+)\s*[°d]\s*(\d+)\s*[\'m]\s*([\d.]+)\s*[\"s]?'
        match = re.match(dms_pattern, dec_str, re.IGNORECASE)
        if match:
            d, m, s = match.groups()
            return sign * (float(d) + float(m) / 60.0 + float(s) / 3600.0)
        
        # Try colon format: "44:19:48"
        colon_pattern = r'(\d+):(\d+):([\d.]+)'
        match = re.match(colon_pattern, dec_str)
        if match:
            d, m, s = match.groups()
            return sign * (float(d) + float(m) / 60.0 + float(s) / 3600.0)
        
        return None
    
    def get_optics(self) -> Dict[str, float]:
        """Get optics settings"""
        try:
            return {
                'focal_length': float(self.focal_var.get()),
                'sensor_width': float(self.sensor_w_var.get()),
                'sensor_height': float(self.sensor_h_var.get())
            }
        except ValueError:
            return None
    
    def get_display_options(self) -> Dict[str, Any]:
        """Get display options"""
        return {
            'mag_limit': float(self.mag_var.get()),
            'show_labels': self.show_labels_var.get(),
            'show_stars': self.show_stars_var.get(),
            'show_dso': self.show_dso_var.get(),
            'show_grid': self.show_grid_var.get(),
            'show_spikes': self.show_spikes_var.get(),
            'spike_count': int(self.spike_count_var.get()),
            'spike_angle': int(self.spike_angle_var.get())
        }
    
    def set_coords(self, ra: float, dec: float):
        """Set the coordinate display values in h m s / d m s format"""
        self.ra_var.set(CoordinateUtils.format_ra(ra))
        self.dec_var.set(CoordinateUtils.format_dec(dec))
    
    def set_focal_length(self, focal: float):
        """Set focal length display"""
        self.focal_var.set(f"{focal:.0f}")
        self.focal_scale.set(focal)
    
    def update_distance_display(self, text: str):
        """Update the distance measurement display"""
        self.distance_label.config(text=text)
    
    def show_object_info(self, obj: CelestialObject):
        """Display object information"""
        self.info_text.config(state=tk.NORMAL)
        self.info_text.delete(1.0, tk.END)
        
        info = f"ID: {obj.id}\n"
        if obj.name and obj.name != obj.id:
            info += f"Name: {obj.name}\n"
        info += f"Type: {obj.object_type_enum.display_name}\n"
        info += f"Magnitude: {obj.magnitude:.2f}\n"
        info += f"\nCoordinates (J2000):\n"
        info += f"  RA:  {obj.format_ra()}\n"
        info += f"       ({obj.ra_hours:.6f}h)\n"
        info += f"  DEC: {obj.format_dec()}\n"
        info += f"       ({obj.dec_degrees:.4f} deg)\n"
        
        self.info_text.insert(tk.END, info)
        self.info_text.config(state=tk.DISABLED)
    
    def clear_object_info(self):
        """Clear the object info display"""
        self.info_text.config(state=tk.NORMAL)
        self.info_text.delete(1.0, tk.END)
        self.info_text.config(state=tk.DISABLED)
    
    # Event handlers
    def _on_goto_target(self):
        if self.on_goto_target:
            self.on_goto_target(self.get_target())
    
    def _on_goto_coords(self):
        ra, dec = self.get_coords()
        if ra is not None and self.on_goto_coords:
            self.on_goto_coords(ra, dec)
    
    def _on_focal_scale(self, value):
        self.focal_var.set(f"{float(value):.0f}")
        self._on_apply_optics()
    
    def _on_sensor_preset(self, event):
        preset_name = self.sensor_preset_var.get()
        if preset_name in SENSOR_PRESETS:
            preset = SENSOR_PRESETS[preset_name]
            self.sensor_w_var.set(str(preset.width_mm))
            self.sensor_h_var.set(str(preset.height_mm))
            if preset_name != "Custom":
                self._on_apply_optics()
    
    def _on_mag_scale(self, value):
        self.mag_var.set(f"{float(value):.1f}")
        self._on_display_change()
    
    def _on_apply_optics(self):
        if self.on_optics_change:
            optics = self.get_optics()
            if optics:
                self.on_optics_change(
                    optics['focal_length'],
                    optics['sensor_width'],
                    optics['sensor_height']
                )
    
    def _on_display_change(self):
        if self.on_display_change:
            self.on_display_change()
    
    def _on_toggle_measure(self):
        self._measuring = not self._measuring
        if self._measuring:
            self.measure_btn.config(text="Stop Measuring")
        else:
            self.measure_btn.config(text="Start Measuring")
        
        if self.on_measure_toggle:
            self.on_measure_toggle(self._measuring)
    
    def _on_clear_measure(self):
        if self.on_clear_measure:
            self.on_clear_measure()
    
    def _on_rotation_toggle(self):
        if self.on_rotation_toggle:
            self.on_rotation_toggle(self.rotation_enabled_var.get())
    
    def _on_rotation_speed_change(self):
        if self.on_rotation_speed_change:
            speed = self.get_rotation_speed()
            self.on_rotation_speed_change(speed)
    
    def _on_rotation_reverse_change(self):
        """Handle rotation direction change"""
        if self.on_rotation_speed_change:
            speed = self.get_rotation_speed()
            self.on_rotation_speed_change(speed)
    
    def _on_tracking_mode_change(self):
        """Handle tracking mode change"""
        if self.on_rotation_speed_change:
            speed = self.get_rotation_speed()
            self.on_rotation_speed_change(speed)
    
    def get_rotation_enabled(self) -> bool:
        """Get whether rotation simulation is enabled"""
        return self.rotation_enabled_var.get()
    
    def get_tracking_mode(self) -> str:
        """Get tracking mode: 'field_rotation', 'equatorial', or 'ra_drift'"""
        mode = self.tracking_mode_var.get()
        if "Field Rotation" in mode:
            return "field_rotation"
        elif "Equatorial" in mode:
            return "equatorial"
        elif "RA Drift" in mode:
            return "ra_drift"
        return "field_rotation"
    
    def get_rotation_speed(self) -> float:
        """Get rotation speed multiplier (negative if reversed)"""
        speed_str = self.rotation_speed_var.get().replace('x', '')
        try:
            speed = float(speed_str)
            if self.rotation_reverse_var.get():
                speed = -speed
            return speed
        except ValueError:
            return 1.0
    
    def update_drift_display(self, drift_arcsec_per_sec: float, focal_length: float):
        """Update the drift rate display"""
        # Calculate pixel drift based on a typical pixel size (around 4 microns)
        # Plate scale = 206265 / focal_length_mm arcsec/mm
        # For 4 micron pixels: arcsec/pixel = plate_scale * 0.004
        plate_scale = 206265 / focal_length  # arcsec/mm
        arcsec_per_pixel = plate_scale * 0.004  # assuming 4 micron pixels
        pixel_drift_per_sec = drift_arcsec_per_sec / arcsec_per_pixel if arcsec_per_pixel > 0 else 0
        
        self.drift_label.config(
            text=f"Drift: {drift_arcsec_per_sec:.2f}\"/s ({pixel_drift_per_sec:.1f} px/s)"
        )
    
    def get_location(self) -> tuple:
        """Get observer latitude and longitude"""
        try:
            lat = float(self.latitude_var.get())
            lon = float(self.longitude_var.get())
            return lat, lon
        except ValueError:
            return 51.5, 0.0  # Default to Greenwich
    
    def get_camera_angle(self) -> float:
        """Get camera angle from polar axis in degrees"""
        try:
            return float(self.camera_angle_var.get())
        except (ValueError, AttributeError):
            return 63.0  # Default camera angle
    
    def get_monitor_config(self) -> tuple:
        """Get monitor size and viewing distance. Returns (size_inches, distance_cm)"""
        try:
            size_str = self.monitor_size_var.get().replace('"', '')
            size = float(size_str)
            distance = float(self.viewing_distance_var.get())
            return size, distance
        except (ValueError, AttributeError):
            return 27.0, 60.0  # Default: 27" at 60cm
    
    def get_fov_multiplier(self) -> float:
        """
        For realistic projection matching a telescope/camera view:
        The simulator should show EXACTLY what the camera sees (1:1 mapping).
        
        With 300mm lens (6.9° FOV), the simulator shows 6.9°.
        Stars appear at correct angular spacing as through the actual lens.
        
        Returns: Always 1.0 for true-to-life representation.
        The monitor/viewing distance settings are for future use but don't affect FOV.
        """
        # For realistic telescope simulation: show exactly what the camera sees
        # No magnification, no reduction - pure 1:1 mapping
        return 1.0

    # Testing section handlers
    def _on_set_target(self):
        """Handle set target button click"""
        if self.on_set_target:
            ra = self._parse_ra(self.target_ra_var.get())
            dec = self._parse_dec(self.target_dec_var.get())
            if ra is not None and dec is not None:
                self.on_set_target(ra, dec, "GoTo Target")
    
    def _on_clear_target(self):
        """Handle clear target button click"""
        if self.on_clear_target:
            self.on_clear_target()
    
    def _on_use_center_as_target(self):
        """Handle use center as target button click"""
        if self.on_use_center_as_target:
            self.on_use_center_as_target()
    
    def _on_goto_pole(self):
        """Navigate to celestial pole (Polaris for Northern hemisphere)"""
        # Get current latitude to determine which pole
        lat = self.get_location()[0]
        
        if lat >= 0:
            # Northern hemisphere - go to North Celestial Pole (near Polaris)
            # Polaris: RA ≈ 2h 31m 49s, DEC ≈ +89° 15' 51"
            ra = 2.5297  # hours
            dec = 89.264  # degrees
        else:
            # Southern hemisphere - go to South Celestial Pole
            # Sigma Octantis area: RA ≈ 21h, DEC ≈ -89°
            ra = 21.0  # hours
            dec = -89.0  # degrees
        
        # Navigate to pole
        if self.on_goto_coords:
            self.on_goto_coords(ra, dec)
    
    def _on_pole_in_corner(self):
        """Position view based on camera angle from polar axis"""
        # Get current latitude to determine positioning
        lat = self.get_location()[0]
        
        # Get camera angle from user input
        # This means view center DEC = 90° - camera_angle
        # Looking at same RA as Polaris puts pole "above" the center
        camera_angle = self.camera_angle_var.get()
        
        if lat >= 0:
            # Northern hemisphere
            # Polaris RA ≈ 2.5h, so look at same RA
            ra = 2.5  # hours
            dec = 90.0 - camera_angle
        else:
            # Southern hemisphere - position view so SCP is visible
            ra = 21.0  # hours (opposite side of sky)
            dec = -(90.0 - camera_angle)
        
        # Navigate to position
        if self.on_goto_coords:
            self.on_goto_coords(ra, dec)
    
    def _on_testing_change(self):
        """Handle testing settings change"""
        if self.on_testing_change:
            self.on_testing_change()
    
    def _on_monitor_size_change(self):
        """Handle monitor size change"""
        # Trigger optics change to recalculate FOV with new multiplier
        if self.on_optics_change:
            optics = self.get_optics()
            if optics:
                self.on_optics_change(optics['focal_length'], optics['sensor_width'], optics['sensor_height'])
    
    def _on_viewing_distance_change(self):
        """Handle viewing distance change"""
        # Trigger optics change to recalculate FOV with new multiplier
        if self.on_optics_change:
            optics = self.get_optics()
            if optics:
                self.on_optics_change(optics['focal_length'], optics['sensor_width'], optics['sensor_height'])
    
    def get_testing_options(self) -> dict:
        """Get all testing options - FOV uses current optics settings"""
        return {
            'show_reticle': self.show_reticle_var.get(),
            'reticle_style': self.reticle_style_var.get(),
            'show_fov_rect': self.show_fov_rect_var.get(),
            'show_cursor_coords': self.show_cursor_coords_var.get(),
            'brightness': self.brightness_var.get()
        }
    
    def update_fov_info(self, fov_w: float, fov_h: float):
        """Update the FOV info label with current optics FOV"""
        self.fov_info_label.config(text=f"FOV: {fov_w:.2f}° × {fov_h:.2f}°")
    
    def set_target_coords(self, ra: float, dec: float):
        """Set target coordinates display"""
        self.target_ra_var.set(CoordinateUtils.format_ra(ra))
        self.target_dec_var.set(CoordinateUtils.format_dec(dec))
    
    # Settings import/export support
    def set_optics(self, focal: float, sensor_w: float, sensor_h: float):
        """Set optics parameters"""
        self.focal_var.set(str(focal))
        self.sensor_w_var.set(str(sensor_w))
        self.sensor_h_var.set(str(sensor_h))
    
    def set_display_options(self, options: Dict[str, Any]):
        """Set display options from dict"""
        if 'mag_limit' in options:
            self.mag_var.set(str(options['mag_limit']))
        if 'show_labels' in options:
            self.show_labels_var.set(options['show_labels'])
        if 'show_stars' in options:
            self.show_stars_var.set(options['show_stars'])
        if 'show_dso' in options:
            self.show_dso_var.set(options['show_dso'])
        if 'show_grid' in options:
            self.show_grid_var.set(options['show_grid'])
        if 'show_spikes' in options:
            self.show_spikes_var.set(options['show_spikes'])
        if 'spike_count' in options:
            self.spike_count_var.set(str(options['spike_count']))
        if 'spike_angle' in options:
            self.spike_angle_var.set(str(options['spike_angle']))
    
    def set_location(self, lat: float, lon: float):
        """Set observer location"""
        self.latitude_var.set(str(lat))
        self.longitude_var.set(str(lon))
    
    def set_rotation_enabled(self, enabled: bool):
        """Set rotation enabled state"""
        self.rotation_enabled_var.set(enabled)
    
    def set_rotation_speed(self, speed: float):
        """Set rotation speed"""
        self.rotation_speed_var.set(speed)
    
    def set_tracking_mode(self, mode: str):
        """Set tracking mode"""
        mode_map = {
            'radec_polar': "RA-DEC Polar",
            'rotation': "Sky Rotation (Untracked)",
            'equatorial': "Equatorial (Tracked)",
            'untracked': "Fixed Alt-Az"
        }
        if mode in mode_map:
            self.tracking_mode_var.set(mode_map[mode])
    
    def set_testing_options(self, options: Dict[str, Any]):
        """Set testing options from dict"""
        if 'show_reticle' in options:
            self.show_reticle_var.set(options['show_reticle'])
        if 'reticle_style' in options:
            self.reticle_style_var.set(options['reticle_style'])
        if 'show_fov_rect' in options:
            self.show_fov_rect_var.set(options['show_fov_rect'])
        if 'show_cursor_coords' in options:
            self.show_cursor_coords_var.set(options['show_cursor_coords'])
        if 'brightness' in options:
            self.brightness_var.set(options['brightness'])