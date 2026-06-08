"""
CLI Interface for chrome-cdp-reader
"""

import click
import json
import sys


@click.group()
@click.version_option(version="0.1.0", prog_name="chrome-cdp-reader")
def cli():
    """
    chrome-cdp-reader - Read your logged-in websites from WSL via Chrome DevTools Protocol
    """
    pass


@cli.command()
@click.argument("target")
@click.option("--search", "-s", help="Search query (for Gmail)")
@click.option("--wait", "-w", default=3, help="Seconds to wait for page load")
def read(target: str, search: str, wait: int):
    """
    Read content from a website.
    
    TARGET can be:
    - A URL (e.g., https://example.com)
    - "gmail" - Read Gmail inbox
    - "zalo" - Read Zalo messages
    - "facebook" - Read Facebook
    """
    from chrome_cdp_reader.bridge import ChromeReader
    
    reader = ChromeReader()
    
    # Check connection
    if not reader.is_connected():
        click.echo("Error: Cannot connect to Chrome.", err=True)
        click.echo("Make sure Chrome is running with --remote-debugging-port=9222", err=True)
        click.echo("Run: crc setup", err=True)
        sys.exit(1)
    
    click.echo(f"Reading {target}...")
    
    try:
        if target.lower() == "gmail":
            result = reader.read_gmail(search=search)
        elif target.lower() == "zalo":
            result = reader.read_zalo()
        else:
            result = reader.read(target, wait=wait)
        
        # Display results
        click.echo(f"\nTitle: {result.get('title', 'N/A')}")
        click.echo(f"URL: {result.get('url', 'N/A')}")
        click.echo(f"\nContent:")
        click.echo("-" * 50)
        click.echo(result.get('text', 'No content')[:2000])
        
        if result.get('links'):
            click.echo(f"\nLinks ({len(result['links'])}):")
            for link in result['links'][:10]:
                click.echo(f"  - {link['text'][:50]}: {link['href']}")
        
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("url")
@click.option("--output", "-o", default="screenshot.png", help="Output file path")
@click.option("--wait", "-w", default=3, help="Seconds to wait for page load")
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
    
    # Cookie status
    cookie_status = cookie_mgr.get_status()
    click.echo(f"\nCookie Manager:")
    click.echo(f"  Windows user: {cookie_status['win_user']}")
    click.echo(f"  Default profile exists: {cookie_status['default_exists']}")
    click.echo(f"  Debug profile exists: {cookie_status['debug_exists']}")
    
    # Chrome status
    chrome_status = launcher.get_status()
    click.echo(f"\nChrome Launcher:")
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
    
    # Step 1: Kill Chrome
    click.echo("\n1. Killing existing Chrome processes...")
    launcher = ChromeLauncher()
    launcher.kill_chrome()
    
    # Step 2: Create debug profile
    click.echo("\n2. Creating debug profile...")
    cookie_mgr = CookieManager()
    cookie_mgr.create_debug_profile()
    
    # Step 3: Copy cookies
    click.echo("\n3. Copying cookies...")
    cookie_mgr.copy_cookies()
    
    # Step 4: Launch Chrome
    click.echo("\n4. Launching Chrome with debug mode...")
    launcher.launch()
    
    # Step 5: Verify
    click.echo("\n5. Verifying connection...")
    status = launcher.verify_connection()
    
    if status["connected"]:
        click.echo(f"✓ Chrome is running: {status['browser']}")
        click.echo("\nSetup complete! You can now use:")
        click.echo("  crc read gmail")
        click.echo("  crc read https://example.com")
    else:
        click.echo("✗ Failed to connect to Chrome")
        click.echo("Please check Chrome is installed and try again")


@cli.command()
def cookies():
    """
    Manage cookies (copy from default to debug profile).
    """
    from chrome_cdp_reader.cookie_manager import CookieManager
    
    manager = CookieManager()
    
    click.echo("Cookie Manager")
    click.echo("=" * 50)
    
    status = manager.get_status()
    click.echo(f"Windows user: {status['win_user']}")
    click.echo(f"Default profile: {status['default_profile']}")
    click.echo(f"Debug profile: {status['debug_profile']}")
    
    click.echo("\nCopying cookies...")
    if manager.copy_cookies():
        click.echo("\n✓ Cookies copied successfully!")
    else:
        click.echo("\n✗ Some cookies failed to copy")
    
    # Verify
    click.echo("\nVerification:")
    cookies = manager.verify_cookies()
    for name, info in cookies.items():
        status = "✓" if info["exists"] else "✗"
        click.echo(f"  {status} {name}: {info['size']} bytes")


def main():
    """Entry point for the CLI."""
    cli()


if __name__ == "__main__":
    main()
