"""External fly camera for the 2026 Ecstatica Windows build.

Run alongside the game. Open the game's Camera Editor first. This tool only
writes the editor's live camera state while Ecstatica has keyboard focus.
"""

from __future__ import annotations

import argparse
import ctypes as C
from ctypes import wintypes as W
from hashlib import sha256
import math
from pathlib import Path
import struct
import sys
import time


if sys.platform != "win32":
    raise SystemExit("This helper runs on Windows only.")

GAME_HASHES = {
    "3d80f4a8ee0d081ea7be1b4c6880b3126892e30c117baca39d28900d274f7050",
    "acde75c4a356a233e7a78770ea37a8651a7661209c08ed2275168995d368cbfc",
}
GLOBAL_BLOCK_PTR_RVA = 0x926510
EDITOR_ACTIVE_RVA = 0x926580
CAMERA_OFFSET = 0x32C850
PROCESS_ACCESS = 0x0400 | 0x0010 | 0x0020 | 0x0008
TH32CS_SNAPPROCESS = 0x00000002
TH32CS_SNAPMODULE = 0x00000008 | 0x00000010
INVALID_HANDLE_VALUE = C.c_void_p(-1).value

VK_RBUTTON = 0x02
VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_SPACE = 0x20
VK_LEFT = 0x25
VK_UP = 0x26
VK_RIGHT = 0x27
VK_DOWN = 0x28
VK_ADD = 0x6B
VK_SUBTRACT = 0x6D
VK_OEM_PLUS = 0xBB
VK_OEM_MINUS = 0xBD
VK_F10 = 0x79

kernel32 = C.WinDLL("kernel32", use_last_error=True)
user32 = C.WinDLL("user32", use_last_error=True)


class PROCESSENTRY32W(C.Structure):
    _fields_ = [
        ("dwSize", W.DWORD), ("cntUsage", W.DWORD),
        ("th32ProcessID", W.DWORD), ("th32DefaultHeapID", C.c_void_p),
        ("th32ModuleID", W.DWORD), ("cntThreads", W.DWORD),
        ("th32ParentProcessID", W.DWORD), ("pcPriClassBase", W.LONG),
        ("dwFlags", W.DWORD), ("szExeFile", W.WCHAR * 260),
    ]


class MODULEENTRY32W(C.Structure):
    _fields_ = [
        ("dwSize", W.DWORD), ("th32ModuleID", W.DWORD),
        ("th32ProcessID", W.DWORD), ("GlblcntUsage", W.DWORD),
        ("ProccntUsage", W.DWORD), ("modBaseAddr", C.c_void_p),
        ("modBaseSize", W.DWORD), ("hModule", C.c_void_p),
        ("szModule", W.WCHAR * 256), ("szExePath", W.WCHAR * 260),
    ]


class POINT(C.Structure):
    _fields_ = [("x", W.LONG), ("y", W.LONG)]


kernel32.CreateToolhelp32Snapshot.argtypes = [W.DWORD, W.DWORD]
kernel32.CreateToolhelp32Snapshot.restype = W.HANDLE
kernel32.Process32FirstW.argtypes = [W.HANDLE, C.POINTER(PROCESSENTRY32W)]
kernel32.Process32FirstW.restype = W.BOOL
kernel32.Process32NextW.argtypes = [W.HANDLE, C.POINTER(PROCESSENTRY32W)]
kernel32.Process32NextW.restype = W.BOOL
kernel32.Module32FirstW.argtypes = [W.HANDLE, C.POINTER(MODULEENTRY32W)]
kernel32.Module32FirstW.restype = W.BOOL
kernel32.Module32NextW.argtypes = [W.HANDLE, C.POINTER(MODULEENTRY32W)]
kernel32.Module32NextW.restype = W.BOOL
kernel32.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
kernel32.OpenProcess.restype = W.HANDLE
kernel32.ReadProcessMemory.argtypes = [W.HANDLE, C.c_void_p, C.c_void_p, C.c_size_t, C.POINTER(C.c_size_t)]
kernel32.ReadProcessMemory.restype = W.BOOL
kernel32.WriteProcessMemory.argtypes = [W.HANDLE, C.c_void_p, C.c_void_p, C.c_size_t, C.POINTER(C.c_size_t)]
kernel32.WriteProcessMemory.restype = W.BOOL
kernel32.CloseHandle.argtypes = [W.HANDLE]
kernel32.CloseHandle.restype = W.BOOL
user32.GetForegroundWindow.restype = W.HWND
user32.GetWindowThreadProcessId.argtypes = [W.HWND, C.POINTER(W.DWORD)]
user32.GetWindowThreadProcessId.restype = W.DWORD
user32.GetAsyncKeyState.argtypes = [C.c_int]
user32.GetAsyncKeyState.restype = W.SHORT
user32.GetCursorPos.argtypes = [C.POINTER(POINT)]
user32.GetCursorPos.restype = W.BOOL


