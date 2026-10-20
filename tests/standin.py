#!/usr/bin/env python3
# tests/standin.py - the stand-in that tests/web_test.py talks to, on one port (4999):
#   LiteLLM      /v1/models, /v1/chat/completions (streamed or not; "Gemini says ..."; a request
#                naming the garage gets a HassTurnOn tool call naming the garage door)
#   Home Assistant  /api/ and /api/states (three person.* entities and a light), token HA_TOKEN
#   a recipes app  /swagger/doc.json (Swagger 2, "Stand-in recipes", 3 commands); while the file
#                /tmp/veil-test/fake/spec-v2 exists it's version 2 (one added, one modified, one deleted)
#   Oread        /oread/openapi.json (OpenAPI 3 with x-wepwawet) and /oread/profiles, token oread-test-token
#
# Run the page tests (never against the live router):
#   python3 tests/make_copy.py /tmp/veil-copy     (starting copies and stand-in assistants, never yours)
#   python3 tests/standin.py &
#   cd /tmp/veil-copy && ROUTER_ROOT=$PWD OFF_PLATFORM_URL=http://127.0.0.1:4999/v1 OFF_PLATFORM_KEY=standin-key python3 -m veil.main &
# OFF_PLATFORM_KEY must be set (any value; the stand-in doesn't check it), or every Off-Platform case fails.
#   python3 tests/web_test.py https://127.0.0.1:8771 http://127.0.0.1:8770 /tmp/veil-copy

import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("STANDIN_PORT", "4999"))
V2 = "/tmp/veil-test/fake/spec-v2"
os.makedirs(os.path.dirname(V2), exist_ok=True)


def recipes_spec():
    v2 = os.path.exists(V2)
    paths = {
        "/recipes": {
            "get": {"summary": "List recipes" + (" (paged)" if v2 else ""),
                    "parameters": [{"name": "page", "in": "query", "required": True, "type": "integer"}] if v2 else [],
                    "responses": {"200": {"description": "ok", "schema": {"type": "array", "items": {"$ref": "#/definitions/Recipe"}}}}},
            "post": {"summary": "Add a recipe",
                     "parameters": [{"name": "body", "in": "body", "required": True, "schema": {"$ref": "#/definitions/NewRecipe"}}],
                     "responses": {"200": {"description": "ok", "schema": {"$ref": "#/definitions/Recipe"}}}},
        },
    }
    if v2:
        paths["/recipes/{id}/rate"] = {"post": {"summary": "Rate a recipe",
                                                "parameters": [{"name": "id", "in": "path", "required": True, "type": "integer"}],
                                                "responses": {"200": {"description": "ok"}}}}
    else:
        paths["/recipes/{id}"] = {"delete": {"summary": "Delete a recipe",
                                             "parameters": [{"name": "id", "in": "path", "required": True, "type": "integer"}],
                                             "responses": {"200": {"description": "ok"}}}}
    return {"swagger": "2.0", "info": {"title": "Stand-in recipes", "version": "2" if v2 else "1"},
            "basePath": "/api", "securityDefinitions": {"K": {"type": "apiKey", "in": "header", "name": "Authorization"}},
            "paths": paths,
            "definitions": {"Recipe": {"type": "object", "properties": {"id": {"type": "integer"}, "name": {"type": "string"}}},
                            "NewRecipe": {"type": "object", "required": ["name"], "properties": {"name": {"type": "string"}}}}}


OREAD_SPEC = {
    "openapi": "3.1.0", "info": {"title": "Oread", "version": "1"}, "servers": [{"url": "/oread"}],
    "x-wepwawet": {
        "version": 1, "title": "Oread", "role": "speech",
        "tabs": {"commands": True, "voice_map": False, "clean_up": False, "lists": True, "options": True},
        "auth": {"in": "header", "name": "Authorization", "prefix": "Bearer "},
        "offers": {"who_spoke": {"title": "Who spoke", "description": "Oread names the speaker of each request.",
                                 "ways": {"wyoming": "in the audio path", "api": "Oread's API", "sensor": "the sensor in Home Assistant"}}},
        "lists": {"people": {"from": "GET /profiles", "id": "name", "name": "name", "house": "people"}},
    },
    "paths": {
        "/profiles": {"get": {"summary": "List profiles", "responses": {"200": {"description": "ok", "content": {"application/json": {
            "schema": {"type": "array", "items": {"type": "object", "properties": {"name": {"type": "string"}}}}}}}}}},
        "/clips": {"get": {"summary": "List clips", "responses": {"200": {"description": "ok"}}}},
    },
}

