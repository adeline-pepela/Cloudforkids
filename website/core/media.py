"""Serves uploaded files (lesson videos, photos, logos) from MEDIA_ROOT, with byte ranges so videos can be seeked
and play in Safari. Fine for a school-sized site; put a CDN or object storage in front if traffic grows."""

import mimetypes
import os
import re

from django.conf import settings
from django.http import FileResponse, Http404, HttpResponse, HttpResponseNotModified, StreamingHttpResponse
from django.utils._os import safe_join
from django.utils.http import http_date, parse_http_date_safe

RANGE = re.compile(r"^bytes=(\d*)-(\d*)$")
CHUNK = 64 * 1024


def _slice(handle, start, length):
    handle.seek(start)
    while length > 0:
        data = handle.read(min(CHUNK, length))
        if not data:
            break
        length -= len(data)
        yield data
    handle.close()


def serve_media(request, path):
    try:
        full = safe_join(settings.MEDIA_ROOT, path)
    except Exception:
        raise Http404("Not found")
    if not os.path.isfile(full):
        raise Http404("Not found")
    stat = os.stat(full)
    since = parse_http_date_safe(request.headers.get("If-Modified-Since", ""))
    if since is not None and int(stat.st_mtime) <= since:
        return HttpResponseNotModified()
    ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
    size = stat.st_size
    match = RANGE.match(request.headers.get("Range", ""))
    if match and (match.group(1) or match.group(2)):
        if match.group(1):
            start = int(match.group(1))
            end = int(match.group(2)) if match.group(2) else size - 1
        else:  # "bytes=-500" means the last 500 bytes
            start, end = max(size - int(match.group(2)), 0), size - 1
        end = min(end, size - 1)
        if start > end or start >= size:
            response = HttpResponse(status=416)
            response["Content-Range"] = f"bytes */{size}"
            return response
        response = StreamingHttpResponse(_slice(open(full, "rb"), start, end - start + 1), status=206, content_type=ctype)
        response["Content-Range"] = f"bytes {start}-{end}/{size}"
        response["Content-Length"] = str(end - start + 1)
    else:
        response = FileResponse(open(full, "rb"), content_type=ctype)
        response["Content-Length"] = str(size)
    response["Accept-Ranges"] = "bytes"
    response["Last-Modified"] = http_date(stat.st_mtime)
    response["Cache-Control"] = "public, max-age=86400"
    return response
