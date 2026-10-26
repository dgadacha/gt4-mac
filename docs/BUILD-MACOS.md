# macOS build (Apple silicon)

GT4Recomp builds and runs natively on a Mac with Apple silicon: the same recompiled game code as the Windows release
1.2.x, compiled for arm64, with the built-in renderer (CoreGS 1.1, Vulkan compute) running on Metal through MoltenVK,
and SDL3 for the window, the keyboard, gamepads and sound. There is no installer or launcher: two scripts build the
game from your own disc image and start it.

Tested on an M3 Pro (macOS 26.6, Apple clang 17, MoltenVK 1.4.2, SDL 3.4.12): the game boots, creates its save on
the memory card, plays the opening movie and the menus, and races (Arcade, Nürburgring Nordschleife, six cars) at a
steady 60 FPS in a 1920x1080 Retina window.

## What you need

| | |
|---|---|
| Mac | Apple silicon (M1 or later) |
| Xcode command line tools | `xcode-select --install` (Apple clang with C++20) |
| Homebrew packages | `brew install cmake ninja python sdl3 molten-vk vulkan-loader vulkan-headers` (`vulkan-tools` adds `vulkaninfo`, optional) |
| Rust | [rustup](https://rustup.rs) with a current stable toolchain (it builds the shader compiler, naga 30, from `tools/wgsl_spirv/Cargo.lock`) |
| Disc image | your own **Gran Turismo 4 USA v2.00 (SCUS-97328)**, as a plain `.iso` of 5,314,478,080 bytes, SHA-256 `67b6c0075837f3ae1132d608acf2858bf13b2dd62d6eae83dff76df02e4e824f` (`docs/inputs/usa-v2.00.json`) |
| Disk space | about 6.5 GB: the disc image (5.3 GB) and about 1 GB of generated code, tools and builds |

The disc image goes at the root of the checkout, named exactly `Gran Turismo 4 (USA) (v2.00).iso` (git ignores it),
or anywhere else with `--iso`. A Redump `.zip` holds this file as is. A `.chd` converts with MAME's `chdman`
(`brew install rom-tools`): `chdman extractdvd -i image.chd -o "Gran Turismo 4 (USA) (v2.00).iso"`, or `extractcd` for
an image made with `createcd`, whose `.bin` (one MODE1/2048 track) is the ISO. The build checks the SHA-256.

## Build

From the checkout root:

```bash
git clone -c core.autocrlf=true https://github.com/snuri00/ps2-web-recomp private/references/ps2-web-recomp
git -C private/references/ps2-web-recomp checkout 1b4808793a12c45125262fd2d5f50a9ec9f7c020
python3 -m venv private/tooling-venv
private/tooling-venv/bin/python -m pip install -r scripts/requirements.txt
private/tooling-venv/bin/python scripts/macos_build.py
```

The donor runtime (ps2-web-recomp, MIT) must be cloned with `core.autocrlf=true`: its pins in `docs/inputs` hash the
Windows checkout, whose files have CRLF line endings.

`scripts/macos_build.py` regenerates every private input of the release recipe (docs/BUILD.md, slice262) from the disc
and the donor, checks each one against its pin, then builds the game. From scratch it takes under three minutes on
an M3 Pro. Run it again at any time: a stage whose output exists is only checked. One stage runs alone with
`--stage <name>`.

| Stage | Output (under `private/`) | Check |
|---|---|---|
| `ee` | `macos-ee-aspect-producer`: `CORE.GT4`, the reconstructed ELF and its aspect patch, the donor translator built here, the 328 generated C++ files and `game-build/libps2game.a`; copies in `fingerprint-check/CORE.GT4` and `reconstructed/SCUS_973.28.elf` | disc, CORE and ELF pins; the generated sources equal the release library's source inventory (`slice217-ee-libraries.json`, `921b18fb...`); `macos-library.json` records the library |
| `vu` | `slice155-vu1-image`, `slice157-vu1-all-entries`, `slice157-vu1-all-gen` (2,048 VU1 programs), `slice160-vu0-image`, `slice160-vu0-gen-r3` (14 VU0 programs) | image, entry list, table and manifest pins (`slice155-vu1-image.json`, `slice160-vu0-image.json`, `slice262-pcsx2.json`) |
| `runtime` | `slice262-frame-cost-runtime`, `slice200-memcard-runtime`, `slice262-license-guard-runtime` | `slice262-frame-cost-runtime.json`, `slice262-pcsx2.json`, `slice262-license-guard-runtime.json` |
| `port` | `slice191-gs-stream-port` | `slice191-gs-stream-runtime.json` |
| `shaders` | `slice153-pacing-shaders` (nine SPIR-V files) | `slice262-frame-cost-runtime.json` |
| `game` | `macos-build/gt4vulkan` and `macos-build/shaders` | CMake checks the capsules, the port, the shaders and the library receipt again |

Every input except the EE library is the same bytes as the Windows release's. The EE library cannot be: it is arm64
code compiled here, so it is tied to its sources instead, which are the release's sources byte for byte.

## Play

```bash
private/tooling-venv/bin/python scripts/macos_play.py
```

The game opens in a 960x540 window (1920x1080 pixels on a Retina display). Options: `--fullscreen`, `--mute` (no
sound), `--controls <file>` (a controls file, [CONTROLS.md](CONTROLS.md)), `--iso <path>`, `--card <file>`.

- **Saves:** the memory card is `private/macos-play/card.ps2`. A new card is empty: the game offers to create its game
  data and formats the card. Every session first copies the card to `private/macos-play/backups/` (the ten newest
  are kept).
- **Log:** `private/macos-play/game.log`. F8 writes the performance report to it.
- **Fullscreen:** `--fullscreen`, or Cmd+F, F11 (fn+F11 on most Mac keyboards) or Alt+Enter in game.
- **Quit:** close the window or press Cmd+Q. The game stops cleanly and writes a pending save.

Keyboard (the Windows layout; keys are named by their label, so on an AZERTY keyboard W is the key marked W):

| Key | PS2 button |
|---|---|
| W, Enter | Cross (accelerate, confirm) |
| S | Square (brake) |
| Space | Circle (handbrake) |
| A, D, arrow keys | D-pad (steer, navigate); E is also D-pad up |
| Backspace, Esc | Triangle (back) |
| Shift | R1 (nitro) |
| R, F | R2, L2 (gear up, gear down) |
| Q | L1 (look back) |
| C, Tab | Select (camera) |
| P | Start (pause) |

Gamepads that SDL3 knows (Xbox, DualShock 4, DualSense, Switch Pro and others) work as on Windows, with analog
triggers and rumble; the first connected pad is player 1.

## Differences from the Windows release

- **Renderer:** CoreGS 1.1 only, at the native resolution (scale 1), with the 16:9 picture and the native aspect
  ratios. GSdx (the PCSX2 GS in `gt4-gs.exe`) is a Windows process, so 1080p-and-above internal resolutions, the
  GSdx options and custom texture packs are not available; `GT4_RENDERER=pcsx2` refuses to start.
- **Interlaced menus:** the game shows its menus and movies in 480i, one field per VBlank. CoreGS 1.1 on Windows
  presents each field line-doubled, so the picture bounces by one field line at every VBlank (docs/STATUS.md,
  slice196). The macOS window blends the last two fields instead (`GT4_DEINTERLACE=blend`, the default; `off` shows
  the bouncing fields): measured on the title screen, consecutive pictures no longer shift (they alternated by two
  lines) and the frame-to-frame difference falls from about 4.0 to 0.9. Races are progressive (480p) and unchanged.
- **Not on macOS:** the launcher and installer, RetroAchievements (WinHTTP and GDI+), `GT4_MONITOR`, the XInput
  backend (`GT4_INPUT=xinput`), the shape capture tools.
- **Port:** the release links `slice200-port`, whose `main.cpp` is a hand edit of the slice191 one (the installer's
  `--portable-check` and a card flush after headless runs) that no script derives. macOS links `slice191-gs-stream-port`,
  which `scripts/prepare_external_vulkan.py` derives; its other three files are identical.
- **Arithmetic:** the code is compiled with `-ffp-contract=off` (arm64 always has fused multiply-add, x86-64 without
  `-march` has none) and `-fno-strict-aliasing` (clang-cl's default), so it computes what the Windows build computes.

## Under the hood

| File | Role |
|---|---|
| `scripts/macos_build.py`, `scripts/macos_play.py` | the build and the start described above |
| `native/window_sdl.cpp` | the game window (SDL3 and a Metal view), the VBlank message pump, keyboard, fullscreen, cursor, card lock; `window.cpp` is the Win32 window |
| `native/audio_sdl.cpp` | the audio output on an SDL3 stream, with the WinMM path's buffers, 60 ms target and rate control; `GT4_MUTE=1` plays at zero gain |
| `native/frame_clock_posix.cpp` | the frame pacer's clock (steady clock, nanosleep and a final spin) |
| `native/native_vulkan.cpp` (`set_interlaced_presentation`) | the field blend of interlaced pictures in transfer operations: the newest field replaces its rows in a woven image, a 2:1 linear blit averages each pair of rows and a 1:2 linear blit returns to the display height; `GT4_PRESENT_DUMP=<folder>` with `GT4_PRESENT_DUMP_FRAMES=first:last` writes the presented pictures (before the window scaling) as PPM files, for tests |
| `native/native_vulkan.*`, `native/vulkan_extensions.*` | the Vulkan loader (`dlopen`: next to the executable, Homebrew `vulkan-loader`, then MoltenVK), the Metal surface (`VK_EXT_metal_surface`, the window's CAMetalLayer as the surface handle), `VK_KHR_portability_enumeration` and `VK_KHR_portability_subset` |
| `native/gs_stream/gs_stream_client_donor_only.cpp` | the GS stream hooks without a GS process: the built-in renderer, every hook returns at once |
| `native/posix_compat.h` | `_putenv_s` and `tmpfile_s` for the shared sources, so the derived port files keep their pinned bytes |
| `scripts/vu1_image.py build --pinned-tail` | the VU1 image without the recorded snapshots: the tail comes from the pin, and the image must equal the pinned image |
| `scripts/prepare_external_vulkan.py`, `scripts/prepare_perf_runtime.py` | write their pinned text files with CRLF on every platform (they used the platform's text mode) |

Environment variables are the Windows ones (docs/BUILD.md and the launcher). `scripts/macos_play.py` sets those of the
launcher: `PS2_SCALE=1`, `PS2_GS=gpu`, `GT4_FORCE_WIDESCREEN=1`, `GT4_FORCE_480P=1`, `GT4_DISPLAY_ASPECT=auto`,
`GT4_PRESENT_MODE=fifo`, `GT4_PERF=1` and `GT4_FULLSCREEN`.

To run the game by hand, for example headless with scheduled presses and frame dumps (PPM, every 100 frames):

```bash
mkdir -p private/macos-run && cp private/reconstructed/SCUS_973.28.elf private/macos-run/SCUS_973.28
cd private/macos-run
../macos-build/gt4vulkan SCUS_973.28 --ntsc --disc "../../Gran Turismo 4 (USA) (v2.00).iso" --memcard card.ps2 \
  --frames 3000 --frames-dir frames --frame-every 100 --press 700:cross:10 --press 1000:cross:10
```

The guest executable must be named `SCUS_973.28`. Add `--window` for the window (with `GT4_MUTE=1` for silence).

## Tests

```bash
ctest --test-dir private/macos-build --output-on-failure
```

After a full build (`cmake --build private/macos-build`), all 36 tests pass, among them the Vulkan pixel tests
(compute raster, display and readback against the CPU reference, presentation and resize on MoltenVK), the
asynchronous stress test, the VU0 and VU1 differential tests and the Python suite (644 tests, 80 skipped: Windows
assets and the Windows-only GS process and capture tools). The Python tests run with the resolved temporary folder
(`/private/var/...`): the tools refuse paths with a linked ancestor, and macOS reaches `/var` through a link.

## Troubleshooting

| Message | Fix |
|---|---|
| `Vulkan loader unavailable` | `brew install vulkan-loader molten-vk`; `vulkaninfo --summary` (from `vulkan-tools`) must list the Apple GPU |
| `missing donor checkout` or a donor pin mismatch | clone the donor again with `-c core.autocrlf=true` (a LF checkout differs from every pin) |
| `... holds [...], expected [...]` | a capsule folder holds an extra file (the checks ignore Finder's `.DS_Store` only): delete the folder, the next build derives it again |
| `Cannot exclusively lock game memory card` | another game session uses the card; close it first |
| `GT4_RENDERER=pcsx2 needs the GS process` | unset `GT4_RENDERER` (the built-in renderer is the only one on macOS) |
