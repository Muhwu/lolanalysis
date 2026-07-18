"""Renders a champion's Matchup guide (general notes + every matchup: patch,
rune pages, Markdown notes) as a printable PDF. Rune/tree/shard icons are
fetched live from ddragon/CommunityDragon at export time (same CDN URLs the
frontend hotlinks in guide.js) and embedded — unlike the JSON export, this
needs network access and is slower. Uses reportlab's core Helvetica fonts
(WinAnsi/Latin-1 only) — non-Latin characters in notes won't render
correctly; embedding a Unicode font was judged out of scope for a v1.
"""
import html
import io
import re

import httpx
from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable, Image, ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

from . import rune_data

RUNE_ICON_URL = "https://ddragon.leagueoflegends.com/cdn/img/{}"
SHARD_ICON_URL = ("https://raw.communitydragon.org/latest/plugins/rcp-be-lol-game-data"
                   "/global/default/v1/perk-images/statmods/{}")
DDRAGON_VERSIONS_URL = "https://ddragon.leagueoflegends.com/api/versions.json"
ITEM_DATA_URL = "https://ddragon.leagueoflegends.com/cdn/{version}/data/en_US/item.json"
ITEM_ICON_URL = "https://ddragon.leagueoflegends.com/cdn/{version}/img/item/{icon}"
ICON_PT = 16  # rune/shard/item icon size in the PDF, in points


def _styles():
    base = getSampleStyleSheet()
    return {
        "Title": base["Title"],
        "H1": ParagraphStyle("GuideH1", parent=base["Heading1"], spaceBefore=14, spaceAfter=6),
        "H2": ParagraphStyle("GuideH2", parent=base["Heading2"], spaceBefore=10, spaceAfter=4),
        "H3": ParagraphStyle("GuideH3", parent=base["Heading3"], spaceBefore=8, spaceAfter=3),
        "Body": ParagraphStyle("GuideBody", parent=base["BodyText"], spaceAfter=6, leading=14),
        "Caption": ParagraphStyle("GuideCaption", parent=base["BodyText"], fontSize=8,
                                   textColor=colors.grey, spaceAfter=10),
        "Meta": ParagraphStyle("GuideMeta", parent=base["BodyText"], fontSize=9,
                                textColor=colors.grey, spaceAfter=4),
    }


