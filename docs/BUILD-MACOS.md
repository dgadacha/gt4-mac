# macOS build (Apple silicon)

GT4Recomp builds and runs natively on a Mac with Apple silicon: the same recompiled game code as the Windows release
1.2.x, compiled for arm64, with the built-in renderer (CoreGS 1.1, Vulkan compute) running on Metal through MoltenVK,
and SDL3 for the window, the keyboard, gamepads and sound. There is no installer or launcher: two scripts build the
game from your own disc image and start it. The PCSX2 GS renderer of the Windows release (`gt4-gs`, higher internal
resolutions) also runs on the Mac, built separately: see [PCSX2 GS renderer](#pcsx2-gs-renderer-gt4-gs).

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
| `menu` | `macos-menu-runtime`: the donor `disc.cpp` read through the disc overlay and the license guard `dispatch.cpp` with the menu bridge (see [In-game Graphics menu](#in-game-graphics-menu-experimental)) | `macos-menu-runtime.json` |
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
- **Dock icon:** a PNG of your own at `private/macos-play/gt4-icon.png` becomes the game's icon in the Dock while it
  runs (`GT4_WINDOW_ICON`); the repository ships no game artwork.
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

- **Renderer:** CoreGS 1.1 by default, at the native resolution (scale 1), with the 16:9 picture and the native
  aspect ratios. The PCSX2 GS renderer is `gt4-gs` built for macOS (Metal), started with `--renderer pcsx2`; there is
  no launcher page for its options: they are on the game's Options > Graphics page.
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

## In-game Graphics menu (experimental)

Options > Screen gets a **Display Mode** row (Window, Full Screen): the game's own row, list, texts, tooltip and
sounds, and the window changes at once.

With the PCSX2 GS renderer, the General group of the Options menu also gets a **Graphics** tile (a television showing
"HD", drawn from the game's Picture Quality icon) after Sound. Its page holds the renderer's settings, made of the
same widgets:

| Row | Choices | `gt4-gs.ini` |
|---|---|---|
| Resolution | Native (the PS2 picture), then the common resolutions that fit in the screen (1280x720, 1920x1080, 2560x1440, 3840x2160) and the screen's own, for example 3024x1964 on a 14-inch MacBook Pro | `upscale_multiplier` |
| MetalFX Upscaling | Off, On (see [HDR and MetalFX](#hdr-and-metalfx)) | `[GT4GS] MetalFX` |
| Anisotropic Filtering | Off, 2x, 4x, 8x, 16x | `MaxAnisotropy` |
| Anti-Aliasing | Off, FXAA | `fxaa` |
| Sharpening | Off, Low, Medium, High (FidelityFX CAS, sharpen only) | `CASMode` 1 and `CASSharpness` 25, 50, 100 |
| Color Boost | Off, Low, Medium, High (shade boost) | `ShadeBoost`, contrast 52, 54, 56 and saturation 57, 64, 72 (50 is neutral) |
| HDR | Off, On | `[GT4GS] HDR` |

Cost, measured on an M3 Pro with the race replay at 5x (frames 3,600 to 6,000, without a window): 4.7 to 5.0 ms of
GS work per frame with none of these effects, 7.2 to 7.7 ms with 16x filtering, FXAA, High sharpening and Medium
color boost together. There is no dithering row: PCSX2's `dithering_ps2 = 0` changes no pixel of the replay (119
frames compared from boot to race at 1x), so GT4 does not use the GS dithering there.

The choices apply within a few frames and are kept in the GS process's settings file; a value written there by hand
that no choice writes shows as the default choice. Cancel on the page restores what the page opened with. The page's
panel sits higher than the Screen page's so that its seven rows stay above the tooltip bar. Without the renderer's
settings (the built-in renderer), neither the tile nor its row shows.

The Graphics page lives in the slot of a page the disc ships unused, Camera (`CameraRoot`): its images
(`US/CameraRoot.gpb`, the same as the Screen page's), its text page and its tile icon, which the build redraws. So the
overlay replaces files and adds none.

How it works:

1. **Disc overlay.** `scripts/gt4_volume_overlay.py` places replacement files past the end of the disc image and
   rewrites their records in the `GT4.VOL` catalogue (only the catalogue pages that change are recompressed; the result
   is read back and checked). With `GT4_DISC_OVERLAY=<file>`, `native/disc_overlay.cpp` serves those bytes through the
   menu capsule's `disc.cpp`. The disc image itself is never written.
2. **Option files.** `scripts/gt4_graphics_menu.py` takes the user's `projects/option` files and edits the widget
   tree (`option.mproject`: the Display Mode row, copied from the Video Output row with our names, and the Graphics
   page, a copy of the Screen page whose rows are such copies), our texts in `US/rtext.rt2` (RT03,
   `scripts/gt4_rtext.py`, which rewrites the disc's file byte for byte), the tile icon in `US/OptionRoot.gpb`
   (`scripts/gt4_option_icon.py`: the Picture Quality television with its colour bars replaced by a blue "HD" screen,
   in the icon format of the disc, 104x45 pixels in 256 colours, written over the unused Camera icon) and the compiled
   option script (`option.adc`, below). It checks the hashes of the files it was written for.
3. **Host bridge.** Two `MSystem` natives are empty in the retail executable: `SetDrawPerfMeter(id, value)` (callback
   `0x001AC238`) and `IsDrawPerfMeter(id)` (`0x001AC240`). The menu capsule's `dispatch.cpp` runs
   `native/menu_bridge.cpp` for them: the first sets host setting `id`, the second returns its value as an Adhoc int,
   built with the game's own functions. A native function gets the result holder in a0, the argument count in a1 and
   the argument array in a2. The window registers setting 1 (display mode) and setting 2 (field blend, not in the menu
   yet); with the PCSX2 GS renderer, setting 3 (the resolution choice) and the read-only settings 11 to 15 and 21 to
   25 (width and height of each resolution offered, `native/gs_resolution.hpp`), which the script writes into the
   list's items, removing the items the screen does not use, then settings 4 (HDR), 5 (MetalFX) and 30 to 33
   (anisotropic filtering, anti-aliasing, sharpening, color boost; `native/gs_menu_settings.hpp` holds what each choice
   writes). Without the bridge, or in a headless run (no window, no display settings), `IsDrawPerfMeter`
   returns nil and the script keeps the row hidden; the Options page shows the Graphics tile only when setting 3
   answers.

The option script is not built by this repository. It is compiled from the reconstructed option scripts of OpenAdhoc
(GPL-3.0) adapted to the v2.00 retail script, with GTAdhocToolchain (MIT) patched to reproduce the 2004 compiler
(Adhoc version 5): local redeclaration, the declared stack size (a call counts its result above the callee, over the
whole function), block-scoped static references, no scope for an unbraced `if` body or a `for` initialisation, logical
chains that jump to their end, no NOP for an empty block, the `case` switch variable. Check: the unmodified rebuild
equals the disc's `option.adc` byte for byte once debug line numbers and source file names are cleared (247,061
bytes on both sides), and the toolchain rewrites the disc's file unchanged (251,715 bytes). Those sources and the
toolchain patch stay private (`private/tools`, `private/menu-work`) until their publication is decided.

```bash
private/tooling-venv/bin/python scripts/gt4_graphics_menu.py build --iso "Gran Turismo 4 (USA) (v2.00).iso" \
  --adc <compiled option.adc> --output private/macos-graphics-menu
```

`scripts/macos_play.py` then starts the game with `private/macos-graphics-menu/overlay.gt4ovl` (`--no-menu-overlay`
starts without it). `GT4_MENU_BRIDGE_TRACE=1` logs every native the scripts call (invoker, callback, arguments).
Checked in game with the rebuilt script: every visible Options page opens and closes (the five General pages, the
four Arcade Mode pages and Course Registration, Photo Lab, the Controllers pages and the Miscellaneous pages); Display
Mode switches the window to full screen and back. Not yet: the display mode is not kept for the next start
(`--fullscreen` decides it).

## PCSX2 GS renderer (gt4-gs)

`gt4-gs` is the PCSX2 GS in a process of its own (GPL-3.0, never linked into the game; docs/GS-LIVE.md), built from
the fork `moesuito/gt4recomp-gs`. Its macOS port is the `gt4gs/macos` branch of
[dgadacha/gt4recomp-gs](https://github.com/dgadacha/gt4recomp-gs/tree/gt4gs/macos), a copy of that fork: the
shared-memory transport on POSIX (`gs_stream_ipc_posix.cpp`), the JIT-free build on arm64, the Metal renderer, and the
picture shown in the game window. It stays a repository of its own, apart from the game's MIT code.

Build it once (about ten minutes on an M3 Pro), from the checkout root:

```bash
git clone --branch gt4gs/macos https://github.com/dgadacha/gt4recomp-gs private/tooling/gt4recomp-gs
cd private/tooling/gt4recomp-gs
xcodebuild -downloadComponent MetalToolchain        # Xcode's Metal shader compiler, about 705 MB
brew install cmake ninja sdl3 zstd lz4 libpng jpeg-turbo webp freetype harfbuzz
.github/workflows/scripts/macos/build-dependencies-gt4gs-arm64.sh ../gt4gs-deps
cmake -S . -B ../gt4gs-build -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_OSX_ARCHITECTURES=arm64 \
  -DCMAKE_PREFIX_PATH="$PWD/../gt4gs-deps;$(brew --prefix)" -DENABLE_QT_UI=OFF -DENABLE_GSRUNNER=OFF \
  -DENABLE_GT4GS=ON -DGT4GS_ONLY=ON -DUSE_VULKAN=OFF -DENABLE_TESTS=OFF -DDISABLE_ADVANCE_SIMD=ON
cmake --build ../gt4gs-build --target pcsx2-gt4gs
```

The result is `private/tooling/gt4gs-build/pcsx2-gt4gs/gt4-gs` with `resources/` beside it (the Metal shaders
`Metal23.metallib`, fonts and `GameIndex.yaml`). Then:

```bash
private/tooling-venv/bin/python scripts/macos_play.py --renderer pcsx2
```

`--upscale N` (1 to 12) sets the internal resolution multiplier; the game's Resolution row changes it too. The settings
are `private/macos-play/gs/gt4-gs.ini` (docs/GS-SETTINGS.md; created on first use with 3x, 1920x1080), its data
(shader cache) `private/macos-play/gs/data`. `--gs-process <path>` starts another build.

How the picture reaches the window: a macOS process cannot draw into another process's window, so `gt4-gs` has no
window in live mode. Its Metal layer is the root of a remote Core Animation context (`pcsx2-gt4gs/LiveViewMac.mm`),
whose id answers CONTROL attach_window (`WindowPayload::layer_id`, docs/GS-STREAM-PROTOCOL.md); the game shows it in
a `CALayerHost` over its Metal view (`native/picture_layer_host.mm`), scaled to the backing scale, so one picture pixel
is one screen pixel. Window resizes and fullscreen send CONTROL resize as on Windows. The Resolution row rewrites
`upscale_multiplier` and sends CONTROL reload_config, which this `gt4-gs` applies to the running GS (the Windows
1.2.1 build answers it with an error).

Measured on an M3 Pro (macOS 26.6), Arcade race on the Nürburgring Nordschleife:

| Internal resolution | Replay, GS work per frame (mean, worst) |
|---|---|
| 1x (native) | 1.8 to 2.2 ms, 5.2 ms |
| 3x (1920x1080) | 2.2 to 2.4 ms, 3.6 ms |
| 4x (2560x1440) | 3.4 to 3.6 ms, 19.7 ms (one frame) |
| 6x (3840x2160) | 7.1 to 7.6 ms, 11.5 ms |

The replay plays a capture of the game's GS stream (`GT4_GS_CAPTURE`, 6,000 frames: boot, menus, movie, race)
through `gt4-gs --replay-gscap` without a window, the GPU at most two frames behind; the race is frames 3,600 to
6,000. In game, 6x in the 1920x1080 window holds 60 FPS: the mean frame interval is 16.666 ms, as with the built-in
renderer, and the slowest frame of each five-second interval is under 19 ms.

Known differences: the 480i menus leave a black band at the bottom of the window (38 to 95 pixels of 1080 on the
pages checked), which the built-in renderer does not show; the first run compiles shaders (a notice at the bottom
left of the picture, gone once they are in the cache).

### HDR and MetalFX

Two options of the macOS `gt4-gs`, in `gt4-gs.ini` `[GT4GS]` (`HDR`, `HDRPeak`, `MetalFX`; docs/GS-SETTINGS.md), set
by `macos_play.py --hdr on|off --metalfx on|off` or the game's Options > Graphics page, which applies them at once:

- **HDR** (displays with EDR headroom, such as the XDR screen of a MacBook Pro): the picture is presented on an
  RGBA16Float layer in extended linear sRGB that asks for high dynamic range (`preferredDynamicRange` and
  `contentsHeadroom` on macOS 26, the EDR flag before). The PS2 picture is SDR: it is decoded to linear light and its
  highlights, from luminance 0.7 (sRGB 0.85), are expanded towards `HDRPeak` percent of SDR white (default 300),
  limited to the screen's potential headroom; shadows and midtones keep their SDR look. The headroom shows only while
  the picture is visible: `gt4-gs` logs the screen's EDR headroom two seconds after HDR turns on (above 1 when it is
  in use). A test program with the same setup across two processes (a remote layer shown with `CALayerHost`) raised
  the headroom of this M3 Pro's screen to 5.33 of a potential 16; window captures stay SDR, so the result is for the
  eye to judge.
- **MetalFX:** Apple's spatial upscaler (macOS 13 or later) enlarges the picture from its internal resolution to its
  rectangle in the window, instead of the presentation's bilinear stretch, when the picture is smaller on both axes
  (for example 2x, 1280x896, in a 1920x1080 window). It is a cheaper way to a sharp full-screen picture than a high
  multiplier: in game, 2x with MetalFX in the 1920x1080 window kept 60 FPS with 4.3 to 6.2 ms of GPU time per race
  frame, against 10.2 to 12.0 ms for 3x without it (GPU times reported by `gt4-gs`, which the Mac's clock scaling
  affects). At a multiplier that already fills the screen it does nothing.

## Under the hood

| File | Role |
|---|---|
| `scripts/macos_build.py`, `scripts/macos_play.py` | the build and the start described above |
| `native/window_sdl.cpp` | the game window (SDL3 and a Metal view), the VBlank message pump, keyboard, fullscreen, cursor, card lock; `window.cpp` is the Win32 window |
| `native/audio_sdl.cpp` | the audio output on an SDL3 stream, with the WinMM path's buffers, 60 ms target and rate control; `GT4_MUTE=1` plays at zero gain |
| `native/frame_clock_posix.cpp` | the frame pacer's clock (steady clock, nanosleep and a final spin) |
| `native/native_vulkan.cpp` (`set_interlaced_presentation`) | the field blend of interlaced pictures in transfer operations: the newest field replaces its rows in a woven image, a 2:1 linear blit averages each pair of rows and a 1:2 linear blit returns to the display height; `GT4_PRESENT_DUMP=<folder>` with `GT4_PRESENT_DUMP_FRAMES=first:last` writes the presented pictures (before the window scaling) as PPM files, for tests |
| `native/native_vulkan.*`, `native/vulkan_extensions.*` | the Vulkan loader (`dlopen`: next to the executable, Homebrew `vulkan-loader`, then MoltenVK), the Metal surface (`VK_EXT_metal_surface`, the window's CAMetalLayer as the surface handle), `VK_KHR_portability_enumeration` and `VK_KHR_portability_subset` |
| `native/gs_stream/gs_stream_client.cpp`, `native/gs_stream/gs_stream_ipc_posix.cpp` | the GS stream client of the Windows release (the process start, file hash and clocks have POSIX versions) and its transport on POSIX shared memory and address waits; `GT4_GS_CAPTURE` writes `.gscap` files with either renderer |
| `native/picture_layer_host.mm` | `GT4_RENDERER=pcsx2`: the GS process's picture layer in the window; `GT4_WINDOW_CAPTURE_DIR=<folder>` (with `GT4_WINDOW_CAPTURE_EVERY`, VBlanks) writes the window as the player sees it, for tests, and logs whether the window is visible and the screen's EDR headroom; each capture holds the game for about 50 ms |
| `native/gs_config_file.*`, `native/gs_resolution.*`, `native/gs_menu_settings.*` | the Graphics page's rows: one key of `gt4-gs.ini` changed in place, the resolutions offered per screen with their multipliers, and the keys each choice of the other rows writes (fixtures `native_gs_config_file`, `native_gs_resolution`, `native_gs_menu_settings`) |
| `native/posix_compat.h` | `_putenv_s`, `tmpfile_s` and `fopen_s` for the shared sources, so the derived port files keep their pinned bytes |
| `scripts/vu1_image.py build --pinned-tail` | the VU1 image without the recorded snapshots: the tail comes from the pin, and the image must equal the pinned image |
| `scripts/prepare_external_vulkan.py`, `scripts/prepare_perf_runtime.py` | write their pinned text files with CRLF on every platform (they used the platform's text mode) |
| `scripts/prepare_menu_runtime.py`, `native/disc_overlay.*`, `native/menu_bridge*` | the in-game Graphics menu hooks (section above) and their fixtures `native_disc_overlay` and `native_menu_bridge` |

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

After a full build (`cmake --build private/macos-build`), all 41 tests pass, among them the Vulkan pixel tests
(compute raster, display and readback against the CPU reference, presentation and resize on MoltenVK), the
asynchronous stress test, the VU0 and VU1 differential tests, the GS stream transport and the Python suite (654
tests, 80 skipped: Windows assets and the Windows-only launcher and capture tools). The Python tests run with the resolved temporary folder
(`/private/var/...`): the tools refuse paths with a linked ancestor, and macOS reaches `/var` through a link.

## Troubleshooting

| Message | Fix |
|---|---|
| `Vulkan loader unavailable` | `brew install vulkan-loader molten-vk`; `vulkaninfo --summary` (from `vulkan-tools`) must list the Apple GPU |
| `missing donor checkout` or a donor pin mismatch | clone the donor again with `-c core.autocrlf=true` (a LF checkout differs from every pin) |
| `... holds [...], expected [...]` | a capsule folder holds an extra file (the checks ignore Finder's `.DS_Store` only): delete the folder, the next build derives it again |
| `Cannot exclusively lock game memory card` | another game session uses the card; close it first |
| `GT4_RENDERER=pcsx2 needs GT4_GS_PROCESS` or `missing GS process` | build `gt4-gs` ([PCSX2 GS renderer](#pcsx2-gs-renderer-gt4-gs)) or start without `--renderer pcsx2` |
| `cannot execute tool 'metal' due to missing Metal Toolchain` (building `gt4-gs`) | `xcodebuild -downloadComponent MetalToolchain` |