def win_error(message: str) -> OSError:
    return OSError(C.get_last_error(), message)


def process_id() -> int | None:
    snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snapshot == INVALID_HANDLE_VALUE:
        raise win_error("Cannot enumerate processes")
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = C.sizeof(entry)
        if kernel32.Process32FirstW(snapshot, C.byref(entry)):
            while True:
                if entry.szExeFile.lower() == "ecstatica.exe":
                    return entry.th32ProcessID
                if not kernel32.Process32NextW(snapshot, C.byref(entry)):
                    break
    finally:
        kernel32.CloseHandle(snapshot)
    return None


def module_info(pid: int) -> tuple[int, Path]:
    snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPMODULE, pid)
    if snapshot == INVALID_HANDLE_VALUE:
        raise win_error("Cannot enumerate game modules")
    try:
        entry = MODULEENTRY32W()
        entry.dwSize = C.sizeof(entry)
        if kernel32.Module32FirstW(snapshot, C.byref(entry)):
            while True:
                if entry.szModule.lower() == "ecstatica.exe":
                    return int(entry.modBaseAddr), Path(entry.szExePath)
                if not kernel32.Module32NextW(snapshot, C.byref(entry)):
                    break
    finally:
        kernel32.CloseHandle(snapshot)
    raise RuntimeError("Ecstatica.exe module was not found")


class GameMemory:
    def __init__(self, pid: int, module_base: int):
        self.pid = pid
        self.module_base = module_base
        self.handle = kernel32.OpenProcess(PROCESS_ACCESS, False, pid)
        if not self.handle:
            raise win_error("Cannot open Ecstatica for memory access")

    def close(self) -> None:
        if self.handle:
            kernel32.CloseHandle(self.handle)
            self.handle = None

    def read(self, address: int, length: int) -> bytes:
        buf = C.create_string_buffer(length)
        read = C.c_size_t()
        if not kernel32.ReadProcessMemory(self.handle, C.c_void_p(address), buf, length, C.byref(read)) or read.value != length:
            raise win_error(f"Cannot read game memory at 0x{address:x}")
        return buf.raw

    def write(self, address: int, data: bytes) -> None:
        buf = C.create_string_buffer(data)
        written = C.c_size_t()
        if not kernel32.WriteProcessMemory(self.handle, C.c_void_p(address), buf, len(data), C.byref(written)) or written.value != len(data):
            raise win_error(f"Cannot write game memory at 0x{address:x}")

    def camera(self) -> int:
        block = struct.unpack("<Q", self.read(self.module_base + GLOBAL_BLOCK_PTR_RVA, 8))[0]
        if not 0x10000 <= block < 0x0000800000000000:
            raise RuntimeError("Game camera block is not ready")
        return block + CAMERA_OFFSET


def focused(pid: int) -> bool:
    window = user32.GetForegroundWindow()
    owner = W.DWORD()
    if window:
        user32.GetWindowThreadProcessId(window, C.byref(owner))
    return owner.value == pid


def key(vk: int) -> bool:
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)


def cursor() -> tuple[int, int]:
    point = POINT()
    if not user32.GetCursorPos(C.byref(point)):
        raise win_error("Cannot read cursor position")
    return point.x, point.y


def wrap_s16(value: float) -> int:
    return ((round(value) + 32768) % 65536) - 32768