def _inline_markup(text):
    """Escapes text, then re-applies a small subset of Markdown as reportlab's
    own mini-markup (bold/italic/code) — Paragraph text is itself a
    restricted XML dialect, so raw user text must be escaped first or it
    could break parsing (or inject arbitrary markup)."""
    text = html.escape(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<i>\1</i>", text)
    text = re.sub(r"`(.+?)`", r'<font face="Courier">\1</font>', text)
    return text


def _markdown_flowables(text, styles):
    """A small, deliberately limited Markdown->flowables converter: headings,
    paragraphs, bullet lists, **bold**/*italic*/`code`. Coaching notes in
    this app are short freeform text, not full documents — no tables,
    nested lists, links, or code blocks."""
    flowables = []
    para_buf, list_buf = [], []

    def flush_para():
        if para_buf:
            flowables.append(Paragraph(_inline_markup(" ".join(para_buf)), styles["Body"]))
            para_buf.clear()

    def flush_list():
        if list_buf:
            flowables.append(ListFlowable(
                [ListItem(Paragraph(_inline_markup(t), styles["Body"])) for t in list_buf],
                bulletType="bullet", leftIndent=14))
            list_buf.clear()

    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        if not line:
            flush_para()
            flush_list()
            continue
        heading = re.match(r"^(#{1,3})\s+(.*)", line)
        if heading:
            flush_para()
            flush_list()
            flowables.append(Paragraph(_inline_markup(heading.group(2)),
                                        styles[f"H{len(heading.group(1))}"]))
            continue
        bullet = re.match(r"^[-*]\s+(.*)", line)
        if bullet:
            flush_para()
            list_buf.append(bullet.group(1))
            continue
        flush_list()
        para_buf.append(line)
    flush_para()
    flush_list()
    return flowables or [Paragraph("<i>No notes.</i>", styles["Body"])]


class _IconFetcher:
    """Fetches + caches rune/shard/item icon bytes for one export call (a
    matchup list commonly reuses the same keystone/shards across several
    pages, and item names repeat across core/situational sections)."""

    def __init__(self):
        self._cache = {}
        self._ddragon_version = None  # None = not yet fetched, False = fetch failed
        self._item_icon_by_name = None  # lazy: item name -> icon filename

    def _get(self, url):
        if url not in self._cache:
            try:
                resp = httpx.get(url, timeout=5.0)
                resp.raise_for_status()
                self._cache[url] = resp.content
            except httpx.HTTPError:
                self._cache[url] = None
        return self._cache[url]

    def rune_or_tree(self, icon_path):
        return self._get(RUNE_ICON_URL.format(icon_path)) if icon_path else None

    def shard(self, icon_path):
        return self._get(SHARD_ICON_URL.format(icon_path)) if icon_path else None

    def _ddragon_version_str(self):
        if self._ddragon_version is None:
            try:
                resp = httpx.get(DDRAGON_VERSIONS_URL, timeout=5.0)
                resp.raise_for_status()
                self._ddragon_version = resp.json()[0]
            except (httpx.HTTPError, ValueError, IndexError, KeyError):
                self._ddragon_version = False
        return self._ddragon_version or None

    def _item_icon_filename(self, name):
        if self._item_icon_by_name is None:
            self._item_icon_by_name = {}
            version = self._ddragon_version_str()
            if version:
                try:
                    resp = httpx.get(ITEM_DATA_URL.format(version=version), timeout=8.0)
                    resp.raise_for_status()
                    items = resp.json().get("data") or {}
                    self._item_icon_by_name = {
                        v["name"]: v["image"]["full"] for v in items.values()
                        if v.get("name") and v.get("image", {}).get("full")}
                except (httpx.HTTPError, ValueError, KeyError):
                    pass
        return self._item_icon_by_name.get(name)

    def item(self, name):
        version = self._ddragon_version_str()
        icon = self._item_icon_filename(name)
        return self._get(ITEM_ICON_URL.format(version=version, icon=icon)) if version and icon else None


def _icon_image(data):
    if not data:
        return None
    try:
        return Image(io.BytesIO(data), width=ICON_PT, height=ICON_PT)
    except Exception:
        return None


def _icon_row_table(imgs):
    if not imgs:
        return None
    table = Table([imgs], hAlign="LEFT")
    table.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return table


def _rune_page_flowables(page, icons, styles):
    imgs = []

    def add(icon_bytes):
        img = _icon_image(icon_bytes)
        if img:
            imgs.append(img)

    add(icons.rune_or_tree(rune_data.RUNE_ICON.get(page.get("keystone"))))
    for name in page.get("primary_runes") or []:
        add(icons.rune_or_tree(rune_data.RUNE_ICON.get(name)))
    add(icons.rune_or_tree(rune_data.TREE_ICON.get(page.get("secondary_tree"))))
    for name in page.get("secondary_runes") or []:
        add(icons.rune_or_tree(rune_data.RUNE_ICON.get(name)))
    for name in page.get("shards") or []:
        add(icons.shard(rune_data.SHARD_ICON.get(name)))

    flowables = []
    table = _icon_row_table(imgs)
    if table:
        flowables.append(table)

    primary = ", ".join(filter(None, [page.get("keystone"), *(page.get("primary_runes") or [])]))
    secondary = ", ".join(filter(None, [page.get("secondary_tree"), *(page.get("secondary_runes") or [])]))
    shards = ", ".join(filter(None, page.get("shards") or []))
    caption_bits = [b for b in (primary, secondary, shards and f"Shards: {shards}") if b]
    if page.get("label"):
        caption_bits.insert(0, f'"{page["label"]}"')
    flowables.append(Paragraph(_inline_markup(" — ".join(caption_bits)), styles["Caption"]))
    return flowables


def _item_row_flowables(items, icons, styles, heading):
    if not items:
        return []
    flowables = [Paragraph(_inline_markup(heading), styles["H3"])]
    imgs = [img for img in (_icon_image(icons.item(name)) for name in items) if img]
    table = _icon_row_table(imgs)
    if table:
        flowables.append(table)
    flowables.append(Paragraph(_inline_markup(", ".join(items)), styles["Caption"]))
    return flowables


def _item_build_flowables(item_build, icons, styles):
    core = (item_build or {}).get("core") or []
    situational = (item_build or {}).get("situational") or []
    if not core and not situational:
        return []
    flowables = [Paragraph("Item build", styles["H1"])]
    flowables.extend(_item_row_flowables(core, icons, styles, "Core build"))
    for section in situational:
        flowables.extend(_item_row_flowables(
            section.get("items") or [], icons, styles, section.get("label") or "Situational"))
    flowables.append(Spacer(1, 6))
    return flowables


def build_champion_guide_pdf(champion, general_notes, item_build, guide):
    """champion: display name string. general_notes: Markdown str.
    item_build: {core: [item name, ...], situational: [{label, items}, ...]}
    as returned by db.get_item_build. guide: {opp_champion: {notes,
    runes: [page, ...], patch_version}} as returned by db.get_matchup_notes.
    Matchups are ordered alphabetically — the "most-played first" ordering
    the UI uses depends on a separate stats query this module deliberately
    doesn't need. Item icons need the champion's build's item *names*
    resolved against the current patch's item data (fetched live, alongside
    the current ddragon version — both cached per export call in
    _IconFetcher) since, unlike rune icons, item icon paths are
    version-scoped."""
    styles = _styles()
    icons = _IconFetcher()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=LETTER, leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=18 * mm, bottomMargin=18 * mm, title=f"{champion} — Matchup Guide")
    story = [Paragraph(f"{html.escape(champion)} — Matchup Guide", styles["Title"]), Spacer(1, 4)]

    if general_notes and general_notes.strip():
        story.append(Paragraph("General notes", styles["H1"]))
        story.extend(_markdown_flowables(general_notes, styles))
        story.append(Spacer(1, 6))

    story.extend(_item_build_flowables(item_build, icons, styles))

    for opp_champion in sorted(guide):
        entry = guide[opp_champion]
        story.append(HRFlowable(width="100%", thickness=0.5, color=colors.lightgrey,
                                 spaceBefore=4, spaceAfter=8))
        story.append(Paragraph(f"vs {html.escape(opp_champion)}", styles["H2"]))
        if entry.get("patch_version"):
            story.append(Paragraph(f"Patch {html.escape(entry['patch_version'])}", styles["Meta"]))
        for page in entry.get("runes") or []:
            story.extend(_rune_page_flowables(page, icons, styles))
        if (entry.get("notes") or "").strip():
            story.extend(_markdown_flowables(entry["notes"], styles))
        else:
            story.append(Paragraph("<i>No notes.</i>", styles["Body"]))

    if len(story) == 2:  # just the title + spacer — nothing else was added
        story.append(Paragraph("No guide content recorded for this champion yet.", styles["Body"]))

    doc.build(story)
    return buf.getvalue()
