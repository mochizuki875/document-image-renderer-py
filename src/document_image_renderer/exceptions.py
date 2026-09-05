"""Exceptions raised by document-image-renderer."""

from __future__ import annotations


class RendererError(Exception):
    """Base exception for document rendering failures."""


class UnsupportedFormatError(RendererError, ValueError):
    """Raised when the input extension is unsupported."""


class DependencyNotFoundError(RendererError):
    """Raised when a required external executable is unavailable."""


class DocumentConversionError(RendererError):
    """Raised when LibreOffice cannot convert an Office document to PDF."""

    def __init__(self, message: str, *, stdout: str = "", stderr: str = "") -> None:
        super().__init__(message)
        self.stdout = stdout
        self.stderr = stderr


class DocumentRenderError(RendererError):
    """Raised when a PDF cannot be rendered as images."""
