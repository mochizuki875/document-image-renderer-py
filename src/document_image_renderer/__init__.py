"""Render PDF and Office documents as page images."""

from document_image_renderer.exceptions import (
    DependencyNotFoundError,
    DocumentConversionError,
    DocumentRenderError,
    RendererError,
    UnsupportedFormatError,
)
from document_image_renderer.models import RenderedImage, RenderOptions, RenderResult
from document_image_renderer.renderer import render_document

__all__ = [
    "DependencyNotFoundError",
    "DocumentConversionError",
    "DocumentRenderError",
    "RenderedImage",
    "RendererError",
    "RenderOptions",
    "RenderResult",
    "UnsupportedFormatError",
    "render_document",
]
