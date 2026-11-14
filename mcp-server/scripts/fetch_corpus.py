"""Download human-written texts for building registers, on your own computer.

Two sources:

  arxiv     Query the free arXiv API for papers in a category and date range
            (default: before 30 Nov 2022, i.e. before ChatGPT).
  manifest  A CSV of links (header: register,url,...) such as the report from
            the Claude in Chrome research prompt. PDF and HTML pages both work.

Each text is cleaned (front matter, references, tables, captions removed) and
saved as plain text under HUMANIZER_HOME/corpus/<register>/. Then run
build_register.py on that folder. Texts stay on your computer; only the
statistics end up in the register file.

Examples (PowerShell, in mcp-server):

  uv run --extra corpus python scripts/fetch_corpus.py arxiv --register academic:published:cs_engineering --category cs.DC cs.SE cs.PF cs.NI --per-category 4
  uv run --extra corpus python scripts/fetch_corpus.py plos --register academic:published:social_sciences --subject Sociology Psychology "Political science" --per-subject 4
  uv run --extra corpus python scripts/fetch_corpus.py manifest ..\\local\\links.csv
  uv run --extra corpus python scripts/fetch_corpus.py files ..\\local\\manual\\ug_cs --register academic:undergraduate:cs_engineering
  uv run python scripts/build_register.py academic:published:cs_engineering "<HUMANIZER_HOME>\\corpus\\academic__published__cs_engineering"

Be polite to the servers: the script waits between downloads (arXiv asks for 3 s).
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from humanizer_mcp import config  # noqa: E402

UA = "humanizer-corpus/0.1 (research; personal use; https://github.com/blader/humanizer)"
ARXIV_API = "https://export.arxiv.org/api/query"
CUTOFF = "202211300000"
ATOM = "{http://www.w3.org/2005/Atom}"

_START_HEADINGS = re.compile(r"^\s*(?:\d+\.?\s*|[IVX]+\.\s*)?introduction\s*$", re.M | re.I)
_END_HEADINGS = re.compile(
    r"^\s*(?:\d+\.?\s*|[IVX]+\.\s*)?(references|bibliography|list of references|works cited|"
    r"acknowledg(e)?ments?|appendix|appendices|declarations)\s*$",
    re.M | re.I,
)


def folder_for(register: str) -> Path:
    safe = register.replace(":", "__").replace("@", "_at_")
    d = config.home_dir() / "corpus" / safe
    d.mkdir(parents=True, exist_ok=True)
    return d


def http_get(url: str, timeout: int = 60, retries: int = 1) -> tuple[bytes, str]:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout * (attempt + 1)) as r:
                return r.read(), r.headers.get("Content-Type", "")
        except urllib.error.HTTPError as e:
            # 429 = "slow down" and 5xx = temporary server trouble: wait, then try once more.
            if e.code in (429, 500, 502, 503, 504) and attempt < retries:
                wait = 60
                try:
                    wait = min(300, int(e.headers.get("Retry-After", 60)))
                except (TypeError, ValueError):
                    pass
                print(f"    server said {e.code}; waiting {wait} s and retrying once...", file=sys.stderr)
                time.sleep(wait)
                continue
            raise  # 403/404 etc.: a retry will not help, and we do not work around blocks
        except (urllib.error.URLError, TimeoutError, OSError):
            if attempt == retries:
                raise
            print("    no answer, retrying once with a longer timeout...", file=sys.stderr)
            time.sleep(5)
    raise RuntimeError("unreachable")


# ------------------------------------------------------------------ cleaning

def _rebuild_paragraphs(text: str) -> str:
    """Theses exported from Word are often double-spaced: every line is followed by a blank
    line, so 'paragraphs' are single lines. Rebuild real paragraphs from line lengths."""
    chunks = [c for c in re.split(r"\n\s*\n", text) if c.strip()]
    if not chunks:
        return text
    single = sum(1 for c in chunks if len(c.strip().splitlines()) == 1)
    if single / len(chunks) < 0.6:
        return text  # normal layout
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    lengths = sorted(len(l) for l in lines if len(l) > 20)
    typical = lengths[len(lengths) // 2] if lengths else 80
    out, cur = [], []
    for i, line in enumerate(lines):
        cur.append(line)
        nxt = lines[i + 1] if i + 1 < len(lines) else ""
        ends_sentence = re.search(r"[.?!:][\"'”’)\]]?$", line) is not None
        short = len(line) < 0.85 * typical
        heading_next = bool(re.match(r"^(\d+(\.\d+)*\.?\s+)?[A-Z][^.]{0,80}$", nxt)) and len(nxt) < 0.6 * typical
        is_heading = len(cur) == 1 and not ends_sentence and len(line) < 0.6 * typical
        if (ends_sentence and short) or heading_next or is_heading or not nxt:
            out.append(" ".join(cur))
            cur = []
    if cur:
        out.append(" ".join(cur))
    return "\n\n".join(out)


def clean_body(text: str, min_words: int = 25, rebuild: bool = True) -> str:
    """Keep prose paragraphs between the introduction and the references.
    rebuild=False for web pages: their paragraphs are already right, and short ones are real."""
    text = text.replace("\r", "")
    text = re.sub(r"[ \t\u00a0]+", " ", text)
    text = "\n".join("" if re.fullmatch(r"\s*\d{1,3}\s*", l) else l for l in text.split("\n"))  # page numbers
    text = re.sub(r"(\w)-\s*\n(?:\s*\n)?\s*([a-z])", r"\1\2", text)  # hyphenation across lines
    # The table of contents also says "Introduction": use the last match in the first 40%.
    starts = [m for m in _START_HEADINGS.finditer(text) if m.start() < len(text) * 0.4]
    if starts:
        text = text[starts[-1].start():]
    ends = [m for m in _END_HEADINGS.finditer(text) if m.start() > len(text) * 0.5]
    if ends:
        text = text[: ends[0].start()]
    if rebuild:
        text = _rebuild_paragraphs(text)
    keep = []
    for para in re.split(r"\n\s*\n", text):
        p = " ".join(l.strip() for l in para.splitlines() if l.strip())
        if len(p.split()) < min_words:
            continue
        if sum(c.isdigit() for c in p) / max(len(p), 1) > 0.12:
            continue  # tables
        if re.match(r"^(Table|Figure|Fig\.|Listing|Algorithm)\s*\d", p):
            continue
        if sum(ch in "{}=<>|_\\$" for ch in p) > 8:
            continue  # code / maths
        if not re.search(r"[.?!][\"')\]]?\s*$", p):
            continue
        keep.append(p)
    return "\n\n".join(keep)


def pdf_to_text(data: bytes) -> str:
    """pdfminer.six keeps words whole (pypdf can split them: "blockch ain"); pypdf is the fallback."""
    import unicodedata

    raw = ""
    try:
        from pdfminer.high_level import extract_text
        from pdfminer.layout import LAParams

        raw = extract_text(io.BytesIO(data), laparams=LAParams(line_margin=0.5, word_margin=0.1, boxes_flow=0.5))
    except Exception:  # noqa: BLE001
        raw = ""
    if len(raw.split()) < 200:
        from pypdf import PdfReader

        pages = []
        for page in PdfReader(io.BytesIO(data)).pages:
            try:
                pages.append(page.extract_text() or "")
            except Exception:  # noqa: BLE001
                pages.append("")
        raw = "\n".join(pages)
        raw = re.sub(r"([.?!])\n(?=[A-Z])", r"\1\n\n", raw)
    raw = unicodedata.normalize("NFKC", raw)  # ligatures: ﬁ -> fi, ﬀ -> ff
    return raw.replace("\x0c", "\n\n")


def html_to_text(data: bytes, url: str) -> str:
    import trafilatura

    out = trafilatura.extract(data, url=url, include_comments=False, include_tables=False,
                              favor_precision=True, output_format="txt")
    return (out or "").replace("\n", "\n\n")


_EN_COMMON = {"the", "of", "and", "to", "in", "is", "that", "for", "it", "as",
              "with", "on", "are", "this", "be", "by", "was", "not", "or", "which"}


def looks_english(text: str) -> bool:
    """True when common English words make up a normal share of the body.
    English prose sits around 20-30%; other languages fall far below 8%."""
    words = re.findall(r"[a-z]+", text.lower())
    if len(words) < 50:
        return True
    return sum(w in _EN_COMMON for w in words) / len(words) >= 0.08


def save_text(register: str, name: str, text: str, meta: dict, min_words: int) -> bool:
    n = len(text.split())
    if n < min_words:
        print(f"    skipped: only {n} words after cleaning", file=sys.stderr)
        return False
    if not looks_english(text):
        print("    skipped: body is not mainly English", file=sys.stderr)
        return False
    folder = folder_for(register)
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", name)[:80]
    (folder / f"{safe}.txt").write_text(text, encoding="utf-8")
    log = folder / "_sources.jsonl"
    with log.open("a", encoding="utf-8") as f:
        f.write(json.dumps({**meta, "file": f"{safe}.txt", "words": n}, ensure_ascii=False) + "\n")
    print(f"    saved {safe}.txt ({n} words)", file=sys.stderr)
    return True


# ------------------------------------------------------------------ arXiv

def parse_arxiv_feed(xml_bytes: bytes) -> list[dict]:
    root = ET.fromstring(xml_bytes)
    out = []
    for e in root.findall(f"{ATOM}entry"):
        arxiv_id = e.findtext(f"{ATOM}id", "").rsplit("/abs/", 1)[-1]
        pdf = next((l.get("href") for l in e.findall(f"{ATOM}link") if l.get("title") == "pdf"), None)
        out.append({
            "id": arxiv_id,
            "title": " ".join(e.findtext(f"{ATOM}title", "").split()),
            "published": e.findtext(f"{ATOM}published", "")[:10],
            "authors": [a.findtext(f"{ATOM}name", "") for a in e.findall(f"{ATOM}author")],
            "pdf": pdf or f"https://arxiv.org/pdf/{arxiv_id}",
        })
    return out


def run_arxiv(args) -> None:
    got = 0
    seen_authors: set[str] = set()
    for cat in args.category:
        query = f"cat:{cat} AND submittedDate:[{args.since}0000 TO {args.until}]"
        url = ARXIV_API + "?" + urllib.parse.urlencode({
            "search_query": query, "start": args.offset, "max_results": args.per_category * 4,
            "sortBy": "submittedDate", "sortOrder": "descending"})
        print(f"arXiv {cat}: {query}", file=sys.stderr)
        feed, _ = http_get(url)
        entries = parse_arxiv_feed(feed)
        saved = 0
        for ent in entries:
            if saved >= args.per_category:
                break
            first = (ent["authors"] or ["?"])[0]
            if first in seen_authors:
                continue  # spread across authors
            time.sleep(3)
            print(f"  {ent['id']}  {ent['title'][:70]}", file=sys.stderr)
            try:
                data, _ = http_get(ent["pdf"])
                text = clean_body(pdf_to_text(data))
            except Exception as ex:  # noqa: BLE001
                print(f"    failed: {ex}", file=sys.stderr)
                continue
            meta = {"source": "arxiv", "id": ent["id"], "title": ent["title"], "year": ent["published"][:4],
                    "authors": ent["authors"][:5], "url": ent["pdf"], "category": cat}
            if save_text(args.register, f"arxiv_{ent['id']}", text, meta, args.min_words):
                saved += 1
                seen_authors.add(first)
        got += saved
        time.sleep(3)
    print(f"Done: {got} papers in {folder_for(args.register)}", file=sys.stderr)


# ------------------------------------------------------------------ PLOS ONE

PLOS_API = "https://api.plos.org/search"
_JATS_DROP = {"table-wrap", "fig", "disp-formula", "inline-formula", "supplementary-material",
              "ref-list", "fn-group", "table", "graphic", "media"}


def jats_body_text(xml_bytes: bytes) -> str:
    """Prose paragraphs from a JATS article: the <body>, minus tables, figures and formulas."""
    root = ET.fromstring(xml_bytes)
    body = root.find(".//body")
    if body is None:
        return ""
    for parent in list(body.iter()):
        kids = list(parent)
        for i, child in enumerate(kids):
            if child.tag in _JATS_DROP:
                tail = child.tail or ""  # keep the text that follows the removed element
                if i > 0:
                    kids[i - 1].tail = (kids[i - 1].tail or "") + tail
                else:
                    parent.text = (parent.text or "") + tail
                parent.remove(child)
    paras = []
    for sec_title_or_p in body.iter():
        if sec_title_or_p.tag == "p":
            t = " ".join("".join(sec_title_or_p.itertext()).split())
            if t:
                paras.append(t)
    return "\n\n".join(paras)


def run_plos(args) -> None:
    got = 0
    seen_first_authors: set[str] = set()
    for subject in args.subject:
        params = {
            "q": f'subject:"{subject}"',
            "fq": ('journal_key:PLoSONE AND doc_type:full AND article_type:"Research Article" AND '
                   f"publication_date:[{args.since}-01-01T00:00:00Z TO {args.until}-12-31T23:59:59Z]"),
            "fl": "id,title_display,publication_date,author_display",
            "rows": args.per_subject * 4, "start": args.offset, "wt": "json",
        }
        url = PLOS_API + "?" + urllib.parse.urlencode(params)
        print(f"PLOS ONE '{subject}' {args.since}-{args.until}", file=sys.stderr)
        data, _ = http_get(url)
        docs = json.loads(data)["response"]["docs"]
        saved = 0
        for d in docs:
            if saved >= args.per_subject:
                break
            first = (d.get("author_display") or ["?"])[0]
            if first in seen_first_authors:
                continue
            doi = d["id"]
            time.sleep(2)
            title = " ".join(str(d.get("title_display", "")).split())
            print(f"  {doi}  {title[:70]}", file=sys.stderr)
            try:
                xml, _ = http_get(f"https://journals.plos.org/plosone/article/file?id={urllib.parse.quote(doi)}&type=manuscript")
                text = clean_body(jats_body_text(xml), min_words=20, rebuild=False)
            except Exception as ex:  # noqa: BLE001
                print(f"    failed: {ex}", file=sys.stderr)
                continue
            meta = {"source": "plos_one", "doi": doi, "title": title, "year": str(d.get("publication_date", ""))[:4],
                    "authors": (d.get("author_display") or [])[:5], "subject": subject}
            if save_text(args.register, "plos_" + doi.split("/")[-1], text, meta, args.min_words):
                saved += 1
                seen_first_authors.add(first)
        got += saved
    print(f"Done: {got} articles in {folder_for(args.register)}", file=sys.stderr)


# ------------------------------------------------------------------ OpenAlex

OPENALEX_API = "https://api.openalex.org/works"
# OpenAlex "fields" (Scopus ASJC): 12 Arts and Humanities, 14 Business/Management/Accounting,
# 20 Economics, 32 Psychology, 33 Social Sciences, 27 Medicine, 31 Physics, 16 Chemistry ...
OPENALEX_FIELDS = {"humanities": 12, "business": 14, "economics": 20, "psychology": 32,
                   "social_sciences": 33, "medicine": 27, "physics": 31, "chemistry": 16}


def run_openalex(args) -> None:
    field = OPENALEX_FIELDS.get(args.field, args.field)
    params = {
        "filter": (f"publication_year:{args.since}-{args.until},type:article,is_oa:true,"
                   f"primary_topic.field.id:{field},language:en,has_fulltext:true"),
        "sort": "cited_by_count:desc",  # well-read journal articles, not stray uploads
        "per-page": min(200, args.count * 5), "page": args.page,
        "select": "id,display_name,publication_year,best_oa_location,authorships",
    }
    url = OPENALEX_API + "?" + urllib.parse.urlencode(params)
    print(f"OpenAlex field {field} {args.since}-{args.until}", file=sys.stderr)
    results = None
    for attempt in range(3):  # OpenAlex sometimes cuts a large reply short
        data, _ = http_get(url)
        try:
            results = json.loads(data)["results"]
            break
        except json.JSONDecodeError:
            print("    OpenAlex reply was cut off; asking again...", file=sys.stderr)
            time.sleep(5)
    if results is None:
        sys.exit("OpenAlex kept sending incomplete replies; try again in a minute.")
    saved, seen_hosts, seen_authors = 0, {}, set()
    for w in results:
        if saved >= args.count:
            break
        loc = w.get("best_oa_location") or {}
        pdf = loc.get("pdf_url")
        if not pdf:
            continue
        host = urllib.parse.urlparse(pdf).netloc
        auths = [a.get("author", {}).get("display_name", "") for a in w.get("authorships") or []]
        first = auths[0] if auths else "?"
        if seen_hosts.get(host, 0) >= args.max_per_site or first in seen_authors:
            continue  # spread across journals/publishers and authors
        title = " ".join(str(w.get("display_name", "")).split())
        print(f"  {w.get('publication_year')}  {title[:70]}  [{host}]", file=sys.stderr)
        time.sleep(1.5)
        try:
            body, ctype = http_get(pdf)
            if not body[:5].lstrip().startswith(b"%PDF"):
                print("    not a PDF (probably a landing or login page), skipped", file=sys.stderr)
                continue
            text = clean_body(pdf_to_text(body))
        except Exception as ex:  # noqa: BLE001
            print(f"    failed: {ex}", file=sys.stderr)
            continue
        meta = {"source": "openalex", "openalex_id": w.get("id"), "title": title,
                "year": w.get("publication_year"), "authors": auths[:5], "url": pdf}
        if save_text(args.register, "oa_" + str(w.get("id", "")).rsplit("/", 1)[-1], text, meta, args.min_words):
            saved += 1
            seen_hosts[host] = seen_hosts.get(host, 0) + 1
            seen_authors.add(first)
    print(f"Done: {saved} articles in {folder_for(args.register)}", file=sys.stderr)


# ------------------------------------------------------------------ StackExchange

SE_API = "https://api.stackexchange.com/2.3/answers"


def se_body_to_text(html_fragment: str) -> str:
    """Answer HTML -> prose. Code blocks and quoted text are not the author's prose, so drop them."""
    import html as htmllib

    t = re.sub(r"(?is)<(pre|code|blockquote)[^>]*>.*?</\1>", " ", html_fragment)
    t = re.sub(r"(?i)</(p|li|h\d)>|<br\s*/?>", "\n\n", t)
    t = re.sub(r"<[^>]+>", " ", t)
    t = htmllib.unescape(t)
    paras = [" ".join(p.split()) for p in re.split(r"\n\s*\n", t)]
    return "\n\n".join(p for p in paras if p)


