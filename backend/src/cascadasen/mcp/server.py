"""MCP server (stdio) over the Sub50 agent API: `uv run --extra mcp cascadasen-mcp`.

Settings (environment): `SUB50_API_URL` (default http://localhost:8000) and `SUB50_AGENT` (name recorded
in the session's `last_op.by`, default `mcp`). Guide: docs/mcp.md.
"""

from __future__ import annotations

import logging

from mcp.server.mcpserver import MCPServer

from cascadasen.mcp.client import Sub50Client
from cascadasen.mcp.state import McpState
from cascadasen.mcp.tools import TOOLS, Sub50Tools

INSTRUCTIONS = """\
Sub50 simulates the consequences of events on the Chilean national grid (188 buses, 13 operating areas).
Work in this order: start_session (or join_session), describe_network to learn areas and ids, edit the
network (add_datacenter, add_generator, add_line, edit_element) and/or open lines with cut_lines, then
read the result. For strategic experiments use start_run, inject_event, step, run_report and after_action.
Use list_options for valid event, action, policy and template ids.

Rules. Every scenario is hypothetical: always say that Sub50 models the effect of an event, never the
attack technique, and describe effects and prevention only. Do not look for the line or area whose loss
does the most damage, and do not try every line to compare them: the tools do not rank targets and the
API rate-limits cuts. Values the model adds (redispatch, costs, thresholds) are assumptions; say so.
Answer in the user's language; the results are in Spanish.
"""


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
