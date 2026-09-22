# Landing image generation record

Generated on 2026-09-20 with the built-in `image_gen` tool, without a CLI or external API key. This record preserves provenance and prompts for the retained assets; see the [asset inventory](assets.md). Originals are archived under `web/docs/assets/`, with runtime WebP files under `web/frontend/public/images/`. These are generated illustrations, not real measurements or footage.

## Static hero

Original: `web/docs/assets/hero-poster.png`; runtime: `web/frontend/public/images/hero-poster.webp`. Direction: one live-looking tiger prawn on the right, dark teal/black negative space on the left, natural underwater light and sandy bed, photographic style without text, logos or detection boxes. Only the direction was retained; the full original prompt is unavailable.

## Second-section observation scene

File: `web/docs/assets/shrimp-observation.png`

Generated independently: a side-above view of three tiger prawns, two clear and one farther away, using a different viewpoint from the hero close-up.

Final prompt:

```text
Use case: photorealistic-natural
Asset type: a wide editorial underwater image for the second section of a shrimp observation website.
Primary request: a realistic side-above camera view of three live tiger prawns (Penaeus monodon) moving slowly just above a dark sandy aquaculture pond bottom. Show two complete shrimp clearly with a third softly farther in the background. Use a different viewpoint from a side-profile hero: slightly overhead three-quarter angle, enough scene to observe whole bodies and their spacing.
Composition: panoramic landscape 16:9, the two main prawns separated with full tail fans and almost all long antennae visible, one near lower center and the second slightly farther upper-right; natural unposed grouping, not a collage. A little negative space along the upper-left. Deep water recedes behind.
Style: high-end natural history underwater photography, anatomically plausible segmented translucent brown and muted olive shells, distinct black tiger bands, delicate swimming legs and antennae, fine real texture rather than glossy CGI. A quiet charcoal and dark teal palette that works beside an existing deep teal underwater shrimp portrait.
Lighting: soft daylight entering from upper-right, subtle dappled water caustics, modest suspended particles, realistic green water, restrained highlights, detail visible in the shells. This is an image of shrimp for visual storytelling, not an analytical detection output.
Constraints: no text, no labels, no bounding boxes, no rulers, no charts, no UI, no fish, no coral, no aquarium equipment, no watermark. Single cohesive photograph.
```

## Transparent poses for the layered swimming scene

Background and shrimp were generated separately so the frontend can independently control camera and animal positions. All three transparent PNG poses came from built-in `image_gen`; sharp produced WebP files while retaining alpha.

| File | Dimensions | Size | Fully transparent pixels |
| --- | --- | ---: | ---: |
| `web/docs/assets/swim/shrimp-01.png` | 1536×1024 RGBA | 1,720,192 bytes | 79.79% |
| `web/docs/assets/swim/shrimp-02.png` | 1536×1024 RGBA | 1,694,990 bytes | 79.53% |
| `web/docs/assets/swim/shrimp-03.png` | 1536×1024 RGBA | 1,735,843 bytes | 79.04% |

Read-only sharp decoding confirmed real alpha in all three files, spanning 0–254. Transparent pixels may retain RGB underneath; compositing and WebP conversion must preserve alpha. Head/front-carapace positions are similar while legs/tail vary across strokes. Each pose depicts the same left-facing tiger prawn on equal-size canvases.

### Pose 01: initial generation

References were the hero shrimp and another pose of the same animal. The following framing edit then retained the full antennae. Both prompts contributed to the retained pose 01.

```text
Use case: background-extraction
Asset type: transparent PNG shrimp sprite, pose 01 of a consistent 3-pose swim cycle for a layered website scene.
Input image 1 is the identity reference: preserve this exact photorealistic tiger prawn's brown-olive shell, dark stripes, head shape, translucent legs and antennae. Input image 2 is another pose of the same shrimp for anatomy reference.
Primary request: render this ONE prawn isolated on a genuinely transparent background with a real alpha channel. Output RGBA PNG with every background pixel alpha=0. Absolutely no solid background, checkerboard pattern, water, haze, floor, aquarium, cast shadow, reflection or scenery.
Composition: landscape canvas approximately 1536x1024. Full complete tiger prawn side view, facing LEFT, head left and tail right, mostly horizontal with the tail very slightly lower. Include ALL antenna tips, full rostrum, all leg tips and the full tail fan with comfortable transparent margins. The complete animal INCLUDING antennae occupies about 80% of the canvas width, centered. Head/eye around x=49% and y=43%; tail around x=85% and y=58%; the antennae extend toward x=10% and curve naturally. Body remains substantial and detailed, not tiny.
Pose 01: the abdomen is comparatively extended, tail fan moderately open, swimming legs swept gently backward in a propulsive stroke; walking legs tucked naturally under the head. This animal must look like the same shrimp shown in the references, not a different species.
Lighting: soft neutral underwater-compatible illumination from the upper right, detailed photographic shell texture, no bright outline or white matte fringe. Preserve translucent appendages as partial alpha where appropriate. No text, no labels, no UI, no watermark. One animal only, one single transparent image, no montage.
```

### Pose 01: final framing edit

