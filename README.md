# document-image-renderer

A Python library that converts PDF, DOCX, PPTX, and XLSX documents into PNG or JPEG images, one image per page or worksheet.
It provides both a Python API and a command-line interface.

Office documents are converted to PDF with LibreOffice, and every PDF page is rasterized with PyMuPDF.
LibreOffice is not used when the input is already a PDF.

## Requirements

- Python 3.10 or later
- PDF rendering: PyMuPDF, installed automatically as a Python dependency
- DOCX, PPTX, and XLSX conversion: LibreOffice

## Reproducibility

When the same LibreOffice version, PyMuPDF version, fonts, and locale are used, every page fixed in the intermediate PDF is rendered at the requested resolution without omission.
However, LibreOffice and Microsoft Office use different rendering engines, so arbitrary Office documents are not guaranteed to match Microsoft Office output pixel for pixel.

Font substitution can change line breaks, character widths, and page counts.
Install the fonts used by the source document and verify that the operating system recognizes them with a standard tool such as `fc-list`.
When distributing or installing fonts on a server, comply with their license terms.

The input file itself is never modified.

See [DESIGN.md](DESIGN.md) for the detailed design and guarantees.

## Installing the Python package

### Install directly from GitHub

Install the repository directly into the current Python environment:

```bash
python -m pip install "document-image-renderer @ git+https://github.com/mochizuki875/document-image-renderer.git"
```

To use a specific tag, branch, or commit, append `@<ref>` to the URL:

```bash
python -m pip install "document-image-renderer @ git+https://github.com/mochizuki875/document-image-renderer.git@main"
```

### Clone into another project and install

From the root of the project that will use this library, clone the repository into a subdirectory and install it:

```bash
git clone https://github.com/mochizuki875/document-image-renderer.git vendor/document-image-renderer
python -m pip install ./vendor/document-image-renderer
```

To edit the library source while using it, install it in editable mode:

```bash
python -m pip install -e './vendor/document-image-renderer[dev]'
```

## Installing LibreOffice

No additional operating-system package is required when processing PDF input only.
To process DOCX, PPTX, or XLSX files, install LibreOffice using the instructions below.

<details><summary>Ubuntu and Debian</summary>

Install Writer, Calc, Impress, and common Latin and Japanese fonts:

```bash
sudo apt-get update
sudo apt-get install -y \
	libreoffice-writer \
	libreoffice-calc \
	libreoffice-impress \
	fonts-liberation \
	fonts-noto-cjk \
	fonts-crosextra-carlito
```

Verify the installation:

```bash
libreoffice --version
```
</details>

<details><summary>Fedora</summary>

Install LibreOffice and Noto fonts, including Japanese fonts:

```bash
sudo dnf install libreoffice google-noto-sans-cjk-fonts liberation-fonts
```

Verify the installation:

```bash
libreoffice --version
```

</details>

<details><summary>macOS</summary>

When using Homebrew, install the official LibreOffice application:

```bash
brew install --cask libreoffice
```

A standard macOS installation does not add `soffice` to `PATH`.
Specify the executable path with `libreoffice_executable` when using the Python API:

```python
options = RenderOptions(
	libreoffice_executable="/Applications/LibreOffice.app/Contents/MacOS/soffice",
)
result = render_document("report.docx", "rendered/report", options=options)
```

To use the CLI or bundled example, add the LibreOffice directory to `PATH` in the current shell:

```bash
export PATH="/Applications/LibreOffice.app/Contents/MacOS:$PATH"
```

Verify the installation:

```bash
/Applications/LibreOffice.app/Contents/MacOS/soffice --version
```

</details>

<details><summary>Windows</summary>

When using WinGet, install the official LibreOffice package:

```powershell
winget install --id TheDocumentFoundation.LibreOffice --exact
```

Open a new terminal after installation.
If `soffice.exe` is not on `PATH`, specify the executable path when using the Python API:

```python
options = RenderOptions(
	libreoffice_executable=r"C:\Program Files\LibreOffice\program\soffice.exe",
)
result = render_document("report.docx", "rendered/report", options=options)
```

To use the CLI or bundled example, add the LibreOffice directory to `PATH` in the current PowerShell session:

```powershell
$env:Path += ";C:\Program Files\LibreOffice\program"
```

Verify the installation:

