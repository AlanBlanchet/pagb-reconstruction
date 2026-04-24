import shutil
import tempfile
from pathlib import Path
from typing import ClassVar

from orix.crystal_map import CrystalMap
from orix.io import load as orix_load, save as orix_save
from pydantic import BaseModel

from pagb_reconstruction.core.crystal import CrystalFamily, LatticeParams
from pagb_reconstruction.core.ebsd_map import EBSDMap
from pagb_reconstruction.core.phase import PhaseConfig


class EBSDLoader(BaseModel):
    supported_extensions: ClassVar[list[str]]

    def load(self, path: Path, detected_ext: str | None = None) -> EBSDMap:
        load_path = path
        tmp_dir = None
        try:
            if detected_ext and path.suffix.lower() != detected_ext:
                tmp_dir = tempfile.mkdtemp()
                tmp = Path(tmp_dir) / (path.stem + detected_ext)
                tmp.symlink_to(path.resolve())
                load_path = tmp
            xmap = orix_load(str(load_path))
        finally:
            if tmp_dir is not None:
                shutil.rmtree(tmp_dir)
        phases = extract_phases(xmap)
        return EBSDMap(crystal_map=xmap, phases=phases)

    def save(self, ebsd_map: EBSDMap, path: Path) -> None:
        orix_save(str(path), ebsd_map.crystal_map)


_LOADERS: dict[str, type[EBSDLoader]] = {}


def register_loader(loader_cls: type[EBSDLoader]):
    for ext in loader_cls.supported_extensions:
        _LOADERS[ext] = loader_cls


def load_ebsd(path: str | Path) -> EBSDMap:
    path = Path(path)
    suffix = path.suffix.lower()

    loader_cls = _LOADERS.get(suffix)
    if loader_cls is None:
        detected = _detect_format(path)
        loader_cls = _LOADERS.get(detected)
        detected_ext = detected
    else:
        detected_ext = None
    if loader_cls is None:
        raise ValueError(
            f"Unsupported file format: {suffix}. Supported: {list(_LOADERS.keys())}"
        )

    loader = loader_cls()
    return loader.load(path, detected_ext=detected_ext)


def _detect_format(path: Path) -> str:
    try:
        with open(path, "rb") as f:
            head = f.read(256).decode("utf-8", errors="ignore")
    except OSError:
        return ""
    if head.startswith("Channel Text File"):
        return ".ctf"
    if "# TEM_PIXperUM" in head or "# x-star" in head:
        return ".ang"
    magic = head[:8].encode()
    if magic[:4] == b"\x89HDF" or magic[:8] == b"\x89HDF\r\n\x1a\n":
        return ".h5"
    return ""


def extract_phases(xmap: CrystalMap) -> list[PhaseConfig]:
    phases = []
    phase_list = xmap.phases_in_data
    for phase_id in phase_list.ids:
        if phase_id < 0:
            continue
        phase = phase_list[phase_id]
        pg = str(phase.point_group) if phase.point_group else "m-3m"
        lattice = (
            getattr(phase, "structure", None)
            and phase.structure
            and getattr(phase.structure, "lattice", None)
        )
        lp = _lattice_from_structure(lattice) if lattice else _default_lattice(pg)
        family = _family_from_point_group(pg)
        phases.append(
            PhaseConfig(
                name=phase.name or f"Phase {phase_id}",
                family=family,
                point_group=pg,
                lattice=lp,
                color=getattr(phase, "color", None) or "#808080",
            )
        )
    return phases


def _lattice_from_structure(lattice) -> LatticeParams:
    return LatticeParams(
        a=lattice.a,
        b=lattice.b,
        c=lattice.c,
        alpha=lattice.alpha,
        beta=lattice.beta,
        gamma=lattice.gamma,
    )


def _default_lattice(point_group: str) -> LatticeParams:
    if "m-3m" in point_group or "43" in point_group:
        return LatticeParams.cubic(2.87)
    return LatticeParams(a=3.0, b=3.0, c=3.0)


_POINT_GROUP_FAMILIES: dict[str, CrystalFamily] = {
    "m-3m": CrystalFamily.CUBIC,
    "432": CrystalFamily.CUBIC,
    "-43m": CrystalFamily.CUBIC,
    "m-3": CrystalFamily.CUBIC,
    "23": CrystalFamily.CUBIC,
    "6/mmm": CrystalFamily.HEXAGONAL,
    "622": CrystalFamily.HEXAGONAL,
    "-6m2": CrystalFamily.HEXAGONAL,
    "6mm": CrystalFamily.HEXAGONAL,
    "6/m": CrystalFamily.HEXAGONAL,
    "-6": CrystalFamily.HEXAGONAL,
    "6": CrystalFamily.HEXAGONAL,
    "4/mmm": CrystalFamily.TETRAGONAL,
    "422": CrystalFamily.TETRAGONAL,
    "-42m": CrystalFamily.TETRAGONAL,
    "4mm": CrystalFamily.TETRAGONAL,
    "4/m": CrystalFamily.TETRAGONAL,
    "-4": CrystalFamily.TETRAGONAL,
    "4": CrystalFamily.TETRAGONAL,
    "-3m": CrystalFamily.TRIGONAL,
    "32": CrystalFamily.TRIGONAL,
    "3m": CrystalFamily.TRIGONAL,
    "-3": CrystalFamily.TRIGONAL,
    "3": CrystalFamily.TRIGONAL,
    "mmm": CrystalFamily.ORTHORHOMBIC,
    "222": CrystalFamily.ORTHORHOMBIC,
    "mm2": CrystalFamily.ORTHORHOMBIC,
    "2/m": CrystalFamily.MONOCLINIC,
    "2": CrystalFamily.MONOCLINIC,
    "m": CrystalFamily.MONOCLINIC,
    "-1": CrystalFamily.TRICLINIC,
    "1": CrystalFamily.TRICLINIC,
}


def _family_from_point_group(pg: str) -> CrystalFamily:
    return _POINT_GROUP_FAMILIES.get(pg, CrystalFamily.CUBIC)
