"""Build a Debian archive with private Python dependencies for the current interpreter."""

import argparse
from email.parser import BytesParser
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
NAME = "fzf-gnat"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    architecture = subprocess.check_output(["dpkg", "--print-architecture"], text=True).strip()
    python = f"python{sys.version_info.major}.{sys.version_info.minor}"
    with tempfile.TemporaryDirectory(prefix=f"{NAME}-") as temp:
        stage = Path(temp) / "package"
        library = stage / "usr/lib" / NAME
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--no-compile", "--target", str(library), str(ROOT)],
            check=True,
        )
        shutil.rmtree(library / "bin", ignore_errors=True)
        metadata = BytesParser().parsebytes(
            next(library.glob("fzf_gnat-*.dist-info/METADATA")).read_bytes()
        )
        version = metadata["Version"]
        binary = stage / "usr/bin" / NAME
        binary.parent.mkdir(parents=True)
        binary.write_text(
            f"#!/usr/bin/{python} -I\n"
            "import sys\n"
            "from pathlib import Path\n"
            f"sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib/{NAME}'))\n"
            "from fzf_gnat.cli import main\n"
            "sys.exit(main())\n"
        )
        binary.chmod(0o755)
        documentation = stage / "usr/share/doc" / NAME
        documentation.mkdir(parents=True)
        shutil.copyfile(ROOT / "README.md", documentation / "README.md")
        control = stage / "DEBIAN/control"
        control.parent.mkdir()
        control.write_text(
            f"Package: {NAME}\n"
            f"Version: {version}\n"
            "Section: devel\n"
            "Priority: optional\n"
            f"Architecture: {architecture}\n"
            "Maintainer: Zakaria Fadli <zakaria1193@gmail.com>\n"
            f"Depends: {python}, libc6, fzf\n"
            "Recommends: bat\n"
            "Description: Fuzzy search Ada sources by unit name and declaration\n"
            " Search GNAT source trees by unit name, shortened file name, or declaration.\n"
            " Python parser dependencies are included in a private directory.\n"
        )
        archive = args.output.resolve() / f"{NAME}_{version}_{architecture}.deb"
        subprocess.run(["dpkg-deb", "--root-owner-group", "--build", str(stage), str(archive)], check=True)
        print(archive)


if __name__ == "__main__":
    main()
