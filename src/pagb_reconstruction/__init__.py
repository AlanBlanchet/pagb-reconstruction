"""PAGB Reconstruction — Prior Austenite Grain Boundary reconstruction from EBSD data."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("pagb-reconstruction")
except PackageNotFoundError:
    __version__ = "0.0.0-dev"
