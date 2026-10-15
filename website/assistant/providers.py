"""Talking to AI providers without their SDKs: one normalised request/reply shape and one adapter per wire format.

Three dialects cover the four providers:
  anthropic  Claude's Messages API
  gemini     Google's generateContent
  openai     /chat/completions, which OpenAI and DeepSeek both speak

Normalised history (a list of dicts):
  {"role": "user", "text": ...}
  {"role": "assistant", "text": ..., "tool_calls": [{"id", "name", "args"}], "raw": <provider blocks>, "model": "provider:model"}
  {"role": "tool", "call_id": ..., "name": ..., "text": ..., "failed": bool}

`raw` keeps the provider's own content (Claude's signed thinking blocks, Gemini's thought signatures) so a turn can be
replayed exactly while the model is unchanged. When the model changes it is dropped and the turn is rebuilt from text.
"""

import json
import logging
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

TIMEOUT = 120  # seconds to wait for each piece of a reply
ANTHROPIC_VERSION = "2023-06-01"
MAX_TOKENS = 8192

PROVIDERS = {
    "anthropic": {
        "dialect": "anthropic", "base": "https://api.anthropic.com/v1", "label": "Claude (Anthropic)",
        "models": ["claude-sonnet-5-5", "claude-opus-5-5", "claude-haiku-5-5", "claude-fable-5-1"],
        "key_hint": "Starts with sk-ant-. Create one at console.anthropic.com > API keys.",
    },
    "openai": {
        "dialect": "openai", "base": "https://api.openai.com/v1", "label": "OpenAI",
        "models": ["gpt-5-mini", "gpt-5", "gpt-4.1", "gpt-4.1-mini", "gpt-4o-mini"],
        "key_hint": "Starts with sk-. Create one at platform.openai.com > API keys.",
    },
    "gemini": {
        "dialect": "gemini", "base": "https://generativelanguage.googleapis.com/v1beta", "label": "Gemini (Google)",
        "models": ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.5-flash-lite"],
        "key_hint": "Create one at aistudio.google.com > Get API key.",
    },
    "deepseek": {
        "dialect": "openai", "base": "https://api.deepseek.com", "label": "DeepSeek",
        "models": ["deepseek-chat", "deepseek-reasoner"],
        "key_hint": "Starts with sk-. Create one at platform.deepseek.com > API keys.",
    },
}


class ProviderError(Exception):
    """The provider refused or failed. The message is written for the person reading it."""


@dataclass
class Reply:
    text: str = ""
    reasoning: str = ""
    tool_calls: list = field(default_factory=list)
    raw: object = None
    stop_reason: str = ""
    usage: dict = field(default_factory=dict)


def new_call_id():
    return "call_" + secrets.token_hex(8)


# ---------------------------------------------------------------- HTTP and server-sent events

def _open(url, payload=None, headers=None, method=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method or ("POST" if data else "GET"), headers={
        "Content-Type": "application/json", "User-Agent": "cloudforkids-assistant/1.0", **(headers or {}),
    })
    try:
        return urllib.request.urlopen(req, timeout=TIMEOUT)
    except urllib.error.HTTPError as err:
        body = err.read().decode("utf-8", "replace")
        raise ProviderError(_explain(err.code, body)) from None
    except urllib.error.URLError as err:
        raise ProviderError(f"Could not reach the provider ({err.reason}). Check the server's internet connection.") from None
    except TimeoutError:
        raise ProviderError("The provider took too long to answer. Try again.") from None


def _explain(status, body):
    detail = body
    try:
        parsed = json.loads(body)
        if isinstance(parsed, list) and parsed:
            parsed = parsed[0]
        err = parsed.get("error", parsed) if isinstance(parsed, dict) else {}
        detail = err.get("message") or err.get("msg") or body if isinstance(err, dict) else str(err)
    except (ValueError, AttributeError):
        pass
    detail = " ".join(str(detail).split())[:300]
    if status in (401, 403):
        lead = "The provider refused the key"
    elif status == 404:
        lead = "The provider does not know this model or address"
    elif status == 429:
        lead = "The provider says the account is over its rate limit or out of credit"
    elif status >= 500:
        lead = "The provider had a problem on its side"
    else:
        lead = "The provider rejected the request"
    return f"{lead} ({status}): {detail}" if detail else f"{lead} ({status})."


