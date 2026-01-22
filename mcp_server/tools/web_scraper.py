"""
Web Scraper Tools

Active operations for fetching and parsing web content.
"""

import re
import requests
from typing import TYPE_CHECKING
from urllib.parse import urlparse, urljoin
from loguru import logger

from mcp_server.errors import MCPToolError, RateLimitedError

if TYPE_CHECKING:
    from fastmcp import FastMCP

# Common headers to avoid bot detection
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def _extract_text_from_html(html: str, max_length: int = 10000) -> str:
    """Extract readable text from HTML, removing scripts and styles."""
    # Remove script and style elements
    html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)

    # Remove HTML comments
    html = re.sub(r'<!--.*?-->', '', html, flags=re.DOTALL)

    # Replace common block elements with newlines
    html = re.sub(r'<(p|div|br|h[1-6]|li|tr)[^>]*>', '\n', html, flags=re.IGNORECASE)

    # Remove all remaining tags
    text = re.sub(r'<[^>]+>', '', html)

    # Decode HTML entities
    text = text.replace('&nbsp;', ' ')
    text = text.replace('&amp;', '&')
    text = text.replace('&lt;', '<')
    text = text.replace('&gt;', '>')
    text = text.replace('&quot;', '"')

    # Clean up whitespace
    text = re.sub(r'\n\s*\n', '\n\n', text)
    text = re.sub(r' +', ' ', text)
    text = text.strip()

    # Truncate if too long
    if len(text) > max_length:
        text = text[:max_length] + "...[truncated]"

    return text


def _extract_metadata(html: str) -> dict:
    """Extract metadata from HTML head."""
    metadata = {}

    # Title
    title_match = re.search(r'<title[^>]*>([^<]+)</title>', html, re.IGNORECASE)
    if title_match:
        metadata['title'] = title_match.group(1).strip()

    # Meta description
    desc_match = re.search(r'<meta[^>]*name=["\']description["\'][^>]*content=["\']([^"\']+)["\']', html, re.IGNORECASE)
    if not desc_match:
        desc_match = re.search(r'<meta[^>]*content=["\']([^"\']+)["\'][^>]*name=["\']description["\']', html, re.IGNORECASE)
    if desc_match:
        metadata['description'] = desc_match.group(1).strip()

    # Open Graph title
    og_title = re.search(r'<meta[^>]*property=["\']og:title["\'][^>]*content=["\']([^"\']+)["\']', html, re.IGNORECASE)
    if og_title:
        metadata['og_title'] = og_title.group(1).strip()

    return metadata


def register(mcp: "FastMCP"):
    """Register web scraper tools with MCP server."""

    @mcp.tool()
    def scrape_url(url: str, extract_text: bool = True) -> dict:
        """Fetch and parse content from a URL.

        Args:
            url: The URL to fetch
            extract_text: If True, extract readable text from HTML

        Returns:
            Dict with url, status, metadata, and content
        """
        # Validate URL
        parsed = urlparse(url)
        if not parsed.scheme:
            url = "https://" + url
            parsed = urlparse(url)

        if parsed.scheme not in ('http', 'https'):
            raise MCPToolError("web_scraper", f"Invalid URL scheme: {parsed.scheme}")

        try:
            resp = requests.get(url, headers=DEFAULT_HEADERS, timeout=15, allow_redirects=True)

            if resp.status_code == 429:
                raise RateLimitedError("web_scraper", retry_after=60)

            if resp.status_code == 403:
                raise MCPToolError("web_scraper", f"Access forbidden (403) for {url}")

            if resp.status_code == 404:
                raise MCPToolError("web_scraper", f"Page not found (404) for {url}")

            resp.raise_for_status()

            html = resp.text
            metadata = _extract_metadata(html)

            result = {
                "url": resp.url,  # Final URL after redirects
                "status": resp.status_code,
                "content_type": resp.headers.get("content-type", ""),
                "metadata": metadata,
            }

            if extract_text:
                result["text"] = _extract_text_from_html(html)
            else:
                result["html_length"] = len(html)

            return result

        except requests.Timeout:
            raise MCPToolError("web_scraper", f"Timeout fetching {url}")
        except requests.RequestException as e:
            raise MCPToolError("web_scraper", str(e))

    @mcp.tool()
    def search_web(query: str, num_results: int = 5) -> dict:
        """Search the web using DuckDuckGo HTML (no API key needed).

        Args:
            query: Search query
            num_results: Maximum number of results (1-10)

        Returns:
            Dict with query and list of results (title, url, snippet)
        """
        try:
            # Use DuckDuckGo HTML search
            search_url = "https://html.duckduckgo.com/html/"
            params = {"q": query}

            resp = requests.post(
                search_url,
                data=params,
                headers=DEFAULT_HEADERS,
                timeout=15
            )

            if resp.status_code == 429:
                raise RateLimitedError("web_search", retry_after=60)

            resp.raise_for_status()
            html = resp.text

            # Parse results - DuckDuckGo HTML format
            results = []

            # Find result blocks
            result_pattern = r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>([^<]+)</a>'
            snippet_pattern = r'<a[^>]*class="result__snippet"[^>]*>([^<]+)</a>'

            links = re.findall(result_pattern, html)
            snippets = re.findall(snippet_pattern, html)

            for i, (url, title) in enumerate(links[:num_results]):
                result = {
                    "title": title.strip(),
                    "url": url,
                    "snippet": snippets[i].strip() if i < len(snippets) else ""
                }
                results.append(result)

            return {
                "query": query,
                "num_results": len(results),
                "results": results
            }

        except requests.RequestException as e:
            raise MCPToolError("web_search", str(e))

    @mcp.tool()
    def fetch_page_links(url: str, same_domain_only: bool = True) -> dict:
        """Fetch all links from a page.

        Args:
            url: The URL to fetch links from
            same_domain_only: If True, only return links to the same domain

        Returns:
            Dict with url and list of links (href, text)
        """
        parsed_base = urlparse(url)
        base_domain = parsed_base.netloc

        try:
            resp = requests.get(url, headers=DEFAULT_HEADERS, timeout=15)
            resp.raise_for_status()
            html = resp.text

            # Find all links
            link_pattern = r'<a[^>]*href=["\']([^"\']+)["\'][^>]*>([^<]*)</a>'
            matches = re.findall(link_pattern, html, re.IGNORECASE)

            links = []
            seen = set()

            for href, text in matches:
                # Normalize URL
                if href.startswith('//'):
                    href = parsed_base.scheme + ':' + href
                elif href.startswith('/'):
                    href = f"{parsed_base.scheme}://{parsed_base.netloc}{href}"
                elif not href.startswith(('http://', 'https://')):
                    href = urljoin(url, href)

                # Skip non-http links
                if not href.startswith(('http://', 'https://')):
                    continue

                # Filter by domain if requested
                if same_domain_only:
                    link_domain = urlparse(href).netloc
                    if link_domain != base_domain:
                        continue

                # Skip duplicates
                if href in seen:
                    continue
                seen.add(href)

                links.append({
                    "href": href,
                    "text": text.strip()[:100]  # Truncate long link text
                })

            return {
                "url": url,
                "num_links": len(links),
                "links": links[:50]  # Limit to 50 links
            }

        except requests.RequestException as e:
            raise MCPToolError("web_scraper", str(e))
