"""SEO infrastructure: XML sitemap and robots.txt."""
from datetime import datetime
from flask import Blueprint, Response, url_for, current_app

from app.models import Treatment, BlogPost

seo_bp = Blueprint("seo", __name__)

STATIC_PAGES = [
    ("main.home", 1.0, "daily"),
    ("main.about", 0.8, "monthly"),
    ("main.treatments", 0.9, "weekly"),
    ("booking.book_appointment", 0.9, "weekly"),
    ("main.timings", 0.6, "monthly"),
    ("main.contact", 0.7, "monthly"),
    ("main.faq", 0.6, "monthly"),
    ("main.blog_list", 0.7, "weekly"),
    ("main.privacy", 0.3, "yearly"),
    ("main.terms", 0.3, "yearly"),
]


@seo_bp.route("/sitemap.xml")
def sitemap():
    urls = []
    today = datetime.utcnow().strftime("%Y-%m-%d")

    for endpoint, priority, freq in STATIC_PAGES:
        urls.append({
            "loc": url_for(endpoint, _external=True),
            "lastmod": today, "priority": priority, "changefreq": freq,
        })

    for t in Treatment.query.filter_by(is_active=True).all():
        urls.append({
            "loc": url_for("main.treatment_detail", slug=t.slug, _external=True),
            "lastmod": today, "priority": 0.8, "changefreq": "monthly",
        })

    for post in BlogPost.query.filter_by(is_published=True).all():
        lastmod = (post.updated_at or post.created_at).strftime("%Y-%m-%d")
        urls.append({
            "loc": url_for("main.blog_post", slug=post.slug, _external=True),
            "lastmod": lastmod, "priority": 0.6, "changefreq": "monthly",
        })

    xml_items = "\n".join(
        f"""  <url>
    <loc>{u['loc']}</loc>
    <lastmod>{u['lastmod']}</lastmod>
    <changefreq>{u['changefreq']}</changefreq>
    <priority>{u['priority']}</priority>
  </url>""" for u in urls
    )
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{xml_items}
</urlset>"""
    return Response(xml, mimetype="application/xml")


@seo_bp.route("/robots.txt")
def robots():
    site_url = current_app.config.get("SITE_URL", "")
    content = f"""User-agent: *
Allow: /
Disallow: /admin
Disallow: /api/

Sitemap: {site_url}/sitemap.xml
"""
    return Response(content, mimetype="text/plain")
