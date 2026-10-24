#!/usr/bin/env python3
"""
Usage examples:
    python yuna_blog_publisher.py --generate
    python yuna_blog_publisher.py --publish
    python yuna_blog_publisher.py --publish --yuna-only
    python yuna_blog_publisher.py --publish --limit 1
    python yuna_blog_publisher.py --list
    python yuna_blog_publisher.py --stats
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import random
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import markdown as md_lib
import requests
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
TOPICS_FILE = BASE_DIR / "topics.json"
PUBLISHED_FILE = BASE_DIR / "published.json"
LOG_FILE = BASE_DIR / "publisher.log"
DRAFTS_DIR = BASE_DIR / "drafts"

load_dotenv(BASE_DIR / ".env")
YUNA_LINK = "https://ko-fi.com/s/45662d5cc0"
MAX_ARTICLES_PER_RUN = 2
MAX_GENERATION_ATTEMPTS = 3
GEMINI_RETRIES = 3
MIN_WORDS = 800
REQUEST_TIMEOUT = 60
GEMINI_TIMEOUT = 120
DEVTO_RATE_LIMIT_WAIT = 300
DEFAULT_GEMINI_MODEL = "gemini-3.5-flash-lite"
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "{model}:generateContent"
)
DEFAULT_DISCLOSURE = (
    "Disclosure: I am the developer of YUNA, the software mentioned in "
    "the last section."
)

# ─── YUNA Blog settings ────────────────────────────────────────────────
# Paths are relative to where index.html (main site) lives.
# Adjust BLOG_SITE_ROOT if your site is not in the same folder as this script.
BLOG_SITE_ROOT = Path(os.getenv("BLOG_SITE_ROOT", str(BASE_DIR.parent))).resolve()
BLOG_DIR = BLOG_SITE_ROOT / "blogs"           # where .md files live
BLOG_INDEX = BLOG_DIR / "index.json"          # posts manifest
SITEMAP_FILE = BLOG_SITE_ROOT / "sitemap.xml" # sitemap at site root
BLOG_PUBLIC_URL = os.getenv(
    "BLOG_PUBLIC_URL", "https://yunaai.online"
).rstrip("/")
BLOG_AUTHOR = os.getenv("BLOG_AUTHOR", "Code-7")
BLOG_REBUILD_SITEMAP = (
    os.getenv("BLOG_REBUILD_SITEMAP", "true").lower() == "true"
)
BLOG_AUTO_GIT = os.getenv("BLOG_AUTO_GIT", "false").lower() == "true"

PROMPT_TEMPLATE = (
    "You are a technical writer for a developer blog. Write a high-quality "
    "SEO-optimized article. TOPIC: {title}. TARGET KEYWORD: {keyword}. "
    "STRICT RULES: Length 900-1300 words in English. Tone helpful, "
    "technical, honest, no marketing hype, no exclamation marks. "
    "Structure: H1 title, Introduction, 3-5 H2 sections with concrete "
    "technical content, at least one real code snippet (Ollama commands, "
    "Python, or terminal), and a final section titled 'A Practical Option "
    "for Windows Users'. In the first 80 percent of the article, DO NOT "
    "mention YUNA. In the final section ONLY, mention YUNA once as one "
    "practical option for Windows users who want a local AI companion with "
    "a Live2D face, and include this exact link once: "
    "https://ko-fi.com/s/45662d5cc0. Do NOT use markdown bold for "
    "emphasis. Output MUST be in Markdown format. Start the output with "
    "exactly: <!-- META: [150-character description] -->. CRITICAL: The "
    "article must be useful EVEN IF the reader never clicks the YUNA link."
)

META_RE = re.compile(r"^\s*<!--\s*META:\s*(.+?)\s*-->", re.DOTALL)

logger = logging.getLogger("yuna_publisher")


class PublishError(Exception):
    """Raised when a platform rejects or fails a publish request."""


# --------------------------------------------------------------------------
# Setup and persistence helpers
# --------------------------------------------------------------------------

def setup_logging() -> None:
    """Configure logging to publisher.log and to the console."""
    logger.setLevel(logging.INFO)
    if logger.handlers:
        return
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S"
    )
    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setFormatter(formatter)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)


def title_hash(title: str) -> str:
    """Return the SHA-256 hex digest of a normalised article title."""
    normalised = " ".join(title.strip().lower().split())
    return hashlib.sha256(normalised.encode("utf-8")).hexdigest()


def now_iso() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_topics() -> list[dict[str, Any]]:
    """Load and validate the topic list from topics.json."""
    if not TOPICS_FILE.exists():
        logger.error("topics.json not found at %s", TOPICS_FILE)
        return []
    try:
        data = json.loads(TOPICS_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        logger.error("topics.json is not valid JSON: %s", exc)
        return []
    topics = []
    for item in data:
        if all(k in item for k in ("title", "keyword", "tags")):
            topics.append(item)
        else:
            logger.warning("Skipping malformed topic entry: %s", item)
    return topics


def load_published() -> dict[str, Any]:
    """Load published.json, returning an empty structure if missing."""
    if not PUBLISHED_FILE.exists():
        return {"articles": {}}
    try:
        data = json.loads(PUBLISHED_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        logger.error(
            "published.json is corrupt. Fix or remove it before running "
            "again to avoid duplicate posts."
        )
        sys.exit(1)
    data.setdefault("articles", {})
    return data


def save_published(published: dict[str, Any]) -> None:
    """Write published.json atomically."""
    tmp_path = PUBLISHED_FILE.with_suffix(".json.tmp")
    tmp_path.write_text(
        json.dumps(published, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    tmp_path.replace(PUBLISHED_FILE)


def record_publication(
    published: dict[str, Any],
    topic: dict[str, Any],
    platform: str,
    url: str,
) -> None:
    """Record a successful platform publication in published.json."""
    entry = published["articles"].setdefault(
        title_hash(topic["title"]),
        {
            "title": topic["title"],
            "keyword": topic["keyword"],
            "created_at": now_iso(),
            "platforms": {},
        },
    )
    entry["platforms"][platform] = {"url": url, "published_at": now_iso()}
    save_published(published)


# --------------------------------------------------------------------------
# Text helpers
# --------------------------------------------------------------------------

def slugify(text: str) -> str:
    """Convert text to a lowercase, hyphenated slug."""
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def devto_tags(tags: list[str]) -> list[str]:
    """Return up to four alphanumeric lowercase tags for Dev.to."""
    cleaned = [re.sub(r"[^a-z0-9]", "", t.lower()) for t in tags]
    return [t for t in cleaned if t][:4]


def extract_meta(text: str) -> tuple[str, str]:
    """Split the META comment from the article body.

    Returns a tuple of (description, body_without_meta).
    """
    match = META_RE.match(text)
    if not match:
        return "", text.strip()
    description = " ".join(match.group(1).split())
    return description, text[match.end():].strip()


def strip_h1(body: str) -> str:
    """Remove a leading H1 line, since platforms take the title separately."""
    lines = body.splitlines()
    for index, line in enumerate(lines):
        if not line.strip():
            continue
        if line.startswith("# "):
            return "\n".join(lines[index + 1:]).strip()
        break
    return body


def md_to_html(body: str) -> str:
    """Convert Markdown to HTML for platforms that need HTML content."""
    return md_lib.markdown(body, extensions=["fenced_code", "tables"])


def clean_model_output(text: str) -> str:
    """Strip code fences or preamble that the model may wrap around output."""
    text = text.strip()
    fence = re.match(r"^```(?:markdown|md)?\s*\n(.*)\n```$", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    meta_index = text.find("<!-- META:")
    if meta_index > 0:
        text = text[meta_index:]
    return text


def validate_article(text: str) -> list[str]:
    """Check an article against the publishing rules.

    Returns a list of failure descriptions; an empty list means it passed.
    """
    failures: list[str] = []
    if not META_RE.match(text):
        failures.append("missing '<!-- META: ... -->' tag at the top")
    word_count = len(re.findall(r"\S+", text))
    if word_count < MIN_WORDS:
        failures.append(f"only {word_count} words (minimum {MIN_WORDS})")
    if text.count("```") < 2:
        failures.append("no complete code block found")
    link_count = text.count(YUNA_LINK)
    if link_count != 1:
        failures.append(f"YUNA link appears {link_count} times (need 1)")
    cutoff = int(len(text) * 0.8)
    if "yuna" in text[:cutoff].lower():
        failures.append("YUNA is mentioned in the first 80 percent")
    return failures


# --------------------------------------------------------------------------
# Gemini
# --------------------------------------------------------------------------

def call_gemini(prompt: str) -> str | None:
    """Call the Gemini API with up to 3 attempts and exponential backoff."""
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        logger.error("GEMINI_API_KEY is not set. Fill it in your .env file.")
        return None
    model = os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL).strip()
    url = GEMINI_URL.format(model=model)
    headers = {"Content-Type": "application/json", "x-goog-api-key": api_key}
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.7, "maxOutputTokens": 4096},
    }
    for attempt in range(1, GEMINI_RETRIES + 1):
        try:
            resp = requests.post(
                url, headers=headers, json=payload, timeout=GEMINI_TIMEOUT
            )
            if resp.status_code == 200:
                text = _parse_gemini_response(resp.json())
                if text:
                    return text
                logger.warning("Gemini returned an empty response.")
            elif resp.status_code in (429, 500, 502, 503, 504):
                logger.warning(
                    "Gemini HTTP %s (attempt %d/%d): %s",
                    resp.status_code, attempt, GEMINI_RETRIES,
                    resp.text[:200],
                )
            else:
                logger.error(
                    "Gemini HTTP %s: %s. Check GEMINI_API_KEY and "
                    "GEMINI_MODEL ('%s') in your .env file.",
                    resp.status_code, resp.text[:300], model,
                )
                return None
        except (requests.RequestException, ValueError) as exc:
            logger.warning(
                "Gemini request failed (attempt %d/%d): %s",
                attempt, GEMINI_RETRIES, exc,
            )
        if attempt < GEMINI_RETRIES:
            delay = 5 * 2 ** (attempt - 1)
            logger.info("Retrying Gemini in %d seconds.", delay)
            time.sleep(delay)
    logger.error("Gemini failed after %d attempts.", GEMINI_RETRIES)
    return None


def _parse_gemini_response(data: dict[str, Any]) -> str:
    """Extract the generated text from a Gemini response payload."""
    try:
        parts = data["candidates"][0]["content"]["parts"]
    except (KeyError, IndexError, TypeError):
        return ""
    return "".join(part.get("text", "") for part in parts).strip()


def generate_article(topic: dict[str, Any]) -> str | None:
    """Generate an article for a topic, regenerating up to 3 times.

    Returns the validated article text, or None if every attempt failed.
    """
    prompt = PROMPT_TEMPLATE.format(
        title=topic["title"], keyword=topic["keyword"]
    )
    for attempt in range(1, MAX_GENERATION_ATTEMPTS + 1):
        logger.info(
            "Generating '%s' (attempt %d/%d)",
            topic["title"], attempt, MAX_GENERATION_ATTEMPTS,
        )
        raw = call_gemini(prompt)
        if raw is None:
            continue
        text = clean_model_output(raw)
        failures = validate_article(text)
        if not failures:
            return text
        logger.warning("Validation failed: %s", "; ".join(failures))
    logger.error("Skipping '%s': no valid article produced.", topic["title"])
    return None


def add_disclosure(text: str) -> str:
    """Append an affiliation disclosure after validation has passed.

    The text can be customised with AFFILIATION_DISCLOSURE in .env, but it
    is always added so readers know the author is the software's developer.
    """
    disclosure = os.getenv("AFFILIATION_DISCLOSURE", "").strip()
    if not disclosure:
        disclosure = DEFAULT_DISCLOSURE
    return f"{text.rstrip()}\n\n---\n\n{disclosure}\n"


# --------------------------------------------------------------------------
# YUNA Blog publisher (static site — writes files locally)
# --------------------------------------------------------------------------

def _yuna_blog_slug(topic: dict[str, Any]) -> str:
    """Return a URL-safe slug for the YUNA blog post."""
    base = slugify(topic["title"])
    return base[:80].strip("-") or "post"


def _yuna_blog_excerpt(description: str, body: str) -> str:
    """Return a clean 150-200 character excerpt."""
    desc = " ".join((description or "").split())
    if desc:
        return desc[:200]
    plain = re.sub(r"[#*`>\[\]()!_-]", " ", body)
    plain = " ".join(plain.split())
    return plain[:200]


def _yuna_blog_date(topic: dict[str, Any]) -> str:
    """Return an ISO date (YYYY-MM-DD) — uses topic date if provided."""
    iso = topic.get("date")
    if iso:
        return str(iso)[:10]
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _ensure_blog_index() -> dict[str, Any]:
    """Load blogs/index.json, creating a default if it does not exist."""
    if not BLOG_INDEX.exists():
        BLOG_DIR.mkdir(parents=True, exist_ok=True)
        data = {"posts": []}
        BLOG_INDEX.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return data
    try:
        data = json.loads(BLOG_INDEX.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PublishError(
            f"{BLOG_INDEX} is corrupt. Fix or remove it before publishing."
        ) from exc
    if isinstance(data, list):
        data = {"posts": data}
    data.setdefault("posts", [])
    return data


def _save_blog_index(data: dict[str, Any]) -> None:
    """Write blogs/index.json atomically, sorted by date descending."""
    posts = data.get("posts", [])
    posts.sort(key=lambda p: p.get("date", ""), reverse=True)
    data["posts"] = posts
    tmp = BLOG_INDEX.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    tmp.replace(BLOG_INDEX)


def _update_sitemap(slug: str, date: str) -> None:
    """Rebuild sitemap.xml from the current blogs/index.json.

    The sitemap always reflects the blog's real content, so it never goes
    out of sync with the manifest. Creates the file if it does not exist.
    """
    if not BLOG_REBUILD_SITEMAP:
        return

    posts = _ensure_blog_index().get("posts", [])
    urls = [
        {
            "loc": f"{BLOG_PUBLIC_URL}/",
            "lastmod": date,
            "changefreq": "weekly",
            "priority": "1.0",
        },
        {
            "loc": f"{BLOG_PUBLIC_URL}/blog/",
            "lastmod": date,
            "changefreq": "weekly",
            "priority": "0.9",
        },
    ]
    for post in posts:
        post_slug = post.get("slug")
        if not post_slug:
            continue
        urls.append({
            "loc": f"{BLOG_PUBLIC_URL}/blog/?p={post_slug}",
            "lastmod": post.get("date", date),
            "changefreq": "monthly",
            "priority": "0.7",
        })

    lines = ['<?xml version="1.0" encoding="UTF-8"?>']
    lines.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')
    for u in urls:
        lines.append("  <url>")
        lines.append(f"    <loc>{u['loc']}</loc>")
        lines.append(f"    <lastmod>{u['lastmod']}</lastmod>")
        lines.append(f"    <changefreq>{u['changefreq']}</changefreq>")
        lines.append(f"    <priority>{u['priority']}</priority>")
        lines.append("  </url>")
    lines.append("</urlset>")
    SITEMAP_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    logger.info("Updated sitemap: %s", SITEMAP_FILE)


def _auto_git_push(topic: dict[str, Any]) -> None:
    """Optionally stage, commit, and push blog changes to git."""
    if not BLOG_AUTO_GIT:
        return
    try:
        subprocess.run(
            ["git", "add", str(BLOG_DIR), str(SITEMAP_FILE)],
            cwd=BLOG_SITE_ROOT, check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", f"blog: publish '{topic['title']}'"],
            cwd=BLOG_SITE_ROOT, check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "push"], cwd=BLOG_SITE_ROOT, check=True,
            capture_output=True,
        )
        logger.info("Pushed new post to git remote.")
    except (OSError, subprocess.CalledProcessError) as exc:
        logger.warning("Git auto-push failed: %s", exc)


def publish_yuna_blog(
    topic: dict[str, Any], description: str, body: str
) -> str:
    """Save an article to blogs/ and update index.json + sitemap.xml.

    Returns the public URL of the new post.
    """
    BLOG_DIR.mkdir(parents=True, exist_ok=True)

    slug = _yuna_blog_slug(topic)
    post_file = BLOG_DIR / f"{slug}.md"
    date_iso = _yuna_blog_date(topic)

    # Write the Markdown file (include title as H1 for direct viewing).
    content = f"# {topic['title']}\n\n{body.strip()}\n"
    post_file.write_text(content, encoding="utf-8")
    logger.info("Wrote blog post: %s", post_file)

    # Update index.json
    index_data = _ensure_blog_index()
    existing_slugs = {p.get("slug") for p in index_data["posts"]}
    entry = {
        "slug": slug,
        "title": topic["title"],
        "date": date_iso,
        "author": BLOG_AUTHOR,
        "excerpt": _yuna_blog_excerpt(description, body),
        "tags": topic.get("tags", [])[:6],
    }
    if slug in existing_slugs:
        for i, p in enumerate(index_data["posts"]):
            if p.get("slug") == slug:
                index_data["posts"][i] = entry
                break
    else:
        index_data["posts"].append(entry)
    _save_blog_index(index_data)
    logger.info(
        "Updated %s (%d posts total)",
        BLOG_INDEX, len(index_data["posts"]),
    )

    # Update sitemap.xml
    _update_sitemap(slug, date_iso)

    # Optionally push to git
    _auto_git_push(topic)

    return f"{BLOG_PUBLIC_URL}/blog/?p={slug}"


# --------------------------------------------------------------------------
# Platform publishers
# --------------------------------------------------------------------------

def _require_ok(
    resp: requests.Response, platform: str, ok: tuple[int, ...], hint: str
) -> None:
    """Raise PublishError when a response status is not an accepted one."""
    if resp.status_code not in ok:
        raise PublishError(
            f"{platform} returned HTTP {resp.status_code}: "
            f"{resp.text[:300]} | Check: {hint}"
        )


def publish_devto(
    topic: dict[str, Any], description: str, body: str
) -> str:
    """Publish to Dev.to, retrying once after a 429 rate-limit response."""
    url = "https://dev.to/api/articles"
    headers = {
        "api-key": os.environ["DEVTO_API_KEY"],
        "Content-Type": "application/json",
    }
    payload = {
        "article": {
            "title": topic["title"],
            "published": True,
            "body_markdown": body,
            "tags": devto_tags(topic["tags"]),
            "description": description[:150],
        }
    }
    resp = requests.post(
        url, headers=headers, json=payload, timeout=REQUEST_TIMEOUT
    )
    if resp.status_code == 429:
        logger.warning(
            "Dev.to returned 429. Waiting %d seconds before one retry.",
            DEVTO_RATE_LIMIT_WAIT,
        )
        time.sleep(DEVTO_RATE_LIMIT_WAIT)
        resp = requests.post(
            url, headers=headers, json=payload, timeout=REQUEST_TIMEOUT
        )
    _require_ok(resp, "Dev.to", (200, 201), "DEVTO_API_KEY is valid")
    return resp.json().get("url", "")


def publish_hashnode(
    topic: dict[str, Any], description: str, body: str
) -> str:
    """Publish to Hashnode using the publishPost GraphQL mutation."""
    query = (
        "mutation PublishPost($input: PublishPostInput!) {"
        " publishPost(input: $input) { post { id url } } }"
    )
    variables = {
        "input": {
            "title": topic["title"],
            "publicationId": os.environ["HASHNODE_PUBLICATION_ID"],
            "contentMarkdown": body,
            "tags": [
                {"name": tag, "slug": slugify(tag)}
                for tag in topic["tags"][:5]
            ],
        }
    }
    resp = requests.post(
        "https://gql.hashnode.com",
        headers={
            "Authorization": os.environ["HASHNODE_TOKEN"],
            "Content-Type": "application/json",
        },
        json={"query": query, "variables": variables},
        timeout=REQUEST_TIMEOUT,
    )
    _require_ok(
        resp, "Hashnode", (200,),
        "HASHNODE_TOKEN and HASHNODE_PUBLICATION_ID",
    )
    data = resp.json()
    if data.get("errors"):
        raise PublishError(
            f"Hashnode GraphQL errors: {data['errors']} | Check: token, "
            "publication ID, and tag slugs"
        )
    post = (data.get("data") or {}).get("publishPost", {}).get("post", {})
    return post.get("url", "")


def publish_medium(
    topic: dict[str, Any], description: str, body: str
) -> str:
    """Publish to Medium via the endpoint specified for this tool."""
    resp = requests.post(
        "https://api.medium.com/v1/users/me/posts",
        headers={
            "Authorization": f"Bearer {os.environ['MEDIUM_TOKEN']}",
            "Content-Type": "application/json",
        },
        json={
            "title": topic["title"],
            "contentFormat": "markdown",
            "content": f"# {topic['title']}\n\n{body}",
            "tags": topic["tags"][:5],
            "publishStatus": "public",
        },
        timeout=REQUEST_TIMEOUT,
    )
    _require_ok(
        resp, "Medium", (200, 201),
        "Medium no longer issues new integration tokens, and the posts "
        "endpoint may require your numeric author id instead of 'me'",
    )
    return resp.json().get("data", {}).get("url", "")


def publish_blogger(
    topic: dict[str, Any], description: str, body: str
) -> str:
    """Publish to Blogger API v3 using a refreshed OAuth2 access token."""
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
    except ImportError as exc:
        raise PublishError(
            "google-auth is not installed. Run: pip install google-auth"
        ) from exc
    credentials = Credentials(
        token=None,
        refresh_token=os.environ["BLOGGER_REFRESH_TOKEN"],
        client_id=os.environ["BLOGGER_CLIENT_ID"],
        client_secret=os.environ["BLOGGER_CLIENT_SECRET"],
        token_uri="https://oauth2.googleapis.com/token",
    )
    try:
        credentials.refresh(Request())
    except Exception as exc:
        raise PublishError(
            f"Could not refresh Blogger OAuth2 token: {exc} | Check: "
            "BLOGGER_CLIENT_ID, BLOGGER_CLIENT_SECRET, "
            "BLOGGER_REFRESH_TOKEN"
        ) from exc
    blog_id = os.environ["BLOGGER_BLOG_ID"]
    resp = requests.post(
        f"https://www.googleapis.com/blogger/v3/blogs/{blog_id}/posts/",
        headers={
            "Authorization": f"Bearer {credentials.token}",
            "Content-Type": "application/json",
        },
        json={
            "kind": "blogger#post",
            "title": topic["title"],
            "content": md_to_html(body),
            "labels": topic["tags"],
        },
        timeout=REQUEST_TIMEOUT,
    )
    _require_ok(
        resp, "Blogger", (200, 201),
        "BLOGGER_BLOG_ID and that the Blogger API v3 is enabled",
    )
    return resp.json().get("url", "")


def publish_wordpress(
    topic: dict[str, Any], description: str, body: str
) -> str:
    """Publish to WordPress.com using the REST API v1.1."""
    site_id = os.environ["WORDPRESS_SITE_ID"]
    resp = requests.post(
        f"https://public-api.wordpress.com/rest/v1.1/sites/{site_id}"
        "/posts/new",
        headers={"Authorization": f"Bearer {os.environ['WORDPRESS_TOKEN']}"},
        data={
            "title": topic["title"],
            "content": md_to_html(body),
            "excerpt": description,
            "tags": ",".join(topic["tags"]),
            "status": "publish",
        },
        timeout=REQUEST_TIMEOUT,
    )
    _require_ok(
        resp, "WordPress.com", (200, 201),
        "WORDPRESS_TOKEN scope and WORDPRESS_SITE_ID",
    )
    return resp.json().get("URL", "")


def publish_tumblr(
    topic: dict[str, Any], description: str, body: str
) -> str:
    """Publish a text post to Tumblr API v2.

    The credential set in .env (consumer key/secret plus token/secret) is
    OAuth 1.0a, so requests-oauthlib signs the request.
    """
    try:
        from requests_oauthlib import OAuth1
    except ImportError as exc:
        raise PublishError(
            "requests-oauthlib is not installed. Run: "
            "pip install requests-oauthlib"
        ) from exc
    auth = OAuth1(
        os.environ["TUMBLR_CONSUMER_KEY"],
        os.environ["TUMBLR_CONSUMER_SECRET"],
        os.environ["TUMBLR_TOKEN"],
        os.environ["TUMBLR_TOKEN_SECRET"],
    )
    blog = os.environ["TUMBLR_BLOG_IDENTIFIER"]
    resp = requests.post(
        f"https://api.tumblr.com/v2/blog/{blog}/post",
        auth=auth,
        data={
            "type": "text",
            "title": topic["title"],
            "body": md_to_html(body),
            "tags": ",".join(topic["tags"]),
            "state": "published",
        },
        timeout=REQUEST_TIMEOUT,
    )
    _require_ok(
        resp, "Tumblr", (200, 201),
        "all four TUMBLR_* credentials and TUMBLR_BLOG_IDENTIFIER",
    )
    post_id = resp.json().get("response", {}).get("id", "")
    return f"https://{blog}/post/{post_id}" if "." in blog else str(post_id)


PLATFORMS: list[dict[str, Any]] = [
    {
        "name": "YUNA Blog",
        "required": True,
        "func": publish_yuna_blog,
        "env": [],
        "local": True,
    },
    {
        "name": "Dev.to", "required": True, "func": publish_devto,
        "env": ["DEVTO_API_KEY"],
    },
    {
        "name": "Hashnode", "required": True, "func": publish_hashnode,
        "env": ["HASHNODE_TOKEN", "HASHNODE_PUBLICATION_ID"],
    },
    {
        "name": "Medium", "required": False, "func": publish_medium,
        "env": ["MEDIUM_TOKEN"],
    },
    {
        "name": "Blogger", "required": False, "func": publish_blogger,
        "env": [
            "BLOGGER_CLIENT_ID", "BLOGGER_CLIENT_SECRET",
            "BLOGGER_REFRESH_TOKEN", "BLOGGER_BLOG_ID",
        ],
    },
    {
        "name": "WordPress.com", "required": False,
        "func": publish_wordpress,
        "env": ["WORDPRESS_TOKEN", "WORDPRESS_SITE_ID"],
    },
    {
        "name": "Tumblr", "required": False, "func": publish_tumblr,
        "env": [
            "TUMBLR_CONSUMER_KEY", "TUMBLR_CONSUMER_SECRET",
            "TUMBLR_TOKEN", "TUMBLR_TOKEN_SECRET",
            "TUMBLR_BLOG_IDENTIFIER",
        ],
    },
]


def is_configured(platform: dict[str, Any]) -> bool:
    """Return True when a platform is available for publishing.

    Local publishers (e.g. YUNA Blog) need no credentials — they are
    enabled automatically as long as they are flagged ``local: True``.
    """
    if platform.get("local"):
        return True
    for name in platform["env"]:
        value = os.getenv(name, "").strip()
        if not value or value.lower().startswith("your_"):
            return False
    return True


def publish_article(
    topic: dict[str, Any], article: str, published: dict[str, Any]
) -> int:
    """Publish one article to every configured platform.

    Returns the number of platforms that accepted the article.
    """
    description, body = extract_meta(article)
    body = strip_h1(body)
    targets = [p for p in PLATFORMS if is_configured(p)]
    if not targets:
        logger.error(
            "No platform is configured. Fill at least DEVTO_API_KEY or "
            "HASHNODE_TOKEN + HASHNODE_PUBLICATION_ID in .env."
        )
        return 0
    done = published["articles"].get(title_hash(topic["title"]), {})
    already = done.get("platforms", {})
    success = 0
    for index, platform in enumerate(targets):
        name = platform["name"]
        if name in already:
            logger.info("Already on %s, skipping.", name)
            continue
        publish_func: Callable[..., str] = platform["func"]
        try:
            url = publish_func(topic, description, body)
        except (PublishError, requests.RequestException) as exc:
            level = logging.ERROR if platform["required"] else logging.WARNING
            logger.log(level, "%s publish failed: %s", name, exc)
        else:
            success += 1
            record_publication(published, topic, name, url)
            logger.info("Published to %s: %s", name, url or "(no URL)")
        if index < len(targets) - 1:
            pause = random.uniform(10, 30)
            logger.info("Waiting %.0f seconds before next platform.", pause)
            time.sleep(pause)
    return success


# --------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------

def pending_topics(
    topics: list[dict[str, Any]], published: dict[str, Any]
) -> list[dict[str, Any]]:
    """Return topics whose title hash has not been published yet."""
    return [
        t for t in topics
        if title_hash(t["title"]) not in published["articles"]
    ]


def run_generation(limit: int, publish: bool) -> None:
    """Generate articles and optionally publish them."""
    topics = load_topics()
    published = load_published()
    queue = pending_topics(topics, published)[:limit]
    if not queue:
        logger.info("No unpublished topics left. Add more to topics.json.")
        return
    DRAFTS_DIR.mkdir(exist_ok=True)
    for index, topic in enumerate(queue):
        article = generate_article(topic)
        if article is None:
            continue
        article = add_disclosure(article)
        draft_path = DRAFTS_DIR / f"{title_hash(topic['title'])[:12]}.md"
        draft_path.write_text(article, encoding="utf-8")
        logger.info("Saved draft: %s", draft_path)
        if publish:
            count = publish_article(topic, article, published)
            logger.info(
                "'%s' published to %d platform(s).", topic["title"], count
            )
            if index < len(queue) - 1:
                pause = random.uniform(90, 240)
                logger.info("Waiting %.0f seconds before next article.", pause)
                time.sleep(pause)


def show_list() -> None:
    """Print every published article with its platform URLs."""
    published = load_published()
    if not published["articles"]:
        print("Nothing published yet.")
        return
    for entry in published["articles"].values():
        print(f"\n{entry['title']}  (keyword: {entry['keyword']})")
        for name, info in entry["platforms"].items():
            print(f"  - {name}: {info['url']}  [{info['published_at']}]")


def show_stats() -> None:
    """Print summary statistics about published articles."""
    published = load_published()
    topics = load_topics()
    articles = published["articles"]
    per_platform: dict[str, int] = {}
    for entry in articles.values():
        for name in entry["platforms"]:
            per_platform[name] = per_platform.get(name, 0) + 1
    print(f"Topics total:       {len(topics)}")
    print(f"Articles published: {len(articles)}")
    print(f"Topics remaining:   {len(pending_topics(topics, published))}")
    for name, count in sorted(per_platform.items()):
        print(f"  {name}: {count}")
    configured = [p["name"] for p in PLATFORMS if is_configured(p)]
    print("Configured platforms: " + (", ".join(configured) or "none"))
    # ── YUNA Blog status ──
    if BLOG_INDEX.exists():
        try:
            posts = _ensure_blog_index().get("posts", [])
            print(f"YUNA blog posts:    {len(posts)}  ({BLOG_INDEX})")
        except PublishError as exc:
            print(f"YUNA blog:          ERROR — {exc}")
    else:
        print(f"YUNA blog:          not initialised ({BLOG_INDEX})")


def _force_yuna_only() -> None:
    """Restrict the active PLATFORMS list to the YUNA Blog publisher."""
    PLATFORMS[:] = [p for p in PLATFORMS if p["name"] == "YUNA Blog"]


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line argument parser."""
    parser = argparse.ArgumentParser(
        description="Generate and publish technical blog articles."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--generate", action="store_true",
        help="generate articles into drafts/ without publishing",
    )
    group.add_argument(
        "--publish", action="store_true",
        help="generate and publish articles",
    )
    group.add_argument(
        "--list", action="store_true", help="show published articles"
    )
    group.add_argument(
        "--stats", action="store_true", help="show publishing statistics"
    )
    parser.add_argument(
        "--limit", type=int, default=MAX_ARTICLES_PER_RUN,
        help=f"number of articles (hard maximum {MAX_ARTICLES_PER_RUN})",
    )
    parser.add_argument(
        "--yuna-only", action="store_true",
        help="publish only to the YUNA static blog (skip other platforms)",
    )
    return parser


def main() -> None:
    """Entry point: parse arguments and run the chosen command."""
    load_dotenv(BASE_DIR / ".env")
    setup_logging()
    args = build_parser().parse_args()
    if args.list:
        show_list()
    elif args.stats:
        show_stats()
    else:
        limit = max(1, min(args.limit, MAX_ARTICLES_PER_RUN))
        if args.limit > MAX_ARTICLES_PER_RUN:
            logger.warning(
                "Limit capped at %d articles per run.", MAX_ARTICLES_PER_RUN
            )
        if args.yuna_only:
            _force_yuna_only()
        run_generation(limit, publish=args.publish)


if __name__ == "__main__":
    main()