"""macOS menu bar app: ring gauges for Claude limits, reset times in the menu.

Menu bar shows two mini rings (session + weekly, percent inside) plus the
time until the 5-hour limit resets. The dropdown shows a large session donut
with the weekly limit as a thin outer arc, and one row per limit.
"""

import threading
import time
import webbrowser

import objc
from AppKit import (
    NSApplication, NSApplicationActivationPolicyAccessory,
    NSAttributedString, NSBezierPath, NSButton, NSColor, NSFont,
    NSFontAttributeName, NSForegroundColorAttributeName, NSImage, NSMakeRect,
    NSMenu, NSMenuItem, NSMutableParagraphStyle, NSParagraphStyleAttributeName,
    NSStatusBar, NSTextAlignmentCenter, NSTextAlignmentLeft,
    NSTextAlignmentRight, NSVariableStatusItemLength, NSView,
)
from Foundation import NSObject, NSTimer
from PyObjCTools import AppHelper

from .limits import (
    CredentialsNotFound, TokenRejected, UsageRateLimited,
    get_limits, reset_label, time_until,
)
from .update import CHECK_INTERVAL_SECONDS, RELEASES_URL, available_update

REFRESH_SECONDS = 60
MENU_WIDTH = 264
RATE_LIMIT_ERROR = "Usage API rate-limited — showing last known data"
DONATE_URL = "https://base.monobank.ua/tilbertbalaban"
USAGE_URL = "https://claude.ai/settings/usage"

GREEN = NSColor.systemGreenColor()
PURPLE = NSColor.systemPurpleColor()
ORANGE = NSColor.systemOrangeColor()
RED = NSColor.systemRedColor()


def ring_color(limit):
    if limit.exhausted:
        return RED
    if limit.warning:
        return ORANGE
    return GREEN if limit.kind == "session" else PURPLE


def draw_ring(center, radius, line_width, percent, color, track_color):
    track = NSBezierPath.bezierPath()
    track.appendBezierPathWithArcWithCenter_radius_startAngle_endAngle_(
        center, radius, 0, 360)
    track.setLineWidth_(line_width)
    track_color.setStroke()
    track.stroke()
    fraction = min(max(percent, 0), 100) / 100.0
    if fraction <= 0:
        return
    arc = NSBezierPath.bezierPath()
    # Start at 12 o'clock and sweep clockwise, like a countdown dial.
    arc.appendBezierPathWithArcWithCenter_radius_startAngle_endAngle_clockwise_(
        center, radius, 90, 90 - 360 * fraction, True)
    arc.setLineWidth_(line_width)
    arc.setLineCapStyle_(1)  # round
    color.setStroke()
    arc.stroke()


def text_attrs(size, color, bold=False, align=NSTextAlignmentCenter):
    style = NSMutableParagraphStyle.alloc().init()
    style.setAlignment_(align)
    font = NSFont.boldSystemFontOfSize_(size) if bold else NSFont.systemFontOfSize_(size)
    return {
        NSFontAttributeName: font,
        NSForegroundColorAttributeName: color,
        NSParagraphStyleAttributeName: style,
    }


def draw_text(text, rect, attrs):
    s = NSAttributedString.alloc().initWithString_attributes_(text, attrs)
    h = s.size().height
    s.drawInRect_(NSMakeRect(rect.origin.x,
                             rect.origin.y + (rect.size.height - h) / 2.0,
                             rect.size.width, h))


def status_bar_image(limits, dark):
    """Two mini rings with the percent inside, like the reference app."""
    size = 18
    gap = 3
    count = max(len(limits), 1)
    img = NSImage.alloc().initWithSize_((count * size + (count - 1) * gap, 20))
    img.lockFocus()
    number_color = NSColor.whiteColor() if dark else NSColor.blackColor()
    track = (NSColor.whiteColor() if dark else NSColor.blackColor()).colorWithAlphaComponent_(0.18)
    for i, limit in enumerate(limits):
        x = i * (size + gap)
        center = (x + size / 2.0, 1 + size / 2.0)
        draw_ring(center, size / 2.0 - 1.5, 2.5, limit.percent, ring_color(limit), track)
        pct = round(limit.percent)
        label = "!" if pct >= 100 else str(pct)
        draw_text(label, NSMakeRect(x, 1, size, size),
                  text_attrs(7.5, number_color, bold=True))
    img.unlockFocus()
    return img


def _symbol_button(symbol, fallback, tooltip, target, action):
    image = NSImage.imageWithSystemSymbolName_accessibilityDescription_(
        symbol, tooltip)
    if image is not None:
        button = NSButton.buttonWithImage_target_action_(image, target, action)
    else:
        button = NSButton.buttonWithTitle_target_action_(fallback, target, action)
    button.setBordered_(False)
    button.setToolTip_(tooltip)
    return button


