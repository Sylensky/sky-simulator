"""
Catalog loaders for NGC and BSC5 astronomical catalogs.
Handles loading, parsing, and searching celestial object data.
"""

import json
from pathlib import Path
from typing import List, Optional, Dict, Any
from abc import ABC, abstractmethod

from ..models.celestial_objects import CelestialObject, StarObject


class CatalogLoader(ABC):
    """Abstract base class for catalog loaders"""
    
    def __init__(self):
        self.objects: List[CelestialObject] = []
        self.loaded = False
    
    @abstractmethod
    def load(self, file_path: Path) -> bool:
        """Load catalog from file"""
        pass
    
    @abstractmethod
    def get_object_count(self) -> int:
        """Get number of loaded objects"""
        pass
    
    def find_by_id(self, object_id: str) -> Optional[CelestialObject]:
        """Find object by exact ID match"""
        object_id_upper = object_id.upper()
        for obj in self.objects:
            if obj.id.upper() == object_id_upper:
                return obj
        return None
    
    def find_by_name(self, name: str) -> Optional[CelestialObject]:
        """Find object by name (case insensitive)"""
        name_upper = name.upper()
        for obj in self.objects:
            if obj.name.upper() == name_upper:
                return obj
        return None
    
    def search(self, query: str) -> List[CelestialObject]:
        """Search objects by ID or name (partial match)"""
        query_upper = query.upper()
        results = []
        for obj in self.objects:
            if query_upper in obj.id.upper() or query_upper in obj.name.upper():
                results.append(obj)
        return results
    
    def get_objects_in_region(self, ra_center: float, dec_center: float,
                              ra_range: float, dec_range: float,
                              mag_limit: float = 15.0) -> List[CelestialObject]:
        """
        Get objects within a rectangular region.
        
        Args:
            ra_center: Center RA in hours
            dec_center: Center DEC in degrees
            ra_range: RA range in degrees
            dec_range: DEC range in degrees
            mag_limit: Maximum magnitude to include
            
        Returns:
            List of objects within the region
        """
        results = []
        ra_range_hours = ra_range / 15.0  # Convert degrees to hours
        
        for obj in self.objects:
            # Skip faint objects
            if obj.magnitude > mag_limit and obj.magnitude != 0:
                continue
            
            # Check DEC range
            if abs(obj.dec_degrees - dec_center) > dec_range / 2:
                continue
            
            # Check RA range (handle wraparound)
            delta_ra = obj.ra_hours - ra_center
            if delta_ra > 12:
                delta_ra -= 24
            elif delta_ra < -12:
                delta_ra += 24
            
            if abs(delta_ra) > ra_range_hours / 2:
                continue
            
            results.append(obj)
        
        return results


class NGCLoader(CatalogLoader):
    """Loader for NGC/IC catalog (JSON format)"""
    
    def load(self, file_path: Path) -> bool:
        """
        Load NGC catalog from JSON file.
        
        Expected format:
        [
            {
                "id": "NGC7000",
                "type": "Nb",
                "ra": 20.98,      # RA in hours
                "dec": 44.33,     # DEC in degrees
                "magnitude": 4.0,
                "size_arcmin": 60.0  # Angular size in arcminutes
            },
            ...
        ]
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self.objects = []
            for entry in data:
                obj = CelestialObject(
                    id=entry['id'],
                    ra=entry['ra'],
                    dec=entry['dec'],
                    magnitude=entry.get('magnitude', 99),
                    obj_type=entry.get('type', '?'),
                    name=entry['id'],  # Use ID as name for NGC objects
                    size_arcmin=entry.get('size_arcmin', 0.0)
                )
                self.objects.append(obj)
            
            self.loaded = True
            return True
            
        except Exception as e:
            print(f"Error loading NGC catalog: {e}")
            return False
    
    def get_object_count(self) -> int:
        return len(self.objects)
    
    def get_galaxies(self) -> List[CelestialObject]:
        """Get all galaxies from the catalog"""
        return [obj for obj in self.objects if obj.obj_type == "Gx"]
    
    def get_nebulae(self) -> List[CelestialObject]:
        """Get all nebulae from the catalog"""
        return [obj for obj in self.objects if obj.obj_type in ("Nb", "Pl")]
    
    def get_clusters(self) -> List[CelestialObject]:
        """Get all clusters from the catalog"""
        return [obj for obj in self.objects if obj.obj_type in ("OC", "Gb")]


class BSC5Loader(CatalogLoader):
    """Loader for Bright Star Catalog 5 (JSON format)"""
    
    def load(self, file_path: Path) -> bool:
        """
        Load BSC5 catalog from JSON file.
        
        Expected format:
        [
            {
                "xno": 15,
                "sra0": 0.0366...,   # RA in radians
                "sdec0": 0.5077...,  # DEC in radians
                "mag": 2.06,
                "name": "ALPHERATZ"
            },
            ...
        ]
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self.objects = []
            for entry in data:
                star = StarObject(
                    id=f"HR{entry['xno']}",
                    ra=entry['sra0'],      # Radians
                    dec=entry['sdec0'],    # Radians
                    magnitude=entry.get('mag', 6.0),
                    obj_type="star",
                    name=entry.get('name', '')
                )
                self.objects.append(star)
            
            self.loaded = True
            return True
            
        except Exception as e:
            print(f"Error loading BSC5 catalog: {e}")
            return False
    
    def get_object_count(self) -> int:
        return len(self.objects)
    
    def get_named_stars(self) -> List[StarObject]:
        """Get all stars with proper names"""
        return [obj for obj in self.objects if obj.name]
    
    def get_bright_stars(self, mag_limit: float = 4.0) -> List[StarObject]:
        """Get stars brighter than magnitude limit"""
        return [obj for obj in self.objects if obj.magnitude <= mag_limit]


