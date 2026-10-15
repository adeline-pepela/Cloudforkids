"""The assistant's loop: ask the model, run (or hold for approval) the tools it asks for, feed the results back, repeat.

A reply row exists before the model has said anything, so the panel has somewhere to watch while text streams in.
The loop stops when the model answers without tools, when a change needs approval (it resumes from that exact point
once every pending change is approved or declined), when the person presses Stop, or after max_rounds steps.
"""

import json
import logging
import threading

from django.conf import settings as django_settings
from django.db import close_old_connections, connections, transaction
from django.utils import timezone

from . import providers, tools
from .access import can_use, default_connection
from .context import system_prompt
from .crypto import KeyUnreadable
from .models import Action, AssistantSettings, Thread, Turn

logger = logging.getLogger(__name__)

RESULT_LIMIT = 12000
HISTORY_USER_TURNS = 12  # older turns are left out of the request (the panel still shows them)
FILES_FOR_TURNS = 3  # images and PDFs travel with the last few messages only; older ones become a short note
DECLINED = "The person declined this, so it was not done. Do not try it again unless they ask."
SUPERSEDED = "Not done: the person sent a new message instead of approving this. Do not try it again unless they ask."


def start(thread, meta):
    """Run the loop for a thread in the background (inline while testing)."""
    Thread.objects.filter(pk=thread.pk).update(busy=True, cancel=False, updated_at=timezone.now())
    if getattr(django_settings, "ASSISTANT_INLINE", False):
        run(thread.pk, meta, inline=True)
        return
    threading.Thread(target=run, args=(thread.pk, meta), daemon=True, name=f"assistant-{thread.pk}").start()


def run(thread_id, meta, inline=False):
    if not inline:
        close_old_connections()
    try:
        _run(thread_id, meta)
    except Exception:
        logger.exception("Assistant loop failed for thread %s", thread_id)
        Turn.objects.filter(thread_id=thread_id, streaming=True).update(
            streaming=False, failed=True, error="Something went wrong on our side. Nothing more was changed. Try again.")
    finally:
        Thread.objects.filter(pk=thread_id).update(busy=False, cancel=False)
        if not inline:
            connections.close_all()


def _say(thread, text, failed=False):
    return Turn.objects.create(thread=thread, role=Turn.Role.ASSISTANT, text="" if failed else text, error=text if failed else "", failed=failed)


def _run(thread_id, meta):
    thread = Thread.objects.select_related("user", "connection").get(pk=thread_id)
    user, settings = thread.user, AssistantSettings.load()
    if not can_use(user, thread.area, settings):
        _say(thread, "The assistant is switched off for your account.", failed=True)
        return
    conn = thread.connection or default_connection()
    if conn is None:
        _say(thread, "No AI provider is set up yet. An admin can add one in Admin > Tools > AI assistant.", failed=True)
        return
    try:
        key = conn.api_key()
    except KeyUnreadable as err:
        _say(thread, str(err), failed=True)
        return

    ctx = tools.Ctx(user=user, area=thread.area, meta=meta, thread=thread)
    offered = [t for t in tools.tools_for(thread.area) if not (settings.read_only and t.writes)]
    specs = [t.spec() for t in offered]
    last_user = thread.turns.filter(role=Turn.Role.USER).order_by("-created_at", "-id").first()
    system = system_prompt(user, thread.area, settings, last_user.screen if last_user else None)

    for _round in range(settings.max_rounds):
        if Thread.objects.filter(pk=thread.pk, cancel=True).exists():
            _say(thread, "Stopped.")
            return
        Thread.objects.filter(pk=thread.pk).update(updated_at=timezone.now())  # still alive
        history = build_history(thread)
        turn = Turn.objects.create(thread=thread, role=Turn.Role.ASSISTANT, streaming=True, model=conn.tag)

        def on_delta(text, reasoning, pk=turn.pk):
            Turn.objects.filter(pk=pk).update(text=text, reasoning=reasoning)

        try:
            reply = providers.chat(conn.provider, conn.model, key, system, history, specs, on_delta)
        except providers.ProviderError as err:
            Turn.objects.filter(pk=turn.pk).update(streaming=False, failed=True, error=str(err)[:500])
            return
        turn.text, turn.reasoning, turn.tool_calls, turn.raw = reply.text, reply.reasoning, reply.tool_calls, reply.raw
        turn.usage, turn.streaming = reply.usage or None, False
        if not reply.text and not reply.tool_calls:
            turn.failed, turn.error = True, f"The model stopped without answering ({reply.stop_reason or 'no reason given'}). Try again or switch model."
        turn.save()
        if not reply.tool_calls:
            return
        if dispatch(thread, turn, reply.tool_calls, ctx, settings):
            return  # waiting for the person to approve or decline
    _say(thread, f"I stopped after {settings.max_rounds} steps so this doesn't run on. Say \"carry on\" if you want me to continue.")


