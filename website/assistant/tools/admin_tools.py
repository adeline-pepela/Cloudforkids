"""Admin console tools. They work on any record the Django admin manages, through that model's own ModelAdmin:
the same queryset, search, form, permission checks, save hooks, actions and admin log as the pages themselves."""

from django.contrib import admin
from django.contrib.admin.utils import lookup_spawns_duplicates
from django.core.exceptions import FieldDoesNotExist, FieldError, ValidationError
from django.db import transaction
from django.db.models.fields.files import FieldFile
from django.urls import NoReverseMatch, reverse

from . import ToolError, Result, changed_since, form_data, form_errors, fresh_snapshot, iso, json_arg, restore, short, snapshot, tool

AREA = "admin"
HIDDEN_APPS = {"assistant", "sessions", "contenttypes", "admin"}
SECRET_FIELDS = {"password", "key_sealed", "token", "checkout_request_id", "merchant_request_id"}
LOOKUPS = {"exact", "iexact", "contains", "icontains", "in", "gt", "gte", "lt", "lte", "startswith", "istartswith",
           "isnull", "year", "month", "day", "date", "range"}
LIST_LIMIT = 50


def _staff(ctx):
    user = ctx.user
    if not (user.is_active and user.is_staff):
        raise ToolError("Only admin staff can use the admin assistant.")


def _registered(ctx):
    for model, model_admin in admin.site._registry.items():
        if model._meta.app_label in HIDDEN_APPS:
            continue
        yield model, model_admin


def _resolve(ctx, name):
    _staff(ctx)
    wanted = str(name or "").strip().lower().replace(" ", "")
    for model, model_admin in _registered(ctx):
        meta = model._meta
        names = {meta.label_lower, meta.model_name, str(meta.verbose_name).lower().replace(" ", ""),
                 str(meta.verbose_name_plural).lower().replace(" ", "")}
        if wanted in names:
            if not model_admin.has_view_or_change_permission(ctx.request):
                raise ToolError(f"You don't have permission to see {meta.verbose_name_plural} in the admin.")
            return model, model_admin
    raise ToolError(f"There is no record type called '{name}'. Use list_record_types to see them.")


def _object(ctx, model, model_admin, record_id):
    obj = model_admin.get_object(ctx.request, str(record_id))
    if obj is None:
        raise ToolError(f"No {model._meta.verbose_name} with id {record_id} (or you can't see it).")
    return obj


def _admin_url(obj):
    meta = obj._meta
    try:
        return reverse(f"admin:{meta.app_label}_{meta.model_name}_change", args=[obj.pk])
    except NoReverseMatch:
        return ""


def _value(obj, f, full=False):
    if f.many_to_many:
        return [{"id": o.pk, "name": str(o)} for o in getattr(obj, f.name).all()[:30]]
    if f.is_relation:
        target = getattr(obj, f.name, None)
        return {"id": target.pk, "name": str(target)} if target is not None else None
    value = getattr(obj, f.attname)
    if isinstance(value, FieldFile):
        return value.name or None
    if hasattr(value, "isoformat"):
        return iso(value)
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    text = str(value)
    limit = 30000 if full else 600
    return text if len(text) <= limit else text[:limit] + f"… [truncated: {len(text)} characters; ask for this field by name to read it all]"


def _fields(model):
    return [f for f in model._meta.get_fields()
            if (f.concrete or f.many_to_many) and not f.auto_created or f.primary_key
            if getattr(f, "name", "") not in SECRET_FIELDS]


def _row(obj, model_admin):
    row = {"id": obj.pk, "name": short(str(obj), 120)}
    for name in model_admin.list_display:
        if not isinstance(name, str) or name in ("__str__", "pk", "id") or name in SECRET_FIELDS:
            continue
        try:
            f = obj._meta.get_field(name)
        except FieldDoesNotExist:
            continue
        if f.many_to_many:
            continue
        row[name] = _value(obj, f) if not f.is_relation else str(getattr(obj, name, "") or "")
    return row


# ---------------------------------------------------------------- reading

@tool(AREA, "list_record_types",
      "List every kind of record in the admin you can see (users, courses, lessons, plans, payments, site settings and so on), "
      "with what you may do to each. Use the 'type' value with the other record tools.")
