import numpy as np
from orix.quaternion import Orientation, Symmetry
from orix.vector import Vector3d

from pagb_reconstruction.core.base import Displayable


class OrientationData(Displayable):

    quaternions: np.ndarray  # (N, 4) array
    symmetry: Symmetry

    @classmethod
    def from_euler(
        cls,
        phi1: np.ndarray,
        Phi: np.ndarray,
        phi2: np.ndarray,
        symmetry: Symmetry,
        degrees: bool = True,
    ):
        ori = Orientation.from_euler(
            np.column_stack([phi1, Phi, phi2]), symmetry=symmetry, degrees=degrees
        )
        return cls(quaternions=ori.data, symmetry=symmetry)

    @classmethod
    def from_orix(cls, orientations: Orientation):
        return cls(quaternions=orientations.data, symmetry=orientations.symmetry)

    @property
    def orientations(self) -> Orientation:
        return Orientation(self.quaternions, symmetry=self.symmetry)

    def to_euler(self, degrees: bool = True) -> np.ndarray:
        return self.orientations.to_euler(degrees=degrees)

    def misorientation_angle(self, other: "OrientationData") -> np.ndarray:
        mori = (~self.orientations) * other.orientations
        mori_fund = mori.map_into_symmetry_reduced_zone()
        return mori_fund.angle.data * (180.0 / np.pi)

    def ipf_color(self, direction: Vector3d | None = None) -> np.ndarray:
        from pagb_reconstruction.utils.colormap import ipf_colors

        return ipf_colors(self.orientations, direction)
