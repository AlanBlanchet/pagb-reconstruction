import configparser
from pathlib import Path
from typing import ClassVar

import numpy as np
from orix.crystal_map import CrystalMap, Phase, PhaseList
from orix.quaternion import Rotation

from pagb_reconstruction.core.ebsd_map import EBSDMap
from pagb_reconstruction.io.base import EBSDLoader, extract_phases, register_loader

# Oxford/HKL Channel5 Laue-group id -> point group symbol.
_LAUE_POINT_GROUP = {
    "1": "-1", "2": "2/m", "3": "mmm", "4": "4/m", "5": "4/mmm",
    "6": "-3", "7": "-3m", "8": "6/m", "9": "6/mmm", "10": "m-3", "11": "m-3m",
}


class CRCLoader(EBSDLoader):
    """Oxford Instruments / HKL Channel5 binary EBSD (.crc + .cpr header).

    orix cannot read this format, yet the canonical martensite / prior-austenite
    datasets (MTEX, Nyyssonen) ship as .crc. Each .crc record starts with a phase
    byte and three Bunge Euler floats (the .cpr [Fields] always lead with phase +
    Euler1-3); the rest of the fixed-size record (MAD/BC/BS/bands/...) is skipped.
    """

    supported_extensions: ClassVar[list[str]] = [".crc"]

    def load(self, path: Path, detected_ext: str | None = None) -> EBSDMap:
        cpr_path = path.with_suffix(".cpr")
        if not cpr_path.exists():
            raise FileNotFoundError(f"Missing Channel5 header {cpr_path.name} next to {path.name}")
        cpr = configparser.ConfigParser(strict=False)
        cpr.optionxform = str.lower
        cpr.read(cpr_path)

        job = cpr["Job"]
        n_cols = int(job["xcells"])
        n_rows = int(job["ycells"])
        dx = float(job.get("griddistx", job.get("griddist", "1")))
        dy = float(job.get("griddisty", job.get("griddist", "1")))
        n_points = n_cols * n_rows

        raw = np.fromfile(path, dtype=np.uint8)
        record_size = raw.size // n_points
        if record_size < 13:
            raise ValueError(f"Unexpected .crc record size {record_size} for {n_points} points")
        rec = np.dtype(
            [("phase", "u1"), ("euler", "<f4", (3,)), ("rest", "V", record_size - 13)]
        )
        data = np.frombuffer(raw[: n_points * record_size].tobytes(), dtype=rec)

        rotations = Rotation.from_euler(data["euler"].astype(np.float64), degrees=False)
        phase_id = data["phase"].astype(np.int32)
        phase_id[phase_id == 0] = -1  # 0 = unindexed in Channel5

        cols, rows = np.meshgrid(np.arange(n_cols), np.arange(n_rows))
        xmap = CrystalMap(
            rotations=rotations,
            phase_id=phase_id,
            x=(cols.ravel() * dx).astype(np.float64),
            y=(rows.ravel() * dy).astype(np.float64),
            phase_list=self._phase_list(cpr),
        )
        return EBSDMap(crystal_map=xmap, phases=extract_phases(xmap))

    @staticmethod
    def _phase_list(cpr: configparser.ConfigParser) -> PhaseList:
        phases = {}
        idx = 1
        while cpr.has_section(f"Phase{idx}"):
            sec = cpr[f"Phase{idx}"]
            point_group = _LAUE_POINT_GROUP.get(sec.get("lauegroup", "11"), "m-3m")
            phases[idx] = Phase(
                name=sec.get("structurename", f"Phase {idx}"),
                point_group=point_group,
            )
            idx += 1
        return PhaseList(phases) if phases else PhaseList(Phase(name="phase", point_group="m-3m"))


register_loader(CRCLoader)
