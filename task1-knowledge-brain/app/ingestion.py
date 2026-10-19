import asyncio
import hashlib
import os
import time
from urllib.parse import urlparse
import xml.etree.ElementTree as ET

import httpx

from .config import settings
from .parser import parse_article, split_chunks
from .store import KnowledgeStore
from .vectors import Embedder

USER_AGENT = "BusinessLabsKnowledgeBrain/1.0 (+polite documentation indexing)"


async def run_ingestion(store: KnowledgeStore, embedder: Embedder, sitemap_url: str,
                       max_pages: int | None = None) -> dict[str, object]:
    parsed_sitemap = urlparse(sitemap_url)
    if parsed_sitemap.scheme != "https" or parsed_sitemap.hostname != "support.brilliantdirectories.com":
        raise ValueError("Only the configured Brilliant Directories support host is allowed for ingestion.")
    timeout = httpx.Timeout(30.0)
    limits = httpx.Limits(max_connections=settings.max_concurrency)
    async with httpx.AsyncClient(timeout=timeout, limits=limits, headers={"User-Agent": USER_AGENT}, follow_redirects=True) as client:
        response = await _get_with_retries(client, sitemap_url)
        root = ET.fromstring(response.text)
        url_entries = _parse_sitemap(root)
        if max_pages is not None:
            url_entries = url_entries[:max_pages]
        sitemap_urls = {url for url, _ in url_entries}
        semaphore = asyncio.Semaphore(max(1, settings.max_concurrency))
        counts = {"added": 0, "updated": 0, "unchanged": 0, "failed": 0}

        async def process(url: str, lastmod: str | None) -> None:
            async with semaphore:
                current = store.page_record(url)
                if current and current["active"] and current["status"] == "success" and lastmod and current["lastmod"] == lastmod:
                    counts["unchanged"] += 1
                    return
                previous_hash = current["content_hash"] if current else None
                document_id = hashlib.sha256(url.encode()).hexdigest()[:20]
                try:
                    page = await _get_with_retries(client, url)
                    article = parse_article(page.text, url)
                    if previous_hash == article.content_hash and current and current["active"]:
                        store.save_page_state(url, document_id, lastmod, "success", article.content_hash)
                        counts["unchanged"] += 1
                        return
                    chunks = []
                    for section in article.sections:
                        for chunk_index, text in enumerate(split_chunks(str(section["text"]))):
                            chunk_id = hashlib.sha256(
                                f"{article.document_id}:{section['section_index']}:{chunk_index}:{text}".encode()
                            ).hexdigest()[:24]
                            related_images = [image for image in article.image_records
                                              if image["context"] and image["context"] in str(section["text"])]
                            chunks.append({
                                "chunk_id": chunk_id,
                                "section": str(section["section"]),
                                "text": text,
                                "images": related_images,
                                "embedding": embedder.encode(f"{article.title}\n{section['section']}\n{text}"),
                            })
                    store.replace_article(article, chunks)
                    store.save_page_state(url, article.document_id, lastmod, "success", article.content_hash)
                    counts["added" if not current or not current["content_hash"] else "updated"] += 1
                except Exception as error:
                    store.save_page_state(url, document_id, lastmod, "failed", error=str(error)[:500])
                    counts["failed"] += 1
                if settings.request_delay_seconds > 0:
                    await asyncio.sleep(settings.request_delay_seconds)

        await asyncio.gather(*(process(url, lastmod) for url, lastmod in url_entries))
        removed = store.deactivate_missing_pages(sitemap_urls) if max_pages is None else 0
        return {"sitemap_url": sitemap_url, "discovered": len(url_entries), "removed": removed, **counts}


async def _get_with_retries(client: httpx.AsyncClient, url: str) -> httpx.Response:
    last_error: Exception | None = None
    for attempt in range(4):
        try:
            response = await client.get(url)
            if response.status_code < 500 and response.status_code not in {408, 429}:
                response.raise_for_status()
                return response
            last_error = httpx.HTTPStatusError("Temporary HTTP failure", request=response.request, response=response)
        except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError) as error:
            last_error = error
            if isinstance(error, httpx.HTTPStatusError) and error.response.status_code < 500 and error.response.status_code not in {408, 429}:
                raise
        if attempt < 3:
            await asyncio.sleep(0.5 * (2 ** attempt))
    assert last_error is not None
    raise last_error


def _parse_sitemap(root: ET.Element) -> list[tuple[str, str | None]]:
    namespace = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    entries: dict[str, str | None] = {}
    for item in root.findall("sm:url", namespace):
        loc = item.findtext("sm:loc", namespaces=namespace)
        lastmod = item.findtext("sm:lastmod", namespaces=namespace)
        if not loc:
            continue
        parsed = urlparse(loc.strip())
        if parsed.scheme == "https" and parsed.hostname == "support.brilliantdirectories.com":
            entries[loc.strip()] = lastmod
    return sorted(entries.items())