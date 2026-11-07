# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Vigesh
"""Actions, one module per group (images, pdf, media, archive, ocr, share)."""

from __future__ import annotations

from spinfix.core.registry import Registry


def build_registry() -> Registry:
    """A registry with every built-in action."""
    from spinfix.actions import archive, images, media, ocr, pdf, share  # noqa: PLC0415

    registry = Registry()
    for module in (images, pdf, media, archive, ocr, share):
        module.register(registry)
    return registry
