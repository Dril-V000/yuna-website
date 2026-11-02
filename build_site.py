#!/usr/bin/env python3
"""
build_site.py - generates static, crawlable SEO pages for https://yunaai.online

Run from the website root (next to index.html):
    pip install markdown
    python build_site.py

Reads:   blogs/index.json, blogs/<slug>.md, reviews.json (optional)
Writes:  assets/pages.css, blog/, blog/<slug>/, faq/, ai-models/,
         requirements/, reviews/ (only if reviews.json has entries),
         sitemap.xml, robots.txt (only if missing)
"""
import html
import json
import re
import sys
from datetime import date
from pathlib import Path

try:
    import markdown
except ImportError:
    sys.exit("Missing dependency. Run:  pip install markdown")

SITE = "https://yunaai.online"
ROOT = Path(__file__).resolve().parent
OG_IMAGE = SITE + "/preview/og-image.png"
TODAY = date.today().isoformat()
E = html.escape

CSS = """:root{--bg:#04040c;--card:#0d0d1f;--border:rgba(110,150,255,.14);--accent:#64b5f6;--accent2:#a78bfa;--text:#eef1ff;--text2:#9aa3cc;--text3:#5a6390}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);font:16px/1.7 Inter,system-ui,-apple-system,"Segoe UI",sans-serif}
nav{position:sticky;top:0;z-index:5;display:flex;gap:1.3rem;align-items:center;flex-wrap:wrap;padding:.85rem 1.5rem;background:rgba(4,4,12,.92);border-bottom:1px solid var(--border)}
nav .logo{font-weight:700;letter-spacing:5px;color:var(--accent);text-decoration:none;margin-right:auto}
nav a{color:var(--text2);text-decoration:none;font-size:.9rem}
nav a:hover{color:var(--accent)}
nav a.cta{background:linear-gradient(135deg,#64b5f6,#a78bfa);color:#04040c;padding:.45rem 1rem;border-radius:9px;font-weight:700}
.wrap{max-width:820px;margin:0 auto;padding:2.5rem 1.5rem 4rem}
h1{font-size:clamp(1.9rem,4.5vw,2.7rem);line-height:1.15;margin-bottom:1rem}
h2{font-size:1.45rem;margin:2.2rem 0 .7rem}
h3{font-size:1.1rem;margin:1.4rem 0 .4rem;color:#7dd3fc}
p,li{color:var(--text2);margin:.7rem 0}
ul,ol{padding-left:1.5rem}
a{color:var(--accent)}
.lead{font-size:1.1rem}
.card{display:block;background:var(--card);border:1px solid var(--border);border-radius:12px;padding:1.2rem 1.3rem;margin:1rem 0;text-decoration:none}
a.card:hover{border-color:rgba(110,150,255,.45)}
.card h2,.card h3{margin:0 0 .4rem;color:var(--text)}
.card p{margin:.3rem 0}
.meta{color:var(--text3);font-size:.85rem}
.stars{color:#fbbf24;letter-spacing:2px}
.md pre{background:#07071a;border:1px solid var(--border);border-radius:10px;padding:1rem;overflow-x:auto}
.md code{font-family:ui-monospace,Consolas,monospace;font-size:.9em}
.md img{max-width:100%;border-radius:10px}
.md table{border-collapse:collapse;width:100%}
.md th,.md td{border-bottom:1px solid var(--border);padding:.5rem;text-align:left}
.md blockquote{border-left:3px solid var(--accent2);padding-left:1rem;margin:1rem 0}
.cta-box{margin-top:2.5rem;padding:1.4rem;border:1px solid var(--border);border-radius:12px;background:var(--card);text-align:center}
.cta-box a.btn{display:inline-block;margin-top:.6rem;background:linear-gradient(135deg,#64b5f6,#a78bfa);color:#04040c;padding:.6rem 1.4rem;border-radius:9px;font-weight:700;text-decoration:none}
footer{text-align:center;padding:2rem 1rem;border-top:1px solid var(--border);color:var(--text3);font-size:.85rem}
footer a{color:var(--text2)}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
"""

