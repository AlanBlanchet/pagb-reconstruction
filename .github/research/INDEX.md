# Research store index

One line per topic file. Check here before dispatching any external lookup — a
question already answered below is returned with its stored provenance and date,
not re-researched.

- [Desktop IA patterns for a map-centric EBSD app](ebsd-desktop-ia-patterns.md)
  — 2026-07-21. How MTEX / AZtecCrystal / ESPRIT / OIM / DREAM3D-NX and
  Lightroom / Resolve / VS Code divide screen space; where small diagnostic plots
  belong; overlay-layer control patterns; Qt dockability as a documented
  usability trap (spatial-memory literature, Qt Creator + KDAB + ParaView).
- [Rust ecosystem for EBSD migration](rust-ecosystem-ebsd-migration.md)
  — crate survey for moving compute kernels to Rust.
- [GitHub issue reporting: attach log file from desktop app](github-issue-reporting.md) — 2026-07-21. No URL-param file attach (confirmed); .log/.zip/.gz accepted via drag-drop (25MB cap, CDN upload only, expanded 2025-08-14); anonymous gist removed 2018; issue API needs auth + issues:write/public_repo scope, 65536-char body cap; OAuth/GitHub-App device flow needs client_id only (no secret, no server) — safe to embed, standard for native/CLI apps; no prior-art combining device-flow-auth + auto-attach + no-server found, recommend inline-log-in-body or manual drag-drop over building full device-flow auth unless friction is measured.
