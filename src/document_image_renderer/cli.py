"""Command-line interface for document-image-renderer."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from document_image_renderer.exceptions import RendererError
from document_image_renderer.models import RenderOptions
from document_image_renderer.renderer import render_document


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="document-image-renderer",
        description="Render every page in a PDF or Office document as an image.",
    )
    parser.add_argument(
        "source",
        type=Path,
        help="PDF, DOC, DOCX, PPT, PPTX, XLS, XLSX, or XLSM input file",
    )
    parser.add_argument("output_directory", type=Path, help="directory for rendered images")
    parser.add_argument("--dpi", type=int, default=200, help="rendering resolution (default: 200)")
    parser.add_argument(
        "--format",
        dest="image_format",
        choices=("png", "jpeg"),
        default="png",
        help="output image format (default: png)",
    )
    parser.add_argument(
        "--jpeg-quality",
        type=int,
        default=90,
        help="JPEG quality from 1 to 100 (default: 90)",
    )
    parser.add_argument("--prefix", help="output file name prefix")
    parser.add_argument(
        "--timeout",
        type=float,
        default=120.0,
        help="LibreOffice timeout in seconds (default: 120)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv)

    try:
        options = RenderOptions(
            dpi=arguments.dpi,
            image_format=arguments.image_format,
            jpeg_quality=arguments.jpeg_quality,
            filename_prefix=arguments.prefix,
            libreoffice_timeout=arguments.timeout,
        )
        result = render_document(arguments.source, arguments.output_directory, options=options)
    except (RendererError, FileNotFoundError, ValueError) as error:
        parser.exit(1, f"error: {error}\n")

    for image in result.images:
        print(image.path)
    return 0
