"""Public value objects used by the renderer."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

ImageFormat = Literal["png", "jpeg"]


@dataclass(frozen=True, slots=True)
class RenderOptions:
    """Options controlling page rasterization and LibreOffice execution."""

    dpi: int = 200
    image_format: ImageFormat = "png"
    jpeg_quality: int = 90
    transparent_background: bool = False
    filename_prefix: str | None = None
    libreoffice_timeout: float = 120.0
    libreoffice_executable: str | None = None

    def __post_init__(self) -> None:
        if not 1 <= self.dpi <= 1200:
            raise ValueError("dpi must be between 1 and 1200")
        if self.image_format not in {"png", "jpeg"}:
            raise ValueError("image_format must be 'png' or 'jpeg'")
        if not 1 <= self.jpeg_quality <= 100:
            raise ValueError("jpeg_quality must be between 1 and 100")
        if self.image_format == "jpeg" and self.transparent_background:
            raise ValueError("JPEG does not support a transparent background")
        if self.libreoffice_timeout <= 0:
            raise ValueError("libreoffice_timeout must be greater than zero")
        if self.filename_prefix is not None:
            if not self.filename_prefix or Path(self.filename_prefix).name != self.filename_prefix:
                raise ValueError("filename_prefix must be a non-empty file name component")


@dataclass(frozen=True, slots=True)
class RenderedImage:
    """Metadata for one rendered page image."""

    page_number: int
    path: Path
    width: int
    height: int


@dataclass(frozen=True, slots=True)
class RenderResult:
    """Result of rendering a document."""

    source: Path
    images: tuple[RenderedImage, ...]

    @property
    def page_count(self) -> int:
        return len(self.images)
