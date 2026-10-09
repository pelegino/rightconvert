"""Notifications, alerts and the format picker, using each platform's native mechanism."""

from __future__ import annotations

import os
import subprocess
import sys

from .engines import MACOS, NO_WINDOW, WINDOWS

TITLE = "Convert"


def _osascript(script: str, *args: str) -> str:
    try:
        result = subprocess.run(["osascript", "-", *args], input=script.encode(), capture_output=True)
    except OSError:
        return ""
    return result.stdout.decode("utf-8", "replace").strip()


_TOAST = r"""
$m = [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime]
$xml = $m::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
$text = $xml.GetElementsByTagName('text')
[void]$text.Item(0).AppendChild($xml.CreateTextNode($env:RIGHTCONVERT_TITLE))
[void]$text.Item(1).AppendChild($xml.CreateTextNode($env:RIGHTCONVERT_MESSAGE))
$app = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe'
$m::CreateToastNotifier($app).Show([Windows.UI.Notifications.ToastNotification]::new($xml))
"""


def notify(message: str) -> None:
    if MACOS:
        _osascript('on run argv\n display notification (item 1 of argv) with title "Convert"\nend run', message)
    elif WINDOWS:
        # Fire and forget: the toast outlives this process. The message travels in the environment
        # so it never has to be quoted into PowerShell source.
        env = dict(os.environ, RIGHTCONVERT_TITLE=TITLE, RIGHTCONVERT_MESSAGE=message)
        try:
            subprocess.Popen(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                              "-Command", _TOAST], env=env, creationflags=NO_WINDOW,
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            pass


def alert(message: str) -> None:
    if MACOS:
        _osascript('on run argv\n activate\n display dialog (item 1 of argv) with title "Convert" '
                   'buttons {"OK"} default button 1 with icon caution\nend run', message)
    elif WINDOWS:
        import ctypes

        MB_ICONWARNING, MB_SETFOREGROUND, MB_TOPMOST = 0x30, 0x10000, 0x40000
        ctypes.windll.user32.MessageBoxW(None, message, TITLE, MB_ICONWARNING | MB_SETFOREGROUND | MB_TOPMOST)
    else:
        print("rightconvert: " + message, file=sys.stderr)


def pick(prompt: str, labels: list[str]) -> int | None:
    """Ask which format to convert to. Returns the chosen index, or None if cancelled."""
    if MACOS:
        choice = _osascript(
            "on run argv\n set theItems to rest of argv\n activate\n"
            ' set choice to choose from list theItems with title "Convert" with prompt (item 1 of argv)'
            ' OK button name "Convert" default items {item 1 of theItems}\n'
            ' if choice is false then return ""\n return item 1 of choice\nend run', prompt, *labels)
        return labels.index(choice) if choice in labels else None
    return _tk_pick(prompt, labels)


def _tk_pick(prompt: str, labels: list[str]) -> int | None:
    if WINDOWS:
        import ctypes

        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            pass
    import tkinter as tk
    from tkinter import ttk

    chosen: list[int] = []
    root = tk.Tk()
    root.title(TITLE)
    root.resizable(False, False)
    root.attributes("-topmost", True)
    icon = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "windows", "rightconvert.ico")
    if WINDOWS and os.path.exists(icon):
        root.iconbitmap(icon)

    frame = ttk.Frame(root, padding=14)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text=prompt).pack(anchor="w", pady=(0, 8))
    listbox = tk.Listbox(frame, height=min(len(labels), 14), width=max(28, max(map(len, labels)) + 4),
                         activestyle="none", exportselection=False, borderwidth=1, relief="solid",
                         highlightthickness=0)
    for label in labels:
        listbox.insert("end", label)
    listbox.selection_set(0)
    listbox.pack(fill="both", expand=True)

    def accept(_event=None):
        selection = listbox.curselection()
        if selection:
            chosen.append(selection[0])
        root.destroy()

    buttons = ttk.Frame(frame)
    buttons.pack(fill="x", pady=(12, 0))
    ttk.Button(buttons, text="Convert", command=accept, default="active").pack(side="right")
    ttk.Button(buttons, text="Cancel", command=root.destroy).pack(side="right", padx=(0, 8))
    listbox.bind("<Double-Button-1>", accept)
    root.bind("<Return>", accept)
    root.bind("<Escape>", lambda _event: root.destroy())

    root.update_idletasks()
    x = (root.winfo_screenwidth() - root.winfo_reqwidth()) // 2
    y = (root.winfo_screenheight() - root.winfo_reqheight()) // 3
    root.geometry(f"+{x}+{y}")
    root.after(50, lambda: (root.focus_force(), listbox.focus_set()))
    root.mainloop()
    return chosen[0] if chosen else None
