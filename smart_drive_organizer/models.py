from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Tuple


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
class DiscoveryGroup:
    """A recurring filename pattern found across distinct files."""
    phrase: str
    suggested_name: str
    category: str
    file_count: int
    sample_files: List[str] = field(default_factory=list)
    sample_locations: List[str] = field(default_factory=list)


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
    discovery_candidates: List[Tuple[Path, str]] = field(default_factory=list)
    discovery_groups: List[DiscoveryGroup] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.source_roots:
            self.source_roots = [self.source_root]

    @property
    def total_bytes(self) -> int:
        return sum(item.size_bytes for item in self.files)
