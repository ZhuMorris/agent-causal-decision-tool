"""Agent Causal Decision Tool — JSON-RPC API server.

Supports two transports:
  stdio  — For agent tool integration (OpenClaw, Codex, Claude Code, etc.)
           Run with: python -m src.api stdio
  http   — FastAPI server for direct external access.
           Run with: uvicorn src.api:app --port 8000
           Or: python -m src.api http [--port 8000]

Both transports expose the same 9 actions:
  decide, decide_ab, decide_rollout, plan_test, audit_result,
  save_result, get_result, compare_results, connect

Request/response format is JSON-RPC 2.0.
Error responses use the structured APIErrorResponse envelope.
"""

from __future__ import annotations

import json
import sys
from importlib.metadata import version as _pkg_version, PackageNotFoundError
from typing import Optional

from .actions import run_action
from .errors import parse_error


# ─── JSON-RPC request parsing ─────────────────────────────────────────────────

def _parse_request(data: dict | list) -> tuple[list[dict], Optional[dict]]:
    """Parse raw JSON dict into a list of JSON-RPC request dicts.

    Returns (batch_requests, parse_error_or_none).
    If parse_error_or_none is non-None, the caller should return it immediately.
    """
    # Batch request
    if isinstance(data, list):
        if len(data) == 0:
            return [], parse_error("Invalid batch request: empty array")
        for item in data:
            if not isinstance(item, dict):
                return [], parse_error("Batch item must be a JSON-RPC request object")
            if "jsonrpc" not in item:
                return [], parse_error("Missing jsonrpc field in batch item")
            if item.get("jsonrpc") != "2.0":
                return [], parse_error(f"Unsupported jsonrpc version: {item.get('jsonrpc')}")
        return data, None

    # Single request
    if not isinstance(data, dict):
        return [], parse_error("Request must be a JSON-RPC request object")
    if data.get("jsonrpc") != "2.0":
        return [], parse_error(f"Unsupported jsonrpc version: {data.get('jsonrpc')}")
    return [data], None


def _get_request_id(item: dict) -> Optional[str | int]:
    """Extract request id from a JSON-RPC request or notification."""
    return item.get("id")


# ─── Stdio transport ──────────────────────────────────────────────────────────

def run_stdio():
    """Run the stdio JSON-RPC server.

    Reads requests from stdin, writes responses to stdout.
    Exits cleanly on EOF or broken pipe.
    """
    buffer = ""

    try:
        while True:
            line = sys.stdin.readline()
            if not line:  # EOF
                break

            buffer += line
            buffer = buffer.strip()

            if not buffer:
                continue

            # Try to parse as complete JSON-RPC message(s)
            try:
                parsed = json.loads(buffer)
            except json.JSONDecodeError:
                # Incomplete JSON — wait for more input
                continue

            buffer = ""  # Reset buffer on successful parse

            requests, parse_err = _parse_request(parsed)
            if parse_err is not None:
                print(json.dumps(parse_err), flush=True)
                continue

            # Process requests — skip response for notifications (no id = no response per JSON-RPC 2.0)
            for req in requests:
                request_id = _get_request_id(req)  # None = notification
                method = req.get("method")
                params = req.get("params", {})
                if not isinstance(params, dict):
                    err_resp = {
                        "jsonrpc": "2.0",
                        "error": {"code": -32600, "message": "Invalid params: must be an object"},
                        "id": request_id,
                    }
                    if request_id is not None:
                        print(json.dumps(err_resp), flush=True)
                    continue

                if method is None:
                    err_resp = {
                        "jsonrpc": "2.0",
                        "error": {"code": -32600, "message": "Missing method field"},
                        "id": request_id,
                    }
                    # Notifications (request_id is None) still get an error response
                    # only if the request itself was malformed; if id is None it's a notification
                    if request_id is not None:
                        print(json.dumps(err_resp), flush=True)
                    continue

                result = run_action(method, params, request_id)
                # Only emit response if request had an id (not a notification)
                if request_id is not None:
                    print(json.dumps(result), flush=True)

    except BrokenPipeError:
        # stdout closed — exit silently
        pass


# ─── HTTP transport (FastAPI) ────────────────────────────────────────────────

def _get_version():
    """Get the installed package version or 'unknown' if not installed."""
    try:
        return _pkg_version("agent_causal_decision_tool")
    except PackageNotFoundError:
        return "unknown"

def _build_http_app():
    """Build the FastAPI app with both RPC and health endpoints."""
    from fastapi import FastAPI, Request, Response
    from fastapi.responses import JSONResponse
    import uvicorn

    _ver = _get_version()
    app = FastAPI(title="Agent Causal Decision API", version=_ver)

    @app.post("/rpc")
    async def rpc_endpoint(request: Request) -> Response:
        """Main JSON-RPC endpoint — accepts single or batch requests."""
        try:
            data = await request.json()
        except Exception:
            return JSONResponse(
                status_code=400,
                content=parse_error("Invalid JSON body"),
            )

        requests, parse_err = _parse_request(data)
        if parse_err is not None:
            return JSONResponse(status_code=400, content=parse_err)

        responses = []
        for req in requests:
            request_id = _get_request_id(req)  # None = notification
            method = req.get("method")
            params = req.get("params", {})
            if not isinstance(params, dict):
                # Notifications (no id) get no response per JSON-RPC 2.0 spec
                if request_id is not None:
                    responses.append({
                        "jsonrpc": "2.0",
                        "error": {"code": -32602, "message": "Invalid params: must be an object"},
                        "id": request_id,
                    })
                continue
            if method is None:
                if request_id is not None:
                    responses.append({
                        "jsonrpc": "2.0",
                        "error": {"code": -32600, "message": "Missing method field"},
                        "id": request_id,
                    })
                continue
            result = run_action(method, params, request_id)
            if request_id is not None:
                responses.append(result)

        if len(responses) == 0:
            return Response(status_code=204)
        if len(responses) == 1:
            return JSONResponse(content=responses[0])
        return JSONResponse(content=responses)

    @app.get("/health")
    async def health():
        """Health check endpoint."""
        return {"status": "ok", "version": _ver}

    return app


def run_http(port: int = 8000):
    """Run the HTTP JSON-RPC server on the given port."""
    try:
        from fastapi import FastAPI
        import uvicorn
    except ImportError:
        sys.stderr.write(
            "Error: fastapi and uvicorn are required for HTTP mode.\n"
            "Install with: pip install fastapi uvicorn\n"
        )
        sys.exit(1)

    app = _build_http_app()
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")


# ─── CLI entry point ─────────────────────────────────────────────────────────

def main():
    """CLI entry point for the API server."""
    import argparse

    parser = argparse.ArgumentParser(description="Agent Causal JSON-RPC API server")
    parser.add_argument(
        "transport",
        choices=["stdio", "http"],
        help="Transport to use: 'stdio' for agent tools, 'http' for FastAPI server"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port for HTTP transport (default: 8000)"
    )
    args = parser.parse_args()

    if args.transport == "stdio":
        run_stdio()
    else:
        run_http(args.port)


if __name__ == "__main__":
    main()