```powershell
& "C:\Program Files\LibreOffice\program\soffice.exe" --version
```

</details>

## Python API

`render_document()` accepts an input document, an output directory, and rendering options, then returns metadata for the generated images.

```python
from pathlib import Path

from document_image_renderer import RenderOptions, render_document

result = render_document(
	Path("report.docx"),
	Path("rendered/report"),
	options=RenderOptions(dpi=200, image_format="png"),
)

print(f"{result.page_count} pages")
for image in result.images:
	print(image.page_number, image.path, image.width, image.height)
```

This example creates sequential images beginning with `rendered/report/report-page-0001.png`.
The order of `result.images` matches the page order of the input document.

### Rendering options

| Argument | Default | Description |
|---|---:|---|
| `dpi` | `200` | Rendering resolution from 1 to 1200 DPI |
| `image_format` | `"png"` | `"png"` or `"jpeg"` |
| `jpeg_quality` | `90` | JPEG quality from 1 to 100 |
| `transparent_background` | `False` | Whether PNG backgrounds are transparent |
| `filename_prefix` | Input file name | Prefix for output file names |
| `libreoffice_timeout` | `120.0` | LibreOffice conversion timeout in seconds |
| `libreoffice_executable` | Auto-detected | Explicit path to the LibreOffice executable |

Existing images with the same names are replaced.
Unrelated files in the output directory are not deleted.
Each XLSX worksheet is scaled to fit on one landscape page before rendering.
For large worksheets, text and cells may become small in order to fit on one page.

## Command line

The following command converts a document to 200 DPI PNG images:

```bash
document-image-renderer tests/fixtures/documents/report.docx example/output/report
```

Generated image paths are written to standard output in page order.
To generate JPEG images, specify the format and quality:

```bash
document-image-renderer report.pptx rendered/slides \
  --dpi 300 \
  --format jpeg \
  --jpeg-quality 92
```

The CLI supports `--dpi`, `--format`, `--jpeg-quality`, `--prefix`, and `--timeout`.
Run `document-image-renderer --help` to see all arguments.

## Running the example program

[example/convert_documents.py](example/convert_documents.py) converts `tests/fixtures/documents/report.docx` to 200 DPI PNG images.
Before running it, install LibreOffice and ensure that either `libreoffice` or `soffice` can be launched from `PATH`.

Install the development dependencies from the repository root:

```bash
python -m pip install -e '.[dev]'
```

Then run the example:

```bash
python example/convert_documents.py
```

The program prints the page count, output directory, and generated image paths:

```text
Converted 2 page(s) to example/output/report
example/output/report/report-page-0001.png
example/output/report/report-page-0002.png
```

Generated images are saved under `example/output/report/`.

## Error handling

All library-specific exceptions inherit from `RendererError`.

- `UnsupportedFormatError`: The input format is not supported.
- `DependencyNotFoundError`: LibreOffice cannot be found when converting an Office document.
- `DocumentConversionError`: LibreOffice fails to produce a PDF.
- `DocumentRenderError`: A PDF cannot be opened or rasterized.

`DocumentConversionError.stdout` and `DocumentConversionError.stderr` retain the LibreOffice diagnostic output.

```python
from document_image_renderer import DocumentConversionError, render_document

try:
	render_document("report.xlsx", "rendered/report")
except DocumentConversionError as error:
	print(error.stderr)
```

## Testing

Unit tests and static checks can run on the host:

```bash
python -m pytest
python -m ruff check src tests example
```

Integration tests that convert every document under `tests/fixtures/documents/` are enabled explicitly in an environment with LibreOffice:

```bash
RUN_INTEGRATION_TESTS=1 python -m pytest -m integration
```

## Dev container

The `.devcontainer/` directory provides a VS Code Dev Containers environment for development without installing LibreOffice directly on the host.
It includes LibreOffice, Liberation, Noto CJK, and Carlito, and substitutes Carlito for Aptos and Aptos Display.
The dev container is optional; the library also works in standard Linux, macOS, and Windows environments that satisfy the requirements above.

## Operational considerations

Encrypted documents, corrupted documents, and legacy Office binary formats (`.doc`, `.ppt`, and `.xls`) are not supported.

## License

Released under the Apache License 2.0.
See [LICENSE](LICENSE) for the full text.