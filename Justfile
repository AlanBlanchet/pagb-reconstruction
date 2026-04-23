set windows-shell := ["powershell", "-NoLogo", "-Command"]

default: run

install:
    uv sync

run *ARGS:
    uv run pagb {{ARGS}}

test *ARGS:
    uv run pytest tests/ {{ARGS}}

build:
    uv run pyinstaller pagb.spec --noconfirm

clean:
    rm -rf dist/ build/ *.AppImage
