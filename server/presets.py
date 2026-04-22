"""Preset prompts — one-tap shortcuts that type canned text into the
currently-focused Cursor window.

Load order:
  1. ``$HC_PRESETS_PATH`` env var, if set, must point at a JSON file.
  2. ``presets.json`` in the repo root (gitignored — edit freely).
  3. Built-in defaults below.

Each preset is an object with:
  - ``id``      (str, optional): stable identifier. Auto-generated from
                label if omitted.
  - ``label``   (str, required): short text shown on the phone button.
  - ``text``    (str, required): string to type into the focused field.
                May contain ``\\n`` — literal newlines are fine.
  - ``submit``  (str, optional): one of ``"queue"`` (Option+Enter — append
                to Cursor's agent queue — DEFAULT), ``"send"`` (plain
                Enter — submit immediately, may interrupt an active
                agent), or ``"none"`` (just type; user can keep editing).
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


REPO_ROOT = Path(__file__).resolve().parent.parent

# Baked-in defaults. Chosen to cover the most common "I wish I could do
# this without reaching for the keyboard" moments while vibe-coding.
# Users can override by creating ``presets.json`` in the repo root.
DEFAULT_PRESETS: list[dict] = [
    {
        "label": "Push",
        "text": "commit all changes with a clear, concise message and push to github",
        "submit": "queue",
    },
    {
        "label": "Continue",
        "text": "continue",
        "submit": "send",
    },
    {
        "label": "Fix",
        "text": "please fix it",
        "submit": "send",
    },
    {
        "label": "Tests",
        "text": "run the tests and fix any failures",
        "submit": "queue",
    },
    {
        "label": "Plan",
        "text": "before making changes, lay out a short step-by-step plan",
        "submit": "queue",
    },
    {
        "label": "Approve",
        "text": "y",
        "submit": "send",
    },
]

VALID_SUBMIT_MODES = {"queue", "send", "none"}


@dataclass
class Preset:
    id: str
    label: str
    text: str
    submit: str  # "queue" | "send" | "none"

    def to_public_dict(self) -> dict:
        """Safe payload to send to the phone — omits ``text`` so preset
        contents aren't exposed to anyone who opens the page, and keeps
        the WebSocket payload small."""
        return {"id": self.id, "label": self.label, "submit": self.submit}


def _slugify(s: str) -> str:
    """Make a stable id from a label (e.g. 'Run tests' → 'run-tests')."""
    s = s.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "preset"


def _normalize(raw: list) -> list[Preset]:
    """Coerce the raw JSON list into a list of validated ``Preset``s.

    Invalid entries are skipped with a warning rather than raising —
    one malformed preset shouldn't break the whole feature.
    """
    out: list[Preset] = []
    used_ids: set[str] = set()

    if not isinstance(raw, list):
        print(f"[presets] expected a JSON list at top level, got {type(raw).__name__}")
        return out

    for i, entry in enumerate(raw):
        if not isinstance(entry, dict):
            print(f"[presets] skipping entry #{i}: not a JSON object")
            continue

        label = entry.get("label")
        text = entry.get("text")
        if not isinstance(label, str) or not label.strip():
            print(f"[presets] skipping entry #{i}: missing / empty 'label'")
            continue
        if not isinstance(text, str) or not text:
            print(f"[presets] skipping entry {label!r}: missing / empty 'text'")
            continue

        submit = entry.get("submit", "queue")
        if submit not in VALID_SUBMIT_MODES:
            print(
                f"[presets] preset {label!r}: invalid submit {submit!r}, "
                f"falling back to 'queue' (valid: {sorted(VALID_SUBMIT_MODES)})"
            )
            submit = "queue"

        raw_id = entry.get("id")
        preset_id = (
            raw_id.strip()
            if isinstance(raw_id, str) and raw_id.strip()
            else _slugify(label)
        )
        # De-duplicate ids so the phone can use them as React-style keys.
        base_id = preset_id
        n = 2
        while preset_id in used_ids:
            preset_id = f"{base_id}-{n}"
            n += 1
        used_ids.add(preset_id)

        out.append(Preset(id=preset_id, label=label.strip(), text=text, submit=submit))

    return out


def _load_from_file(path: Path) -> Optional[list[Preset]]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except json.JSONDecodeError as exc:
        print(f"[presets] {path} is not valid JSON: {exc}")
        return None
    except OSError as exc:
        print(f"[presets] could not read {path}: {exc}")
        return None
    return _normalize(raw)


def load_presets() -> list[Preset]:
    """Resolve presets from env override → repo-root file → defaults."""
    env_path = os.environ.get("HC_PRESETS_PATH", "").strip()
    if env_path:
        p = Path(env_path).expanduser()
        loaded = _load_from_file(p)
        if loaded is not None:
            print(f"[presets] loaded {len(loaded)} from {p} (via HC_PRESETS_PATH)")
            return loaded
        print(f"[presets] HC_PRESETS_PATH={env_path} could not be loaded, falling back")

    local = REPO_ROOT / "presets.json"
    loaded = _load_from_file(local)
    if loaded is not None:
        print(f"[presets] loaded {len(loaded)} from {local}")
        return loaded

    print(f"[presets] using {len(DEFAULT_PRESETS)} built-in defaults")
    return _normalize(DEFAULT_PRESETS)
