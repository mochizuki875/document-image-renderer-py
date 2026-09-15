"""Document conversion and page rendering implementation."""

from __future__ import annotations

import shutil
import subprocess
from contextlib import AbstractContextManager, nullcontext
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from xml.etree import ElementTree
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile

import pymupdf

from document_image_renderer.exceptions import (
    DependencyNotFoundError,
    DocumentConversionError,
    DocumentRenderError,
    UnsupportedFormatError,
)
from document_image_renderer.models import RenderedImage, RenderOptions, RenderResult

SUPPORTED_EXTENSIONS = frozenset(
    {".pdf", ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx", ".xlsm"}
)
OFFICE_EXTENSIONS = SUPPORTED_EXTENSIONS - {".pdf"}
DRAWINGML_NAMESPACE = "http://schemas.openxmlformats.org/drawingml/2006/main"
PRESENTATIONML_NAMESPACE = "http://schemas.openxmlformats.org/presentationml/2006/main"
SPREADSHEETML_NAMESPACE = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
CALC_SINGLE_PAGE_FILTER = (
        'pdf:calc_pdf_Export:{"SinglePageSheets":{"type":"boolean","value":"true"}}'
)
LIBREOFFICE_PROFILE = """<?xml version="1.0" encoding="UTF-8"?>
<oor:items xmlns:oor="http://openoffice.org/2001/registry">
    <item oor:path="/org.openoffice.Office.Common/Security/Scripting">
        <prop oor:name="MacroSecurityLevel" oor:op="fuse"><value>3</value></prop>
    </item>
</oor:items>
"""


def render_document(
    source: str | Path,
    output_directory: str | Path,
    *,
    options: RenderOptions | None = None,
) -> RenderResult:
    """Render every page in a PDF or Office document to an image."""
    source_path = Path(source).expanduser().resolve()
    output_path = Path(output_directory).expanduser().resolve()
    render_options = options or RenderOptions()

    if not source_path.is_file():
        raise FileNotFoundError(f"Input document does not exist: {source_path}")

    extension = source_path.suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise UnsupportedFormatError(
            f"Unsupported document format '{extension or '<none>'}': {source_path}. "
            f"Supported formats: {supported}"
        )

    output_path.mkdir(parents=True, exist_ok=True)
    prefix = render_options.filename_prefix or source_path.stem

    # Office inputs need temporary storage for the converted PDF and user profile.
    temporary_directory: AbstractContextManager[str]
    if extension in OFFICE_EXTENSIONS:
        temporary_directory = TemporaryDirectory(prefix="document-image-renderer-")
    else:
        temporary_directory = nullcontext("")

    with temporary_directory as temporary_path:
        pdf_path = source_path
        if extension in OFFICE_EXTENSIONS:
            pdf_path = _convert_office_to_pdf(
                source_path,
                Path(temporary_path),
                render_options,
            )
        images = _render_pdf(pdf_path, output_path, prefix, render_options)

    return RenderResult(source=source_path, images=images)


def _convert_office_to_pdf(
    source: Path,
    working_directory: Path,
    options: RenderOptions,
) -> Path:
    executable = options.libreoffice_executable or shutil.which("libreoffice") or shutil.which(
        "soffice"
    )
    if executable is None:
        raise DependencyNotFoundError(
            f"LibreOffice is required to convert '{source.suffix.lower()}' documents. "
            "Run the project in its devcontainer or install LibreOffice."
        )

    output_directory = working_directory / "output"
    profile_directory = working_directory / "profile"
    output_directory.mkdir()
    profile_directory.mkdir()
    _configure_libreoffice_profile(profile_directory)

    conversion_source = _prepare_office_source(source, working_directory)
    conversion_filter = CALC_SINGLE_PAGE_FILTER if source.suffix.lower() == ".xls" else "pdf"

    # An isolated profile avoids lock conflicts and user-specific LibreOffice settings.
    command = [
        executable,
        "--headless",
        "--nologo",
        "--nodefault",
        "--nolockcheck",
        "--nofirststartwizard",
        f"-env:UserInstallation={profile_directory.as_uri()}",
        "--convert-to",
        conversion_filter,
        "--outdir",
        str(output_directory),
        str(conversion_source),
    ]

    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=options.libreoffice_timeout,
        )
    except subprocess.TimeoutExpired as error:
        raise DocumentConversionError(
            f"LibreOffice timed out while converting: {source}",
            stdout=_text_or_empty(error.stdout),
            stderr=_text_or_empty(error.stderr),
        ) from error
    except OSError as error:
        raise DocumentConversionError(
            f"Could not start LibreOffice while converting {source}: {error}"
        ) from error

    pdf_path = output_directory / f"{source.stem}.pdf"
    if completed.returncode != 0 or not pdf_path.is_file():
        raise DocumentConversionError(
            f"LibreOffice failed to convert document to PDF: {source}",
            stdout=completed.stdout,
            stderr=completed.stderr,
        )
    return pdf_path