def list_record_types(ctx, args):
    _staff(ctx)
    rows = []
    for model, model_admin in _registered(ctx):
        req = ctx.request
        if not model_admin.has_view_or_change_permission(req):
            continue
        rows.append({
            "type": model._meta.label_lower, "name": str(model._meta.verbose_name_plural),
            "can": [w for w, ok in (("add", model_admin.has_add_permission(req)), ("change", model_admin.has_change_permission(req)),
                                    ("delete", model_admin.has_delete_permission(req))) if ok],
        })
    return Result(sorted(rows, key=lambda r: r["type"]))


@tool(AREA, "describe_record_type",
      "Show the fields of a record type as the admin's add/edit form has them (type, required, choices, help text), "
      "the filters you can search by, and the bulk actions the admin offers for it. Read this before creating or editing.",
      {"type": {"type": "string", "description": "e.g. accounts.user, courses.lesson"}}, ["type"])
def describe_record_type(ctx, args):
    model, model_admin = _resolve(ctx, args.get("type"))
    form = model_admin.get_form(ctx.request, None, change=False)()
    fields = []
    for name, f in form.fields.items():
        item = {"name": name, "type": type(f).__name__.replace("Field", "").lower() or "text", "required": f.required}
        if f.help_text:
            item["help"] = short(f.help_text, 160)
        choices = getattr(f, "choices", None)
        if choices is not None and not hasattr(f, "queryset"):
            item["choices"] = [str(c[0]) for c in list(choices)[:30] if c[0] != ""]
        if hasattr(f, "queryset"):
            item["choices_from"] = f.queryset.model._meta.label_lower + " (pass ids)"
        fields.append(item)
    actions = [{"name": name, "label": str(desc)} for name, (_fn, _n, desc) in model_admin.get_actions(ctx.request).items()
               if name != "delete_selected"]
    return Result({
        "type": model._meta.label_lower, "name": str(model._meta.verbose_name_plural),
        "form_fields": fields, "search_covers": list(model_admin.search_fields),
        "filters": [f if isinstance(f, str) else getattr(f, "__name__", str(f)) for f in model_admin.list_filter],
        "bulk_actions": actions,
    })


@tool(AREA, "search_records",
      "Find records of one type. 'query' uses the admin search box; 'filters' are exact field lookups such as "
      "{\"role\": \"facilitator\", \"is_approved\": false} or {\"date_joined__gte\": \"2026-10-01\"}. Returns at most 50 rows "
      "and says how many matched in total.",
      {
          "type": {"type": "string"},
          "query": {"type": "string", "description": "Words to search for, as typed in the admin search box"},
          "filters": {"type": "object", "description": "Field lookups, e.g. {\"tier__name\": \"Foundational\"}"},
          "order_by": {"type": "string", "description": "A field name, '-' first for newest/highest first"},
          "limit": {"type": "integer", "description": "1 to 50, default 20"},
          "offset": {"type": "integer"},
      }, ["type"])
def search_records(ctx, args):
    model, model_admin = _resolve(ctx, args.get("type"))
    qs = model_admin.get_queryset(ctx.request)
    query = (args.get("query") or "").strip()
    if query:
        qs, may_have_duplicates = model_admin.get_search_results(ctx.request, qs, query)
        if may_have_duplicates:
            qs = qs.distinct()
    filters = json_arg(args.get("filters"), "filters")
    for key, value in filters.items():
        parts = key.split("__")
        if any(p in SECRET_FIELDS for p in parts):
            raise ToolError(f"Searching by {key} is not allowed.")
        if parts[-1] not in LOOKUPS and len(parts) > 3:
            raise ToolError(f"Filter {key} is too deep. Use at most two related steps.")
    try:
        if filters:
            qs = qs.filter(**filters)
            if any(lookup_spawns_duplicates(model._meta, k) for k in filters):
                qs = qs.distinct()
        order = (args.get("order_by") or "").strip()
        if order and order.lstrip("-").split("__")[0] not in SECRET_FIELDS:
            qs = qs.order_by(order)
        total = qs.count()
        limit = max(1, min(LIST_LIMIT, int(args.get("limit") or 20)))
        offset = max(0, int(args.get("offset") or 0))
        rows = [_row(o, model_admin) for o in qs[offset:offset + limit]]
    except (FieldError, ValueError, ValidationError, TypeError) as err:
        raise ToolError(f"That search did not work: {short(err, 200)}. Check the field names with describe_record_type.")
    return Result({"type": model._meta.label_lower, "showing": f"{len(rows)} of {total}" + (f", from {offset + 1}" if offset else ""),
                   "rows": rows})


