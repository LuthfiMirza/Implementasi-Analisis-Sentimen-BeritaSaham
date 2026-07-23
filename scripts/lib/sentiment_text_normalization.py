from __future__ import annotations

import hashlib
import html
import re
import unicodedata
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "utm_id",
    "gclid", "fbclid", "mc_cid", "mc_eid", "igshid", "ref", "ref_src"
}


def normalize_text(value: object) -> str:
    text = "" if value is None else str(value)
    text = html.unescape(text)
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.lower()
    text = re.sub(r"[\t\f\v ]+", " ", text)
    text = re.sub(r" *\n+ *", " ", text)
    text = re.sub(r"[“”„‟]", '"', text)
    text = re.sub(r"[‘’‚‛]", "'", text)
    text = re.sub(r"[–—−]", "-", text)
    text = re.sub(r"(?<!\d)\s*([,;:!?])\s*(?!\d)", r"\1 ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_url(value: object) -> str:
    raw = "" if value is None else unicodedata.normalize("NFKC", html.unescape(str(value))).strip()
    if not raw:
        return ""
    parsed = urlsplit(raw)
    query = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True) if k not in TRACKING_PARAMS]
    netloc = parsed.netloc.lower()
    path = re.sub(r"/+$", "", parsed.path)
    return urlunsplit((parsed.scheme.lower(), netloc, path, urlencode(query, doseq=True), ""))


def build_combined_text(row: dict, rule: str = "target_entity + title + summary + content_snippet") -> str:
    parts = [
        row.get("target_entity"),
        row.get("title"),
        row.get("summary"),
        row.get("content_snippet"),
    ]
    return normalize_text(" ".join(str(part) for part in parts if part))


def sha256_text(value: object) -> str:
    return hashlib.sha256(("" if value is None else str(value)).encode("utf-8")).hexdigest()


def normalized_fields(row: dict) -> dict:
    normalized_title = normalize_text(row.get("title"))
    normalized_summary = normalize_text(row.get("summary"))
    normalized_content = normalize_text(row.get("content_snippet"))
    normalized_full = normalize_text(row.get("full_text") or "")
    combined = build_combined_text(row)
    url = normalize_url(row.get("url") or row.get("source_url"))
    return {
        "normalized_title": normalized_title,
        "normalized_summary": normalized_summary,
        "normalized_content_snippet": normalized_content,
        "normalized_full_text": normalized_full,
        "normalized_combined_text": combined,
        "exact_text_sha256": sha256_text(combined),
        "normalized_title_sha256": sha256_text(normalized_title),
        "normalized_url": url,
        "normalized_url_hash": sha256_text(url) if url else "",
    }


PLACEHOLDER_VALUES = {"", "n/a", "na", "none", "null", "unknown", "-", "--"}
EMPTY_TEXT_SHA256 = hashlib.sha256(b"").hexdigest()


def is_usable_grouping_value(value: str | None) -> bool:
    if value is None:
        return False
    text = normalize_text(value)
    if text in PLACEHOLDER_VALUES:
        return False
    if text == EMPTY_TEXT_SHA256 or EMPTY_TEXT_SHA256.startswith(text):
        return False
    return len(text) >= 3
