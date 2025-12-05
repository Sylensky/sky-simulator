"""
Coordinate utilities for astronomical calculations.
Handles RA/DEC coordinate transformations and angular distance calculations.
"""

import math
from typing import Tuple, Optional


class CoordinateUtils:
    """
    Utility class for astronomical coordinate calculations.
    
    All methods are static and work with the standard astronomical
    coordinate system:
    - Right Ascension (RA): 0-24 hours
    - Declination (DEC): -90 to +90 degrees
    """
    
    @staticmethod
    def ra_to_degrees(ra_hours: float) -> float:
        """Convert Right Ascension from hours to degrees"""
        return ra_hours * 15.0  # 24 hours = 360 degrees
    
    @staticmethod
    def degrees_to_ra(degrees: float) -> float:
        """Convert degrees to Right Ascension hours"""
        return degrees / 15.0
    
    @staticmethod
    def radians_to_ra_hours(radians: float) -> float:
        """Convert radians to RA hours"""
        return radians * 12.0 / math.pi
    
    @staticmethod
    def ra_hours_to_radians(ra_hours: float) -> float:
        """Convert RA hours to radians"""
        return ra_hours * math.pi / 12.0
    
    @staticmethod
    def normalize_ra(ra_hours: float) -> float:
        """Normalize RA to 0-24 hour range"""
        while ra_hours < 0:
            ra_hours += 24
        while ra_hours >= 24:
            ra_hours -= 24
        return ra_hours
    
    @staticmethod
    def clamp_dec(dec_deg: float) -> float:
        """Clamp declination to -90 to +90 range"""
        return max(-90, min(90, dec_deg))
    
    @staticmethod
    def angular_distance(ra1_h: float, dec1_deg: float, 
                         ra2_h: float, dec2_deg: float) -> float:
        """
        Calculate angular distance between two points using haversine formula.
        
        Args:
            ra1_h: RA of first point in hours
            dec1_deg: DEC of first point in degrees
            ra2_h: RA of second point in hours
            dec2_deg: DEC of second point in degrees
            
        Returns:
            Angular distance in degrees
        """
        # Convert to radians
        ra1 = math.radians(ra1_h * 15)  # hours to degrees to radians
        ra2 = math.radians(ra2_h * 15)
        dec1 = math.radians(dec1_deg)
        dec2 = math.radians(dec2_deg)
        
        # Haversine formula
        delta_ra = ra2 - ra1
        delta_dec = dec2 - dec1
        
        a = math.sin(delta_dec / 2) ** 2 + \
            math.cos(dec1) * math.cos(dec2) * math.sin(delta_ra / 2) ** 2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        
        return math.degrees(c)
    
    @staticmethod
    def degrees_to_arcmin(degrees: float) -> float:
        """Convert degrees to arcminutes"""
        return degrees * 60.0
    
    @staticmethod
    def degrees_to_arcsec(degrees: float) -> float:
        """Convert degrees to arcseconds"""
        return degrees * 3600.0
    
    @staticmethod
    def format_ra(ra_hours: float) -> str:
        """Format RA as hours, minutes, seconds string"""
        ra_h = int(ra_hours)
        ra_m = int((ra_hours - ra_h) * 60)
        ra_s = ((ra_hours - ra_h) * 60 - ra_m) * 60
        return f"{ra_h}h {ra_m}m {ra_s:.2f}s"
    
    @staticmethod
    def format_dec(dec_deg: float) -> str:
        """Format DEC as degrees, arcmin, arcsec string"""
        dec_sign = '+' if dec_deg >= 0 else '-'
        dec = abs(dec_deg)
        dec_d = int(dec)
        dec_m = int((dec - dec_d) * 60)
        dec_s = ((dec - dec_d) * 60 - dec_m) * 60
        return f"{dec_sign}{dec_d}° {dec_m}' {dec_s:.1f}\""
    
    @staticmethod
    def parse_ra(ra_string: str) -> Optional[float]:
        """
        Parse RA string in various formats to hours.
        
        Supports:
        - Decimal hours: "12.5"
        - HMS format: "12h 30m 0s" or "12:30:00"
        
        Returns:
            RA in hours, or None if parsing fails
        """
        try:
            # Try decimal first
            return float(ra_string)
        except ValueError:
            pass
        
        # Try HMS format
        import re
        
        # Pattern for "12h 30m 0s" or "12h30m0s"
        hms_pattern = r'(\d+)h\s*(\d+)m\s*([\d.]+)s?'
        match = re.match(hms_pattern, ra_string.lower())
        if match:
            h, m, s = match.groups()
            return float(h) + float(m) / 60 + float(s) / 3600
        
        # Pattern for "12:30:00"
        colon_pattern = r'(\d+):(\d+):([\d.]+)'
        match = re.match(colon_pattern, ra_string)
        if match:
            h, m, s = match.groups()
            return float(h) + float(m) / 60 + float(s) / 3600
        
        return None
    
    @staticmethod
    def parse_dec(dec_string: str) -> Optional[float]:
        """
        Parse DEC string in various formats to degrees.
        
        Supports:
        - Decimal degrees: "45.5" or "-30.25"
        - DMS format: "+45° 30' 0\"" or "-30:15:00"
        
        Returns:
            DEC in degrees, or None if parsing fails
        """
        try:
            # Try decimal first
            return float(dec_string)
        except ValueError:
            pass
        
        import re
        
        # Pattern for "+45° 30' 0\"" or "45d 30m 0s"
        dms_pattern = r'([+-]?)(\d+)[°d]\s*(\d+)[\'m]\s*([\d.]+)[\"s]?'
        match = re.match(dms_pattern, dec_string)
        if match:
            sign, d, m, s = match.groups()
            value = float(d) + float(m) / 60 + float(s) / 3600
            return -value if sign == '-' else value
        
        # Pattern for "-30:15:00"
        colon_pattern = r'([+-]?)(\d+):(\d+):([\d.]+)'
        match = re.match(colon_pattern, dec_string)
        if match:
            sign, d, m, s = match.groups()
            value = float(d) + float(m) / 60 + float(s) / 3600
            return -value if sign == '-' else value
        
        return None
