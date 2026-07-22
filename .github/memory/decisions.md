# User-pronounced decisions — pagb-reconstruction

One line per decision the user pronounced. A recorded decision is a FROZEN axis; never reopen without the user.

- 2026-07-17 — **Styling language: SCSS** (compiled to Qt QSS via `qtsass` at runtime). User asked "Can we style in css or a better styling lang (scss)?" → yes, adopt SCSS as the single styling source.
- 2026-07-17 — **Kill the left-border-colour trick.** User: "I don't like that we overuse the left border color trick. I don't even think it's beautiful." Elevation/grouping must come from surface tone + spacing, NOT coloured left stripes or accent-coloured group headers.
- 2026-07-17 — **Real vector icon set, not Qt standard pixmaps / emoji.** User dislikes current styles/icons, wants to innovate. Adopt `qtawesome` (Phosphor / Material Design / Codicons). No more SP\_\* mismatches (zoom=arrows, fit=titlebar glyph) or emoji glyphs.
- 2026-07-17 — **NO "motion" MCP.** This is a PySide6/Qt desktop app; motion.dev is web/React. Animation uses Qt-native (QPropertyAnimation / easing curves). Confirmed with user's question.
- 2026-07-17 — **Design mandate: generic code, maximal ergonomics** (placements, scrolls), accessible + smart + beautiful. Features inspired by other EBSD software (MTEX/AZtec/OIM) but goal = more accessible/beautiful, not clone.
- 2026-07-22 — **"Precision instrument" direction REMOVED by the user** (he deleted the line himself). New mandate, his words: "we can get both the functionalities AND something good" — workflow ergonomics AND a beautiful look, together.
- 2026-07-22 — **DREAM3D-NX is NOT a visual reference.** User: "I saw that software and styles look horrible to be honest." Its INTERACTION SKELETON (ordered workflow steps, params for the selected step, result view permanently central) may inspire structure; its LOOK must not. Visual identity stays ours: SCSS themes, Phosphor icons, flat surfaces. No 3D features implied or planned — "3D" is just that product's name.
