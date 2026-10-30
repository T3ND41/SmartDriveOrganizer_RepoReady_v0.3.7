from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List


@dataclass
class PlannedFile:
    source: Path
    category: str
    topic: str
    extension_folder: str
    destination: Path
    reason: str
    confidence: float
    size_bytes: int


@dataclass
class ScanPlan:
    source_root: Path
    output_root: Path
    selected_categories: List[str]
    files: List[PlannedFile] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    skipped_count: int = 0
    scanned_count: int = 0
    source_roots: List[Path] = field(default_factory=list)
    selected_extension_filters: Dict[str, List[str]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.source_roots:
            self.source_roots = [self.source_root]

    @property
    def total_bytes(self) -> int:
        return sum(item.size_bytes for item in self.files)
