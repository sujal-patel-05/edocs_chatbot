import struct
import pytest
from src.edocs.ingest.chm_meta import parse_system

def test_parse_system_basic():
    # Construct binary #SYSTEM structure
    # Header: 4-byte version
    data = bytearray(b"\x03\x00\x00\x00")
    
    # Entry 0: contents_file (eDocs.hhc)
    val0 = b"eDocs.hhc\x00"
    data.extend(struct.pack("<HH", 0, len(val0)) + val0)
    
    # Entry 2: default_topic (_WhatsNew_C.html)
    val2 = b"_WhatsNew_C.html\x00"
    data.extend(struct.pack("<HH", 2, len(val2)) + val2)
    
    # Entry 3: title (Symitar eDocs)
    val3 = b"Symitar eDocs\x00"
    data.extend(struct.pack("<HH", 3, len(val3)) + val3)
    
    meta = parse_system(bytes(data))
    assert meta["contents_file"] == "eDocs.hhc"
    assert meta["default_topic"] == "_WhatsNew_C.html"
    assert meta["title"] == "Symitar eDocs"
    assert "index_file" not in meta
