"""
CLI Interface for chrome-cdp-reader
"""

import click
import sys
import json

try:
    from importlib.metadata import version as _pkg_version
    __version__ = _pkg_version("chrome-cdp-reader")
except Exception:
    __version__ = "0.0.0"


@click.group()
@click.version_option(version=__version__, prog_name="chrome-cdp-reader")
def cli():
    """
    chrome-cdp-reader - Read your logged-in websites from WSL via Chrome DevTools Protocol
    """
    pass


@cli.command()
@click.argument("target")
@click.option("--search", "-s", help="Search query (for Gmail)")
@click.option(
    "--wait", "-w", type=click.IntRange(min=1), default=15, show_default=True,
    help="Maximum seconds to wait for page readiness",
)
@click.option("--max-chars", default=4000, help="Max characters of text to print")
@click.option("--json", "as_json", is_flag=True, help="Output raw JSON instead of formatted text")
def read(target: str, search: str, wait: int, max_chars: int, as_json: bool):
    """
    Read content from a website.

    TARGET can be:
    - A URL (e.g., https://example.com)
    - "gmail" - Read Gmail inbox
    - "zalo" - Read Zalo messages
    - "facebook" - Read Facebook
    """
    from chrome_cdp_reader.bridge import ChromeReader
    from chrome_cdp_reader.errors import ConnectionError, exit_code_for
    from chrome_cdp_reader.url_validation import validate_scheme

    reader = ChromeReader()

    # Check connection
    if not reader.is_connected():
        click.echo("Error: Cannot connect to Chrome.", err=True)
        click.echo("Make sure Chrome is running with --remote-debugging-port=9222", err=True)
        click.echo("Run: crc setup", err=True)
        sys.exit(exit_code_for(ConnectionError("not connected")))

    if not as_json:
        click.echo(f"Reading {target}...", err=True)

    try:
        # Phase 1: validate target URL scheme BEFORE any navigation.
        # Site aliases (gmail/zalo/facebook) bypass scheme validation.
        if target.lower() not in ("gmail", "zalo", "facebook"):
            validate_scheme(target)

        if target.lower() == "gmail":
            result = reader.read_gmail(search=search, wait=wait)
        elif target.lower() == "zalo":
            result = reader.read_zalo(wait=wait)
        elif target.lower() == "facebook":
            result = reader.read_facebook(wait=wait)
        else:
            result = reader.read(target, wait=wait)

        if as_json:
            click.echo(json.dumps(result, ensure_ascii=False, indent=2))
            return

        # Display results
        click.echo(f"\nTitle: {result.get('title', 'N/A')}")
        click.echo(f"URL: {result.get('url', 'N/A')}")
        click.echo("\nContent:")
        click.echo("-" * 50)
        text = result.get('text', 'No content')
        if len(text) > max_chars:
            text = text[:max_chars] + f"\n... [truncated, {len(text)} chars total]"
        click.echo(text)

        if result.get('links'):
            click.echo(f"\nLinks ({len(result['links'])}):")
            for link in result['links'][:10]:
                click.echo(f"  - {link['text'][:50]}: {link['href']}")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        from chrome_cdp_reader.errors import (
            ChromeCDPReaderError,
            exit_code_for,
        )
        code = exit_code_for(e) if isinstance(e, ChromeCDPReaderError) else 1
        sys.exit(code)


@cli.command()
@click.argument("url")
@click.option("--output", "-o", default="screenshot.png", help="Output file path")
@click.option(
    "--wait", "-w", type=click.IntRange(min=1), default=15, show_default=True,
    help="Maximum seconds to wait for page readiness",
)
def screenshot(url: str, output: str, wait: int):
    """
    Take a screenshot of a URL.
    """
    from chrome_cdp_reader.bridge import ChromeReader

    reader = ChromeReader()

    if not reader.is_connected():
        click.echo("Error: Cannot connect to Chrome.", err=True)
        sys.exit(1)

    click.echo(f"Taking screenshot of {url}...")

    try:
        result = reader.screenshot(url, output=output, wait=wait)
        click.echo(f"Screenshot saved to: {result}")
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command()
def status():
    """
    Check Chrome connection status.
    """
    from chrome_cdp_reader.bridge import ChromeReader
    from chrome_cdp_reader.cookie_manager import CookieManager
    from chrome_cdp_reader.chrome_launcher import ChromeLauncher

    reader = ChromeReader()
    cookie_mgr = CookieManager()
    launcher = ChromeLauncher()

    click.echo("Chrome CDP Reader Status")
    click.echo("=" * 50)

    # Connection
    if reader.is_connected():
        version = reader.get_version()
        click.echo(f"✓ Connected to Chrome: {version.get('Browser', 'Unknown')}")
    else:
        click.echo("✗ Not connected to Chrome")

    # Tabs
    try:
        tabs = reader.get_tabs()
        click.echo(f"✓ Open tabs: {len(tabs)}")
    except Exception:
        click.echo("✗ Cannot list tabs")

    # Cookie status (debug profile only — no cookie copy)
    cookie_status = cookie_mgr.get_status()
    click.echo("\nDebug Profile:")
    click.echo(f"  Windows user: {cookie_status['win_user']}")
    click.echo(f"  Profile (Windows): {cookie_status['windows_profile']}")
    click.echo(f"  Profile (WSL): {cookie_status['wsl_profile']}")
    click.echo(f"  Exists: {cookie_status['exists']}")

    # Chrome status
    chrome_status = launcher.get_status()
    click.echo("\nChrome Launcher:")
    click.echo(f"  Debug port: {chrome_status['debug_port']}")


@cli.command()
def setup():
    """
    Setup Chrome debug mode (run once).
    """
    from chrome_cdp_reader.cookie_manager import CookieManager
    from chrome_cdp_reader.chrome_launcher import ChromeLauncher

    click.echo("Setting up Chrome debug mode...")
    click.echo("=" * 50)

    # Step 1: Kill Chrome bound to the debug port
    click.echo("\n1. Killing existing Chrome debug processes...")
    launcher = ChromeLauncher()
    if not launcher.kill_chrome():
        click.echo("✗ Failed to kill Chrome debug process", err=True)
        sys.exit(1)

    # Step 2: Create debug profile (empty; you log in ONCE, cookies persist)
    click.echo("\n2. Creating debug profile...")
    cookie_mgr = CookieManager()
    if not cookie_mgr.create_debug_profile():
        click.echo("✗ Failed to create debug profile", err=True)
        sys.exit(1)
    click.echo(f"  Debug profile: {cookie_mgr.debug_profile}")
    click.echo("  (Log in ONCE in the opened Chrome; cookies persist there.)")

    # Step 3: Launch Chrome
    click.echo("\n3. Launching Chrome with debug mode...")
    if not launcher.launch():
        click.echo("✗ Failed to launch Chrome", err=True)
        sys.exit(1)

    # Step 4: Verify
    click.echo("\n4. Verifying connection...")
    status = launcher.verify_connection()

    if status["connected"]:
        click.echo(f"✓ Chrome is running: {status['browser']}")
        click.echo("\nSetup complete! Log in once, then use:")
        click.echo("  crc read gmail")
        click.echo("  crc read https://example.com")
    else:
        click.echo("✗ Failed to connect to Chrome", err=True)
        click.echo("Please check Chrome is installed and try again", err=True)
        sys.exit(1)


def main():
    """Entry point for the CLI."""
    cli()


if __name__ == "__main__":
    main()
