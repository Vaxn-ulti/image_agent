import gzip
import json
import struct
from pathlib import Path
from typing import Any


def _read_header(path: Path) -> bytes:
    opener = gzip.open if path.name.endswith(".gz") else open
    with opener(path, "rb") as f:
        return f.read(348)


def parse_nifti_header(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    header = _read_header(p)
    if len(header) < 348:
        raise ValueError("File is too small for a NIfTI header")
    sizeof_hdr_le = struct.unpack("<i", header[:4])[0]
    sizeof_hdr_be = struct.unpack(">i", header[:4])[0]
    endian = "<" if sizeof_hdr_le == 348 else ">" if sizeof_hdr_be == 348 else None
    if endian is None:
        raise ValueError("Not a valid NIfTI-1 file: sizeof_hdr != 348")
    dim = struct.unpack(endian + "8h", header[40:56])
    pixdim = struct.unpack(endian + "8f", header[76:108])
    datatype = struct.unpack(endian + "h", header[70:72])[0]
    bitpix = struct.unpack(endian + "h", header[72:74])[0]
    magic = header[344:348].decode("ascii", errors="ignore").strip("\x00")
    ndim = max(dim[0], 0)
    shape = [int(x) for x in dim[1 : 1 + ndim]]
    return {
        "filename": p.name,
        "format": "NIFTI",
        "ndim": int(ndim),
        "shape": shape,
        "pixdim": [float(x) for x in pixdim[1 : 1 + max(ndim, 1)]],
        "datatype": int(datatype),
        "bitpix": int(bitpix),
        "magic": magic,
        "json": json.dumps({"shape": shape}),
    }
