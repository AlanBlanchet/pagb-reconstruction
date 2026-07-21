//! Rust implementation of the reconstruction's hot quaternion kernels.
//!
//! Evaluation prototype. It implements the SAME contract as the numpy and numba
//! backends in `utils/compute.py` (`disorientation_deg`, `pairwise_below`), so it
//! can be compared against them for correctness and speed on real data.
//!
//! The interesting one is `pairwise_below`: O(N^2) over parent grains, each element
//! doing a ~24-way symmetry reduction. That is the one place a compiled,
//! thread-parallel implementation could plausibly beat both numpy (which has to
//! materialise an (N, N, 24) intermediate) and the GPU kernel (which is
//! launch/bandwidth-bound here, as measured).

use numpy::ndarray::{Array1, Array2, ArrayView2};
use numpy::{IntoPyArray, PyArray1, PyArray2, PyReadonlyArray2};
use pyo3::prelude::*;
use rayon::prelude::*;

const RAD_TO_DEG: f64 = 180.0 / std::f64::consts::PI;

/// Symmetry-reduced disorientation angle between two unit quaternions, in degrees.
///
/// The smallest angle over the symmetry group corresponds to the LARGEST |w| of
/// `sym * mori`, so the reduction is a max over the group — one `acos` per pair
/// rather than one per symmetry operator.
#[inline(always)]
fn disorientation(q1: &[f64], q2: &[f64], sym: &ArrayView2<f64>) -> f64 {
    // mori = q1 * conj(q2)
    let mw = q1[0] * q2[0] + q1[1] * q2[1] + q1[2] * q2[2] + q1[3] * q2[3];
    let mx = -q1[0] * q2[1] + q1[1] * q2[0] - q1[2] * q2[3] + q1[3] * q2[2];
    let my = -q1[0] * q2[2] + q1[1] * q2[3] + q1[2] * q2[0] - q1[3] * q2[1];
    let mz = -q1[0] * q2[3] - q1[1] * q2[2] + q1[2] * q2[1] + q1[3] * q2[0];

    let mut best = 0.0f64;
    for s in 0..sym.nrows() {
        let w = (sym[[s, 0]] * mw - sym[[s, 1]] * mx - sym[[s, 2]] * my - sym[[s, 3]] * mz).abs();
        if w > best {
            best = w;
        }
    }
    if best > 1.0 {
        best = 1.0;
    }
    2.0 * best.acos() * RAD_TO_DEG
}

/// Element-wise disorientation between two equal-length quaternion arrays.
#[pyfunction]
fn disorientation_deg<'py>(
    py: Python<'py>,
    q1: PyReadonlyArray2<'py, f64>,
    q2: PyReadonlyArray2<'py, f64>,
    sym: PyReadonlyArray2<'py, f64>,
) -> PyResult<Bound<'py, PyArray1<f64>>> {
    let a = q1.as_array();
    let b = q2.as_array();
    let s = sym.as_array();
    let n = a.nrows();

    let mut out = Array1::<f64>::zeros(n);
    py.allow_threads(|| {
        out.as_slice_mut()
            .unwrap()
            .par_iter_mut()
            .enumerate()
            .for_each(|(i, o)| {
                let qa = [a[[i, 0]], a[[i, 1]], a[[i, 2]], a[[i, 3]]];
                let qb = [b[[i, 0]], b[[i, 1]], b[[i, 2]], b[[i, 3]]];
                *o = disorientation(&qa, &qb, &s);
            });
    });
    Ok(out.into_pyarray(py))
}

/// Upper-triangular boolean matrix of pairs closer than `threshold_deg`.
///
/// Rows go to rayon; nothing larger than the output is allocated, so there is no
/// (N, N, 24) intermediate to blow out memory.
#[pyfunction]
fn pairwise_below<'py>(
    py: Python<'py>,
    quats: PyReadonlyArray2<'py, f64>,
    sym: PyReadonlyArray2<'py, f64>,
    threshold_deg: f64,
) -> PyResult<Bound<'py, PyArray2<bool>>> {
    let q = quats.as_array();
    let s = sym.as_array();
    let n = q.nrows();

    let mut out = Array2::<bool>::from_elem((n, n), false);
    py.allow_threads(|| {
        out.as_slice_mut()
            .unwrap()
            .par_chunks_mut(n)
            .enumerate()
            .for_each(|(i, row)| {
                let qi = [q[[i, 0]], q[[i, 1]], q[[i, 2]], q[[i, 3]]];
                for j in (i + 1)..n {
                    let qj = [q[[j, 0]], q[[j, 1]], q[[j, 2]], q[[j, 3]]];
                    row[j] = disorientation(&qi, &qj, &s) < threshold_deg;
                }
            });
    });
    Ok(out.into_pyarray(py))
}

#[pymodule]
fn pagb_rust(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(disorientation_deg, m)?)?;
    m.add_function(wrap_pyfunction!(pairwise_below, m)?)?;
    Ok(())
}

#[cfg(test)]
#[path = "lib_test.rs"]
mod lib_test;
