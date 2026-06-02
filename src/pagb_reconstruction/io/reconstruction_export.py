from pathlib import Path
from typing import ClassVar

import numpy as np
from orix.quaternion import Rotation

from pagb_reconstruction.core.ebsd_map import EBSDMap
from pagb_reconstruction.core.reconstruction import ReconstructionResult


class ReconstructionExporter:
    """Writes a reconstruction result to disk, dispatching on file suffix.

    Mirrors the loader registry in io/base.py: a single entry point (save)
    routes the path to the writer for its extension.
    """

    _WRITERS: ClassVar[dict[str, str]] = {".ang": "_to_ang", ".npz": "_to_npz"}

    @classmethod
    def supported_extensions(cls) -> list[str]:
        return sorted(cls._WRITERS)

    @classmethod
    def save(cls, path: Path, ebsd_map: EBSDMap, result: ReconstructionResult) -> None:
        writer = cls._WRITERS.get(path.suffix.lower())
        if writer is None:
            raise ValueError(
                f"Unsupported export format: {path.suffix}. "
                f"Supported: {cls.supported_extensions()}"
            )
        getattr(cls, writer)(path, ebsd_map, result)

    @staticmethod
    def _coords(ebsd_map: EBSDMap) -> tuple[np.ndarray, np.ndarray]:
        cm = ebsd_map.crystal_map
        n = cm.size
        xs = cm.x if cm.x is not None else np.zeros(n)
        ys = cm.y if cm.y is not None else np.zeros(n)
        return np.asarray(xs), np.asarray(ys)

    @staticmethod
    def _to_ang(path: Path, ebsd_map: EBSDMap, result: ReconstructionResult) -> None:
        euler = Rotation(result.parent_orientations.reshape(-1, 4)).to_euler()
        xs, ys = ReconstructionExporter._coords(ebsd_map)
        step_y, step_x = ebsd_map.step_size
        rows, cols = ebsd_map.shape
        phase_ids = ebsd_map.phase_ids
        fit = result.fit_angles
        parent_ids = result.parent_grain_ids
        variant_ids = result.variant_ids
        n = ebsd_map.crystal_map.size

        with open(path, "w") as f:
            f.write("# HEADER: Start\n")
            f.write("# TEM_PIXperUM          1.000000\n")
            f.write("# x-star                0.000000\n")
            f.write("# y-star                0.000000\n")
            f.write("# z-star                0.000000\n")
            f.write("# WorkingDistance       0.000000\n#\n")
            for i, phase in enumerate(ebsd_map.phases, start=1):
                lp = phase.lattice
                f.write(f"# Phase {i}\n")
                f.write(f"# MaterialName    {phase.name}\n")
                f.write("# Formula\n")
                f.write("# Info\n")
                f.write(f"# Symmetry              {phase.point_group}\n")
                f.write(
                    f"# LatticeConstants      {lp.a:.3f} {lp.b:.3f} {lp.c:.3f} "
                    f"{lp.alpha:.3f} {lp.beta:.3f} {lp.gamma:.3f}\n"
                )
                f.write("# NumberFamilies        0\n#\n")
            f.write("# GRID: SqrGrid\n")
            f.write(f"# XSTEP: {step_x:.6f}\n")
            f.write(f"# YSTEP: {step_y:.6f}\n")
            f.write(f"# NCOLS_ODD: {cols}\n")
            f.write(f"# NCOLS_EVEN: {cols}\n")
            f.write(f"# NROWS: {rows}\n#\n")
            f.write("# OPERATOR: pagb-reconstruction\n")
            f.write("# SAMPLEID:\n")
            f.write("# SCANID:\n#\n")
            f.write(
                "# COLUMNS: phi1 PHI phi2 x y IQ CI Phase SEM_Signal Fit "
                "ParentID VariantID FitAngle\n"
            )
            f.write("# HEADER: End\n")
            for i in range(n):
                phi1, Phi, phi2 = euler[i]
                f.write(
                    f"{phi1:.5f} {Phi:.5f} {phi2:.5f} "
                    f"{float(xs[i]):.5f} {float(ys[i]):.5f} "
                    f"1.0 1.0 {int(phase_ids[i])} 1 {float(fit[i]):.4f} "
                    f"{int(parent_ids[i])} {int(variant_ids[i])} "
                    f"{float(fit[i]):.4f}\n"
                )

    @staticmethod
    def _to_npz(path: Path, ebsd_map: EBSDMap, result: ReconstructionResult) -> None:
        rows, cols = ebsd_map.shape
        step_y, step_x = ebsd_map.step_size
        xs, ys = ReconstructionExporter._coords(ebsd_map)
        np.savez_compressed(
            path,
            parent_orientations=result.parent_orientations,
            parent_grain_ids=result.parent_grain_ids,
            fit_angles=result.fit_angles,
            variant_ids=result.variant_ids,
            packet_ids=result.packet_ids,
            block_ids=result.block_ids,
            bain_ids=result.bain_ids,
            child_quaternions=ebsd_map.quaternions,
            phase_ids=ebsd_map.phase_ids,
            x=xs,
            y=ys,
            shape=np.array([rows, cols], dtype=np.int32),
            step=np.array([step_y, step_x], dtype=np.float64),
        )
