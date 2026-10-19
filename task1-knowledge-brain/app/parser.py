from dataclasses import dataclass
import hashlib
import json
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag


@dataclass
class ParsedArticle:
    document_id: str
    title: str
    url: str
    content_hash: str
    sections: list[dict[str, object]]
    image_records: list[dict[str, str]]


def parse_article(html: str, url: str) -> ParsedArticle:
    soup = BeautifulSoup(html, "lxml")
    for element in soup.select("script, style, nav, footer, header, aside, noscript, form"):
        element.decompose()

    main = soup.select_one("main, article, [role='main'], .article-body, .solution-content") or soup.body or soup
    title_tag = soup.select_one("h1") or soup.title
    title = title_tag.get_text(" ", strip=True) if title_tag else url.rstrip("/").split("/")[-1]
    article_id = _article_id(url)
    sections: list[dict[str, object]] = []
    image_records: list[dict[str, str]] = []
    current_heading = title
    current_parts: list[str] = []
    section_index = 0

    def save_section() -> None:
        nonlocal section_index, current_parts
        text = "\n".join(part for part in current_parts if part).strip()
        if text:
            sections.append({"section": current_heading, "text": text, "section_index": section_index})
            section_index += 1
        current_parts = []

    for node in main.find_all(["h2", "h3", "h4", "p", "li", "tr", "img"], recursive=True):
        if not isinstance(node, Tag):
            continue
        if node.name in {"h2", "h3", "h4"}:
            save_section()
            current_heading = node.get_text(" ", strip=True) or title
        elif node.name == "img":
            src = node.get("src") or node.get("data-src") or node.get("data-original")
            if not src:
                continue
            image_url = urljoin(url, str(src))
            if urlparse(image_url).scheme not in {"http", "https"}:
                continue
            alt_text = str(node.get("alt", "")).strip()
            nearby_text = node.parent.get_text(" ", strip=True)[:500] if node.parent else ""
            image_records.append({"url": image_url, "alt": alt_text, "context": nearby_text})
            current_parts.append(f"[Image: {alt_text or 'screenshot'}; context: {nearby_text}]".strip())
        else:
            text = node.get_text(" ", strip=True)
            if text:
                current_parts.append(text)
    save_section()

    if not sections:
        text = main.get_text("\n", strip=True)
        if text:
            sections.append({"section": title, "text": text, "section_index": 0})
    content_hash = hashlib.sha256(
        (
            title
            + "\n"
            + "\n".join(str(section["text"]) for section in sections)
            + "\n"
            + json.dumps(image_records, sort_keys=True, ensure_ascii=True)
        ).encode("utf-8")
    ).hexdigest()
    return ParsedArticle(article_id, title, url, content_hash, sections, image_records)


def split_chunks(text: str, max_chars: int = 1400, overlap: int = 180) -> list[str]:
    if len(text) <= max_chars:
        return [text] if text.strip() else []
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + max_chars)
        if end < len(text):
            boundary = max(text.rfind("\n", start, end), text.rfind(". ", start, end))
            if boundary > start + max_chars // 2:
                end = boundary + 1
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end == len(text):
            break
        start = max(start + 1, end - overlap)
    return chunks


def _article_id(url: str) -> str:
    path = urlparse(url).path.rstrip("/")
    if path:
        return path.split("/")[-1]
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]