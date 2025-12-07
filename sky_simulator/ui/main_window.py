"""
Main window for the Night Sky Simulator application.
Coordinates all UI components and application logic.
"""

import math
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from pathlib import Path
from typing import List, Tuple, Optional
from datetime import datetime, timedelta
import os
import sys
import importlib
import json

from ..catalogs.catalog_loader import CatalogManager
from ..models.celestial_objects import CelestialObject
from ..models.tracking_modes import (
    TrackingModeManager, TrackingState, TrackingUpdate,
    create_tracking_manager
)
from ..utils.coordinates import CoordinateUtils
from .sky_canvas import SkyCanvas
from .control_panel import ControlPanel

# Earth's sidereal rotation rate: 360 degrees in 23h 56m 4s = 15.041 arcsec/sec
EARTH_ROTATION_RATE_ARCSEC_PER_SEC = 15.041


class MainWindow:
    """
    Main application window for the Night Sky Simulator.
    
    Coordinates all UI components and manages the application state.
    """
    
    def __init__(self, root: tk.Tk, catalogs_path: Path = None, debug_mode: bool = False):
        """
        Initialize the main window.
        
        Args:
            root: Tkinter root window
            catalogs_path: Path to the catalogs directory
            debug_mode: Enable hot reload functionality
        """
        self.root = root
        self.root.title("Night Sky Simulator" + (" [DEBUG]" if debug_mode else ""))
        self.root.geometry("1400x900")
        self.debug_mode = debug_mode
        
        # Catalog manager
        self.catalog_manager = CatalogManager()
        
        # State
        self.distance_points: List[Tuple[float, float]] = []
        self.measuring_mode = False
        self.selected_object: Optional[CelestialObject] = None
        
        # Tracking mode manager (camera at 63° from polar axis)
        self._tracking_manager = create_tracking_manager(camera_angle=63.0)
        
        # Earth rotation state
        self._rotation_enabled = False
        self._rotation_speed = 1.0  # Multiplier
        self._rotation_timer_id = None
        
        # Observer location (default: Lat 47°N, Lon 9°E)
        self._observer_lat = 47.0
        self._observer_lon = 9.0
        
        # Simulation time (starts at current UTC time)
        self._sim_time = datetime.utcnow()
        self._time_update_id = None
        
        # Camera FOV for testing overlay - will be calculated from optics settings
        self._camera_focal = 200  # Default focal length (matches control panel)
        self._camera_fov_width = 10.3  # Default for 200mm on full frame
        self._camera_fov_height = 6.9
        
        # Build UI
        self._build_ui()
        
        # Load catalogs
        if catalogs_path:
            self._load_catalogs(catalogs_path)
        else:
            # Try to find catalogs relative to this file
            self._auto_find_catalogs()
        
        # Initial view
        self._goto_target("NGC7000")
        
        # Initialize camera FOV from current optics settings
        self._init_camera_fov()
        
        # Initialize time display
        self._update_time_display()
        
        # Setup hot reload if in debug mode
        if self.debug_mode:
            self._setup_hot_reload()
    
    def _init_camera_fov(self):
        """Initialize camera FOV from current optics settings"""
        optics = self.control_panel.get_optics()
        if optics:
            focal = optics['focal_length']
            sensor_w = optics['sensor_width']
            sensor_h = optics['sensor_height']
            
            # Calculate camera FOV
            import math
            self._camera_fov_width = 2 * math.degrees(math.atan(sensor_w / (2 * focal)))
            self._camera_fov_height = 2 * math.degrees(math.atan(sensor_h / (2 * focal)))
            self._camera_focal = focal
            
            # Set simulator to show 2.5x wider view
            simulator_focal = focal / 2.5
            self.sky_canvas.fov_calculator.focal_length = simulator_focal
            
            # Update FOV info display
            self.control_panel.update_fov_info(self._camera_fov_width, self._camera_fov_height)
    
    def _build_ui(self):
        """Build the main UI"""
        # Menu bar
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        
        # Settings menu
        settings_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Settings", menu=settings_menu)
        settings_menu.add_command(label="Export Settings...", command=self._export_settings)
        settings_menu.add_command(label="Import Settings...", command=self._import_settings)
        
        # Help menu
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="Mount Testing Setup Guide", command=self._show_setup_guide)
        help_menu.add_separator()
        help_menu.add_command(label="About", command=self._show_about)
        
        # Main container
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Control panel (left)
        self.control_panel = ControlPanel(main_frame)
        self._connect_control_callbacks()
        
        # Sky view (right)
        view_frame = ttk.LabelFrame(main_frame, text="Sky View")
        view_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.sky_canvas = SkyCanvas(
            view_frame,
            on_click=self._on_canvas_click,
            on_motion=self._on_canvas_motion
        )
        self.sky_canvas.on_zoom_callback = self._on_zoom
        self.sky_canvas.set_on_time_click(self._show_time_dialog)
        
        # Status bars
        self.fov_var = tk.StringVar(value="FOV: calculating...")
        fov_bar = ttk.Label(self.root, textvariable=self.fov_var,
                           relief=tk.SUNKEN, anchor=tk.W)
        fov_bar.pack(side=tk.BOTTOM, fill=tk.X)
        
        self.status_var = tk.StringVar(value="Loading catalogs...")
        status_bar = ttk.Label(self.root, textvariable=self.status_var,
                              relief=tk.SUNKEN, anchor=tk.W)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)
    
    def _connect_control_callbacks(self):
        """Connect control panel callbacks"""
        self.control_panel.on_goto_target = self._goto_target
        self.control_panel.on_goto_coords = self._goto_coords
        self.control_panel.on_optics_change = self._on_optics_change
        self.control_panel.on_display_change = self._update_view
        self.control_panel.on_measure_toggle = self._on_measure_toggle
        self.control_panel.on_clear_measure = self._clear_distance_points
        self.control_panel.on_rotation_toggle = self._on_rotation_toggle
        self.control_panel.on_rotation_speed_change = self._on_rotation_speed_change
        self.control_panel.on_location_change = self._on_location_change
        
        # Testing callbacks
        self.control_panel.on_testing_change = self._on_testing_change
        self.control_panel.on_set_target = self._on_set_target_marker
        self.control_panel.on_clear_target = self._on_clear_target_marker
        self.control_panel.on_use_center_as_target = self._on_use_center_as_target
    
    def _auto_find_catalogs(self):
        """Try to automatically find catalogs directory"""
        # Look relative to this module
        module_path = Path(__file__).resolve()
        
        # Try several possible locations (data/ directory first, then legacy catalogues/)
        possible_paths = [
            Path.cwd() / "data",  # ./data (Docker default)
            module_path.parent.parent.parent / "data",  # sky_simulator/ui -> sky_simulator -> project/data
            module_path.parent.parent.parent.parent / "data",  # One more level up
            Path("/app/data"),  # Docker container path
            # Legacy catalogues paths
            module_path.parent.parent.parent / "catalogues",
            module_path.parent.parent.parent.parent / "catalogues",
            Path.cwd() / "catalogues",
            Path.cwd().parent / "catalogues",
        ]
        
        for path in possible_paths:
            if path.exists():
                self._load_catalogs(path)
                return
        
        messagebox.showwarning("Catalogs Not Found",
                              "Could not find catalogs directory. "
                              "Some features may not work.")
    
    def _load_catalogs(self, path: Path):
        """Load astronomical catalogs"""
        self.status_var.set("Loading catalogs...")
        self.root.update()
        
        if self.catalog_manager.load_all(path):
            status = self.catalog_manager.get_status()
            self.status_var.set(
                f"Loaded {status['ngc_count']} DSOs and {status['bsc5_count']} stars"
            )
            
            # Set objects on canvas
            self.sky_canvas.set_objects(
                self.catalog_manager.ngc_objects,
                self.catalog_manager.stars
            )
            
            # Try to find images directory
            images_path = path / "images"
            if not images_path.exists():
                images_path = path.parent / "images"
            if images_path.exists():
                self.sky_canvas.set_images_path(images_path)
        else:
            self.status_var.set("Error loading catalogs")
    
    def _update_view(self):
        """Update the sky view"""
        options = self.control_panel.get_display_options()
        
        self.sky_canvas.mag_limit = options['mag_limit']
        self.sky_canvas.show_labels = options['show_labels']
        self.sky_canvas.show_grid = options.get('show_grid', True)
        
        # Star appearance options
        self.sky_canvas.show_diffraction_spikes = options.get('show_spikes', True)
        self.sky_canvas.diffraction_spike_count = options.get('spike_count', 4)
        self.sky_canvas.diffraction_spike_rotation = options.get('spike_angle', 45)
        
        self.sky_canvas.render(
            show_stars=options['show_stars'],
            show_dso=options['show_dso']
        )
        
        # Draw distance measurements
        self._draw_distance_measurements()
        
        # Update FOV display with formatted coordinates
        fov = self.sky_canvas.fov_calculator.fov
        ra_formatted = CoordinateUtils.format_ra(self.sky_canvas.center_ra)
        dec_formatted = CoordinateUtils.format_dec(self.sky_canvas.center_dec)
        self.fov_var.set(
            f"FOV: {fov.width_deg:.2f}° x {fov.height_deg:.2f}° | "
            f"Center: RA {ra_formatted}, DEC {dec_formatted}"
        )
    
    def _goto_target(self, target_name: str):
        """Navigate to a named target"""
        obj = self.catalog_manager.find_object(target_name)
        
        if obj:
            # Use tracking mode's goto handler
            state = self._create_tracking_state()
            new_ra, new_dec, reset_rotation = self._tracking_manager.current_mode.on_goto(
                obj.ra_hours, obj.dec_degrees, state
            )
            
            if reset_rotation:
                self.sky_canvas.reset_rotation_angle()
            
            self.sky_canvas.set_center(new_ra, new_dec)
            self.control_panel.set_coords(obj.ra_hours, obj.dec_degrees)
            self._update_view()
            self.control_panel.show_object_info(obj)
            self.selected_object = obj
        else:
            messagebox.showwarning("Not Found",
                                  f"Object '{target_name}' not found in catalogs.")
    
    def _goto_coords(self, ra: float, dec: float):
        """Navigate to specific coordinates"""
        if not 0 <= ra < 24:
            messagebox.showerror("Invalid RA", "RA must be between 0 and 24 hours")
            return
        if not -90 <= dec <= 90:
            messagebox.showerror("Invalid DEC", "DEC must be between -90 and +90 degrees")
            return
        
        # Use tracking mode's goto handler
        state = self._create_tracking_state()
        new_ra, new_dec, reset_rotation = self._tracking_manager.current_mode.on_goto(
            ra, dec, state
        )
        
        if reset_rotation:
            self.sky_canvas.reset_rotation_angle()
        
        self.sky_canvas.set_center(new_ra, new_dec)
        self._update_view()
    
    def _create_tracking_state(self) -> TrackingState:
        """Create a TrackingState from current application state"""
        lat, lon = self.control_panel.get_location()
        lst = self._calculate_lst(self._sim_time, lon)
        
        return TrackingState(
            center_ra=self.sky_canvas.center_ra,
            center_dec=self.sky_canvas.center_dec,
            rotation_angle=self.sky_canvas.get_rotation_angle(),
            lst=lst,
            observer_lat=lat,
            observer_lon=lon
        )
    
    def _on_optics_change(self, focal: float, sensor_w: float, sensor_h: float):
        """Handle optics parameter changes"""
        # Store the camera focal length and calculate camera FOV
        self._camera_focal = focal
        self.sky_canvas.set_optics(focal, sensor_w, sensor_h)
        
        # Get the camera FOV
        fov = self.sky_canvas.fov_calculator.fov
        
        # Store the camera FOV for the rectangle overlay
        self._camera_fov_width = fov.width_deg
        self._camera_fov_height = fov.height_deg
        
        # Set simulator FOV to at least 2.5x the camera FOV for context
        simulator_focal = focal / 2.5  # 2.5x wider view than camera
        self.sky_canvas.fov_calculator.focal_length = simulator_focal
        
        self._update_view()
        self._update_drift_display()
        
        # Update FOV info in testing section (shows camera FOV, not simulator FOV)
        self.control_panel.update_fov_info(self._camera_fov_width, self._camera_fov_height)
        
        # Update FOV rectangle if enabled
        options = self.control_panel.get_testing_options()
        if options['show_fov_rect']:
            self.sky_canvas.set_fov_rectangle(
                enabled=True,
                width_deg=self._camera_fov_width,
                height_deg=self._camera_fov_height
            )
    
    def _on_zoom(self, focal_length: float):
        """Handle zoom (from mouse wheel) - this zooms the simulator view only"""
        # Don't update control panel focal length - that's the camera setting
        # The scroll wheel just zooms the simulator view for navigation
        self._update_view()
        
        # Update drift display since it depends on focal length
        self._update_drift_display()
        
        # Camera FOV stays the same - only simulator view changes
        self.control_panel.update_fov_info(self._camera_fov_width, self._camera_fov_height)
    
    def _on_canvas_click(self, ra: float, dec: float):
        """Handle canvas click"""
        if self.measuring_mode:
            self.distance_points.append((ra, dec))
            self._update_view()
            self._update_distance_display()
            return
        
        # Find nearest object
        nearest = self._find_nearest_object(ra, dec)
        if nearest:
            self.control_panel.show_object_info(nearest)
            self.selected_object = nearest
    
    def _on_canvas_motion(self, ra: float, dec: float):
        """Handle mouse motion over canvas"""
        ra_str = CoordinateUtils.format_ra(ra)
        dec_str = CoordinateUtils.format_dec(dec)
        
        nearest = self._find_nearest_object(ra, dec, max_dist=0.3)
        if nearest:
            name = nearest.name if nearest.name else nearest.id
            self.status_var.set(f"Cursor: RA {ra_str}, DEC {dec_str} | Near: {name}")
        else:
            self.status_var.set(f"Cursor: RA {ra_str}, DEC {dec_str}")
    
    def _on_measure_toggle(self, measuring: bool):
        """Handle measurement mode toggle"""
        self.measuring_mode = measuring
        if measuring:
            self.sky_canvas.set_cursor("crosshair")
            self.control_panel.update_distance_display("Click to add points...")
        else:
            self.sky_canvas.set_cursor("")
    
    def _clear_distance_points(self):
        """Clear all distance measurement points"""
        self.distance_points = []
        self._update_view()
        self.control_panel.update_distance_display("Click 'Start Measuring'")
    
    def _draw_distance_measurements(self):
        """Draw distance measurement overlays"""
        for i, (ra, dec) in enumerate(self.distance_points):
            self.sky_canvas.draw_measurement_point(ra, dec, i + 1)
        
        for i in range(len(self.distance_points) - 1):
            ra1, dec1 = self.distance_points[i]
            ra2, dec2 = self.distance_points[i + 1]
            self.sky_canvas.draw_measurement_line(ra1, dec1, ra2, dec2)
    
    def _update_distance_display(self):
        """Update distance measurement text"""
        if len(self.distance_points) < 2:
            if self.measuring_mode:
                self.control_panel.update_distance_display("Click to add points...")
            return
        
        total_dist = 0
        segments = []
        
        for i in range(len(self.distance_points) - 1):
            ra1, dec1 = self.distance_points[i]
            ra2, dec2 = self.distance_points[i + 1]
            dist = CoordinateUtils.angular_distance(ra1, dec1, ra2, dec2)
            total_dist += dist
            segments.append(f"P{i+1}-P{i+2}: {dist:.4f} deg")
        
        dist_arcmin = CoordinateUtils.degrees_to_arcmin(total_dist)
        dist_arcsec = CoordinateUtils.degrees_to_arcsec(total_dist)
        
        text = f"Total: {total_dist:.4f} deg\n"
        text += f"({dist_arcmin:.2f}' / {dist_arcsec:.1f}\")\n"
        text += "\n".join(segments[-3:])
        
        self.control_panel.update_distance_display(text)
    
    def _find_nearest_object(self, ra: float, dec: float,
                            max_dist: float = 0.5) -> Optional[CelestialObject]:
        """Find the nearest object to given coordinates"""
        options = self.control_panel.get_display_options()
        nearest = None
        min_dist = max_dist
        
        # Check DSOs
        if options['show_dso']:
            for obj in self.catalog_manager.ngc_objects:
                if obj.magnitude <= options['mag_limit'] or obj.magnitude == 0:
                    dist = CoordinateUtils.angular_distance(
                        ra, dec, obj.ra_hours, obj.dec_degrees
                    )
                    if dist < min_dist:
                        min_dist = dist
                        nearest = obj
        
        # Check stars
        if options['show_stars']:
            for star in self.catalog_manager.stars:
                if star.magnitude <= options['mag_limit']:
                    dist = CoordinateUtils.angular_distance(
                        ra, dec, star.ra_hours, star.dec_degrees
                    )
                    if dist < min_dist:
                        min_dist = dist
                        nearest = star
        
        return nearest
    
    def _setup_hot_reload(self):
        """Setup hot reload for debug mode"""
        print("[DEBUG] Hot reload enabled - press F5 to reload modules")
        self.root.bind('<F5>', self._hot_reload)
        self._last_reload_time = 0
    
    def _hot_reload(self, event=None):
        """Reload Python modules for hot reload"""
        import time
        
        # Debounce rapid key presses
        current_time = time.time()
        if current_time - self._last_reload_time < 1.0:
            return
        self._last_reload_time = current_time
        
        print("[DEBUG] Reloading modules...")
        self.status_var.set("Reloading modules...")
        self.root.update()
        
        try:
            # Reload all sky_simulator modules
            modules_to_reload = [
                name for name in sys.modules.keys()
                if name.startswith('sky_simulator')
            ]
            
            # Sort to reload in dependency order (parent modules first)
            modules_to_reload.sort(key=lambda x: x.count('.'))
            
            for module_name in modules_to_reload:
                if module_name in sys.modules:
                    try:
                        importlib.reload(sys.modules[module_name])
                        print(f"  Reloaded: {module_name}")
                    except Exception as e:
                        print(f"  Failed to reload {module_name}: {e}")
            
            # Refresh the view
            self._update_view()
            
            self.status_var.set("Modules reloaded successfully! Press F5 to reload again.")
            print("[DEBUG] Reload complete!")
        except Exception as e:
            self.status_var.set(f"Reload error: {str(e)}")
            print(f"[DEBUG] Reload error: {e}")
    
    def _on_rotation_toggle(self, enabled: bool):
        """Handle Earth rotation toggle"""
        self._rotation_enabled = enabled
        
        if enabled:
            # Reset simulation time to current time when starting
            self._sim_time = datetime.utcnow()
            self._start_rotation()
            self._update_drift_display()
            self._update_time_display()
        else:
            self._stop_rotation()
    
    def _on_rotation_speed_change(self, speed: float):
        """Handle rotation speed change"""
        self._rotation_speed = speed
        self._update_drift_display()
    
    def _on_location_change(self, lat: float, lon: float):
        """Handle observer location change"""
        self._observer_lat = lat
        self._observer_lon = lon
        self._update_time_display()
        self._update_drift_display()
    
    # Testing feature handlers
    def _on_testing_change(self):
        """Handle testing settings change"""
        options = self.control_panel.get_testing_options()
        
        # Update reticle
        self.sky_canvas.set_reticle(
            enabled=options['show_reticle'],
            style=options['reticle_style']
        )
        
        # Update FOV rectangle - uses stored camera FOV (not simulator FOV)
        self.sky_canvas.set_fov_rectangle(
            enabled=options['show_fov_rect'],
            width_deg=self._camera_fov_width,
            height_deg=self._camera_fov_height
        )
        
        # Update FOV info label in control panel (camera FOV)
        self.control_panel.update_fov_info(self._camera_fov_width, self._camera_fov_height)
        
        # Update cursor coords display
        self.sky_canvas.set_cursor_coords_display(options['show_cursor_coords'])
        
        # Update brightness
        self.sky_canvas.set_brightness(options['brightness'])
        
        self._update_view()
    
    def _on_set_target_marker(self, ra: float, dec: float, label: str):
        """Set a target marker at specified coordinates"""
        self.sky_canvas.set_target_marker(ra, dec, label)
        self._update_view()
    
    def _on_clear_target_marker(self):
        """Clear the target marker"""
        self.sky_canvas.clear_target_marker()
        self._update_view()
    
    def _on_use_center_as_target(self):
        """Use current center as target marker"""
        ra = self.sky_canvas.center_ra
        dec = self.sky_canvas.center_dec
        self.sky_canvas.set_target_marker(ra, dec, "GoTo Target")
        self.control_panel.set_target_coords(ra, dec)
        self._update_view()
    
    def _show_time_dialog(self):
        """Show dialog to adjust simulation time"""
        dialog = tk.Toplevel(self.root)
        dialog.title("Adjust Time")
        dialog.geometry("350x280")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        
        # Center on parent
        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - 350) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 280) // 2
        dialog.geometry(f"+{x}+{y}")
        
        # Try to grab focus (may fail in some environments)
        try:
            dialog.grab_set()
        except tk.TclError:
            pass  # Ignore grab errors
        
        # Calculate timezone from longitude
        tz_offset_hours = self._observer_lon / 15.0
        tz_hours = int(tz_offset_hours)
        tz_mins = int(abs(tz_offset_hours - tz_hours) * 60)
        tz_sign = "+" if tz_offset_hours >= 0 else "-"
        tz_str = f"UTC{tz_sign}{abs(tz_hours)}:{tz_mins:02d}"
        
        # Current times
        from datetime import timedelta
        local_time = self._sim_time + timedelta(hours=tz_offset_hours)
        
        # Info label
        ttk.Label(dialog, text=f"Observer Timezone: {tz_str} (based on longitude)",
                 font=('Arial', 9)).pack(pady=(10, 5))
        
        # Date frame
        date_frame = ttk.LabelFrame(dialog, text="Date (UTC)")
        date_frame.pack(fill=tk.X, padx=10, pady=5)
        
        date_inner = ttk.Frame(date_frame)
        date_inner.pack(pady=5)
        
        ttk.Label(date_inner, text="Year:").grid(row=0, column=0, padx=2)
        year_var = tk.StringVar(value=str(self._sim_time.year))
        year_entry = ttk.Entry(date_inner, textvariable=year_var, width=6)
        year_entry.grid(row=0, column=1, padx=2)
        
        ttk.Label(date_inner, text="Month:").grid(row=0, column=2, padx=2)
        month_var = tk.StringVar(value=str(self._sim_time.month))
        month_entry = ttk.Entry(date_inner, textvariable=month_var, width=4)
        month_entry.grid(row=0, column=3, padx=2)
        
        ttk.Label(date_inner, text="Day:").grid(row=0, column=4, padx=2)
        day_var = tk.StringVar(value=str(self._sim_time.day))
        day_entry = ttk.Entry(date_inner, textvariable=day_var, width=4)
        day_entry.grid(row=0, column=5, padx=2)
        
        # Time frame
        time_frame = ttk.LabelFrame(dialog, text="Time (UTC)")
        time_frame.pack(fill=tk.X, padx=10, pady=5)
        
        time_inner = ttk.Frame(time_frame)
        time_inner.pack(pady=5)
        
        ttk.Label(time_inner, text="Hour:").grid(row=0, column=0, padx=2)
        hour_var = tk.StringVar(value=str(self._sim_time.hour))
        hour_entry = ttk.Entry(time_inner, textvariable=hour_var, width=4)
        hour_entry.grid(row=0, column=1, padx=2)
        
        ttk.Label(time_inner, text="Min:").grid(row=0, column=2, padx=2)
        min_var = tk.StringVar(value=str(self._sim_time.minute))
        min_entry = ttk.Entry(time_inner, textvariable=min_var, width=4)
        min_entry.grid(row=0, column=3, padx=2)
        
        ttk.Label(time_inner, text="Sec:").grid(row=0, column=4, padx=2)
        sec_var = tk.StringVar(value=str(self._sim_time.second))
        sec_entry = ttk.Entry(time_inner, textvariable=sec_var, width=4)
        sec_entry.grid(row=0, column=5, padx=2)
        
        # Quick buttons
        quick_frame = ttk.Frame(dialog)
        quick_frame.pack(fill=tk.X, padx=10, pady=5)
        
        def set_now():
            now = datetime.utcnow()
            year_var.set(str(now.year))
            month_var.set(str(now.month))
            day_var.set(str(now.day))
            hour_var.set(str(now.hour))
            min_var.set(str(now.minute))
            sec_var.set(str(now.second))
        
        def add_hours(h):
            try:
                current = datetime(
                    int(year_var.get()), int(month_var.get()), int(day_var.get()),
                    int(hour_var.get()), int(min_var.get()), int(sec_var.get())
                )
                new_time = current + timedelta(hours=h)
                year_var.set(str(new_time.year))
                month_var.set(str(new_time.month))
                day_var.set(str(new_time.day))
                hour_var.set(str(new_time.hour))
                min_var.set(str(new_time.minute))
                sec_var.set(str(new_time.second))
            except ValueError:
                pass
        
        ttk.Button(quick_frame, text="Now", command=set_now, width=8).pack(side=tk.LEFT, padx=2)
        ttk.Button(quick_frame, text="-6h", command=lambda: add_hours(-6), width=6).pack(side=tk.LEFT, padx=2)
        ttk.Button(quick_frame, text="-1h", command=lambda: add_hours(-1), width=6).pack(side=tk.LEFT, padx=2)
        ttk.Button(quick_frame, text="+1h", command=lambda: add_hours(1), width=6).pack(side=tk.LEFT, padx=2)
        ttk.Button(quick_frame, text="+6h", command=lambda: add_hours(6), width=6).pack(side=tk.LEFT, padx=2)
        
        # Buttons
        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(fill=tk.X, padx=10, pady=10)
        
        def apply_time():
            try:
                self._sim_time = datetime(
                    int(year_var.get()), int(month_var.get()), int(day_var.get()),
                    int(hour_var.get()), int(min_var.get()), int(sec_var.get())
                )
                self._update_time_display()
                self._update_view()
                dialog.destroy()
            except ValueError as e:
                ttk.Label(dialog, text=f"Invalid date/time!", foreground='red').pack()
        
        ttk.Button(btn_frame, text="Apply", command=apply_time).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="Cancel", command=dialog.destroy).pack(side=tk.RIGHT, padx=5)
    
    def _start_rotation(self):
        """Start the Earth rotation simulation"""
        if self._rotation_timer_id:
            self.root.after_cancel(self._rotation_timer_id)
        
        self._rotation_tick()
    
    def _stop_rotation(self):
        """Stop the Earth rotation simulation"""
        if self._rotation_timer_id:
            self.root.after_cancel(self._rotation_timer_id)
            self._rotation_timer_id = None
    
    def _calculate_lst(self, utc_time: datetime, longitude: float) -> float:
        """
        Calculate Local Sidereal Time (LST) from UTC time and longitude.
        
        Args:
            utc_time: UTC datetime
            longitude: Observer longitude in degrees (East positive)
            
        Returns:
            LST in hours (0-24)
        """
        # Calculate Julian Date
        year = utc_time.year
        month = utc_time.month
        day = utc_time.day
        hour = utc_time.hour + utc_time.minute / 60.0 + utc_time.second / 3600.0
        
        if month <= 2:
            year -= 1
            month += 12
        
        A = int(year / 100)
        B = 2 - A + int(A / 4)
        
        JD = int(365.25 * (year + 4716)) + int(30.6001 * (month + 1)) + day + hour / 24.0 + B - 1524.5
        
        # Calculate Greenwich Mean Sidereal Time (GMST)
        D = JD - 2451545.0  # Days since J2000.0
        GMST = 280.46061837 + 360.98564736629 * D + 0.000387933 * (D / 36525) ** 2
        
        # Normalize to 0-360 degrees
        GMST = GMST % 360
        if GMST < 0:
            GMST += 360
        
        # Convert to hours
        GMST_hours = GMST / 15.0
        
        # Calculate LST by adding longitude (converted to hours)
        LST = GMST_hours + longitude / 15.0
        
        # Normalize to 0-24 hours
        LST = LST % 24
        if LST < 0:
            LST += 24
        
        return LST
    
    def _rotation_tick(self):
        """Perform one rotation tick - simulate stars drifting due to Earth's rotation"""
        if not self._rotation_enabled:
            return
        
        # Update interval - fixed 50ms real time between ticks
        update_interval_ms = 50
        update_interval_sec = update_interval_ms / 1000.0
        
        # Calculate simulated time advance based on speed multiplier
        sim_seconds = update_interval_sec * abs(self._rotation_speed)
        sim_time_advance = timedelta(seconds=sim_seconds)
        
        if self._rotation_speed < 0:
            self._sim_time -= sim_time_advance
        else:
            self._sim_time += sim_time_advance
        
        # Get tracking mode key from control panel and update manager
        mode_key = self.control_panel.get_tracking_mode()
        self._tracking_manager.set_mode(mode_key)
        
        # Update camera angle from control panel
        self._tracking_manager.camera_angle = self.control_panel.get_camera_angle()
        
        # Create current tracking state
        lat, lon = self.control_panel.get_location()
        lst = self._calculate_lst(self._sim_time, lon)
        
        state = TrackingState(
            center_ra=self.sky_canvas.center_ra,
            center_dec=self.sky_canvas.center_dec,
            rotation_angle=self.sky_canvas.get_rotation_angle(),
            lst=lst,
            observer_lat=lat,
            observer_lon=lon
        )
        
        # Calculate update using current tracking mode
        update = self._tracking_manager.current_mode.calculate_update(
            state, sim_seconds, self._rotation_speed
        )
        
        # Apply rotation delta ONLY - do NOT change projection mode!
        # The projection mode (RA-DEC vs Alt-Az) is a user setting, not tied to simulation
        if update.reset_rotation:
            self.sky_canvas.reset_rotation_angle()
        elif abs(update.delta_rotation) > 0.0001:
            self.sky_canvas.add_rotation_angle(update.delta_rotation)
        
        # Update center coordinates if mode changes them (e.g., RA drift)
        if (abs(update.new_ra - state.center_ra) > 0.00001 or 
            abs(update.new_dec - state.center_dec) > 0.00001):
            self.sky_canvas.set_center(update.new_ra, update.new_dec)
            self.control_panel.set_coords(update.new_ra, update.new_dec)
        
        # Update time display (this updates LST in the canvas)
        self._update_time_display()
        
        # Update view to show star rotation
        self._update_view()
        
        # Schedule next tick
        self._rotation_timer_id = self.root.after(update_interval_ms, self._rotation_tick)
    
    def _update_time_display(self):
        """Update the time overlay on the sky canvas"""
        # Get location from control panel
        lat, lon = self.control_panel.get_location()
        self._observer_lat = lat
        self._observer_lon = lon
        
        # Calculate LST
        lst = self._calculate_lst(self._sim_time, lon)
        
        # Update sky canvas
        self.sky_canvas.set_time_info(self._sim_time, lst, lat, lon)
    
    def _update_drift_display(self):
        """Update the drift rate display based on current DEC and camera focal length"""
        # At the celestial equator, drift is 15.041 arcsec/sec
        # At other declinations, apparent drift = 15.041 * cos(dec) arcsec/sec
        dec_rad = math.radians(self.sky_canvas.center_dec)
        drift_arcsec = EARTH_ROTATION_RATE_ARCSEC_PER_SEC * math.cos(dec_rad) * self._rotation_speed
        
        # Use camera focal length (equipment setting), NOT simulator view focal length
        focal_length = self._camera_focal
        self.control_panel.update_drift_display(drift_arcsec, focal_length)
    
    def _show_setup_guide(self):
        """Show the mount testing setup guide"""
        dialog = tk.Toplevel(self.root)
        dialog.title("Mount Testing Setup Guide")
        dialog.geometry("800x600")
        dialog.transient(self.root)
        
        # Center on parent
        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - 800) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 600) // 2
        dialog.geometry(f"+{x}+{y}")
        
        # Create scrollable text
        frame = ttk.Frame(dialog)
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        scrollbar = ttk.Scrollbar(frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        text = tk.Text(frame, wrap=tk.WORD, yscrollcommand=scrollbar.set,
                      font=('Courier', 10), bg='#f0f0f0')
        text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=text.yview)
        
        # Setup guide content
        guide = """
╔═══════════════════════════════════════════════════════════════════════════╗
║            EQUATORIAL MOUNT TESTING SETUP GUIDE                           ║
╚═══════════════════════════════════════════════════════════════════════════╝

This guide explains how to physically set up your equipment to test mount 
GoTo accuracy and tracking using this simulator as a "virtual sky".

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 CONCEPT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

The monitor displays a simulated sky. Your mount must be "polar aligned" to 
the monitor (not to the real Polaris) so that:
  • Mount's RA axis rotates parallel to monitor surface
  • Mount's DEC axis moves perpendicular to monitor
  • Camera points at monitor to see the simulated stars


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 PHYSICAL SETUP - SIDE VIEW
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Option A: Tilted Monitor (Recommended)
───────────────────────────────────────

         North (up)
            ↑
            │    [Monitor]         Tilt monitor back by 
            │      /│              latitude angle
            │     / │              (e.g., 51.5° for London)
            │    /  │
            │   /   │
            │  /    │
    ────────┼─/─────┴──────── Horizontal
            │/  
            
      [Camera on Mount]        Mount stays level
         pointing up           Polar axis points at monitor
                               perpendicular to its surface


Option B: Tilted Mount (If monitor must stay vertical)
───────────────────────────────────────────────────────

            North
              ↑
              │
         [Monitor]              Monitor vertical
              │
              │
              │
    ──────────┴────────────── Horizontal
         
          [Camera]             Mount base tilted up
            ↗                  by latitude angle
      [Mount Base]             Polar axis points
        on wedge              perpendicular to monitor
          /
       ──/──


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 TOP VIEW - Mount Alignment
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

                    Monitor face
                   (vertical plane)
                         │
                         │
                    ┌────┴────┐
                    │         │  ← Screen shows stars
                    │ Monitor │
                    │         │
                    └────┬────┘
                         │
                         ↓ Polar axis
                     direction
                         
                    [Camera]───→ pointing at monitor
                         │
                    [RA axis] ─ parallel to monitor surface
                         │
                    [Mount base]


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 EASIEST SETUP (Mount already polar aligned + vertical monitor)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

If your mount is already polar aligned AND you want to keep monitor vertical:

1. Configure Simulator
   ───────────────────
   • Set LOCATION to match your mount (e.g., 51.5°N, 0°E)
   • Set DATE/TIME to current date/time
   • Set FOCAL LENGTH to your lens (e.g., 400mm)
   • Set SENSOR SIZE (Full Frame: 36×24mm)
   • Enable "Show Camera FOV Rectangle"

2. Position Monitor + Mount
   ────────────────────────
   • Keep monitor VERTICAL (no tilt!)
   • Place 2-3 meters from mount (for lens focus)
   • Maximum brightness, darken room
   • Point mount horizontally at monitor (Alt ≈ 0°, pointing due South)

3. Navigate to Horizon View
   ─────────────────────────
   • In simulator, drag view to show sky at HORIZON
   • Look for stars near Altitude = 0°, Azimuth = 180° (due South)
   • This is what mount sees when pointing horizontally
   • Center view on celestial equator (DEC ≈ 0°)

4. Synchronize Mount
   ─────────────────
   • Note RA/DEC shown at simulator center
   • Command mount to slew to those coordinates
   • Camera should now see what simulator shows
   • Enable "Simulate Rotation" at 1x speed

5. Test GoTo and Tracking
   ──────────────────────
   • Use "Set Target" to mark any visible star
   • Command mount to GoTo that target
   • Star should center in camera view
   • Track at various speeds to verify accuracy

KEY INSIGHT: With vertical monitor, you're simulating looking at the horizon
(not the pole). Mount stays level, points horizontally at monitor. Simulator
shows horizon view instead of pole view.


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 ALTERNATIVE: Tilted Monitor Setup (More Sky Coverage)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

If mount is polar aligned with phone app:

1. Configure Simulator
   ───────────────────
   • Set LOCATION to match your mount (e.g., 51.5°N, 0°E)
   • Set DATE/TIME to current date/time
   • Set FOCAL LENGTH to your lens (e.g., 400mm)
   • Set SENSOR SIZE (Full Frame: 36×24mm)
   • Enable "Show Camera FOV Rectangle"

2. Position Monitor
   ────────────────
   • Tilt monitor back by your LATITUDE angle (51.5° for London)
   • Use phone inclinometer app for accuracy
   • Place 2-3 meters from mount (for lens focus)
   • Maximum brightness, darken room

3. Point Camera at Monitor
   ────────────────────────
   • Your mount is ALREADY polar aligned (to real celestial pole)
   • Point camera at monitor center
   • Mount should point upward at angle ≈ latitude
   • Monitor tilt matches what mount expects to see

4. Synchronize Coordinates
   ───────────────────────
   • In simulator, navigate to show pole region (high DEC)
   • Note current RA/DEC of monitor center
   • Command mount to slew to those coordinates
   • Camera should now see what simulator shows
   • Enable "Simulate Rotation" at 1x speed

5. Verify and Test
   ────────────────
   • Stars should rotate around pole as in real sky
   • Test GoTo to various targets
   • Track at various speeds

ADVANTAGE: Tilted monitor lets you test full range of DEC angles, not just
horizon. More realistic for actual observing sessions.


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 DETAILED SETUP (If mount is NOT already polar aligned)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. SIMULATOR CONFIGURATION
   ───────────────────────
   • Set observer location to match your mount's location setting
   • Example: 51.5°N, 0°E for Greenwich
   • Set your camera's focal length (e.g., 400mm)
   • Set sensor size (Full Frame: 36×24mm)
   • Enable "Show Camera FOV Rectangle" in Mount Testing section

2. MONITOR PLACEMENT
   ──────────────────
   • Position monitor 2-3 meters away (for 400mm lens to focus)
   • Maximum brightness
   • Darken room for better contrast
   
   Choose method (both equally accurate):
   
   A) Tilt monitor back by EXACT latitude angle (51.5° for London)
      - Use digital angle finder or smartphone inclinometer app
      - Measure angle from horizontal on monitor back/stand
      - Secure monitor firmly so angle doesn't shift
      - This simulates looking at celestial pole from your latitude
   
   B) Keep monitor vertical, tilt mount by EXACT latitude angle
      - Place wedge under mount (must equal latitude angle precisely)
      - Or use adjustable platform with angle measurement
      - Mount polar axis will then point perpendicular to monitor

3. MOUNT POSITIONING
   ──────────────────
   • Place mount on stable, level surface (check with spirit level)
   • Point polar axis perpendicular to monitor face (see step 5)
   • Polar axis should aim at monitor center
   • Distance: far enough for lens minimum focus (typically 2-3m)
   • Ensure mount base is rigid and won't shift during testing
   • If using method B (vertical monitor), mount must be on wedge

4. CAMERA MOUNTING
   ────────────────
   • Attach camera to mount
   • Point camera at monitor
   • Compose so yellow FOV rectangle fills about 40% of viewfinder
   • Focus on monitor (manual focus, infinity won't work!)

5. PRECISE POLAR ALIGNMENT (Critical Step!)
   ──────────────────────────────────────────
   
   The monitor represents the celestial sphere. Your mount's polar axis
   must point EXACTLY perpendicular to the monitor surface.
   
   TOOLS NEEDED:
   • Carpenter's square or large set square
   • Spirit level
   • Measuring tape or ruler
   • Laser pointer (optional but very helpful)
   • Smartphone inclinometer app (optional)
   
   METHOD 1: Laser Alignment (Most Accurate)
   ─────────────────────────────────────────
   a) Attach small laser pointer to mount's polar axis
      (tape or rubber bands work)
   b) Turn on laser, point at monitor
   c) Laser dot should hit monitor at right angle (perpendicular)
   d) Slowly rotate RA axis through full range
   e) Laser should trace a HORIZONTAL line on monitor
   f) If line is diagonal or vertical:
      - Adjust mount's orientation/tilt
      - Repeat until line is perfectly horizontal
   g) Adjust mount distance so laser hits monitor center
   
   METHOD 2: Square Alignment (Good Accuracy)
   ──────────────────────────────────────────
   a) Place carpenter's square against monitor surface
   b) One edge flat on monitor, other edge points toward mount
   c) Sight along square's edge - should point at polar axis
   d) Check from multiple points on monitor (top, middle, bottom)
   e) All lines should converge at polar axis
   f) Adjust mount position until all checks align
   
   METHOD 3: Distance Measurement (Moderate Accuracy)
   ──────────────────────────────────────────────────
   a) Measure distance from polar axis to TOP of monitor = D1
   b) Measure distance from polar axis to BOTTOM of monitor = D2
   c) If D1 = D2 (within 1cm), axis aims at center
   d) Rotate mount 90° and repeat with LEFT/RIGHT edges
   e) Adjust until all four measurements equal
   
   VERIFICATION:
   • Unlock both mount axes
   • Manually sweep RA through full range
   • Camera view should move HORIZONTALLY across monitor only
   • Now sweep DEC through full range  
   • Camera view should move VERTICALLY on monitor only
   • Any diagonal motion = not perpendicular, adjust and recheck
   
   ACCURACY GOAL:
   • < 0.5° error = < 1cm positional offset per meter distance
   • Use protractor or inclinometer to verify axis angle if needed
   • For 51.5° latitude: polar axis should be 38.5° from horizontal


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 TESTING PROCEDURES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

TEST 1: Polar Alignment Quality Check
──────────────────────────────────────
1. In simulator, enable "Simulate Rotation" at 100x speed
2. Enable "Show Crosshair" for reference
3. Center Polaris (or any bright star near pole) in camera view
4. Lock DEC axis (RA tracking disabled)
5. Watch for 60 seconds real time (= 100 minutes simulated)
6. Measure drift direction and amount:
   • Horizontal drift only = PERFECT alignment
   • Vertical drift < 5 pixels = excellent (< 0.1° error)
   • Vertical drift 5-20 pixels = acceptable (0.1-0.5° error)
   • Vertical drift > 20 pixels = poor, recheck perpendicularity
7. Repeat test with stars in EAST and WEST parts of sky
8. All stars should drift horizontally only if aligned correctly
9. With perfect alignment, periodic error should be < 10 arcsec

TEST 2: GoTo Accuracy
─────────────────────
1. In simulator "Mount Testing", enter target RA/DEC
2. Click "Set Target" (green marker appears)
3. Command mount to GoTo same coordinates
4. Check camera view - marker should be centered
5. "Offset" display shows your GoTo error
6. Repeat with different targets across the sky

TEST 3: Tracking Accuracy
─────────────────────────
1. Center a bright star in camera
2. Enable rotation at 10x or 30x speed
3. Watch star over 1-2 minutes
4. Star should stay centered
5. Drift indicates tracking error or polar misalignment


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 TIPS & TROUBLESHOOTING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

PROBLEM: Can't focus on monitor
  → Solution: Increase distance or use shorter focal length (200mm)

PROBLEM: Stars too dim in camera
  → Solution: Increase monitor brightness
  → Solution: Use simulator's "Star Brightness" control (up to 3x)
  → Solution: Increase camera ISO or exposure time

PROBLEM: FOV rectangle too small/large
  → Solution: Verify focal length matches your lens
  → Solution: Verify sensor size matches your camera
  → Solution: Use scroll wheel to zoom simulator view

PROBLEM: Mount's RA motion moves camera vertically
  → Solution: Polar axis not perpendicular to monitor
  → Solution: Use laser or square to verify 90° alignment

PROBLEM: Objects appear in wrong orientation
  → Solution: Check latitude setting in simulator matches mount setting
  → Solution: Verify monitor tilt angle exactly matches latitude

PROBLEM: Tracking drift not consistent across sky
  → Solution: Polar axis not pointing at monitor center - adjust mount position
  → Solution: Monitor not truly flat - check for warping or curve

PROBLEM: Can't get polar axis exactly perpendicular
  → Solution: Use smartphone inclinometer app on polar axis
  → Solution: Mount axis should read (90° - latitude) from horizontal
  → Solution: For 51.5° latitude: polar axis should be 38.5° from horizontal


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 SIMPLIFIED TESTING (WITHOUT POLAR ALIGNMENT)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

If polar alignment is too complex, test GoTo accuracy only:

1. Keep monitor vertical (no tilt)
2. Mount camera on simple pan/tilt head (not equatorial mount)
3. Use simulator in Alt-Az mode (already enabled)
4. Click "Use Center" to mark current camera position
5. Manually slew camera to new position
6. Check if crosshair still centered
7. Measures pointing accuracy without tracking

This won't test tracking, but verifies basic positioning accuracy.


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 EQUIPMENT RECOMMENDATIONS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

REQUIRED:
  • Large monitor (27" or larger recommended)
  • Camera with lens (200-600mm range ideal)
  • Equatorial mount with GoTo
  • 2-3 meters clear space

HELPFUL:
  • Angle finder or protractor (for monitor tilt)
  • Wedge or adjustable platform (for mount tilt)
  • Dark room or blackout curtains
  • Remote shutter or intervalometer (for long exposures)


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

For questions or issues, refer to the README.md file or project documentation.

"""
        
        text.insert('1.0', guide)
        text.config(state=tk.DISABLED)
        
        # Close button
        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(side=tk.BOTTOM, pady=10)
        ttk.Button(btn_frame, text="Close", command=dialog.destroy, width=15).pack()
    
    def _show_about(self):
        """Show about dialog"""
        about_text = """Night Sky Simulator v1.0

A Python-based astronomical simulator for:
• Visual sky simulation with real catalog data
• Equatorial mount GoTo testing
• Astrophotography planning
• Educational visualization

Features:
• Alt-Az coordinate mode
• Earth rotation simulation
• Mount testing tools
• Real NGC2000 & BSC5 catalogs

Built with Python + tkinter
© 2025"""
        
        messagebox.showinfo("About Night Sky Simulator", about_text)
    
    def _export_settings(self):
        """Export all settings to JSON file"""
        try:
            # Get location from control panel
            lat, lon = self.control_panel.get_location()
            
            # Collect all settings - comprehensive dump
            settings = {
                'version': '1.0',
                'view': {
                    'center_ra': self.sky_canvas.center_ra,
                    'center_dec': self.sky_canvas.center_dec,
                    'focal_length': self.sky_canvas.fov_calculator.focal_length,
                    'rotation_angle': self.sky_canvas.get_rotation_angle(),
                },
                'optics': self.control_panel.get_optics(),
                'display': self.control_panel.get_display_options(),
                'location': {
                    'latitude': lat,
                    'longitude': lon,
                },
                'rotation': {
                    'enabled': self.control_panel.get_rotation_enabled(),
                    'speed': self.control_panel.get_rotation_speed(),
                    'tracking_mode': self.control_panel.get_tracking_mode(),
                },
                'testing': self.control_panel.get_testing_options(),
                'simulation_time': self._sim_time.isoformat(),
                'canvas': {
                    'altaz_mode': self.sky_canvas._altaz_mode,
                    'show_grid': self.sky_canvas.show_grid,
                    'show_labels': self.sky_canvas.show_labels,
                    'mag_limit': self.sky_canvas.mag_limit,
                    'show_diffraction_spikes': self.sky_canvas.show_diffraction_spikes,
                    'diffraction_spike_count': self.sky_canvas.diffraction_spike_count,
                    'diffraction_spike_rotation': self.sky_canvas.diffraction_spike_rotation,
                },
                'camera_fov': {
                    'width': self._camera_fov_width,
                    'height': self._camera_fov_height,
                    'focal': self._camera_focal,
                },
                'selected_object': {
                    'name': self.selected_object.name if self.selected_object else None,
                    'id': self.selected_object.id if self.selected_object else None,
                    'ra': self.selected_object.ra_hours if self.selected_object else None,
                    'dec': self.selected_object.dec_degrees if self.selected_object else None,
                },
                'target': self.control_panel.get_target(),
            }
            
            # Use /app/settings if available (mounted in dev), otherwise /tmp
            if os.path.exists("/app/settings") and os.access("/app/settings", os.W_OK):
                default_dir = "/app/settings"
            else:
                default_dir = "/tmp"
            
            # Ask for save location
            filename = filedialog.asksaveasfilename(
                title="Export Settings",
                defaultextension=".json",
                filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
                initialfile="sky_simulator_settings.json",
                initialdir=default_dir
            )
            
            if filename:
                with open(filename, 'w') as f:
                    json.dump(settings, f, indent=2)
                messagebox.showinfo("Export Successful", 
                                   f"Settings exported to:\n{filename}")
        except Exception as e:
            messagebox.showerror("Export Error", 
                               f"Failed to export settings:\n{str(e)}")
    
    def _import_settings(self):
        """Import settings from JSON file"""
        try:
            # Use /app/settings if available (mounted in dev), otherwise /tmp
            if os.path.exists("/app/settings") and os.access("/app/settings", os.R_OK):
                default_dir = "/app/settings"
            else:
                default_dir = "/app"
            
            # Ask for file to load
            filename = filedialog.askopenfilename(
                title="Import Settings",
                filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
                initialdir=default_dir
            )
            
            if not filename:
                return
            
            with open(filename, 'r') as f:
                settings = json.load(f)
            
            # Apply settings
            if 'view' in settings:
                view = settings['view']
                if 'center_ra' in view and 'center_dec' in view:
                    self._goto_coords(view['center_ra'], view['center_dec'])
                if 'focal_length' in view:
                    self.sky_canvas.fov_calculator.focal_length = view['focal_length']
            
            if 'optics' in settings:
                optics = settings['optics']
                self.control_panel.set_optics(
                    optics.get('focal_length', 200),
                    optics.get('sensor_width', 36),
                    optics.get('sensor_height', 24)
                )
                self._on_optics_change(
                    optics.get('focal_length', 200),
                    optics.get('sensor_width', 36),
                    optics.get('sensor_height', 24)
                )
            
            if 'display' in settings:
                self.control_panel.set_display_options(settings['display'])
            
            if 'location' in settings:
                loc = settings['location']
                self.control_panel.set_location(
                    loc.get('latitude', 51.5),
                    loc.get('longitude', 0.0)
                )
                self._on_location_change(
                    loc.get('latitude', 51.5),
                    loc.get('longitude', 0.0)
                )
            
            if 'rotation' in settings:
                rot = settings['rotation']
                if 'tracking_mode' in rot:
                    self.control_panel.set_tracking_mode(rot['tracking_mode'])
                if 'speed' in rot:
                    self.control_panel.set_rotation_speed(rot['speed'])
                if 'enabled' in rot and rot['enabled']:
                    self.control_panel.set_rotation_enabled(True)
                    self._on_rotation_toggle(True)
            
            if 'testing' in settings:
                self.control_panel.set_testing_options(settings['testing'])
                self._on_testing_change()
            
            if 'simulation_time' in settings:
                self._sim_time = datetime.fromisoformat(settings['simulation_time'])
                self._update_time_display()
            
            # Apply canvas settings
            if 'canvas' in settings:
                canvas = settings['canvas']
                if 'altaz_mode' in canvas:
                    self.sky_canvas.set_altaz_mode(canvas['altaz_mode'])
                if 'show_grid' in canvas:
                    self.sky_canvas.show_grid = canvas['show_grid']
                if 'show_labels' in canvas:
                    self.sky_canvas.show_labels = canvas['show_labels']
                if 'mag_limit' in canvas:
                    self.sky_canvas.mag_limit = canvas['mag_limit']
                if 'show_diffraction_spikes' in canvas:
                    self.sky_canvas.show_diffraction_spikes = canvas['show_diffraction_spikes']
                if 'diffraction_spike_count' in canvas:
                    self.sky_canvas.diffraction_spike_count = canvas['diffraction_spike_count']
                if 'diffraction_spike_rotation' in canvas:
                    self.sky_canvas.diffraction_spike_rotation = canvas['diffraction_spike_rotation']
            
            # Apply rotation angle
            if 'view' in settings and 'rotation_angle' in settings['view']:
                self.sky_canvas._rotation_angle = settings['view']['rotation_angle']
            
            # Apply camera FOV
            if 'camera_fov' in settings:
                fov = settings['camera_fov']
                if 'width' in fov:
                    self._camera_fov_width = fov['width']
                if 'height' in fov:
                    self._camera_fov_height = fov['height']
                if 'focal' in fov:
                    self._camera_focal = fov['focal']
            
            # Restore target/selected object
            if 'target' in settings and settings['target']:
                # Try to navigate to the saved target
                self._goto_target(settings['target'])
            elif 'selected_object' in settings and settings['selected_object']:
                # If no target name, but we have coordinates, go there
                obj = settings['selected_object']
                if obj.get('ra') is not None and obj.get('dec') is not None:
                    self._goto_coords(obj['ra'], obj['dec'])
            
            self._update_view()
            
            messagebox.showinfo("Import Successful", 
                               "Settings imported successfully!")
        except Exception as e:
            messagebox.showerror("Import Error", 
                               f"Failed to import settings:\n{str(e)}")
    
    def run(self):
        """Start the application main loop"""
        if self.debug_mode:
            print("[DEBUG] Debug mode active - F5 to reload modules")
        self.root.mainloop()