@tool(AREA, "get_record",
      "Read one record in full: every field (long text is shortened unless you name the field in 'fields'), plus its admin link.",
      {"type": {"type": "string"}, "id": {"type": "string"},
       "fields": {"type": "array", "items": {"type": "string"}, "description": "Only these fields, shown in full (e.g. a lesson's content)"}},
      ["type", "id"])
def get_record(ctx, args):
    model, model_admin = _resolve(ctx, args.get("type"))
    obj = _object(ctx, model, model_admin, args.get("id"))
    wanted = set(args.get("fields") or [])
    data = {"id": obj.pk, "name": str(obj)}
    for f in _fields(model):
        if wanted and f.name not in wanted:
            continue
        data[f.name] = _value(obj, f, full=bool(wanted))
    return Result({"type": model._meta.label_lower, "record": data, "admin_link": _admin_url(obj)}, link=_admin_url(obj))


@tool(AREA, "platform_overview",
      "The admin dashboard's numbers and its 'Needs your attention' list: learners, enrolments, completions, unread "
      "contact messages, payments in the last 30 days, facilitators waiting for approval, consent waiting, and so on.")
def platform_overview(ctx, args):
    _staff(ctx)
    from core.admin import _dashboard_data

    data = _dashboard_data()
    return Result({
        "cards": [{"label": c["label"], "value": c["value"], "detail": c["sub"]} for c in data["cards"]],
        "needs_attention": [a["text"] for a in data["attention"]],
        "courses": [{"title": c["title"], "tier": c["tier"], "enrolled": c["enrollments"], "completion_percent": c["rate"]} for c in data["courses"]],
        "newest_members": [f"{u.get_full_name() or u.username} ({u.get_role_display()})" for u in data["recent_users"]],
    })


@tool(AREA, "monthly_report",
      "The monthly programme report (as on Tools > Monthly report): new learners, active learners, lessons, labs, quizzes, "
      "pass rate, courses completed, hardest lessons, counties and schools.",
      {"month": {"type": "string", "description": "YYYY-MM, default this month"}})
def monthly_report(ctx, args):
    _staff(ctx)
    from core.admin_tools import build_report, month_bounds

    first, start, end = month_bounds(args.get("month") or "")
    r = build_report(first, start, end)
    keep = ["new_learners", "new_parents", "new_facilitators", "new_classes", "active_learners", "lessons_completed",
            "labs_completed", "quizzes_taken", "quiz_pass_rate", "quiz_avg", "courses_completed", "badges", "total_learners",
            "total_parents_linked", "total_classes", "total_schools", "total_counties", "pending_consent"]
    out = {"month": first.strftime("%B %Y"), **{k: r[k] for k in keep}}
    out["courses"] = [{"course": c["course"].title, "lessons_completed": c["completions"], "learners": c["learners"],
                       "completed_course": c["graduates"]} for c in r["course_rows"]]
    out["hardest_lessons"] = [{"lesson": h["lesson__title"], "average": round(h["avg"]), "attempts": h["n"]} for h in r["hard"]]
    out["counties"], out["schools"] = r["counties"], r["schools"]
    return Result(out)


# ---------------------------------------------------------------- writing

def _save_with_admin(ctx, model_admin, form, obj, change):
    obj = model_admin.save_form(ctx.request, form, change=change)
    model_admin.save_model(ctx.request, obj, form, change)
    model_admin.save_related(ctx.request, form, formsets=[], change=change)
    message = model_admin.construct_change_message(ctx.request, form, None, add=not change)
    if change:
        model_admin.log_change(ctx.request, obj, message)
    else:
        model_admin.log_addition(ctx.request, obj, message)
    return obj


def _describe_create(ctx, args):
    model, _ma = _resolve(ctx, args.get("type"))
    values = json_arg(args.get("values"), "values")
    shown = ", ".join(f"{k} {short(v, 40)}" for k, v in list(values.items())[:4] if "password" not in k)
    return f"Create a {model._meta.verbose_name}" + (f" with {shown}" if shown else "")


