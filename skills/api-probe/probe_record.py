"""Record what one API probe actually saw, and trim a real response into a safe test fixture.

The api-probe skill says every API detail comes from a run, not from memory: status, size, speed, the
headers that set limits, what an error body says, and one trimmed real response saved as a fixture. This
module is network-free; you make the call however you like (keys from the environment, in headers only),
then hand the result here. `record_probe` writes down status/bytes/seconds/limit headers and classifies
the error (401/403 key, 400 bad name, 429 too many, 5xx server). `trim_fixture` keeps the shape of a JSON
response while cutting long lists to a few items. `scan_secrets` refuses a fixture that still carries a key-
or token-shaped string. `fixture_name` builds `<source>_<what>_<date>.json`. `rejected_names` pulls the
offending symbol(s) out of an all-or-nothing rejection body so the name mapping can be found.

Usage:
    from probe_record import record_probe, trim_fixture, scan_secrets, fixture_name
    rec = record_probe("alpaca", url, status, headers, body_bytes, seconds)
    fixture = trim_fixture(json.loads(body_bytes), max_items=3)
    assert not scan_secrets(json.dumps(fixture))
    python probe_record.py --selftest
"""
import json
import re
import sys

LIMIT_HEADER_HINTS = ("ratelimit", "rate-limit", "retry-after", "cache-control", "expires", "etag",
                      "last-modified", "deprecation", "sunset", "link", "content-type", "x-request-id")

SECRET_PATTERNS = [
    (re.compile(r"(?i)\b(api[_-]?key|secret|token|password|passwd|authorization)\b\s*[\"']?\s*[:=]\s*[\"']?[A-Za-z0-9_\-./+]{8,}"), "key=value secret"),
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9_\-.=]{16,}"), "bearer token"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "AWS access key id"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"), "GitHub token"),
    (re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}\b"), "sk- style API key"),
    (re.compile(r"\b(PK|AK)[A-Z0-9]{18}\b"), "broker key id shape"),
]


def classify_status(status):
    """Name the cause of a status in words, the way the client must."""
    if 200 <= status < 300:
        return "ok"
    if status in (401, 403):
        return "auth: wrong/missing key or plan does not include this"
    if status == 400 or status == 422:
        return "bad request: often one bad name/param rejects the whole call"
    if status == 404:
        return "not found: wrong path or unknown name"
    if status == 414:
        return "URL too long: batch is too big for a GET"
    if status == 429:
        return "rate limited: too many calls, honour Retry-After"
    if 500 <= status < 600:
        return "server error: retry later, not our bug yet"
    return "unexpected status"


def limit_headers(headers):
    """Keep only the headers that decide pacing, limits, caching or deprecation (lower-cased keys)."""
    out = {}
    for k, v in (headers or {}).items():
        lk = k.lower()
        if any(h in lk for h in LIMIT_HEADER_HINTS):
            out[lk] = v
    return out


def rejected_names(body, candidates):
    """Return the candidate names that appear in an error body (which name killed the request)."""
    text = body.decode("utf-8", "replace") if isinstance(body, bytes) else str(body)
    hits = []
    for name in candidates:
        if re.search(r"(?<![A-Za-z0-9.\-])" + re.escape(name) + r"(?![A-Za-z0-9]|[.\-_][A-Za-z0-9])", text):
            hits.append(name)
    return hits


def record_probe(source, url, status, headers, body, seconds, n_names=None, note=""):
    """One dated-able probe record: status, cause in words, bytes, seconds, per-name speed, limit headers."""
    size = len(body) if body is not None else 0
    rec = {
        "source": source,
        "url": re.sub(r"(?i)([?&](?:api[_-]?key|token|key|secret)=)[^&]+", r"\1REDACTED", url),
        "status": int(status),
        "cause": classify_status(int(status)),
        "bytes": size,
        "seconds": round(float(seconds), 4),
        "url_length": len(url),
        "headers": limit_headers(headers),
        "note": note,
    }
    if n_names:
        rec["names_per_call"] = n_names
        rec["seconds_per_name"] = round(float(seconds) / n_names, 6)
    return rec


def trim_fixture(obj, max_items=3, max_str=200):
    """Keep the structure of a JSON value but cut every list to max_items and long strings to max_str."""
    if isinstance(obj, dict):
        return {k: trim_fixture(v, max_items, max_str) for k, v in obj.items()}
    if isinstance(obj, list):
        return [trim_fixture(v, max_items, max_str) for v in obj[:max_items]]
    if isinstance(obj, str) and len(obj) > max_str:
        return obj[:max_str]
    return obj


def scan_secrets(text):
    """Return a list of (label, excerpt) for anything secret-shaped. Empty list = clean."""
    found = []
    for pat, label in SECRET_PATTERNS:
        for m in pat.finditer(text):
            s = m.group(0)
            found.append((label, s[:6] + "..."))
    return found


