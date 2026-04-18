from __future__ import annotations

import argparse
import os
import sys

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("SpiceClientGtk", "3.0")
gi.require_version("SpiceClientGLib", "2.0")

from gi.repository import Gdk, GLib, Gtk, SpiceClientGLib, SpiceClientGtk


DEFAULT_TITLE = "vm-display"
DEFAULT_URI = "spice://127.0.0.1:5930"
TOGGLE_ACCEL = "Control_L+Shift_L+space"
DEBUG = os.environ.get("VM_DISPLAY_DEBUG", "") not in ("", "0", "false", "False")


def debug(msg: str) -> None:
    if DEBUG:
        print(f"[vm-display] {msg}", file=sys.stderr, flush=True)


class VMDisplayWindow(Gtk.Window):
    def __init__(self, uri: str, title: str = DEFAULT_TITLE):
        super().__init__(title=title)
        self.set_default_size(1600, 900)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.connect("destroy", self._on_destroy)
        self.connect("key-press-event", self._on_window_key_press)
        self.connect("map-event", self._on_map_event)

        self.uri = uri
        self.session = SpiceClientGLib.Session.new()
        self.session.set_property("uri", uri)
        self.session.connect_after("channel-new", self._on_channel_new)

        self.display: SpiceClientGtk.Display | None = None
        self.captured = False
        self.connected_channels: dict[int, SpiceClientGLib.Channel] = {}

        self.header = Gtk.HeaderBar()
        self.header.set_show_close_button(True)
        self.header.props.title = title
        self.header.props.subtitle = uri
        self.set_titlebar(self.header)

        self.capture_label = Gtk.Label(label="HOST")
        self.header.pack_start(self.capture_label)

        self.release_button = Gtk.Button(label="Release")
        self.release_button.connect("clicked", lambda *_: self.release_input())
        self.header.pack_end(self.release_button)

        self.status_label = Gtk.Label(label="Connecting…")
        self.status_label.set_xalign(0.0)

        self.root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add(self.root)

        self.display_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.display_box.set_hexpand(True)
        self.display_box.set_vexpand(True)

        self.root.pack_start(self.display_box, True, True, 0)
        self.root.pack_end(self.status_label, False, False, 6)

        self.show_all()
        GLib.idle_add(self._initial_present)
        self.status("Opening session…")
        ok = self.session.connect()
        debug(f"session.connect -> {ok}")

    def _initial_present(self) -> bool:
        debug("initial_present")
        try:
            self.move(80, 80)
            self.present()
            self.show_all()
        except Exception as exc:
            debug(f"initial_present exception: {exc!r}")
        return False

    def _on_map_event(self, *_args) -> bool:
        debug("map-event")
        return False

    def status(self, text: str) -> None:
        debug(f"status: {text}")
        self.status_label.set_text(text)

    def set_capture_state(self, captured: bool) -> None:
        self.captured = captured
        self.capture_label.set_text("GUEST" if captured else "HOST")
        if self.display is not None:
            self.display.set_property("grab-keyboard", captured)
            self.display.set_property("grab-mouse", captured)
            if captured:
                self.display.grab_focus()
            else:
                try:
                    self.display.keyboard_ungrab()
                except Exception:
                    pass
                try:
                    self.display.mouse_ungrab()
                except Exception:
                    pass

    def release_input(self) -> None:
        self.set_capture_state(False)
        self.status("Released guest input")

    def capture_input(self) -> None:
        self.set_capture_state(True)
        self.status("Captured guest input")

    def toggle_input(self) -> None:
        if self.captured:
            self.release_input()
        else:
            self.capture_input()

    def _install_display(self, channel_id: int) -> None:
        if self.display is not None:
            return

        debug(f"install display channel_id={channel_id}")
        display = SpiceClientGtk.Display.new(self.session, channel_id)
        display.set_hexpand(True)
        display.set_vexpand(True)
        display.set_property("resize-guest", True)
        display.set_property("scaling", True)
        display.set_property("grab-keyboard", False)
        display.set_property("grab-mouse", False)
        display.set_grab_keys(SpiceClientGtk.GrabSequence.new_from_string(TOGGLE_ACCEL))
        display.connect("button-press-event", self._on_display_button_press)
        display.connect("grab-broken-event", self._on_grab_broken)
        display.connect("grab-notify", self._on_grab_notify)
        display.connect("key-press-event", self._on_display_key_press)

        self.display = display
        self.display_box.pack_start(display, True, True, 0)
        self.display_box.show_all()
        self.set_capture_state(False)
        self.status("Display ready. Click inside to capture. Ctrl+Shift+Space toggles guest input.")

    def _on_channel_new(self, _session, channel) -> None:
        channel_id = channel.get_property("channel-id")
        debug(f"channel_new type={channel.__gtype__.name} id={channel_id}")
        self.connected_channels[channel_id] = channel
        typename = channel.__gtype__.name
        self.status(f"Channel connected: {typename} #{channel_id}")
        if isinstance(channel, SpiceClientGLib.DisplayChannel):
            self._install_display(channel_id)
        elif isinstance(channel, SpiceClientGLib.MainChannel):
            channel.connect_after("notify::mouse-mode", self._on_main_mouse_mode)
            channel.connect_after("notify::agent-connected", self._on_main_agent_connected)

    def _on_main_mouse_mode(self, channel, _pspec) -> None:
        try:
            mode = channel.get_property("mouse-mode")
        except Exception:
            mode = "?"
        self.status(f"Mouse mode: {mode}")

    def _on_main_agent_connected(self, channel, _pspec) -> None:
        try:
            connected = channel.get_property("agent-connected")
        except Exception:
            connected = "?"
        self.status(f"Agent connected: {connected}")

    def _on_display_button_press(self, _widget, _event) -> bool:
        if not self.captured:
            self.capture_input()
        return False

    def _on_grab_broken(self, *_args) -> bool:
        self.set_capture_state(False)
        self.status("Grab broken; back to host input")
        return False

    def _on_grab_notify(self, widget, was_grabbed) -> None:
        has_grab = False
        try:
            has_grab = bool(widget.has_grab())
        except Exception:
            pass
        if not has_grab and self.captured:
            self.set_capture_state(False)
            self.status("Grab notify: host input")

    def _on_display_key_press(self, _widget, event: Gdk.EventKey) -> bool:
        if self._is_toggle_accel(event):
            self.toggle_input()
            return True
        return False

    def _on_window_key_press(self, _widget, event: Gdk.EventKey) -> bool:
        if self._is_toggle_accel(event):
            self.toggle_input()
            return True
        if event.keyval == Gdk.KEY_Escape and not self.captured:
            self.close()
            return True
        return False

    def _is_toggle_accel(self, event: Gdk.EventKey) -> bool:
        ctrl = bool(event.state & Gdk.ModifierType.CONTROL_MASK)
        shift = bool(event.state & Gdk.ModifierType.SHIFT_MASK)
        alt = bool(event.state & Gdk.ModifierType.MOD1_MASK)
        return ctrl and shift and not alt and event.keyval == Gdk.KEY_space

    def _on_destroy(self, *_args) -> None:
        debug("destroy")
        try:
            self.session.disconnect()
        except Exception as exc:
            debug(f"session.disconnect exception: {exc!r}")
        Gtk.main_quit()


def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Minimal SPICE display client")
    p.add_argument("--uri", default=DEFAULT_URI, help="SPICE URI (default: %(default)s)")
    p.add_argument("--title", default=DEFAULT_TITLE, help="Window title")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_argparser().parse_args(argv)
    win = VMDisplayWindow(uri=args.uri, title=args.title)
    win.show_all()
    Gtk.main()
    return 0
