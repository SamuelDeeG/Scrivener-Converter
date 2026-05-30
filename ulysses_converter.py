"""
Ulysses Converter
-----------------
GUI application for converting Ulysses projects (.ulproj, .textpack, .md)
into either:
  1. A folder of RTF files (directory export)
  2. A ready-to-open Scrivener project (.scriv)

Font issues are fixed automatically on all output RTF files.

Requires: PyQt5
Install:  pip install PyQt5
"""

import os
import re
import sys
import uuid
import zipfile
import shutil
import plistlib
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QFileDialog, QTextEdit,
    QRadioButton, QButtonGroup, QGroupBox, QListWidget, QListWidgetItem,
    QProgressBar, QSizePolicy, QAbstractItemView, QFrame, QSplitter,
    QMessageBox, QTabWidget
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QMimeData, QSize
from PyQt5.QtGui import QDragEnterEvent, QDropEvent, QColor


# =============================================================================
# Styling
# =============================================================================

STYLE = """
QMainWindow, QWidget {
    background-color: #1e1e2e;
    color: #cdd6f4;
    font-family: 'Segoe UI', Arial, sans-serif;
    font-size: 13px;
}

QGroupBox {
    border: 1px solid #45475a;
    border-radius: 6px;
    margin-top: 10px;
    padding-top: 8px;
    font-weight: bold;
    color: #89b4fa;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
}

QPushButton {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 5px;
    padding: 6px 14px;
    min-width: 80px;
}
QPushButton:hover {
    background-color: #45475a;
    border-color: #89b4fa;
}
QPushButton:pressed {
    background-color: #585b70;
}
QPushButton#convertBtn {
    background-color: #89b4fa;
    color: #1e1e2e;
    font-weight: bold;
    padding: 8px 20px;
    font-size: 14px;
}
QPushButton#convertBtn:hover {
    background-color: #b4befe;
}
QPushButton#convertBtn:disabled {
    background-color: #45475a;
    color: #6c7086;
}

QLineEdit {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 4px;
    padding: 5px 8px;
}
QLineEdit:focus {
    border-color: #89b4fa;
}

QListWidget {
    background-color: #181825;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 4px;
}
QListWidget::item {
    padding: 4px 8px;
}
QListWidget::item:selected {
    background-color: #313244;
    color: #89b4fa;
}
QListWidget::item:hover {
    background-color: #262637;
}

QTextEdit {
    background-color: #11111b;
    color: #a6e3a1;
    border: 1px solid #45475a;
    border-radius: 4px;
    font-family: 'Consolas', 'Courier New', monospace;
    font-size: 12px;
}

QRadioButton {
    color: #cdd6f4;
    spacing: 6px;
}
QRadioButton::indicator {
    width: 14px;
    height: 14px;
    border-radius: 7px;
    border: 2px solid #45475a;
    background-color: #313244;
}
QRadioButton::indicator:checked {
    background-color: #89b4fa;
    border-color: #89b4fa;
}

QProgressBar {
    background-color: #313244;
    border: 1px solid #45475a;
    border-radius: 4px;
    text-align: center;
    color: #cdd6f4;
    height: 16px;
}
QProgressBar::chunk {
    background-color: #89b4fa;
    border-radius: 3px;
}

QLabel#dropLabel {
    color: #6c7086;
    border: 2px dashed #45475a;
    border-radius: 6px;
    padding: 14px;
    background-color: #181825;
}

QSplitter::handle {
    background-color: #45475a;
    width: 1px;
}

QScrollBar:vertical {
    background-color: #181825;
    width: 10px;
    border-radius: 5px;
}
QScrollBar::handle:vertical {
    background-color: #45475a;
    border-radius: 5px;
    min-height: 20px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

QTabWidget::pane {
    border: 1px solid #45475a;
    border-radius: 0 6px 6px 6px;
    padding: 8px;
    background-color: #1e1e2e;
}
QTabBar::tab {
    background-color: #313244;
    color: #cdd6f4;
    padding: 6px 18px;
    border: 1px solid #45475a;
    border-bottom: none;
    border-radius: 6px 6px 0 0;
    margin-right: 2px;
}
QTabBar::tab:selected {
    background-color: #1e1e2e;
    color: #89b4fa;
    border-bottom: 1px solid #1e1e2e;
}
QTabBar::tab:hover:!selected {
    background-color: #45475a;
}
"""


# =============================================================================
# Conversion logic (from main.py)
# =============================================================================

SKIP_GROUPS = {"Trash-ultrash"}

HEADING_SIZES = {
    "heading1": 36, "heading2": 32, "heading3": 28,
    "heading4": 26, "heading5": 24, "heading6": 24,
}
HEADING_TAGS = set(HEADING_SIZES.keys())


def sanitize_filename(name):
    safe = re.sub(r'[\\/*?:"<>|]', "", name)
    safe = safe.strip().strip(".")
    return safe or "Untitled"


def unique_path(folder, title, ext=".rtf"):
    base = sanitize_filename(title)
    path = os.path.join(folder, f"{base}{ext}")
    counter = 2
    while os.path.exists(path):
        path = os.path.join(folder, f"{base}_{counter}{ext}")
        counter += 1
    return path


def rtf_escape(text):
    out = []
    for ch in text:
        if ch == '\\':
            out.append('\\\\')
        elif ch == '{':
            out.append('\\{')
        elif ch == '}':
            out.append('\\}')
        elif ord(ch) > 127:
            out.append(f'\\u{ord(ch)}?')
        else:
            out.append(ch)
    return ''.join(out)


def wrap_rtf_directory(paragraphs_rtf):
    """RTF header for directory-export mode (matches original main.py style)."""
    return (
        r'{\rtf1\ansi\deff0'
        r'{\fonttbl{\f0\froman\fcharset0 Times New Roman;}}'
        r'{\colortbl;}'
        '\n'
        + paragraphs_rtf
        + '\n}'
    )


def wrap_rtf_scrivener(paragraphs_rtf):
    """RTF header matching Scrivener Windows native format (Georgia, fs32)."""
    return (
        r'{\rtf1\ansi\ansicpg1252\uc1\deff0' '\n'
        r'{\fonttbl{\f0\froman\fcharset0\fprq2 Georgia;}{\f1\froman\fcharset0\fprq2 Georgia;}}' '\n'
        r'{\colortbl;\red0\green0\blue0;\red255\green255\blue255;\red128\green128\blue128;}' '\n'
        r'\paperw12240\paperh15840\margl1800\margr1800\margt1440\margb1440\deftab1200\f0\fs32\cf0' '\n'
        + paragraphs_rtf
        + '\n}'
    )


def get_block_kind(p_elem):
    for child in p_elem:
        if child.tag == "tags":
            for subchild in child:
                if subchild.tag == "tag":
                    return subchild.get("kind", None)
        elif child.tag == "tag":
            return child.get("definition", None)
    return None


# ---------------------------------------------------------------------------
# RTF image embedding
# ---------------------------------------------------------------------------

def _jpeg_dimensions(data):
    """Return (w, h) from JPEG binary, or (None, None)."""
    i = 2
    while i + 4 < len(data):
        if data[i] != 0xFF:
            break
        marker = data[i + 1]
        length = int.from_bytes(data[i + 2:i + 4], 'big')
        if marker in (0xC0, 0xC1, 0xC2, 0xC3):
            h = int.from_bytes(data[i + 5:i + 7], 'big')
            w = int.from_bytes(data[i + 7:i + 9], 'big')
            return w, h
        i += 2 + length
    return None, None


def _png_dimensions(data):
    """Return (w, h) from PNG binary, or (None, None)."""
    if len(data) < 24 or data[:8] != b'\x89PNG\r\n\x1a\n':
        return None, None
    return (int.from_bytes(data[16:20], 'big'),
            int.from_bytes(data[20:24], 'big'))


def _image_to_rtf_pict(img_data, ext):
    """
    Encode image binary as an inline RTF \\shppict block (Scrivener Windows format).
    Returns the RTF string, or a text placeholder if the format isn't supported.
    """
    ext = ext.lower().lstrip('.')
    if ext in ('jpg', 'jpeg'):
        pict_type = r'\jpegblip'
        w, h = _jpeg_dimensions(img_data)
    elif ext == 'png':
        pict_type = r'\pngblip'
        w, h = _png_dimensions(img_data)
    else:
        return r'{\i [image]}'

    # Convert pixel dimensions to twips at 96 dpi (1 twip = 1/1440 inch)
    dpi = 96
    if w and h:
        w_px, h_px = w, h
        w_twips = int(w / dpi * 1440)
        h_twips = int(h / dpi * 1440)
    else:
        w_px, h_px = 300, 225
        w_twips, h_twips = 4320, 3240

    # Cap at 5760 twips (4 inches) wide, scale height proportionally
    if w_twips > 5760:
        ratio = 5760 / w_twips
        w_twips = 5760
        h_twips = int(h_twips * ratio)

    # Break hex into 76-char lines (standard RTF hex encoding)
    raw_hex = img_data.hex()
    hex_lines = '\n'.join(raw_hex[i:i+76] for i in range(0, len(raw_hex), 76))

    # Use {\*\shppict{...}} wrapper — matches Scrivener Windows native format exactly.
    # {\*\nisusfilename UUID} is the image identifier Scrivener embeds; the \* makes
    # it an optional destination so other RTF readers skip it safely.
    img_uuid = str(uuid.uuid4()).upper()
    return (
        '{\\*\\shppict'
        f'{{\\pict'
        f'{{\\*\\nisusfilename {img_uuid}}}'
        f'\\picw{w_px}\\pich{h_px}'
        f'\\picwgoal{w_twips}\\pichgoal{h_twips}'
        f'{pict_type} {hex_lines}'
        '}}'
    )


def element_to_rtf(elem, images=None):
    """images: dict mapping Ulysses image identifier → (binary_data, ext)"""
    parts = []
    if elem.text:
        parts.append(rtf_escape(elem.text))
    for child in elem:
        if child.tag == "tag":
            pass
        elif child.tag == "element":
            kind = child.get("kind", "")
            inner = element_to_rtf(child, images)
            if kind == "strong":
                parts.append(f'{{\\b {inner}}}')
            elif kind == "emph":
                parts.append(f'{{\\i {inner}}}')
            elif kind == "delete":
                parts.append(f'{{\\strike {inner}}}')
            elif kind == "code":
                parts.append(f'{{\\f1 {inner}}}')
            elif kind == "image":
                # Look up the image identifier in the <attribute> child
                identifier = None
                for attr in child:
                    if attr.tag == "attribute" and attr.get("identifier") == "image":
                        identifier = (attr.text or "").strip()
                        break
                if identifier and images and identifier in images:
                    img_data, ext = images[identifier]
                    parts.append(_image_to_rtf_pict(img_data, ext))
                else:
                    parts.append(r'{\i [image]}')
            elif kind in ("inlineComment", "annotation"):
                pass
            else:
                parts.append(inner)
        elif child.tag == "link":
            parts.append(element_to_rtf(child, images))
        elif child.tag == "image":
            # Top-level <image> tag (older Ulysses format)
            identifier = None
            for attr in child:
                if attr.tag == "attribute" and attr.get("identifier") == "image":
                    identifier = (attr.text or "").strip()
                    break
            if identifier and images and identifier in images:
                img_data, ext = images[identifier]
                parts.append(_image_to_rtf_pict(img_data, ext))
            else:
                parts.append(r'{\i [image]}')
        else:
            parts.append(element_to_rtf(child, images))
        if child.tail:
            parts.append(rtf_escape(child.tail))
    return "".join(parts)


