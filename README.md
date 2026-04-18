# vm-display

A minimal SPICE display client for local VMs.

Goals:
- keep the good SPICE/QXL resolution and rendering path
- remove UI clutter
- make keyboard/mouse capture deterministic
- iterate quickly outside of virt-viewer/remote-viewer

Current MVP stack:
- Python 3
- GTK 3 via PyGObject
- spice-gtk / spice-client-glib

Current behavior:
- connect to a SPICE URI
- show one display window
- no automatic keyboard/mouse grab on mere focus/hover
- explicit click-to-capture
- `Ctrl+Shift+Space` toggles guest input
- `Release` button returns input to host

## Run

```bash
python -m vm_display --uri spice://127.0.0.1:5930
```

Or:

```bash
./scripts/run-local-windows.sh
```

For the Windows VM helper launcher:

```bash
./scripts/launch-windows.sh
```
