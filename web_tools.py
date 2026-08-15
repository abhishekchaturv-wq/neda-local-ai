"""On-demand internet access for NEDA — a tool it can call during a conversation
when it needs current information beyond what's indexed locally. NOT an autonomous
background crawler: this only runs when the model actually decides to call it while
answering a real question, same as the HPM/Pine tools.

Uses DuckDuckGo's keyless HTML endpoint (no API key, no signup) for search, and a
generic page-text extractor for fetching a specific URL — both free, local, zero
Claude tokens involved.

web_fetch (below) is a raw HTTP GET — it has no JS engine, so a client-rendered
SPA (Angular/React admin console, etc.) comes back as an empty shell. Added
web_fetch_rendered (2026-08-14) for exactly that case: it drives a real headless
Chrome instance to let the page's JS actually run before reading the text. It
reuses the user's already-installed Chrome.app via selenium + webdriver-manager
(the latter only downloads the small chromedriver binary, not a second copy of
the browser). Important limit, unlike Claude's claude-in-chrome tool: this opens
a brand-new, logged-out browser profile every time — no cookies, no session, no
SSO. It renders JS fine but cannot see anything behind a login wall.
"""
import re
import ssl
import urllib.parse
import urllib.request

from bs4 import BeautifulSoup

_SSLCTX = ssl.create_default_context()
_SSLCTX.check_hostname = False
_SSLCTX.verify_mode = ssl.CERT_NONE


def _get(url, timeout=15):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://duckduckgo.com/",
    })
    with urllib.request.urlopen(req, timeout=timeout, context=_SSLCTX) as r:
        return r.read().decode("utf-8", errors="ignore")


def web_search(query: str) -> list[dict]:
    """Search the public web for a query and return the top results. Use this when
    a question needs current information that isn't in the local knowledge base —
    e.g. something not related to BMC Helix or the user's Pine Script library.

    Args:
        query: The search query.

    Returns:
        A list of up to 8 dicts, each with title, url, and snippet.
    """
    url = "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({"q": query})
    try:
        html = _get(url)
    except Exception as e:
        return [{"error": f"search failed: {e}"}]

    soup = BeautifulSoup(html, "html.parser")
    results = []
    for r in soup.select(".result")[:8]:
        title_el = r.select_one(".result__a")
        snippet_el = r.select_one(".result__snippet")
        if not title_el:
            continue
        href = title_el.get("href", "")
        # DuckDuckGo HTML results wrap the real URL in a redirect param
        parsed = urllib.parse.urlparse(href)
        qs = urllib.parse.parse_qs(parsed.query)
        real_url = qs.get("uddg", [href])[0]
        results.append({
            "title": title_el.get_text(strip=True),
            "url": real_url,
            "snippet": snippet_el.get_text(strip=True) if snippet_el else "",
        })
    return results


def web_fetch(url: str) -> str:
    """Fetch a specific web page and return its main text content. Use this after
    web_search to read the actual content of a promising result, or when the user
    gives you a direct URL to look at.

    Args:
        url: The full URL to fetch.

    Returns:
        The page's extracted text (truncated to ~4000 chars), or an error message.
    """
    try:
        html = _get(url, timeout=20)
    except Exception as e:
        return f"error fetching {url}: {e}"

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer"]):
        tag.decompose()
    text = soup.get_text(separator="\n", strip=True)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text[:4000]


def web_fetch_rendered(url: str, wait_seconds: float = 3.0) -> str:
    """Fetch a web page THROUGH A REAL HEADLESS BROWSER so its JavaScript actually
    runs before reading the text — use this when plain web_fetch comes back
    basically empty (a bare shell like "Hash Handler", "Loading...", a near-empty
    <div id="app">, or similar) on a page that's obviously a JS-driven single-page
    app (an admin console, dashboard, or similar client-rendered app).

    IMPORTANT LIMIT: this opens a brand-new, logged-out browser session every
    call — no cookies, no saved login, no SSO. It can render a public JS-heavy
    page fine, but if the URL requires being logged in, this will just render
    the login page, not the real content behind it. If that happens, say so
    plainly rather than treating whatever comes back as the real answer.

    Args:
        url: The full URL to fetch.
        wait_seconds: How long to let the page's JS finish rendering before
            reading the text (default 3s; raise it for slower-loading pages).

    Returns:
        The rendered page's visible text (truncated to ~4000 chars), or an
        error message.
    """
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from webdriver_manager.chrome import ChromeDriverManager
    import time as _time

    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--window-size=1280,1024")

    driver = None
    try:
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)
        driver.set_page_load_timeout(30)
        driver.get(url)
        _time.sleep(wait_seconds)
        text = driver.find_element("tag name", "body").text
    except Exception as e:
        return f"error rendering {url}: {e}"
    finally:
        if driver:
            driver.quit()

    text = re.sub(r"\n{3,}", "\n\n", text.strip())
    return text[:4000] if text else "(page rendered but body text was empty)"