class HeaderView(NSView):
    """App title with the donate ($) and refresh icon buttons on the right."""

    def initWithTarget_(self, target):
        self = objc.super(HeaderView, self).initWithFrame_(
            NSMakeRect(0, 0, MENU_WIDTH, 38))
        if self is None:
            return None
        stats = _symbol_button("chart.bar.xaxis", "📊",
                               "Open claude.ai usage stats", target, "openUsage:")
        stats.setFrame_(NSMakeRect(MENU_WIDTH - 100, 7, 26, 24))
        self.addSubview_(stats)
        donate = _symbol_button("dollarsign.circle", "$",
                                "Support the developer", target, "donate:")
        donate.setFrame_(NSMakeRect(MENU_WIDTH - 70, 7, 26, 24))
        self.addSubview_(donate)
        refresh = _symbol_button("arrow.clockwise", "↻",
                                 "Refresh", target, "refresh:")
        refresh.setFrame_(NSMakeRect(MENU_WIDTH - 40, 7, 26, 24))
        self.addSubview_(refresh)
        return self

    def drawRect_(self, rect):
        draw_text("✳ Claude Limits", NSMakeRect(16, 3, MENU_WIDTH - 120, 32),
                  text_attrs(14, NSColor.labelColor(), bold=True,
                             align=NSTextAlignmentLeft))


class DonutView(NSView):
    """Large session donut with the weekly limit as a thin outer arc."""

    def initWithLimits_(self, limits):
        self = objc.super(DonutView, self).initWithFrame_(
            NSMakeRect(0, 0, MENU_WIDTH, 170))
        if self is None:
            return None
        self._limits = limits
        return self

    def drawRect_(self, rect):
        session = next((l for l in self._limits if l.kind == "session"), None)
        weekly = next((l for l in self._limits if l.kind == "weekly_all"), None)
        primary = session or (self._limits[0] if self._limits else None)
        if primary is None:
            return
        center = (MENU_WIDTH / 2.0, 85)
        track = NSColor.labelColor().colorWithAlphaComponent_(0.12)
        draw_ring(center, 62, 11, primary.percent, ring_color(primary), track)
        if weekly is not None:
            draw_ring(center, 74, 3.5, weekly.percent, ring_color(weekly),
                      NSColor.clearColor())
        draw_text("%d%%" % round(primary.percent),
                  NSMakeRect(0, 78, MENU_WIDTH, 40),
                  text_attrs(28, NSColor.labelColor(), bold=True))
        draw_text("Used", NSMakeRect(0, 54, MENU_WIDTH, 20),
                  text_attrs(12, NSColor.secondaryLabelColor()))


class LimitRowView(NSView):
    """Mini ring + limit name + reset time, like the reference app's rows."""

    def initWithLimit_(self, limit):
        self = objc.super(LimitRowView, self).initWithFrame_(
            NSMakeRect(0, 0, MENU_WIDTH, 36))
        if self is None:
            return None
        self._limit = limit
        return self

    def drawRect_(self, rect):
        bg = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
            NSMakeRect(10, 2, MENU_WIDTH - 20, 32), 8, 8)
        NSColor.labelColor().colorWithAlphaComponent_(0.06).setFill()
        bg.fill()
        limit = self._limit
        track = NSColor.labelColor().colorWithAlphaComponent_(0.15)
        draw_ring((20 + 9, 18), 7.5, 2.5, limit.percent, ring_color(limit), track)
        pct = round(limit.percent)
        draw_text("!" if pct >= 100 else str(pct), NSMakeRect(20, 9, 18, 18),
                  text_attrs(6.5, NSColor.labelColor(), bold=True))
        draw_text(limit.label, NSMakeRect(46, 2, 92, 32),
                  text_attrs(13, NSColor.secondaryLabelColor(),
                             align=NSTextAlignmentLeft))
        draw_text(reset_label(limit.resets_at), NSMakeRect(120, 2, MENU_WIDTH - 136, 32),
                  text_attrs(13, NSColor.labelColor(), bold=True,
                             align=NSTextAlignmentRight))


class ErrorRowView(NSView):
    """Fixed-width warning row so long messages never widen the menu."""

    def initWithMessage_(self, message):
        self = objc.super(ErrorRowView, self).initWithFrame_(
            NSMakeRect(0, 0, MENU_WIDTH, 34))
        if self is None:
            return None
        self._message = message
        return self

    def drawRect_(self, rect):
        attrs = text_attrs(11, NSColor.secondaryLabelColor(),
                           align=NSTextAlignmentLeft)
        NSAttributedString.alloc().initWithString_attributes_(
            "⚠️ " + self._message, attrs).drawInRect_(
            NSMakeRect(16, 2, MENU_WIDTH - 32, 30))


