from __future__ import annotations

import subprocess
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pymupdf
import pytest

from document_image_renderer import (
    DependencyNotFoundError,
    DocumentConversionError,
    RenderOptions,
    UnsupportedFormatError,
    render_document,
)


def create_pdf(path: Path, page_count: int = 2) -> None:
    with pymupdf.open() as document:
        for page_number in range(1, page_count + 1):
            page = document.new_page(width=72, height=144)
            page.insert_text((10, 20), f"Page {page_number}")
        document.save(path)


def test_renders_every_pdf_page_at_requested_dpi(tmp_path: Path) -> None:
    source = tmp_path / "input.pdf"
    create_pdf(source)

    result = render_document(source, tmp_path / "images", options=RenderOptions(dpi=144))

    assert result.source == source.resolve()
    assert result.page_count == 2
    assert [image.page_number for image in result.images] == [1, 2]
    assert [image.path.name for image in result.images] == [
        "input-page-0001.png",
        "input-page-0002.png",
    ]
    assert [(image.width, image.height) for image in result.images] == [(144, 288), (144, 288)]
    assert all(image.path.is_file() for image in result.images)


def test_renders_jpeg_with_custom_prefix(tmp_path: Path) -> None:
    source = tmp_path / "input.pdf"
    create_pdf(source, page_count=1)

    result = render_document(
        source,
        tmp_path / "images",
        options=RenderOptions(image_format="jpeg", jpeg_quality=80, filename_prefix="preview"),
    )

    assert result.images[0].path.name == "preview-page-0001.jpg"
    with pymupdf.open(result.images[0].path) as image:
        assert image.page_count == 1


def test_rejects_unsupported_extension(tmp_path: Path) -> None:
    source = tmp_path / "input.txt"
    source.write_text("not a document", encoding="utf-8")

    with pytest.raises(UnsupportedFormatError, match="Unsupported document format"):
        render_document(source, tmp_path / "images")