NAV = [("/#features", "Features"), ("/ai-models/", "AI Models"), ("/requirements/", "Requirements"),
       ("/faq/", "FAQ"), ("/blog/", "Blog")]

generated = []  # URL paths for the sitemap, e.g. "blog/"


def page(path, title, desc, body, schema=None, og_type="website", head_extra="", lastmod=None):
    """Write <path>/index.html and register it for the sitemap."""
    url = f"{SITE}/{path}/"
    nav = "".join(f'<a href="{h}">{t}</a>' for h, t in NAV)
    ld = "".join(
        '<script type="application/ld+json">' + json.dumps(s, ensure_ascii=False) + "</script>"
        for s in (schema or [])
    )
    doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{E(title)}</title>
<meta name="description" content="{E(desc)}">
<link rel="canonical" href="{url}">
<link rel="icon" href="/favicon.ico">
<meta name="theme-color" content="#04040c">
<meta property="og:title" content="{E(title)}">
<meta property="og:description" content="{E(desc)}">
<meta property="og:type" content="{og_type}">
<meta property="og:url" content="{url}">
<meta property="og:site_name" content="YUNA">
<meta property="og:image" content="{OG_IMAGE}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{E(title)}">
<meta name="twitter:description" content="{E(desc)}">
<meta name="twitter:image" content="{OG_IMAGE}">
<link rel="stylesheet" href="/assets/pages.css">
{head_extra}
{ld}
</head>
<body>
<nav><a class="logo" href="/">YUNA</a>{nav}<a class="cta" href="/#pricing">Get YUNA</a></nav>
<main class="wrap">
{body}
<div class="cta-box"><strong>YUNA: local AI companion with a Live2D face</strong><br>
<span class="meta">Runs offline on Windows. Pay once, from $10.</span><br>
<a class="btn" href="/#pricing">See pricing</a></div>
</main>
<footer><a href="/">Home</a> &middot; <a href="/blog/">Blog</a> &middot; <a href="/faq/">FAQ</a> &middot;
<a href="https://discord.gg/ARg6yujhdc" rel="noopener">Discord</a> &middot;
<a href="https://ko-fi.com/code7" rel="noopener">Support</a><br>&copy; 2026 YUNA</footer>
</body>
</html>
"""
    out = ROOT / path / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(doc, encoding="utf-8")
    generated.append((f"{path}/", lastmod or TODAY))
    print("  wrote", out.relative_to(ROOT))


def app_schema(extra=None):
    s = {
        "@context": "https://schema.org",
        "@type": "SoftwareApplication",
        "name": "YUNA",
        "applicationCategory": "MultimediaApplication",
        "operatingSystem": "Windows 10, Windows 11",
        "description": "Local AI companion with voice conversation and a Live2D animated face. "
                       "Runs offline, no subscription.",
        "url": SITE + "/",
        "image": OG_IMAGE,
        "offers": {"@type": "AggregateOffer", "priceCurrency": "USD", "lowPrice": "10", "highPrice": "15"},
    }
    if extra:
        s.update(extra)
    return s


# --------------------------------------------------------------------------- FAQ
FAQS = [
    ("Does YUNA need an internet connection?",
     "Only on first launch to download the AI model. After that it's fully offline. No cloud calls, no telemetry, nothing leaves your machine."),
    ("Can I use my own OpenAI or Claude API key?",
     "Yes. YUNA supports OpenAI, Anthropic, DeepSeek, Google Gemini, Groq, and more. Enter your API key in settings and use any model you have access to."),
    ("Does it run without a GPU?",
     "Yes. A GPU is optional. YUNA runs on CPU-only machines; an i5 with 8 GB RAM is enough. A GPU makes larger models faster, but it's not required to get started."),
    ("Can I change Yuna's personality?",
     "Yes, completely. Edit the system prompt directly from the settings panel. Name it, set the tone, define how she responds. You can also create entirely separate characters."),
    ("What's the refund policy?",
     "Due to the digital nature of the product, we offer support-first resolution. If YUNA doesn't work on your machine and we're unable to fix the issue, you may request a refund within 7 days of purchase, minus any applicable transfer fees or taxes."),
    ("Does it work on Mac or Linux?",
     "Currently Windows 10 and 11 only. Mac and Linux support are planned for a future release. Existing license holders will get access at no extra cost."),
    ("How do I transfer my license to a new PC?",
     "Contact us through Discord or email with your license key and proof of purchase. We'll deactivate the old device and reactivate on your new machine, free of charge."),
]


def build_faq():
    items = "".join(f'<div class="card"><h2>{E(q)}</h2><p>{E(a)}</p></div>' for q, a in FAQS)
    schema = [{
        "@context": "https://schema.org", "@type": "FAQPage",
        "mainEntity": [{"@type": "Question", "name": q,
                        "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in FAQS],
    }]
    page("faq", "YUNA FAQ: Offline Use, GPU, Pricing, Refunds & Licenses",
         "Answers about YUNA, the local AI companion: offline use, GPU requirements, API keys, personalities, refunds and license transfers.",
         f'<h1>YUNA frequently asked questions</h1><p class="lead">Quick answers about running YUNA, licenses and support.</p>{items}',
         schema)


# --------------------------------------------------------------------------- AI models
def build_models():
    body = """<h1>Use any AI model with YUNA: local or via API</h1>
