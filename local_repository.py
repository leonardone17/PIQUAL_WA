from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

DISPLAY_SEQUENCES = ["T2_SAG", "T2_AX", "T2_COR", "DWI", "ADC", "DCE"]
SEQUENCE_ALIASES = {
    "DCE": ["DCE", "T1_CE", "T1CE"],
    "T2_SAG": ["T2_SAG", "T2-SAG"],
    "T2_AX": ["T2_AX", "T2-AX"],
    "T2_COR": ["T2_COR", "T2-COR"],
    "DWI": ["DWI"],
    "ADC": ["ADC"],
}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}


@dataclass
class CaseData:
    folder_name: str
    excel_prefix: str
    sequences: Dict[str, List[Path]]


class LocalCaseRepository:
    def __init__(self, root_dir: str | Path):
        self.root_dir = Path(root_dir)

    def load_cases(self) -> List[CaseData]:
        if not self.root_dir.exists():
            raise FileNotFoundError(f"Cartella casi non trovata: {self.root_dir}")

        case_dirs = sorted([p for p in self.root_dir.iterdir() if p.is_dir()])
        cases: List[CaseData] = []
        for idx, case_dir in enumerate(case_dirs, start=1):
            sequences: Dict[str, List[Path]] = {}
            for display_name in DISPLAY_SEQUENCES:
                seq_dir = self._resolve_sequence_dir(case_dir, display_name)
                if seq_dir is None:
                    continue
                files = sorted(
                    [p for p in seq_dir.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS],
                    key=lambda p: p.name.lower(),
                )
                if files:
                    sequences[display_name] = files
            if sequences:
                cases.append(CaseData(folder_name=case_dir.name, excel_prefix=f"Caso{idx:02d}", sequences=sequences))
        return cases

    def _resolve_sequence_dir(self, case_dir: Path, display_name: str) -> Path | None:
        aliases = SEQUENCE_ALIASES.get(display_name, [display_name])
        children = {child.name.lower(): child for child in case_dir.iterdir() if child.is_dir()}
        for alias in aliases:
            match = children.get(alias.lower())
            if match is not None:
                return match
        return None