```text
Use case: precise-object-edit
Asset type: transparent shrimp sprite pose 01, corrected framing.
The input image is the exact EDIT TARGET and already has genuine transparency. Preserve its true RGBA alpha channel and the exact shrimp identity, shell markings, lighting, photorealistic quality and pose.
Change ONLY framing: fit the COMPLETE prawn including every antenna tip, leg tip and tail tip comfortably inside the 1536x1024 canvas. Shrink the complete animal to approximately 78% of its current size and center it, restoring any cropped antenna tips naturally. Leave a transparent margin of at least 100 pixels on the left and right, and at least 80 pixels on the top and bottom. Nothing may touch the canvas edge. Do not stretch or rotate the animal.
Keep one left-facing shrimp, head left, tail right, long delicate naturally curved antennae complete. The underlying body remains extended with swimming legs angled backward.
The background must remain truly transparent with alpha zero, including between appendages. Do not render a colored matte, any glow, shadows, ground, water, scenery or checkerboard. No new subject, no labels, no text. Single centered transparent PNG.
```

### Pose 02

Based on selected pose 01; keep the head/canvas placement fixed while changing swimming legs and tail fan.

```text
Use case: precise-object-edit
Asset type: transparent PNG shrimp sprite, swimming pose 02.
Input image is the exact EDIT TARGET: pose 01 of the same shrimp. It already contains a real transparent alpha channel. Output another truly transparent RGBA PNG, same 1536x1024 dimensions, no background.
Preserve identical camera angle, canvas, subject scale, body placement, head/eye pixel position, shell markings, color, lighting and detailed photographic texture. Do not translate, rotate, zoom or recenter. Keep all antennae and every appendage entirely inside the existing transparent margins.
Change ONLY a natural swimming stroke: move the swimming legs under the abdomen forward compared with pose 01; gently flex the walking legs a few degrees; bring the tail-fan lobes slightly together while bending the last two abdominal segments inward only a little. The head and large front carapace must be completely still, the change should be apparent in the legs and tail, suitable for a three-pose swim cycle. Allow a very slight graceful antenna tip drift while keeping roots fixed.
The background remains genuine zero-alpha transparency, including gaps between legs. No water, floor, haze, colored matte, checkerboard, shadow, reflection, outline or glow. Keep translucent antennae and legs naturally antialiased into alpha. One left-facing photorealistic tiger prawn only, no labels, no text, no watermark.
```

### Pose 03

Based on poses 02 and 01, with a slightly flexed abdomen and open tail fan.

```text
Use case: precise-object-edit
Asset type: transparent PNG shrimp sprite, swimming pose 03.
Input image 1 is the previous pose 02 and the exact EDIT TARGET. Input image 2 is pose 01 and fixes the original specimen identity and alignment. Produce one truly transparent RGBA PNG of the same 1536x1024 dimensions.
Keep exact canvas, camera angle, scale, head and eye coordinates, front carapace outline, shell stripes, color and light. Do not translate, rotate, zoom or recenter. Keep all antenna tips, every leg and tail tip inside the transparent margins.
Change ONLY the next swimming stroke: bend the last three abdominal segments inward a little more than pose 02, spread the tail fan visibly open, and sweep the swimming legs back outward in the return stroke. Walking legs flex into a distinct but restrained position compared with the prior two poses. Antenna tips sway gently while the roots stay fixed. Preserve physically plausible tiger prawn anatomy and identity. The head and front body stay absolutely aligned with input 1 to avoid jumping in a sprite cycle.
Output genuine zero-alpha transparent background, no matte, no checkerboard drawn into pixels, no water, floor, scenery, shadows, reflections, halo, edge glow, text, labels or watermark. Retain clean antialiased transparent edges and natural translucency in the slender appendages. One left-facing realistic tiger prawn only.
```


## Layered scene: surface-to-bed background

Source: built-in image_gen. Original: opaque 1024 × 1536 `web/docs/assets/swim/ocean-depth.png`. Runtime: `web/frontend/public/images/swim/ocean-depth.webp`, compressed with sharp. Dark negative space remains on the left; the surface, water column and bed form a vertical scene for camera cropping.

Final prompt:

```text
Use case: photorealistic-natural
Asset type: tall environmental background plate for a cinematic scroll-driven aquaculture website. This is a brand-new environment with NO animals, designed for separately composited swimming shrimp.
Primary request: a seamless vertical underwater world, seen from a submerged camera looking diagonally forward; the viewer can pan down this single environment from the bright underside of the water surface to a dark sandy pond bed.
Composition: portrait 2:3 canvas, highest practical resolution. At the top 10-15% show the underside of gently rippling water catching daylight, muted turquoise light and delicate dappled caustics. The middle 55% is open dark teal water with believable subtle suspended sediment and long soft sunlight shafts. The lower 30% reveals a natural dark sandy/gravel aquaculture pond bottom receding into green water, with a few small dark stones along the bottom edge only. The left half should remain especially dark and uncluttered for white webpage copy; visible environment detail on the right side. Deep underwater photography with realistic depth, soft volumetric lighting, fine photographic grain.
Palette: deep ocean teal #071e20, dark green water, subtle pale green daylight. Clean rich depth, not flat fog, not glossy CGI.
Constraints: absolutely no shrimp, fish, animals, coral, seaweed forest, people, tanks, equipment, signs, text, lettering, UI, frames or watermarks. One continuous coherent camera view from surface to floor, NOT a split panel, NOT a collage. Background is fully opaque.
```
