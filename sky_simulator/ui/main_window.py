"""
Main window for the Night Sky Simulator application.
Coordinates all UI components and application logic.
"""

import math
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path
from typing import List, Tuple, Optional
from datetime import datetime, timedelta
import os
import sys
import importlib

from ..catalogs.catalog_loader import CatalogManager
from ..models.celestial_objects import CelestialObject
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
        
        # Earth rotation state
        self._rotation_enabled = False
        self._rotation_speed = 1.0  # Multiplier
        self._rotation_timer_id = None
        
        # Observer location (default: Greenwich)
        self._observer_lat = 51.5
        self._observer_lon = 0.0
        
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
            self.sky_canvas.set_center(obj.ra_hours, obj.dec_degrees)
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
        
        self.sky_canvas.set_center(ra, dec)
        self._update_view()
    
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
        
        # Update interval
        update_interval_ms = 50
        update_interval_sec = update_interval_ms / 1000.0
        
        # Advance simulation time
        sim_time_advance = timedelta(seconds=update_interval_sec * self._rotation_speed)
        self._sim_time += sim_time_advance
        
        # Simulating an UNTRACKED camera (fixed to Earth, alt-az or stationary):
        # - Earth rotates eastward (counter-clockwise when viewed from north pole)
        # - Stars appear to drift WESTWARD across the sky
        # - On screen: stars move from LEFT to RIGHT (when north is up)
        # - To achieve this: we INCREASE the view center RA, which shifts
        #   the view eastward, making stars appear to move right/westward
        # 
        # Rate: Earth rotates 360° in 23h 56m 4s (sidereal day)
        # = 15.041 arcsec/sec of apparent star motion
        
        ra_drift_per_sec = EARTH_ROTATION_RATE_ARCSEC_PER_SEC / 15.0 / 3600.0  # hours/sec
        ra_drift = ra_drift_per_sec * update_interval_sec * self._rotation_speed
        
        # Increase RA to make stars appear to move right (westward on screen)
        new_ra = self.sky_canvas.center_ra + ra_drift
        
        # Wrap RA around 24 hours
        if new_ra >= 24:
            new_ra -= 24
        elif new_ra < 0:
            new_ra += 24
        
        self.sky_canvas.center_ra = new_ra
        
        # Update time display
        self._update_time_display()
        
        self._update_view()
        
        # Update coordinate display
        self.control_panel.set_coords(new_ra, self.sky_canvas.center_dec)
        
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
        """Update the drift rate display based on current DEC and focal length"""
        # At the celestial equator, drift is 15.041 arcsec/sec
        # At other declinations, apparent drift = 15.041 * cos(dec) arcsec/sec
        dec_rad = math.radians(self.sky_canvas.center_dec)
        drift_arcsec = EARTH_ROTATION_RATE_ARCSEC_PER_SEC * math.cos(dec_rad) * self._rotation_speed
        
        focal_length = self.sky_canvas.fov_calculator.focal_length
        self.control_panel.update_drift_display(drift_arcsec, focal_length)
    
    def run(self):
        """Start the application main loop"""
        if self.debug_mode:
            print("[DEBUG] Debug mode active - F5 to reload modules")
        self.root.mainloop()
