"""
CLI Interface for chrome-cdp-reader
"""

import click
import sys


@click.group()
@click.version_option(version="1.0.0", prog_name="chrome-cdp-reader")
def cli():
    """
    chrome-cdp-reader - Secure AI Browser Controller via Extension WebSocket
    """
    pass

@cli.command()
def mcp():
    """
    Start the MCP Server (Chrome Extension WebSocket Bridge).
    """
    try:
        from chrome_cdp_reader.mcp_server import main as mcp_main
        mcp_main()
    except Exception as e:
        click.echo(f"Error starting server: {e}", err=True)
        sys.exit(1)

def main():
    """Entry point for the CLI."""
    cli()

if __name__ == "__main__":
    main()
