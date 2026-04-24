from __future__ import annotations

import argparse
from datetime import datetime
import os
import sys

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("SpiceClientGtk", "3.0")
gi.require_version("SpiceClientGLib", "2.0")

from gi.repository import GLib, Gtk, SpiceClientGLib, SpiceClientGtk


DEFAULT_TITLE = "vm-display"
DEFAULT_URI = "spice://127.0.0.1:5930"
DEBUG = os.environ.get("VM_DISPLAY_DEBUG", "") not in ("", "0", "false", "False")


def debug(msg: str) -> None:
    if DEBUG:
        ts = datetime.now().isoformat(timespec="seconds")
        print(f"[vm-display {ts}] {msg}", file=sys.stderr, flush=True)


class VMDisplayWindow(Gtk.Window):
    def __init__(self, uri: str, title: str = DEFAULT_TITLE):
        super().__init__(title=title)
        self.set_default_size(1600, 900)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_decorated(False)
        self.connect("destroy", self._on_destroy)

        self.uri = uri
        self.session = SpiceClientGLib.Session.new()
        self.session.set_property("uri", uri)
        self.session.connect_after("channel-new", self._on_channel_new)

        self.display: SpiceClientGtk.Display | None = None
        self.connected_channels: dict[int, SpiceClientGLib.Channel] = {}

        self.display_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.display_box.set_hexpand(True)
        self.display_box.set_vexpand(True)
        self.add(self.display_box)

        self.show_all()
        GLib.idle_add(self._initial_present)
        self.status("Opening session…")
        ok = self.session.connect()
        debug(f"session.connect -> {ok}")

    def _initial_present(self) -> bool:
        debug("initial_present")
        try:
            self.present()
            self.show_all()
        except Exception as exc:
            debug(f"initial_present exception: {exc!r}")
        return False

    def status(self, text: str) -> None:
        debug(f"status: {text}")

    def _install_display(self, channel_id: int) -> None:
        if self.display is not None:
            return

        debug(f"install display channel_id={channel_id}")
        display = SpiceClientGtk.Display.new(self.session, channel_id)
        display.set_hexpand(True)
        display.set_vexpand(True)
        display.set_can_focus(True)
        display.set_property("resize-guest", True)
        display.set_property("scaling", True)
        display.set_property("grab-keyboard", False)
        display.set_property("grab-mouse", False)
        display.connect("button-press-event", self._on_display_button_press)

        self.display = display
        self.display_box.pack_start(display, True, True, 0)
        display.connect("focus-in-event", lambda *_args: debug("display focus-in") or False)
        display.connect("focus-out-event", lambda *_args: debug("display focus-out") or False)
        display.connect("key-press-event", self._on_display_key_press)
        display.connect("key-release-event", self._on_display_key_release)

        self.display_box.show_all()
        self.status("Display ready.")

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

    def _on_display_button_press(self, widget, event) -> bool:
        debug(f"button-press button={getattr(event, 'button', '?')} x={getattr(event, 'x', '?')} y={getattr(event, 'y', '?')}")
        widget.grab_focus()
        return False

    def _on_display_key_press(self, _widget, event) -> bool:
        debug(f"key-press keyval={getattr(event, 'keyval', '?')} hardware_keycode={getattr(event, 'hardware_keycode', '?')} state={getattr(event, 'state', '?')}")
        return False

    def _on_display_key_release(self, _widget, event) -> bool:
        debug(f"key-release keyval={getattr(event, 'keyval', '?')} hardware_keycode={getattr(event, 'hardware_keycode', '?')} state={getattr(event, 'state', '?')}")
        return False

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
