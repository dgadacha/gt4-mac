// SPDX-License-Identifier: MIT
// macOS: see picture_layer_host.hpp. Objective-C++ built with ARC (native/CMakeLists.txt).
#import "picture_layer_host.hpp"

#import <AppKit/AppKit.h>
#import <ImageIO/ImageIO.h>
#import <QuartzCore/QuartzCore.h>

#include <cstring>
#include <dlfcn.h>

// Private Core Animation interface, declared as Chromium declares it for the same purpose
// (ui/base/cocoa/remote_layer_api.h): a layer that shows a CAContext of another process of the same login session.
@interface CALayerHost : CALayer
@property uint32_t contextId;
@end

namespace {

CALayer *g_parent = nil;
CALayerHost *g_host = nil;
std::uint32_t g_width = 1, g_height = 1;
double g_scale = 1.0;

// The host spans the remote layer's pixels and is scaled to the window's points, anchored at the origin.
void apply_geometry() {
  [CATransaction begin];
  [CATransaction setDisableActions:YES];
  g_host.anchorPoint = CGPointZero;
  g_host.position = CGPointZero;
  g_host.bounds = CGRectMake(0, 0, g_width, g_height);
  g_host.transform = CATransform3DMakeScale(1.0 / g_scale, 1.0 / g_scale, 1.0);
  [CATransaction commit];
  [CATransaction flush];
}

}  // namespace

void gt4::picture_host::prepare(void *metal_layer) {
  g_parent = (__bridge CALayer *)metal_layer;
  [CATransaction begin];
  [CATransaction setDisableActions:YES];
  g_parent.backgroundColor = CGColorGetConstantColor(kCGColorBlack);
  [CATransaction commit];
}

bool gt4::picture_host::show(std::uint32_t context_id) {
  if (g_host || !g_parent || !context_id)
    return false;
  g_host = [CALayerHost layer];
  g_host.contextId = context_id;
  [CATransaction begin];
  [CATransaction setDisableActions:YES];
  [g_parent addSublayer:g_host];
  [CATransaction commit];
  apply_geometry();
  return true;
}

void gt4::picture_host::resize(std::uint32_t pixel_width, std::uint32_t pixel_height, double scale) {
  g_width = pixel_width ? pixel_width : 1;
  g_height = pixel_height ? pixel_height : 1;
  g_scale = scale > 0.0 ? scale : 1.0;
  if (g_host)
    apply_geometry();
}

bool gt4::picture_host::shown() { return g_host != nil; }

double gt4::picture_host::edr_headroom() { return [[NSScreen mainScreen] maximumExtendedDynamicRangeColorComponentValue]; }

bool gt4::picture_host::window_visible(void *ns_window) {
  return ([(__bridge NSWindow *)ns_window occlusionState] & NSWindowOcclusionStateVisible) != 0;
}

void gt4::picture_host::release() {
  if (g_host) {
    [CATransaction begin];
    [CATransaction setDisableActions:YES];
    [g_host removeFromSuperlayer];
    [CATransaction commit];
  }
  g_host = nil;
  g_parent = nil;
}

bool gt4::picture_host::capture_window(void *ns_window, const char *png_path) {
  const auto window_number = static_cast<std::uint32_t>([(__bridge NSWindow *)ns_window windowNumber]);
  // CGWindowListCreateImage is marked unavailable by the SDK (ScreenCaptureKit replaces it) but still answers for the
  // caller's own windows; it is looked up at run time.
  using CreateImage = CGImageRef (*)(CGRect, std::uint32_t, std::uint32_t, std::uint32_t);
  static const auto create = reinterpret_cast<CreateImage>(dlsym(RTLD_DEFAULT, "CGWindowListCreateImage"));
  constexpr std::uint32_t kIncludingWindow = 8, kBoundsIgnoreFraming = 1;
  CGImageRef image = create ? create(CGRectNull, kIncludingWindow, window_number, kBoundsIgnoreFraming) : nullptr;
  if (!image)
    return false;
  CFURLRef url = CFURLCreateFromFileSystemRepresentation(nullptr, reinterpret_cast<const UInt8 *>(png_path),
                                                         static_cast<CFIndex>(std::strlen(png_path)), false);
  CGImageDestinationRef file = url ? CGImageDestinationCreateWithURL(url, CFSTR("public.png"), 1, nullptr) : nullptr;
  bool written = false;
  if (file) {
    CGImageDestinationAddImage(file, image, nullptr);
    written = CGImageDestinationFinalize(file);
    CFRelease(file);
  }
  if (url)
    CFRelease(url);
  CGImageRelease(image);
  return written;
}