<p class="lead">YUNA is a voice AI companion with a Live2D face. The "brain" is up to you: run a model fully on your PC with Ollama, or connect your own API key.</p>
<h2>Run locally with Ollama</h2>
<p>Any Ollama model works out of the box. If it runs on Ollama, it runs in YUNA, with no configuration. Whatever you have pulled (Qwen, DeepSeek-R1, Llama, Gemma, Mistral and others) appears automatically. Nothing leaves your machine and no API key is needed.</p>
<h2>Connect a cloud provider with your own API key</h2>
<ul>
<li><strong>OpenAI</strong>: use any GPT model your key can access.</li>
<li><strong>Anthropic (Claude)</strong>: use any Claude model your key can access.</li>
<li><strong>Google Gemini</strong>: use any Gemini model your key can access.</li>
<li><strong>DeepSeek</strong>: reasoning and chat models.</li>
<li><strong>Groq</strong>: fast hosted open models such as Llama and Mixtral.</li>
</ul>
<p>Enter the key in settings, pick the model you like and switch whenever you want.</p>
<h2>Local or cloud: which should you pick?</h2>
<table><tr><th></th><th>Local (Ollama)</th><th>Cloud (API key)</th></tr>
<tr><td>Privacy</td><td>Everything stays on your PC</td><td>Messages go to the provider</td></tr>
<tr><td>Internet</td><td>Only for the first model download</td><td>Required</td></tr>
<tr><td>Cost</td><td>Free after you buy YUNA</td><td>Provider usage fees</td></tr>
<tr><td>Speed</td><td>Depends on your hardware</td><td>Fast on any PC</td></tr></table>
<p>See the <a href="/requirements/">system requirements</a> or the <a href="/faq/">FAQ</a>.</p>"""
    page("ai-models", "AI Models for YUNA: Ollama, OpenAI, Claude, Gemini, DeepSeek, Groq",
         "Run YUNA with local Ollama models or connect your own OpenAI, Claude, Gemini, DeepSeek or Groq API key. Fully offline option, no subscription.",
         body)


# --------------------------------------------------------------------------- Requirements
def build_requirements():
    body = """<h1>YUNA system requirements: no GPU needed</h1>