def run_stackexchange(args) -> None:
    import datetime as dt

    frm = int(dt.datetime(int(args.since), 1, 1).timestamp())
    to = int(dt.datetime(int(args.until), 12, 31, 23, 59).timestamp())
    total = 0
    for site in args.site:
        params = {"site": site, "sort": "votes", "order": "desc", "fromdate": frm, "todate": to,
                  "pagesize": min(100, args.per_site * 4), "filter": "withbody"}
        data, _ = http_get(SE_API + "?" + urllib.parse.urlencode(params))
        try:
            import gzip
            data = gzip.decompress(data)  # the API always gzips
        except OSError:
            pass
        items = json.loads(data).get("items", [])
        print(f"StackExchange {site}: {len(items)} answers", file=sys.stderr)
        saved, owners = 0, set()
        for it in items:
            if saved >= args.per_site:
                break
            owner = (it.get("owner") or {}).get("user_id")
            if owner in owners:
                continue  # one answer per person
            text = se_body_to_text(it.get("body", ""))
            meta = {"source": "stackexchange", "site": site, "answer_id": it.get("answer_id"),
                    "score": it.get("score"), "year": dt.datetime.fromtimestamp(it.get("creation_date", 0)).year,
                    "url": f"https://{site}.stackexchange.com/a/{it.get('answer_id')}"}
            if save_text(args.register, f"se_{site}_{it.get('answer_id')}", text, meta, args.min_words):
                saved += 1
                owners.add(owner)
        total += saved
        time.sleep(2)
    print(f"Done: {total} answers in {folder_for(args.register)}", file=sys.stderr)


