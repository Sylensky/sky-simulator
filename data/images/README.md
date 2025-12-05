# Celestial Object Images

This directory contains images for rendering celestial objects in the sky simulator.

## Directory Structure

```
images/
├── dso/           # Deep Sky Object images
│   ├── NGC7000.png    # North America Nebula
│   ├── NGC224.png     # Andromeda Galaxy (M31)
│   ├── NGC1976.png    # Orion Nebula (M42)
│   └── ...
├── stars/         # Star images by color
│   ├── star_blue.png
│   ├── star_white.png
│   ├── star_yellow.png
│   ├── star_orange.png
│   └── star_red.png
└── generic/       # Generic type images
    ├── galaxy.png
    ├── nebula.png
    ├── open_cluster.png
    ├── globular_cluster.png
    └── planetary_nebula.png
```

## Image Requirements

- **Format**: PNG with transparency (preferred), JPEG, or WebP
- **Size**: Any size (will be scaled dynamically)
- **Recommended resolution**: 128x128 or larger for DSOs, 32x32 for stars

## DSO Images

Name your DSO images with their catalog ID:
- `NGC7000.png` - North America Nebula
- `NGC224.png` or `M31.png` - Andromeda Galaxy
- `IC434.png` - Horsehead Nebula region

## Star Images

Star images are selected based on spectral type:
- **O, B class** → `star_blue.png`
- **A, F class** → `star_white.png`  
- **G class** → `star_yellow.png`
- **K class** → `star_orange.png`
- **M class** → `star_red.png`

## Generic Images

Used when no specific DSO image is available:
- `galaxy.png` - For type "Gx"
- `nebula.png` - For type "Nb"
- `open_cluster.png` - For type "OC"
- `globular_cluster.png` - For type "Gb"
- `planetary_nebula.png` - For type "Pl"

## Sources for Images

You can obtain astronomical images from:
- [NASA Image Gallery](https://images.nasa.gov/)
- [ESA/Hubble](https://esahubble.org/)
- [Stellarium](https://stellarium.org/) (bundled textures)
- Your own astrophotography!

Note: Ensure you have proper licensing rights for any images used.
