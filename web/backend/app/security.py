"""Local browser-request protection; this is deliberately not user authentication."""
import secrets
from uuid import UUID

from starlette.datastructures import Headers
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse

from .storage import ARTIFACT_NAMES

MULTIPART_OVERHEAD_BYTES = 16 * 1024
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def is_media_read(scope):
    """Native media/download requests may omit Origin; JSON APIs may not."""
    if scope["method"] not in {"GET", "HEAD"}:
        return False
    parts = scope["path"].split("/")
    if len(parts) not in {5, 6} or parts[:3] != ["", "api", "jobs"]:
        return False
    try:
        UUID(parts[3])
    except ValueError:
        return False
    if len(parts) == 5:
        return parts[4] in {"video", "thumbnail"}
    return parts[4] == "artifacts" and parts[5] in ARTIFACT_NAMES


class LocalRequestProtection:
    """Reject unauthorized origins / mutations without calling receive()."""

    def __init__(self, app, *, allowed_origins, csrf_token: str, max_upload_bytes: int):
        self.app = app
        self.allowed_origins = frozenset(allowed_origins)
        self.csrf_token = csrf_token.encode("ascii")
        self.body_limit = max_upload_bytes + MULTIPART_OVERHEAD_BYTES

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        hosts = headers.getlist("host")
        if len(hosts) != 1:
            await self.reject(scope, receive, send, 400, "無效的 Host。")
            return
        origins = headers.getlist("origin")
        # The outer TrustedHostMiddleware has already validated this hostname.
        # Permit the API's own origin so Swagger /docs can use its token workflow.
        same_origin = f"{scope.get('scheme', 'http')}://{hosts[0]}"
        accepted_origin = len(origins) == 1 and (origins[0] in self.allowed_origins or origins[0] == same_origin)
        if origins and not accepted_origin:
            await self.reject(scope, receive, send, 403, "不接受此網頁來源。")
            return
        if (headers.get("sec-fetch-site", "").lower() == "cross-site"
                and not accepted_origin and not is_media_read(scope)):
            await self.reject(scope, receive, send, 403, "跨網站請求必須來自允許的網頁來源。")
            return
        if scope["method"] not in SAFE_METHODS:
            tokens = headers.getlist("x-tide-csrf")
            supplied = tokens[0].encode("utf-8") if len(tokens) == 1 else b""
            if not secrets.compare_digest(supplied, self.csrf_token):
                await self.reject(scope, receive, send, 403, "請先取得 /api/session 的 CSRF token，再以 X-Tide-CSRF 傳送。")
                return

        is_upload = scope["path"].rstrip("/") == "/api/jobs"
        is_assistant = scope["path"].startswith("/api/assistant/")
        if scope["method"] == "POST" and (is_upload or is_assistant):
            body_limit = self.body_limit if is_upload else 16 * 1024
            lengths = headers.getlist("content-length")
            if lengths:
                # Avoid integer-conversion surprises or ambiguous duplicate lengths.
                if len(lengths) != 1 or not lengths[0].isascii() or not lengths[0].isdigit() or len(lengths[0]) > 20:
                    await self.reject(scope, receive, send, 400, "無效的 Content-Length。")
                    return
                if int(lengths[0]) > body_limit:
                    await self.reject(scope, receive, send, 413, "請求超過大小限制。")
                    return
            received = 0

            async def limited_receive():
                nonlocal received
                message = await receive()
                if message["type"] == "http.request":
                    received += len(message.get("body", b""))
                    if received > body_limit:
                        # Raised inside the parser; its BaseException cleanup closes temp files.
                        raise HTTPException(413, "請求超過大小限制。")
                return message

            await self.app(scope, limited_receive, send)
        else:
            await self.app(scope, receive, send)

    @staticmethod
    async def reject(scope, receive, send, status, detail):
        await JSONResponse({"detail": detail}, status_code=status, headers={"Cache-Control": "no-store"})(scope, receive, send)