def iter_sse(chunks):
    """Yield (event, data) from server-sent events. Frames end at a blank line; a network chunk can hold part of a
    frame or several frames, so everything is buffered until a whole frame has arrived."""
    buffer = ""
    for chunk in chunks:
        buffer += chunk.decode("utf-8", "replace") if isinstance(chunk, bytes) else chunk
        buffer = buffer.replace("\r\n", "\n").replace("\r", "\n")
        while "\n\n" in buffer:
            frame, buffer = buffer.split("\n\n", 1)
            parsed = _frame(frame)
            if parsed:
                yield parsed
    if buffer.strip():
        parsed = _frame(buffer)
        if parsed:
            yield parsed


def _frame(frame):
    event, data = "", []
    for line in frame.split("\n"):
        if not line or line.startswith(":"):
            continue
        name, _, value = line.partition(":")
        value = value[1:] if value.startswith(" ") else value
        if name == "event":
            event = value
        elif name == "data":
            data.append(value)
    if not data:
        return None
    return event, "\n".join(data)


def _chunks(response):
    """Read a streaming response as it arrives (line by line works with chunked transfer encoding)."""
    with response:
        for line in response:
            yield line


class _Throttle:
    """Call on_delta with the whole text so far, at most every `every` seconds (and always at the end)."""

    def __init__(self, on_delta, every=0.18):
        self.on_delta, self.every, self.last = on_delta, every, 0.0

    def __call__(self, text, reasoning, force=False):
        if not self.on_delta:
            return
        now = time.monotonic()
        if force or now - self.last >= self.every:
            self.last = now
            self.on_delta(text, reasoning)


# ---------------------------------------------------------------- public entry points

def chat(provider, model, key, system, messages, tools=(), on_delta=None, base=None):
    """Send one request and stream the reply. `tools` are {"name", "description", "parameters"} with JSON Schema."""
    info = PROVIDERS.get(provider)
    if not info:
        raise ProviderError(f"Unknown provider {provider}.")
    base = (base or info["base"]).rstrip("/")
    tag = f"{provider}:{model}"
    throttle = _Throttle(on_delta)
    dialect = info["dialect"]
    if dialect == "anthropic":
        return _anthropic(base, model, key, system, messages, list(tools), throttle, tag)
    if dialect == "gemini":
        return _gemini(base, model, key, system, messages, list(tools), throttle, tag)
    return _openai(provider, base, model, key, system, messages, list(tools), throttle, tag)


def test_connection(provider, model, key):
    """A tiny real request with this exact key and model. Returns the reply text or raises ProviderError."""
    reply = chat(provider, model, key, "You are checking a connection. Reply with the single word OK.",
                 [{"role": "user", "text": "Reply with OK."}])
    if not (reply.text or reply.reasoning).strip():
        raise ProviderError("The provider answered, but with an empty reply. Try another model.")
    return reply.text.strip()[:200] or "(it replied with reasoning only)"


def list_models(provider, key):
    """Model ids the key can use, straight from the provider."""
    info = PROVIDERS[provider]
    base = info["base"].rstrip("/")
    if info["dialect"] == "anthropic":
        res = _open(f"{base}/models?limit=100", headers={"x-api-key": key, "anthropic-version": ANTHROPIC_VERSION})
        ids = [m["id"] for m in json.load(res).get("data", [])]
    elif info["dialect"] == "gemini":
        res = _open(f"{base}/models?pageSize=200", headers={"x-goog-api-key": key})
        ids = [m["name"].split("/", 1)[-1] for m in json.load(res).get("models", [])
               if "generateContent" in m.get("supportedGenerationMethods", [])]
    else:
        res = _open(f"{base}/models", headers={"Authorization": f"Bearer {key}"})
        ids = [m["id"] for m in json.load(res).get("data", [])]
        if provider == "openai":
            skip = ("embedding", "whisper", "tts", "dall-e", "image", "audio", "realtime", "moderation", "transcribe", "search")
            ids = [i for i in ids if (i.startswith(("gpt-", "o1", "o3", "o4", "chatgpt")) and not any(s in i for s in skip))]
    return sorted(set(ids), reverse=True)