def _configure_libreoffice_profile(profile_directory: Path) -> None:
    user_directory = profile_directory / "user"
    user_directory.mkdir()
    # Very High security prevents document macros from running in the isolated profile.
    (user_directory / "registrymodifications.xcu").write_text(
        LIBREOFFICE_PROFILE,
        encoding="utf-8",
    )


def _prepare_office_source(source: Path, working_directory: Path) -> Path:
    if source.suffix.lower() == ".pptx":
        return _normalize_pptx_lines(source, working_directory)
    if source.suffix.lower() in {".xlsx", ".xlsm"}:
        return _fit_xlsx_sheets_to_pages(source, working_directory)
    return source


def _normalize_pptx_lines(source: Path, working_directory: Path) -> Path:
    # Keep the original file untouched and create a temporary copy only when needed.
    normalized_slides: dict[str, bytes] = {}
    try:
        with ZipFile(source) as presentation:
            for name in presentation.namelist():
                if not name.startswith("ppt/slides/slide") or not name.endswith(".xml"):
                    continue
                slide_xml = presentation.read(name)
                normalized_xml = _normalize_negative_line_extents(slide_xml)
                if normalized_xml != slide_xml:
                    normalized_slides[name] = normalized_xml

            if not normalized_slides:
                return source

            normalized_source = working_directory / source.name
            with ZipFile(normalized_source, "w", ZIP_DEFLATED) as normalized_presentation:
                for member in presentation.infolist():
                    # Replace only changed slide XML and preserve every other package member.
                    normalized_presentation.writestr(
                        member,
                        normalized_slides.get(member.filename, presentation.read(member.filename)),
                    )
    except (BadZipFile, ElementTree.ParseError, OSError):
        # Let LibreOffice report malformed presentations through the existing error path.
        return source

    return normalized_source


def _fit_xlsx_sheets_to_pages(source: Path, working_directory: Path) -> Path:
    normalized_source = working_directory / source.name
    try:
        with ZipFile(source) as workbook, ZipFile(
            normalized_source, "w", ZIP_DEFLATED
        ) as normalized_workbook:
            for member in workbook.infolist():
                data = workbook.read(member.filename)
                if member.filename.startswith("xl/worksheets/sheet") and member.filename.endswith(
                    ".xml"
                ):
                    data = _fit_worksheet_to_page(data)
                normalized_workbook.writestr(member, data)
    except (BadZipFile, ElementTree.ParseError, OSError):
        # Let LibreOffice report malformed workbooks through the existing error path.
        return source

    return normalized_source


