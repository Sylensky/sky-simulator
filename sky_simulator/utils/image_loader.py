"""
Image loader for celestial object images.
Handles loading, caching, and scaling of DSO and star images.
"""

import os
import math
from pathlib import Path
from typing import Dict, Optional, Tuple
from functools import lru_cache

try:
    from PIL import Image, ImageTk, ImageEnhance
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    Image = None
    ImageTk = None


class ImageLoader:
    """
    Loads and caches celestial object images.
    
    Images are expected to be in a directory structure like:
    images/
        dso/
            NGC7000.png
            NGC224.png
            ...
        stars/
            star_blue.png
            star_white.png
            star_red.png
            ...
    """
    
    def __init__(self, images_path: Path = None):
        """
        Initialize the image loader.
        
        Args:
            images_path: Base path for images directory
        """
        self.images_path = images_path
        self._image_cache: Dict[str, 'Image.Image'] = {}
        self._tk_image_cache: Dict[str, 'ImageTk.PhotoImage'] = {}
        self._available = PIL_AVAILABLE
        
        # Default star images by spectral class color
        self._star_colors = {
            'O': 'blue',
            'B': 'blue', 
            'A': 'white',
            'F': 'white',
            'G': 'yellow',
            'K': 'orange',
            'M': 'red',
        }
    
    @property
    def available(self) -> bool:
        """Check if image loading is available (PIL installed)"""
        return self._available and self.images_path is not None
    
    def set_images_path(self, path: Path):
        """Set the base path for images"""
        self.images_path = path
        self._image_cache.clear()
        self._tk_image_cache.clear()
    
    def get_dso_image(self, object_id: str, size: Tuple[int, int] = (64, 64)) -> Optional['ImageTk.PhotoImage']:
        """
        Get a DSO image scaled to the specified size.
        
        Args:
            object_id: The DSO identifier (e.g., "NGC7000")
            size: Target size as (width, height)
            
        Returns:
            PhotoImage for use with tkinter, or None if not found
        """
        if not self.available:
            return None
        
        cache_key = f"dso_{object_id}_{size[0]}x{size[1]}"
        
        if cache_key in self._tk_image_cache:
            return self._tk_image_cache[cache_key]
        
        # Try to load the image
        image = self._load_dso_image(object_id)
        if image is None:
            return None
        
        # Scale the image
        scaled = self._scale_image(image, size)
        if scaled is None:
            return None
        
        # Convert to PhotoImage
        tk_image = ImageTk.PhotoImage(scaled)
        self._tk_image_cache[cache_key] = tk_image
        
        return tk_image
    
    def get_star_image(self, spectral_type: str = 'G', magnitude: float = 5.0,
                       size: Tuple[int, int] = (16, 16)) -> Optional['ImageTk.PhotoImage']:
        """
        Get a star image based on spectral type and magnitude.
        
        Args:
            spectral_type: The star's spectral classification
            magnitude: Visual magnitude (affects brightness)
            size: Target size as (width, height)
            
        Returns:
            PhotoImage for use with tkinter, or None if not found
        """
        if not self.available:
            return None
        
        # Determine color from spectral type
        color = 'white'
        if spectral_type:
            first_char = spectral_type[0].upper()
            color = self._star_colors.get(first_char, 'white')
        
        cache_key = f"star_{color}_{size[0]}x{size[1]}"
        
        if cache_key in self._tk_image_cache:
            return self._tk_image_cache[cache_key]
        
        # Try to load the star image
        image = self._load_star_image(color)
        if image is None:
            return None
        
        # Scale the image
        scaled = self._scale_image(image, size)
        if scaled is None:
            return None
        
        # Convert to PhotoImage
        tk_image = ImageTk.PhotoImage(scaled)
        self._tk_image_cache[cache_key] = tk_image
        
        return tk_image
    
    def get_generic_dso_image(self, obj_type: str, size: Tuple[int, int] = (32, 32)) -> Optional['ImageTk.PhotoImage']:
        """
        Get a generic DSO image based on object type.
        
        Args:
            obj_type: Object type code (Gx, Nb, OC, Gb, Pl)
            size: Target size as (width, height)
            
        Returns:
            PhotoImage for use with tkinter, or None if not found
        """
        if not self.available:
            return None
        
        type_to_file = {
            'Gx': 'galaxy',
            'Nb': 'nebula',
            'OC': 'open_cluster',
            'Gb': 'globular_cluster',
            'Pl': 'planetary_nebula',
            'C+N': 'cluster_nebula',
        }
        
        filename = type_to_file.get(obj_type, 'generic')
        cache_key = f"generic_{filename}_{size[0]}x{size[1]}"
        
        if cache_key in self._tk_image_cache:
            return self._tk_image_cache[cache_key]
        
        # Try to load
        image = self._load_generic_image(filename)
        if image is None:
            return None
        
        scaled = self._scale_image(image, size)
        if scaled is None:
            return None
        
        tk_image = ImageTk.PhotoImage(scaled)
        self._tk_image_cache[cache_key] = tk_image
        
        return tk_image
    
    def _load_dso_image(self, object_id: str) -> Optional['Image.Image']:
        """Load a DSO image from disk"""
        if not self.images_path:
            return None
        
        dso_path = self.images_path / "dso"
        
        # Try different file extensions
        for ext in ['.png', '.jpg', '.jpeg', '.webp']:
            filepath = dso_path / f"{object_id}{ext}"
            if filepath.exists():
                try:
                    return Image.open(filepath).convert('RGBA')
                except Exception as e:
                    print(f"Error loading DSO image {filepath}: {e}")
        
        return None
    
    def _load_star_image(self, color: str) -> Optional['Image.Image']:
        """Load a star image from disk"""
        if not self.images_path:
            return None
        
        star_path = self.images_path / "stars"
        
        for ext in ['.png', '.jpg', '.jpeg', '.webp']:
            filepath = star_path / f"star_{color}{ext}"
            if filepath.exists():
                try:
                    return Image.open(filepath).convert('RGBA')
                except Exception as e:
                    print(f"Error loading star image {filepath}: {e}")
        
        return None
    
    def _load_generic_image(self, name: str) -> Optional['Image.Image']:
        """Load a generic DSO type image from disk"""
        if not self.images_path:
            return None
        
        generic_path = self.images_path / "generic"
        
        for ext in ['.png', '.jpg', '.jpeg', '.webp']:
            filepath = generic_path / f"{name}{ext}"
            if filepath.exists():
                try:
                    return Image.open(filepath).convert('RGBA')
                except Exception as e:
                    print(f"Error loading generic image {filepath}: {e}")
        
        return None
    
    def _scale_image(self, image: 'Image.Image', size: Tuple[int, int]) -> Optional['Image.Image']:
        """Scale an image to the target size"""
        try:
            # Use LANCZOS for high-quality downscaling
            return image.resize(size, Image.Resampling.LANCZOS)
        except Exception as e:
            print(f"Error scaling image: {e}")
            return None
    
    def clear_cache(self):
        """Clear all cached images"""
        self._image_cache.clear()
        self._tk_image_cache.clear()
    
    def preload_common_images(self, dso_ids: list = None):
        """
        Preload commonly used images into cache.
        
        Args:
            dso_ids: List of DSO IDs to preload
        """
        if not self.available:
            return
        
        # Preload star images
        for color in self._star_colors.values():
            self.get_star_image(color[0], size=(16, 16))
        
        # Preload generic DSO images
        for obj_type in ['Gx', 'Nb', 'OC', 'Gb', 'Pl']:
            self.get_generic_dso_image(obj_type, size=(32, 32))
        
        # Preload specific DSO images if provided
        if dso_ids:
            for dso_id in dso_ids:
                self.get_dso_image(dso_id, size=(64, 64))


# Global image loader instance
_image_loader: Optional[ImageLoader] = None


def get_image_loader() -> ImageLoader:
    """Get the global image loader instance"""
    global _image_loader
    if _image_loader is None:
        _image_loader = ImageLoader()
    return _image_loader


def init_image_loader(images_path: Path) -> ImageLoader:
    """Initialize the global image loader with a path"""
    global _image_loader
    _image_loader = ImageLoader(images_path)
    return _image_loader