_NON_TEXT_KINDS = {"image", "inlineComment", "annotation"}


def _has_image_element(p_elem):
    """Return True if this paragraph contains an image element."""
    for child in p_elem.iter():
        if child.tag in ("image",) or (child.tag == "element" and child.get("kind") == "image"):
            return True
    return False


def get_plain_text(p_elem):
    parts = []
    if p_elem.text:
        parts.append(p_elem.text)
    for child in p_elem:
        if child.tag == "tag":
            if child.tail:
                parts.append(child.tail)
        elif child.tag == "element" and child.get("kind", "") in _NON_TEXT_KINDS:
            if child.tail:
                parts.append(child.tail)
        else:
            parts.append(get_plain_text(child))
            if child.tail:
                parts.append(child.tail)
    return "".join(parts)


def paragraphs_to_rtf(p_elems, scrivener_format=False, images=None):
    rtf_parts = []
    i = 0

    par_open  = r'\pard\plain\fs32 \sa60\sb60\ltrch\loch ' if scrivener_format else r'{\pard\sb60\sa60 '
    par_close = r'\par' if scrivener_format else r'\par}'

    def par(content):
        if scrivener_format:
            return f'{par_open}{{{content}}}{par_close}'
        else:
            return f'{{\\pard\\sb60\\sa60 {content}\\par}}'

    def empty_par():
        if scrivener_format:
            return r'\par\pard\plain\fs32 \ltrch\loch '
        else:
            return r'{\pard\sb0\sa0\par}'

    while i < len(p_elems):
        p = p_elems[i]
        kind = get_block_kind(p)
        text = element_to_rtf(p, images)
        plain = get_plain_text(p).strip()

        if kind in HEADING_TAGS:
            size = HEADING_SIZES[kind]
            if scrivener_format:
                rtf_parts.append(
                    f'\\pard\\plain\\fs{size} \\sa60\\sb120\\b\\ltrch\\loch {{{text}}}\\par'
                )
            else:
                rtf_parts.append(
                    f'{{\\pard\\sb120\\sa60\\b\\fs{size} {text}\\par}}'
                )
            i += 1

        elif kind == "divider":
            if scrivener_format:
                rtf_parts.append(r'\pard\plain\fs32 \sa120\sb120\qc {* * *}\par')
            else:
                rtf_parts.append(r'{\pard\sb120\sa120\qc * * *\par}')
            i += 1

        elif kind == "blockquote":
            if scrivener_format:
                rtf_parts.append(
                    f'\\pard\\plain\\fs32 \\li720\\ri720\\sa60\\sb60\\ltrch\\loch {{{text}}}\\par'
                )
            else:
                rtf_parts.append(
                    f'{{\\pard\\li720\\ri720\\sb60\\sa60 {text}\\par}}'
                )
            i += 1

        elif kind == "unorderedList":
            while i < len(p_elems) and get_block_kind(p_elems[i]) == "unorderedList":
                item_text = element_to_rtf(p_elems[i], images)
                if scrivener_format:
                    rtf_parts.append(
                        f'\\pard\\plain\\fs32 \\li360\\fi-360\\ltrch\\loch {{\\bullet\\tab {item_text}}}\\par'
                    )
                else:
                    rtf_parts.append(
                        f'{{\\pard\\li360\\fi-360 \\bullet\\tab {item_text}\\par}}'
                    )
                i += 1

        elif kind == "orderedList":
            num = 1
            while i < len(p_elems) and get_block_kind(p_elems[i]) == "orderedList":
                item_text = element_to_rtf(p_elems[i], images)
                if scrivener_format:
                    rtf_parts.append(
                        f'\\pard\\plain\\fs32 \\li360\\fi-360\\ltrch\\loch {{{num}.\\tab {item_text}}}\\par'
                    )
                else:
                    rtf_parts.append(
                        f'{{\\pard\\li360\\fi-360 {num}.\\tab {item_text}\\par}}'
                    )
                i += 1
                num += 1

        elif kind == "codeblock":
            code_lines = []
            i += 1
            while i < len(p_elems):
                if get_block_kind(p_elems[i]) == "codeblock":
                    i += 1
                    break
                code_lines.append(rtf_escape(get_plain_text(p_elems[i])))
                i += 1
            code_text = "\\line ".join(code_lines)
            if scrivener_format:
                rtf_parts.append(
                    f'\\pard\\plain\\fs28 \\f1\\sa60\\sb60\\ltrch\\loch {{{code_text}}}\\par'
                )
            else:
                rtf_parts.append(f'{{\\pard\\f1\\sb60\\sa60 {code_text}\\par}}')

        elif re.match(r'^#+', plain) or plain.startswith('@:'):
            i += 1

        elif not plain:
            if _has_image_element(p):
                rtf_parts.append(par(text))
                i += 1
            else:
                j = i
                while j < len(p_elems) and not get_plain_text(p_elems[j]).strip() and not _has_image_element(p_elems[j]):
                    j += 1
                rtf_parts.append(empty_par())
                i = j

        else:
            rtf_parts.append(par(text))
            i += 1

    sep = '\n' if scrivener_format else '\n'
    return sep.join(rtf_parts)