def _fit_worksheet_to_page(worksheet_xml: bytes) -> bytes:
    namespaces = dict(
        namespace
        for _, namespace in ElementTree.iterparse(BytesIO(worksheet_xml), events=("start-ns",))
    )
    for prefix, uri in namespaces.items():
        ElementTree.register_namespace(prefix, uri)

    root = ElementTree.fromstring(worksheet_xml)
    qualified = f"{{{SPREADSHEETML_NAMESPACE}}}"

    sheet_properties = root.find(f"{qualified}sheetPr")
    if sheet_properties is None:
        sheet_properties = ElementTree.Element(f"{qualified}sheetPr")
        root.insert(0, sheet_properties)
    page_setup_properties = sheet_properties.find(f"{qualified}pageSetUpPr")
    if page_setup_properties is None:
        page_setup_properties = ElementTree.SubElement(
            sheet_properties, f"{qualified}pageSetUpPr"
        )
    page_setup_properties.set("fitToPage", "1")

    page_setup = root.find(f"{qualified}pageSetup")
    if page_setup is None:
        page_setup = ElementTree.Element(f"{qualified}pageSetup")
        page_margins = root.find(f"{qualified}pageMargins")
        insertion_index = (
            list(root).index(page_margins) + 1 if page_margins is not None else len(root)
        )
        root.insert(insertion_index, page_setup)

    # Fit each worksheet onto one landscape page before LibreOffice exports it.
    page_setup.attrib.pop("scale", None)
    page_setup.set("orientation", "landscape")
    page_setup.set("fitToWidth", "1")
    page_setup.set("fitToHeight", "1")
    return ElementTree.tostring(root, encoding="utf-8", xml_declaration=True)


def _normalize_negative_line_extents(slide_xml: bytes) -> bytes:
    # Preserve original namespace prefixes when serializing modified slide XML.
    namespaces = dict(
        namespace
        for _, namespace in ElementTree.iterparse(BytesIO(slide_xml), events=("start-ns",))
    )
    for prefix, uri in namespaces.items():
        ElementTree.register_namespace(prefix, uri)

    root = ElementTree.fromstring(slide_xml)
    changed = False
    namespace = {"a": DRAWINGML_NAMESPACE, "p": PRESENTATIONML_NAMESPACE}
    for shape in root.findall(".//p:sp", namespace):
        geometry = shape.find("p:spPr/a:prstGeom", namespace)
        if geometry is None or geometry.get("prst") != "line":
            continue

        transform = shape.find("p:spPr/a:xfrm", namespace)
        if transform is None:
            continue
        offset = transform.find("a:off", namespace)
        extent = transform.find("a:ext", namespace)
        if offset is None or extent is None:
            continue

        # PowerPoint normalizes negative line extents, but LibreOffice renders them mirrored.
        for offset_name, extent_name in (("x", "cx"), ("y", "cy")):
            extent_value = int(extent.get(extent_name, "0"))
            if extent_value < 0:
                offset.set(offset_name, str(int(offset.get(offset_name, "0")) + extent_value))
                extent.set(extent_name, str(-extent_value))
                changed = True

    if not changed:
        return slide_xml
    return ElementTree.tostring(root, encoding="utf-8", xml_declaration=True)


def _render_pdf(
    pdf_path: Path,
    output_directory: Path,
    prefix: str,
    options: RenderOptions,
) -> tuple[RenderedImage, ...]:
    extension = "jpg" if options.image_format == "jpeg" else "png"
    # PDF coordinates use 72 points per inch, so this scale produces the requested DPI.
    scale = options.dpi / 72
    matrix = pymupdf.Matrix(scale, scale)
    rendered: list[RenderedImage] = []

    try:
        with pymupdf.open(pdf_path) as document:
            if document.needs_pass:
                raise DocumentRenderError(f"Password-protected PDF is not supported: {pdf_path}")

            page_digits = max(4, len(str(document.page_count)))
            for page_index, page in enumerate(document):
                pixmap = page.get_pixmap(
                    matrix=matrix,
                    colorspace=pymupdf.csRGB,
                    alpha=options.transparent_background,
                )
                image_path = output_directory / (
                    f"{prefix}-page-{page_index + 1:0{page_digits}d}.{extension}"
                )
                save_options = {}
                if options.image_format == "jpeg":
                    save_options["jpg_quality"] = options.jpeg_quality
                pixmap.save(image_path, output=options.image_format, **save_options)
                rendered.append(
                    RenderedImage(
                        page_number=page_index + 1,
                        path=image_path,
                        width=pixmap.width,
                        height=pixmap.height,
                    )
                )
    except DocumentRenderError:
        raise
    except (OSError, RuntimeError, ValueError) as error:
        raise DocumentRenderError(f"Could not render PDF '{pdf_path}': {error}") from error

    return tuple(rendered)


def _text_or_empty(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return value