<p class="lead">YUNA runs on modest Windows hardware. A graphics card is optional.</p>
<h2>Minimum</h2>
<ul><li><strong>CPU:</strong> Intel Core i5 6th gen or AMD Ryzen 5 1600 / FX-8350</li>
<li><strong>RAM:</strong> 8 GB (16 GB recommended)</li>
<li><strong>Storage:</strong> 2-8 GB free, depending on the model</li>
<li><strong>GPU:</strong> not required</li>
<li><strong>OS:</strong> Windows 10 or Windows 11</li></ul>
<h2>Recommended</h2>
<p>Core i7 / Ryzen 7, 16 GB RAM and a dedicated CUDA GPU. Larger models such as Llama 3.1 8B and Gemma 2 9B run noticeably faster.</p>
<h2>Internet</h2>
<p>Needed only on first launch to download the model. After that YUNA works fully offline, with no cloud and no telemetry.</p>
<h2>Mac and Linux</h2>
<p>Not yet. They are planned, and existing license holders will get access at no extra cost. More answers in the <a href="/faq/">FAQ</a>.</p>"""
    page("requirements", "YUNA System Requirements: Windows 10/11, 8 GB RAM, No GPU Needed",
         "YUNA runs on an i5 or Ryzen 5 with 8 GB RAM, with no GPU required. Windows 10 and 11. Offline after the first model download.",
         body)


# --------------------------------------------------------------------------- Reviews
def pick(d, *keys, default=""):
    for k in keys:
        if d.get(k) not in (None, ""):
            return d[k]
    return default


def build_reviews():
    f = ROOT / "reviews.json"
    if not f.exists():
        print("  (no reviews.json - skipped /reviews/)")
        return
    data = json.loads(f.read_text(encoding="utf-8"))
    data = data if isinstance(data, list) else data.get("reviews", [])
    revs = []
    for r in data:
        text = str(pick(r, "text", "review", "comment", "body")).strip()
        name = str(pick(r, "name", "author", "user")).strip()
        try:
            rating = max(1, min(5, int(float(pick(r, "rating", "stars", default=5)))))
        except ValueError:
            rating = 5
        if text and name:
            revs.append({"name": name, "rating": rating, "text": text, "date": str(pick(r, "date"))})
    if not revs:
        print("  (reviews.json has no usable entries - skipped /reviews/)")
        return
    cards = "".join(
        f'<div class="card"><div class="stars" aria-label="{x["rating"]} out of 5">'
        f'{"&#9733;" * x["rating"]}{"&#9734;" * (5 - x["rating"])}</div>'
        f'<p>{E(x["text"])}</p><p class="meta">{E(x["name"])}'
        f'{(" &middot; " + E(x["date"])) if x["date"] else ""} &middot; verified buyer</p></div>'
        for x in revs
    )
    avg = round(sum(x["rating"] for x in revs) / len(revs), 1)
    extra = {
        "review": [{
            "@type": "Review",
            "author": {"@type": "Person", "name": x["name"]},
            "reviewRating": {"@type": "Rating", "ratingValue": x["rating"], "bestRating": 5},
            "reviewBody": x["text"],
            **({"datePublished": x["date"]} if re.match(r"^\d{4}-\d{2}-\d{2}$", x["date"]) else {}),
        } for x in revs],
        "aggregateRating": {"@type": "AggregateRating", "ratingValue": avg,
                            "reviewCount": len(revs), "bestRating": 5},
    }
    page("reviews", "YUNA Reviews from Real Buyers",
         f"What buyers say about YUNA, the local AI companion. {len(revs)} verified reviews, average {avg}/5.",
         f'<h1>What buyers say about YUNA</h1><p class="lead">Reviews from people who bought a license.</p>{cards}',
         [app_schema(extra)])


# --------------------------------------------------------------------------- Blog
def build_blog():
    manifest = ROOT / "blogs" / "index.json"
    if not manifest.exists():
        print("  (blogs/index.json not found - skipped blog)")
        return
    data = json.loads(manifest.read_text(encoding="utf-8"))
    posts = data if isinstance(data, list) else data.get("posts", [])
    posts.sort(key=lambda p: p.get("date") or "", reverse=True)

    cards = []
    for p in posts:
        slug = p.get("slug")
        md_file = ROOT / "blogs" / f"{slug}.md"
        if not slug or not md_file.exists():
            print("  ! skipping missing post:", slug)
            continue
        text = md_file.read_text(encoding="utf-8")
        text = re.sub(r"\A\s*#\s+.*\n", "", text, count=1)  # we render the title as <h1>
        content = markdown.markdown(text, extensions=["fenced_code", "tables", "toc"])
        title = p.get("title") or slug
        excerpt = p.get("excerpt") or re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", content)).strip()[:155]
        d = str(p.get("date") or "")[:10]
        author = p.get("author") or "Code-7"
        tags = " ".join(f'<span class="meta">#{E(t)}</span>' for t in p.get("tags", []))
        body = (f'<p class="meta"><a href="/blog/">&larr; All posts</a></p><article><h1>{E(title)}</h1>'
                f'<p class="meta">{E(d)} &middot; {E(author)} {tags}</p><div class="md">{content}</div></article>')
        schema = [{
            "@context": "https://schema.org", "@type": "Article", "headline": title[:110],
            "description": excerpt, "image": OG_IMAGE,
            "author": {"@type": "Person", "name": author},
            "publisher": {"@type": "Organization", "name": "YUNA", "url": SITE + "/"},
            "mainEntityOfPage": f"{SITE}/blog/{slug}/",
            **({"datePublished": d, "dateModified": d} if re.match(r"^\d{4}-\d{2}-\d{2}$", d) else {}),
        }]
        page(f"blog/{slug}", f"{title} | YUNA Blog", excerpt[:155], body, schema,
             og_type="article", lastmod=d if re.match(r"^\d{4}-\d{2}-\d{2}$", d) else None)
        cards.append(f'<a class="card" href="/blog/{E(slug)}/"><h2>{E(title)}</h2><p>{E(excerpt)}</p>'
                     f'<p class="meta">{E(d)}</p></a>')

    # Old links like /blog/?p=slug are forwarded to the new static URLs.
    redirect = ('<script>var p=new URLSearchParams(location.search).get("p");'
                'if(p)location.replace("/blog/"+encodeURIComponent(p)+"/");</script>')
    page("blog", "YUNA Blog: Local AI Companion Guides, News & Updates",
         "Guides, release notes and tips for YUNA, the local AI companion with a Live2D face.",
         '<h1>News, guides &amp; updates</h1><p class="lead">Everything about your local AI companion.</p>'
         + ("".join(cards) or "<p>No posts yet.</p>"),
         head_extra=redirect)


# --------------------------------------------------------------------------- Sitemap / robots
def write_sitemap():
    rows = [("", TODAY)] + generated
    xml = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for path, mod in rows:
        xml.append(f"<url><loc>{SITE}/{path}</loc><lastmod>{mod}</lastmod></url>")
    xml.append("</urlset>")
    (ROOT / "sitemap.xml").write_text("\n".join(xml) + "\n", encoding="utf-8")
    print("  wrote sitemap.xml with", len(rows), "URLs")
    robots = ROOT / "robots.txt"
    if not robots.exists():
        robots.write_text(f"User-agent: *\nAllow: /\n\nSitemap: {SITE}/sitemap.xml\n", encoding="utf-8")
        print("  wrote robots.txt")
    else:
        print("  robots.txt exists - left unchanged (make sure it has: Sitemap: %s/sitemap.xml)" % SITE)


def main():
    print("Building YUNA site pages...")
    (ROOT / "assets").mkdir(exist_ok=True)
    (ROOT / "assets" / "pages.css").write_text(CSS, encoding="utf-8")
    build_faq()
    build_models()
    build_requirements()
    build_reviews()
    build_blog()
    write_sitemap()
    print("Done. Commit and push everything, then submit sitemap.xml in Search Console.")


if __name__ == "__main__":
    main()