def _last_user_index(messages):
    for i in range(len(messages) - 1, -1, -1):
        if messages[i]["role"] == "user":
            return i
    return -1


# ---------------------------------------------------------------- Anthropic (Claude)

def _anthropic_messages(messages, tag):
    out = []

    def push(role, blocks):
        if out and out[-1]["role"] == role:
            out[-1]["content"].extend(blocks)
        else:
            out.append({"role": role, "content": list(blocks)})

    for m in messages:
        if m["role"] == "user":
            push("user", [{"type": "text", "text": m["text"] or "(empty)"}])
        elif m["role"] == "assistant":
            if m.get("raw") and m.get("model") == tag and isinstance(m["raw"], list):
                blocks = m["raw"]
            else:
                blocks = [{"type": "text", "text": m["text"]}] if m.get("text") else []
                blocks += [{"type": "tool_use", "id": c["id"], "name": c["name"], "input": c.get("args") or {}} for c in m.get("tool_calls") or []]
            if blocks:
                push("assistant", blocks)
        elif m["role"] == "tool":
            push("user", [{"type": "tool_result", "tool_use_id": m["call_id"], "content": m["text"] or "(no output)", "is_error": bool(m.get("failed"))}])
    return out


def _anthropic(base, model, key, system, messages, tools, throttle, tag):
    payload = {"model": model, "max_tokens": MAX_TOKENS, "system": system, "stream": True,
               "messages": _anthropic_messages(messages, tag)}
    if tools:
        payload["tools"] = [{"name": t["name"], "description": t["description"], "input_schema": t["parameters"]} for t in tools]
    res = _open(f"{base}/messages", payload, {"x-api-key": key, "anthropic-version": ANTHROPIC_VERSION})
    blocks, partial, reply = {}, {}, Reply()
    for event, data in iter_sse(_chunks(res)):
        try:
            msg = json.loads(data)
        except ValueError:
            continue
        kind = msg.get("type", event)
        if kind == "error":
            raise ProviderError(f"The provider stopped with an error: {msg.get('error', {}).get('message', data)[:300]}")
        if kind == "message_start":
            reply.usage.update(msg.get("message", {}).get("usage") or {})
        elif kind == "content_block_start":
            block = dict(msg["content_block"])
            if block.get("type") == "tool_use":
                block["input"] = {}
                partial[msg["index"]] = ""
            blocks[msg["index"]] = block
        elif kind == "content_block_delta":
            idx, delta = msg["index"], msg["delta"]
            block = blocks.setdefault(idx, {"type": "text", "text": ""})
            if delta.get("type") == "text_delta":
                block["text"] = block.get("text", "") + delta["text"]
            elif delta.get("type") == "thinking_delta":
                block["thinking"] = block.get("thinking", "") + delta["thinking"]
            elif delta.get("type") == "signature_delta":
                block["signature"] = block.get("signature", "") + delta["signature"]
            elif delta.get("type") == "input_json_delta":
                partial[idx] = partial.get(idx, "") + delta.get("partial_json", "")
            ordered = [blocks[i] for i in sorted(blocks)]
            throttle("".join(b.get("text", "") for b in ordered if b.get("type") == "text"),
                     "".join(b.get("thinking", "") for b in ordered if b.get("type") == "thinking"))
        elif kind == "content_block_stop":
            idx = msg["index"]
            if idx in partial:
                try:
                    blocks[idx]["input"] = json.loads(partial.pop(idx) or "{}")
                except ValueError:
                    blocks[idx]["input"] = {}
        elif kind == "message_delta":
            reply.stop_reason = msg.get("delta", {}).get("stop_reason") or reply.stop_reason
            reply.usage.update(msg.get("usage") or {})
    ordered = [blocks[i] for i in sorted(blocks)]
    reply.raw = ordered
    reply.text = "".join(b.get("text", "") for b in ordered if b.get("type") == "text")
    reply.reasoning = "".join(b.get("thinking", "") for b in ordered if b.get("type") == "thinking")
    reply.tool_calls = [{"id": b["id"], "name": b["name"], "args": b.get("input") or {}} for b in ordered if b.get("type") == "tool_use"]
    throttle(reply.text, reply.reasoning, force=True)
    return reply


