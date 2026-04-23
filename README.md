# PAGB Reconstruction

Prior Austenite Grain Boundary reconstruction from EBSD data. PySide6 desktop application with orix-backed crystallographic engine.

## Features

- **EBSD file loading** — ANG, CTF, HDF5 formats via extensible loader registry
- **Orientation relationships** — KS, NW, GT, Pitsch, Bain presets with OR refinement
- **Reconstruction algorithms** — Variant graph (recommended) and grain graph with Markov clustering
- **15+ visualization modes** — IPF maps, KAM, GOS, GROD, Schmid factor, CSL boundaries, parent IPF, variant/packet/Bain maps
- **Grain metrics** — intercept and area methods, ASTM grain size number
- **Interactive viewer** — pixel info on hover/click, crosshairs, histogram equalization, export to PNG/CSV/NPY
- **Dark theme** — Catppuccin-inspired styling with qdarktheme

## Download

Pre-built binaries for Linux and Windows are available on the [Releases](https://github.com/AlanBlanchet/pagb-reconstruction/releases) page.

## Install from Source

```bash
uv sync
uv run pagb
```

## Development

Requires [just](https://github.com/casey/just) (optional) and [uv](https://github.com/astral-sh/uv).

```bash
just install    # uv sync
just test       # uv run pytest tests/
just run        # uv run pagb
```

Or without just:

```bash
uv sync
uv run pytest tests/ -v
uv run pagb
```

## Building

Build a standalone executable with PyInstaller:

```bash
just build
```

Build an AppImage (Linux):

```bash
bash packaging/build-appimage.sh
```

## Release Process

Push a version tag to trigger the release workflow:

```bash
git tag v0.1.0
git push --tags
```

This builds Linux and Windows artifacts and creates a GitHub Release.

## Architecture

```
src/pagb_reconstruction/
├── core/       # Pydantic data models, grain detection, graph clustering, reconstruction engine
├── io/         # File loaders (ANG, CTF, HDF5) via registry pattern
├── ui/         # PySide6 + pyqtgraph desktop application
└── utils/      # Numba-accelerated math (QuaternionOps, MisorientationOps), IPF coloring
```

**Key classes:** `EBSDMap` (spatial map with 15+ map properties), `ReconstructionEngine` (grain graph / variant graph pipeline), `OrientationRelationship` (OR presets via classmethod registry), `Grain` (spatial region with crystallographic data).

## License

MIT
