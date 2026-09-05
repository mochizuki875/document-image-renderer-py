from __future__ import annotations

import os
import shutil
from pathlib import Path

import pymupdf
import pytest

from document_image_renderer import render_document

DOCUMENT_DIRECTORY = Path(__file__).parent / "fixtures" / "documents"
TEST_DOCUMENTS = tuple(sorted(path for path in DOCUMENT_DIRECTORY.iterdir() if path.is_file()))
if not TEST_DOCUMENTS:
    raise RuntimeError(f"No integration test documents found in {DOCUMENT_DIRECTORY}")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_INTEGRATION_TESTS") != "1",
        reason="set RUN_INTEGRATION_TESTS=1 to run bundled document conversions",
    ),
]


@pytest.mark.parametrize("source", TEST_DOCUMENTS, ids=lambda path: path.name)
def test_renders_fixture_document(source: Path, tmp_path: Path) -> None:
    if source.suffix.lower() != ".pdf" and not (
        shutil.which("libreoffice") or shutil.which("soffice")
    ):
        pytest.skip("LibreOffice is not installed")

    result = render_document(source, tmp_path / source.name)

    assert result.page_count > 0
    for rendered_image in result.images:
        assert rendered_image.width > 0
        assert rendered_image.height > 0
        with pymupdf.open(rendered_image.path) as image:
            assert image.page_count == 1