HA_STATES = [
    {"entity_id": "person.beth", "attributes": {"friendly_name": "Beth"}},
    {"entity_id": "person.sam", "attributes": {"friendly_name": "Sam", "device_trackers": ["device_tracker.phone"]}},
    {"entity_id": "person.sam_old_phone", "attributes": {"friendly_name": "Sam old phone"}},
    {"entity_id": "light.kitchen", "attributes": {"friendly_name": "Kitchen"}},
]


def reply_for(body):
    """What the stand-in model says: words, or a tool call when the garage is named."""
    msgs = body.get("messages") or []
    last = msgs[-1] if msgs else {}
    if last.get("role") == "tool":
        # says whether it was still offered tools (the router takes them away at its tool-round cap)
        return "Gemini says it's done." + ("" if body.get("tools") else " (words only)"), []
    said = str(last.get("content") or "")
    if "garage" in said.lower():
        return None, [{"id": "call_1", "type": "function",
                       "function": {"name": "HassTurnOn", "arguments": json.dumps({"name": "garage door"})}}]
    return f"Gemini says: here's my answer to {said}", []


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, code, obj, ctype="application/json"):
        data = obj if isinstance(obj, bytes) else json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def auth(self):
        return self.headers.get("Authorization", "")

    def do_GET(self):
        p = self.path.split("?")[0]
        if p == "/openapi.json":            # LiteLLM's own description of its commands
            return self.send(200, {"openapi": "3.1.0", "info": {"title": "LiteLLM API", "version": "1.80.0"},
                                   "paths": {"/v1/models": {"get": {"summary": "Model List"}},
                                             "/v1/chat/completions": {"post": {"summary": "Chat Completion"}}}})
        if p in ("/v1/models", "/models"):
            return self.send(200, {"data": [{"id": "gemini-lite"}, {"id": "house-router"}]})
        if p == "/api/":
            ok = self.auth() in ("Bearer HA_TOKEN", "Bearer ha-long-lived-token-for-tests")
            return self.send(200 if ok else 401, {"message": "API running."})
        if p == "/api/states":
            if self.auth() != "Bearer ha-long-lived-token-for-tests" and self.auth() != "Bearer HA_TOKEN":
                return self.send(401, {"message": "no"})
            return self.send(200, HA_STATES)
        if p == "/swagger/doc.json":
            return self.send(200, recipes_spec())
        if p == "/oread/openapi.json":
            if self.auth() != "Bearer oread-test-token":
                return self.send(401, {"detail": "sign in"})
            return self.send(200, OREAD_SPEC)
        if p == "/oread/profiles":
            if self.auth() != "Bearer oread-test-token":
                return self.send(401, {"detail": "sign in"})
            return self.send(200, [{"name": "Sam"}, {"name": "Elizabeth"}, {"name": "Sam Jr"}])
        return self.send(404, {"detail": "not here"})

    def do_POST(self):
        p = self.path.split("?")[0]
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        if p not in ("/v1/chat/completions", "/chat/completions"):
            return self.send(404, {"detail": "not here"})
        text, calls = reply_for(body)
        base = {"id": "standin", "object": "chat.completion", "created": int(time.time()), "model": body.get("model", "gemini-lite")}
        if not body.get("stream"):
            msg = {"role": "assistant", "content": text}
            if calls:
                msg["tool_calls"] = calls
            return self.send(200, dict(base, choices=[{"index": 0, "message": msg,
                                                       "finish_reason": "tool_calls" if calls else "stop"}],
                                       usage={"prompt_tokens": 100, "completion_tokens": 10, "total_tokens": 110}))
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()

        def chunk(delta, finish=None):
            c = dict(base, object="chat.completion.chunk", choices=[{"index": 0, "delta": delta, "finish_reason": finish}])
            self.wfile.write(f"data: {json.dumps(c)}\n\n".encode())

        chunk({"role": "assistant"})
        if calls:
            chunk({"tool_calls": [dict(tc, index=i) for i, tc in enumerate(calls)]})
            chunk({}, "tool_calls")
        else:
            for word in text.split(" "):
                chunk({"content": word + " "})
            chunk({}, "stop")
        self.wfile.write(b"data: [DONE]\n\n")


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
