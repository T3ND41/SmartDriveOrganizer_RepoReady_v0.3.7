from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List


@dataclass(frozen=True)
class DriveInfo:
    """A mounted storage volume that can be offered as a scan source."""

    root: Path
    kind: str
    label: str = ""
    total_bytes: int = 0
    free_bytes: int = 0

    @property
    def display_name(self) -> str:
        name = f"{self.root} — {self.kind}"
        if self.label:
            name += f" — {self.label}"
        if self.total_bytes:
            name += f" — {format_bytes(self.free_bytes)} free / {format_bytes(self.total_bytes)}"
        return name

    @property
    def default_selected(self) -> bool:
        # Local fixed and removable storage are the usual meaning of "this device".
        # Mapped network drives remain visible, but are selected only by user choice.
        return self.kind in {"Fixed", "Removable", "Mounted volume"}


def format_bytes(value: int) -> str:
    amount = float(max(0, value))
    for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
        if amount < 1024 or unit == "PB":
            return f"{amount:.1f} {unit}" if unit != "B" else f"{int(amount)} B"
        amount /= 1024
    return f"{amount:.1f} PB"


def _windows_drives() -> List[DriveInfo]:
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    get_logical_drives = kernel32.GetLogicalDrives
    get_logical_drives.restype = wintypes.DWORD
    mask = get_logical_drives()
    if not mask:
        raise OSError(ctypes.get_last_error(), "Windows could not enumerate logical drives")

    get_drive_type = kernel32.GetDriveTypeW
    get_drive_type.argtypes = [wintypes.LPCWSTR]
    get_drive_type.restype = wintypes.UINT

    get_volume_information = kernel32.GetVolumeInformationW
    get_volume_information.argtypes = [
        wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD),
        ctypes.POINTER(wintypes.DWORD), wintypes.LPWSTR, wintypes.DWORD,
    ]
    get_volume_information.restype = wintypes.BOOL

    get_disk_free_space = kernel32.GetDiskFreeSpaceExW
    get_disk_free_space.argtypes = [
        wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_ulonglong),
        ctypes.POINTER(ctypes.c_ulonglong), ctypes.POINTER(ctypes.c_ulonglong),
    ]
    get_disk_free_space.restype = wintypes.BOOL

    type_names = {2: "Removable", 3: "Fixed", 4: "Network"}
    found: List[DriveInfo] = []
    for index in range(26):
        if not (mask & (1 << index)):
            continue
        root_text = f"{chr(65 + index)}:\\"
        drive_type = int(get_drive_type(root_text))
        # Skip CD/DVD, RAM disks, unknown devices and empty card-reader slots.
        if drive_type not in type_names:
            continue

        label_buffer = ctypes.create_unicode_buffer(261)
        filesystem_buffer = ctypes.create_unicode_buffer(261)
        serial = wintypes.DWORD()
        max_component = wintypes.DWORD()
        flags = wintypes.DWORD()
        label = ""
        if get_volume_information(
            root_text, label_buffer, len(label_buffer), ctypes.byref(serial),
            ctypes.byref(max_component), ctypes.byref(flags),
            filesystem_buffer, len(filesystem_buffer),
        ):
            label = label_buffer.value.strip()

        free_to_caller = ctypes.c_ulonglong()
        total = ctypes.c_ulonglong()
        total_free = ctypes.c_ulonglong()
        total_bytes = free_bytes = 0
        if get_disk_free_space(root_text, ctypes.byref(free_to_caller), ctypes.byref(total), ctypes.byref(total_free)):
            total_bytes = int(total.value)
            free_bytes = int(free_to_caller.value)
        found.append(DriveInfo(Path(root_text), type_names[drive_type], label, total_bytes, free_bytes))
    return found


def _unix_mounts() -> List[DriveInfo]:
    """Best-effort mounted-volume discovery for Linux/macOS development use."""
    roots = {Path(os.path.abspath(os.sep))}
    try:
        import psutil  # optional; not required by the Windows build
        for partition in psutil.disk_partitions(all=False):
            mountpoint = Path(partition.mountpoint)
            if mountpoint.exists() and mountpoint.is_dir():
                roots.add(mountpoint.resolve())
    except ImportError:
        # Without psutil, the root filesystem is still a valid scan source.
        pass
    except OSError:
        pass

    result: List[DriveInfo] = []
    for root in sorted(roots, key=lambda item: str(item)):
        try:
            usage = os.statvfs(root)
            total_bytes = int(usage.f_blocks * usage.f_frsize)
            free_bytes = int(usage.f_bavail * usage.f_frsize)
        except (AttributeError, OSError):
            total_bytes = free_bytes = 0
        result.append(DriveInfo(root, "Mounted volume", "", total_bytes, free_bytes))
    return result


def discover_drives() -> List[DriveInfo]:
    """Return mounted storage volumes, prioritizing local Windows drive letters."""
    if sys.platform == "win32":
        return _windows_drives()
    return _unix_mounts()
