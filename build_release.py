"""Build the Windows x64 portable distribution from a clean checkout."""
from pathlib import Path
import os
import sys
import shutil
import importlib.metadata as metadata
# Keep unrelated toolchains (e.g. Poppler ICU) out of DLL discovery.
os.environ["PATH"] = os.pathsep.join([str(Path(sys.executable).parent), str(Path(os.environ["SystemRoot"]) / "System32"), os.environ["SystemRoot"]])
import PyInstaller.__main__
root = Path(__file__).resolve().parent
os.chdir(root)
PyInstaller.__main__.run([
    "--noconfirm", "--windowed", "--onedir", "--contents-directory", ".",
    "--name", "SHD-Media-Terminal", "--icon", str(root / "ui/assets/shd-minimal.ico"),
    "--add-data", str(root / "ui") + ":ui", "--add-data", str(root / "LICENSE") + ":.", "--add-data", str(root / "README.md") + ":.",
    "--distpath", str(root / "dist"), "--workpath", str(root / "build"), "--specpath", str(root / "build"), "--exclude-module", "PyQt5", "--exclude-module", "PyQt6",
    "--exclude-module", "PySide2", "app.py",
])

output = root / "dist/SHD-Media-Terminal"
# Use the runtime shipped with Qt rather than Python's older VC runtime.
for name in ("VCRUNTIME140.dll", "VCRUNTIME140_1.dll"):
    source = output / "PySide6" / name
    if source.exists():
        shutil.copy2(source, output / name)
licenses = output / "third-party-licenses"
licenses.mkdir(exist_ok=True)
for name in ("PySide6", "PySide6_Addons", "PySide6_Essentials", "shiboken6", "requests", "urllib3", "certifi", "charset-normalizer", "idna", "beautifulsoup4", "soupsieve", "PySocks", "lxml", "PyInstaller"):
    try:
        dist = metadata.distribution(name)
    except metadata.PackageNotFoundError:
        continue
    for file in dist.files or []:
        if ".dist-info/" in str(file) and any(word in str(file).lower() for word in ("license", "copying", "notice")):
            source = Path(dist.locate_file(file))
            target = licenses / name / str(file).split(".dist-info/", 1)[1]
            target.parent.mkdir(parents=True, exist_ok=True)
            if source.is_file():
                shutil.copy2(source, target)
shutil.copy2(root / "THIRD_PARTY.md", output / "THIRD_PARTY.md")
