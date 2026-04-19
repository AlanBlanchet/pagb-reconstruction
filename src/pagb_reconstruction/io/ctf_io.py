from typing import ClassVar

from pagb_reconstruction.io.base import EBSDLoader, register_loader


class CTFLoader(EBSDLoader):
    supported_extensions: ClassVar[list[str]] = [".ctf"]


register_loader(CTFLoader)
