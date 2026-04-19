from typing import ClassVar

from pagb_reconstruction.io.base import EBSDLoader, register_loader


class ANGLoader(EBSDLoader):
    supported_extensions: ClassVar[list[str]] = [".ang"]


register_loader(ANGLoader)
