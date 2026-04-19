from enum import Enum

from pydantic import BaseModel


class CrystalFamily(str, Enum):
    CUBIC = "cubic"
    HEXAGONAL = "hexagonal"
    TETRAGONAL = "tetragonal"
    ORTHORHOMBIC = "orthorhombic"
    MONOCLINIC = "monoclinic"
    TRICLINIC = "triclinic"
    TRIGONAL = "trigonal"


_POINT_GROUP_TO_SPACE_GROUP: dict[str, int] = {
    "m-3m": 225,
    "432": 207,
    "-43m": 215,
    "m-3": 200,
    "23": 195,
    "6/mmm": 191,
    "622": 177,
    "-6m2": 187,
    "6mm": 183,
    "6/m": 175,
    "-6": 174,
    "6": 168,
    "4/mmm": 123,
    "422": 89,
    "-42m": 111,
    "4mm": 99,
    "4/m": 83,
    "-4": 81,
    "4": 75,
    "mmm": 47,
    "222": 16,
    "mm2": 25,
    "2/m": 10,
    "2": 3,
    "m": 6,
    "-1": 2,
    "1": 1,
    "-3m": 166,
    "32": 149,
    "3m": 156,
    "-3": 147,
    "3": 143,
}


class LatticeParams(BaseModel):
    a: float
    b: float
    c: float
    alpha: float = 90.0
    beta: float = 90.0
    gamma: float = 90.0

    @classmethod
    def cubic(cls, a: float):
        return cls(a=a, b=a, c=a)

    @classmethod
    def hexagonal(cls, a: float, c: float):
        return cls(a=a, b=a, c=c, alpha=90, beta=90, gamma=120)
