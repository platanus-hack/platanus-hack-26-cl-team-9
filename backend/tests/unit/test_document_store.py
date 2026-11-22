"""DocumentStore adapters: conditional writes, head/delete, TTL and key safety."""

import io
import json
import time

import boto3
import pytest
from botocore.response import StreamingBody
from botocore.stub import Stubber

from cascadasen.domain.ports import ConflictError
from cascadasen.infrastructure.document_store import FileDocumentStore, MemoryDocumentStore, S3DocumentStore


class Clock:
    def __init__(self) -> None:
        self.now = time.time()

    def __call__(self) -> float:
        return self.now


@pytest.fixture(params=["memory", "file"])
def make_store(request, tmp_path):
    def make(ttl_s=None, clock=time.time):
        if request.param == "memory":
            return MemoryDocumentStore(ttl_s=ttl_s, clock=clock)
        return FileDocumentStore(tmp_path, ttl_s=ttl_s, clock=clock)

    return make


def test_create_once_then_conflict(make_store):
    store = make_store()
    etag = store.put("sessions/a.json", {"x": 1}, if_none_match=True)
    assert store.get("sessions/a.json") == ({"x": 1}, etag)
    with pytest.raises(ConflictError):
        store.put("sessions/a.json", {"x": 2}, if_none_match=True)


def test_update_with_stale_etag_conflicts(make_store):
    store = make_store()
    first = store.put("runs/r.json", {"v": 1})
    second = store.put("runs/r.json", {"v": 2}, if_match=first)
    assert second != first
    with pytest.raises(ConflictError):
        store.put("runs/r.json", {"v": 3}, if_match=first)
    with pytest.raises(ConflictError):
        store.put("runs/missing.json", {"v": 1}, if_match=first)
    assert store.get("runs/r.json")[0] == {"v": 2}


def test_get_returns_a_copy(make_store):
    store = make_store()
    store.put("k.json", {"a": [1]})
    doc, _ = store.get("k.json")
    doc["a"].append(2)
    assert store.get("k.json")[0] == {"a": [1]}


def test_head_and_delete(make_store):
    store = make_store()
    assert store.head("k.json") is None and store.get("k.json") is None
    etag = store.put("k.json", {"a": 1})
    assert store.head("k.json") == etag
    store.delete("k.json")
    store.delete("k.json")  # deleting a missing key is a no-op
    assert store.head("k.json") is None and store.get("k.json") is None


def test_entries_expire_after_ttl(make_store):
    clock = Clock()
    store = make_store(ttl_s=60, clock=clock)
    store.put("k.json", {"a": 1})
    clock.now += 30
    assert store.get("k.json") is not None
    clock.now += 31
    assert store.get("k.json") is None and store.head("k.json") is None
    store.put("k.json", {"a": 2}, if_none_match=True)  # an expired key can be created again
    assert store.get("k.json")[0] == {"a": 2}


@pytest.mark.parametrize("key", ["../x", "/etc/passwd", "a/../../x", ""])
def test_file_store_rejects_unsafe_keys(tmp_path, key):
    store = FileDocumentStore(tmp_path / "root")
    with pytest.raises(ValueError):
        store.get(key)
    with pytest.raises(ValueError):
        store.put(key, {})


# ------------------------------------------------------------------------- S3 (stubbed)


@pytest.fixture
def s3():
    client = boto3.client(
        "s3", region_name="us-east-1", aws_access_key_id="test", aws_secret_access_key="test"
    )
    with Stubber(client) as stub:
        yield S3DocumentStore("bucket", client=client), stub


def _body(doc: dict) -> StreamingBody:
    data = json.dumps(doc).encode()
    return StreamingBody(io.BytesIO(data), len(data))


def test_s3_get_returns_doc_and_etag(s3):
    store, stub = s3
    stub.add_response(
        "get_object", {"Body": _body({"a": 1}), "ETag": '"e1"'}, {"Bucket": "bucket", "Key": "runs/r.json"}
    )
    assert store.get("runs/r.json") == ({"a": 1}, '"e1"')


def test_s3_put_passes_conditions(s3):
    store, stub = s3
    base = {"Bucket": "bucket", "Key": "k.json", "Body": b'{"a":1}', "ContentType": "application/json"}
    stub.add_response("put_object", {"ETag": '"e2"'}, {**base, "IfMatch": '"e1"'})
    stub.add_response("put_object", {"ETag": '"e3"'}, {**base, "IfNoneMatch": "*"})
    assert store.put("k.json", {"a": 1}, if_match='"e1"') == '"e2"'
    assert store.put("k.json", {"a": 1}, if_none_match=True) == '"e3"'


@pytest.mark.parametrize(
    ("code", "status"), [("PreconditionFailed", 412), ("ConditionalRequestConflict", 409)]
)
def test_s3_failed_condition_is_a_conflict(s3, code, status):
    store, stub = s3
    stub.add_client_error("put_object", service_error_code=code, http_status_code=status)
    with pytest.raises(ConflictError):
        store.put("k.json", {"a": 1}, if_match='"e1"')


def test_s3_missing_key_is_none(s3):
    store, stub = s3
    stub.add_client_error("get_object", service_error_code="NoSuchKey", http_status_code=404)
    stub.add_client_error("head_object", service_error_code="404", http_status_code=404)
    assert store.get("k.json") is None
    assert store.head("k.json") is None
