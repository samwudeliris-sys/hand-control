"""Virtual cursor state machine for cross-machine edge crossing.

The phone sends us raw ``(dx, dy)`` mouse deltas. We maintain a
virtual cursor position that spans both the Mac and the PC screen
(concatenated along whichever axis the user configured). When that
virtual position enters the PC's region, we start routing events to
the PC peer instead of the local Mac cursor.

Why track virtual position instead of reading each machine's live
cursor? Two reasons:

1. Polling the live cursor in two places and diffing is racy; the
   phone might send several deltas before we've synced.
2. It makes the "park the cursor at the boundary" behavior
   deterministic — we always know exactly which pixel to warp to.

Layout convention: we model the two screens as rectangles in a
shared virtual coordinate space. Let MW, MH be Mac primary size
and PW, PH be PC primary size:

    side='right'  →  Mac at (0..MW,   0..MH),  PC at (MW..MW+PW, 0..PH)
    side='left'   →  PC  at (0..PW,   0..PH),  Mac at (PW..PW+MW, 0..MH)
    side='above'  →  PC  at (0..PW,   0..PH),  Mac at (0..MW,    PH..PH+MH)
    side='below'  →  Mac at (0..MW,   0..MH),  PC at (0..PW,     MH..MH+PH)

We align screens at the top/left edge — good enough for v1. A
future enhancement could offset them based on a user-configured
y (or x) origin so a small Mac next to a tall PC feels natural.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Host = Literal["mac", "pc"]
Side = Literal["left", "right", "above", "below"]


@dataclass
class ScreenLayout:
    mac_w: int
    mac_h: int
    pc_w: int
    pc_h: int
    side: Side

    @property
    def horizontal(self) -> bool:
        return self.side in ("left", "right")

    # --- region boundaries ---------------------------------------------------

    def mac_box(self) -> tuple[int, int, int, int]:
        """(x0, y0, x1, y1) for Mac screen in virtual coords."""
        if self.side == "right":
            return (0, 0, self.mac_w, self.mac_h)
        if self.side == "left":
            return (self.pc_w, 0, self.pc_w + self.mac_w, self.mac_h)
        if self.side == "above":
            return (0, self.pc_h, self.mac_w, self.pc_h + self.mac_h)
        # below
        return (0, 0, self.mac_w, self.mac_h)

    def pc_box(self) -> tuple[int, int, int, int]:
        if self.side == "right":
            return (self.mac_w, 0, self.mac_w + self.pc_w, self.pc_h)
        if self.side == "left":
            return (0, 0, self.pc_w, self.pc_h)
        if self.side == "above":
            return (0, 0, self.pc_w, self.pc_h)
        # below
        return (0, self.mac_h, self.pc_w, self.mac_h + self.pc_h)


@dataclass
class VirtualCursor:
    """Owns the virtual cursor position and the current active host."""

    x: float
    y: float
    host: Host
    layout: ScreenLayout

    @classmethod
    def centered_on_mac(cls, layout: ScreenLayout) -> "VirtualCursor":
        mx0, my0, mx1, my1 = layout.mac_box()
        return cls(x=(mx0 + mx1) / 2, y=(my0 + my1) / 2, host="mac", layout=layout)

    def apply_delta(self, dx: float, dy: float) -> tuple[Host, float, float]:
        """Update the virtual position by ``(dx, dy)`` and return
        ``(new_host, local_x, local_y)`` where local_* is the
        screen-local pixel coordinate on the new host.

        Crosses are detected by comparing the old host's region
        against the new virtual position. The virtual position is
        clamped to the combined layout so you can't drift infinitely
        past an edge (that would make it feel unresponsive coming
        back).
        """
        self.x += dx
        self.y += dy

        L = self.layout
        mx0, my0, mx1, my1 = L.mac_box()
        px0, py0, px1, py1 = L.pc_box()

        # Combined bounding box, used for clamping.
        bx0 = min(mx0, px0)
        by0 = min(my0, py0)
        bx1 = max(mx1, px1)
        by1 = max(my1, py1)
        self.x = max(bx0, min(bx1 - 1, self.x))
        self.y = max(by0, min(by1 - 1, self.y))

        # Which host owns the new position?
        in_mac = mx0 <= self.x < mx1 and my0 <= self.y < my1
        in_pc = px0 <= self.x < px1 and py0 <= self.y < py1

        if in_mac:
            new_host: Host = "mac"
        elif in_pc:
            new_host = "pc"
        else:
            # Fell in the dead-zone (e.g. screens of different
            # heights with an L-shape gap). Stay on the current host
            # and clamp the out-of-range axis to its region.
            new_host = self.host

        # Clamp the OUT axis to the new host's region so parked
        # cursors don't try to warp to invalid rows/cols.
        if new_host == "mac":
            local_x = int(self.x - mx0)
            local_y = int(max(0, min(my1 - my0 - 1, self.y - my0)))
        else:
            local_x = int(self.x - px0)
            local_y = int(max(0, min(py1 - py0 - 1, self.y - py0)))

        crossed = new_host != self.host
        self.host = new_host
        _ = crossed  # retained for future: we could return it too
        return new_host, local_x, local_y

    def seed_from_mac_cursor(self, local_x: int, local_y: int) -> None:
        """Sync the virtual position to the real Mac cursor location.

        Called at startup so the first phone stroke doesn't fling the
        cursor halfway across the virtual canvas.
        """
        mx0, my0, _, _ = self.layout.mac_box()
        self.x = mx0 + local_x
        self.y = my0 + local_y
        self.host = "mac"

    # Convenience for the handoff warps ----------------------------------

    def mac_edge_on_cross_from_pc(self) -> tuple[int, int]:
        """Mac-local pixel to warp to when cursor returns from PC."""
        mx0, my0, mx1, my1 = self.layout.mac_box()
        if self.layout.side == "left":   # coming from PC (on left)
            return (1, int(max(0, min(my1 - my0 - 1, self.y - my0))))
        if self.layout.side == "right":
            return (mx1 - mx0 - 2, int(max(0, min(my1 - my0 - 1, self.y - my0))))
        if self.layout.side == "above":
            return (int(max(0, min(mx1 - mx0 - 1, self.x - mx0))), 1)
        return (int(max(0, min(mx1 - mx0 - 1, self.x - mx0))), my1 - my0 - 2)

    def pc_edge_on_cross_from_mac(self) -> tuple[int, int]:
        """PC-local pixel to warp to when cursor enters PC."""
        px0, py0, px1, py1 = self.layout.pc_box()
        if self.layout.side == "left":
            return (px1 - px0 - 2, int(max(0, min(py1 - py0 - 1, self.y - py0))))
        if self.layout.side == "right":
            return (1, int(max(0, min(py1 - py0 - 1, self.y - py0))))
        if self.layout.side == "above":
            return (int(max(0, min(px1 - px0 - 1, self.x - px0))), py1 - py0 - 2)
        return (int(max(0, min(px1 - px0 - 1, self.x - px0))), 1)
