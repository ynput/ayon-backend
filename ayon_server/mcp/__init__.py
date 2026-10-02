"""Proxy for the MCP service, reached through a WebSocket tunnel.

The MCP service (ayon-mcp) connects to ``/api/mcp/ws`` and serves the MCP
endpoint ``/api/mcp`` through that connection, so it needs no listening
port, public IP or ingress. See ``protocol`` for the wire format and
``hub`` for routing across server workers.
"""

__all__ = ["mcp_tunnels", "proxy_request"]

from .hub import TunnelHub
from .proxy import proxy_request

mcp_tunnels = TunnelHub()