# ---------------------------------------------------------------- OpenAI-style (OpenAI, DeepSeek)

def _openai_messages(provider, system, messages, tag):
    out = [{"role": "system", "content": system}]
    current_turn = _last_user_index(messages)
    for i, m in enumerate(messages):
        if m["role"] == "user":
            out.append({"role": "user", "content": m["text"] or "(empty)"})
        elif m["role"] == "assistant":
            item = {"role": "assistant", "content": m.get("text") or ""}
            calls = m.get("tool_calls") or []
            if calls:
                item["tool_calls"] = [{"id": c["id"], "type": "function",
                                       "function": {"name": c["name"], "arguments": json.dumps(c.get("args") or {})}} for c in calls]
                # DeepSeek's thinking mode wants its reasoning back while it is still working through tools in this turn
                raw = m.get("raw") or {}
                if provider == "deepseek" and i > current_turn and m.get("model") == tag and isinstance(raw, dict) and raw.get("reasoning_content"):
                    item["reasoning_content"] = raw["reasoning_content"]
            if item["content"] or calls:
                out.append(item)
        elif m["role"] == "tool":
            out.append({"role": "tool", "tool_call_id": m["call_id"], "content": m["text"] or "(no output)"})
    return out


def _openai(provider, base, model, key, system, messages, tools, throttle, tag):
    payload = {"model": model, "stream": True, "messages": _openai_messages(provider, system, messages, tag),
               "stream_options": {"include_usage": True}}
    if tools:
        payload["tools"] = [{"type": "function", "function": {"name": t["name"], "description": t["description"], "parameters": t["parameters"]}} for t in tools]
    res = _open(f"{base}/chat/completions", payload, {"Authorization": f"Bearer {key}"})
    text, reasoning, calls, reply = "", "", {}, Reply()
    for _event, data in iter_sse(_chunks(res)):
        if data.strip() == "[DONE]":
            break
        try:
            msg = json.loads(data)
        except ValueError:
            continue
        if msg.get("error"):
            raise ProviderError(f"The provider stopped with an error: {str(msg['error'].get('message', msg['error']))[:300]}")
        if msg.get("usage"):
            reply.usage = msg["usage"]
        for choice in msg.get("choices") or []:
            delta = choice.get("delta") or {}
            text += delta.get("content") or ""
            reasoning += delta.get("reasoning_content") or delta.get("reasoning") or ""
            for tc in delta.get("tool_calls") or []:
                slot = calls.setdefault(tc.get("index", 0), {"id": "", "name": "", "arguments": ""})
                slot["id"] = tc.get("id") or slot["id"]
                fn = tc.get("function") or {}
                slot["name"] += fn.get("name") or ""
                slot["arguments"] += fn.get("arguments") or ""
            if choice.get("finish_reason"):
                reply.stop_reason = choice["finish_reason"]
        throttle(text, reasoning)
    for idx in sorted(calls):
        slot = calls[idx]
        try:
            args = json.loads(slot["arguments"] or "{}")
        except ValueError:
            args = {"_unparsed": slot["arguments"]}
        reply.tool_calls.append({"id": slot["id"] or new_call_id(), "name": slot["name"], "args": args if isinstance(args, dict) else {}})
    reply.text, reply.reasoning = text, reasoning
    reply.raw = {"reasoning_content": reasoning} if (provider == "deepseek" and reasoning) else None
    throttle(text, reasoning, force=True)
    return reply


