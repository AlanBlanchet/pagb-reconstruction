from typing import ClassVar

from pagb_reconstruction.io.base import EBSDLoader, register_loader


class HDF5Loader(EBSDLoader):
    supported_extensions: ClassVar[list[str]] = [".h5", ".hdf5", ".h5ebsd"]


register_loader(HDF5Loader)
