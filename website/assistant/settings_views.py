"""Admin > Tools > AI assistant: provider connections (tested before they can be saved), switches and the activity log.
Super admins only. A key goes in once and never comes back out: pages and responses show its last four characters."""

import json

from django import forms
from django.contrib import admin, messages
from django.core import signing
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import providers
from .access import connections_changed
from .crypto import fingerprint, seal
from .models import Action, AssistantSettings, Connection

TEST_SALT = "assistant-connection-test"
TEST_VALID_FOR = 30 * 60  # a passed test lets you save within 30 minutes


class SettingsForm(forms.ModelForm):
    class Meta:
        model = AssistantSettings
        fields = ["enabled", "for_admins", "for_tutors", "read_only", "confirm_writes", "max_rounds"]


def _superuser(view):
    def wrapper(request, *args, **kwargs):
        if not request.user.is_superuser:
            if request.headers.get("Accept", "").startswith("application/json") or request.method == "POST" and request.content_type == "application/json":
                return JsonResponse({"ok": False, "error": "Only a super admin can change the assistant's settings."}, status=403)
            messages.error(request, "Only a super admin can change the assistant's settings.")
            return redirect("admin:index")
        return view(request, *args, **kwargs)
    wrapper.__name__ = view.__name__
    return wrapper


def _body(request):
    try:
        data = json.loads(request.body or b"{}")
    except ValueError:
        data = {}
    return data if isinstance(data, dict) else {}


def _fields(data):
    provider = str(data.get("provider") or "")
    model = str(data.get("model") or "").strip()[:100]
    key = str(data.get("key") or "").strip()
    if provider not in providers.PROVIDERS:
        raise ValueError("Choose a provider.")
    if not model:
        raise ValueError("Choose or type a model.")
    if len(key) < 8:
        raise ValueError("Paste the API key.")
    return provider, model, key


@_superuser
def settings_page(request):
    current = AssistantSettings.load()
    form = SettingsForm(request.POST or None, instance=AssistantSettings.objects.get(pk=current.pk))
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Assistant settings saved.")
        return redirect("tools:assistant_settings")
    provider_info = {k: {"label": v["label"], "models": v["models"], "hint": v["key_hint"]} for k, v in providers.PROVIDERS.items()}
    context = {
        **admin.site.each_context(request), "title": "AI assistant", "form": form,
        "connections": Connection.objects.select_related("saved_by"),
        "providers": provider_info,
        "activity": Action.objects.filter(writes=True).exclude(status=Action.Status.PENDING).select_related("user").order_by("-created_at")[:40],
    }
    return render(request, "admin/assistant_settings.html", context)


@_superuser
@require_POST
def test(request):
    try:
        provider, model, key = _fields(_body(request))
        reply = providers.test_connection(provider, model, key)
    except (ValueError, providers.ProviderError) as err:
        return JsonResponse({"ok": False, "error": str(err)})
    token = signing.dumps({"fp": fingerprint(provider, model, key)}, salt=TEST_SALT)
    return JsonResponse({"ok": True, "reply": reply, "token": token})


@_superuser
@require_POST
def models(request):
    data = _body(request)
    provider, key = str(data.get("provider") or ""), str(data.get("key") or "").strip()
    if provider not in providers.PROVIDERS or len(key) < 8:
        return JsonResponse({"ok": False, "error": "Choose a provider and paste the key first."})
    try:
        found = providers.list_models(provider, key)
    except providers.ProviderError as err:
        return JsonResponse({"ok": False, "error": str(err)})
    return JsonResponse({"ok": True, "models": found[:150]})


@_superuser
@require_POST
def save(request):
    data = _body(request)
    try:
        provider, model, key = _fields(data)
    except ValueError as err:
        return JsonResponse({"ok": False, "error": str(err)})
    try:
        passed = signing.loads(str(data.get("token") or ""), salt=TEST_SALT, max_age=TEST_VALID_FOR)
    except signing.BadSignature:
        return JsonResponse({"ok": False, "error": "Test the connection first. Save works only after a test passes with this exact key and model."})
    if passed.get("fp") != fingerprint(provider, model, key):
        return JsonResponse({"ok": False, "error": "The key or model changed after the test. Test again, then save."})
    make_default = bool(data.get("make_default")) or not Connection.objects.exists()
    if make_default:
        Connection.objects.update(is_default=False)
    conn = Connection.objects.create(
        provider=provider, model=model, label=str(data.get("label") or "").strip()[:80], key_sealed=seal(key),
        key_last4=key[-4:], is_default=make_default, tested_at=timezone.now(), saved_by=request.user,
    )
    connections_changed()
    messages.success(request, f"Saved {conn.display_name}.")
    return JsonResponse({"ok": True})


@_superuser
@require_POST
def retest(request, pk):
    conn = Connection.objects.filter(pk=pk).first()
    if conn is None:
        return JsonResponse({"ok": False, "error": "That connection is gone."})
    try:
        reply = providers.test_connection(conn.provider, conn.model, conn.api_key())
    except Exception as err:  # KeyUnreadable or ProviderError, both written for people
        return JsonResponse({"ok": False, "error": str(err)})
    conn.tested_at = timezone.now()
    conn.save(update_fields=["tested_at"])
    return JsonResponse({"ok": True, "reply": reply})


@_superuser
@require_POST
def make_default(request, pk):
    conn = Connection.objects.filter(pk=pk).first()
    if conn:
        Connection.objects.update(is_default=False)
        Connection.objects.filter(pk=pk).update(is_default=True)
        messages.success(request, f"{conn.display_name} is now the default.")
    return redirect("tools:assistant_settings")


@_superuser
@require_POST
def remove(request, pk):
    conn = Connection.objects.filter(pk=pk).first()
    if conn:
        was_default = conn.is_default
        conn.delete()
        if was_default:
            nxt = Connection.objects.order_by("-saved_at").first()
            if nxt:
                Connection.objects.filter(pk=nxt.pk).update(is_default=True)
        connections_changed()
        messages.success(request, f"Removed {conn.display_name}. Its key is deleted.")
    return redirect("tools:assistant_settings")