def fixture_name(source, what, date):
    """tests/fixtures/feeds/<source>_<what>_<date>.json naming, with unsafe characters folded."""
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        raise ValueError("date must be YYYY-MM-DD, got %r" % (date,))
    clean = lambda s: re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-").lower()
    return "%s_%s_%s.json" % (clean(source), clean(what), date)


SOFT_REFUSAL = re.compile(r"(?i)rate.?limit|too many|per second|per minute|sparingly|slow down|throttl|quota|"
                          r"exceeded|premium|demo purposes|try again")


def soft_refusal(status, body):
    """A refusal that arrives as HTTP 200 (Alpha Vantage answers "Information": "...1 request per second" with
    200). Returns the matched words, or "" when the body reads like real data."""
    if not 200 <= status < 300:
        return ""
    text = body.decode("utf-8", "replace") if isinstance(body, bytes) else str(body)
    m = SOFT_REFUSAL.search(text[:2000])
    return m.group(0) if m else ""


PREMIUM = re.compile(r"(?i)premium (endpoint|plan|feature|subscription)|subscribe to any of the premium|"
                     r"not (included|available) (in|on) your (plan|subscription)|upgrade your (plan|subscription)")


def refusal_kind(status, body):
    """'premium' | 'rate' | 'error' | '' for one response. A refusal is a SHORT JSON object (<= 3 keys) whose text
    names it; a data file that merely contains the word (a CSV row "Premium Income Fund") is not one.
    'premium' (2026-10-24 L11362: Alpha Vantage NEWS_SENTIMENT and OVERVIEW answered HTTP 200 + {"Information":
    "...This is a premium endpoint..."}) means the plan lacks the endpoint: drop it, never retry, never pace for it.
    'rate' means slow down and retry later. 'error' is a short {"Error Message"/"error_message": ...} body."""
    if not 200 <= status < 300:
        return "rate" if status == 429 else "error"
    text = body.decode("utf-8", "replace") if isinstance(body, bytes) else str(body)
    try:
        obj = json.loads(text)
    except ValueError:
        return ""
    if not isinstance(obj, dict) or not obj or len(obj) > 3:
        return ""
    words = " ".join(str(v) for v in obj.values())
    if PREMIUM.search(words):
        return "premium"
    if SOFT_REFUSAL.search(words):
        return "rate"
    if any(k.lower().replace(" ", "_") in ("error_message", "error", "errors") for k in obj):
        return "error"
    return ""


def key_values_in(data, values_by_name):
    """Names whose real VALUE appears in data (raw, URL-encoded or lower-cased). Returns names only, never values.
    A shape scan (scan_secrets) misses a plain 16-character key; this compares the value itself (2026-10-24 L11419:
    av_fixtures.py asserted `key not in body` for every fixture). Values shorter than 8 characters are skipped as
    too likely to match by chance; callers should say so."""
    import urllib.parse
    blob = data if isinstance(data, bytes) else str(data).encode("utf-8")
    low = blob.lower()
    hits = []
    for name, value in values_by_name.items():
        if not value or len(value) < 8:
            continue
        forms = {value.encode(), urllib.parse.quote(value, safe="").encode()}
        if any(f in blob for f in forms) or value.lower().encode() in low:
            hits.append(name)
    return hits


def burst_probe(call, n=2, gap_s=0.1, sleep=None, clock=None):
    """Question 6: call the endpoint n times gap_s apart and report the first call that is refused - the hidden
    per-second limit a single probe never sees. `call()` -> (status, body). Returns a list of
    {"i", "status", "cause", "soft_refusal", "t"} and prints nothing; refused calls still cost quota, so keep n small.
    """
    import time as _t
    sleep, clock = sleep or _t.sleep, clock or _t.monotonic
    t0, out = clock(), []
    for i in range(n):
        if i:
            sleep(gap_s)
        status, body = call()
        soft = soft_refusal(status, body)
        out.append({"i": i, "status": status, "cause": "refused (soft, HTTP 200)" if soft else classify_status(status),
                    "soft_refusal": soft, "t": round(clock() - t0, 3)})
    return out


def burst_verdict(rows):
    """'NO HIDDEN LIMIT at this pace' or 'HIDDEN LIMIT: call k refused after t s (<cause>)'."""
    for r in rows:
        if r["soft_refusal"] or not 200 <= r["status"] < 300:
            return f"HIDDEN LIMIT: call {r['i'] + 1} refused after {r['t']} s ({r['cause']}: {r['soft_refusal'] or r['status']})"
    return f"NO HIDDEN LIMIT at this pace ({len(rows)} calls)"


