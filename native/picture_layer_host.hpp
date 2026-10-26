// SPDX-License-Identifier: MIT
// macOS, GT4_RENDERER=pcsx2: the GS process's picture in the game window (window_sdl.cpp).
//
// A macOS process cannot put a view inside another process's window, so the GS process (gt4-gs) renders into a remote
// Core Animation context and answers CONTROL attach_window with its id (gs_stream::WindowPayload::layer_id, read through
// gs_stream::picture_layer_id). This host shows that context in a CALayerHost over the window's Metal layer. The remote
// layer is sized in pixels with one point per pixel, so the host is scaled by the inverse of the backing scale: the
// picture covers the window with one picture pixel per screen pixel. Every function runs on the main thread.
#pragma once

#include <cstdint>

namespace gt4::picture_host {

// The window's Metal layer (SDL_Metal_GetLayer), black until the picture shows.
void prepare(void *metal_layer);
// Shows the remote context over the Metal layer; false when a picture is already shown or nothing was prepared.
bool show(std::uint32_t context_id);
// The window's picture size in pixels and its backing scale (pixels per point).
void resize(std::uint32_t pixel_width, std::uint32_t pixel_height, double scale);
bool shown();
// Removes the picture before the Metal layer goes away.
void release();

// Test aid (GT4_WINDOW_CAPTURE_DIR): writes the window (an NSWindow, SDL_PROP_WINDOW_COCOA_WINDOW_POINTER) as the
// WindowServer composed it to a PNG file. A process may read its own windows this way without the screen recording
// permission. Any renderer.
bool capture_window(void *ns_window, const char *png_path);

}  // namespace gt4::picture_host