def clamp_s16(value: float) -> int:
    return max(-32768, min(32767, round(value)))


def camera_axes(pitch: float, yaw: float, roll: float) -> tuple[tuple[float, float, float], ...]:
    """Return forward, right, up in the game's X/right, Y/down, Z/forward frame."""
    p, y, r = (angle * math.tau / 65536 for angle in (pitch, yaw, roll))
    sp, cp = math.sin(p), math.cos(p)
    sy, cy = math.sin(y), math.cos(y)
    sr, cr = math.sin(r), math.cos(r)
    forward = (-sy * cp, sp, cy * cp)
    level_right = (cy, 0.0, sy)
    level_up = (-sy * sp, -cp, cy * sp)
    right = tuple(level_right[i] * cr + level_up[i] * sr for i in range(3))
    up = tuple(level_up[i] * cr - level_right[i] * sr for i in range(3))
    return forward, right, up


def describe(raw: bytes) -> str:
    pos = struct.unpack_from("<hhh", raw, 8)
    angles = struct.unpack_from("<hhh", raw, 14)
    live = tuple(round(x / 65536, 2) for x in struct.unpack_from("<qqq", raw, 0x70))
    generation = struct.unpack_from("<Q", raw, 0x58)[0]
    return f"camera_valid={raw[0]} position={pos} angles={angles} live={live} generation={generation}"


def update_camera(game: GameMemory, address: int, pos: list[float], pitch: float, yaw: float, roll: float, generation: int) -> None:
    xyz = tuple(clamp_s16(v) for v in pos)
    angles = (clamp_s16(pitch), wrap_s16(yaw), wrap_s16(roll))
    pose = struct.pack("<hhhhhh", *xyz, *angles)
    # Editor values, current view values, and renderer's 16.16 live position.
    game.write(address + 8, pose)
    game.write(address + 0x30, pose)
    game.write(address + 0x70, struct.pack("<qqq", *(round(v * 65536) for v in pos)))
    game.write(address + 0x88, struct.pack("<dd", float(angles[0]), float(angles[1] & 0xFFFF)))
    game.write(address + 0x58, struct.pack("<Q", (generation + 1) & 0xFFFFFFFFFFFFFFFF))


