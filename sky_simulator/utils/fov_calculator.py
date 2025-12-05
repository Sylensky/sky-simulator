"""
Field of View (FOV) calculator for optical systems.
Calculates FOV based on focal length and sensor dimensions.
"""

import math
from typing import Tuple
from dataclasses import dataclass


@dataclass
class FOVResult:
    """Result of FOV calculation"""
    width_deg: float
    height_deg: float
    diagonal_deg: float
    
    @property
    def width_arcmin(self) -> float:
        return self.width_deg * 60
    
    @property
    def height_arcmin(self) -> float:
        return self.height_deg * 60
    
    @property
    def area_sq_deg(self) -> float:
        return self.width_deg * self.height_deg
    
    def __str__(self) -> str:
        return f"{self.width_deg:.2f}° × {self.height_deg:.2f}°"


class FOVCalculator:
    """
    Calculator for field of view based on optics and sensor size.
    
    The FOV is calculated using the formula:
    FOV = 2 * arctan(sensor_size / (2 * focal_length))
    
    This provides the actual angular field of view in degrees.
    """
    
    def __init__(self, focal_length_mm: float, 
                 sensor_width_mm: float, 
                 sensor_height_mm: float):
        """
        Initialize the FOV calculator.
        
        Args:
            focal_length_mm: Focal length in millimeters
            sensor_width_mm: Sensor width in millimeters
            sensor_height_mm: Sensor height in millimeters
        """
        self.focal_length = focal_length_mm
        self.sensor_width = sensor_width_mm
        self.sensor_height = sensor_height_mm
    
    @property
    def fov(self) -> FOVResult:
        """Calculate the field of view"""
        return self.calculate_fov(
            self.focal_length,
            self.sensor_width,
            self.sensor_height
        )
    
    @staticmethod
    def calculate_fov(focal_length_mm: float,
                      sensor_width_mm: float,
                      sensor_height_mm: float) -> FOVResult:
        """
        Calculate field of view for given optics parameters.
        
        Args:
            focal_length_mm: Focal length in mm
            sensor_width_mm: Sensor width in mm
            sensor_height_mm: Sensor height in mm
            
        Returns:
            FOVResult with width, height, and diagonal in degrees
        """
        fov_w = 2 * math.degrees(math.atan(sensor_width_mm / (2 * focal_length_mm)))
        fov_h = 2 * math.degrees(math.atan(sensor_height_mm / (2 * focal_length_mm)))
        
        # Diagonal FOV
        diagonal = math.sqrt(sensor_width_mm ** 2 + sensor_height_mm ** 2)
        fov_d = 2 * math.degrees(math.atan(diagonal / (2 * focal_length_mm)))
        
        return FOVResult(fov_w, fov_h, fov_d)
    
    @staticmethod
    def calculate_plate_scale(focal_length_mm: float) -> float:
        """
        Calculate plate scale in arcsec/mm.
        
        The plate scale determines how many arcseconds of sky
        correspond to 1mm on the sensor.
        
        Args:
            focal_length_mm: Focal length in mm
            
        Returns:
            Plate scale in arcseconds per millimeter
        """
        # 206265 arcsec/radian
        return 206265.0 / focal_length_mm
    
    @staticmethod
    def calculate_image_scale(focal_length_mm: float, 
                             pixel_size_um: float) -> float:
        """
        Calculate image scale in arcsec/pixel.
        
        Args:
            focal_length_mm: Focal length in mm
            pixel_size_um: Pixel size in micrometers
            
        Returns:
            Image scale in arcseconds per pixel
        """
        # Convert pixel size to mm
        pixel_size_mm = pixel_size_um / 1000.0
        plate_scale = FOVCalculator.calculate_plate_scale(focal_length_mm)
        return plate_scale * pixel_size_mm
    
    @staticmethod
    def focal_length_for_fov(desired_fov_deg: float, 
                             sensor_size_mm: float) -> float:
        """
        Calculate required focal length for a desired FOV.
        
        Args:
            desired_fov_deg: Desired field of view in degrees
            sensor_size_mm: Sensor dimension in mm (width or height)
            
        Returns:
            Required focal length in mm
        """
        fov_rad = math.radians(desired_fov_deg / 2)
        return sensor_size_mm / (2 * math.tan(fov_rad))
    
    def magnification_equivalent(self, reference_focal: float = 50.0) -> float:
        """
        Calculate 35mm equivalent magnification.
        
        Args:
            reference_focal: Reference focal length (default 50mm for "normal" lens)
            
        Returns:
            Magnification factor relative to reference
        """
        return self.focal_length / reference_focal
    
    def update(self, focal_length: float = None,
               sensor_width: float = None,
               sensor_height: float = None):
        """Update calculator parameters"""
        if focal_length is not None:
            self.focal_length = focal_length
        if sensor_width is not None:
            self.sensor_width = sensor_width
        if sensor_height is not None:
            self.sensor_height = sensor_height
