# Desktop IA patterns for a map-centric EBSD app

Researched 2026-07-21, for the UI ergonomics rework (space poorly used, plots
squished, controls not shown at the right moment).

## Domain reference apps

**MTEX / kikuchipy / orix** — no app chrome. Script-driven; each plot call spawns
a figure, multi-panel composition is manual (`subplot`, `'add2all'`). The toolbox
layer imposes zero IA opinion, so not a model to imitate. Worth stealing:
kikuchipy inherits HyperSpy's **navigator** model — one figure, upper panel a 2D
map with a cursor, lower panel the linked Kikuchi pattern at that pixel.
Sources: mtex-toolbox.github.io/CombinedPlots.html,
kikuchipy.org/tutorials/visualizing_patterns.html

**Oxford AZtecCrystal** — left dockable Project pane (tree + phases table + map
navigation thumbnail), horizontal mode-selector strip above the canvas,
unlimited stackable map layers in the main workspace.
Source: nano.oxinst.com/azteccrystal

**Bruker ESPRIT** — splitter-based SEM chrome: Devices / Project tree / Image
capture / Spectrum-result panes, resizable by dragging splitters, separate
floating option dialogs. Docked panels, not tabs.

**EDAX OIM Analysis** — defining feature is **cross-linked views**: click a point
anywhere and it highlights in every other map, plot and table simultaneously.
Window chrome itself UNVERIFIED (source fetch failed).

**DREAM3D-NX** — the strongest reference found. Three separated concerns:
*Pipeline View* (ordered list of steps = the actual workflow), *Filter List View*
(searchable catalog to drag in), *Filter Parameters View* (params for the
**currently selected** step only). All independently dockable; viewer docked
right by default. Directly relevant to a Phases/OR/Reconstruction tab problem.
Source: dream3d.io/nx_reference_manual/.../PipelineView.html

**ATEX** — no layout detail surfaced. UNVERIFIED.

Cross-tool: commercial vendors converge on tree/project panel (left) + params +
dominant canvas + mode strip. DREAM3D-NX alone separates step-list from
per-step-params.

## General desktop patterns

- **Page/workspace switching** — Resolve's 7 fixed pages, Blender workspace tabs,
  Affinity Personas. The whole toolset swaps. Best when stages need genuinely
  disjoint tools; **costly when a central object must persist across stages**,
  since a full reconfigure risks losing viewport/zoom state.
- **Collapsible sections in a fixed side column** — Lightroom Develop
  (Basic/Tone Curve/HSL/Detail, each independently collapsible; filmstrip stays
  mounted). Viewer and navigation persist, only right-column content changes.
  Best fit for a map-centric app.
- **Inspector/properties column** — Unity, Figma, Photoshop. Persistent, purely a
  function of current selection; position never changes.
- **Contextual controls at the cursor** — Fusion 360's right-click radial menu.
- **VS Code activity bar** — pure navigation strip selecting *which* container
  populates the side panel; guidelines forbid it launching content directly.

## The three specific problems

**(a) Small diagnostic plots.** napari (Qt, closest analog) ships
histogram/profile plots as `add_dock_widget` panels beside the canvas.
Photoshop's histogram panel is dockable and collapses compact/expanded. ImageJ's
floating-MDI model is the **legacy anti-pattern** — breaks on tiling WMs and
multi-monitor (imagej/imagej#32). Precedent converges on **dockable, collapsible
side panel**; not a floating window, not buried in a tab or page.

**(b) Contextual controls without felt "jumping".** No dedicated literature
beyond Nielsen's progressive disclosure (defer advanced controls behind an
explicit request). Affinity's document-state-gated persona — a persona appears
only when relevant — is the closest concrete precedent.

**(c) Overlay-layer control.** Two families: web-map corner-floating widgets
(Leaflet/Mapbox layers control — fine for 2-4 toggles, no reorder) vs the
desktop-pro **docked layers panel** (QGIS/Photoshop/Figma: visibility checkbox +
drag reorder + right-click opacity/properties, scales to many layers). For an
EBSD map with boundaries, IPF, packet/block/variant colouring and quality maps,
the **docked layers-list** is the right family — layer count and Z-order matter.

## Qt-specific

- Qt Creator devs explicitly avoided `QDockWidget` for most panels ("adds too
  much UI clutter"). KDAB built KDDockWidgets because stock QDockWidget "mixes
  GUI code with logic/state in a spaghetti manner" with combinatorial
  per-platform bugs. Source: kdab.com/introducing-kddockwidgets
- ParaView's own 2010 usability review flagged its dockable Object Inspector's
  Apply/Reset placement and mode-switching disruption as **documented usability
  defects**. Source: paraview.org/ParaView_Usability_Improvements
- MathWorks' own blog calls MATLAB docking's state-persistence failure and its
  being blocked in compiled apps "regrettable, unnecessary, self-defeating".
- **Spatial memory is the load-bearing argument**: NN Group plus the ACM
  Foundations & Trends survey "Supporting and Exploiting Spatial Memory in User
  Interfaces" find that rearranging UI breaks spatial memory and automaticity,
  and adaptive/rearranging interfaces "have not worked well". This is a genuine
  argument for **constraining, not maximizing, dockability** in a repeated-use
  analysis tool.
- `QMainWindow::saveState/restoreState` works but is fragile: version must match,
  every dock and toolbar needs a unique `objectName` or restore silently fails,
  and applying a stylesheet before restore causes sizing bugs.
- `QStackedWidget` (bare, no built-in tab bar) + a custom icon strip is the
  direct Qt implementation of a Resolve-style page switcher — distinct from
  `QTabWidget`, which bundles its own tab bar.

## Recommendation for this app

Keep the **map as the one constant canvas**, never rebuilt on navigation.
Replace the flat Phases/OR/Reconstruction/Stats tab row with DREAM3D-NX's split:
a left ordered **step list** (Phases → OR → Reconstruction — the real pipeline,
small, always visible) separate from a **params panel for the selected step
only**, both narrow, never fighting the map for space.

Diagnostic plots (misorientation histogram, KS spectrum, pole figure) become
**dockable, collapsible panels** toggled from a small icon row — not squished
inline in a params panel, not buried behind a page switch.

Overlay layers get a **QGIS/Photoshop-style docked layer list** (checkbox +
opacity + reorder), not a corner legend.

On dockability: allow *some* panels (diagnostic plots, the layer list) to float
and dock freely, but keep the **step-list ↔ params ↔ map skeleton fixed**. Per
the spatial-memory literature and the Qt Creator/KDAB criticism, "dockable
everything" for a single-document, repeated-daily-use tool is the documented
usability trap, not a virtue to maximize.

Use `QStackedWidget` + a slim icon strip **only** if genuinely disjoint stages
appear (raw import vs reconstruction review); otherwise the collapsible-panel
model alone solves "space poorly used / plots squished" without page-switch
overhead.