def run(game: GameMemory, address: int, speed: float, hz: float, probe: bool) -> None:
    raw = game.read(address, 0xD0)
    editor_active = game.read(game.module_base + EDITOR_ACTIVE_RVA, 1)[0]
    print(f"editor_active={editor_active} {describe(raw)}")
    if probe:
        return
    print("Open the Camera Editor in a loaded scene. Fly: WASD, Space/Ctrl for height; look: hold right mouse or arrows; roll: Q/E (editor) or Z/C; Shift: faster; +/-: speed; Ctrl+Shift+F10: exit.")
    last = time.monotonic()
    last_cursor = cursor()
    was_adjusting = False
    pos = [float(v) for v in struct.unpack_from("<hhh", raw, 8)]
    pitch, yaw, roll = [float(v) for v in struct.unpack_from("<hhh", raw, 14)]
    previous_active = False
    plus_down = minus_down = False
    while True:
        time.sleep(1 / hz)
        now = time.monotonic()
        dt = min(now - last, 0.1)
        last = now
        raw = game.read(address, 0xD0)
        editor_active = game.read(game.module_base + EDITOR_ACTIVE_RVA, 1)[0]
        active = raw[0] == 1 and editor_active == 1 and focused(game.pid)
        if active and key(VK_CONTROL) and key(VK_SHIFT) and key(VK_F10):
            print("Freecam helper stopped.")
            return
        if not active:
            if previous_active:
                print("Camera Editor closed or Ecstatica lost focus; movement paused.")
            previous_active = False
            last_cursor = cursor()
            was_adjusting = False
            continue
        if not previous_active:
            pos = [float(v) for v in struct.unpack_from("<hhh", raw, 8)]
            pitch, yaw, roll = [float(v) for v in struct.unpack_from("<hhh", raw, 14)]
            print("Fly camera active:", describe(raw))
            previous_active = True
        else:
            current_pos = struct.unpack_from("<hhh", raw, 8)
            current_angles = struct.unpack_from("<hhh", raw, 14)
            if (any(abs(current_pos[i] - pos[i]) > 2 for i in range(3))
                    or abs(current_angles[0] - pitch) > 128
                    or abs(wrap_s16(current_angles[1] - yaw)) > 128
                    or abs(wrap_s16(current_angles[2] - roll)) > 128):
                pos = [float(v) for v in current_pos]
                pitch, yaw, roll = [float(v) for v in current_angles]
            else:
                # The game's own Q/E keys change roll; retain that change while flying.
                roll = float(current_angles[2])

        plus = key(VK_ADD) or key(VK_OEM_PLUS)
        minus = key(VK_SUBTRACT) or key(VK_OEM_MINUS)
        if plus and not plus_down:
            speed = min(speed * 1.5, 10000)
            print(f"Speed: {speed:.0f} world units/s")
        if minus and not minus_down:
            speed = max(speed / 1.5, 10)
            print(f"Speed: {speed:.0f} world units/s")
        plus_down, minus_down = plus, minus

        adjusting = key(VK_RBUTTON)
        mouse = cursor()
        dx = mouse[0] - last_cursor[0] if adjusting and was_adjusting else 0
        dy = mouse[1] - last_cursor[1] if adjusting and was_adjusting else 0
        last_cursor, was_adjusting = mouse, adjusting
        yaw -= 48 * dx + (key(VK_RIGHT) - key(VK_LEFT)) * 9000 * dt
        pitch += 48 * dy + (key(VK_DOWN) - key(VK_UP)) * 9000 * dt
        pitch = max(-16000, min(16000, pitch))
        roll_input = int(key(ord("C"))) - int(key(ord("Z")))
        roll += roll_input * 7000 * dt

        forward = int(key(ord("W"))) - int(key(ord("S")))
        side = int(key(ord("D"))) - int(key(ord("A")))
        rise = int(key(VK_SPACE)) - int(key(VK_CONTROL))
        magnitude = math.sqrt(forward * forward + side * side + rise * rise)
        if magnitude > 1:
            forward /= magnitude
            side /= magnitude
            rise /= magnitude
        step = speed * (4 if key(VK_SHIFT) else 1) * dt
        axes = camera_axes(pitch, yaw, roll)
        world_up = (0.0, -1.0, 0.0)
        for i in range(3):
            pos[i] += (axes[0][i] * forward + axes[1][i] * side + world_up[i] * rise) * step
        pos = [float(clamp_s16(value)) for value in pos]
        if forward or side or rise or roll_input or dx or dy or key(VK_LEFT) or key(VK_RIGHT) or key(VK_UP) or key(VK_DOWN):
            generation = struct.unpack_from("<Q", raw, 0x58)[0]
            update_camera(game, address, pos, pitch, yaw, roll, generation)


def main() -> None:
    parser = argparse.ArgumentParser(description="Fly the Camera Editor camera in Ecstatica")
    parser.add_argument("--probe", action="store_true", help="Read camera state without changing it")
    parser.add_argument("--speed", type=float, default=500, help="Move speed in world units per second")
    parser.add_argument("--hz", type=float, default=30, help="Update rate")
    args = parser.parse_args()
    if not 10 <= args.hz <= 120 or not 10 <= args.speed <= 10000:
        parser.error("Use 10-120 Hz and speed 10-10000")
    pid = process_id()
    if pid is None:
        raise SystemExit("Ecstatica.exe is not running. Start a game first.")
    base, path = module_info(pid)
    digest = sha256(path.read_bytes()).hexdigest()
    if digest not in GAME_HASHES:
        raise SystemExit(f"Unsupported Ecstatica.exe version ({digest}). No memory was changed.")
    game = GameMemory(pid, base)
    try:
        address = game.camera()
        print(f"Attached to Ecstatica PID {pid}; camera state 0x{address:x}")
        run(game, address, args.speed, args.hz, args.probe)
    finally:
        game.close()


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError) as exc:
        raise SystemExit(str(exc)) from exc
