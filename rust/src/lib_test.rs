//! Correctness tests for the Rust kernels, independent of Python.
//!
//! These assert the mathematical invariants of a symmetry-reduced disorientation.
//! Agreement with the shipped numpy backend is asserted separately from Python
//! (see `benchmarks/rust_vs_python.py`), which is the check that actually matters
//! for a drop-in backend.

use super::*;
use numpy::ndarray::{arr2, Array2};

fn identity_sym() -> Array2<f64> {
    arr2(&[[1.0, 0.0, 0.0, 0.0]])
}

/// 24 proper rotations of the cubic group are what the app passes; for unit tests
/// the identity plus a 90-degree z rotation is enough to exercise the reduction.
fn small_sym() -> Array2<f64> {
    let c = (0.5f64).sqrt();
    arr2(&[[1.0, 0.0, 0.0, 0.0], [c, 0.0, 0.0, c]])
}

#[test]
fn identical_orientations_have_zero_disorientation() {
    let sym = identity_sym();
    let q = [1.0, 0.0, 0.0, 0.0];
    let angle = disorientation(&q, &q, &sym.view());
    assert!(angle.abs() < 1e-9, "expected 0, got {angle}");
}

#[test]
fn known_ninety_degree_rotation() {
    let sym = identity_sym();
    let c = (0.5f64).sqrt();
    let a = [1.0, 0.0, 0.0, 0.0];
    let b = [c, 0.0, 0.0, c]; // 90 deg about z
    let angle = disorientation(&a, &b, &sym.view());
    assert!((angle - 90.0).abs() < 1e-9, "expected 90, got {angle}");
}

#[test]
fn symmetry_reduces_the_angle() {
    // With the 90-deg operator in the group, a 90-deg misorientation reduces to 0.
    let c = (0.5f64).sqrt();
    let a = [1.0, 0.0, 0.0, 0.0];
    let b = [c, 0.0, 0.0, c];
    let full = disorientation(&a, &b, &identity_sym().view());
    let reduced = disorientation(&a, &b, &small_sym().view());
    assert!((full - 90.0).abs() < 1e-9);
    assert!(reduced < 1e-9, "symmetry should reduce this to 0, got {reduced}");
}

#[test]
fn disorientation_is_symmetric_in_its_arguments() {
    let sym = small_sym();
    let a = [0.5, 0.5, 0.5, 0.5];
    let b = [(0.5f64).sqrt(), 0.0, (0.5f64).sqrt(), 0.0];
    let ab = disorientation(&a, &b, &sym.view());
    let ba = disorientation(&b, &a, &sym.view());
    assert!((ab - ba).abs() < 1e-9, "{ab} != {ba}");
}

#[test]
fn angle_stays_within_range_for_random_unit_quaternions() {
    // Deterministic pseudo-random unit quaternions; the angle must always be a
    // real number in [0, 180] — this is what a clamp bug in the acos would break.
    let sym = small_sym();
    let mut seed = 12345u64;
    let mut next = || {
        seed = seed.wrapping_mul(6364136223846793005).wrapping_add(1442695040888963407);
        ((seed >> 11) as f64) / ((1u64 << 53) as f64) - 0.5
    };
    for _ in 0..2000 {
        let mut a = [next(), next(), next(), next()];
        let mut b = [next(), next(), next(), next()];
        for q in [&mut a, &mut b] {
            let n = (q[0] * q[0] + q[1] * q[1] + q[2] * q[2] + q[3] * q[3]).sqrt();
            for v in q.iter_mut() {
                *v /= n;
            }
        }
        let angle = disorientation(&a, &b, &sym.view());
        assert!(angle.is_finite(), "non-finite angle");
        assert!((0.0..=180.0).contains(&angle), "out of range: {angle}");
    }
}
