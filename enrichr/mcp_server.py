"""ENRICHR MCP server — exposes scan() as an MCP tool for Cognis.Studio."""
from __future__ import annotations
from enrichr.core import scan, to_json

def serve() -> int:
    """Start an MCP stdio server. Requires the optional 'mcp' extra:
        pip install "cognis-enrichr[mcp]"
    """
    try:
        from mcp.server.fastmcp import FastMCP
    except Exception:
        print("Install the MCP extra: pip install 'cognis-enrichr[mcp]'")
        return 1
    app = FastMCP("enrichr")

    @app.tool()
    def enrichr_scan(target: str) -> str:
        """Enrich a leads CSV with firmographics, tech stack, and contact validation from pluggable providers, caching results to avoid duplicate API spend.. Returns JSON findings."""
        return to_json(scan(target))

    app.run()
    return 0
