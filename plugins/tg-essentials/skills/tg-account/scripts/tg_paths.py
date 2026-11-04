"""Locate tdata without loading keys or connecting to Telegram. Run directly to diagnose."""
import json
import os
import pathlib
import subprocess
import sys


def default_tdata() -> pathlib.Path:
    home = pathlib.Path.home()
    if sys.platform == "win32":
        return pathlib.Path(os.environ.get("APPDATA", home)) / "Telegram Desktop" / "tdata"
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / "Telegram Desktop" / "tdata"
    return home / ".local" / "share" / "TelegramDesktop" / "tdata"


def windows_commands(notes: list[str]) -> list[tuple[str, str]]:
    import winreg

    commands = []
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\tg\shell\open\command") as key:
            command, kind = winreg.QueryValueEx(key, "")
        if kind in (winreg.REG_SZ, winreg.REG_EXPAND_SZ) and isinstance(command, str):
            commands.append(("HKCU tg handler", os.path.expandvars(command)))
    except OSError:
        notes.append("HKCU tg handler unavailable")

    # Restrict discovery to this login session and bound a slow or unavailable CIM service.
    powershell = pathlib.Path(os.environ.get("SystemRoot", "C:/Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    script = (
        "[Console]::OutputEncoding = [Text.UTF8Encoding]::new(); "
        "$ErrorActionPreference = 'Stop'; "
        "$session = [Diagnostics.Process]::GetCurrentProcess().SessionId; "
        "@(Get-CimInstance Win32_Process -Filter \"Name='Telegram.exe'\" | "
        "Where-Object { $_.SessionId -eq $session } | "
        "Select-Object -ExpandProperty CommandLine) | ConvertTo-Json -Compress"
    )
    try:
        result = subprocess.run(
            [str(powershell), "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, text=True, encoding="utf-8", timeout=3,
            check=True, creationflags=subprocess.CREATE_NO_WINDOW,
        )
        values = json.loads(result.stdout or "null")
        if isinstance(values, str):
            values = [values]
        for command in values or []:
            if isinstance(command, str) and command:
                commands.append(("running Telegram", command))
    except (OSError, subprocess.SubprocessError, ValueError):
        notes.append("Running Telegram lookup unavailable or timed out (3s limit)")
    return commands


def windows_args(command: str) -> list[str]:
    import ctypes

    shell = ctypes.WinDLL("shell32", use_last_error=True)
    shell.CommandLineToArgvW.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_int)]
    shell.CommandLineToArgvW.restype = ctypes.POINTER(ctypes.c_wchar_p)
    kernel = ctypes.WinDLL("kernel32")
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    count = ctypes.c_int()
    argv = shell.CommandLineToArgvW(command, ctypes.byref(count))
    if not argv:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return argv[:count.value]
    finally:
        kernel.LocalFree(argv)


def resolve_tdata(notes: list[str] | None = None) -> pathlib.Path:
    if notes is None:
        notes = []

    def checked(path: pathlib.Path, source: str) -> pathlib.Path | None:
        path = path.expanduser().resolve()
        if path.is_dir() and any((path / f"key_data{suffix}").is_file() for suffix in ("s", "0", "1")):
            notes.append(f"{source}: {path}")
            return path
        notes.append(f"{source}: {path} (missing folder or key_data marker)")
        return None

    explicit = os.environ.get("TG_TDATA")
    if explicit:
        path = checked(pathlib.Path(os.path.expandvars(explicit)), "TG_TDATA")
        if path is not None:
            return path
        raise SystemExit("Invalid TG_TDATA. Set it to the Telegram Desktop tdata folder.\n" + "\n".join(notes))
    path = checked(default_tdata(), "standard")
    if path is not None:
        return path

    candidates = set()
    if sys.platform == "win32":
        for source, command in windows_commands(notes):
            try:
                args = windows_args(command)
            except OSError:
                notes.append(f"{source}: cannot parse executable path")
                continue
            exe = pathlib.Path(args[0])
            if not exe.is_absolute() or exe.name.lower() != "telegram.exe" or not exe.is_file():
                notes.append(f"{source}: expected an existing absolute Telegram.exe path")
                continue
            if any(arg.lower() in ("-workdir", "-key") for arg in args[1:]):
                raise SystemExit(f"{source} uses a custom profile. Set TG_TDATA explicitly.")
            path = checked(exe.parent / "tdata", source)
            if path is not None:
                candidates.add(path)
    if len(candidates) == 1:
        return candidates.pop()
    if candidates:
        raise SystemExit("Multiple tdata profiles found. Set TG_TDATA explicitly.\n" + "\n".join(notes))
    raise SystemExit("No usable tdata found. Set TG_TDATA to the Telegram Desktop tdata folder.\n" + "\n".join(notes))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    details = []
    resolve_tdata(details)
    print("\n".join(details))