def _undo_create(ctx, info):
    model, model_admin = _resolve(ctx, info["type"])
    obj = model._default_manager.filter(pk=info["id"]).first()
    if obj is None:
        return "It was already gone."
    if not model_admin.has_delete_permission(ctx.request, obj):
        raise ToolError("You don't have permission to delete it.")
    _deleted, _count, perms_needed, protected = model_admin.get_deleted_objects([obj], ctx.request)
    if perms_needed or protected:
        raise ToolError("It can't be removed now: other records depend on it.")
    model_admin.log_deletions(ctx.request, model._default_manager.filter(pk=obj.pk))
    model_admin.delete_model(ctx.request, obj)
    return f"Removed the {model._meta.verbose_name} it created."


@tool(AREA, "create_record",
      "Create a record through the admin's own add form, so the same validation and save rules apply. Read "
      "describe_record_type first for the field names. Related records are given by id; many-to-many by a list of ids. "
      "Files cannot be uploaded this way.",
      {"type": {"type": "string"}, "values": {"type": "object", "description": "Field name -> value"}}, ["type", "values"],
      writes=True, describe=_describe_create, undo=_undo_create)
def create_record(ctx, args):
    model, model_admin = _resolve(ctx, args.get("type"))
    if not model_admin.has_add_permission(ctx.request):
        raise ToolError(f"You don't have permission to add {model._meta.verbose_name_plural}.")
    form_class = model_admin.get_form(ctx.request, None, change=False)
    form = form_class(data=form_data(form_class, values=json_arg(args.get("values"), "values")), files={})
    if not form.is_valid():
        raise ToolError(f"Not saved. {form_errors(form)}")
    with transaction.atomic():
        obj = _save_with_admin(ctx, model_admin, form, None, change=False)
    link = _admin_url(obj)
    return Result({"created": str(obj), "id": obj.pk, "admin_link": link, "notes": ctx.notes()},
                  undo={"type": model._meta.label_lower, "id": obj.pk}, undo_label="Delete it", link=link)


def _describe_update(ctx, args):
    model, model_admin = _resolve(ctx, args.get("type"))
    obj = _object(ctx, model, model_admin, args.get("id"))
    values = json_arg(args.get("values"), "values")
    changes = ", ".join(f"{k} to {short(v, 50)!s}" for k, v in list(values.items())[:4] if "password" not in k)
    more = f" and {len(values) - 4} more" if len(values) > 4 else ""
    return f"Change {model._meta.verbose_name} \"{short(obj, 60)}\": set {changes}{more}"


def _undo_restore(ctx, info):
    model, model_admin = _resolve(ctx, info["type"])
    if changed_since(model, info["id"], info.get("after")):
        raise ToolError("It has been changed again since, so undo would overwrite that. Edit it by hand instead.")
    obj = model._default_manager.get(pk=info["id"])
    if not model_admin.has_change_permission(ctx.request, obj):
        raise ToolError("You don't have permission to change it.")
    obj = restore(info["before"])
    model_admin.log_change(ctx.request, obj, "Undid a change made with the assistant.")
    return f"Put {model._meta.verbose_name} \"{short(obj, 60)}\" back as it was."


@tool(AREA, "update_record",
      "Change some fields of one record through the admin's edit form. Only the fields you pass change; every other "
      "field keeps its value. Read the record first with get_record.",
      {"type": {"type": "string"}, "id": {"type": "string"},
       "values": {"type": "object", "description": "Only the fields to change, e.g. {\"is_approved\": true}"}},
      ["type", "id", "values"], writes=True, describe=_describe_update, undo=_undo_restore)
def update_record(ctx, args):
    model, model_admin = _resolve(ctx, args.get("type"))
    obj = _object(ctx, model, model_admin, args.get("id"))
    if not model_admin.has_change_permission(ctx.request, obj):
        raise ToolError(f"You don't have permission to change this {model._meta.verbose_name}.")
    values = json_arg(args.get("values"), "values")
    if not values:
        raise ToolError("Say which fields to change.")
    before = snapshot(obj)
    form_class = model_admin.get_form(ctx.request, obj, change=True)
    form = form_class(data=form_data(form_class, instance=obj, values=values), files={}, instance=obj)
    if not form.is_valid():
        raise ToolError(f"Not saved. {form_errors(form)}")
    if not form.changed_data:
        return Result({"changed": [], "message": "Nothing changed: it already had those values."})
    with transaction.atomic():
        obj = _save_with_admin(ctx, model_admin, form, obj, change=True)
    link = _admin_url(obj)
    return Result({"changed": form.changed_data, "record": str(obj), "admin_link": link, "notes": ctx.notes()},
                  undo={"type": model._meta.label_lower, "id": obj.pk, "before": before, "after": fresh_snapshot(obj)}, link=link)


