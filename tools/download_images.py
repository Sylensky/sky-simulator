#!/usr/bin/env python3
"""
SkyView Image Downloader for Sky Simulator

Downloads DSO images from NASA's SkyView service.
https://skyview.gsfc.nasa.gov/

Usage:
    python download_images.py                    # Download top 100 brightest DSOs
    python download_images.py --all              # Download all DSOs (slow!)
    python download_images.py --ids NGC7000 M31  # Download specific objects
    python download_images.py --limit 50         # Download top 50 brightest
"""

import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.parse
from pathlib import Path
from typing import List, Dict, Optional

# SkyView API endpoint
SKYVIEW_URL = "https://skyview.gsfc.nasa.gov/cgi-bin/images"

# Default survey to use (Digitized Sky Survey is good for optical)
DEFAULT_SURVEY = "DSS2 Red"

# Alternative surveys for different object types
SURVEYS_BY_TYPE = {
    "Gx": "DSS2 Red",      # Galaxies - optical
    "Nb": "DSS2 Red",      # Nebulae - optical (could use H-Alpha)
    "OC": "DSS2 Red",      # Open clusters
    "Gb": "DSS2 Red",      # Globular clusters
    "Pl": "DSS2 Blue",     # Planetary nebulae - blue shows them better
}


def load_catalog(catalog_path: Path) -> List[Dict]:
    """Load the NGC catalog"""
    with open(catalog_path, 'r') as f:
        return json.load(f)


def get_image_url(ra_hours: float, dec_deg: float, size_arcmin: float,
                  survey: str = DEFAULT_SURVEY, pixels: int = 256) -> str:
    """
    Build SkyView URL for an image.
    
    Args:
        ra_hours: Right Ascension in hours
        dec_deg: Declination in degrees
        size_arcmin: Size of image in arcminutes
        survey: Survey to use
        pixels: Image size in pixels
        
    Returns:
        URL to download the image
    """
    # Convert RA from hours to degrees
    ra_deg = ra_hours * 15.0
    
    # Size in degrees (minimum 0.1 degrees for very small objects)
    size_deg = max(0.1, size_arcmin / 60.0 * 1.5)  # Add 50% padding
    
    params = {
        'Survey': survey,
        'Position': f'{ra_deg},{dec_deg}',
        'Size': str(size_deg),
        'Pixels': str(pixels),
        'Return': 'JPEG',
        'Scaling': 'Log',      # Logarithmic scaling shows faint details
        'Sampler': 'Lanczos',  # High quality resampling
    }
    
    query = urllib.parse.urlencode(params)
    return f"{SKYVIEW_URL}?{query}"


def download_image(url: str, output_path: Path, timeout: int = 30) -> bool:
    """
    Download an image from URL.
    
    Returns:
        True if successful, False otherwise
    """
    try:
        request = urllib.request.Request(url)
        request.add_header('User-Agent', 'SkySim/1.0 (educational)')
        
        with urllib.request.urlopen(request, timeout=timeout) as response:
            content = response.read()
            
            # Check if we got a valid image (JPEG starts with FFD8)
            if len(content) < 100 or content[:2] != b'\xff\xd8':
                print(f"  Warning: Invalid image data received")
                return False
            
            with open(output_path, 'wb') as f:
                f.write(content)
            return True
            
    except urllib.error.HTTPError as e:
        print(f"  HTTP Error {e.code}: {e.reason}")
        return False
    except urllib.error.URLError as e:
        print(f"  URL Error: {e.reason}")
        return False
    except Exception as e:
        print(f"  Error: {e}")
        return False


