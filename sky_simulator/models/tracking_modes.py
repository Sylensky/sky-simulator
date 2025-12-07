"""
Tracking mode classes for sky simulation.

Each tracking mode defines how rotation is applied during simulation:
- How much rotation per tick
- Whether rotation resets on GoTo

The projection mode (RA-DEC vs Alt-Az) is handled separately and does NOT
change when simulation starts/stops.
"""

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Tuple, Optional


@dataclass
class TrackingState:
    """Current state of the tracking simulation"""
    center_ra: float  # hours
    center_dec: float  # degrees
    rotation_angle: float  # degrees, accumulated field rotation
    lst: float  # Local Sidereal Time in hours
    observer_lat: float  # degrees
    observer_lon: float  # degrees


@dataclass
class TrackingUpdate:
    """Result of a tracking tick update"""
    new_ra: float  # hours
    new_dec: float  # degrees
    delta_rotation: float  # degrees to add to rotation angle
    reset_rotation: bool = False  # If True, reset rotation angle to 0


class TrackingMode(ABC):
    """Abstract base class for tracking modes"""
    
    # Sidereal rotation rate: 360° per sidereal day (23h 56m 4s = 86164 seconds)
    SIDEREAL_RATE_DEG_PER_SEC = 360.0 / 86164.0  # ≈ 0.00417807 deg/sec
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Display name for this mode"""
        pass
    
    @property
    @abstractmethod
    def description(self) -> str:
        """Description of what this mode simulates"""
        pass
    
    @abstractmethod
    def calculate_update(
        self, 
        state: TrackingState, 
        sim_seconds: float,
        speed_multiplier: float
    ) -> TrackingUpdate:
        """
        Calculate the tracking update for one tick.
        
        Args:
            state: Current tracking state
            sim_seconds: Simulated seconds elapsed this tick (already multiplied by speed)
            speed_multiplier: The speed multiplier (for direction, can be negative)
            
        Returns:
            TrackingUpdate with rotation delta
        """
        pass
    
    def on_goto(self, target_ra: float, target_dec: float, state: TrackingState) -> Tuple[float, float, bool]:
        """
        Handle a GoTo command.
        
        Args:
            target_ra: Target RA in hours
            target_dec: Target DEC in degrees
            state: Current tracking state
            
        Returns:
            (new_ra, new_dec, reset_rotation) - coordinates and whether to reset rotation
        """
        # Default: go directly to target and reset rotation
        return target_ra, target_dec, True


class EquatorialTrackedMode(TrackingMode):
    """
    Equatorial mount with perfect sidereal tracking.
    
    - Mount compensates for Earth's rotation perfectly
    - Stars stay completely stationary in the field
    - No field rotation visible
    """
    
    @property
    def name(self) -> str:
        return "Equatorial (Tracked)"
    
    @property
    def description(self) -> str:
        return "Perfect sidereal tracking - stars stay fixed"
    
    def calculate_update(
        self, 
        state: TrackingState, 
        sim_seconds: float,
        speed_multiplier: float
    ) -> TrackingUpdate:
        # No rotation - perfect tracking
        return TrackingUpdate(
            new_ra=state.center_ra,
            new_dec=state.center_dec,
            delta_rotation=0.0
        )


class FieldRotationMode(TrackingMode):
    """
    Shows field rotation at sidereal rate around celestial pole.
    
    - Field rotates around celestial pole at sidereal rate
    - Objects stay at same RA/DEC but rotate in the field
    - Simulates untracked equatorial mount or field rotation effect
    """
    
    @property
    def name(self) -> str:
        return "Field Rotation"
    
    @property
    def description(self) -> str:
        return "Field rotates around pole at sidereal rate"
    
    def calculate_update(
        self, 
        state: TrackingState, 
        sim_seconds: float,
        speed_multiplier: float
    ) -> TrackingUpdate:
        # Field rotates at sidereal rate around celestial pole
        delta_angle = self.SIDEREAL_RATE_DEG_PER_SEC * sim_seconds
        if speed_multiplier < 0:
            delta_angle = -delta_angle
        
        return TrackingUpdate(
            new_ra=state.center_ra,
            new_dec=state.center_dec,
            delta_rotation=delta_angle
        )


class RADriftMode(TrackingMode):
    """
    Simulates RA drift - view center moves in RA at sidereal rate.
    
    - View center drifts in RA (like fixed camera, stars drift through)
    - No field rotation
    - Good for testing drift alignment
    """
    
    @property
    def name(self) -> str:
        return "RA Drift"
    
    @property
    def description(self) -> str:
        return "View drifts in RA at sidereal rate"
    
    def calculate_update(
        self, 
        state: TrackingState, 
        sim_seconds: float,
        speed_multiplier: float
    ) -> TrackingUpdate:
        # RA drifts at sidereal rate (15°/hour = 1 hour RA per hour)
        # In hours: 1 hour of RA per sidereal hour
        ra_drift_hours_per_sec = 1.0 / 3600.0  # 1 hour RA per 3600 seconds
        
        delta_ra = ra_drift_hours_per_sec * sim_seconds
        if speed_multiplier < 0:
            delta_ra = -delta_ra
        
        new_ra = (state.center_ra + delta_ra) % 24.0
        
        return TrackingUpdate(
            new_ra=new_ra,
            new_dec=state.center_dec,
            delta_rotation=0.0
        )


class TrackingModeManager:
    """
    Manages tracking modes and provides easy access to them.
    """
    
    def __init__(self, camera_angle_deg: float = 63.0):
        """
        Initialize with camera setup parameters.
        
        Args:
            camera_angle_deg: Angle of camera from polar axis (0° = looking at pole)
        """
        self.camera_angle = camera_angle_deg
        
        # Initialize available modes
        self._modes = {
            'equatorial': EquatorialTrackedMode(),
            'field_rotation': FieldRotationMode(),
            'ra_drift': RADriftMode(),
        }
        
        self._current_mode_key = 'field_rotation'
    
    @property
    def modes(self) -> dict:
        """Get all available tracking modes"""
        return self._modes
    
    @property
    def current_mode(self) -> TrackingMode:
        """Get the currently active tracking mode"""
        return self._modes[self._current_mode_key]
    
    @property
    def current_mode_key(self) -> str:
        """Get the key of the current mode"""
        return self._current_mode_key
    
    def set_mode(self, mode_key: str) -> bool:
        """
        Set the current tracking mode.
        
        Args:
            mode_key: Key of the mode to activate
            
        Returns:
            True if mode was changed, False if invalid key
        """
        if mode_key in self._modes:
            self._current_mode_key = mode_key
            return True
        return False
    
    def get_mode(self, mode_key: str) -> Optional[TrackingMode]:
        """Get a specific tracking mode by key"""
        return self._modes.get(mode_key)
    
    def calculate_pole_viewing_position(self, observer_lat: float) -> Tuple[float, float]:
        """
        Calculate RA/DEC to position the view so Polaris is visible
        based on camera angle from polar axis.
        
        Args:
            observer_lat: Observer latitude in degrees
            
        Returns:
            (ra_hours, dec_degrees) for optimal pole viewing
        """
        POLARIS_RA = 2.530  # hours (2h 31m 49s)
        
        # Camera angle from polar axis determines DEC of view center
        view_dec = 90.0 - self.camera_angle
        view_ra = POLARIS_RA
        
        return view_ra, view_dec
    
    def get_mode_display_names(self) -> dict:
        """Get mapping of mode keys to display names"""
        return {key: mode.name for key, mode in self._modes.items()}


# Convenience function to create a default manager
def create_tracking_manager(camera_angle: float = 63.0) -> TrackingModeManager:
    """Create a tracking mode manager with given camera angle"""
    return TrackingModeManager(camera_angle_deg=camera_angle)
