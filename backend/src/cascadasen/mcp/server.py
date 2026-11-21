"""MCP server (stdio) over the Sub50 agent API: `uv run --extra mcp cascadasen-mcp`.

Settings (environment): `SUB50_API_URL` (default http://localhost:8000) and `SUB50_AGENT` (name recorded
in the session's `last_op.by`, default `mcp`). Guide: docs/mcp.md.
"""

from __future__ import annotations

import logging

from mcp.server.mcpserver import MCPServer

from cascadasen.mcp.client import Sub50Client
from cascadasen.mcp.state import McpState
from cascadasen.mcp.tools import INSTRUCTIONS, TOOLS, Sub50Tools


def build_server(tools: Sub50Tools | None = None) -> MCPServer:
    tools = tools or Sub50Tools(Sub50Client(), McpState())
    server = MCPServer("sub50", instructions=INSTRUCTIONS)
    for name in TOOLS:
        server.add_tool(getattr(tools, name), name=name)
    return server


def main() -> None:
    logging.getLogger("httpx").setLevel(logging.WARNING)  # its INFO lines carry the session id
    build_server().run("stdio")


if __name__ == "__main__":
    main()