def test_office_document_requires_libreoffice(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "input.docx"
    source.write_bytes(b"placeholder")
    monkeypatch.setattr("document_image_renderer.renderer.shutil.which", lambda _: None)

    with pytest.raises(DependencyNotFoundError, match="LibreOffice is required"):
        render_document(source, tmp_path / "images")


def test_converts_office_document_with_isolated_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "input.docx"
    source.write_bytes(b"placeholder")
    captured_command: list[str] = []
    captured_profile_xml = ""

    def fake_run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        nonlocal captured_profile_xml
        captured_command.extend(command)
        profile_argument = next(
            argument
            for argument in command
            if argument.startswith("-env:UserInstallation=file:")
        )
        profile_directory = Path(
            profile_argument.removeprefix("-env:UserInstallation=").removeprefix("file://")
        )
        captured_profile_xml = (
            profile_directory / "user" / "registrymodifications.xcu"
        ).read_text()
        output_directory = Path(command[command.index("--outdir") + 1])
        create_pdf(output_directory / "input.pdf", page_count=1)
        return subprocess.CompletedProcess(command, 0, "converted", "")

    monkeypatch.setattr(
        "document_image_renderer.renderer.shutil.which", lambda _: "/usr/bin/libreoffice"
    )
    monkeypatch.setattr("document_image_renderer.renderer.subprocess.run", fake_run)

    result = render_document(source, tmp_path / "images")

    assert result.page_count == 1
    assert "--headless" in captured_command
    assert 'oor:name="MacroSecurityLevel"' in captured_profile_xml
    assert "<value>3</value>" in captured_profile_xml


def test_normalizes_negative_pptx_line_extents_before_conversion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "input.pptx"
    slide_xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
       xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
  <p:cSld><p:spTree><p:sp><p:spPr>
    <a:xfrm><a:off x="6400800" y="3547872"/><a:ext cx="-960120" cy="886968"/></a:xfrm>
    <a:prstGeom prst="line"><a:avLst/></a:prstGeom>
  </p:spPr></p:sp></p:spTree></p:cSld>
</p:sld>"""
    with ZipFile(source, "w", ZIP_DEFLATED) as presentation:
        presentation.writestr("ppt/slides/slide1.xml", slide_xml)

    def fake_run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        converted_source = Path(command[-1])
        assert converted_source != source
        with ZipFile(converted_source) as presentation:
            normalized_xml = presentation.read("ppt/slides/slide1.xml")
        assert b'x="5440680"' in normalized_xml
        assert b'cx="960120"' in normalized_xml
        output_directory = Path(command[command.index("--outdir") + 1])
        create_pdf(output_directory / "input.pdf", page_count=1)
        return subprocess.CompletedProcess(command, 0, "converted", "")

    monkeypatch.setattr(
        "document_image_renderer.renderer.shutil.which", lambda _: "/usr/bin/libreoffice"
    )
    monkeypatch.setattr("document_image_renderer.renderer.subprocess.run", fake_run)

    result = render_document(source, tmp_path / "images")

    assert result.page_count == 1


@pytest.mark.parametrize("extension", [".xlsx", ".xlsm"])
def test_fits_each_modern_excel_sheet_to_one_landscape_page(
    extension: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / f"input{extension}"
    worksheet_xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData/>
  <pageMargins left="0.7" right="0.7" top="0.75" bottom="0.75"/>
</worksheet>"""
    with ZipFile(source, "w", ZIP_DEFLATED) as workbook:
        workbook.writestr("xl/worksheets/sheet1.xml", worksheet_xml)

    def fake_run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        converted_source = Path(command[-1])
        assert converted_source != source
        with ZipFile(converted_source) as workbook:
            normalized_xml = workbook.read("xl/worksheets/sheet1.xml")
        assert b'fitToPage="1"' in normalized_xml
        assert b'orientation="landscape"' in normalized_xml
        assert b'fitToWidth="1"' in normalized_xml
        assert b'fitToHeight="1"' in normalized_xml
        output_directory = Path(command[command.index("--outdir") + 1])
        create_pdf(output_directory / "input.pdf", page_count=1)
        return subprocess.CompletedProcess(command, 0, "converted", "")

    monkeypatch.setattr(
        "document_image_renderer.renderer.shutil.which", lambda _: "/usr/bin/libreoffice"
    )
    monkeypatch.setattr("document_image_renderer.renderer.subprocess.run", fake_run)

    result = render_document(source, tmp_path / "images")

    assert result.page_count == 1


def test_uses_single_page_pdf_filter_for_xls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "input.xls"
    source.write_bytes(b"placeholder")
    captured_command: list[str] = []

    def fake_run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        captured_command.extend(command)
        output_directory = Path(command[command.index("--outdir") + 1])
        create_pdf(output_directory / "input.pdf", page_count=1)
        return subprocess.CompletedProcess(command, 0, "converted", "")

    monkeypatch.setattr(
        "document_image_renderer.renderer.shutil.which", lambda _: "/usr/bin/libreoffice"
    )
    monkeypatch.setattr("document_image_renderer.renderer.subprocess.run", fake_run)

    result = render_document(source, tmp_path / "images")

    assert result.page_count == 1
    conversion_filter = captured_command[captured_command.index("--convert-to") + 1]
    assert "calc_pdf_Export" in conversion_filter
    assert "SinglePageSheets" in conversion_filter


@pytest.mark.parametrize("extension", [".doc", ".ppt"])
def test_converts_legacy_office_documents_directly(
    extension: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / f"input{extension}"
    source.write_bytes(b"placeholder")
    captured_command: list[str] = []

    def fake_run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        captured_command.extend(command)
        output_directory = Path(command[command.index("--outdir") + 1])
        create_pdf(output_directory / "input.pdf", page_count=1)
        return subprocess.CompletedProcess(command, 0, "converted", "")

    monkeypatch.setattr(
        "document_image_renderer.renderer.shutil.which", lambda _: "/usr/bin/libreoffice"
    )
    monkeypatch.setattr("document_image_renderer.renderer.subprocess.run", fake_run)

    render_document(source, tmp_path / "images")

    assert captured_command[-1] == str(source)
    assert captured_command[captured_command.index("--convert-to") + 1] == "pdf"


def test_exposes_libreoffice_diagnostics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "input.pptx"
    source.write_bytes(b"placeholder")
    monkeypatch.setattr(
        "document_image_renderer.renderer.shutil.which", lambda _: "/usr/bin/libreoffice"
    )
    monkeypatch.setattr(
        "document_image_renderer.renderer.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 1, "output", "failure"),
    )

    with pytest.raises(DocumentConversionError) as captured:
        render_document(source, tmp_path / "images")

    assert captured.value.stdout == "output"
    assert captured.value.stderr == "failure"


@pytest.mark.parametrize(
    ("keyword", "value"),
    [
        ("dpi", 0),
        ("jpeg_quality", 101),
        ("libreoffice_timeout", 0),
        ("filename_prefix", "../outside"),
    ],
)
def test_rejects_invalid_options(keyword: str, value: object) -> None:
    with pytest.raises(ValueError):
        RenderOptions(**{keyword: value})