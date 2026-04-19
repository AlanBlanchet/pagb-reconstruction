"""Download sample EBSD data for testing."""

from pathlib import Path

from orix.data import sdss_ferrite_austenite
from orix.io import save


def main():
    data_dir = Path("data")
    data_dir.mkdir(exist_ok=True)

    print("Downloading super duplex stainless steel EBSD data...")
    xmap = sdss_ferrite_austenite(allow_download=True)
    print(f"Shape: {xmap.shape}, Size: {xmap.size} points")
    print(f"Phases: {xmap.phases_in_data}")

    out_path = data_dir / "sdss_ferrite_austenite.ang"
    save(out_path, xmap)
    print(f"Saved to {out_path}")


if __name__ == "__main__":
    main()
