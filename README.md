# Ecstatica Free Camera

Fly around the world in the Windows release of **Ecstatica** using the game's Camera Editor. The camera moves independently of the character. This is an external Python helper; it does not replace or modify `Ecstatica.exe` on disk.

## Requirements

- Windows and Python 3.10 or newer (`py` or `python` available on the command line).
- A supported Ecstatica executable. The helper checks the game's SHA-256 hash before accessing its memory and exits if the build is unknown.
- The game's **Software** background renderer (`Graphics > Background > Software`).

## Install and use

1. Keep `freecam.py` and `START_FREECAM.cmd` together. You can put them in `Ecstatica\mod\`; there is no need to replace the game's executable.
2. Start or load a game and open the Camera Editor with **F5** (the key on the tested installation).
3. Double-click `START_FREECAM.cmd`, then click back into the game.
4. Fly using the controls below. The helper pauses when the game loses focus or the Camera Editor closes.
5. To stop it, press **Ctrl+Shift+F10** while the game is focused, or close the helper's console window.

## Controls

| Input | Action |
| --- | --- |
| W / S | Fly forward / backward along the camera's view |
| A / D | Strafe left / right relative to the view |
| Space / Ctrl | Move vertically up / down |
| Hold right mouse button and move mouse | Look around |
| Arrow keys | Look around without the mouse |
| Q / E | Roll via the game's Camera Editor |
| Z / C | Roll via the helper |
| Shift | Move faster |
| + / - | Increase / decrease movement speed |

## Troubleshooting

- **Nothing moves:** Check that a game is loaded, the Camera Editor is open, and Ecstatica has focus. The helper only moves the camera under these conditions.
- **Unsupported executable:** The installed game build differs from the builds this helper recognizes. It will exit without changing game memory.
- **The helper window closes with an error:** Open a command prompt in the folder containing `freecam.py` and run `python freecam.py --probe`. Probe mode prints the camera state without changing it.
- **A distant area is missing:** Scene loading and culling still follow the game's own logic. The player may need to enter that area first.

The helper changes the live camera only while it runs. It does not move the player character or write to the game files.
