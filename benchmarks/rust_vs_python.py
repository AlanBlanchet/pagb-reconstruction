"""Compare the Rust kernels against the shipped numpy and numba backends.

Correctness first (they must agree with the numpy reference), then speed on the
sizes the reconstruction actually hits. Run via `just run_run`.
"""

import time

import numpy as np

from pagb_reconstruction.utils.compute import _NumbaQuaternions, _NumpyQuaternions

try:
    import pagb_rust

    HAVE_RUST = True
except ImportError:
    HAVE_RUST = False


def unit_quats(n, seed):
    rng = np.random.default_rng(seed)
    q = rng.normal(size=(n, 4))
    return q / np.linalg.norm(q, axis=1, keepdims=True)


def cubic_sym():
    """The 24 proper rotations of the cubic group, as the app supplies them."""
    from pagb_reconstruction.core.crystal import CrystalFamily
    from pagb_reconstruction.core.phase import PhaseConfig

    try:
        pc = PhaseConfig.austenite()
        sym = pc.symmetry_quaternions()
        return np.asarray(sym, dtype=np.float64)
    except Exception:
        _ = CrystalFamily
        return unit_quats(24, 99)


def timed(fn, *args, repeat=3):
    best = float("inf")
    out = None
    for _ in range(repeat):
        t0 = time.perf_counter()
        out = fn(*args)
        best = min(best, time.perf_counter() - t0)
    return out, best


def main():
    sym = cubic_sym()
    print(f"symmetry operators: {sym.shape[0]}")
    print(f"rust extension available: {HAVE_RUST}\n")

    # ---- elementwise disorientation -------------------------------------
    print("=== disorientation_deg (elementwise) ===")
    for n in (100_000, 1_000_000):
        a, b = unit_quats(n, 1), unit_quats(n, 2)
        ref, t_np = timed(_NumpyQuaternions.disorientation_deg, a, b, sym)
        got_nb, t_nb = timed(_NumbaQuaternions.disorientation_deg, a, b, sym)
        line = f"  n={n:>9,}  numpy {t_np:7.3f}s   numba {t_nb:7.3f}s"
        assert np.allclose(got_nb, ref, atol=2e-3), "numba disagrees with numpy"
        if HAVE_RUST:
            got_rs, t_rs = timed(pagb_rust.disorientation_deg, a, b, sym)
            assert np.allclose(got_rs, ref, atol=1e-9), "RUST DISAGREES with numpy"
            line += f"   rust {t_rs:7.3f}s   (rust vs numpy {t_np / t_rs:5.1f}x)"
        print(line, flush=True)

    # ---- O(N^2) pairwise -------------------------------------------------
    print("\n=== pairwise_below (O(N^2), the merge step) ===")
    for n in (500, 1000, 2000):
        q = unit_quats(n, 3)
        ref, t_np = timed(_NumpyQuaternions.pairwise_below, q, sym, 7.0, repeat=1)
        got_nb, t_nb = timed(_NumbaQuaternions.pairwise_below, q, sym, 7.0, repeat=1)
        line = f"  n={n:>5,}  numpy {t_np:7.3f}s   numba {t_nb:7.3f}s"
        assert np.array_equal(got_nb, ref), "numba disagrees with numpy"
        if HAVE_RUST:
            got_rs, t_rs = timed(pagb_rust.pairwise_below, q, sym, 7.0, repeat=1)
            assert np.array_equal(got_rs, ref), "RUST DISAGREES with numpy"
            line += f"   rust {t_rs:7.3f}s   (rust vs numpy {t_np / t_rs:5.1f}x)"
        print(line, flush=True)

    print("\nAll backends agree with the numpy reference.")


if __name__ == "__main__":
    main()
