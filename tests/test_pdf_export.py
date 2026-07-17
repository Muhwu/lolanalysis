import base64

import httpx
import pytest

from server import pdf_export

# smallest possible valid PNG (1x1, transparent)
TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "+A8AAQUBAScY42YAAAAASUVORK5CYII=")


@pytest.fixture(autouse=True)
def fake_icon_fetch(monkeypatch):
    """No network in tests — every icon "fetch" returns a tiny valid PNG."""
    def fake_get(url, timeout=5.0):
        return httpx.Response(200, content=TINY_PNG, request=httpx.Request("GET", url))
    monkeypatch.setattr(pdf_export.httpx, "get", fake_get)


def test_inline_markup_escapes_then_applies_bold_italic_code():
    assert pdf_export._inline_markup("**bold** and *italic* and `code`") == \
        "<b>bold</b> and <i>italic</i> and <font face=\"Courier\">code</font>"
    # user text with markup-like characters must be escaped, not injected
    assert pdf_export._inline_markup("<script>&") == "&lt;script&gt;&amp;"


def test_markdown_flowables_headings_lists_paragraphs():
    styles = pdf_export._styles()
    text = "# Title\n\nSome text.\n\n- one\n- two\n\nMore text."
    flowables = pdf_export._markdown_flowables(text, styles)
    # heading, paragraph, list, paragraph
    assert len(flowables) == 4
    assert flowables[0].style.name == "GuideH1"
    assert flowables[2].__class__.__name__ == "ListFlowable"


def test_markdown_flowables_blank_text_shows_placeholder():
    styles = pdf_export._styles()
    flowables = pdf_export._markdown_flowables("", styles)
    assert len(flowables) == 1
    assert "No notes" in flowables[0].text


ITEM_BUILD = {
    "core": ["Riftmaker", "Nashor's Tooth"],
    "situational": [{"label": "vs heavy AP", "items": ["Zhonya's Hourglass"]}],
}


def _item_aware_get(url, timeout=5.0):
    request = httpx.Request("GET", url)
    if url == pdf_export.DDRAGON_VERSIONS_URL:
        return httpx.Response(200, json=["14.20.1"], request=request)
    if url == pdf_export.ITEM_DATA_URL.format(version="14.20.1"):
        data = {"data": {
            "3153": {"name": "Riftmaker", "image": {"full": "3153.png"}},
            "3115": {"name": "Nashor's Tooth", "image": {"full": "3115.png"}},
            "3157": {"name": "Zhonya's Hourglass", "image": {"full": "3157.png"}},
        }}
        return httpx.Response(200, json=data, request=request)
    return httpx.Response(200, content=TINY_PNG, request=request)


def test_build_champion_guide_pdf_returns_valid_pdf_bytes(monkeypatch):
    monkeypatch.setattr(pdf_export.httpx, "get", _item_aware_get)
    guide = {
        "Darius": {
            "notes": "# Lane\n\nPlay **safe**.",
            "patch_version": "14.2",
            "runes": [{
                "label": "Standard",
                "primary_tree": "Precision", "keystone": "Conqueror",
                "primary_runes": ["Triumph", "Legend: Alacrity", "Last Stand"],
                "secondary_tree": "Resolve", "secondary_runes": ["Bone Plating", "Overgrowth"],
                "shards": ["Adaptive Force", "Armor", "Health"],
            }],
        },
        "Wukong": {"notes": "", "patch_version": "", "runes": []},
    }
    pdf_bytes = pdf_export.build_champion_guide_pdf("Gwen", "General notes.", ITEM_BUILD, guide)
    assert pdf_bytes.startswith(b"%PDF")
    assert len(pdf_bytes) > 500


def test_build_champion_guide_pdf_empty_everything_does_not_crash():
    pdf_bytes = pdf_export.build_champion_guide_pdf("Gwen", "", {"core": [], "situational": []}, {})
    assert pdf_bytes.startswith(b"%PDF")


def test_build_champion_guide_pdf_survives_icon_fetch_failure(monkeypatch):
    def failing_get(url, timeout=5.0):
        raise httpx.ConnectError("no network")
    monkeypatch.setattr(pdf_export.httpx, "get", failing_get)
    guide = {"Darius": {
        "notes": "notes", "patch_version": "14.2",
        "runes": [{
            "label": "", "primary_tree": "Precision", "keystone": "Conqueror",
            "primary_runes": ["Triumph", "Legend: Alacrity", "Last Stand"],
            "secondary_tree": "Resolve", "secondary_runes": ["Bone Plating", "Overgrowth"],
            "shards": ["Adaptive Force", "Armor", "Health"],
        }],
    }}
    pdf_bytes = pdf_export.build_champion_guide_pdf("Gwen", "", ITEM_BUILD, guide)
    assert pdf_bytes.startswith(b"%PDF")


def test_icon_fetcher_caches_by_url():
    calls = []

    def counting_get(url, timeout=5.0):
        calls.append(url)
        return httpx.Response(200, content=TINY_PNG, request=httpx.Request("GET", url))

    import server.pdf_export as mod
    fetcher = mod._IconFetcher()
    orig = mod.httpx.get
    mod.httpx.get = counting_get
    try:
        fetcher.rune_or_tree("icon.png")
        fetcher.rune_or_tree("icon.png")
        fetcher.rune_or_tree("other.png")
    finally:
        mod.httpx.get = orig
    assert len(calls) == 2  # repeated icon.png request was cached
