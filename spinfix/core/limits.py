# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Vigesh
"""Every safety limit in one place.

Changing any value here needs Vigesh's approval (CLAUDE.md §4.6).
"""

from __future__ import annotations

from dataclasses import dataclass

KB = 1024
MB = 1024 * KB
GB = 1024 * MB


@dataclass(frozen=True, slots=True)
class Limits:
    # Images
    max_image_pixels: int = 180_000_000  # 180 MP; Pillow refuses anything larger

    # PDFs
    max_pdf_pages: int = 2_000
    max_render_dpi: int = 600
    max_render_pixels: int = 60_000_000  # per rendered page

    # Archives
    max_archive_total_bytes: int = 10 * GB
    max_archive_ratio_total: int = 50  # total uncompressed <= 50 x input size
    max_archive_entries: int = 100_000
    max_archive_entry_ratio: int = 1_000  # per entry, uncompressed / compressed
    free_space_margin_bytes: int = 200 * MB

    # Jobs and files
    job_timeout_seconds: float = 30 * 60
    external_tool_timeout_seconds: float = 6 * 60 * 60
    batch_confirm_above: int = 500
    max_input_bytes: int = 20 * GB
    max_path_length: int = 259  # MAX_PATH - 1 (no long-path opt-in)

    # IPC
    ipc_max_message_bytes: int = 64 * KB

    def archive_size_cap(self, input_bytes: int) -> int:
        """Total uncompressed cap: 10 GB or 50 x input, whichever is smaller."""
        return min(self.max_archive_total_bytes, max(input_bytes, 1) * self.max_archive_ratio_total)


DEFAULT_LIMITS = Limits()
