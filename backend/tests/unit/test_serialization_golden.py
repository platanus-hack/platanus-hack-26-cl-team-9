"""Golden bytes of the compact JSON encoders. Etags (`document_store._etag`) and the audit hash chain
(`audit.canonical`) hash these outputs, so a changed byte invalidates stored sessions and run traces."""

import hashlib
from pathlib import Path

from cascadasen.domain.theater.audit import canonical
from cascadasen.infrastructure.document_store import _encode, _etag
from cascadasen.infrastructure.files import write_json

DOC = {"z": 1, "á": "ñandú ✓", "a": [1.5, None, True, {"k": "</x>"}], "n": {"b": 0.1, "a": 2}}


def test_encode_is_compact_utf8_and_keeps_insertion_order():
    data = _encode(DOC)
    assert data == '{"z":1,"á":"ñandú ✓","a":[1.5,null,true,{"k":"</x>"}],"n":{"b":0.1,"a":2}}'.encode()
    assert _etag(data) == hashlib.sha256(data).hexdigest()


def test_canonical_sorts_keys_rounds_floats_and_stringifies_unknowns():
    obj = {
        "z": 1,
        "á": "ñandú ✓",
        3: [0.123456789, {2, 1}, (1, 2)],
        "p": Path("/tmp/x"),
        "f": frozenset({"b", "a"}),
    }
    assert canonical(obj) == ('{"3":[0.123457,[1,2],[1,2]],"f":["a","b"],"p":"/tmp/x","z":1,"á":"ñandú ✓"}')


def test_write_json_creates_folders_and_matches_encode(tmp_path):
    path = tmp_path / "a" / "b" / "doc.json"
    assert write_json(path, DOC) == len(_encode(DOC))
    assert path.read_bytes() == _encode(DOC)