def _selftest():
    ok = True

    def check(cond, desc):
        nonlocal ok
        print(("PASS " if cond else "FAIL ") + desc)
        ok = ok and bool(cond)

    body = json.dumps({"bars": {"AAPL": [{"t": i, "c": 100 + i} for i in range(50)]}, "next_page_token": None}).encode()
    hdr = {"X-RateLimit-Remaining": "199", "Content-Type": "application/json", "Server": "nginx", "Date": "x"}
    rec = record_probe("alpaca", "https://x.test/v2/bars?symbols=AAPL&apikey=SHOULDNOTSHOW", 200, hdr, body, 0.5, n_names=2)
    check(rec["status"] == 200 and rec["cause"] == "ok" and rec["bytes"] == len(body), "record keeps status, cause and byte size")
    check(set(rec["headers"]) == {"x-ratelimit-remaining", "content-type"}, "only limit/pacing headers are kept")
    check("SHOULDNOTSHOW" not in rec["url"] and rec["seconds_per_name"] == 0.25, "key in URL redacted; seconds per name computed")

    err = record_probe("alpaca", "https://x.test/v2/bars", 400, {}, b'{"message":"invalid symbol: BRK-B"}', 0.1)
    check(err["cause"].startswith("bad request") and rejected_names(b'{"message":"invalid symbol: BRK-B"}', ["AAPL", "BRK-B", "BRK"]) == ["BRK-B"],
          "400 classified and the one rejecting name is found (BRK but not BRK-B prefix confusion)")
    check(classify_status(429).startswith("rate limited") and classify_status(403).startswith("auth"), "429 and 403 named in words")

    fx = trim_fixture(json.loads(body), max_items=3)
    check(len(fx["bars"]["AAPL"]) == 3 and fx["bars"]["AAPL"][2] == {"t": 2, "c": 102} and "next_page_token" in fx,
          "trim keeps structure and first items, cuts long lists")

    fake = "api" + "_key" + '": "' + "Ab3" * 6 + '"'
    check(scan_secrets(json.dumps(fx)) == [] and len(scan_secrets(fake)) >= 1, "secret scan passes clean fixture and CATCHES a planted key")

    check(fixture_name("Alpaca", "daily bars", "2026-10-12") == "alpaca_daily-bars_2026-10-12.json", "fixture name built")
    try:
        fixture_name("alpaca", "bars", "10/12/2026")
        check(False, "bad date in fixture name is refused")
    except ValueError:
        check(True, "bad date in fixture name is refused")

    quote = b'{"Global Quote": {"01. symbol": "IBM", "05. price": "251.0600"}}'
    av = (b'{"Information": "Thank you for using Alpha Vantage! Please consider spreading out your free API requests '
          b'more sparingly (1 request per second)."}')
    replies = iter([(200, quote), (200, av)])
    t = [0.0]
    rows = burst_probe(lambda: next(replies), n=2, gap_s=0.1, sleep=lambda dt: t.__setitem__(0, t[0] + dt),
                       clock=lambda: t[0])
    check(rows[0]["soft_refusal"] == "" and rows[1]["soft_refusal"] and rows[1]["t"] == 0.1,
          "burst probe: the real 2026-10-21 Alpha Vantage refusal is caught although it came with HTTP 200")
    check(burst_verdict(rows).startswith("HIDDEN LIMIT: call 2") and
          burst_verdict(burst_probe(lambda: (200, quote), n=3, gap_s=0, sleep=lambda dt: None)).startswith("NO HIDDEN"),
          "burst verdict names the refused call, and a clean run says NO HIDDEN LIMIT")
    check(burst_verdict(burst_probe(lambda: (429, b"{}"), n=1, sleep=lambda dt: None)).startswith("HIDDEN LIMIT: call 1"),
          "a 429 counts as refused")

    prem = (b'{\n    "Information": "Thank you for using Alpha Vantage! This is a premium endpoint. You may subscribe '
            b'to any of the premium plans at https://www.alphavantage.co/premium/ to instantly unlock all premium '
            b'endpoints"\n}')
    check(refusal_kind(200, prem) == "premium" and refusal_kind(200, av) == "rate",
          "refusal_kind: the real 2026-10-24 premium answer (HTTP 200) is 'premium', the per-second one is 'rate'")
    csv = b"symbol,name,exchange\r\nPAPI,Parametric Premium Income ETF,NYSE\r\n"
    check(refusal_kind(200, csv) == "" and refusal_kind(200, quote) == "" and soft_refusal(200, csv),
          "planted: a CSV naming a 'Premium Income' fund is data for refusal_kind (soft_refusal alone flags it)")
    check(refusal_kind(200, b'{"error_message": "Bad Request.  The series does not exist."}') == "error"
          and refusal_kind(429, b"") == "rate", "a short error_message body is 'error' (FRED, L7207); 429 is 'rate'")
    import secrets as _s
    k1, k2 = _s.token_hex(8), _s.token_urlsafe(6)          # runtime-only fake keys, never printed
    import urllib.parse as _u
    blob = b"url=https://x.test/q?apikey=" + _u.quote(k1).encode() + b"&f=1"
    check(key_values_in(blob, {"A_KEY": k1, "SHORT": k2}) == ["A_KEY"] and key_values_in(b"clean", {"A_KEY": k1}) == [],
          "key_values_in names a planted real key value, skips short values, passes a clean file")
    check(k1 not in json.dumps(key_values_in(blob, {"A_KEY": k1})), "key_values_in returns names, not values")
    return ok


def main(argv):
    if not argv or argv[0] == "--selftest":
        return 0 if _selftest() else 1
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