def download_dso_images(catalog: List[Dict], output_dir: Path,
                        limit: Optional[int] = None,
                        specific_ids: Optional[List[str]] = None,
                        pixels: int = 256,
                        delay: float = 1.0) -> Dict[str, int]:
    """
    Download images for DSOs from catalog.
    
    Args:
        catalog: List of DSO dictionaries
        output_dir: Directory to save images
        limit: Maximum number of images to download
        specific_ids: Only download these specific IDs
        pixels: Image resolution
        delay: Delay between requests (be nice to the server)
        
    Returns:
        Dictionary with download statistics
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    
    stats = {'success': 0, 'failed': 0, 'skipped': 0}
    
    # Filter and sort catalog
    if specific_ids:
        # Download specific objects
        objects = [obj for obj in catalog if obj['id'] in specific_ids]
    else:
        # Sort by magnitude (brightest first), filter out objects without size
        objects = [obj for obj in catalog if obj.get('size_arcmin', 0) > 0]
        objects = sorted(objects, key=lambda x: x.get('magnitude', 99))
        
        if limit:
            objects = objects[:limit]
    
    total = len(objects)
    print(f"Downloading images for {total} objects...")
    print(f"Output directory: {output_dir}")
    print()
    
    for i, obj in enumerate(objects, 1):
        obj_id = obj['id']
        output_path = output_dir / f"{obj_id}.jpg"
        
        # Skip if already exists
        if output_path.exists():
            print(f"[{i}/{total}] {obj_id}: Already exists, skipping")
            stats['skipped'] += 1
            continue
        
        ra = obj['ra']
        dec = obj['dec']
        size = obj.get('size_arcmin', 10)  # Default 10 arcmin if not specified
        obj_type = obj.get('type', 'Gx')
        survey = SURVEYS_BY_TYPE.get(obj_type, DEFAULT_SURVEY)
        
        print(f"[{i}/{total}] {obj_id} ({obj_type}): RA={ra:.2f}h DEC={dec:.1f}° Size={size:.1f}'")
        
        url = get_image_url(ra, dec, size, survey=survey, pixels=pixels)
        
        if download_image(url, output_path):
            print(f"  ✓ Saved to {output_path.name}")
            stats['success'] += 1
        else:
            stats['failed'] += 1
        
        # Be nice to the server
        if i < total:
            time.sleep(delay)
    
    return stats


def main():
    parser = argparse.ArgumentParser(
        description='Download DSO images from NASA SkyView',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                          Download top 100 brightest DSOs
  %(prog)s --all                    Download all DSOs (will take a long time!)
  %(prog)s --ids NGC7000 NGC224     Download specific objects
  %(prog)s --limit 50 --pixels 512  Download 50 objects at 512px resolution
  %(prog)s --catalog custom.json    Use custom catalog file
        """
    )
    
    parser.add_argument('--catalog', type=Path, 
                        default=Path('data/ngc2000.json'),
                        help='Path to NGC catalog JSON file')
    parser.add_argument('--output', type=Path,
                        default=Path('data/images/dso'),
                        help='Output directory for images')
    parser.add_argument('--limit', type=int, default=100,
                        help='Maximum number of images to download (default: 100)')
    parser.add_argument('--all', action='store_true',
                        help='Download all objects (overrides --limit)')
    parser.add_argument('--ids', nargs='+', metavar='ID',
                        help='Download specific object IDs only')
    parser.add_argument('--pixels', type=int, default=256,
                        help='Image resolution in pixels (default: 256)')
    parser.add_argument('--delay', type=float, default=1.0,
                        help='Delay between requests in seconds (default: 1.0)')
    
    args = parser.parse_args()
    
    # Check catalog exists
    if not args.catalog.exists():
        print(f"Error: Catalog file not found: {args.catalog}")
        sys.exit(1)
    
    # Load catalog
    print(f"Loading catalog from {args.catalog}...")
    catalog = load_catalog(args.catalog)
    print(f"Loaded {len(catalog)} objects")
    print()
    
    # Determine limit
    limit = None if args.all else args.limit
    
    # Download images
    stats = download_dso_images(
        catalog=catalog,
        output_dir=args.output,
        limit=limit,
        specific_ids=args.ids,
        pixels=args.pixels,
        delay=args.delay
    )
    
    # Print summary
    print()
    print("=" * 50)
    print("Download Summary:")
    print(f"  Successful: {stats['success']}")
    print(f"  Failed:     {stats['failed']}")
    print(f"  Skipped:    {stats['skipped']}")
    print("=" * 50)


if __name__ == '__main__':
    main()
