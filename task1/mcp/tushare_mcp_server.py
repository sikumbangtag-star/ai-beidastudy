#!/usr/bin/env python3
"""Minimal stdio MCP server for the Tushare Pro HTTP API."""

from __future__ import annotations

import json
import os
import sys
import traceback
import urllib.error
import urllib.request
from typing import Any


SERVER_NAME = "tushare"
SERVER_VERSION = "0.1.0"
TUSHARE_API_URL = os.environ.get("TUSHARE_API_URL", "https://api.tushare.pro")


TOOLS: list[dict[str, Any]] = [
    {
        "name": "tushare_query",
        "description": (
            "Call any Tushare Pro API by api_name. Use params for API parameters "
            "and fields for comma-separated response fields."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["api_name"],
            "properties": {
                "api_name": {
                    "type": "string",
                    "description": "Tushare Pro API name, for example stock_basic, daily, trade_cal.",
                },
                "params": {
                    "type": "object",
                    "description": "Tushare API parameters.",
                    "additionalProperties": True,
                    "default": {},
                },
                "fields": {
                    "type": "string",
                    "description": "Comma-separated fields to return. Leave empty for Tushare default.",
                    "default": "",
                },
            },
        },
    },
    {
        "name": "stock_basic",
        "description": "List A-share stock metadata from Tushare stock_basic.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "exchange": {"type": "string", "default": ""},
                "market": {"type": "string", "default": ""},
                "list_status": {"type": "string", "default": "L"},
                "fields": {
                    "type": "string",
                    "default": "ts_code,symbol,name,area,industry,market,list_date",
                },
            },
        },
    },
    {
        "name": "daily",
        "description": "Fetch daily stock bars from Tushare daily.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "ts_code": {"type": "string", "description": "Example: 000001.SZ"},
                "trade_date": {"type": "string", "description": "YYYYMMDD"},
                "start_date": {"type": "string", "description": "YYYYMMDD"},
                "end_date": {"type": "string", "description": "YYYYMMDD"},
                "fields": {
                    "type": "string",
                    "default": "ts_code,trade_date,open,high,low,close,pre_close,change,pct_chg,vol,amount",
                },
            },
        },
    },
    {
        "name": "trade_cal",
        "description": "Fetch exchange trading calendar from Tushare trade_cal.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "exchange": {"type": "string", "default": "SSE"},
                "start_date": {"type": "string", "description": "YYYYMMDD"},
                "end_date": {"type": "string", "description": "YYYYMMDD"},
                "is_open": {"type": "string", "description": "0 or 1"},
                "fields": {
                    "type": "string",
                    "default": "exchange,cal_date,is_open,pretrade_date",
                },
            },
        },
    },
]


def _read_message() -> dict[str, Any] | None:
    headers: dict[str, str] = {}

    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            return None
        line = line.strip()
        if not line:
            break
        key, _, value = line.decode("ascii").partition(":")
        headers[key.lower()] = value.strip()

    content_length = int(headers.get("content-length", "0"))
    if content_length <= 0:
        return None

    body = sys.stdin.buffer.read(content_length)
    return json.loads(body.decode("utf-8"))


def _write_message(message: dict[str, Any]) -> None:
    body = json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    sys.stdout.buffer.write(f"Content-Length: {len(body)}\r\n\r\n".encode("ascii"))
    sys.stdout.buffer.write(body)
    sys.stdout.buffer.flush()


def _result(request_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error(request_id: Any, code: int, message: str, data: Any = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }
    if data is not None:
        payload["error"]["data"] = data
    return payload


def _call_tushare(api_name: str, params: dict[str, Any] | None = None, fields: str = "") -> dict[str, Any]:
    token = os.environ.get("TUSHARE_TOKEN") or os.environ.get("TUSHARE_PRO_TOKEN")
    if not token:
        raise RuntimeError("Missing TUSHARE_TOKEN environment variable.")

    payload = {
        "api_name": api_name,
        "token": token,
        "params": params or {},
        "fields": fields or "",
    }
    request = urllib.request.Request(
        TUSHARE_API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": f"{SERVER_NAME}/{SERVER_VERSION}"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Tushare HTTP {exc.code}: {detail}") from exc

    result = json.loads(raw)
    if result.get("code") not in (0, None):
        raise RuntimeError(result.get("msg") or f"Tushare returned code {result.get('code')}")
    return result


def _table_to_text(result: dict[str, Any]) -> str:
    data = result.get("data") or {}
    fields = data.get("fields") or []
    rows = data.get("items") or []

    if not fields:
        return json.dumps(result, ensure_ascii=False, indent=2)

    output = {
        "fields": fields,
        "row_count": len(rows),
        "rows": [dict(zip(fields, row)) for row in rows],
    }
    return json.dumps(output, ensure_ascii=False, indent=2)


def _handle_tool_call(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if name == "tushare_query":
        api_name = str(arguments["api_name"])
        params = arguments.get("params") or {}
        fields = str(arguments.get("fields") or "")
    elif name == "stock_basic":
        api_name = "stock_basic"
        fields = str(arguments.get("fields") or "ts_code,symbol,name,area,industry,market,list_date")
        params = {
            key: value
            for key, value in {
                "exchange": arguments.get("exchange", ""),
                "market": arguments.get("market", ""),
                "list_status": arguments.get("list_status", "L"),
            }.items()
            if value not in (None, "")
        }
    elif name == "daily":
        api_name = "daily"
        fields = str(
            arguments.get("fields")
            or "ts_code,trade_date,open,high,low,close,pre_close,change,pct_chg,vol,amount"
        )
        params = {
            key: value
            for key in ("ts_code", "trade_date", "start_date", "end_date")
            if (value := arguments.get(key)) not in (None, "")
        }
    elif name == "trade_cal":
        api_name = "trade_cal"
        fields = str(arguments.get("fields") or "exchange,cal_date,is_open,pretrade_date")
        params = {
            key: value
            for key in ("exchange", "start_date", "end_date", "is_open")
            if (value := arguments.get(key)) not in (None, "")
        }
    else:
        raise RuntimeError(f"Unknown tool: {name}")

    result = _call_tushare(api_name, params, fields)
    return {"content": [{"type": "text", "text": _table_to_text(result)}], "isError": False}


def _handle_request(message: dict[str, Any]) -> dict[str, Any] | None:
    request_id = message.get("id")
    method = message.get("method")
    params = message.get("params") or {}

    if request_id is None:
        return None

    if method == "initialize":
        return _result(
            request_id,
            {
                "protocolVersion": params.get("protocolVersion", "2024-11-05"),
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            },
        )
    if method == "ping":
        return _result(request_id, {})
    if method == "tools/list":
        return _result(request_id, {"tools": TOOLS})
    if method == "tools/call":
        name = params.get("name")
        arguments = params.get("arguments") or {}
        return _result(request_id, _handle_tool_call(name, arguments))

    return _error(request_id, -32601, f"Method not found: {method}")


def main() -> int:
    while True:
        message = _read_message()
        if message is None:
            return 0
        try:
            response = _handle_request(message)
        except Exception as exc:  # noqa: BLE001 - MCP errors should be returned to the client.
            request_id = message.get("id")
            response = _error(request_id, -32000, str(exc), traceback.format_exc())
        if response is not None:
            _write_message(response)


if __name__ == "__main__":
    raise SystemExit(main())
