# PyInstaller recipe for the one-file Pawtation.exe (run from the repository root):
#   python packaging/make_icon.py
#   pyinstaller --noconfirm --clean packaging/pawtation.spec
# Shipped, read-only files (data/, assets/, the GameCube guide) go inside the exe; pawtation/paths.py finds them.
# Your own files (config.json, state.json, packs/, mods/, plugins/, swiss/) are created next to Pawtation.exe.
import os

root = os.path.abspath(os.path.join(SPECPATH, ".."))
icon = os.path.join(SPECPATH, "pawtation.ico")

a = Analysis(
    [os.path.join(SPECPATH, "pawtation_app.py")],
    pathex=[root],
    datas=[(os.path.join(root, "data"), "data"),
           (os.path.join(root, "assets"), "assets"),
           (os.path.join(root, "docs", "GAMECUBE_GUIDE.md"), "docs")],
    hiddenimports=["pawtation.setup_wizard", "pawtation.swissget"],
    excludes=["PIL", "numpy", "pytest"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name="Pawtation",
    console=False,                     # a window app: no black console box
    icon=icon if os.path.exists(icon) else None,
    upx=False,                         # packed executables trip more antivirus false alarms
)
