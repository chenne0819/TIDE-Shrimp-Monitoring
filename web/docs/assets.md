# Visual asset provenance

Landing images were generated with OpenAI image generation for illustration. They are not evidence of detections, water classification or recorded animal motion. The application uses compressed WebP files under `web/frontend/public/images/`.

## Runtime images

Paths below are relative to `web/frontend/public/`.

| File | Dimensions | Purpose |
| --- | --- | --- |
| `images/hero-poster.webp` | 1672 × 941 | Static fallback while loading, after failure, or with reduced motion |
| `images/shrimp-observation.webp` | 1672 × 941 | Three-shrimp observation illustration in the feature section |
| `images/swim/ocean-depth.webp` | 1024 × 1536 | Opaque surface/water-column/pond-bed background |
| `images/swim/shrimp-01.webp` | 1536 × 1024 | Transparent shrimp pose 1 |
| `images/swim/shrimp-02.webp` | 1536 × 1024 | Transparent shrimp pose 2 |
| `images/swim/shrimp-03.webp` | 1536 × 1024 | Transparent shrimp pose 3 |

The four swim layers total **883,224 bytes (approximately 863 KiB)**. Shrimp WebP files retain real alpha channels; do not discard alpha or expose RGB values stored beneath transparent pixels.

See the [scene implementation](swimming-scene.md) for image requirements and replacement instructions. Runtime URLs are site-root-relative `/images/...`.

## Synthetic demos and excluded private media

Published dashboard/recording demo values are synthetic and separate from the real API. The AI demo also uses synthetic measurements, with separately persisted conversations/boards and real model calls when enabled.

Private recordings and extracted stills are not bundled.

Generated landing illustrations are not substitutes for sample measurements or thumbnails of real recordings. Real video playback requires footage supplied by the operator and successful analysis.
