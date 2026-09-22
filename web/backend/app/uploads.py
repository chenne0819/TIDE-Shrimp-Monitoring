"""One bounded multipart upload with limits enforced while receiving file parts."""
from dataclasses import dataclass
from typing import Literal

from fastapi import HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from python_multipart.exceptions import MultipartParseError
from python_multipart.multipart import parse_options_header
from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartException, MultiPartParser
from starlette.requests import ClientDisconnect


class UploadFields(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pond: str = "A-01"
    recorded_at: str | None = None
    mode: Literal["general", "head_tail", "predict"] = "general"
    water_policy: Literal["stop", "report"] = "report"
    max_frames: int | None = Field(default=None, gt=0, le=2_147_483_647)


FIELD_NAMES = frozenset(UploadFields.model_fields)
MAX_PART_HEADER_BYTES = 4096
MAX_FIELD_BYTES = 1024


@dataclass
class UploadPayload:
    file: UploadFile
    fields: UploadFields


class BoundedMultipartParser(MultiPartParser):
    def __init__(self, headers, stream, *, max_file_bytes):
        super().__init__(headers, stream, max_files=1, max_fields=len(FIELD_NAMES), max_part_size=MAX_FIELD_BYTES)
        self.max_file_bytes = max_file_bytes
        self.seen_names = set()
        self.finished = False
        self.part_bytes = 0
        self.header_bytes = 0
        self.header_names = set()

    def on_part_begin(self):
        super().on_part_begin()
        self.part_bytes = self.header_bytes = 0
        self.header_names = set()

    def count_header(self, amount):
        self.header_bytes += amount
        if self.header_bytes > MAX_PART_HEADER_BYTES:
            raise HTTPException(413, "Multipart 標頭過大。")

    def on_header_field(self, data, start, end):
        self.count_header(end - start)
        super().on_header_field(data, start, end)

    def on_header_value(self, data, start, end):
        self.count_header(end - start)
        super().on_header_value(data, start, end)

    def on_header_end(self):
        name = self._current_partial_header_name.lower()
        if name in self.header_names:
            raise MultiPartException("Duplicate multipart header")
        self.header_names.add(name)
        super().on_header_end()

    def on_headers_finished(self):
        disposition, options = parse_options_header(self._current_part.content_disposition)
        try:
            name = options.get(b"name", b"").decode("ascii")
        except UnicodeDecodeError as exc:
            raise MultiPartException("Invalid multipart field name") from exc
        is_file = b"filename" in options
        if disposition != b"form-data" or not name:
            raise MultiPartException("Invalid multipart content disposition")
        if name in self.seen_names:
            raise MultiPartException("Duplicate multipart field")
        if is_file and name != "file":
            raise MultiPartException("Only the file field may contain a file")
        if not is_file and name not in FIELD_NAMES:
            raise MultiPartException("Unexpected multipart field")
        self.seen_names.add(name)
        # Validation above runs before the base parser can allocate another temp file.
        super().on_headers_finished()

    def on_part_data(self, data, start, end):
        if self._current_part.file is not None:
            self.part_bytes += end - start
            if self.part_bytes > self.max_file_bytes:
                raise HTTPException(413, "影片超過上傳大小限制。")
        super().on_part_data(data, start, end)

    def on_end(self):
        self.finished = True
        super().on_end()

    def close_files(self):
        # Includes unfinished parts omitted from FormData. Synchronous close also runs
        # when the enclosing coroutine has been cancelled/disconnected.
        for handle in self._files_to_close_on_error:
            handle.close()

    async def parse(self):
        try:
            form = await super().parse()
            if not self.finished:
                raise MultiPartException("Incomplete multipart body")
            return form
        except BaseException:
            self.close_files()
            raise


async def receive_upload(request: Request):
    content_type, options = parse_options_header(request.headers.get("content-type", ""))
    if content_type != b"multipart/form-data":
        raise HTTPException(415, "上傳必須使用 multipart/form-data。")
    boundary = options.get(b"boundary", b"")
    if not boundary or len(boundary) > 200:
        raise HTTPException(400, "無效的 multipart boundary。")
    parser = BoundedMultipartParser(request.headers, request.stream(), max_file_bytes=request.app.state.settings.max_upload_bytes)
    try:
        try:
            form = await parser.parse()
        except (MultiPartException, MultipartParseError, ClientDisconnect) as exc:
            raise HTTPException(400, "上傳內容不完整，或包含重複／不支援的欄位。") from exc
        file = form.get("file")
        if not isinstance(file, UploadFile):
            raise HTTPException(422, "請提供 file 影片欄位。")
        try:
            fields = UploadFields.model_validate({key: value for key, value in form.multi_items() if key != "file"})
        except ValidationError as exc:
            raise HTTPException(422, exc.errors(include_context=False, include_url=False)) from exc
        yield UploadPayload(file=file, fields=fields)
    finally:
        parser.close_files()


UPLOAD_OPENAPI = {
    "requestBody": {
        "required": True,
        "content": {
            "multipart/form-data": {
                "schema": {
                    "type": "object", "additionalProperties": False, "required": ["file"],
                    "properties": {"file": {"type": "string", "format": "binary"}, **UploadFields.model_json_schema()["properties"]},
                }
            }
        },
    }
}
