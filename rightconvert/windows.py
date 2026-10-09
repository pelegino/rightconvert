"""Explorer integration: a classic "Convert >" submenu for each supported file type.

Everything lives under HKEY_CURRENT_USER, so no administrator rights are needed. Windows 10 shows
the menu directly; Windows 11 shows it under "Show more options".
"""

from __future__ import annotations

import os
import sys

from .engines import targets_for
from .formats import CATEGORY, SMALLER_TARGETS, TARGETS, all_extensions, ext_of, label_for

CLASSES = r"Software\Classes"
VERB = "RightConvert"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def launcher() -> str:
    return os.path.join(ROOT, "bin", "rightconvert")


def icon() -> str:
    return os.path.join(ROOT, "windows", "rightconvert.ico")


def gui_python() -> str:
    """pythonw.exe next to the running interpreter, so conversions don't open a console window."""
    folder, name = os.path.split(sys.executable)
    windowed = os.path.join(folder, name.replace("python", "pythonw", 1))
    return windowed if os.path.exists(windowed) else sys.executable


def command(target: str = "") -> str:
    to = f" --to {target}" if target else ""
    return f'"{gui_python()}" "{launcher()}" --gui --batch{to} -- "%1"'


def verb_order(category: str) -> list[str]:
    """Every possible target of a category, in menu order (Explorer sorts verbs by key name)."""
    order = []
    for t in TARGETS[category]:
        order.append(t)
        if category == "image" and t in SMALLER_TARGETS:
            order.append(t + "-small")
    return order


def menu_entries(ext: str) -> list[tuple[str, str, str]]:
    """(key name, label, target) for each Convert submenu entry of an extension."""
    category = CATEGORY[ext_of("x." + ext)]
    available = targets_for("x." + ext)
    # The same target gets the same key name for every extension of a category, so a mixed
    # selection (say .jpg and .png) runs the same verb on each file.
    return [(f"{i:02d}_{t}", label_for(category, t), t)
            for i, t in enumerate(verb_order(category)) if t in available]


def _delete_tree(winreg, root, path: str) -> None:
    try:
        key = winreg.OpenKey(root, path, 0, winreg.KEY_ALL_ACCESS)
    except FileNotFoundError:
        return
    with key:
        while True:
            try:
                child = winreg.EnumKey(key, 0)
            except OSError:
                break
            _delete_tree(winreg, root, path + "\\" + child)
    winreg.DeleteKey(root, path)


def _set(winreg, path: str, values: dict[str, str]) -> None:
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_WRITE) as key:
        for name, value in values.items():
            winreg.SetValueEx(key, name or None, 0, winreg.REG_SZ, value)


def _menu_keys() -> list[str]:
    keys = [rf"{CLASSES}\SystemFileAssociations\.{ext}\shell\{VERB}" for ext in all_extensions()]
    return keys + [rf"{CLASSES}\Directory\shell\{VERB}"]


def _refresh_explorer() -> None:
    import ctypes

    SHCNE_ASSOCCHANGED = 0x08000000
    ctypes.windll.shell32.SHChangeNotify(SHCNE_ASSOCCHANGED, 0, None, None)


def unregister(quiet: bool = False) -> int:
    import winreg

    for key in _menu_keys():
        _delete_tree(winreg, winreg.HKEY_CURRENT_USER, key)
    _refresh_explorer()
    if not quiet:
        print("Removed the Convert menu from Explorer.")
    return 0


def register() -> int:
    import winreg

    unregister(quiet=True)
    menus = 0
    for ext in all_extensions():
        entries = menu_entries(ext)
        if not entries:
            continue
        base = rf"{CLASSES}\SystemFileAssociations\.{ext}\shell\{VERB}"
        _set(winreg, base, {"MUIVerb": "Convert", "Icon": icon(), "SubCommands": "", "MultiSelectModel": "Player"})
        for name, label, target in entries:
            _set(winreg, rf"{base}\shell\{name}", {"MUIVerb": label, "MultiSelectModel": "Player"})
            _set(winreg, rf"{base}\shell\{name}\command", {"": command(target)})
        menus += 1
    folder = rf"{CLASSES}\Directory\shell\{VERB}"
    _set(winreg, folder, {"MUIVerb": "Convert...", "Icon": icon(), "MultiSelectModel": "Player"})
    _set(winreg, folder + r"\command", {"": command()})
    _refresh_explorer()
    print(f"Added the Convert menu for {menus} file types.")
    return 0
