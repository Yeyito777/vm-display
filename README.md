# vm-display

A minimal SPICE display client for local VMs.

Goals:
- keep the good SPICE/QXL resolution and rendering path
- remove UI clutter
- stay simple and easy to iterate on outside virt-viewer/remote-viewer
- leave window locking / focus pinning to the window manager layer

Current stack:
- Python 3
- GTK 3 via PyGObject
- spice-gtk / spice-client-glib

Current behavior:
- connect to a SPICE URI
- open as an undecorated display window
- resize/scale with the guest through SPICE/QXL
- no built-in keyboard/mouse lock toggle logic
- pair with the window manager's lock behavior if you want the window pinned

## Run

Normal day-to-day Windows VM usage is through vm-cli:

```bash
vm start windows
```

Standalone viewer only:

```bash
python -m vm_display --uri spice://127.0.0.1:5930
```

Or:

```bash
./scripts/run-local-windows.sh
```

For local vm-display development against the Windows VM profile:

```bash
./scripts/launch-windows.sh
```

That helper now starts or reuses a headless `vm` session and then attaches `vm-display` directly.
