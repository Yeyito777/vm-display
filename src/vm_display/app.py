from __future__ import annotations

import argparse
from datetime import datetime
import os
import sys

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("SpiceClientGtk", "3.0")
gi.require_version("SpiceClientGLib", "2.0")

from gi.repository import Gdk, GLib, Gtk, SpiceClientGLib, SpiceClientGtk


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
        self.connect("focus-in-event", self._on_window_focus_in)
        self.connect("map-event", self._on_window_mapped)

        self.uri = uri
        self.session = SpiceClientGLib.Session.new()
        self.session.set_property("uri", uri)
        self.gtk_session = SpiceClientGtk.GtkSession.get(self.session)
        self.gtk_session.set_property("auto-clipboard", True)
        self.session.connect_after("channel-new", self._on_channel_new)

        self.display: SpiceClientGtk.Display | None = None
        self.connected_channels: dict[int, SpiceClientGLib.Channel] = {}
        self._paste_queue: list[int] = []
        self._paste_source_active = False
        self._paste_release_keyval: int | None = None

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
        GLib.idle_add(self._focus_display, "display-installed")
        self.status("Display ready.")

    def _focus_display(self, reason: str = "") -> bool:
        if self.display is not None:
            debug(f"focus display reason={reason}")
            try:
                self.display.grab_focus()
            except Exception as exc:
                debug(f"focus display failed: {exc!r}")
        return False

    def _on_window_focus_in(self, *_args) -> bool:
        debug("window focus-in")
        GLib.idle_add(self._focus_display, "window-focus-in")
        return False

    def _on_window_mapped(self, *_args) -> bool:
        debug("window mapped")
        GLib.idle_add(self._focus_display, "window-mapped")
        return False

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
        if self._is_host_paste_event(event):
            self._paste_release_keyval = int(event.keyval)
            GLib.timeout_add(100, self._paste_host_clipboard_as_keys)
            return True
        return False

    def _on_display_key_release(self, _widget, event) -> bool:
        debug(f"key-release keyval={getattr(event, 'keyval', '?')} hardware_keycode={getattr(event, 'hardware_keycode', '?')} state={getattr(event, 'state', '?')}")
        if self._paste_release_keyval is not None and int(event.keyval) == self._paste_release_keyval:
            self._paste_release_keyval = None
            return True
        return False

    def _is_host_paste_event(self, event) -> bool:
        state = int(getattr(event, "state", 0))
        keyval = int(getattr(event, "keyval", 0))
        ctrl = bool(state & int(Gdk.ModifierType.CONTROL_MASK))
        shift = bool(state & int(Gdk.ModifierType.SHIFT_MASK))
        return (ctrl and keyval in (Gdk.KEY_v, Gdk.KEY_V)) or (shift and keyval == Gdk.KEY_Insert)

    def _paste_host_clipboard_as_keys(self) -> bool:
        if self.display is None:
            return False
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        text = clipboard.wait_for_text() or ""
        if not text:
            debug("host paste requested but clipboard is empty")
            return False
        keyvals = self._text_to_keyvals(text)
        if not keyvals:
            debug("host paste requested but clipboard has no typeable keyvals")
            return False
        debug(f"host paste typing {len(keyvals)} keyvals from {len(text)} chars")
        self._release_paste_modifiers()
        self._paste_queue.extend(keyvals)
        if not self._paste_source_active:
            self._paste_source_active = True
            GLib.timeout_add(1, self._drain_paste_queue)
        return False

    def _release_paste_modifiers(self) -> None:
        if self.display is None:
            return
        for keyval in (Gdk.KEY_Control_L, Gdk.KEY_Control_R, Gdk.KEY_Shift_L, Gdk.KEY_Shift_R):
            try:
                self.display.send_keys([keyval], SpiceClientGtk.DisplayKeyEvent.RELEASE)
            except Exception as exc:
                debug(f"host paste modifier release failed: {exc!r}")

    def _text_to_keyvals(self, text: str) -> list[int]:
        keyvals: list[int] = []
        for ch in text:
            if ch == "\r":
                continue
            if ch == "\n":
                keyvals.append(Gdk.KEY_Return)
            elif ch == "\t":
                keyvals.append(Gdk.KEY_Tab)
            elif ch == "\b":
                keyvals.append(Gdk.KEY_BackSpace)
            else:
                keyval = Gdk.unicode_to_keyval(ord(ch))
                if keyval and keyval != Gdk.KEY_VoidSymbol:
                    keyvals.append(int(keyval))
        return keyvals

    def _drain_paste_queue(self) -> bool:
        if self.display is None:
            self._paste_queue.clear()
            self._paste_source_active = False
            return False
        for _ in range(min(8, len(self._paste_queue))):
            keyval = self._paste_queue.pop(0)
            try:
                self.display.send_keys([keyval], SpiceClientGtk.DisplayKeyEvent.CLICK)
            except Exception as exc:
                debug(f"host paste send_keys failed: {exc!r}")
                self._paste_queue.clear()
                self._paste_source_active = False
                return False
        if self._paste_queue:
            return True
        self._paste_source_active = False
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
