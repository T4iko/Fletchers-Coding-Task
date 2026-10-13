import zipfile
from pathlib import Path

PDF = "application/pdf"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
OLE = "application/x-ole-storage"  # legacy .doc/.xls OR a password-protected OOXML file
UNKNOWN = "application/octet-stream"


def sniff_mime(path: Path) -> str:
    with open(path, "rb") as f:
        head = f.read(1024)
    if b"%PDF-" in head[:1024]:  # spec allows junk before the header
        return PDF
    if head.startswith(b"PK\x03\x04"):
        try:
            with zipfile.ZipFile(path) as z:
                names = set(z.namelist())
            if "word/document.xml" in names:
                return DOCX
        except zipfile.BadZipFile:
            return UNKNOWN
    if head.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
        return OLE
    return UNKNOWN