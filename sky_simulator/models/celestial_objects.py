"""
Celestial object data models.
Defines the data structures for stars, deep sky objects, and their properties.
"""

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ObjectType(Enum):
    """Types of celestial objects"""
    STAR = "star"
    GALAXY = "Gx"
    NEBULA = "Nb"
    OPEN_CLUSTER = "OC"
    GLOBULAR_CLUSTER = "Gb"
    PLANETARY_NEBULA = "Pl"
    DOUBLE_STAR = "D*"
    DOUBLE_STAR_ALT = "**"
    CLUSTER_NEBULA = "C+N"
    KNOT = "Kt"
    UNKNOWN = "?"
    
    @classmethod
    def from_string(cls, type_str: str) -> "ObjectType":
        """Convert string type to ObjectType enum"""
        type_map = {
            "star": cls.STAR,
            "*": cls.STAR,
            "Gx": cls.GALAXY,
            "Nb": cls.NEBULA,
            "OC": cls.OPEN_CLUSTER,
            "Gb": cls.GLOBULAR_CLUSTER,
            "Pl": cls.PLANETARY_NEBULA,
            "D*": cls.DOUBLE_STAR,
            "**": cls.DOUBLE_STAR_ALT,
            "C+N": cls.CLUSTER_NEBULA,
            "Kt": cls.KNOT,
        }
        return type_map.get(type_str, cls.UNKNOWN)
    
    @property
    def display_name(self) -> str:
        """Get human-readable name for the object type"""
        names = {
            ObjectType.STAR: "Star",
            ObjectType.GALAXY: "Galaxy",
            ObjectType.NEBULA: "Diffuse Nebula",
            ObjectType.OPEN_CLUSTER: "Open Cluster",
            ObjectType.GLOBULAR_CLUSTER: "Globular Cluster",
            ObjectType.PLANETARY_NEBULA: "Planetary Nebula",
            ObjectType.DOUBLE_STAR: "Double Star",
            ObjectType.DOUBLE_STAR_ALT: "Double Star",
            ObjectType.CLUSTER_NEBULA: "Cluster + Nebula",
            ObjectType.KNOT: "Knot",
            ObjectType.UNKNOWN: "Unknown",
        }
        return names.get(self, "Unknown")
    
    @property
    def color(self) -> str:
        """Get display color for the object type"""
        colors = {
            ObjectType.STAR: "#FFFFFF",
            ObjectType.GALAXY: "#FF6B6B",
            ObjectType.NEBULA: "#6BCB77",
            ObjectType.OPEN_CLUSTER: "#4D96FF",
            ObjectType.GLOBULAR_CLUSTER: "#FFD93D",
            ObjectType.PLANETARY_NEBULA: "#C780FA",
            ObjectType.DOUBLE_STAR: "#AAAAAA",
            ObjectType.DOUBLE_STAR_ALT: "#AAAAAA",
            ObjectType.CLUSTER_NEBULA: "#6BCB77",
            ObjectType.KNOT: "#FF9F45",
            ObjectType.UNKNOWN: "#888888",
        }
        return colors.get(self, "#FFFFFF")


@dataclass
class CelestialObject:
    """
    Represents a celestial object (star or DSO).
    
    Attributes:
        id: Unique identifier (e.g., "NGC7000", "HR1234")
        ra: Right Ascension in hours (0-24) for NGC catalog
        dec: Declination in degrees (-90 to +90) for NGC catalog
        magnitude: Visual magnitude (lower = brighter)
        obj_type: Type of object (string code like "Gx", "Nb", etc.)
        name: Common name if available
        size_arcmin: Angular size in arcminutes (for DSOs)
    """
    id: str
    ra: float  # Right Ascension in hours (0-24) for NGC, radians for stars
    dec: float  # Declination in degrees for NGC, radians for stars
    magnitude: float
    obj_type: str = "star"
    name: str = ""
    size_arcmin: float = 0.0  # Angular size in arcminutes
    
    @property
    def ra_hours(self) -> float:
        """Return RA in hours"""
        return self.ra
    
    @property
    def ra_degrees(self) -> float:
        """Return RA in degrees (0-360)"""
        return self.ra * 15.0  # 24 hours = 360 degrees
    
    @property
    def dec_degrees(self) -> float:
        """Return DEC in degrees"""
        return self.dec
    
    @property
    def object_type_enum(self) -> ObjectType:
        """Get ObjectType enum for this object"""
        return ObjectType.from_string(self.obj_type)
    
    @property
    def display_name(self) -> str:
        """Get the best display name for this object"""
        return self.name if self.name else self.id
    
    def format_ra(self) -> str:
        """Format RA as hours, minutes, seconds string"""
        ra_h = int(self.ra_hours)
        ra_m = int((self.ra_hours - ra_h) * 60)
        ra_s = ((self.ra_hours - ra_h) * 60 - ra_m) * 60
        return f"{ra_h}h {ra_m}m {ra_s:.2f}s"
    
    def format_dec(self) -> str:
        """Format DEC as degrees, arcmin, arcsec string"""
        dec = self.dec_degrees
        dec_sign = '+' if dec >= 0 else '-'
        dec = abs(dec)
        dec_d = int(dec)
        dec_m = int((dec - dec_d) * 60)
        dec_s = ((dec - dec_d) * 60 - dec_m) * 60
        return f"{dec_sign}{dec_d}° {dec_m}' {dec_s:.1f}\""
    
    def __str__(self) -> str:
        return f"{self.id} ({self.obj_type}) at RA={self.format_ra()}, DEC={self.format_dec()}"


@dataclass 
class StarObject(CelestialObject):
    """
    Star from BSC5 catalog.
    
    Note: RA/DEC are stored in radians for BSC5 stars,
    so we override the conversion properties.
    """
    
    @property
    def ra_hours(self) -> float:
        """Convert RA from radians to hours"""
        return self.ra * 12.0 / math.pi
    
    @property
    def ra_degrees(self) -> float:
        """Convert RA from radians to degrees"""
        return math.degrees(self.ra)
    
    @property
    def dec_degrees(self) -> float:
        """Convert DEC from radians to degrees"""
        return math.degrees(self.dec)


@dataclass
class SensorPreset:
    """Represents a camera sensor size preset"""
    name: str
    width_mm: float
    height_mm: float
    
    @property
    def aspect_ratio(self) -> float:
        """Calculate aspect ratio (width/height)"""
        return self.width_mm / self.height_mm
    
    @property
    def diagonal_mm(self) -> float:
        """Calculate diagonal size in mm"""
        return math.sqrt(self.width_mm ** 2 + self.height_mm ** 2)


# Common sensor presets
SENSOR_PRESETS = {
    "Full Frame (36x24mm)": SensorPreset("Full Frame", 36.0, 24.0),
    "APS-C Canon (22.3x14.9mm)": SensorPreset("APS-C Canon", 22.3, 14.9),
    "APS-C Nikon/Sony (23.5x15.6mm)": SensorPreset("APS-C Nikon/Sony", 23.5, 15.6),
    "Micro 4/3 (17.3x13mm)": SensorPreset("Micro 4/3", 17.3, 13.0),
    "1 inch (13.2x8.8mm)": SensorPreset("1 inch", 13.2, 8.8),
    "1/2.3 inch (6.17x4.55mm)": SensorPreset("1/2.3 inch", 6.17, 4.55),
    "Custom": SensorPreset("Custom", 36.0, 24.0),
}
