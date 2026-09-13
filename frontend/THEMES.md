# Portfolio themes

Warm is the saved original appearance from commit 5a45218b7969d5adc03204534c0146549a416307. The original colors remain as CSS variable fallbacks in index.css, portfolio-refinement.css and activity-focus.css. Warm intentionally does not override those tokens, so selecting it restores the original palette, including the four-level activity graphs.

Midnight and Forest define shared RGB color roles in src/themes.css. Keep activity heatmap levels readable on their dark cards. Mask colors, illustrations and theme preview swatches are not recolored.

The home-page sun button uses a native popover and native radio inputs. Escape and clicking outside dismiss it; arrow keys switch the focused radio selection. The versioned localStorage key is portfolio:theme:v1. Invalid or unavailable storage falls back to Warm, and failed writes still apply the selected theme for the current visit. The small head script applies a saved theme before rendering; keep its accepted IDs aligned with src/lib/themes.ts.