def xml_content_to_rtf(xml_text, title="", skip_first_heading=True,
                        scrivener_format=False, images=None):
    """images: dict {identifier_str: (binary_data, ext)} for inline image embedding."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        body = f'{{\\pard {rtf_escape(xml_text)}\\par}}'
        return wrap_rtf_scrivener(body) if scrivener_format else wrap_rtf_directory(body)

    string_elem = root.find("string")
    if string_elem is None:
        return wrap_rtf_scrivener("") if scrivener_format else wrap_rtf_directory("")

    p_elems = list(string_elem.findall("p"))

    if skip_first_heading:
        start = 0
        while start < len(p_elems) and not get_plain_text(p_elems[start]).strip():
            start += 1
        if start < len(p_elems):
            kind = get_block_kind(p_elems[start])
            plain = get_plain_text(p_elems[start]).strip()
            is_heading = kind in HEADING_TAGS or re.match(r'^#+\s', plain)
            if is_heading:
                p_elems = p_elems[:start] + p_elems[start + 1:]

    body = paragraphs_to_rtf(p_elems, scrivener_format=scrivener_format, images=images)
    return wrap_rtf_scrivener(body) if scrivener_format else wrap_rtf_directory(body)


def get_sheet_title(xml_text, fallback="Untitled"):
    try:
        root = ET.fromstring(xml_text)
        string_elem = root.find("string")
        if string_elem is None:
            return fallback
        for p in string_elem.findall("p"):
            kind = get_block_kind(p)
            text = get_plain_text(p).strip()
            if not text:
                continue
            text = re.sub(r'^#+\s*', '', text)
            if text:
                return text[:80]
    except ET.ParseError:
        pass
    return fallback


# =============================================================================
# Font fixer (from fixfonts.py)
# =============================================================================

FONT_PATTERN = re.compile(
    r'(\\f\d+)\\fmodern(\\fcharset\d+(?:\\fprq\d+)? )[^;]+;'
)
FONT_REPLACEMENT = r'\1\\froman\2Georgia;'
SIZE_PATTERN = re.compile(r'\\fs\d+')
SIZE_REPLACEMENT = r'\\fs32'
PLAIN_PATTERN = re.compile(r'\\plain(?!\\fs)')
PLAIN_REPLACEMENT = r'\\plain\\fs32'


def fix_rtf_content(content):
    """Apply all font fixes to RTF content string. Returns (fixed_content, changed_bool)."""
    needs_font_fix = bool(FONT_PATTERN.search(content))
    needs_size_fix = bool(SIZE_PATTERN.search(content) and r'\fs32' not in content)
    needs_plain_fix = bool(PLAIN_PATTERN.search(content))

    if not (needs_font_fix or needs_size_fix or needs_plain_fix):
        return content, False

    fixed = content
    if needs_font_fix:
        fixed = FONT_PATTERN.sub(FONT_REPLACEMENT, fixed)
    if needs_size_fix:
        fixed = SIZE_PATTERN.sub(SIZE_REPLACEMENT, fixed)
    if needs_plain_fix:
        fixed = PLAIN_PATTERN.sub(PLAIN_REPLACEMENT, fixed)
    return fixed, True


def fix_rtf_file(rtf_path):
    """Read, fix, and write an RTF file. Returns True if changed."""
    try:
        content = Path(rtf_path).read_text(encoding="cp1252")
    except Exception:
        try:
            content = Path(rtf_path).read_text(encoding="utf-8")
        except Exception:
            return False
    fixed, changed = fix_rtf_content(content)
    if changed:
        try:
            Path(rtf_path).write_text(fixed, encoding="cp1252")
        except Exception:
            Path(rtf_path).write_text(fixed, encoding="utf-8")
    return changed


# =============================================================================
# Scrivener project builder
# =============================================================================

def new_uuid():
    return str(uuid.uuid4()).upper()


def scriv_timestamp():
    """Scrivener timestamp: 'YYYY-MM-DD HH:MM:SS -0600'"""
    now = datetime.now()
    return now.strftime("%Y-%m-%d %H:%M:%S -0600")


class ScrivNode:
    """Represents a node in the Scrivener binder tree."""
    def __init__(self, title, node_type="Text", uuid_str=None):
        self.title = title
        self.node_type = node_type  # Text, Folder, DraftFolder, ResearchFolder, TrashFolder
        self.uuid = uuid_str or new_uuid()
        self.children = []
        self.rtf_content = None  # only for Text nodes

    def add_child(self, node):
        self.children.append(node)
        return node


def build_scrivx_xml(project_name, draft_root, research_root, trash_root, project_uuid):
    """Build the .scrivx XML string matching Scrivener 3 for Windows format."""
    ts = scriv_timestamp()

    # Section type UUIDs — stable for this project
    type_heading    = new_uuid()
    type_subheading = new_uuid()
    type_section    = new_uuid()

    lines = ['<?xml version="1.0" encoding="UTF-8"?>']
    lines.append(
        f'<ScrivenerProject Template="No" Version="2.0" '
        f'Identifier="{project_uuid}" Creator="SCRWIN-3.1.6.0" '
        f'Device="Pomegranate" Modified="{ts}" ModID="{new_uuid()}">'
    )
    lines.append('    <Binder>')

    def render_node(node, indent=8):
        pad = ' ' * indent
        is_folder = node.node_type == "Folder"
        is_text        = node.node_type == "Text"

        lines.append(
            f'{pad}<BinderItem UUID="{node.uuid}" Type="{node.node_type}" '
            f'Created="{ts}" Modified="{ts}">'
        )
        lines.append(f'{pad}    <Title>{_xml_escape(node.title)}</Title>')
        lines.append(f'{pad}    <MetaData>')
        lines.append(f'{pad}        <IncludeInCompile>Yes</IncludeInCompile>')
        if is_text and node.rtf_content is not None:
            lines.append(f'{pad}        <FileExtension>rtf</FileExtension>')
        lines.append(f'{pad}    </MetaData>')

        # TextSettings only on Folder and Text nodes, not on root folders
        if is_folder or is_text:
            lines.append(f'{pad}    <TextSettings>')
            lines.append(f'{pad}        <TextSelection>0,0</TextSelection>')
            lines.append(f'{pad}    </TextSettings>')

        # CorkboardAndOutliner on Folder nodes
        if is_folder and node.children:
            first_child_uuid = node.children[0].uuid
            lines.append(f'{pad}    <CorkboardAndOutliner>')
            lines.append(f'{pad}        <SelectedSubdocumentUUIDs>{first_child_uuid}</SelectedSubdocumentUUIDs>')
            lines.append(f'{pad}        <CorkboardSettings>')
            lines.append(f'{pad}            <Arrangement>Linear</Arrangement>')
            lines.append(f'{pad}        </CorkboardSettings>')
            lines.append(f'{pad}    </CorkboardAndOutliner>')

        if node.children:
            lines.append(f'{pad}    <Children>')
            for child in node.children:
                render_node(child, indent + 8)
            lines.append(f'{pad}    </Children>')
        lines.append(f'{pad}</BinderItem>')

    render_node(draft_root)
    render_node(research_root)
    render_node(trash_root)

    lines.append('    </Binder>')
    lines.append('    <Collections>')
    lines.append(
        f'        <Collection Type="Binder" ID="{new_uuid()}" Color="0.145098 0.207843 0.164706">'
    )
    lines.append('            <Title>Binder</Title>')
    lines.append('        </Collection>')
    lines.append(
        f'        <Collection Type="RecentSearch" ID="{new_uuid()}" Color="0.321569 0.458824 0.360784">'
    )
    lines.append('            <Title>Search Results</Title>')
    lines.append(
        '            <SearchSettings Operator="Any" Type="All" Scope="All" '
        'CompileSetting="All" CaseSensitive="No" IgnoreDiacritics="No"></SearchSettings>'
    )
    lines.append('        </Collection>')
    lines.append('    </Collections>')
    lines.append('    <SectionTypes>')
    lines.append('        <TypeDefinitions>')
    lines.append(f'            <Type ID="{type_heading}">Heading</Type>')
    lines.append(f'            <Type ID="{type_subheading}">Sub-Heading</Type>')
    lines.append(f'            <Type ID="{type_section}">Section</Type>')
    lines.append('        </TypeDefinitions>')
    lines.append('        <LevelTypes>')
    lines.append('            <Folders>')
    lines.append(f'                <Type>{type_heading}</Type>')
    lines.append('            </Folders>')
    lines.append('            <Containers>')
    lines.append(f'                <Type>{type_section}</Type>')
    lines.append('            </Containers>')
    lines.append('            <Files>')
    lines.append(f'                <Type>{type_section}</Type>')
    lines.append('            </Files>')
    lines.append('        </LevelTypes>')
    lines.append('    </SectionTypes>')
    lines.append('    <LabelSettings>')
    lines.append('        <Title>Label</Title>')
    lines.append('        <DefaultLabelID>-1</DefaultLabelID>')
    lines.append('        <Labels>')
    lines.append('            <Label ID="-1">No Label</Label>')
    lines.append('            <Label ID="0" Color="0.993500 0.701213 0.732586">Red</Label>')
    lines.append('            <Label ID="1" Color="0.995422 0.790951 0.652384">Orange</Label>')
    lines.append('            <Label ID="2" Color="0.997726 0.892729 0.652567">Yellow</Label>')
    lines.append('            <Label ID="3" Color="0.715862 0.948714 0.697688">Green</Label>')
    lines.append('            <Label ID="4" Color="0.702312 0.888273 0.974258">Blue</Label>')
    lines.append('            <Label ID="5" Color="0.957565 0.766751 0.999619">Purple</Label>')
    lines.append('        </Labels>')
    lines.append('    </LabelSettings>')
    lines.append('    <StatusSettings>')
    lines.append('        <Title>Status</Title>')
    lines.append('        <DefaultStatusID>-1</DefaultStatusID>')
    lines.append('        <StatusItems>')
    lines.append('            <Status ID="-1">No Status</Status>')
    lines.append('            <Status ID="0">To Do</Status>')
    lines.append('            <Status ID="1">In Progress</Status>')
    lines.append('            <Status ID="2">First Draft</Status>')
    lines.append('            <Status ID="3">Revised Draft</Status>')
    lines.append('            <Status ID="4">Final Draft</Status>')
    lines.append('            <Status ID="5">Done</Status>')
    lines.append('        </StatusItems>')
    lines.append('    </StatusSettings>')
    lines.append(
        f'    <ProjectTargets Notify="No">'
    )
    lines.append(
        f'        <DraftTarget Type="Words" CountIncludedOnly="Yes" CurrentCompileGroupOnly="No" '
        f'Deadline="{ts}" IgnoreDeadline="Yes">0</DraftTarget>'
    )
    lines.append(
        '        <SessionTarget Type="Words" CountDraftOnly="No" AllowNegatives="Yes" '
        'ResetType="Time" ResetTime="01:00" DeterminedFromDeadline="No" '
        'CanWriteOnDeadlineDate="Yes" WritingDays="">0</SessionTarget>'
    )
    lines.append('    </ProjectTargets>')
    lines.append(f'    <RecentWritingHistory Date="{ts[:10]} 00:00:00 -0600">')
    lines.append('        <DraftWordCount>0</DraftWordCount>')
    lines.append('        <DraftCharCount>0</DraftCharCount>')
    lines.append('        <OtherWordCount>0</OtherWordCount>')
    lines.append('        <OtherCharCount>0</OtherCharCount>')
    lines.append('    </RecentWritingHistory>')
    lines.append(
        '    <PrintSettings PaperSize="612.0,792.0" LeftMargin="72.0" RightMargin="72.0" '
        'TopMargin="72.0" BottomMargin="72.0" PaperType="na-letter" Orientation="Portrait" '
        'ScaleFactor="1.0" HorizontallyCentered="Yes" VerticallyCentered="Yes" '
        'Collates="No" PagesAcross="1" PagesDown="1"/>'
    )
    lines.append('</ScrivenerProject>')

    return '\n'.join(lines)


def _xml_escape(text):
    return (text.replace('&', '&amp;').replace('<', '&lt;')
                .replace('>', '&gt;').replace('"', '&quot;'))


def collect_text_nodes(node):
    """Recursively yield all Text nodes from a binder tree."""
    if node.node_type == "Text" and node.rtf_content is not None:
        yield node
    for child in node.children:
        yield from collect_text_nodes(child)


# =============================================================================
# ulproj -> structured node tree
# =============================================================================

def build_node_tree_from_ulproj(ulproj_path, log_fn=print):
    """
    Parse a .ulproj zip and return (project_name, draft_root).
    Images are embedded directly into the RTF content via \\pict blocks.
    """
    image_extensions = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"}

    with zipfile.ZipFile(ulproj_path, "r") as z:
        all_names = z.namelist()

        # Read group display names
        group_display = {}
        for name in all_names:
            basename = name.replace("\\", "/").split("/")[-1]
            if basename in ("Info.ulgroup", "Info.ultrash"):
                folder = "/".join(name.replace("\\", "/").split("/")[:-1])
                try:
                    data = plistlib.loads(z.read(name))
                    group_display[folder] = data.get("displayName", folder.split("/")[-1])
                except Exception:
                    group_display[folder] = folder.split("/")[-1]

        # Project name
        project_name = "Project"
        for folder, dname in group_display.items():
            if folder.endswith("-ulproject") and "/" not in folder:
                project_name = dname
                break

        log_fn(f"  Project: {project_name}")

        # Build a folder-path -> ScrivNode map
        # Each ulgroup path maps to a Folder node
        folder_nodes = {}

        def get_or_create_folder(path_parts, parent_node):
            """Recursively get/create folder nodes for a path."""
            if not path_parts:
                return parent_node
            key = "/".join(path_parts)
            if key in folder_nodes:
                return folder_nodes[key]
            display = group_display.get(key, path_parts[-1])
            if not display or display == path_parts[-1]:
                display = re.sub(r'[a-f0-9]{32}', '', path_parts[-1]).strip('-').strip() or path_parts[-1]
            node = ScrivNode(sanitize_filename(display), node_type="Folder")
            folder_nodes[key] = node
            parent_node.add_child(node)
            return node

        draft_root = ScrivNode(project_name, node_type="DraftFolder")

        # Process Content.xml files
        for name in sorted(all_names):
            zip_name = name.replace("\\", "/")
            if not zip_name.endswith("/Content.xml"):
                continue
            if any(skip in zip_name for skip in SKIP_GROUPS):
                continue

            try:
                xml_text = z.read(name).decode("utf-8")
            except Exception as e:
                log_fn(f"  Warning: Could not read {name}: {e}")
                continue

            title = get_sheet_title(xml_text)
            if not title or title == "Untitled":
                # Keep sheets that have text OR image content; skip truly blank ones
                has_content = False
                try:
                    root_elem = ET.fromstring(xml_text)
                    se = root_elem.find("string")
                    if se is not None:
                        for p in se.findall("p"):
                            if get_plain_text(p).strip() or _has_image_element(p):
                                has_content = True
                                break
                except Exception:
                    pass
                if not has_content:
                    continue

            # Build the folder path for this sheet
            parts = zip_name.split("/")
            # parts[-1] = "Content.xml", parts[-2] = sheet uuid folder, rest = group path
            group_path_parts = parts[:-2]

            # Filter out the project root and Main-ulgroup
            display_parts = []
            for idx, part in enumerate(group_path_parts):
                if part.endswith("-ulproject"):
                    continue
                if part == "Main-ulgroup":
                    continue
                full_path = "/".join(group_path_parts[:idx + 1])
                disp = group_display.get(full_path, "")
                if not disp:
                    # Try to humanize the UUID-like folder name
                    clean = re.sub(r'^[a-f0-9]{32}-?', '', part).strip('-')
                    disp = clean if clean else part
                display_parts.append((full_path, disp))

            # Find or create the parent folder node
            parent = draft_root
            for full_path, disp in display_parts:
                key = full_path
                if key not in folder_nodes:
                    node = ScrivNode(sanitize_filename(disp), node_type="Folder")
                    folder_nodes[key] = node
                    parent.add_child(node)
                parent = folder_nodes[key]

            # Build images dict for this sheet: {identifier → (data, ext)}
            # The identifier is the hash embedded in the image filename,
            # e.g. "17eb4d87..." from "Image 5-29-26.17eb4d87....jpeg"
            sheet_prefix = "/".join(parts[:-1]) + "/"
            images = {}
            for img_name in all_names:
                img_zip = img_name.replace("\\", "/")
                if img_zip.startswith(sheet_prefix):
                    ext = os.path.splitext(img_zip)[1].lower()
                    if ext in image_extensions:
                        img_filename = img_zip.split("/")[-1]
                        # Extract the identifier (last dot-separated segment before extension)
                        name_no_ext = os.path.splitext(img_filename)[0]
                        identifier = name_no_ext.split(".")[-1] if "." in name_no_ext else name_no_ext
                        img_data = z.read(img_name)
                        images[identifier] = (img_data, ext.lstrip("."))
                        log_fn(f"  Image: {img_filename}")

            # Create the text node — images are embedded inline in the RTF
            sheet_node = ScrivNode(title, node_type="Text")
            sheet_node.rtf_content = xml_content_to_rtf(
                xml_text, title=title, scrivener_format=True, images=images
            )
            parent.add_child(sheet_node)
            log_fn(f"  Sheet: {title}")

    return project_name, draft_root


# =============================================================================
# Main conversion functions called by worker thread
# =============================================================================

def convert_to_directory(input_path, output_folder, log_fn=print):
    """Convert a .ulproj to a folder of RTF files, then fix fonts."""
    count = 0
    image_extensions = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"}
    os.makedirs(output_folder, exist_ok=True)

    if input_path.endswith(".ulproj"):
        with zipfile.ZipFile(input_path, "r") as z:
            all_names = z.namelist()

            group_display = {}
            for name in all_names:
                basename = name.replace("\\", "/").split("/")[-1]
                if basename in ("Info.ulgroup", "Info.ultrash"):
                    folder = "/".join(name.replace("\\", "/").split("/")[:-1])
                    try:
                        data = plistlib.loads(z.read(name))
                        group_display[folder] = data.get("displayName", folder.split("/")[-1])
                    except Exception:
                        group_display[folder] = folder.split("/")[-1]

            project_name = "Project"
            for folder, dname in group_display.items():
                if folder.endswith("-ulproject") and "/" not in folder:
                    project_name = dname
                    break
            log_fn(f"  Project: {project_name}")

            for name in all_names:
                zip_name = name.replace("\\", "/")
                if not zip_name.endswith("/Content.xml"):
                    continue
                if any(skip in zip_name for skip in SKIP_GROUPS):
                    continue

                try:
                    xml_text = z.read(name).decode("utf-8")
                except Exception as e:
                    log_fn(f"  Warning: {e}")
                    continue

                title = get_sheet_title(xml_text)
                rtf_content = xml_content_to_rtf(xml_text, title=title, scrivener_format=False)

                parts = zip_name.split("/")
                output_parts = [project_name]
                for part in parts[:-2]:
                    if part.endswith("-ulproject"):
                        continue
                    if part == "Main-ulgroup":
                        continue
                    folder_path = "/".join(parts[:parts.index(part) + 1])
                    display = group_display.get(folder_path, part)
                    if display:
                        output_parts.append(sanitize_filename(display))

                dest_folder = os.path.join(output_folder, *output_parts)
                os.makedirs(dest_folder, exist_ok=True)

                output_path = unique_path(dest_folder, title, ext=".rtf")
                with open(output_path, "w", encoding="ascii", errors="replace") as f:
                    f.write(rtf_content)
                log_fn(f"  Saved: {os.path.relpath(output_path, output_folder)}")
                count += 1

                sheet_prefix = "/".join(parts[:-1]) + "/"
                for img_name in all_names:
                    img_zip = img_name.replace("\\", "/")
                    if img_zip.startswith(sheet_prefix):
                        ext = os.path.splitext(img_zip)[1].lower()
                        if ext in image_extensions:
                            images_dir = os.path.join(dest_folder, "images")
                            os.makedirs(images_dir, exist_ok=True)
                            img_filename = img_zip.split("/")[-1]
                            with open(os.path.join(images_dir, img_filename), "wb") as f:
                                f.write(z.read(img_name))
                            log_fn(f"  Image: {img_filename}")

    elif input_path.endswith(".textpack"):
        count += _process_textpack_dir(input_path, output_folder, log_fn)
    elif input_path.endswith(".md"):
        count += _process_md_dir(input_path, output_folder, log_fn)

    # Fix fonts on all generated RTF files
    fixed_count = 0
    for root_dir, dirs, files in os.walk(output_folder):
        for fname in files:
            if fname.lower().endswith(".rtf"):
                if fix_rtf_file(os.path.join(root_dir, fname)):
                    fixed_count += 1
    if fixed_count:
        log_fn(f"  Font-fixed {fixed_count} RTF file(s)")

    log_fn(f"  Done — {count} sheet(s) saved to: {output_folder}")
    return count


def convert_to_scrivener(input_path, output_folder, log_fn=print):
    """Convert a .ulproj to a Scrivener .scriv project."""
    if not input_path.endswith(".ulproj"):
        log_fn("  Scrivener output is only supported for .ulproj files.")
        return 0

    project_name, draft_root = build_node_tree_from_ulproj(input_path, log_fn)
    safe_name = sanitize_filename(project_name)

    # Determine output path
    scriv_dir = os.path.join(output_folder, f"{safe_name}.scriv")
    counter = 2
    while os.path.exists(scriv_dir):
        scriv_dir = os.path.join(output_folder, f"{safe_name}_{counter}.scriv")
        counter += 1

    files_data_dir = os.path.join(scriv_dir, "Files", "Data")
    os.makedirs(files_data_dir, exist_ok=True)
    os.makedirs(os.path.join(scriv_dir, "Files"), exist_ok=True)
    os.makedirs(os.path.join(scriv_dir, "Settings"), exist_ok=True)

    research_root = ScrivNode("Research", node_type="ResearchFolder")
    trash_root = ScrivNode("Trash", node_type="TrashFolder")
    project_uuid = new_uuid()

    # Write RTF files for each text node
    all_text_nodes = list(collect_text_nodes(draft_root))
    for node in all_text_nodes:
        node_dir = os.path.join(files_data_dir, node.uuid)
        os.makedirs(node_dir, exist_ok=True)
        rtf_path = os.path.join(node_dir, "content.rtf")
        try:
            with open(rtf_path, "w", encoding="cp1252", errors="replace") as f:
                f.write(node.rtf_content)
        except Exception:
            with open(rtf_path, "w", encoding="utf-8") as f:
                f.write(node.rtf_content)
        fix_rtf_file(rtf_path)

    # Build and write .scrivx
    scrivx_content = build_scrivx_xml(
        project_name, draft_root, research_root, trash_root, project_uuid
    )
    scrivx_filename = f"{safe_name}.scrivx"
    scrivx_path = os.path.join(scriv_dir, scrivx_filename)
    with open(scrivx_path, "w", encoding="utf-8") as f:
        f.write(scrivx_content)

    # Write binder.autosave and binder.backup — Scrivener Windows reads these
    # as the primary binder source (ZIP-wrapped copy of the .scrivx XML).
    files_dir = os.path.join(scriv_dir, "Files")
    for binder_filename in ("binder.autosave", "binder.backup"):
        binder_path = os.path.join(files_dir, binder_filename)
        with zipfile.ZipFile(binder_path, "w", compression=zipfile.ZIP_DEFLATED) as bz:
            bz.writestr(scrivx_filename, scrivx_content.encode("utf-8"))

    # Write all required support files
    _write_scrivener_support_files(
        scriv_dir, draft_root, research_root, trash_root, all_text_nodes
    )

    count = len(all_text_nodes)
    log_fn(f"  Done — {count} sheet(s) saved to: {scriv_dir}")
    return count


def _collect_all_uuids(node):
    """Return all UUIDs in binder order (depth-first)."""
    uuids = [node.uuid]
    for child in node.children:
        uuids.extend(_collect_all_uuids(child))
    return uuids


def _collect_folder_uuids(node):
    """Return UUIDs of folder-type nodes (for mobile-outline.states expanded list)."""
    uuids = []
    if node.node_type in ("DraftFolder", "ResearchFolder", "TrashFolder", "Folder"):
        uuids.append(node.uuid)
    for child in node.children:
        uuids.extend(_collect_folder_uuids(child))
    return uuids


def _write_scrivener_support_files(scriv_dir, draft_root, research_root, trash_root, all_text_nodes):
    """
    Write every file a Scrivener 3 for Windows project needs to open correctly,
    including on mobile (Scrivener for iOS/Android).
    """
    import json as _json

    files_dir = os.path.join(scriv_dir, "Files")
    settings_dir = os.path.join(scriv_dir, "Settings")

    # ------------------------------------------------------------------
    # Files/version.txt  — must be "23" for Scrivener 3
    # ------------------------------------------------------------------
    with open(os.path.join(files_dir, "version.txt"), "w") as f:
        f.write("23")

    # ------------------------------------------------------------------
    # Files/search.indexes  — pre-populated so Scrivener doesn't warn on open
    # ------------------------------------------------------------------
    def _collect_index_nodes(node, acc):
        if node.node_type in ("Text", "Folder"):
            acc.append(node)
        for child in node.children:
            _collect_index_nodes(child, acc)

    index_nodes = []
    _collect_index_nodes(draft_root, index_nodes)
    _collect_index_nodes(research_root, index_nodes)
    idx_lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<SearchIndexes Version="1.0">', '    <Documents>']
    for n in index_nodes:
        idx_lines.append(f'        <Document ID="{n.uuid}">')
        idx_lines.append(f'            <Title>{_xml_escape(n.title)}</Title>')
        idx_lines.append('        </Document>')
    idx_lines.extend(['    </Documents>', '</SearchIndexes>', ''])
    with open(os.path.join(files_dir, "search.indexes"), "w", encoding="utf-8") as f:
        f.write('\n'.join(idx_lines))

    # ------------------------------------------------------------------
    # Files/writing.history  — empty history, Scrivener fills in
    # ------------------------------------------------------------------
    with open(os.path.join(files_dir, "writing.history"), "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n<WritingHistory/>\n')

    # ------------------------------------------------------------------
    # Files/styles.xml  — standard Scrivener default styles
    # Keeping these ensures headings/quotes display correctly on mobile.
    # ------------------------------------------------------------------
    styles_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<Styles>\n'
        '    <Style ID="1B4BF4A6-7148-4D19-BF14-E706010C259A" Name="Title" Type="Para+Char" FontChange="Size">\n'
        r'        <Format><![CDATA[{\rtf1\ansi\ansicpg1252\uc1\deff0{\fonttbl{\f0\fnil\fcharset0\fprq2 Georgia;}}{\colortbl;\red0\green0\blue0;\red255\green255\blue255;}\paperw12240\paperh15840\margl1800\margr1800\deftab1200\f0\fs56\cf0\pard\plain \sb260\ltrch\loch {\f0\fs56\b0\i0 Attributes}}]]></Format>' + '\n'
        '    </Style>\n'
        '    <Style ID="DBDFDA70-AE58-4FF5-A58C-91265E2A9331" Name="Heading 1" Shortcut="4" Type="Para+Char" FontChange="Size">\n'
        r'        <Format><![CDATA[{\rtf1\ansi\ansicpg1252\uc1\deff0{\fonttbl{\f0\fnil\fcharset0\fprq2 Georgia;}}{\colortbl;\red0\green0\blue0;\red255\green255\blue255;}\paperw12240\paperh15840\margl1800\margr1800\deftab1200\f0\fs36\cf0\pard\plain \sb260\ltrch\loch {\f0\fs36\b1\i0 Attributes}}]]></Format>' + '\n'
        '    </Style>\n'
        '    <Style ID="6D32C9CC-30F9-4085-B965-3CC9DA2103B0" Name="Heading 2" Shortcut="5" Type="Para+Char" FontChange="Size">\n'
        r'        <Format><![CDATA[{\rtf1\ansi\ansicpg1252\uc1\deff0{\fonttbl{\f0\fnil\fcharset0\fprq2 Georgia;}}{\colortbl;\red0\green0\blue0;\red255\green255\blue255;}\paperw12240\paperh15840\margl1800\margr1800\deftab1200\f0\fs26\cf0\pard\plain \sb260\ltrch\loch {\f0\fs26\b1\i0 Attributes}}]]></Format>' + '\n'
        '    </Style>\n'
        '    <Style ID="BB003012-2C9A-4D7B-A0D2-82F0CC5D0451" Name="Centered Text" Shortcut="1" Type="Para">\n'
        r'        <Format><![CDATA[{\rtf1\ansi\ansicpg1252\uc1\deff0{\fonttbl{\f0\fnil\fcharset0\fprq2 Georgia;}}{\colortbl;\red0\green0\blue0;\red255\green255\blue255;}\paperw12240\paperh15840\margl1800\margr1800\deftab1200\f0\fs26\cf0\pard\plain \qc\ltrch\loch {\f0\fs26\b0\i0 Attributes}}]]></Format>' + '\n'
        '    </Style>\n'
        '    <Style ID="BC9C3AB1-882B-4429-8630-15C6A4605915" Name="Block Quote" Shortcut="2" Type="Para" FontChange="Size">\n'
        r'        <Format><![CDATA[{\rtf1\ansi\ansicpg1252\uc1\deff0{\fonttbl{\f0\fnil\fcharset0\fprq2 Georgia;}}{\colortbl;\red0\green0\blue0;\red255\green255\blue255;}\paperw12240\paperh15840\margl1800\margr1800\deftab1200\f0\fs24\cf0\pard\plain \li720\sa240\sb240\ltrch\loch {\f0\fs24\b0\i0 Attributes}}]]></Format>' + '\n'
        '    </Style>\n'
        '    <Style ID="45C0816B-4DBD-413A-98DD-1ADEEF65303E" Name="Code Block" Next="45C0816B-4DBD-413A-98DD-1ADEEF65303E" Type="Para+Char" FontChange="Face+Size">\n'
        r'        <Format><![CDATA[{\rtf1\ansi\ansicpg1252\uc1\deff0{\fonttbl{\f0\fnil\fcharset0\fprq2 Consolas;}}{\colortbl;\red0\green0\blue0;\red255\green255\blue255;}\paperw12240\paperh15840\margl1800\margr1800\deftab1200\f0\fs22\cf0\pard\plain \li720\ltrch\loch {\f0\fs22\b0\i0 Attributes}}]]></Format>' + '\n'
        '    </Style>\n'
        '</Styles>\n'
    )
    with open(os.path.join(files_dir, "styles.xml"), "w", encoding="utf-8") as f:
        f.write(styles_xml)

    # ------------------------------------------------------------------
    # Files/Data/docs.checksum
    # Format: <UUID>/content.rtf=<sha1>  (one line per document)
    # Scrivener uses this to verify document integrity; empty = content hidden.
    # ------------------------------------------------------------------
    import hashlib as _hashlib
    checksum_lines = []
    for node in all_text_nodes:
        rtf_path = os.path.join(files_dir, "Data", node.uuid, "content.rtf")
        if os.path.exists(rtf_path):
            sha1 = _hashlib.sha1(open(rtf_path, "rb").read()).hexdigest()
            checksum_lines.append(f"{node.uuid}/content.rtf={sha1}")
    with open(os.path.join(files_dir, "Data", "docs.checksum"), "w", encoding="utf-8") as f:
        f.write("\n".join(checksum_lines) + ("\n" if checksum_lines else ""))

    # ------------------------------------------------------------------
    # Settings/ui.ini
    # ------------------------------------------------------------------
    with open(os.path.join(settings_dir, "ui.ini"), "w") as f:
        f.write("[General]\n")

    # ------------------------------------------------------------------
    # Settings/favorites.xml
    # ------------------------------------------------------------------
    with open(os.path.join(settings_dir, "favorites.xml"), "w", encoding="utf-8") as f:
        f.write(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<Favorites Version="1.0">\n'
            '    <MoveTo><Recent/><Popular/></MoveTo>\n'
            '    <Append><Recent/><Popular/></Append>\n'
            '</Favorites>\n'
        )

    # ------------------------------------------------------------------
    # Settings/recents.txt  — UUIDs of recently viewed items (all of them)
    # Scrivener uses this to restore the last open document on launch.
    # List all text nodes first (most recently "viewed"), then folders.
    # ------------------------------------------------------------------
    all_uuids = (
        [n.uuid for n in all_text_nodes]
        + _collect_folder_uuids(draft_root)
        + _collect_folder_uuids(research_root)
        + _collect_folder_uuids(trash_root)
    )
    # Deduplicate while preserving order
    seen = set()
    unique_uuids = []
    for u in all_uuids:
        if u not in seen:
            seen.add(u)
            unique_uuids.append(u)
    with open(os.path.join(settings_dir, "recents.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(unique_uuids) + "\n")

    # ------------------------------------------------------------------
    # Settings/mobile-outline.states
    # Controls which binder groups are expanded in the mobile app.
    # DraftFolder and its immediate children should be expanded.
    # ------------------------------------------------------------------
    expanded_uuids = [draft_root.uuid] + [c.uuid for c in draft_root.children]
    mobile_outline = {"$ROOT": expanded_uuids}
    with open(os.path.join(settings_dir, "mobile-outline.states"), "w", encoding="utf-8") as f:
        _json.dump(mobile_outline, f, indent=2)

    # ------------------------------------------------------------------
    # Settings/mobile.settings
    # TextScaleFactor: scale multiplier for text on mobile (1.0 = no scaling).
    # DocStates: scroll position per document — start at top for all.
    # This file is the key to mobile font stability: without it, mobile
    # Scrivener may apply its own font overrides that break the RTF styling.
    # ------------------------------------------------------------------
    doc_states = {node.uuid: {"scrollPos": "0"} for node in all_text_nodes}
    mobile_settings = {
        "TextScaleFactor": 1.0,
        "DocStates": doc_states
    }
    with open(os.path.join(settings_dir, "mobile.settings"), "w", encoding="utf-8") as f:
        _json.dump(mobile_settings, f, indent=2)

    # ------------------------------------------------------------------
    # Settings/ui-common.xml
    # Tells Scrivener which document to open and which binder items to
    # expand on launch. We open the first text node (or DraftFolder if
    # there are no text nodes).
    # ------------------------------------------------------------------
    first_text_uuid = all_text_nodes[0].uuid if all_text_nodes else draft_root.uuid
    expanded_items = "\n".join(
        f"        <ItemID>{uid}</ItemID>"
        for uid in ([draft_root.uuid]
                    + [c.uuid for c in draft_root.children]
                    + [research_root.uuid])
    )
    ui_common_xml = f'''\
<?xml version="1.0" encoding="UTF-8"?>
<UIStates>
    <Binder Show="Yes">
        <ShowCollections>No</ShowCollections>
        <SelectedCollection>0</SelectedCollection>
        <SubdocumentCounts>No</SubdocumentCounts>
        <ExpandedItems>
{expanded_items}
        </ExpandedItems>
        <Selection>
            <ItemID>{first_text_uuid}</ItemID>
        </Selection>
        <SearchResultsSort Titles="Ascending" Dates="Ascending">None</SearchResultsSort>
    </Binder>
    <Inspector Show="No" View="Notes">
        <ShowProjectBookmarks>No</ShowProjectBookmarks>
        <ShowSimilarTexts>No</ShowSimilarTexts>
        <FootnoteNumbers Prompt="No">No</FootnoteNumbers>
    </Inspector>
    <Split>None</Split>
    <BinderAffects>Current</BinderAffects>
    <Labels>
        <Binder FullWidth="No">No</Binder>
        <Icons>No</Icons>
        <IndexCards>No</IndexCards>
        <OutlinerRows>No</OutlinerRows>
        <ScriveningsTitles>No</ScriveningsTitles>
    </Labels>
    <Corkboards>
        <LabelIndicators>Yes</LabelIndicators>
        <Stamps>No</Stamps>
        <Keywords>No</Keywords>
        <Numbers Restart="No">No</Numbers>
        <SnapToGrid>No</SnapToGrid>
        <BlankCardsAsGhosts>No</BlankCardsAsGhosts>
    </Corkboards>
    <Text>
        <ShowFormatBar>Yes</ShowFormatBar>
        <UseVerticalLayout>No</UseVerticalLayout>
        <ShowScriveningsTitles>No</ShowScriveningsTitles>
        <ShowInvisibles>No</ShowInvisibles>
        <RevisionMode>0</RevisionMode>
        <TextChecking>
            <Spelling>Yes</Spelling>
            <Grammar>No</Grammar>
            <SmartQuotes>Yes</SmartQuotes>
            <SmartDashes>Yes</SmartDashes>
        </TextChecking>
    </Text>
    <FullScreen>
        <ShowRuler>No</ShowRuler>
        <PageLayout Facing="No">No</PageLayout>
        <TypewriterScrolling>Yes</TypewriterScrolling>
    </FullScreen>
    <Editors Primary="Editor1" Active="Editor1">
        <Editor1>
            <View>
                <ShowHeader>Yes</ShowHeader>
                <ShowFooter>Yes</ShowFooter>
                <GroupsViewMode>Corkboard</GroupsViewMode>
                <CurrentViewMode>Single</CurrentViewMode>
                <SelectionAffects>Current</SelectionAffects>
                <Content>
                    <ItemID>{first_text_uuid}</ItemID>
                </Content>
                <NavigationHistory CurrentIndex="-1"/>
            </View>
            <Text>
                <ShowRuler>No</ShowRuler>
                <PageLayout Facing="No">No</PageLayout>
                <TypewriterScrolling>No</TypewriterScrolling>
                <LineNumbers Interval="1">No</LineNumbers>
                <Selection>0,0</Selection>
            </Text>
            <Outliner>
                <Columns>
                    <ColID>title</ColID>
                    <ColID>label</ColID>
                    <ColID>status</ColID>
                    <ColID>sectionType</ColID>
                </Columns>
                <TitlesOnly>No</TitlesOnly>
                <HideIcons>No</HideIcons>
                <ShowNumbers>No</ShowNumbers>
                <KeywordsAsChips>Yes</KeywordsAsChips>
                <FixedRowHeights>No</FixedRowHeights>
            </Outliner>
            <Corkboard>
                <CardsAcross>-1</CardsAcross>
                <KeywordChips>5</KeywordChips>
                <SizeCardsToFit>No</SizeCardsToFit>
                <CardHeightRatio>0.6666</CardHeightRatio>
                <SectionsArrangement>Wrap</SectionsArrangement>
                <LabelThreadsUseColumns>No</LabelThreadsUseColumns>
            </Corkboard>
            <Copyholder PreferredOrientation="Vertical" VerticalPos="Right" HorizontalPos="Top">
                <Content></Content>
                <Text>
                    <ShowRuler>No</ShowRuler>
                    <PageLayout Facing="No">No</PageLayout>
                    <TypewriterScrolling>No</TypewriterScrolling>
                    <LineNumbers Interval="1">No</LineNumbers>
                </Text>
            </Copyholder>
        </Editor1>
        <Editor2>
            <View>
                <ShowHeader>Yes</ShowHeader>
                <ShowFooter>Yes</ShowFooter>
                <GroupsViewMode>Corkboard</GroupsViewMode>
                <CurrentViewMode>Single</CurrentViewMode>
                <SelectionAffects>Current</SelectionAffects>
                <Content/>
                <NavigationHistory CurrentIndex="-1"/>
            </View>
            <Text>
                <ShowRuler>No</ShowRuler>
                <PageLayout Facing="No">No</PageLayout>
                <TypewriterScrolling>No</TypewriterScrolling>
                <LineNumbers Interval="1">No</LineNumbers>
                <Selection>0,0</Selection>
            </Text>
            <Outliner>
                <Columns>
                    <ColID>title</ColID>
                    <ColID>label</ColID>
                    <ColID>status</ColID>
                    <ColID>sectionType</ColID>
                </Columns>
                <TitlesOnly>No</TitlesOnly>
                <HideIcons>No</HideIcons>
                <ShowNumbers>No</ShowNumbers>
                <KeywordsAsChips>Yes</KeywordsAsChips>
                <FixedRowHeights>No</FixedRowHeights>
            </Outliner>
            <Corkboard>
                <CardsAcross>-1</CardsAcross>
                <KeywordChips>5</KeywordChips>
                <SizeCardsToFit>No</SizeCardsToFit>
                <CardHeightRatio>0.6666</CardHeightRatio>
                <SectionsArrangement>Wrap</SectionsArrangement>
                <LabelThreadsUseColumns>No</LabelThreadsUseColumns>
            </Corkboard>
            <Copyholder PreferredOrientation="Vertical" VerticalPos="Right" HorizontalPos="Top">
                <Content></Content>
                <Text>
                    <ShowRuler>No</ShowRuler>
                    <PageLayout Facing="No">No</PageLayout>
                    <TypewriterScrolling>No</TypewriterScrolling>
                    <LineNumbers Interval="1">No</LineNumbers>
                </Text>
            </Copyholder>
        </Editor2>
    </Editors>
</UIStates>
'''
    with open(os.path.join(settings_dir, "ui-common.xml"), "w", encoding="utf-8") as f:
        f.write(ui_common_xml)


def _process_textpack_dir(textpack_path, output_folder, log_fn):
    image_extensions = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"}
    os.makedirs(output_folder, exist_ok=True)
    temp_folder = tempfile.mkdtemp()
    count = 0
    try:
        with zipfile.ZipFile(textpack_path, "r") as z:
            z.extractall(temp_folder)
        all_texts = []
        image_folder = None
        for root_dir, dirs, files in os.walk(temp_folder):
            if "text.md" in files:
                with open(os.path.join(root_dir, "text.md"), "r", encoding="utf-8") as f:
                    all_texts.append(f.read())
            for fname in files:
                if os.path.splitext(fname)[1].lower() in image_extensions:
                    image_folder = root_dir
        documents = []
        for text in all_texts:
            documents.extend(_split_markdown(text))
        for title, content in documents:
            out_path = unique_path(output_folder, title, ext=".md")
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(content)
            log_fn(f"  Saved: {os.path.basename(out_path)}")
            count += 1
        if image_folder:
            images_output = os.path.join(output_folder, "images")
            os.makedirs(images_output, exist_ok=True)
            for fname in os.listdir(image_folder):
                if os.path.splitext(fname)[1].lower() in image_extensions:
                    shutil.copy2(
                        os.path.join(image_folder, fname),
                        os.path.join(images_output, fname)
                    )
    finally:
        shutil.rmtree(temp_folder, ignore_errors=True)
    return count


def _process_md_dir(md_path, output_folder, log_fn):
    os.makedirs(output_folder, exist_ok=True)
    with open(md_path, "r", encoding="utf-8") as f:
        text = f.read()
    documents = _split_markdown(text)
    for title, content in documents:
        out_path = unique_path(output_folder, title, ext=".md")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(content)
        log_fn(f"  Saved: {os.path.basename(out_path)}")
    return len(documents)


def _split_markdown(text):
    pattern = re.compile(r"^(# .+)$", re.MULTILINE)
    matches = list(pattern.finditer(text))
    if not matches:
        return [("Untitled", text)]
    documents = []
    for i, match in enumerate(matches):
        title = match.group(1).lstrip("# ").strip()
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        documents.append((title, text[start:end].strip()))
    return documents


# =============================================================================
# Scrivener reader + reverse converters
# =============================================================================

def _rtf_to_paragraphs(rtf_text):
    """
    Parse RTF content and return a list of paragraph strings (plain text).
    Handles Scrivener 3 for Windows RTF format.
    """
    paragraphs = []
    current = []
    i = 0
    n = len(rtf_text)
    depth = 0
    skip_depths = set()

    SKIP_WORDS = frozenset({
        'fonttbl', 'colortbl', 'stylesheet', 'info', 'listtable',
        'listoverridetable', 'rsidtbl', 'generator', 'themedata',
        'colorschememapping', 'shppict', 'nonshppict',
    })

    def skipping():
        return bool(skip_depths)

    while i < n:
        c = rtf_text[i]

        if c == '{':
            depth += 1
            j = i + 1
            while j < n and rtf_text[j] in ' \t\r\n':
                j += 1
            if j < n and rtf_text[j] == '\\':
                if j + 1 < n and rtf_text[j + 1] == '*':
                    skip_depths.add(depth)
                else:
                    k = j + 1
                    while k < n and rtf_text[k].isalpha():
                        k += 1
                    if rtf_text[j + 1:k] in SKIP_WORDS:
                        skip_depths.add(depth)
            i += 1

        elif c == '}':
            skip_depths.discard(depth)
            depth -= 1
            i += 1

        elif c == '\\':
            if i + 1 >= n:
                i += 1
                continue
            nc = rtf_text[i + 1]

            if nc in '\\{}':
                if not skipping():
                    current.append(nc)
                i += 2
            elif nc == "'":
                hex_str = rtf_text[i + 2:i + 4]
                if len(hex_str) == 2:
                    try:
                        byte_val = int(hex_str, 16)
                        if not skipping():
                            current.append(bytes([byte_val]).decode('cp1252', errors='replace'))
                    except ValueError:
                        pass
                i += 4
            elif nc == 'u' and i + 2 < n and (rtf_text[i + 2].isdigit() or rtf_text[i + 2] == '-'):
                j = i + 2
                neg = rtf_text[j] == '-'
                if neg:
                    j += 1
                num_start = j
                while j < n and rtf_text[j].isdigit():
                    j += 1
                if j > num_start:
                    num = int(rtf_text[num_start:j])
                    if neg:
                        num = -num
                    if num < 0:
                        num += 65536
                    if not skipping():
                        try:
                            current.append(chr(num))
                        except (ValueError, OverflowError):
                            current.append('?')
                    if j < n and rtf_text[j:j + 2] == "\\'":
                        j += 4
                    elif j < n and rtf_text[j] not in '\\{}':
                        j += 1
                i = j
            elif nc.isalpha():
                j = i + 1
                while j < n and rtf_text[j].isalpha():
                    j += 1
                word = rtf_text[i + 1:j]
                if j < n and rtf_text[j] == '-':
                    j += 1
                while j < n and rtf_text[j].isdigit():
                    j += 1
                if j < n and rtf_text[j] == ' ':
                    j += 1
                if not skipping():
                    if word == 'par':
                        paragraphs.append(''.join(current).strip())
                        current = []
                    elif word == 'line':
                        current.append('\n')
                    elif word == 'tab':
                        current.append('\t')
                    elif word == 'bullet':
                        current.append('•')
                    elif word == 'endash':
                        current.append('–')
                    elif word == 'emdash':
                        current.append('—')
                    elif word in ('lquote', 'rquote'):
                        current.append('’' if word == 'rquote' else '‘')
                    elif word in ('ldblquote', 'rdblquote'):
                        current.append('”' if word == 'rdblquote' else '“')
                i = j
            else:
                i += 2

        elif c in '\r\n':
            i += 1
        else:
            if not skipping():
                current.append(c)
            i += 1

    if current:
        para = ''.join(current).strip()
        if para:
            paragraphs.append(para)

    return paragraphs


def parse_scriv_binder(scriv_path):
    """
    Parse a Scrivener .scriv folder.
    Returns (project_name, list_of_binder_dicts).
    Each dict: {uuid, type, title, children}.
    """
    scrivx_files = [f for f in os.listdir(scriv_path) if f.endswith('.scrivx')]
    if not scrivx_files:
        raise ValueError(f"No .scrivx file found in: {scriv_path}")
    scrivx_path = os.path.join(scriv_path, scrivx_files[0])
    project_name = scrivx_files[0][:-len('.scrivx')]

    tree = ET.parse(scrivx_path)
    root = tree.getroot()

    def parse_item(elem):
        children = []
        ce = elem.find('Children')
        if ce is not None:
            for child in ce.findall('BinderItem'):
                children.append(parse_item(child))
        return {
            'uuid':     elem.get('UUID', ''),
            'type':     elem.get('Type', 'Text'),
            'title':    elem.findtext('Title', 'Untitled'),
            'children': children,
        }

    binder = root.find('Binder')
    nodes = [parse_item(item) for item in (binder.findall('BinderItem') if binder is not None else [])]
    return project_name, nodes


def _walk_scriv_text_nodes(nodes, path_parts):
    """Recursively yield (path_parts, node) for all Text nodes."""
    for node in nodes:
        ntype = node['type']
        safe_title = sanitize_filename(node['title'])
        if ntype in ('DraftFolder', 'ResearchFolder'):
            yield from _walk_scriv_text_nodes(node['children'], path_parts + [safe_title])
        elif ntype == 'Folder':
            yield from _walk_scriv_text_nodes(node['children'], path_parts + [safe_title])
        elif ntype == 'Text':
            yield path_parts, node


def convert_scriv_to_directory(scriv_path, output_folder, log_fn=print):
    """Extract a Scrivener project to a folder of RTF files."""
    project_name, nodes = parse_scriv_binder(scriv_path)
    data_dir = os.path.join(scriv_path, 'Files', 'Data')
    count = 0
    log_fn(f"  Project: {project_name}")

    for path_parts, node in _walk_scriv_text_nodes(nodes, [sanitize_filename(project_name)]):
        rtf_src = os.path.join(data_dir, node['uuid'], 'content.rtf')
        if not os.path.exists(rtf_src):
            log_fn(f"  Skipped (no content): {node['title']}")
            continue
        dest_dir = os.path.join(output_folder, *path_parts)
        os.makedirs(dest_dir, exist_ok=True)
        dest_path = unique_path(dest_dir, node['title'], ext='.rtf')
        shutil.copy2(rtf_src, dest_path)
        log_fn(f"  Saved: {os.path.relpath(dest_path, output_folder)}")
        count += 1

    log_fn(f"  Done — {count} document(s) saved to: {output_folder}")
    return count


_ULYSSES_MARKUP_XML = """\
    <tag definition="heading1" pattern="#"></tag>
    <tag definition="heading2" pattern="##"></tag>
    <tag definition="heading3" pattern="###"></tag>
    <tag definition="heading4" pattern="####"></tag>
    <tag definition="heading5" pattern="#####"></tag>
    <tag definition="heading6" pattern="######"></tag>
    <tag definition="divider" pattern="----"></tag>
    <tag definition="filename" pattern="@:"></tag>
    <tag definition="blockquote" pattern="&gt;"></tag>
    <tag definition="comment" pattern="%%"></tag>
    <tag definition="orderedList" pattern="\\d."></tag>
    <tag definition="unorderedList" pattern="*"></tag>
    <tag definition="unorderedList" pattern="+"></tag>
    <tag definition="unorderedList" pattern="-"></tag>
    <tag definition="codeblock" pattern="''"></tag>
    <tag definition="codeblock" pattern="``"></tag>
    <tag definition="nativeblock" pattern="~~"></tag>
    <tag definition="code" startPattern="`" endPattern="`"></tag>
    <tag definition="delete" startPattern="||" endPattern="||"></tag>
    <tag definition="emph" startPattern="*" endPattern="*"></tag>
    <tag definition="emph" startPattern="_" endPattern="_"></tag>
    <tag definition="inlineComment" startPattern="++" endPattern="++"></tag>
    <tag definition="inlineNative" startPattern="~" endPattern="~"></tag>
    <tag definition="mark" startPattern="::" endPattern="::"></tag>
    <tag definition="strong" startPattern="**" endPattern="**"></tag>
    <tag definition="strong" startPattern="__" endPattern="__"></tag>
    <tag definition="annotation" startPattern="{" endPattern="}"></tag>
    <tag definition="link" startPattern="[" endPattern="]"></tag>
    <tag definition="footnote" pattern="(fn)"></tag>
    <tag definition="image" pattern="(img)"></tag>
    <tag definition="video" pattern="(vid)"></tag>"""


def _ulysses_sheet_xml(paragraphs):
    def xe(s):
        return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    p_tags = '\n'.join(f'<p>{xe(p)}</p>' if p else '<p></p>' for p in paragraphs) or '<p></p>'
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<sheet version="1" app_version="40" known_version="14">\n'
        '<markup version="1" identifier="markdownxl" displayName="Markdown XL">\n'
        f'{_ULYSSES_MARKUP_XML}\n'
        '</markup>\n'
        '<string xml:space="preserve">\n'
        f'{p_tags}\n'
        '</string>\n'
        '</sheet>'
    )


def _ulysses_plist(display_name):
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"'
        ' "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
        '<plist version="1.0">\n<dict>\n'
        f'    <key>displayName</key>\n    <string>{_xml_escape(display_name)}</string>\n'
        '</dict>\n</plist>'
    )


def convert_scriv_to_ulysses(scriv_path, output_folder, log_fn=print):
    """Convert a Scrivener .scriv project to a Ulysses .ulproj file."""
    project_name, nodes = parse_scriv_binder(scriv_path)
    safe_name = sanitize_filename(project_name)
    data_dir = os.path.join(scriv_path, 'Files', 'Data')

    ulproj_path = os.path.join(output_folder, f"{safe_name}.ulproj")
    counter = 2
    while os.path.exists(ulproj_path):
        ulproj_path = os.path.join(output_folder, f"{safe_name}_{counter}.ulproj")
        counter += 1

    log_fn(f"  Project: {project_name}")
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    proj_prefix = f"{safe_name}-ulproject"
    main_prefix = f"{proj_prefix}/Main-ulgroup"
    count = 0

    with zipfile.ZipFile(ulproj_path, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('Info.plist',
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"'
            ' "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
            '<plist version="1.0">\n<dict/>\n</plist>')
        zf.writestr(f"{proj_prefix}/Info.ulgroup", _ulysses_plist(project_name))
        zf.writestr(f"{main_prefix}/Info.ulgroup", _ulysses_plist('Main'))
        zf.writestr(f"{proj_prefix}/Trash-ultrash/Info.ultrash", _ulysses_plist('Trash'))

        metadata_tpl = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"'
            ' "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
            '<plist version="1.0">\n<dict>\n'
            f'    <key>creationDate</key>\n    <string>{ts}</string>\n'
            f'    <key>modificationDate</key>\n    <string>{ts}</string>\n'
            '</dict>\n</plist>'
        )

        def write_nodes(node_list, parent_prefix):
            nonlocal count
            for node in node_list:
                ntype = node['type']
                if ntype == 'TrashFolder':
                    continue
                if ntype in ('DraftFolder', 'ResearchFolder'):
                    write_nodes(node['children'], parent_prefix)
                elif ntype == 'Folder':
                    grp_id = uuid.uuid4().hex
                    grp_prefix = f"{parent_prefix}/{grp_id}-ulgroup"
                    zf.writestr(f"{grp_prefix}/Info.ulgroup", _ulysses_plist(node['title']))
                    write_nodes(node['children'], grp_prefix)
                elif ntype == 'Text':
                    rtf_src = os.path.join(data_dir, node['uuid'], 'content.rtf')
                    if not os.path.exists(rtf_src):
                        log_fn(f"  Skipped (no content): {node['title']}")
                        continue
                    try:
                        rtf_text = open(rtf_src, 'r', encoding='cp1252', errors='replace').read()
                    except Exception:
                        rtf_text = open(rtf_src, 'r', encoding='utf-8', errors='replace').read()
                    paragraphs = _rtf_to_paragraphs(rtf_text)
                    sheet_id = uuid.uuid4().hex
                    sheet_prefix = f"{parent_prefix}/{sheet_id}.ulysses"
                    zf.writestr(f"{sheet_prefix}/Content.xml", _ulysses_sheet_xml(paragraphs))
                    zf.writestr(f"{sheet_prefix}/Metadata.plist", metadata_tpl)
                    log_fn(f"  Sheet: {node['title']}")
                    count += 1

        write_nodes(nodes, main_prefix)

    log_fn(f"  Done — {count} sheet(s) saved to: {ulproj_path}")
    return count


# =============================================================================
# Worker thread
# =============================================================================

class ConversionWorker(QThread):
    log_line = pyqtSignal(str)
    progress = pyqtSignal(int)
    finished = pyqtSignal(bool, str)

    def __init__(self, input_files, output_folder, mode):
        super().__init__()
        self.input_files = input_files  # list of file paths
        self.output_folder = output_folder
        self.mode = mode  # "directory" or "scrivener"

    def run(self):
        total = len(self.input_files)
        try:
            for idx, fpath in enumerate(self.input_files):
                fname = os.path.basename(fpath)
                self.log_line.emit(f"\n[{idx+1}/{total}] Processing: {fname}")
                self.progress.emit(int((idx / total) * 90))

                if self.mode == "directory":
                    convert_to_directory(fpath, self.output_folder, self.log_line.emit)
                else:
                    convert_to_scrivener(fpath, self.output_folder, self.log_line.emit)

            self.progress.emit(100)
            self.finished.emit(True, self.output_folder)
        except Exception as e:
            self.log_line.emit(f"\n[ERROR] {e}")
            import traceback
            self.log_line.emit(traceback.format_exc())
            self.finished.emit(False, str(e))


class ReverseConversionWorker(QThread):
    log_line = pyqtSignal(str)
    progress = pyqtSignal(int)
    finished = pyqtSignal(bool, str)

    def __init__(self, scriv_path, output_folder, mode):
        super().__init__()
        self.scriv_path = scriv_path
        self.output_folder = output_folder
        self.mode = mode  # "directory" or "ulysses"

    def run(self):
        try:
            self.log_line.emit(f"\nProcessing: {os.path.basename(self.scriv_path)}")
            self.progress.emit(10)
            if self.mode == "directory":
                convert_scriv_to_directory(self.scriv_path, self.output_folder, self.log_line.emit)
            else:
                convert_scriv_to_ulysses(self.scriv_path, self.output_folder, self.log_line.emit)
            self.progress.emit(100)
            self.finished.emit(True, self.output_folder)
        except Exception as e:
            self.log_line.emit(f"\n[ERROR] {e}")
            import traceback
            self.log_line.emit(traceback.format_exc())
            self.finished.emit(False, str(e))


# =============================================================================
# Drag-and-drop file list widget
# =============================================================================

class DropFileList(QListWidget):
    files_dropped = pyqtSignal(list)

    ACCEPTED_EXTENSIONS = {".ulproj", ".textpack", ".md"}

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DropOnly)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setMinimumHeight(120)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        paths = []
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            ext = os.path.splitext(path)[1].lower()
            if ext in self.ACCEPTED_EXTENSIONS:
                paths.append(path)
        if paths:
            self.files_dropped.emit(paths)
        event.acceptProposedAction()

    def get_all_files(self):
        return [self.item(i).data(Qt.UserRole) for i in range(self.count())]


# =============================================================================
# Main window
# =============================================================================

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Ulysses → Scrivener Converter")
        self.setMinimumSize(820, 640)
        self.resize(960, 720)
        self._worker = None
        self._build_ui()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(8)

        tabs = QTabWidget()
        tabs.addTab(self._build_tab1(), "Ulysses → Scrivener")
        tabs.addTab(self._build_tab2(), "Scrivener → Export")
        main_layout.addWidget(tabs, 1)

        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("color: #6c7086; font-size: 11px;")
        main_layout.addWidget(self.status_label)

    def _build_tab1(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 12, 8, 8)
        layout.setSpacing(12)

        sub = QLabel("Convert .ulproj projects to a folder of RTF files or a ready-to-open Scrivener project.")
        sub.setStyleSheet("color: #6c7086; font-size: 12px;")
        sub.setWordWrap(True)
        layout.addWidget(sub)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(6)
        layout.addWidget(splitter, 1)

        # ── Left panel ──
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 6, 0)
        left_layout.setSpacing(12)

        input_group = QGroupBox("Input Files")
        input_v = QVBoxLayout(input_group)
        drop_label = QLabel("Drag & drop .ulproj / .textpack / .md files here\nor use the Browse button below")
        drop_label.setObjectName("dropLabel")
        drop_label.setAlignment(Qt.AlignCenter)
        drop_label.setWordWrap(True)
        drop_label.setMinimumHeight(54)
        input_v.addWidget(drop_label)
        self.file_list = DropFileList()
        self.file_list.files_dropped.connect(self._add_files)
        input_v.addWidget(self.file_list)
        btn_row = QHBoxLayout()
        btn_browse = QPushButton("Browse…")
        btn_browse.clicked.connect(self._browse_files)
        btn_clear = QPushButton("Clear List")
        btn_clear.clicked.connect(self._clear_files)
        btn_remove = QPushButton("Remove Selected")
        btn_remove.clicked.connect(self._remove_selected)
        btn_row.addWidget(btn_browse)
        btn_row.addWidget(btn_remove)
        btn_row.addWidget(btn_clear)
        btn_row.addStretch()
        input_v.addLayout(btn_row)
        left_layout.addWidget(input_group)

        out_group = QGroupBox("Output Folder")
        out_h = QHBoxLayout(out_group)
        self.out_edit = QLineEdit()
        self.out_edit.setPlaceholderText("Choose where to save the output…")
        btn_out = QPushButton("Browse…")
        btn_out.clicked.connect(self._browse_output)
        out_h.addWidget(self.out_edit)
        out_h.addWidget(btn_out)
        left_layout.addWidget(out_group)

        mode_group = QGroupBox("Conversion Mode")
        mode_v = QVBoxLayout(mode_group)
        self.radio_folder = QRadioButton("Extract to folder  —  RTF files in a directory tree")
        self.radio_folder.setChecked(True)
        self.radio_scriv = QRadioButton("Convert to Scrivener project  —  creates a .scriv file (.ulproj only)")
        self._mode_group = QButtonGroup()
        self._mode_group.addButton(self.radio_folder, 0)
        self._mode_group.addButton(self.radio_scriv, 1)
        note = QLabel("Fonts are fixed automatically (Georgia 16pt) on all RTF output.")
        note.setStyleSheet("color: #a6e3a1; font-size: 11px; margin-top: 4px;")
        note.setWordWrap(True)
        mode_v.addWidget(self.radio_folder)
        mode_v.addWidget(self.radio_scriv)
        mode_v.addWidget(note)
        left_layout.addWidget(mode_group)

        left_layout.addStretch()
        self.btn_convert = QPushButton("Convert")
        self.btn_convert.setObjectName("convertBtn")
        self.btn_convert.clicked.connect(self._start_conversion)
        left_layout.addWidget(self.btn_convert)
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        left_layout.addWidget(self.progress_bar)
        splitter.addWidget(left_panel)

        # ── Right panel: log ──
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(6, 0, 0, 0)
        right_layout.setSpacing(4)
        log_header = QHBoxLayout()
        log_label = QLabel("Log")
        log_label.setStyleSheet("font-weight: bold; color: #89b4fa;")
        btn_clear_log = QPushButton("Clear")
        btn_clear_log.setFixedWidth(60)
        btn_clear_log.clicked.connect(self._clear_log)
        log_header.addWidget(log_label)
        log_header.addStretch()
        log_header.addWidget(btn_clear_log)
        right_layout.addLayout(log_header)
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setLineWrapMode(QTextEdit.NoWrap)
        right_layout.addWidget(self.log_area, 1)
        splitter.addWidget(right_panel)
        splitter.setSizes([440, 480])

        return tab

    def _build_tab2(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 12, 8, 8)
        layout.setSpacing(12)

        sub = QLabel("Extract a Scrivener .scriv project to a folder of RTF files, preserving the binder structure.")
        sub.setStyleSheet("color: #6c7086; font-size: 12px;")
        sub.setWordWrap(True)
        layout.addWidget(sub)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(6)
        layout.addWidget(splitter, 1)

        # ── Left panel ──
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 6, 0)
        left_layout.setSpacing(12)

        in_group = QGroupBox("Input Project (.scriv folder)")
        in_h = QHBoxLayout(in_group)
        self.rev_scriv_edit = QLineEdit()
        self.rev_scriv_edit.setPlaceholderText("Select a .scriv folder…")
        btn_in = QPushButton("Browse…")
        btn_in.clicked.connect(self._rev_browse_scriv)
        in_h.addWidget(self.rev_scriv_edit)
        in_h.addWidget(btn_in)
        left_layout.addWidget(in_group)

        out_group = QGroupBox("Output Folder")
        out_h = QHBoxLayout(out_group)
        self.rev_out_edit = QLineEdit()
        self.rev_out_edit.setPlaceholderText("Choose where to save the output…")
        btn_out = QPushButton("Browse…")
        btn_out.clicked.connect(self._rev_browse_output)
        out_h.addWidget(self.rev_out_edit)
        out_h.addWidget(btn_out)
        left_layout.addWidget(out_group)

        left_layout.addStretch()
        self.rev_btn_convert = QPushButton("Extract to RTF Directory")
        self.rev_btn_convert.setObjectName("convertBtn")
        self.rev_btn_convert.clicked.connect(self._rev_start_conversion)
        left_layout.addWidget(self.rev_btn_convert)
        self.rev_progress_bar = QProgressBar()
        self.rev_progress_bar.setValue(0)
        self.rev_progress_bar.setVisible(False)
        left_layout.addWidget(self.rev_progress_bar)
        splitter.addWidget(left_panel)

        # ── Right panel: log ──
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(6, 0, 0, 0)
        right_layout.setSpacing(4)
        log_header = QHBoxLayout()
        log_label = QLabel("Log")
        log_label.setStyleSheet("font-weight: bold; color: #89b4fa;")
        btn_clear_log = QPushButton("Clear")
        btn_clear_log.setFixedWidth(60)
        btn_clear_log.clicked.connect(lambda: self.rev_log_area.clear())
        log_header.addWidget(log_label)
        log_header.addStretch()
        log_header.addWidget(btn_clear_log)
        right_layout.addLayout(log_header)
        self.rev_log_area = QTextEdit()
        self.rev_log_area.setReadOnly(True)
        self.rev_log_area.setLineWrapMode(QTextEdit.NoWrap)
        right_layout.addWidget(self.rev_log_area, 1)
        splitter.addWidget(right_panel)
        splitter.setSizes([440, 480])

        return tab

    # ── File management ──

    def _add_files(self, paths):
        existing = set(self.file_list.get_all_files())
        for path in paths:
            if path not in existing:
                item = QListWidgetItem(os.path.basename(path))
                item.setData(Qt.UserRole, path)
                item.setToolTip(path)
                self.file_list.addItem(item)
                existing.add(path)
        self._update_status()

    def _browse_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Select Ulysses Files", "",
            "Ulysses Files (*.ulproj *.textpack *.md);;All Files (*)"
        )
        if paths:
            self._add_files(paths)

    def _remove_selected(self):
        for item in self.file_list.selectedItems():
            self.file_list.takeItem(self.file_list.row(item))
        self._update_status()

    def _clear_files(self):
        self.file_list.clear()
        self._update_status()

    def _browse_output(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Output Folder")
        if folder:
            self.out_edit.setText(folder)

    def _update_status(self):
        n = self.file_list.count()
        self.status_label.setText(
            f"{n} file(s) queued" if n else "Ready"
        )

    def _clear_log(self):
        self.log_area.clear()

    # ── Conversion ──

    def _start_conversion(self):
        files = self.file_list.get_all_files()
        output_folder = self.out_edit.text().strip()

        if not files:
            QMessageBox.warning(self, "No Files", "Please add at least one file to convert.")
            return
        if not output_folder:
            QMessageBox.warning(self, "No Output Folder", "Please choose an output folder.")
            return
        if not os.path.isdir(output_folder):
            try:
                os.makedirs(output_folder, exist_ok=True)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Could not create output folder:\n{e}")
                return

        mode = "scrivener" if self.radio_scriv.isChecked() else "directory"

        # Warn if non-ulproj chosen with Scrivener mode
        if mode == "scrivener":
            bad = [f for f in files if not f.endswith(".ulproj")]
            if bad:
                QMessageBox.warning(
                    self, "Unsupported Files",
                    "Scrivener output is only supported for .ulproj files.\n"
                    f"The following will be skipped:\n" + "\n".join(os.path.basename(b) for b in bad)
                )
                files = [f for f in files if f.endswith(".ulproj")]
                if not files:
                    return

        self.btn_convert.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.log_area.append(f"=== Starting conversion ({mode} mode) ===")

        self._worker = ConversionWorker(files, output_folder, mode)
        self._worker.log_line.connect(self._on_log)
        self._worker.progress.connect(self.progress_bar.setValue)
        self._worker.finished.connect(self._on_finished)
        self._worker.start()

    def _on_log(self, line):
        self.log_area.append(line)
        sb = self.log_area.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_finished(self, success, message):
        self.btn_convert.setEnabled(True)
        self.progress_bar.setVisible(False)
        if success:
            self.log_area.append(f"\n=== Conversion complete ===")
            self.status_label.setText(f"Done — output in: {message}")
            QMessageBox.information(
                self, "Done",
                f"Conversion complete!\n\nOutput saved to:\n{message}"
            )
        else:
            self.log_area.append(f"\n=== Conversion failed ===")
            self.status_label.setText("Conversion failed — see log")

    # ── Tab 2: Scrivener → Export ──

    def _rev_browse_scriv(self):
        folder = QFileDialog.getExistingDirectory(self, "Select .scriv Folder")
        if folder:
            self.rev_scriv_edit.setText(folder)

    def _rev_browse_output(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Output Folder")
        if folder:
            self.rev_out_edit.setText(folder)

    def _rev_start_conversion(self):
        scriv_path = self.rev_scriv_edit.text().strip()
        output_folder = self.rev_out_edit.text().strip()

        if not scriv_path:
            QMessageBox.warning(self, "No Input", "Please select a .scriv folder.")
            return
        if not os.path.isdir(scriv_path):
            QMessageBox.warning(self, "Not Found", f"Folder not found:\n{scriv_path}")
            return
        if not any(f.endswith('.scrivx') for f in os.listdir(scriv_path)):
            QMessageBox.warning(self, "Not a Scrivener Project",
                                "No .scrivx file found in the selected folder.\n"
                                "Please select a .scriv project folder.")
            return
        if not output_folder:
            QMessageBox.warning(self, "No Output Folder", "Please choose an output folder.")
            return
        try:
            os.makedirs(output_folder, exist_ok=True)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not create output folder:\n{e}")
            return

        self.rev_btn_convert.setEnabled(False)
        self.rev_progress_bar.setVisible(True)
        self.rev_progress_bar.setValue(0)
        self.rev_log_area.append("=== Extracting to RTF directory ===")

        self._rev_worker = ReverseConversionWorker(scriv_path, output_folder, "directory")
        self._rev_worker.log_line.connect(self._rev_on_log)
        self._rev_worker.progress.connect(self.rev_progress_bar.setValue)
        self._rev_worker.finished.connect(self._rev_on_finished)
        self._rev_worker.start()

    def _rev_on_log(self, line):
        self.rev_log_area.append(line)
        self.rev_log_area.verticalScrollBar().setValue(
            self.rev_log_area.verticalScrollBar().maximum()
        )

    def _rev_on_finished(self, success, message):
        self.rev_btn_convert.setEnabled(True)
        self.rev_progress_bar.setVisible(False)
        if success:
            self.rev_log_area.append(f"\n=== Export complete ===")
            self.status_label.setText(f"Done — output in: {message}")
            QMessageBox.information(
                self, "Done",
                f"Export complete!\n\nOutput saved to:\n{message}"
            )
        else:
            self.rev_log_area.append(f"\n=== Export failed ===")
            self.status_label.setText("Export failed — see log")


# =============================================================================
# Entry point
# =============================================================================

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
