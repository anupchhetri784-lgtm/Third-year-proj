import requests
import re
import urllib.parse
import html
import time
import random
import hashlib

# ─── In-memory result cache (avoids hammering DDG for same queries) ──────────
_cache = {}  # key -> (timestamp, results)
_CACHE_TTL = 300  # 5 minutes

def _cache_key(query):
    return hashlib.md5(query.lower().strip().encode()).hexdigest()


def search_web(query, num_results=4):
    """
    Queries DuckDuckGo HTML search for the query, parses results,
    and returns a list of dicts with title, url, snippet, and host.

    Features:
    - Auto-appends 'Nepal' to queries that don't mention it (keeps results travel-relevant)
    - In-memory result cache (TTL=5 min) to avoid rate limiting
    - Retry logic with short random jitter delay on 202 (rate-limit) responses
    """
    search_query = query.strip()
    if not search_query:
        return []

    # Keep results Nepal-travel focused
    if "nepal" not in search_query.lower():
        search_query = f"{search_query} Nepal"

    # Check cache first
    ck = _cache_key(search_query)
    if ck in _cache:
        ts, cached_results = _cache[ck]
        if time.time() - ts < _CACHE_TTL:
            return cached_results
        else:
            del _cache[ck]

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                      '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
    }
    ddg_url = 'https://html.duckduckgo.com/html/'
    params = {'q': search_query}

    results = []
    max_retries = 2

    for attempt in range(max_retries + 1):
        try:
            response = requests.get(ddg_url, params=params, headers=headers, timeout=8)

            if response.status_code == 202:
                # DDG rate-limiting – wait and retry
                if attempt < max_retries:
                    wait = 1.0 + random.uniform(0.3, 0.8)
                    print(f"DDG rate-limit (202), retrying in {wait:.1f}s (attempt {attempt+1})...")
                    time.sleep(wait)
                    continue
                else:
                    print("DDG rate-limit persisted after retries, returning empty.")
                    return []

            if response.status_code != 200:
                print(f"Web search failed with HTTP {response.status_code}")
                return []

            content = response.text
            blocks = content.split('web-result ')

            for b in blocks[1:]:
                title_match = re.search(
                    r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', b, re.DOTALL)
                snippet_match = re.search(
                    r'class="result__snippet"[^>]*>(.*?)</a>', b, re.DOTALL)

                if title_match and snippet_match:
                    raw_url = title_match.group(1)
                    raw_title = title_match.group(2)
                    raw_snippet = snippet_match.group(1)

                    # Decode the DDG redirect to get the real URL
                    real_url = raw_url
                    if 'uddg=' in raw_url:
                        parsed = urllib.parse.urlparse(raw_url)
                        qs = urllib.parse.parse_qs(parsed.query)
                        if 'uddg' in qs:
                            real_url = qs['uddg'][0]
                    elif raw_url.startswith('//'):
                        real_url = 'https:' + raw_url

                    # Clean host for display
                    try:
                        host = urllib.parse.urlparse(real_url).netloc
                        if host.startswith('www.'):
                            host = host[4:]
                    except Exception:
                        host = 'web'

                    # Strip HTML tags
                    clean_title = re.sub(r'<[^>]+>', '', raw_title)
                    clean_snippet = re.sub(r'<[^>]+>', '', raw_snippet)

                    # Unescape HTML entities & collapse whitespace
                    clean_title = ' '.join(html.unescape(clean_title).split())
                    clean_snippet = ' '.join(html.unescape(clean_snippet).split())

                    results.append({
                        'title': clean_title,
                        'url': real_url,
                        'snippet': clean_snippet,
                        'host': host,
                    })

                    if len(results) >= num_results:
                        break

            # Store in cache and return
            _cache[ck] = (time.time(), results)
            return results

        except Exception as e:
            print(f"Error executing web search (attempt {attempt+1}): {e}")
            if attempt < max_retries:
                time.sleep(0.5)
            else:
                return []

    return results


if __name__ == '__main__':
    print("Testing search_web function directly...")
    res = search_web("what is the local currency?")
    for index, r in enumerate(res):
        try:
            print(f"\n[{index+1}] {r['title']}")
            print(f"    URL: {r['url']} ({r['host']})")
            print(f"    Snippet: {r['snippet']}")
        except UnicodeEncodeError:
            title_safe = r['title'].encode('ascii', 'replace').decode('ascii')
            snippet_safe = r['snippet'].encode('ascii', 'replace').decode('ascii')
            print(f"\n[{index+1}] {title_safe}")
            print(f"    URL: {r['url']} ({r['host']})")
            print(f"    Snippet: {snippet_safe}")