def build_history(thread):
    """The conversation in the normalised shape. Every tool call is followed by its result, always."""
    turns = list(thread.turns.order_by("created_at", "id"))
    user_idx = [i for i, t in enumerate(turns) if t.role == Turn.Role.USER]
    if len(user_idx) > HISTORY_USER_TURNS:
        turns = turns[user_idx[-HISTORY_USER_TURNS]:]
    results = {t.call_id: t for t in turns if t.role == Turn.Role.TOOL}
    recent = {t.pk for t in [t for t in turns if t.role == Turn.Role.USER][-FILES_FOR_TURNS:]}
    out = []
    for t in turns:
        if t.role == Turn.Role.USER:
            files = []
            for f in t.files or []:
                if f.get("kind") == "text" or t.pk in recent:
                    files.append(f)
                else:
                    files.append({"name": f.get("name"), "kind": "text", "text": "(attached earlier; ask the person to attach it again to look at it)"})
            out.append({"role": "user", "text": t.text, "files": files})
        elif t.role == Turn.Role.ASSISTANT:
            if t.streaming or (t.failed and not t.tool_calls):
                continue
            out.append({"role": "assistant", "text": t.text, "tool_calls": t.tool_calls or [], "raw": t.raw, "model": t.model})
            for call in t.tool_calls or []:
                r = results.get(call["id"])
                out.append({"role": "tool", "call_id": call["id"], "name": call["name"],
                            "text": r.text if r else "No result (it was interrupted).", "failed": bool(r.failed) if r else True})
    return out


def dispatch(thread, turn, calls, ctx, settings):
    """Run each call, or hold it for approval. Returns True if anything is waiting for the person."""
    waiting = False
    for call in calls:
        name, args = call.get("name", ""), call.get("args")
        tool = tools.get(name)
        if not isinstance(args, dict):
            args = {}
        known = tool is not None and tool.area == thread.area
        action = Action.objects.create(
            thread=thread, turn=turn, user=thread.user, call_id=call["id"], tool=name[:60], args=args,
            writes=bool(known and tool.writes), summary=(tool.sentence(ctx, args) if known else f"Use {name}")[:300],
            status=Action.Status.PENDING,
        )
        if not known:
            finish(action, f"There is no tool called {name} here.", failed=True)
            continue
        missing = [p for p in tool.parameters.get("required", []) if args.get(p) in (None, "")]
        if missing:
            finish(action, f"Missing: {', '.join(missing)}.", failed=True)
        elif tool.writes and settings.read_only:
            finish(action, "Read-only mode is on, so nothing was changed. An admin can turn it off in the assistant settings.", failed=True)
        elif tool.writes and (settings.confirm_writes or tool.must_confirm(args)):
            waiting = True
        else:
            execute(action, tool, ctx)
    return waiting


def execute(action, tool, ctx):
    ctx.request._messages = tools._Collected()
    try:
        with transaction.atomic():
            result = tool.run(ctx, action.args)
    except tools.ToolError as err:
        finish(action, str(err), failed=True)
        return
    except Exception:
        logger.exception("Assistant tool %s failed", tool.name)
        finish(action, "Something went wrong on our side while doing this. Nothing was saved.", failed=True)
        return
    if tool.undo and result.undo:
        action.undo, action.undo_label = result.undo, result.undo_label
    action.link = result.link or ""
    finish(action, json.dumps(result.data, ensure_ascii=False, default=str))


def finish(action, text, failed=False, status=None):
    if len(text) > RESULT_LIMIT:
        text = text[:RESULT_LIMIT] + " … [cut short: ask for less, or for one record at a time]"
    action.status = status or (Action.Status.FAILED if failed else Action.Status.DONE)
    action.result = text
    action.decided_at = timezone.now()
    action.save()
    Turn.objects.update_or_create(
        thread=action.thread, role=Turn.Role.TOOL, call_id=action.call_id,
        defaults={"tool_name": action.tool, "text": text, "failed": failed or action.status == Action.Status.DECLINED},
    )


def decide(action, approve, meta):
    """The person approved or declined a held change. Resume the loop once nothing in that reply is still waiting."""
    settings = AssistantSettings.load()
    thread = action.thread
    if approve:
        tool = tools.get(action.tool)
        if settings.read_only:
            finish(action, "Read-only mode is on, so nothing was changed.", failed=True)
        else:
            execute(action, tool, tools.Ctx(user=action.user, area=thread.area, meta=meta, thread=thread))
    else:
        finish(action, DECLINED, status=Action.Status.DECLINED)
    if not action.turn.actions.filter(status=Action.Status.PENDING).exists():
        start(thread, meta)


def supersede_pending(thread):
    """A new message while changes wait for approval: those changes are dropped, and the model is told so."""
    for action in thread.actions.filter(status=Action.Status.PENDING):
        finish(action, SUPERSEDED, status=Action.Status.DECLINED)


def undo(action, meta):
    tool = tools.get(action.tool)
    if action.status != Action.Status.DONE or not action.undo or tool is None or tool.undo is None:
        raise tools.ToolError("This can't be undone.")
    if AssistantSettings.load().read_only:
        raise tools.ToolError("Read-only mode is on, so nothing can be changed, undo included.")
    ctx = tools.Ctx(user=action.user, area=action.thread.area, meta=meta, thread=action.thread)
    with transaction.atomic():
        message = tool.undo(ctx, action.undo)
    action.status = Action.Status.UNDONE
    action.save(update_fields=["status"])
    Turn.objects.filter(thread=action.thread, role=Turn.Role.TOOL, call_id=action.call_id).update(
        text=f"{action.result}\n[Afterwards the person pressed Undo: {message}]")
    return message
