# Visual asset provenance

Landing images were generated with OpenAI's built-in `image_gen` on **2026-09-20** for illustration. They are not evidence of detections, water classification or recorded animal motion. Sharp compresses the runtime WebP files. Generated PNG originals are archived under `web/docs/assets/`, outside the frontend's public directory.

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

Originals: `web/docs/assets/hero-poster.png`, `web/docs/assets/shrimp-observation.png`, and four corresponding PNGs under `web/docs/assets/swim/`. The hero original's recorded SHA-256 is `AD918CC8D1C8C57310B8AE5AC8022C52C500F4ED8CED649687F6918D3186BBF9`.

See [scene implementation](swimming-scene.md) and [generation prompts](landing-image-prompts.md). Runtime URLs are site-root-relative `/images/...`.

## Synthetic demos and excluded private media

Published dashboard/recording demo values are synthetic and separate from the real API. The AI demo also uses synthetic measurements, with separately persisted conversations/boards and real model calls when enabled.

The former standalone local preview used `frontend/public/demo/sample.mp4` and `sample.jpg`: the first eight output frames from the owner's private ventral-view shrimp footage, transcoded to H.264 with a first-frame still. Those assets are **excluded from this publication**, and the published demo does not bundle private footage or stills. The historical chart demo values were not claimed to originate from that short clip.

Generated landing illustrations are not substitutes for sample measurements or thumbnails of real recordings. Real video playback requires footage supplied by the operator and successful analysis.