# ------------------------------------------------------------------ manifest

def run_manifest(args) -> None:
    rows = []
    with open(args.csv, encoding="utf-8") as f:
        text = f.read()
    # accept a markdown report with ```csv blocks, or a plain CSV
    blocks = re.findall(r"```csv\s*\n(.*?)```", text, re.S) or [text]
    for block in blocks:
        rows += list(csv.DictReader(io.StringIO(block.strip())))
    print(f"{len(rows)} links in {args.csv}", file=sys.stderr)
    for i, row in enumerate(rows, 1):
        url, register = (row.get("url") or "").strip(), (row.get("register") or "").strip()
        if not url or not register or row.get("access", "").strip() == "needs_login":
            continue
        try:
            year = int(re.findall(r"\d{4}", row.get("year", "") or "0")[0])
        except IndexError:
            year = 0
        if year and year > 2022:
            print(f"  skip (published {year}): {url}", file=sys.stderr)
            continue
        print(f"[{i}/{len(rows)}] {register}  {url}", file=sys.stderr)
        try:
            data, ctype = http_get(url)
            # Trust the bytes, not the URL: a ".pdf" link can return an HTML error or login page.
            is_pdf = data[:5].lstrip().startswith(b"%PDF") or (
                "pdf" in ctype.lower() and not data.lstrip()[:1] == b"<")
            raw = pdf_to_text(data) if is_pdf else html_to_text(data, url)
            text = clean_body(raw, min_words=25) if is_pdf else clean_body(raw, min_words=3, rebuild=False)
            if not text.strip() and not is_pdf:
                print("    got a web page, not a PDF: download it in your browser and use the 'files' mode",
                      file=sys.stderr)
        except Exception as ex:  # noqa: BLE001
            print(f"    failed: {ex}", file=sys.stderr)
            continue
        name = re.sub(r"^https?://(www\.)?", "", url).strip("/")
        min_words = args.min_words if register.startswith("academic") else min(args.min_words, 350)
        save_text(register, name, text, {**row, "source": "manifest"}, min_words)
        time.sleep(args.delay)


