set windows-shell := ["powershell", "-NoLogo", "-Command"]

default: run

install:
    uv sync

run *ARGS:
    uv run pagb {{ARGS}}

test *ARGS:
    uv run pytest tests/ {{ARGS}}

build:
    uv run pyinstaller pagb.spec --noconfirm

clean:
    rm -rf dist/ build/ *.AppImage rust_test/target/ .sweep-log/

# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------

# Verify everything: Rust kernels, Python suite, backend agreement, live app.
verify: rust-test rust-build bench test sweep
    @echo ""
    @echo "verify complete - Rust kernels, Python suite, backend agreement and the app sweep all passed."

# Rust unit tests (pure Rust, no Python involved).
rust-test:
    @echo "-- Rust unit tests --"
    cd rust_test && cargo test --release

# Compile the Rust extension into the venv as an importable module.
rust-build:
    @echo "-- building Rust extension --"
    cd rust_test && ../.venv/bin/maturin develop --release

# Rust vs numpy vs numba: asserts they AGREE, then reports speed.
bench:
    @echo "-- backend comparison --"
    uv run python benchmarks/rust_vs_python.py

# Drive the assembled app through every interaction on the real test map.
sweep:
    @echo "-- end-to-end interaction sweep --"
    uv run python scripts/interaction_sweep.py .sweep-log

# Which compute backend and device are live.
gpu-check:
    uv run pagb --gpu-check

# Reconstruct the bundled test map and print quality metrics.
reconstruct:
    uv run python -c "from pagb_reconstruction.io.base import load_ebsd; from pagb_reconstruction.core.reconstruction import ReconstructionConfig, ReconstructionEngine; from pagb_reconstruction.core.fit_metrics import reconstruction_quality; m = load_ebsd('data/martensite_roomtemp.ctf'); r = ReconstructionEngine(m, ReconstructionConfig()).run(); q = reconstruction_quality(r, m.step_size); print(f'parents={q.n_parents} ECD={q.area_weighted_ecd_um:.1f}um recon={q.pct_reconstructed:.1f}% fit={q.mean_fit_deg:.2f}deg')"
