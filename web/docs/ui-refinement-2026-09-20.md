# Dashboard readability refinement

Historical change record, 2026-09-20. The TIDE mark, deep-teal/pale-green palette, routes and analysis flow were retained. Small, low-contrast 9–11px dashboard text was enlarged; model, API and database behavior did not change.

- Common text: 15–16px; supporting text: 14px; chart ticks: 13px; headings: 20px; values: 34–42px.
- Light-mode secondary text changed from `#71817a` to `#4b6259`, increasing contrast on white from approximately 4.10:1 to 6.58:1. Dark mode uses brighter text.
- Five KPI cards share a desktop row, becoming three columns at medium widths, two on mobile and one at very narrow widths. Tables scroll horizontally inside their own containers.
- Mobile retains water/sex distributions; date inputs use 16px and stack vertically on narrow screens.
- Headings use plain descriptions for overview, daily results and recent videos, while retaining demo labels and measurement limitations.

Styles are in [dashboard-readability.css](../frontend/src/app/dashboard-readability.css), scoped to `.app-shell` rather than the landing page. See [the layered scene](swimming-scene.md) for landing motion.