class CatalogManager:
    """Manages multiple catalogs and provides unified search"""
    
    def __init__(self):
        self.ngc_loader = NGCLoader()
        self.bsc5_loader = BSC5Loader()
        self._catalogs_path: Optional[Path] = None
    
    def set_catalogs_path(self, path: Path):
        """Set the base path for catalog files"""
        self._catalogs_path = path
    
    def load_all(self, base_path: Path = None) -> bool:
        """Load all catalogs from the given base path"""
        if base_path:
            self._catalogs_path = base_path
        
        if not self._catalogs_path:
            return False
        
        success = True
        
        # Load NGC catalog - try multiple possible locations
        ngc_paths = [
            self._catalogs_path / "ngc2000.json",  # Direct in data/
            self._catalogs_path / "ngc" / "converted" / "ngc2000_compact.json",  # Legacy path
        ]
        ngc_loaded = False
        for ngc_path in ngc_paths:
            if ngc_path.exists():
                if self.ngc_loader.load(ngc_path):
                    ngc_loaded = True
                    break
        if not ngc_loaded:
            print(f"NGC catalog not found in {self._catalogs_path}")
            success = False
        
        # Load BSC5 catalog - try multiple possible locations
        bsc5_paths = [
            self._catalogs_path / "bsc5ra.json",  # Direct in data/
            self._catalogs_path / "bsc5" / "converted" / "bsc5ra_compact.json",  # Legacy path
        ]
        bsc5_loaded = False
        for bsc5_path in bsc5_paths:
            if bsc5_path.exists():
                if self.bsc5_loader.load(bsc5_path):
                    bsc5_loaded = True
                    break
        if not bsc5_loaded:
            print(f"BSC5 catalog not found in {self._catalogs_path}")
            success = False
        
        return success
    
    @property
    def ngc_objects(self) -> List[CelestialObject]:
        return self.ngc_loader.objects
    
    @property
    def stars(self) -> List[StarObject]:
        return self.bsc5_loader.objects
    
    @property
    def all_objects(self) -> List[CelestialObject]:
        return self.ngc_loader.objects + self.bsc5_loader.objects
    
    def find_object(self, identifier: str) -> Optional[CelestialObject]:
        """Find an object by ID or name in any catalog"""
        # Try NGC first
        obj = self.ngc_loader.find_by_id(identifier)
        if obj:
            return obj
        
        # Try BSC5
        obj = self.bsc5_loader.find_by_id(identifier)
        if obj:
            return obj
        
        # Try by name
        obj = self.bsc5_loader.find_by_name(identifier)
        if obj:
            return obj
        
        # Partial search
        results = self.search(identifier)
        if results:
            return results[0]
        
        return None
    
    def search(self, query: str) -> List[CelestialObject]:
        """Search all catalogs"""
        results = []
        results.extend(self.ngc_loader.search(query))
        results.extend(self.bsc5_loader.search(query))
        return results
    
    def get_status(self) -> Dict[str, Any]:
        """Get catalog loading status"""
        return {
            "ngc_loaded": self.ngc_loader.loaded,
            "ngc_count": self.ngc_loader.get_object_count(),
            "bsc5_loaded": self.bsc5_loader.loaded,
            "bsc5_count": self.bsc5_loader.get_object_count(),
            "total_count": self.ngc_loader.get_object_count() + self.bsc5_loader.get_object_count()
        }