def _describe_delete(ctx, args):
    model, model_admin = _resolve(ctx, args.get("type"))
    obj = _object(ctx, model, model_admin, args.get("id"))
    _deleted, counts, _perms, _protected = model_admin.get_deleted_objects([obj], ctx.request)
    others = sum(counts.values()) - 1
    tail = f", with {others} linked record{'s' if others != 1 else ''} that go with it" if others > 0 else ""
    return f"Delete {model._meta.verbose_name} \"{short(obj, 60)}\" for good{tail}"


@tool(AREA, "delete_record",
      "Delete one record, exactly like the admin's Delete button (records that depend on it go too). This cannot be undone. "
      "Always ask yourself whether archiving or deactivating would do instead.",
      {"type": {"type": "string"}, "id": {"type": "string"}}, ["type", "id"],
      writes=True, always_confirm=True, describe=_describe_delete)
def delete_record(ctx, args):
    model, model_admin = _resolve(ctx, args.get("type"))
    obj = _object(ctx, model, model_admin, args.get("id"))
    if not model_admin.has_delete_permission(ctx.request, obj):
        raise ToolError(f"You don't have permission to delete this {model._meta.verbose_name}.")
    _deleted, counts, perms_needed, protected = model_admin.get_deleted_objects([obj], ctx.request)
    if perms_needed:
        raise ToolError(f"Deleting it would also delete {', '.join(sorted(perms_needed))}, which you don't have permission to delete.")
    if protected:
        raise ToolError(f"It can't be deleted while these depend on it: {', '.join(short(p, 60) for p in list(protected)[:5])}.")
    name = str(obj)
    with transaction.atomic():
        model_admin.log_deletions(ctx.request, model._default_manager.filter(pk=obj.pk))
        model_admin.delete_model(ctx.request, obj)
    return Result({"deleted": name, "with": {str(k): v for k, v in counts.items()}})


def _describe_action(ctx, args):
    model, model_admin = _resolve(ctx, args.get("type"))
    actions = model_admin.get_actions(ctx.request)
    label = str(actions[args.get("action")][2]) if args.get("action") in actions else args.get("action")
    ids = args.get("ids") or []
    names = [short(o, 40) for o in model_admin.get_queryset(ctx.request).filter(pk__in=ids)[:3]]
    more = f" and {len(ids) - 3} more" if len(ids) > 3 else ""
    return f"{label} for {', '.join(names)}{more}"


@tool(AREA, "run_bulk_action",
      "Run one of the admin's bulk actions (the 'Action' menu above a list) on chosen records, e.g. approve facilitators "
      "and email them, mark contact messages handled, rebuild a module exam. describe_record_type lists them.",
      {"type": {"type": "string"}, "action": {"type": "string", "description": "The action's name"},
       "ids": {"type": "array", "items": {"type": "string"}}}, ["type", "action", "ids"],
      writes=True, always_confirm=True, describe=_describe_action)
def run_bulk_action(ctx, args):
    model, model_admin = _resolve(ctx, args.get("type"))
    actions = model_admin.get_actions(ctx.request)
    name = args.get("action")
    if name == "delete_selected":
        raise ToolError("Use delete_record to delete, one record at a time.")
    if name not in actions:
        raise ToolError(f"No bulk action called {name}. Available: {', '.join(a for a in actions if a != 'delete_selected')}.")
    ids = [str(i) for i in args.get("ids") or []][:200]
    queryset = model_admin.get_queryset(ctx.request).filter(pk__in=ids)
    if not queryset.exists():
        raise ToolError("None of those records were found.")
    func = actions[name][0]
    with transaction.atomic():
        func(model_admin, ctx.request, queryset)
    return Result({"ran": str(actions[name][2]), "records": queryset.count(), "notes": ctx.notes()})
