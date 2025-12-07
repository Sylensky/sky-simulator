"""
Sky canvas component for rendering the night sky view.
Handles coordinate transformations and object rendering.
"""

import math
import tkinter as tk
from tkinter import ttk
from typing import List, Optional, Tuple, Callable
from pathlib import Path

from ..models.celestial_objects import CelestialObject, ObjectType
from ..utils.coordinates import CoordinateUtils
from ..utils.fov_calculator import FOVCalculator
from ..utils.image_loader import ImageLoader, get_image_loader, init_image_loader


class SkyCanvas:
    """
    Canvas component for rendering the night sky.
    
    Handles:
    - Coordinate transformations (RA/DEC to screen)
    - Object rendering with type-specific symbols
    - Grid overlay
    - Mouse interaction
    """
    
    def __init__(self, parent: tk.Widget, 
                 on_click: Callable[[float, float], None] = None,
                 on_motion: Callable[[float, float], None] = None):
        """
        Initialize the sky canvas.
        
        Args:
            parent: Parent tkinter widget
            on_click: Callback for canvas clicks (ra_hours, dec_deg)
            on_motion: Callback for mouse motion (ra_hours, dec_deg)
        """
        self.parent = parent
        self.on_click_callback = on_click
        self.on_motion_callback = on_motion
        
        # View parameters
        self.center_ra = 0.0  # hours
        self.center_dec = 0.0  # degrees
        self.fov_calculator = FOVCalculator(200, 36, 24)
        
        # Display options
        self.show_grid = True
        self.show_labels = True
        self.mag_limit = 8.0
        
        # Star rendering options
        self.show_diffraction_spikes = False  # Disabled by default
        self.diffraction_spike_count = 4  # 4 or 6 spikes typical
        self.diffraction_spike_rotation = 45  # degrees, 45 for diagonal spikes
        
        # Create canvas
        self.canvas = tk.Canvas(parent, bg='#0a0a20', highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        
        # Bind events
        self.canvas.bind('<Configure>', self._on_resize)
        self.canvas.bind('<Motion>', self._on_motion)
        self.canvas.bind('<MouseWheel>', self._on_scroll)
        self.canvas.bind('<Button-4>', self._on_scroll)  # Linux scroll up
        self.canvas.bind('<Button-5>', self._on_scroll)  # Linux scroll down
        
        # Drag movement bindings - all mouse buttons for free dragging
        self.canvas.bind('<ButtonPress-1>', self._on_drag_start)    # Left mouse
        self.canvas.bind('<ButtonPress-2>', self._on_drag_start)    # Middle mouse
        self.canvas.bind('<ButtonPress-3>', self._on_drag_start)    # Right mouse
        self.canvas.bind('<B1-Motion>', self._on_drag)              # Left mouse drag
        self.canvas.bind('<B2-Motion>', self._on_drag)              # Middle mouse drag
        self.canvas.bind('<B3-Motion>', self._on_drag)              # Right mouse drag
        self.canvas.bind('<ButtonRelease-1>', self._on_drag_end)    # Left mouse release
        self.canvas.bind('<ButtonRelease-2>', self._on_drag_end)    # Middle mouse release
        self.canvas.bind('<ButtonRelease-3>', self._on_drag_end)    # Right mouse release
        
        # Drag state
        self._drag_start_x: Optional[float] = None
        self._drag_start_y: Optional[float] = None
        self._drag_start_ra: float = 0.0
        self._drag_start_dec: float = 0.0
        self._drag_start_pa: float = 0.0  # Parallactic angle at drag start
        self._is_dragging: bool = False
        
        # Rotation state for sky rotation mode
        self._rotation_angle = 0.0  # degrees, cumulative rotation around pole
        
        # Image loader
        self._image_loader: Optional[ImageLoader] = None
        self._use_images: bool = True  # Can be toggled
        self._active_images: List = []  # Keep references to prevent GC
        
        # Object rendering cache
        self._objects: List[CelestialObject] = []
        self._dso_objects: List[CelestialObject] = []
        self._star_objects: List[CelestialObject] = []
        
        # Callbacks for zoom
        self.on_zoom_callback: Optional[Callable[[float], None]] = None
        
        # Time/location overlay
        self._show_time_overlay = True
        self._current_time = None  # datetime object
        self._observer_lat = 51.5
        self._observer_lon = 0.0
        self._lst = 0.0  # Local sidereal time in hours
        
        # Field rotation (parallactic angle) - disabled by default to avoid flip issues
        self._apply_field_rotation = False
        self._parallactic_angle = 0.0  # radians
        
        # Alt-Az simulation mode - when enabled, shows sky as seen from observer location
        # with Polaris at altitude = observer latitude
        self._altaz_mode = True  # Enable realistic horizon-based view
        
        # Polar mode - when enabled in RA-DEC, flips Y axis so pole is at top
        self._polar_mode = False
        
        # Object info overlay (bottom-right corner)
        self._hovered_object: Optional[CelestialObject] = None
        self._selected_object: Optional[CelestialObject] = None
        
        # Time overlay click callback
        self._on_time_click_callback: Optional[Callable[[], None]] = None
        self._time_overlay_bounds: Optional[Tuple[int, int, int, int]] = None  # x1, y1, x2, y2
        
        # Target marker for GoTo testing
        self._target_marker_ra: Optional[float] = None  # hours
        self._target_marker_dec: Optional[float] = None  # degrees
        self._target_marker_label: str = ""
        
        # FOV rectangle overlay for camera testing
        self._show_fov_rectangle = False
        self._fov_rect_width_deg = 5.2  # degrees (e.g., 400mm on full frame)
        self._fov_rect_height_deg = 3.5
        self._fov_rect_color = '#ffff00'  # yellow
        
        # Enhanced crosshair/reticle
        self._show_reticle = True
        self._reticle_style = 'crosshair'  # 'crosshair', 'circle', 'target'
        
        # Coordinate readout at cursor
        self._show_cursor_coords = True
        self._cursor_ra: Optional[float] = None
        self._cursor_dec: Optional[float] = None
        
        # Star brightness multiplier
        self._brightness_multiplier = 1.0
        self._contrast = 1.0
    
    @property
    def width(self) -> int:
        return self.canvas.winfo_width()
    
    @property
    def height(self) -> int:
        return self.canvas.winfo_height()
    
    @property
    def fov_width(self) -> float:
        """FOV width in degrees"""
        return self.fov_calculator.fov.width_deg
    
    @property
    def fov_height(self) -> float:
        """FOV height in degrees"""
        return self.fov_calculator.fov.height_deg
    
    def set_center(self, ra_hours: float, dec_deg: float):
        """Set the view center position"""
        self.center_ra = CoordinateUtils.normalize_ra(ra_hours)
        self.center_dec = CoordinateUtils.clamp_dec(dec_deg)
        # Recalculate parallactic angle for new view center
        self._update_parallactic_angle()
    
    def add_rotation_angle(self, delta_degrees: float):
        """Add to the cumulative rotation angle for sky rotation mode"""
        self._rotation_angle += delta_degrees
        self._rotation_angle = self._rotation_angle % 360  # Keep in 0-360 range
    
    def reset_rotation_angle(self):
        """Reset the rotation angle to zero"""
        self._rotation_angle = 0.0
    
    def get_rotation_angle(self) -> float:
        """Get current rotation angle in degrees"""
        return self._rotation_angle
    
    def set_altaz_mode(self, enabled: bool):
        """
        Set Alt-Az mode.
        When True: Display in Alt-Az coordinates (horizon-based view)
        When False: Display in RA/DEC coordinates (equatorial view)
        """
        self._altaz_mode = enabled
    
    def set_polar_mode(self, enabled: bool):
        """
        Set Polar mode for RA-DEC projection.
        When True: Y-axis points toward celestial pole, X-axis flipped for realistic view
        When False: Standard equatorial projection
        """
        self._polar_mode = enabled
    
    def is_dragging(self) -> bool:
        """Check if user is currently dragging the view"""
        return self._is_dragging
    
    def set_optics(self, focal_length: float, sensor_width: float, sensor_height: float):
        """Update optical parameters"""
        self.fov_calculator.update(focal_length, sensor_width, sensor_height)
    
    def set_objects(self, dso_objects: List[CelestialObject], 
                    star_objects: List[CelestialObject]):
        """Set the objects to render"""
        self._dso_objects = dso_objects
        self._star_objects = star_objects
        self._objects = dso_objects + star_objects
    
    def set_images_path(self, images_path: Path):
        """Set the path for celestial object images"""
        self._image_loader = init_image_loader(images_path)
    
    def set_use_images(self, use_images: bool):
        """Enable or disable image rendering"""
        self._use_images = use_images
    
    def ra_dec_to_canvas(self, ra_hours: float, dec_deg: float) -> Optional[Tuple[float, float]]:
        """
        Convert RA/DEC coordinates to canvas pixel coordinates using
        stereographic projection centered on the view center.
        
        When altaz_mode is enabled, coordinates are first transformed to
        altitude/azimuth based on observer location and LST, giving a
        realistic view where Polaris appears at altitude = observer latitude.
        
        Args:
            ra_hours: Right Ascension in hours
            dec_deg: Declination in degrees
            
        Returns:
            (x, y) canvas coordinates, or None if outside view
        """
        if self.width <= 1 or self.height <= 1:
            return None
        
        fov_w = self.fov_width
        fov_h = self.fov_height
        
        # Convert to radians
        ra_rad = math.radians(ra_hours * 15.0)
        dec_rad = math.radians(dec_deg)
        
        if self._altaz_mode:
            # Transform to Alt-Az coordinates for realistic view
            lat_rad = math.radians(self._observer_lat)
            lst_rad = math.radians(self._lst * 15.0)
            
            # Hour angle
            ha_rad = lst_rad - ra_rad
            
            # Calculate altitude
            sin_alt = (math.sin(lat_rad) * math.sin(dec_rad) + 
                      math.cos(lat_rad) * math.cos(dec_rad) * math.cos(ha_rad))
            alt_rad = math.asin(max(-1, min(1, sin_alt)))
            
            # Object below horizon
            if alt_rad < math.radians(-5):  # Allow slightly below for rendering
                return None
            
            # Calculate azimuth (0=N, 90=E, 180=S, 270=W)
            cos_az = (math.sin(dec_rad) - math.sin(lat_rad) * sin_alt) / (math.cos(lat_rad) * math.cos(alt_rad) + 1e-10)
            cos_az = max(-1, min(1, cos_az))
            az_rad = math.acos(cos_az)
            if math.sin(ha_rad) > 0:
                az_rad = 2 * math.pi - az_rad
            
            # Now do the same for the center point
            center_ra_rad = math.radians(self.center_ra * 15.0)
            center_dec_rad = math.radians(self.center_dec)
            center_ha_rad = lst_rad - center_ra_rad
            
            sin_center_alt = (math.sin(lat_rad) * math.sin(center_dec_rad) + 
                             math.cos(lat_rad) * math.cos(center_dec_rad) * math.cos(center_ha_rad))
            center_alt_rad = math.asin(max(-1, min(1, sin_center_alt)))
            
            cos_center_az = (math.sin(center_dec_rad) - math.sin(lat_rad) * sin_center_alt) / (math.cos(lat_rad) * math.cos(center_alt_rad) + 1e-10)
            cos_center_az = max(-1, min(1, cos_center_az))
            center_az_rad = math.acos(cos_center_az)
            if math.sin(center_ha_rad) > 0:
                center_az_rad = 2 * math.pi - center_az_rad
            
            # Stereographic projection in alt-az space
            # Looking at the sky: up = higher altitude, 
            # left/right depends on which direction we're facing
            
            # Angular separation in alt-az
            cos_c = (math.sin(center_alt_rad) * math.sin(alt_rad) + 
                    math.cos(center_alt_rad) * math.cos(alt_rad) * math.cos(az_rad - center_az_rad))
            
            if cos_c < 0:
                return None
            
            if cos_c >= 1.0:
                x_proj = 0
                y_proj = 0
            else:
                k = 1.0 / (1.0 + cos_c) if cos_c > -0.99 else 10.0
                
                # Standard stereographic projection
                # x = horizontal (azimuth direction)
                # y = vertical (altitude direction)
                delta_az = az_rad - center_az_rad
                # Normalize delta_az to -pi to pi
                while delta_az > math.pi:
                    delta_az -= 2 * math.pi
                while delta_az < -math.pi:
                    delta_az += 2 * math.pi
                
                x_proj = k * math.cos(alt_rad) * math.sin(delta_az)
                y_proj = k * (math.cos(center_alt_rad) * math.sin(alt_rad) - 
                             math.sin(center_alt_rad) * math.cos(alt_rad) * math.cos(delta_az))
                
                # Mirror x so that when facing south, east is on the left
                # (as it appears when looking at the real sky facing south)
                x_proj = -x_proj
        else:
            # Pure equatorial mode
            center_ra_rad = math.radians(self.center_ra * 15.0)
            center_dec_rad = math.radians(self.center_dec)
            
            # Calculate angular separation using spherical trigonometry
            cos_c = (math.sin(center_dec_rad) * math.sin(dec_rad) + 
                     math.cos(center_dec_rad) * math.cos(dec_rad) * math.cos(ra_rad - center_ra_rad))
            
            if cos_c < 0:
                return None
            
            if cos_c >= 1.0:
                x_proj = 0
                y_proj = 0
            else:
                k = 1.0 / (1.0 + cos_c) if cos_c > -0.99 else 10.0
                x_proj = k * math.cos(dec_rad) * math.sin(ra_rad - center_ra_rad)
                y_proj = k * (math.cos(center_dec_rad) * math.sin(dec_rad) - 
                             math.sin(center_dec_rad) * math.cos(dec_rad) * math.cos(ra_rad - center_ra_rad))
            
            # Apply field rotation around celestial pole if rotation angle is set
            # The rotation happens around where the North Celestial Pole (DEC +90°) 
            # would project to on the screen
            if abs(self._rotation_angle) > 0.001:
                # Calculate pole position in projection coordinates
                # At DEC = 90°, sin(dec) = 1, cos(dec) = 0
                # The pole projects to (x=0, y=k*(cos(center_dec)*1 - sin(center_dec)*0))
                #                     = (0, k*cos(center_dec))
                # where k depends on angular distance from view center to pole
                
                # Angular distance from view center to pole
                # cos(c) = sin(center_dec) * sin(90°) + cos(center_dec) * cos(90°) * cos(dRA)
                #        = sin(center_dec) * 1 + cos(center_dec) * 0
                #        = sin(center_dec)
                cos_c_pole = math.sin(center_dec_rad)
                
                # Calculate pole projection position
                if cos_c_pole > -0.99:  # Pole not directly behind us
                    k_pole = 1.0 / (1.0 + cos_c_pole) if cos_c_pole > -0.99 else 10.0
                    pole_x = 0  # Pole is on the DEC axis (no RA offset at pole)
                    pole_y = k_pole * math.cos(center_dec_rad)  # Above center if looking north of equator
                    
                    # Rotate projection coordinates around pole position
                    theta = math.radians(self._rotation_angle)
                    cos_theta = math.cos(theta)
                    sin_theta = math.sin(theta)
                    
                    # Translate to pole-centered coordinates
                    dx = x_proj - pole_x
                    dy = y_proj - pole_y
                    
                    # Rotate
                    x_rot = dx * cos_theta - dy * sin_theta
                    y_rot = dx * sin_theta + dy * cos_theta
                    
                    # Translate back
                    x_proj = x_rot + pole_x
                    y_proj = y_rot + pole_y
        
        # Apply field rotation (parallactic angle) if enabled
        # Note: sky rotation is now applied in RA/DEC space above, not here
        if self._apply_field_rotation and abs(self._parallactic_angle) > 0.001:
            pa = -self._parallactic_angle
            x_rot = x_proj * math.cos(pa) - y_proj * math.sin(pa)
            y_rot = x_proj * math.sin(pa) + y_proj * math.cos(pa)
            x_proj = x_rot
            y_proj = y_rot
        
        # Convert projection coordinates to degrees
        x_deg = math.degrees(x_proj)
        y_deg = math.degrees(y_proj)
        
        # Check if within FOV (with some margin)
        margin = 1.1
        if abs(x_deg) > fov_w / 2 * margin or abs(y_deg) > fov_h / 2 * margin:
            return None
        
        # Convert to canvas coordinates
        x = self.width / 2 - (x_deg / fov_w) * self.width
        y = self.height / 2 - (y_deg / fov_h) * self.height
        
        return x, y
    
    def canvas_to_ra_dec(self, x: float, y: float) -> Tuple[float, float]:
        """
        Convert canvas pixel coordinates to RA/DEC using inverse stereographic projection.
        
        Returns:
            (ra_hours, dec_degrees)
        """
        fov_w = self.fov_width
        fov_h = self.fov_height
        
        # Convert canvas to projection coordinates (in degrees)
        x_deg = -(x - self.width / 2) / self.width * fov_w
        y_deg = -(y - self.height / 2) / self.height * fov_h
        
        # Convert to radians
        x_rad = math.radians(x_deg)
        y_rad = math.radians(y_deg)
        center_ra_rad = math.radians(self.center_ra * 15.0)
        center_dec_rad = math.radians(self.center_dec)
        
        # Inverse stereographic projection
        rho = math.sqrt(x_rad**2 + y_rad**2)
        
        if rho < 1e-10:
            # At center
            return self.center_ra, self.center_dec
        
        c = 2 * math.atan(rho / 2)
        
        # Calculate DEC
        sin_dec = math.cos(c) * math.sin(center_dec_rad) + (y_rad * math.sin(c) * math.cos(center_dec_rad)) / rho
        dec_rad = math.asin(max(-1, min(1, sin_dec)))
        
        # Calculate RA
        ra_rad = center_ra_rad + math.atan2(
            x_rad * math.sin(c),
            rho * math.cos(center_dec_rad) * math.cos(c) - y_rad * math.sin(center_dec_rad) * math.sin(c)
        )
        
        ra = math.degrees(ra_rad) / 15.0
        dec = math.degrees(dec_rad)
        
        ra = CoordinateUtils.normalize_ra(ra)
        dec = CoordinateUtils.clamp_dec(dec)
        
        return ra, dec
    
    def magnitude_to_size(self, mag: float) -> float:
        """Convert magnitude to display size (for stars without angular size)"""
        # Brighter stars (lower magnitude) should be larger
        # Magnitude -1.5 (Sirius) -> ~12px, Magnitude 6 -> ~2px
        if mag <= -1:
            return 12
        elif mag <= 0:
            return 10
        elif mag <= 1:
            return 8
        elif mag <= 2:
            return 6
        elif mag <= 3:
            return 5
        elif mag <= 4:
            return 4
        elif mag <= 5:
            return 3
        elif mag <= 6:
            return 2.5
        else:
            return max(1.5, 2.5 - (mag - 6) * 0.3)
    
    def arcmin_to_pixels(self, arcmin: float) -> float:
        """
        Convert angular size in arcminutes to pixels based on current FOV.
        
        Args:
            arcmin: Angular size in arcminutes
            
        Returns:
            Size in pixels (diameter)
        """
        if self.width <= 1:
            return 1
        
        # FOV width in arcminutes
        fov_arcmin = self.fov_width * 60.0
        
        # Pixels per arcminute
        pixels_per_arcmin = self.width / fov_arcmin
        
        # Return diameter in pixels
        return arcmin * pixels_per_arcmin
    
    def render(self, show_stars: bool = True, show_dso: bool = True):
        """Render the sky view"""
        self.canvas.delete("all")
        self._active_images.clear()  # Clear image references
        
        if self.width <= 1 or self.height <= 1:
            return
        
        # Draw grid
        if self.show_grid:
            self._draw_grid()
        
        # Draw center crosshair
        self._draw_crosshair()
        
        # Draw stars (background layer)
        if show_stars:
            for obj in self._star_objects:
                if obj.magnitude <= self.mag_limit:
                    pos = self.ra_dec_to_canvas(obj.ra_hours, obj.dec_degrees)
                    if pos:
                        self._draw_object(obj, pos)
        
        # Draw DSOs (foreground layer)
        if show_dso:
            for obj in self._dso_objects:
                if obj.magnitude <= self.mag_limit or obj.magnitude == 0:
                    pos = self.ra_dec_to_canvas(obj.ra_hours, obj.dec_degrees)
                    if pos:
                        self._draw_object(obj, pos)
        
        # Draw time overlay (top-right)
        if self._show_time_overlay and self._current_time:
            self._draw_time_overlay()
        
        # Draw FOV rectangle overlay
        if self._show_fov_rectangle:
            self._draw_fov_rectangle()
        
        # Draw target marker
        if self._target_marker_ra is not None:
            self._draw_target_marker()
        
        # Draw cursor coordinate readout
        if self._show_cursor_coords and self._cursor_ra is not None:
            self._draw_cursor_coords()
        
        # Draw object info overlay (bottom-right)
        self._draw_object_info_overlay()
    
    def _draw_grid(self):
        """Draw equatorial coordinate grid with proper convergence at poles"""
        fov_w = self.fov_width
        fov_h = self.fov_height
        
        # Grid colors - distinct colors for RA and DEC
        ra_line_color = '#2a4a2a'      # Green tint for RA (hour) lines
        ra_label_color = '#55aa55'     # Brighter green for RA labels
        dec_line_color = '#4a2a2a'     # Red tint for DEC lines  
        dec_label_color = '#aa5555'    # Brighter red for DEC labels
        pole_color = '#8888ff'         # Blue for celestial poles
        celestial_equator_color = '#aaaa44'  # Yellow for celestial equator
        
        # Determine grid spacing based on FOV
        if fov_w > 30:
            ra_step, dec_step = 2.0, 10.0
        elif fov_w > 10:
            ra_step, dec_step = 1.0, 5.0
        elif fov_w > 5:
            ra_step, dec_step = 0.5, 2.0
        elif fov_w > 2:
            ra_step, dec_step = 0.25, 1.0
        else:
            ra_step, dec_step = 0.1, 0.5
        
        # Calculate visible RA/DEC range
        ra_min = self.center_ra - fov_w / 30  # Convert FOV degrees to RA hours
        ra_max = self.center_ra + fov_w / 30
        dec_min = max(-90, self.center_dec - fov_h / 2)
        dec_max = min(90, self.center_dec + fov_h / 2)
        
        # Draw DEC lines (parallels of declination)
        dec_start = math.floor(dec_min / dec_step) * dec_step
        dec_end = math.ceil(dec_max / dec_step) * dec_step
        
        for dec in range(int(dec_start), int(dec_end) + 1):
            if dec % int(dec_step) == 0 if dec_step >= 1 else abs(dec - round(dec / dec_step) * dec_step) < 0.01:
                # Draw DEC line as series of points across the RA range
                points = []
                num_segments = 20
                for i in range(num_segments + 1):
                    ra = ra_min + (ra_max - ra_min) * i / num_segments
                    # Handle RA wraparound
                    if ra < 0:
                        ra += 24
                    elif ra >= 24:
                        ra -= 24
                    pos = self.ra_dec_to_canvas(ra, dec)
                    if pos:
                        points.append(pos)
                
                if len(points) >= 2:
                    # Use special color for celestial equator
                    line_color = celestial_equator_color if dec == 0 else dec_line_color
                    line_width = 2 if dec == 0 else 1
                    
                    # Draw as connected line segments
                    for i in range(len(points) - 1):
                        self.canvas.create_line(points[i][0], points[i][1], 
                                               points[i+1][0], points[i+1][1],
                                               fill=line_color, dash=(2, 2) if dec != 0 else None,
                                               width=line_width)
                    # Label at left edge
                    label_text = "Eq" if dec == 0 else f"{dec:+d}°"
                    self.canvas.create_text(10, points[0][1], text=label_text,
                                           fill=celestial_equator_color if dec == 0 else dec_label_color, 
                                           font=('Arial', 9 if dec == 0 else 8, 'bold' if dec == 0 else 'normal'),
                                           anchor=tk.W)
        
        # Draw RA lines (hour circles / meridians)
        ra_start = math.floor(ra_min / ra_step) * ra_step
        ra_end = math.ceil(ra_max / ra_step) * ra_step
        
        # Iterate through RA values
        ra = ra_start
        while ra <= ra_end:
            # Normalize RA
            ra_norm = ra
            if ra_norm < 0:
                ra_norm += 24
            elif ra_norm >= 24:
                ra_norm -= 24
            
            # Check if this is a grid line
            if abs(ra_norm - round(ra_norm / ra_step) * ra_step) < 0.01 or ra_step < 0.25:
                # Draw RA line as series of points along declination
                points = []
                num_segments = 40  # More segments for smooth curves near poles
                
                for i in range(num_segments + 1):
                    dec = dec_min + (dec_max - dec_min) * i / num_segments
                    pos = self.ra_dec_to_canvas(ra_norm, dec)
                    if pos:
                        points.append((pos, dec))
                
                if len(points) >= 2:
                    # Draw as connected line segments
                    for i in range(len(points) - 1):
                        self.canvas.create_line(points[i][0][0], points[i][0][1], 
                                               points[i+1][0][0], points[i+1][0][1],
                                               fill=ra_line_color, dash=(2, 2))
                    
                    # Label at bottom
                    ra_h = int(ra_norm)
                    ra_m = int((ra_norm - ra_h) * 60)
                    if ra_step >= 1:
                        label = f"{ra_h}h"
                    else:
                        label = f"{ra_h}h{ra_m:02d}m"
                    
                    self.canvas.create_text(points[-1][0][0], self.height - 10, 
                                           text=label, fill=ra_label_color,
                                           font=('Arial', 8))
            
            ra += ra_step
        
        # Draw celestial pole markers if visible
        # North Celestial Pole (near Polaris)
        ncp_pos = self.ra_dec_to_canvas(0, 90)
        if ncp_pos:
            x, y = ncp_pos
            # Draw concentric circles around NCP
            for r in [5, 10, 15]:
                self.canvas.create_oval(x - r, y - r, x + r, y + r, 
                                       outline=pole_color, width=1, dash=(1, 2))
            # Cross at center
            self.canvas.create_line(x - 8, y, x + 8, y, fill=pole_color, width=2)
            self.canvas.create_line(x, y - 8, x, y + 8, fill=pole_color, width=2)
            self.canvas.create_text(x + 18, y, text="NCP", fill=pole_color, 
                                   font=('Arial', 9, 'bold'), anchor=tk.W)
        
        # South Celestial Pole
        scp_pos = self.ra_dec_to_canvas(0, -90)
        if scp_pos:
            x, y = scp_pos
            for r in [5, 10, 15]:
                self.canvas.create_oval(x - r, y - r, x + r, y + r,
                                       outline=pole_color, width=1, dash=(1, 2))
            self.canvas.create_line(x - 8, y, x + 8, y, fill=pole_color, width=2)
            self.canvas.create_line(x, y - 8, x, y + 8, fill=pole_color, width=2)
            self.canvas.create_text(x + 18, y, text="SCP", fill=pole_color,
                                   font=('Arial', 9, 'bold'), anchor=tk.W)
    
    def _draw_crosshair(self):
        """Draw center crosshair/reticle"""
        if not self._show_reticle:
            return
            
        cx, cy = self.width / 2, self.height / 2
        color = '#ff4444'  # Red reticle for visibility
        
        if self._reticle_style == 'target':
            # Target style: concentric circles with crosshair
            for r in [10, 25, 50]:
                self.canvas.create_oval(cx - r, cy - r, cx + r, cy + r,
                                       outline=color, width=1)
            # Crosshair extending from outer circle
            self.canvas.create_line(cx - 70, cy, cx - 50, cy, fill=color, width=2)
            self.canvas.create_line(cx + 50, cy, cx + 70, cy, fill=color, width=2)
            self.canvas.create_line(cx, cy - 70, cx, cy - 50, fill=color, width=2)
            self.canvas.create_line(cx, cy + 50, cx, cy + 70, fill=color, width=2)
            # Small center dot
            self.canvas.create_oval(cx - 2, cy - 2, cx + 2, cy + 2, fill=color, outline=color)
        elif self._reticle_style == 'circle':
            # Circle with center dot
            self.canvas.create_oval(cx - 30, cy - 30, cx + 30, cy + 30,
                                   outline=color, width=2)
            self.canvas.create_oval(cx - 2, cy - 2, cx + 2, cy + 2, fill=color, outline=color)
        else:  # 'crosshair' (default)
            # Simple crosshair with gap in center
            gap = 10
            length = 40
            self.canvas.create_line(cx - length, cy, cx - gap, cy, fill=color, width=2)
            self.canvas.create_line(cx + gap, cy, cx + length, cy, fill=color, width=2)
            self.canvas.create_line(cx, cy - length, cx, cy - gap, fill=color, width=2)
            self.canvas.create_line(cx, cy + gap, cx, cy + length, fill=color, width=2)
            # Small center dot
            self.canvas.create_oval(cx - 2, cy - 2, cx + 2, cy + 2, fill=color, outline=color)
    
    def _draw_time_overlay(self):
        """Draw time and location information in the top-right corner (clickable)"""
        if not self._current_time:
            return
        
        # Calculate timezone offset from longitude (approximate: 1 hour per 15 degrees)
        tz_offset_hours = self._observer_lon / 15.0
        tz_offset_minutes = int(tz_offset_hours * 60)
        tz_hours = tz_offset_minutes // 60
        tz_mins = abs(tz_offset_minutes % 60)
        
        # Calculate local time
        from datetime import timedelta
        local_time = self._current_time + timedelta(hours=tz_offset_hours)
        
        # Format time strings
        utc_str = self._current_time.strftime("%Y-%m-%d %H:%M:%S") + " UTC"
        tz_sign = "+" if tz_offset_hours >= 0 else "-"
        local_str = local_time.strftime("%H:%M:%S") + f" (UTC{tz_sign}{abs(tz_hours)}:{tz_mins:02d})"
        
        # Format LST
        lst_h = int(self._lst)
        lst_m = int((self._lst - lst_h) * 60)
        lst_s = ((self._lst - lst_h) * 60 - lst_m) * 60
        lst_str = f"LST: {lst_h:02d}h {lst_m:02d}m {lst_s:04.1f}s"
        
        # Format location
        lat_dir = "N" if self._observer_lat >= 0 else "S"
        lon_dir = "E" if self._observer_lon >= 0 else "W"
        loc_str = f"Loc: {abs(self._observer_lat):.1f}°{lat_dir}, {abs(self._observer_lon):.1f}°{lon_dir}"
        
        # Calculate hour angle and parallactic angle for display
        ha_hours = self._lst - self.center_ra
        while ha_hours > 12:
            ha_hours -= 24
        while ha_hours < -12:
            ha_hours += 24
        ha_sign = "+" if ha_hours >= 0 else ""
        pa_deg = math.degrees(self._parallactic_angle)
        pa_str = f"HA:{ha_sign}{ha_hours:.1f}h PA:{pa_deg:+.1f}°"
        
        # Draw semi-transparent background box
        padding = 8
        line_height = 16
        box_width = 220
        box_height = line_height * 5 + padding * 2
        
        x = self.width - box_width - 10
        y = 10
        
        # Store bounds for click detection
        self._time_overlay_bounds = (x, y, x + box_width, y + box_height)
        
        # Dark background with transparency effect (clickable indicator)
        self.canvas.create_rectangle(x, y, x + box_width, y + box_height,
                                    fill='#0a0a20', outline='#4444aa',
                                    tags="time_overlay")
        
        # Click hint
        self.canvas.create_text(x + box_width - 5, y + 5,
                               text="⚙", fill='#666688', font=('Arial', 10),
                               anchor=tk.NE, tags="time_overlay")
        
        # Draw text lines
        text_x = x + padding
        font = ('Consolas', 10)
        
        self.canvas.create_text(text_x, y + padding + line_height * 0.5,
                               text=utc_str, fill='#88aaff', font=font,
                               anchor=tk.W, tags="time_overlay")
        self.canvas.create_text(text_x, y + padding + line_height * 1.5,
                               text=local_str, fill='#aaaaff', font=font,
                               anchor=tk.W, tags="time_overlay")
        self.canvas.create_text(text_x, y + padding + line_height * 2.5,
                               text=lst_str, fill='#aaffaa', font=font,
                               anchor=tk.W, tags="time_overlay")
        self.canvas.create_text(text_x, y + padding + line_height * 3.5,
                               text=loc_str, fill='#ffaa88', font=font,
                               anchor=tk.W, tags="time_overlay")
        self.canvas.create_text(text_x, y + padding + line_height * 4.5,
                               text=pa_str, fill='#ffaaff', font=font,
                               anchor=tk.W, tags="time_overlay")
    
    def _draw_fov_rectangle(self):
        """Draw a FOV rectangle overlay showing camera field of view"""
        # Calculate the FOV rectangle in canvas coordinates
        # The rectangle represents what a camera with certain optics would see
        
        fov_w = self.fov_width
        fov_h = self.fov_height
        
        # Calculate pixel dimensions of the FOV rectangle
        rect_w_pixels = (self._fov_rect_width_deg / fov_w) * self.width
        rect_h_pixels = (self._fov_rect_height_deg / fov_h) * self.height
        
        # Center the rectangle
        cx, cy = self.width / 2, self.height / 2
        x1 = cx - rect_w_pixels / 2
        y1 = cy - rect_h_pixels / 2
        x2 = cx + rect_w_pixels / 2
        y2 = cy + rect_h_pixels / 2
        
        # Draw the rectangle
        self.canvas.create_rectangle(x1, y1, x2, y2,
                                    outline=self._fov_rect_color, width=2,
                                    tags="fov_rect")
        
        # Draw corner marks for better visibility
        corner_len = 15
        # Top-left
        self.canvas.create_line(x1, y1, x1 + corner_len, y1, fill=self._fov_rect_color, width=3)
        self.canvas.create_line(x1, y1, x1, y1 + corner_len, fill=self._fov_rect_color, width=3)
        # Top-right
        self.canvas.create_line(x2, y1, x2 - corner_len, y1, fill=self._fov_rect_color, width=3)
        self.canvas.create_line(x2, y1, x2, y1 + corner_len, fill=self._fov_rect_color, width=3)
        # Bottom-left
        self.canvas.create_line(x1, y2, x1 + corner_len, y2, fill=self._fov_rect_color, width=3)
        self.canvas.create_line(x1, y2, x1, y2 - corner_len, fill=self._fov_rect_color, width=3)
        # Bottom-right
        self.canvas.create_line(x2, y2, x2 - corner_len, y2, fill=self._fov_rect_color, width=3)
        self.canvas.create_line(x2, y2, x2, y2 - corner_len, fill=self._fov_rect_color, width=3)
        
        # Label with FOV dimensions
        fov_label = f"Camera FOV: {self._fov_rect_width_deg:.1f}° × {self._fov_rect_height_deg:.1f}°"
        self.canvas.create_text(cx, y1 - 10, text=fov_label,
                               fill=self._fov_rect_color, font=('Arial', 10, 'bold'),
                               anchor=tk.S, tags="fov_rect")
    
    def _draw_target_marker(self):
        """Draw a target marker at the specified RA/DEC for GoTo testing"""
        if self._target_marker_ra is None or self._target_marker_dec is None:
            return
        
        pos = self.ra_dec_to_canvas(self._target_marker_ra, self._target_marker_dec)
        if pos is None:
            return
        
        x, y = pos
        color = '#00ff00'  # Green for target
        
        # Draw target marker (diamond with crosshair)
        size = 20
        # Diamond shape
        self.canvas.create_polygon(
            x, y - size,  # top
            x + size, y,  # right
            x, y + size,  # bottom
            x - size, y,  # left
            outline=color, fill='', width=2, tags="target_marker"
        )
        
        # Inner crosshair
        self.canvas.create_line(x - size + 5, y, x + size - 5, y,
                               fill=color, width=1, tags="target_marker")
        self.canvas.create_line(x, y - size + 5, x, y + size - 5,
                               fill=color, width=1, tags="target_marker")
        
        # Center dot
        self.canvas.create_oval(x - 3, y - 3, x + 3, y + 3,
                               fill=color, outline=color, tags="target_marker")
        
        # Label
        if self._target_marker_label:
            label = self._target_marker_label
        else:
            ra_h = int(self._target_marker_ra)
            ra_m = int((self._target_marker_ra - ra_h) * 60)
            dec_sign = "+" if self._target_marker_dec >= 0 else ""
            label = f"TARGET: {ra_h}h{ra_m:02d}m {dec_sign}{self._target_marker_dec:.1f}°"
        
        self.canvas.create_text(x, y - size - 5, text=label,
                               fill=color, font=('Arial', 10, 'bold'),
                               anchor=tk.S, tags="target_marker")
        
        # Distance from center
        cx, cy = self.width / 2, self.height / 2
        dist_pixels = math.sqrt((x - cx)**2 + (y - cy)**2)
        # Convert to degrees
        dist_deg = (dist_pixels / self.width) * self.fov_width
        dist_arcmin = dist_deg * 60
        
        if dist_arcmin < 1:
            dist_str = f'Offset: {dist_arcmin * 60:.1f}"'
        elif dist_arcmin < 60:
            dist_str = f"Offset: {dist_arcmin:.1f}'"
        else:
            dist_str = f"Offset: {dist_deg:.2f}°"
        
        self.canvas.create_text(x, y + size + 15, text=dist_str,
                               fill=color, font=('Arial', 9),
                               anchor=tk.N, tags="target_marker")
    
    def _draw_cursor_coords(self):
        """Draw coordinate readout at cursor position"""
        if self._cursor_ra is None or self._cursor_dec is None:
            return
        
        # Format coordinates
        ra_h = int(self._cursor_ra)
        ra_m = int((self._cursor_ra - ra_h) * 60)
        ra_s = ((self._cursor_ra - ra_h) * 60 - ra_m) * 60
        
        dec_sign = "+" if self._cursor_dec >= 0 else "-"
        dec_d = int(abs(self._cursor_dec))
        dec_m = int((abs(self._cursor_dec) - dec_d) * 60)
        dec_s = ((abs(self._cursor_dec) - dec_d) * 60 - dec_m) * 60
        
        coord_text = f"RA: {ra_h:02d}h {ra_m:02d}m {ra_s:04.1f}s\nDEC: {dec_sign}{dec_d:02d}° {dec_m:02d}' {dec_s:04.1f}\""
        
        # Draw in bottom-left corner
        padding = 10
        self.canvas.create_rectangle(padding - 5, self.height - 55, 200, self.height - padding + 5,
                                    fill='#0a0a20', outline='#444466', tags="cursor_coords")
        self.canvas.create_text(padding, self.height - 45,
                               text=coord_text, fill='#aaaaff',
                               font=('Consolas', 10), anchor=tk.NW, tags="cursor_coords")
    
    # Public methods for testing features
    def set_target_marker(self, ra_hours: Optional[float], dec_deg: Optional[float], label: str = ""):
        """
        Set a target marker at the specified coordinates.
        Use this to mark where your mount's GoTo should point.
        
        Args:
            ra_hours: Right Ascension in hours (None to clear)
            dec_deg: Declination in degrees (None to clear)
            label: Optional label for the marker
        """
        self._target_marker_ra = ra_hours
        self._target_marker_dec = dec_deg
        self._target_marker_label = label
    
    def clear_target_marker(self):
        """Clear the target marker"""
        self._target_marker_ra = None
        self._target_marker_dec = None
        self._target_marker_label = ""
    
    def set_fov_rectangle(self, enabled: bool, width_deg: float = 5.2, height_deg: float = 3.5, color: str = '#ffff00'):
        """
        Enable/disable the FOV rectangle overlay.
        
        Args:
            enabled: Whether to show the FOV rectangle
            width_deg: FOV width in degrees
            height_deg: FOV height in degrees
            color: Rectangle color
        """
        self._show_fov_rectangle = enabled
        self._fov_rect_width_deg = width_deg
        self._fov_rect_height_deg = height_deg
        self._fov_rect_color = color
    
    def set_reticle(self, enabled: bool = True, style: str = 'crosshair'):
        """
        Configure the center reticle.
        
        Args:
            enabled: Whether to show the reticle
            style: 'crosshair', 'circle', or 'target'
        """
        self._show_reticle = enabled
        self._reticle_style = style
    
    def set_cursor_coords_display(self, enabled: bool):
        """Enable/disable coordinate readout at cursor position"""
        self._show_cursor_coords = enabled
    
    def set_brightness(self, multiplier: float = 1.0, contrast: float = 1.0):
        """
        Set star brightness and contrast.
        
        Args:
            multiplier: Brightness multiplier (1.0 = normal)
            contrast: Contrast adjustment (1.0 = normal)
        """
        self._brightness_multiplier = max(0.1, min(3.0, multiplier))
        self._contrast = max(0.5, min(2.0, contrast))
    
    def set_time_info(self, current_time, lst: float, lat: float, lon: float):
        """
        Update time and location information for the overlay.
        
        Args:
            current_time: datetime object (UTC)
            lst: Local sidereal time in hours
            lat: Observer latitude in degrees
            lon: Observer longitude in degrees
        """
        self._current_time = current_time
        self._lst = lst
        self._observer_lat = lat
        self._observer_lon = lon
        
        # Recalculate parallactic angle for field rotation
        self._update_parallactic_angle()
    
    def _draw_object_info_overlay(self):
        """Draw object information in the bottom-right corner"""
        # Get the object to display (selected or hovered, or center object)
        obj = self._selected_object or self._hovered_object
        
        # If no object selected/hovered, find the closest object to center
        if obj is None:
            obj = self._find_center_object()
        
        if obj is None:
            return
        
        # Build info lines
        lines = []
        
        # Name
        lines.append(("Name:", obj.name, '#ffffff'))
        
        # Type
        obj_type = obj.object_type_enum
        lines.append(("Type:", obj_type.display_name, obj_type.color))
        
        # Coordinates
        ra_h = int(obj.ra_hours)
        ra_m = int((obj.ra_hours - ra_h) * 60)
        ra_s = ((obj.ra_hours - ra_h) * 60 - ra_m) * 60
        dec_sign = "+" if obj.dec_degrees >= 0 else ""
        dec_d = int(abs(obj.dec_degrees))
        dec_m = int((abs(obj.dec_degrees) - dec_d) * 60)
        dec_s = ((abs(obj.dec_degrees) - dec_d) * 60 - dec_m) * 60
        coord_str = f"{ra_h}h{ra_m:02d}m{ra_s:04.1f}s {dec_sign}{dec_d}°{dec_m:02d}'{dec_s:04.1f}\""
        lines.append(("Coords:", coord_str, '#aaaaff'))
        
        # Magnitude
        if obj.magnitude > 0:
            lines.append(("Mag:", f"{obj.magnitude:.1f}", '#ffaa88'))
        
        # Size (for DSOs)
        if obj.size_arcmin > 0:
            if obj.size_arcmin >= 60:
                size_str = f"{obj.size_arcmin/60:.1f}°"
            elif obj.size_arcmin >= 1:
                size_str = f"{obj.size_arcmin:.1f}'"
            else:
                size_str = f'{obj.size_arcmin*60:.1f}"'
            lines.append(("Size:", size_str, '#88ffaa'))
        
        # Catalog ID if different from name
        if obj.id and obj.id != obj.name:
            lines.append(("ID:", obj.id, '#888888'))
        
        # Draw the overlay box
        padding = 8
        line_height = 16
        label_width = 55
        box_width = 220
        box_height = len(lines) * line_height + padding * 2
        
        x = self.width - box_width - 10
        y = self.height - box_height - 10
        
        # Dark background
        self.canvas.create_rectangle(x, y, x + box_width, y + box_height,
                                    fill='#0a0a20', outline='#333366',
                                    tags="overlay")
        
        # Draw lines
        font = ('Consolas', 10)
        font_bold = ('Consolas', 10, 'bold')
        
        for i, (label, value, color) in enumerate(lines):
            text_y = y + padding + line_height * (i + 0.5)
            # Label
            self.canvas.create_text(x + padding, text_y,
                                   text=label, fill='#888888', font=font,
                                   anchor=tk.W, tags="overlay")
            # Value
            self.canvas.create_text(x + padding + label_width, text_y,
                                   text=value, fill=color, 
                                   font=font_bold if i == 0 else font,
                                   anchor=tk.W, tags="overlay")
    
    def _find_center_object(self) -> Optional[CelestialObject]:
        """Find the object closest to the center of the view"""
        best_obj = None
        best_dist = float('inf')
        
        # Search threshold in degrees (half of FOV)
        threshold = min(self.fov_width, self.fov_height) / 2
        
        for obj in self._dso_objects:
            # Calculate angular distance
            ra_diff = (obj.ra_hours - self.center_ra) * 15  # degrees
            dec_diff = obj.dec_degrees - self.center_dec
            
            # Simple distance (not accounting for cos(dec) for simplicity)
            dist = math.sqrt(ra_diff**2 + dec_diff**2)
            
            if dist < best_dist and dist < threshold:
                best_dist = dist
                best_obj = obj
        
        return best_obj
    
    def set_selected_object(self, obj: Optional[CelestialObject]):
        """Set the currently selected object"""
        self._selected_object = obj
    
    def set_hovered_object(self, obj: Optional[CelestialObject]):
        """Set the currently hovered object"""
        self._hovered_object = obj
    
    def _update_parallactic_angle(self):
        """
        Calculate the parallactic angle for the current view center.
        
        The parallactic angle is the angle between the direction to the 
        celestial pole and the zenith direction at the observation point.
        
        Formula: tan(q) = sin(HA) / (tan(lat)*cos(dec) - sin(dec)*cos(HA))
        where HA = hour angle = LST - RA
        
        Note: Field rotation is disabled by default as it causes discontinuities.
        """
        # Calculate hour angle (how far past meridian the target is)
        ha_hours = self._lst - self.center_ra
        # Normalize to -12 to +12 hours
        while ha_hours > 12:
            ha_hours -= 24
        while ha_hours < -12:
            ha_hours += 24
        
        ha_rad = math.radians(ha_hours * 15.0)
        lat_rad = math.radians(self._observer_lat)
        dec_rad = math.radians(self.center_dec)
        
        sin_ha = math.sin(ha_rad)
        cos_ha = math.cos(ha_rad)
        sin_dec = math.sin(dec_rad)
        cos_dec = math.cos(dec_rad)
        
        denominator = math.tan(lat_rad) * cos_dec - sin_dec * cos_ha
        
        if abs(denominator) < 1e-10:
            self._parallactic_angle = 0.0
        else:
            self._parallactic_angle = math.atan2(sin_ha, denominator)
    
    def _draw_object(self, obj: CelestialObject, pos: Tuple[float, float]):
        """Draw a celestial object"""
        x, y = pos
        obj_type = obj.object_type_enum
        color = obj_type.color
        
        # Calculate size: use real angular size for DSOs, magnitude for stars
        if obj.obj_type == "star" or obj.size_arcmin <= 0:
            size = self.magnitude_to_size(obj.magnitude)
            use_real_size = False
        else:
            # Use real angular size in pixels (diameter)
            size = self.arcmin_to_pixels(obj.size_arcmin)
            # Only enforce a minimum size for visibility (no maximum cap)
            size = max(4, size)
            use_real_size = True
        
        # For stars, use special star rendering
        if obj.obj_type == "star":
            self._draw_star(obj, pos, size, color)
            return
        
        # Try to draw DSO with image first
        if self._use_images and self._image_loader and self._image_loader.available:
            if self._draw_object_with_image(obj, pos, size, use_real_size):
                return  # Successfully drew with image
        
        # Fall back to symbol rendering
        self._draw_object_symbol(obj, pos, size, color, obj_type, use_real_size)
    
    def _draw_star(self, obj: CelestialObject, pos: Tuple[float, float], 
                   size: float, color: str):
        """
        Draw a photorealistic star with optional diffraction spikes.
        Designed to look realistic when photographed by a camera.
        
        Args:
            obj: The star object
            pos: Canvas position (x, y)
            size: Star size in pixels (radius)
            color: Star color
        """
        x, y = pos
        r = size
        
        # Get star color based on spectral type if available
        spectral = getattr(obj, 'spectral_type', None)
        if spectral:
            star_color = self._get_star_color(spectral)
        else:
            star_color = color
        
        # Draw diffraction spikes for bright stars (magnitude < 4)
        if self.show_diffraction_spikes and obj.magnitude < 4 and r >= 3:
            self._draw_diffraction_spikes(x, y, r, obj.magnitude, star_color)
        
        # Draw photorealistic star with multiple layers simulating Gaussian PSF
        # This creates a more realistic appearance for camera testing
        
        # Layer 1: Very faint outer halo (simulates atmospheric scatter)
        if r >= 4:
            halo_r = r * 2.5
            halo_color = self._dim_color(star_color, 0.08)
            self.canvas.create_oval(x - halo_r, y - halo_r, x + halo_r, y + halo_r,
                                   fill=halo_color, outline='', tags=("object", obj.id))
        
        # Layer 2: Outer glow (simulates seeing/defocus)
        if r >= 3:
            glow_r = r * 1.8
            glow_color = self._dim_color(star_color, 0.15)
            self.canvas.create_oval(x - glow_r, y - glow_r, x + glow_r, y + glow_r,
                                   fill=glow_color, outline='', tags=("object", obj.id))
        
        # Layer 3: Middle glow
        if r >= 2:
            mid_r = r * 1.3
            mid_color = self._dim_color(star_color, 0.35)
            self.canvas.create_oval(x - mid_r, y - mid_r, x + mid_r, y + mid_r,
                                   fill=mid_color, outline='', tags=("object", obj.id))
        
        # Layer 4: Inner glow
        inner_r = r * 0.9
        inner_color = self._dim_color(star_color, 0.6)
        self.canvas.create_oval(x - inner_r, y - inner_r, x + inner_r, y + inner_r,
                               fill=inner_color, outline='', tags=("object", obj.id))
        
        # Layer 5: Bright core (saturated center)
        core_r = r * 0.5
        self.canvas.create_oval(x - core_r, y - core_r, x + core_r, y + core_r,
                               fill=star_color, outline='', tags=("object", obj.id))
        
        # Layer 6: Hot center (white/saturated for very bright stars)
        if r >= 4 and obj.magnitude < 3:
            hot_r = r * 0.25
            # Blend star color with white for hot center
            hot_color = self._brighten_color(star_color, 0.7)
            self.canvas.create_oval(x - hot_r, y - hot_r, x + hot_r, y + hot_r,
                                   fill=hot_color, outline='', tags=("object", obj.id))
        
        # Draw label for named bright stars
        if self.show_labels and obj.name and obj.magnitude < 4:
            self.canvas.create_text(x + r * 2 + 5, y, text=obj.name,
                                   fill=star_color, font=('Arial', 8),
                                   anchor=tk.W, tags=("label", obj.id))
    
    def _draw_diffraction_spikes(self, x: float, y: float, r: float, 
                                  magnitude: float, color: str):
        """
        Draw diffraction spikes around a star.
        
        Args:
            x, y: Star center position
            r: Star radius
            magnitude: Star magnitude (brighter = longer spikes)
            color: Spike color
        """
        # Spike length based on magnitude (brighter = longer)
        # Mag -1.5 -> length ~40, Mag 3 -> length ~10
        base_length = max(8, 30 - magnitude * 5)
        spike_length = base_length * (r / 5)  # Scale with star size
        
        # Spike width tapers from center
        spike_width = max(1, r * 0.3)
        
        # Calculate spike angles
        rotation_rad = math.radians(self.diffraction_spike_rotation)
        angle_step = 2 * math.pi / self.diffraction_spike_count
        
        for i in range(self.diffraction_spike_count):
            angle = rotation_rad + i * angle_step
            
            # Calculate spike endpoints
            # Start slightly outside the star core
            start_dist = r * 0.5
            end_dist = r + spike_length
            
            x1 = x + math.cos(angle) * start_dist
            y1 = y + math.sin(angle) * start_dist
            x2 = x + math.cos(angle) * end_dist
            y2 = y + math.sin(angle) * end_dist
            
            # Draw spike (tapered line)
            # Use stipple for a softer look on longer spikes
            self.canvas.create_line(x1, y1, x2, y2,
                                   fill=color, width=spike_width,
                                   tags=("spike",))
            
            # Draw a thinner extension for very bright stars
            if magnitude < 2:
                ext_length = spike_length * 0.5
                x3 = x + math.cos(angle) * (end_dist + ext_length)
                y3 = y + math.sin(angle) * (end_dist + ext_length)
                dim_color = self._dim_color(color, 0.4)
                self.canvas.create_line(x2, y2, x3, y3,
                                       fill=dim_color, width=max(1, spike_width * 0.5),
                                       tags=("spike",))
    
    def _get_star_color(self, spectral_type: str) -> str:
        """Get star color based on spectral classification."""
        if not spectral_type:
            return "#FFFFFF"
        
        first_char = spectral_type[0].upper()
        colors = {
            'O': '#9BB0FF',  # Blue
            'B': '#AABFFF',  # Blue-white
            'A': '#CAD7FF',  # White
            'F': '#F8F7FF',  # Yellow-white
            'G': '#FFF4EA',  # Yellow (like Sun)
            'K': '#FFD2A1',  # Orange
            'M': '#FFCC6F',  # Red-orange
        }
        return colors.get(first_char, '#FFFFFF')
    
    def _dim_color(self, hex_color: str, factor: float) -> str:
        """
        Dim a hex color by a factor (0-1).
        
        Args:
            hex_color: Color in #RRGGBB format
            factor: Brightness factor (0=black, 1=original)
            
        Returns:
            Dimmed color in #RRGGBB format
        """
        # Parse hex color
        hex_color = hex_color.lstrip('#')
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
        
        # Dim and blend with background
        bg_r, bg_g, bg_b = 10, 10, 32  # Match canvas background #0a0a20
        r = int(r * factor + bg_r * (1 - factor))
        g = int(g * factor + bg_g * (1 - factor))
        b = int(b * factor + bg_b * (1 - factor))
        
        return f'#{r:02x}{g:02x}{b:02x}'
    
    def _brighten_color(self, hex_color: str, factor: float) -> str:
        """
        Brighten a hex color towards white.
        
        Args:
            hex_color: Color in #RRGGBB format
            factor: Blend factor with white (0=original, 1=white)
            
        Returns:
            Brightened color in #RRGGBB format
        """
        # Parse hex color
        hex_color = hex_color.lstrip('#')
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
        
        # Blend towards white
        r = int(r + (255 - r) * factor)
        g = int(g + (255 - g) * factor)
        b = int(b + (255 - b) * factor)
        
        return f'#{r:02x}{g:02x}{b:02x}'

    def _draw_object_with_image(self, obj: CelestialObject, pos: Tuple[float, float], 
                                 size: float, use_real_size: bool = False) -> bool:
        """
        Try to draw object with an image.
        
        Args:
            obj: The celestial object
            pos: Canvas position (x, y)
            size: Size in pixels
            use_real_size: If True, size represents real angular size in pixels
        
        Returns:
            True if image was drawn, False to fall back to symbol
        """
        x, y = pos
        
        if obj.obj_type == "star":
            # Get spectral type from object if available
            spectral = getattr(obj, 'spectral_type', 'G')
            img_size = max(4, int(size * 3))
            image = self._image_loader.get_star_image(
                spectral_type=spectral,
                magnitude=obj.magnitude,
                size=(img_size, img_size)
            )
        else:
            # For DSOs, use the real angular size if available
            if use_real_size:
                img_size = max(16, int(size))
            else:
                img_size = max(16, int(size * 6))
            
            # Try specific DSO image first, then generic
            image = self._image_loader.get_dso_image(obj.id, size=(img_size, img_size))
            if image is None:
                image = self._image_loader.get_generic_dso_image(obj.obj_type, size=(img_size, img_size))
        
        if image:
            self._active_images.append(image)  # Keep reference
            self.canvas.create_image(x, y, image=image, tags=("object", obj.id))
            
            # Still draw label
            if self.show_labels:
                label = obj.name if obj.name else obj.id
                if obj.obj_type != "star" or (obj.name and obj.magnitude < 4):
                    self.canvas.create_text(x + img_size // 2 + 3, y, text=label,
                                           fill=obj.object_type_enum.color, 
                                           font=('Arial', 8),
                                           anchor=tk.W, tags=("label", obj.id))
            return True
        
        return False
    
    def _draw_object_symbol(self, obj: CelestialObject, pos: Tuple[float, float],
                            size: float, color: str, obj_type: ObjectType,
                            use_real_size: bool = False):
        """
        Draw DSO using traditional astronomical symbols.
        
        Args:
            obj: The celestial object
            pos: Canvas position (x, y)
            size: Size in pixels (diameter if use_real_size=True)
            color: Color for the symbol
            obj_type: Object type enum
            use_real_size: If True, size represents real angular size (diameter)
        """
        x, y = pos
        
        # For real-sized DSOs, size is diameter - convert to radius
        # Ensure minimum visibility
        if use_real_size:
            r = max(4, size / 2)  # radius from diameter, min 4px
        else:
            r = max(3, size)  # magnitude-based size is already radius-like
        
        if obj_type == ObjectType.GALAXY:
            # Ellipse for galaxies (elongated shape)
            rx = r
            ry = r * 0.5
            self.canvas.create_oval(x - rx, y - ry, x + rx, y + ry,
                                   outline=color, width=2, tags=("object", obj.id))
        elif obj_type in (ObjectType.NEBULA, ObjectType.CLUSTER_NEBULA):
            # Square for nebulae
            self.canvas.create_rectangle(x - r, y - r, x + r, y + r,
                                        outline=color, width=2, tags=("object", obj.id))
        elif obj_type == ObjectType.OPEN_CLUSTER:
            # Dashed circle for open clusters
            self.canvas.create_oval(x - r, y - r, x + r, y + r,
                                   outline=color, width=1, dash=(3, 3),
                                   tags=("object", obj.id))
        elif obj_type == ObjectType.GLOBULAR_CLUSTER:
            # Circle with cross for globular clusters
            self.canvas.create_oval(x - r, y - r, x + r, y + r,
                                   outline=color, width=2, tags=("object", obj.id))
            cross_r = r * 0.6
            self.canvas.create_line(x - cross_r, y, x + cross_r, y,
                                   fill=color, tags=("object", obj.id))
            self.canvas.create_line(x, y - cross_r, x, y + cross_r,
                                   fill=color, tags=("object", obj.id))
        elif obj_type == ObjectType.PLANETARY_NEBULA:
            # Circle with lines for planetary nebulae
            self.canvas.create_oval(x - r, y - r, x + r, y + r,
                                   outline=color, width=2, tags=("object", obj.id))
            line_ext = r * 0.4
            self.canvas.create_line(x - r - line_ext, y, x - r, y,
                                   fill=color, tags=("object", obj.id))
            self.canvas.create_line(x + r, y, x + r + line_ext, y,
                                   fill=color, tags=("object", obj.id))
        else:
            # Default circle
            self.canvas.create_oval(x - r, y - r, x + r, y + r,
                                   outline=color, width=1, tags=("object", obj.id))
        
        # Draw label if enabled (for DSOs, not stars - stars handled in _draw_star)
        if self.show_labels:
            label = obj.name if obj.name else obj.id
            label_offset = r + 5
            self.canvas.create_text(x + label_offset, y, text=label,
                                   fill=color, font=('Arial', 8),
                                   anchor=tk.W, tags=("label", obj.id))
    
    def draw_measurement_point(self, ra: float, dec: float, index: int):
        """Draw a measurement point"""
        pos = self.ra_dec_to_canvas(ra, dec)
        if pos:
            x, y = pos
            self.canvas.create_oval(x - 5, y - 5, x + 5, y + 5,
                                   fill='#FF0000', outline='white', width=2,
                                   tags="measure")
            self.canvas.create_text(x, y - 12, text=f"P{index}",
                                   fill='white', font=('Arial', 9, 'bold'),
                                   tags="measure")
    
    def draw_measurement_line(self, ra1: float, dec1: float,
                             ra2: float, dec2: float):
        """Draw a line between two measurement points"""
        pos1 = self.ra_dec_to_canvas(ra1, dec1)
        pos2 = self.ra_dec_to_canvas(ra2, dec2)
        
        if pos1 and pos2:
            self.canvas.create_line(pos1[0], pos1[1], pos2[0], pos2[1],
                                   fill='#FF6666', width=2, dash=(4, 2),
                                   tags="measure")
    
    def set_cursor(self, cursor: str):
        """Set the canvas cursor"""
        self.canvas.config(cursor=cursor)
    
    def _on_resize(self, event):
        """Handle canvas resize"""
        self.parent.after(100, lambda: self.render())
    
    def _on_click(self, event):
        """Handle canvas click"""
        if self.on_click_callback:
            ra, dec = self.canvas_to_ra_dec(event.x, event.y)
            self.on_click_callback(ra, dec)
    
    def _on_motion(self, event):
        """Handle mouse motion"""
        # Update cursor coordinates for display
        ra, dec = self.canvas_to_ra_dec(event.x, event.y)
        self._cursor_ra = ra
        self._cursor_dec = dec
        
        if self.on_motion_callback:
            self.on_motion_callback(ra, dec)
        
        # If showing cursor coords, need to re-render
        if self._show_cursor_coords:
            # Only update the cursor coords overlay, not full render
            self.canvas.delete("cursor_coords")
            self._draw_cursor_coords()
    
    def _on_scroll(self, event):
        """Handle mouse scroll for zoom"""
        if event.num == 5 or (hasattr(event, 'delta') and event.delta < 0):
            # Zoom out
            new_focal = max(10, self.fov_calculator.focal_length * 0.9)
        else:
            # Zoom in
            new_focal = min(2000, self.fov_calculator.focal_length * 1.1)
        
        self.fov_calculator.focal_length = new_focal
        
        if self.on_zoom_callback:
            self.on_zoom_callback(new_focal)
        
        self.render()

    def _on_drag_start(self, event):
        """Handle start of drag operation"""
        # Check if clicking on time overlay
        if self._time_overlay_bounds:
            x1, y1, x2, y2 = self._time_overlay_bounds
            if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                # Clicked on time overlay
                if self._on_time_click_callback:
                    self._on_time_click_callback()
                return  # Don't start drag
        
        self._drag_start_x = event.x
        self._drag_start_y = event.y
        self._drag_last_x = event.x
        self._drag_last_y = event.y
        self._drag_start_ra = self.center_ra
        self._drag_start_dec = self.center_dec
        self._is_dragging = True
        self.canvas.config(cursor='fleur')  # Move cursor
    
    def set_on_time_click(self, callback: Callable[[], None]):
        """Set callback for when time overlay is clicked"""
        self._on_time_click_callback = callback
    
    def _on_drag(self, event):
        """Handle drag motion for panning - free movement in Alt-Az space"""
        if not self._is_dragging or self._drag_last_x is None:
            return
        
        # Calculate incremental pixel delta since last update
        dx = event.x - self._drag_last_x
        dy = event.y - self._drag_last_y
        
        # Update last position for next incremental update
        self._drag_last_x = event.x
        self._drag_last_y = event.y
        
        # Convert pixel delta to angular delta
        fov_w = self.fov_width
        fov_h = self.fov_height
        
        # Angular movement in degrees
        delta_x_deg = (dx / self.width) * fov_w
        delta_y_deg = (dy / self.height) * fov_h
        
        if self._altaz_mode:
            # In Alt-Az mode, convert screen movement to Alt-Az then back to RA/DEC
            lat_rad = math.radians(self._observer_lat)
            lst_rad = math.radians(self._lst * 15.0)
            center_ra_rad = math.radians(self.center_ra * 15.0)
            center_dec_rad = math.radians(self.center_dec)
            center_ha_rad = lst_rad - center_ra_rad
            
            # Current center altitude
            sin_alt = (math.sin(lat_rad) * math.sin(center_dec_rad) + 
                      math.cos(lat_rad) * math.cos(center_dec_rad) * math.cos(center_ha_rad))
            center_alt = math.asin(max(-1, min(1, sin_alt)))
            
            # Current center azimuth
            cos_az = (math.sin(center_dec_rad) - math.sin(lat_rad) * sin_alt) / (math.cos(lat_rad) * math.cos(center_alt) + 1e-10)
            cos_az = max(-1, min(1, cos_az))
            center_az = math.acos(cos_az)
            if math.sin(center_ha_rad) > 0:
                center_az = 2 * math.pi - center_az
            
            # Apply screen movement to Alt-Az
            # Drag left = content moves left = looking more to the east (higher az)
            new_az = center_az - math.radians(delta_x_deg)
            new_alt = center_alt + math.radians(delta_y_deg)
            
            # Clamp altitude
            new_alt = max(math.radians(-10), min(math.radians(90), new_alt))
            
            # Convert new Alt-Az back to RA/DEC
            sin_dec = (math.sin(lat_rad) * math.sin(new_alt) + 
                      math.cos(lat_rad) * math.cos(new_alt) * math.cos(new_az))
            new_dec_rad = math.asin(max(-1, min(1, sin_dec)))
            
            # HA = atan2(-sin(az)*cos(alt), cos(lat)*sin(alt) - sin(lat)*cos(alt)*cos(az))
            new_ha = math.atan2(-math.sin(new_az) * math.cos(new_alt),
                               math.cos(lat_rad) * math.sin(new_alt) - math.sin(lat_rad) * math.cos(new_alt) * math.cos(new_az))
            
            # RA = LST - HA
            new_ra_rad = lst_rad - new_ha
            new_ra = math.degrees(new_ra_rad) / 15.0
            new_dec = math.degrees(new_dec_rad)
            
            new_ra = CoordinateUtils.normalize_ra(new_ra)
            new_dec = CoordinateUtils.clamp_dec(new_dec)
        else:
            # Equatorial mode - direct RA/DEC movement
            delta_ra_hours = delta_x_deg / 15.0
            new_ra = CoordinateUtils.normalize_ra(self.center_ra + delta_ra_hours)
            new_dec = CoordinateUtils.clamp_dec(self.center_dec + delta_y_deg)
        
        self.center_ra = new_ra
        self.center_dec = new_dec
        
        # Re-render
        self.render()
    
    def _on_drag_end(self, event):
        """Handle end of drag operation"""
        self._is_dragging = False
        self._drag_start_x = None
        self._drag_start_y = None
        self._drag_last_x = None
        self._drag_last_y = None
        self.canvas.config(cursor='')  # Reset cursor
