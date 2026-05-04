from pagb_reconstruction.core.base import CrystallographicEntity
from pagb_reconstruction.core.crystal import CrystalFamily, LatticeParams


class PhaseConfig(CrystallographicEntity):
    name: str
    color: str = "#808080"
    phase_id: int = 0
    space_group: int | None = None

    @classmethod
    def austenite(cls):
        return cls(
            name="Austenite",
            family=CrystalFamily.CUBIC,
            point_group="m-3m",
            lattice=LatticeParams.cubic(3.60),
            color="#FF6B6B",
            space_group=225,
        )

    @classmethod
    def ferrite(cls):
        return cls(
            name="Ferrite",
            family=CrystalFamily.CUBIC,
            point_group="m-3m",
            lattice=LatticeParams.cubic(2.87),
            color="#4ECDC4",
            space_group=229,
        )

    @classmethod
    def martensite(cls):
        return cls(
            name="Martensite",
            family=CrystalFamily.CUBIC,
            point_group="m-3m",
            lattice=LatticeParams.cubic(2.87),
            color="#45B7D1",
            space_group=229,
        )
