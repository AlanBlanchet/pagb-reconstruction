import numpy as np
from orix.quaternion import Orientation
from pydantic import ConfigDict

from pagb_reconstruction.core.base import Displayable
from pagb_reconstruction.core.orientation_relationship import OrientationRelationship


class VariantAnalyzer(Displayable):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    or_relationship: OrientationRelationship
    variant_ids: np.ndarray
    parent_orientations: np.ndarray
    child_orientations: np.ndarray

    @property
    def n_variants(self) -> int:
        return len(self.or_relationship.variant_quaternions())

    def packet_ids(self) -> np.ndarray:
        n_variants = self.n_variants
        variants_per_packet = max(n_variants // 4, 1)
        return self.variant_ids // variants_per_packet

    def bain_group_ids(self) -> np.ndarray:
        return self.variant_ids % 3

    def variant_frequency(self) -> dict[int, int]:
        unique, counts = np.unique(self.variant_ids, return_counts=True)
        return dict(zip(unique.tolist(), counts.tolist()))

    def variant_deviation_angles(self) -> np.ndarray:
        variants = self.or_relationship.variant_quaternions()
        n_pixels = len(self.child_orientations)
        deviations = np.zeros(n_pixels)

        for i in range(n_pixels):
            vid = self.variant_ids[i]
            if vid < 0 or vid >= len(variants):
                deviations[i] = np.nan
                continue

            parent_ori = Orientation(self.parent_orientations[i].reshape(1, 4))
            v_ori = Orientation(variants[vid].reshape(1, 4))
            predicted = parent_ori * v_ori
            child_ori = Orientation(self.child_orientations[i].reshape(1, 4))
            mori = (~predicted) * child_ori
            deviations[i] = float(np.abs(mori.angle.data[0])) * 180.0 / np.pi

        return deviations