class StatusApp(NSObject):
    def applicationDidFinishLaunching_(self, _notification):
        self._limits = []
        self._error = None
        self._skip_ticks = 0
        self._update = None
        self._last_update_check = 0.0
        self.status_item = NSStatusBar.systemStatusBar().statusItemWithLength_(
            NSVariableStatusItemLength)
        self.status_item.button().setImagePosition_(2)  # NSImageLeft
        self.menu = NSMenu.alloc().init()
        self.status_item.setMenu_(self.menu)
        self._render()
        NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            REFRESH_SECONDS, self, "tick:", None, True)
        self.tick_(None)

    def tick_(self, _timer):
        if self._skip_ticks > 0:
            self._skip_ticks -= 1
            return
        threading.Thread(target=self._fetch, daemon=True).start()

    @objc.python_method
    def _fetch(self):
        if time.time() - self._last_update_check > CHECK_INTERVAL_SECONDS:
            self._last_update_check = time.time()
            self._update = available_update()
        limits, error = None, None
        try:
            limits = get_limits()
        except CredentialsNotFound:
            error = "No Claude Code credentials — run `claude` and sign in"
        except TokenRejected:
            error = "Token expired — use Claude Code once to refresh it"
        except UsageRateLimited:
            error = RATE_LIMIT_ERROR
        except Exception:
            error = "Could not reach api.anthropic.com"
        AppHelper.callAfter(self._apply, limits, error)

    @objc.python_method
    def _apply(self, limits, error):
        if limits is not None:
            self._limits = limits
        self._error = error
        # The usage endpoint has its own rate limit; poll gently after a 429.
        self._skip_ticks = 4 if error == RATE_LIMIT_ERROR else 0
        self._render()

    @objc.python_method
    def _render(self):
        button = self.status_item.button()
        bar_limits = [l for l in self._limits
                      if l.kind in ("session", "weekly_all")] or self._limits[:2]
        session = next((l for l in self._limits if l.kind == "session"), None)
        if bar_limits:
            dark = "dark" in str(button.effectiveAppearance().name()).lower()
            button.setImage_(status_bar_image(bar_limits, dark))
            button.setTitle_(" " + time_until(session.resets_at) if session else "")
        else:
            button.setImage_(None)
            button.setTitle_("✳ …" if self._error is None else "✳ ?")
        self._rebuild_menu()

    @objc.python_method
    def _rebuild_menu(self):
        self.menu.removeAllItems()
        header_item = NSMenuItem.alloc().init()
        header_item.setView_(HeaderView.alloc().initWithTarget_(self))
        self.menu.addItem_(header_item)
        if self._limits:
            donut_item = NSMenuItem.alloc().init()
            donut_item.setView_(DonutView.alloc().initWithLimits_(self._limits))
            self.menu.addItem_(donut_item)
            for limit in self._limits:
                row = NSMenuItem.alloc().init()
                row.setView_(LimitRowView.alloc().initWithLimit_(limit))
                self.menu.addItem_(row)
        if self._error:
            err = NSMenuItem.alloc().init()
            err.setView_(ErrorRowView.alloc().initWithMessage_(self._error))
            self.menu.addItem_(err)
        if self._update:
            self.menu.addItem_(NSMenuItem.separatorItem())
            self._add_action("Update available — v" + self._update, "openReleases:")
        self.menu.addItem_(NSMenuItem.separatorItem())
        self._add_action("Quit", "quit:")

    @objc.python_method
    def _add_action(self, title, selector):
        item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            title, selector, "")
        item.setTarget_(self)
        self.menu.addItem_(item)

    def refresh_(self, _sender):
        self._skip_ticks = 0
        self.tick_(None)

    def openUsage_(self, _sender):
        self.menu.cancelTracking()
        webbrowser.open(USAGE_URL)

    def donate_(self, _sender):
        self.menu.cancelTracking()
        webbrowser.open(DONATE_URL)

    def openReleases_(self, _sender):
        self.menu.cancelTracking()
        webbrowser.open(RELEASES_URL)

    def quit_(self, _sender):
        NSApplication.sharedApplication().terminate_(None)


def main():
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
    delegate = StatusApp.alloc().init()
    app.setDelegate_(delegate)
    AppHelper.runEventLoop()


if __name__ == "__main__":
    main()