# ---------------------------------------------------------------- Gemini

def gemini_schema(schema):
    """Gemini reads an OpenAPI subset: no additionalProperties, and an object must list its properties. A free-form
    object becomes a JSON string (the tool layer accepts either)."""
    if not isinstance(schema, dict):
        return schema
    out = {}
    for k, v in schema.items():
        if k in ("additionalProperties", "$schema", "default", "examples"):
            continue
        if k == "properties":
            out[k] = {name: gemini_schema(sub) for name, sub in v.items()}
        elif k == "items":
            out[k] = gemini_schema(v)
        else:
            out[k] = v
    if out.get("type") == "object" and not out.get("properties"):
        return {"type": "string", "description": (out.get("description", "") + " Write it as a JSON object.").strip()}
    return out


def _gemini_contents(messages, tag):
    out = []

    def push(role, parts):
        if out and out[-1]["role"] == role:
            out[-1]["parts"].extend(parts)
        else:
            out.append({"role": role, "parts": list(parts)})

    for m in messages:
        if m["role"] == "user":
            push("user", [{"text": m["text"] or "(empty)"}])
        elif m["role"] == "assistant":
            if m.get("raw") and m.get("model") == tag and isinstance(m["raw"], list):
                parts = m["raw"]
            else:
                parts = [{"text": m["text"]}] if m.get("text") else []
                parts += [{"functionCall": {"name": c["name"], "args": c.get("args") or {}}} for c in m.get("tool_calls") or []]
            if parts:
                push("model", parts)
        elif m["role"] == "tool":
            response = {"error": m["text"]} if m.get("failed") else {"result": m["text"]}
            part = {"functionResponse": {"name": m["name"], "response": response}}
            if m.get("call_id", "").startswith("gem_"):
                part["functionResponse"]["id"] = m["call_id"][4:]
            push("user", [part])
    return out


def _gemini(base, model, key, system, messages, tools, throttle, tag):
    payload = {"systemInstruction": {"parts": [{"text": system}]}, "contents": _gemini_contents(messages, tag)}
    if tools:
        payload["tools"] = [{"functionDeclarations": [
            {"name": t["name"], "description": t["description"], "parameters": gemini_schema(t["parameters"])} for t in tools
        ]}]
    if model.startswith(("gemini-2.5", "gemini-3")):
        payload["generationConfig"] = {"thinkingConfig": {"includeThoughts": True}}
    url = f"{base}/models/{urllib.parse.quote(model, safe='-._')}:streamGenerateContent?alt=sse"
    res = _open(url, payload, {"x-goog-api-key": key})
    parts, text, reasoning, reply = [], "", "", Reply()
    for _event, data in iter_sse(_chunks(res)):
        try:
            msg = json.loads(data)
        except ValueError:
            continue
        if msg.get("error"):
            raise ProviderError(f"The provider stopped with an error: {str(msg['error'].get('message', msg['error']))[:300]}")
        if msg.get("usageMetadata"):
            reply.usage = msg["usageMetadata"]
        for cand in msg.get("candidates") or []:
            for part in (cand.get("content") or {}).get("parts") or []:
                if part.get("thought"):
                    reasoning += part.get("text", "")
                    if part.get("thoughtSignature"):
                        parts.append(part)
                    continue
                parts.append(part)
                text += part.get("text", "")
            if cand.get("finishReason"):
                reply.stop_reason = cand["finishReason"]
        throttle(text, reasoning)
    if reply.stop_reason in ("SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST") and not text and not parts:
        raise ProviderError("Gemini declined to answer this (safety filter). Try rewording.")
    for part in parts:
        call = part.get("functionCall")
        if call:
            cid = f"gem_{call['id']}" if call.get("id") else new_call_id()
            reply.tool_calls.append({"id": cid, "name": call.get("name", ""), "args": call.get("args") or {}})
    reply.raw, reply.text, reply.reasoning = parts, text, reasoning
    throttle(text, reasoning, force=True)
    return reply
