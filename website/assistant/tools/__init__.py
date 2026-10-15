"""The assistant's tools. Every tool runs as the signed-in person, through the same forms, permission checks and
helpers the admin console and the facilitator portal use. The assistant never has an identity of its own."""

import json
from dataclasses import dataclass, field
from typing import Callable, Optional

from django.contrib.messages import constants as message_levels
from django.core import serializers
from django.forms import MultiWidget
from django.http import HttpRequest
from django.utils.dateparse import parse_date, parse_datetime, parse_time

AREAS = ("admin", "teach")


class ToolError(Exception):
    """A refusal or a problem the person should hear about in plain words."""


@dataclass
class Result:
    data: object
    undo: Optional[dict] = None
    undo_label: str = "Undo"
    link: str = ""


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict
    run: Callable
    area: str
    writes: bool = False
    always_confirm: object = False  # True, or a function(args) -> bool for tools where only some calls leave the building
    describe: Optional[Callable] = None  # (ctx, args) -> one plain sentence for the approval card
    undo: Optional[Callable] = None  # (ctx, info) -> message

    def spec(self):
        return {"name": self.name, "description": self.description, "parameters": self.parameters}

    def must_confirm(self, args):
        return self.always_confirm(args) if callable(self.always_confirm) else bool(self.always_confirm)

    def sentence(self, ctx, args):
        if self.describe:
            try:
                return str(self.describe(ctx, args))[:300]
            except Exception:  # a describe() that cannot find its record still needs a card
                pass
        return f"Run {self.name.replace('_', ' ')}"


REGISTRY = {}


def tool(area, name, description, params=None, required=(), writes=False, always_confirm=False, describe=None, undo=None):
    """Register a tool. `params` maps a name to a JSON Schema fragment."""

    def wrap(fn):
        REGISTRY[name] = Tool(
            name=name, description=description, run=fn, area=area, writes=writes, always_confirm=always_confirm,
            describe=describe, undo=undo,
            parameters={"type": "object", "properties": params or {}, "required": list(required)},
        )
        return fn

    return wrap


def tools_for(area):
    from . import admin_tools, teach_tools  # noqa: F401  (registers them)

    return [t for t in REGISTRY.values() if t.area == area]


def get(name):
    from . import admin_tools, teach_tools  # noqa: F401

    return REGISTRY.get(name)


# ---------------------------------------------------------------- running as the user

class _Collected:
    """Stands in for Django's message storage so the platform's own "Class updated." style messages reach the model."""

    def __init__(self):
        self.items = []

    def add(self, level, message, extra_tags=""):
        self.items.append(("error" if level >= message_levels.ERROR else "info", str(message)))

    def __iter__(self):
        return iter(self.items)


@dataclass
class Ctx:
    user: object
    area: str
    request: HttpRequest = None
    meta: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.request is None:
            self.request = make_request(self.user, self.meta)

    def notes(self):
        return [text for _level, text in self.request._messages]


def make_request(user, meta):
    request = HttpRequest()
    request.method = "POST"
    request.user = user
    request.META = {"SERVER_NAME": "localhost", "SERVER_PORT": "80", **(meta or {})}
    request.path = request.path_info = "/assistant/"
    request._messages = _Collected()
    request.session = {}
    return request


def request_meta(request):
    """The parts of a real request a tool may need later (to build absolute links), safe to keep in a thread."""
    keep = ("HTTP_HOST", "SERVER_NAME", "SERVER_PORT", "HTTP_X_FORWARDED_PROTO", "HTTP_X_FORWARDED_HOST", "wsgi.url_scheme", "REMOTE_ADDR")
    return {k: request.META[k] for k in keep if k in request.META}


# ---------------------------------------------------------------- forms: fill a real form from a few values

def json_arg(value, name="value"):
    """Objects may arrive as JSON text (Gemini sends free-form objects that way)."""
    if isinstance(value, str):
        try:
            value = json.loads(value or "{}")
        except ValueError:
            raise ToolError(f"{name} must be a JSON object.")
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ToolError(f"{name} must be an object of field names and values.")
    return value


def form_data(form_class, instance=None, values=None, form_kwargs=None):
    """Data for binding `form_class`: every field's current value (from `instance`, or its default), with `values`
    laid on top. Only the fields named in `values` change, which is how update tools stay partial."""
    values = dict(values or {})
    unbound = form_class(instance=instance, **(form_kwargs or {})) if instance is not None else form_class(**(form_kwargs or {}))
    unknown = [k for k in values if k not in unbound.fields]
    if unknown:
        allowed = ", ".join(n for n, f in unbound.fields.items() if not f.disabled)
        raise ToolError(f"These fields cannot be set here: {', '.join(unknown)}. Fields you can set: {allowed}.")
    data = {}
    for name, bound in unbound.fields.items():
        if bound.disabled or _is_file(bound):
            if name in values and _is_file(bound):
                raise ToolError(f"{name} is a file. Upload files on the page itself; the assistant cannot.")
            continue
        value = values[name] if name in values else unbound[name].value()
        _put(data, name, bound, value)
    return data


def _is_file(field_obj):
    from django.forms import FileField

    return isinstance(field_obj, FileField)


def _put(data, name, field_obj, value):
    widget = getattr(field_obj.widget, "widget", field_obj.widget)  # the admin wraps related fields
    if value is None:
        return
    if hasattr(value, "pk"):
        value = value.pk
    if isinstance(widget, MultiWidget):
        if isinstance(value, str):
            value = parse_datetime(value) or parse_date(value) or parse_time(value) or value
        parts = widget.decompress(value) if not isinstance(value, (list, tuple)) else list(value)
        for i, part in enumerate(parts):
            if part is not None:
                data[f"{name}_{i}"] = part
        return
    if isinstance(value, (list, tuple, set)) or hasattr(value, "__iter__") and not isinstance(value, (str, bytes, dict)):
        data[name] = [getattr(v, "pk", v) for v in value]
        return
    data[name] = value


def form_errors(form):
    parts = []
    for name, errors in form.errors.get_json_data().items():
        label = "Form" if name == "__all__" else name
        parts.append(f"{label}: {' '.join(e['message'] for e in errors)}")
    return "; ".join(parts) or "The form did not accept these values."


# ---------------------------------------------------------------- snapshots for undo

def snapshot(obj):
    return serializers.serialize("json", [obj])


def restore(data):
    """Put a record back exactly as a snapshot shows it (fields and many-to-many links)."""
    for item in serializers.deserialize("json", data):
        item.save()
        return item.object


def fresh_snapshot(obj):
    return snapshot(type(obj)._default_manager.get(pk=obj.pk))


def changed_since(model, pk, after):
    """True when the record no longer matches what the assistant left, so an undo would overwrite someone's change."""
    obj = model._default_manager.filter(pk=pk).first()
    if obj is None:
        return True
    return after is not None and snapshot(obj) != after


def short(value, limit=400):
    text = " ".join(str(value).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def iso(dt):
    from django.utils import timezone

    if dt is None:
        return None
    if hasattr(dt, "tzinfo") and dt.tzinfo is not None:
        dt = timezone.localtime(dt)
    return dt.isoformat(timespec="minutes") if hasattr(dt, "hour") else dt.isoformat()
