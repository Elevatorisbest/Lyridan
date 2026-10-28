"""Write build metadata before packaging.

  python tools/write_build_info.py [--dev N]

* lyridan/_build.py               BUILD label shown in the window title / About box
* packaging/windows/version_info.txt   Windows file version resource
Prints the full version string (e.g. 2.0.0 or 2.0.0-dev.37) for CI to reuse.
"""
import argparse
import datetime
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from lyridan import VERSION  # noqa: E402

p = argparse.ArgumentParser()
p.add_argument("--dev", type=int, help="dev build number")
a = p.parse_args()

label = f"{VERSION}-dev.{a.dev}" if a.dev else VERSION
stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
with open(os.path.join(ROOT, "lyridan", "_build.py"), "w", encoding="utf-8") as fh:
    fh.write(f'BUILD = "{label}"\nBUILD_DATE = "{stamp}"\n')

nums = [int(x) for x in VERSION.split(".")[:3]] + [a.dev or 0]
tup = ", ".join(map(str, nums))
vi = f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers=({tup}), prodvers=({tup}), mask=0x3f, flags=0x0, OS=0x40004,
                    fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', 'Elevatorisbest'),
      StringStruct('FileDescription', 'Lyridan - lyrics to Rocksmith vocals'),
      StringStruct('FileVersion', '{label}'),
      StringStruct('InternalName', 'Lyridan'),
      StringStruct('LegalCopyright', 'GPL-2.0'),
      StringStruct('OriginalFilename', 'Lyridan.exe'),
      StringStruct('ProductName', 'Lyridan'),
      StringStruct('ProductVersion', '{label}')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""
os.makedirs(os.path.join(ROOT, "packaging", "windows"), exist_ok=True)
with open(os.path.join(ROOT, "packaging", "windows", "version_info.txt"), "w", encoding="utf-8") as fh:
    fh.write(vi)
print(label)
