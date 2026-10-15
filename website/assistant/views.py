"""The assistant panel's JSON endpoints. The panel polls a thread while a reply streams in."""

import json
from datetime import timedelta
from functools import wraps

from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from . import loop
from .access import can_use, default_connection
from .context import clean_screen
from .models import Action, AssistantSettings, Connection, Thread, Turn
from .tools import ToolError, request_meta

STALE_AFTER = timedelta(minutes=4)  # a reply that has been "busy" this long was cut off (a server restart)
FILE_AREAS = ("admin", "teach")  # children and parents don't attach files
MAX_FILES = 4
TEXT_LIMIT = 300_000  # characters of a text file
BINARY_LIMIT = 2_000_000  # characters of base64 (about 1.5 MB), under Django's request size limit
IMAGE_TYPES = ("image/png", "image/jpeg", "image/webp", "image/gif")


def clean_files(raw):
    """Attached files as the browser sent them, checked: [{name, type, kind, text|data, size}]."""
    if not raw:
        return []
    if not isinstance(raw, list) or len(raw) > MAX_FILES:
        raise ValueError(f"Attach up to {MAX_FILES} files.")
    files = []
    for f in raw:
        if not isinstance(f, dict):
            raise ValueError("A file could not be read.")
        name, mime, kind = str(f.get("name") or "file")[:120], str(f.get("type") or ""), f.get("kind")
        if kind == "text":
            text = str(f.get("text") or "")
            if len(text) > TEXT_LIMIT:
                raise ValueError(f"{name} is too long. Attach a smaller file.")
            files.append({"name": name, "type": mime or "text/plain", "kind": "text", "text": text, "size": len(text)})
        elif kind in ("image", "pdf"):
            data = str(f.get("data") or "")
            if kind == "image" and mime not in IMAGE_TYPES:
                raise ValueError(f"{name}: attach PNG, JPEG, WebP or GIF images.")
            if not data or len(data) > BINARY_LIMIT:
                raise ValueError(f"{name} is too big. Attach a file under 1.5 MB.")
            files.append({"name": name, "type": mime if kind == "image" else "application/pdf", "kind": kind, "data": data, "size": len(data) * 3 // 4})
        else:
            raise ValueError(f"{name}: attach text, CSV, JSON, an image or a PDF.")
    return files


def _json(request):
    try:
        data = json.loads(request.body or b"{}")
    except ValueError:
        data = {}
    return data if isinstance(data, dict) else {}


def _error(message, status=400):
    return JsonResponse({"ok": False, "error": message}, status=status)


def api(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return _error("Please sign in again.", 401)
        return view(request, *args, **kwargs)
    return wrapper


def _thread(request, pk):
    thread = Thread.objects.filter(pk=pk, user=request.user).select_related("connection").first()
    if thread is None or not can_use(request.user, thread.area):
        return None
    if thread.busy and thread.updated_at < timezone.now() - STALE_AFTER:
        Thread.objects.filter(pk=thread.pk).update(busy=False)
        Turn.objects.filter(thread=thread, streaming=True).update(streaming=False, failed=True, error="This reply was cut off. Try again.")
        thread.busy = False
    return thread


def _action_json(a):
    return {
        "id": a.id, "tool": a.tool, "summary": a.summary, "status": a.status, "writes": a.writes,
        "can_undo": a.status == Action.Status.DONE and bool(a.undo), "undo_label": a.undo_label or "Undo",
        "link": a.link, "error": a.result[:300] if a.status == Action.Status.FAILED else "",
    }


def _thread_json(thread):
    turns = list(thread.turns.exclude(role=Turn.Role.TOOL).order_by("created_at", "id"))[-80:]
    actions = {}
    for a in Action.objects.filter(turn__in=[t.pk for t in turns]).order_by("created_at", "id"):
        actions.setdefault(a.turn_id, []).append(_action_json(a))
    return {
        "ok": True, "id": thread.pk, "title": str(thread), "busy": thread.busy,
        "connection_id": thread.connection_id,
        "turns": [{
            "id": t.pk, "role": t.role, "files": [f.get("name") for f in t.files or []], "text": t.text, "reasoning": t.reasoning if t.role == Turn.Role.ASSISTANT else "",
            "streaming": t.streaming, "failed": t.failed, "error": t.error, "when": timezone.localtime(t.created_at).strftime("%H:%M"),
            "actions": actions.get(t.pk, []),
        } for t in turns],
    }


@api
@require_GET
def state(request):
    area = request.GET.get("area", "")
    settings = AssistantSettings.load()
    if not can_use(request.user, area, settings):
        return _error("The assistant isn't available here.", 403)
    default = default_connection()
    threads = Thread.objects.filter(user=request.user, area=area)[:25]
    return JsonResponse({
        "ok": True,
        "connections": [{"id": c.pk, "name": c.display_name} for c in Connection.objects.all()],
        "default_connection": default.pk if default else None,
        "read_only": settings.read_only, "confirm_writes": settings.confirm_writes,
        "can_configure": request.user.is_superuser,
        "can_attach": area in FILE_AREAS,
        "threads": [{"id": t.pk, "title": str(t), "when": timezone.localtime(t.updated_at).strftime("%d %b, %H:%M")} for t in threads],
    })


@api
@require_GET
def thread_detail(request, pk):
    thread = _thread(request, pk)
    if thread is None:
        return _error("That chat isn't there any more.", 404)
    return JsonResponse(_thread_json(thread))


@api
@require_POST
def send(request):
    data = _json(request)
    area = data.get("area", "")
    if not can_use(request.user, area):
        return _error("The assistant isn't available here.", 403)
    text = str(data.get("text") or "").strip()[:8000]
    if not text:
        return _error("Write a message first.")
    try:
        files = clean_files(data.get("files")) if area in FILE_AREAS else []
    except ValueError as err:
        return _error(str(err))
    if area == "learn":
        from live import moderation

        reason = moderation.check(text)
        if reason:
            return _error(moderation.REASONS[reason].replace(" in class chat", " here"))
    if data.get("thread"):
        thread = _thread(request, data["thread"])
        if thread is None or thread.area != area:
            return _error("That chat isn't there any more.", 404)
        if thread.busy:
            return _error("Still working on the last reply. Wait for it, or press Stop.", 409)
    else:
        thread = Thread.objects.create(user=request.user, area=area, title=" ".join(text.split())[:80])
    if data.get("connection"):
        conn = Connection.objects.filter(pk=data["connection"]).first()
        if conn and conn.pk != thread.connection_id:
            thread.connection = conn
            thread.save(update_fields=["connection", "updated_at"])
    loop.supersede_pending(thread)
    Turn.objects.create(thread=thread, role=Turn.Role.USER, text=text, screen=clean_screen(data.get("screen")), files=files)
    loop.start(thread, request_meta(request))
    thread.refresh_from_db()
    return JsonResponse(_thread_json(thread), status=202)


@api
@require_POST
def stop(request, pk):
    thread = _thread(request, pk)
    if thread is None:
        return _error("That chat isn't there any more.", 404)
    Thread.objects.filter(pk=thread.pk, busy=True).update(cancel=True)
    return JsonResponse({"ok": True})


@api
@require_POST
def delete_thread(request, pk):
    Thread.objects.filter(pk=pk, user=request.user, busy=False).delete()
    return JsonResponse({"ok": True})


def _own_action(request, pk):
    action = Action.objects.filter(pk=pk, user=request.user).select_related("thread", "turn").first()
    if action is None or not can_use(request.user, action.thread.area):
        return None
    return action


@api
@require_POST
def decide(request, pk):
    action = _own_action(request, pk)
    if action is None:
        return _error("That change isn't there any more.", 404)
    if action.status != Action.Status.PENDING:
        return _error("That change was already dealt with.", 409)
    if action.thread.busy:
        return _error("Still working. Try again in a moment.", 409)
    loop.decide(action, bool(_json(request).get("approve")), request_meta(request))
    action.thread.refresh_from_db()
    return JsonResponse(_thread_json(action.thread))


@api
@require_POST
def undo(request, pk):
    action = _own_action(request, pk)
    if action is None:
        return _error("That change isn't there any more.", 404)
    try:
        message = loop.undo(action, request_meta(request))
    except ToolError as err:
        return _error(str(err), 409)
    return JsonResponse({"ok": True, "message": message, **_thread_json(action.thread)})