def run_files(args) -> None:
    """Clean PDFs / HTML / text files you downloaded yourself (e.g. from sites that block scripts)."""
    paths = [p for p in sorted(Path(args.folder).glob("*")) if p.suffix.lower() in {".pdf", ".html", ".htm", ".txt", ".md", ".docx"}]
    print(f"{len(paths)} files in {args.folder}", file=sys.stderr)
    for p in paths:
        print(f"  {p.name}", file=sys.stderr)
        try:
            data = p.read_bytes()
            if p.suffix.lower() == ".pdf" or data[:4] == b"%PDF":
                text = clean_body(pdf_to_text(data))
            elif p.suffix.lower() in {".html", ".htm"}:
                text = clean_body(html_to_text(data, p.as_uri()), min_words=3, rebuild=False)
            elif p.suffix.lower() == ".docx":
                from humanizer_mcp.text_utils import read_document
                text = clean_body(read_document(p))
            else:
                text = clean_body(data.decode("utf-8", errors="replace"), min_words=3, rebuild=False)
        except Exception as ex:  # noqa: BLE001
            print(f"    failed: {ex}", file=sys.stderr)
            continue
        save_text(args.register, f"local_{p.stem}", text, {"source": "local_file", "file_name": p.name}, args.min_words)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("arxiv")
    a.add_argument("--register", required=True)
    a.add_argument("--category", nargs="+", required=True, help="e.g. cs.DC cs.SE (see arxiv.org/category_taxonomy)")
    a.add_argument("--per-category", type=int, default=4)
    a.add_argument("--since", default="2015", help="year, e.g. 2015")
    a.add_argument("--until", default=CUTOFF, help="YYYYMMDDHHMM, default 30 Nov 2022")
    a.add_argument("--offset", type=int, default=0, help="skip this many results (for a second batch)")
    a.add_argument("--min-words", type=int, default=1500)
    m = sub.add_parser("manifest")
    m.add_argument("csv", help="CSV or markdown report with ```csv blocks")
    m.add_argument("--min-words", type=int, default=800)
    m.add_argument("--delay", type=float, default=2.0)
    pl = sub.add_parser("plos", help="PLOS ONE research articles via the public API")
    pl.add_argument("--register", required=True)
    pl.add_argument("--subject", nargs="+", required=True, help='e.g. "Sociology" "Psychology" "Ecology"')
    pl.add_argument("--per-subject", type=int, default=4)
    pl.add_argument("--since", default="2015")
    pl.add_argument("--until", default="2019")
    pl.add_argument("--offset", type=int, default=0)
    pl.add_argument("--min-words", type=int, default=2000)
    oa = sub.add_parser("openalex", help="open-access journal articles via the OpenAlex API")
    oa.add_argument("--register", required=True)
    oa.add_argument("--field", required=True, help="humanities, business, economics, psychology, social_sciences, ... or a field id")
    oa.add_argument("--count", type=int, default=15)
    oa.add_argument("--since", default="2015")
    oa.add_argument("--until", default="2019")
    oa.add_argument("--page", type=int, default=1)
    oa.add_argument("--max-per-site", type=int, default=2)
    oa.add_argument("--min-words", type=int, default=3000)
    se = sub.add_parser("stackexchange", help="top answers from StackExchange sites")
    se.add_argument("--register", default="forum_post")
    se.add_argument("--site", nargs="+", required=True, help="e.g. academia workplace writers history")
    se.add_argument("--per-site", type=int, default=4)
    se.add_argument("--since", default="2015")
    se.add_argument("--until", default="2019")
    se.add_argument("--min-words", type=int, default=250)
    f = sub.add_parser("files", help="clean files you downloaded yourself")
    f.add_argument("folder")
    f.add_argument("--register", required=True)
    f.add_argument("--min-words", type=int, default=800)
    args = ap.parse_args()
    if args.cmd == "files":
        run_files(args)
        return
    if args.cmd == "plos":
        run_plos(args)
        return
    if args.cmd == "openalex":
        run_openalex(args)
        return
    if args.cmd == "stackexchange":
        run_stackexchange(args)
        return
    if args.cmd == "arxiv":
        args.since = args.since[:4] + "0101"
        run_arxiv(args)
    else:
        run_manifest(args)


if __name__ == "__main__":
    main()
