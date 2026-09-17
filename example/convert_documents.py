"""Convert the bundled samplefile.docx fixture to page images."""

from __future__ import annotations

from pathlib import Path

from document_image_renderer import RenderOptions, render_document

PROJECT_DIRECTORY = Path(__file__).parent.parent
EXAMPLE_DIRECTORY = PROJECT_DIRECTORY / "example"
SOURCE = PROJECT_DIRECTORY / "tests" / "fixtures" / "documents" / "samplefile.docx"
OUTPUT_DIRECTORY = EXAMPLE_DIRECTORY / "output"


def main() -> int:
    result = render_document(
        SOURCE,
        OUTPUT_DIRECTORY,
        options=RenderOptions(dpi=200, image_format="png"),
    )

    print(f"Converted {result.page_count} page(s) to {OUTPUT_DIRECTORY}")
    for image in result.images:
        print(image.path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
