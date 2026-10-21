"""Bounded replay of exact text quotations from original source bytes.

This offline adapter does not infer settlement meanings or grant source rights.
JSON-pointer evidence remains a separate, unchanged contract. Text evidence uses
an explicit version, media type, extraction algorithm and UTF-8 byte offsets.
The caller must establish the source format; there is no content sniffing.

``html-static-text-v1`` accepts a conservatively nested HTML document/fragment,
excludes comments, head and executable/embedded/template content, inserts spaces
at block boundaries, decodes HTML character references, and collapses only ASCII
whitespace and NBSP. It does not claim browser visibility, evaluate CSS/JavaScript,
or fetch resources. Malformed/unsupported markup fails instead of guessing.
``utf8-text-v1`` preserves the supplied UTF-8 bytes exactly.

Derived text is never substituted for the original retained response: both its
original hash/length and the derived-text hash/length are independently replayed.
"""
from __future__ import annotations

import hashlib
from html.parser import HTMLParser
import re

from .integrity import IntegrityError, canonical

TEXT_REPLAY_SCHEMA = "source-evidence-text-v1"
MAX_RAW_BYTES = 2 * 1024 * 1024
MAX_TEXT_BYTES = 512 * 1024
MAX_QUOTE_BYTES = 4096
MAX_HTML_NODES = 65536
MAX_HTML_DEPTH = 128
EXTRACTORS = {"text/html": "html-static-text-v1", "text/plain": "utf8-text-v1"}
REPLAY_FIELDS = {"schema_version", "media_type", "encoding", "extractor", "text_sha256", "text_bytes"}
BINDING_FIELDS = {"start", "end", "source_value", "meaning"}
_SHA = re.compile(r"[a-f0-9]{64}\Z")
_SPACE = re.compile(r"[ \t\r\n\f\v\u00a0]+")
_VOID = frozenset("area base br col embed hr img input link meta param source track wbr".split())
_EXCLUDED = frozenset("head script style template noscript iframe object svg math textarea".split())
_BLOCK = frozenset("address article aside blockquote br caption dd details dialog div dl dt fieldset "
                   "figcaption figure footer form h1 h2 h3 h4 h5 h6 header hgroup hr li main nav ol p "
                   "pre section summary table tbody td tfoot th thead tr ul".split())


def _require(condition, message):
    if not condition:
        raise IntegrityError(message)


def _utf8(raw):
    _require(type(raw) is bytes and 0 < len(raw) <= MAX_RAW_BYTES, "Invalid bounded original text-source bytes")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise IntegrityError("Text source must be valid UTF-8") from error
    _require(not text.startswith("\ufeff"), "UTF-8 BOM is unsupported by this extractor version")
    _require(not any(ord(c) < 32 and c not in "\t\r\n\f" for c in text), "Unsupported text-source control character")
    return text


class _StaticText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.parts = []
        self.part_bytes = 0
        self.nodes = 0

    def _node(self):
        self.nodes += 1
        _require(self.nodes <= MAX_HTML_NODES, "HTML source exceeds extraction node limit")

    def _write(self, text):
        if not any(hidden for _, hidden in self.stack):
            self.part_bytes += len(text.encode("utf-8"))
            _require(self.part_bytes <= MAX_TEXT_BYTES, "HTML source exceeds extracted-text limit")
            self.parts.append(text)

    def handle_starttag(self, tag, attrs):
        self._node()
        names = [name for name, _ in attrs]
        _require(len(names) == len(set(names)), "Duplicate HTML attributes are ambiguous")
        values = dict(attrs)
        if tag == "meta":
            charset = values.get("charset")
            if charset is not None:
                _require(charset.lower() in {"utf-8", "utf8"}, "HTML declares an unsupported encoding")
            if (values.get("http-equiv") or "").lower() == "content-type":
                content = values.get("content") or ""
                match = re.search(r"charset\s*=\s*[\"']?([^\s;\"']+)", content, re.I)
                _require(match is None or match.group(1).lower() in {"utf-8", "utf8"}, "HTML declares an unsupported encoding")
        if tag in _BLOCK:
            self._write(" ")
        if tag not in _VOID:
            hidden = tag in _EXCLUDED or "hidden" in values or (values.get("aria-hidden") or "").lower() == "true"
            self.stack.append((tag, hidden))
            _require(len(self.stack) <= MAX_HTML_DEPTH, "HTML source exceeds nesting limit")

    def handle_startendtag(self, tag, attrs):
        _require(tag in _VOID, "Unsupported self-closing non-void HTML element")
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        self._node()
        _require(bool(self.stack) and self.stack[-1][0] == tag, "Unbalanced or implicitly closed HTML is unsupported")
        self.stack.pop()
        if tag in _BLOCK:
            self._write(" ")

    def handle_data(self, data):
        self._node()
        self._write(data)

    def handle_comment(self, data):
        self._node()

    def handle_decl(self, decl):
        self._node()
        _require(decl.lower() == "doctype html", "Unsupported HTML declaration")

    def handle_pi(self, data):
        raise IntegrityError("HTML processing instructions are unsupported")

    def unknown_decl(self, data):
        raise IntegrityError("Unknown HTML declaration")

    def result(self):
        self.close()
        _require(not self.stack, "Unclosed HTML element")
        return _SPACE.sub(" ", "".join(self.parts)).strip().encode("utf-8")


def extract_source_text(raw, media_type):
    """Return deterministic UTF-8 text bytes, without changing retained raw bytes."""
    _require(type(media_type) is str and media_type in EXTRACTORS, "Unsupported explicit source media type")
    decoded = _utf8(raw)
    if media_type == "text/plain":
        result = raw
    else:
        parser = _StaticText()
        try:
            parser.feed(decoded)
            result = parser.result()
        except IntegrityError:
            raise
        except (ValueError, RecursionError) as error:
            raise IntegrityError("Unsupported HTML source") from error
    _require(0 < len(result) <= MAX_TEXT_BYTES, "Empty or unbounded extracted source text")
    return result


def make_text_replay(raw, media_type):
    """Describe extraction only; no evidence/admission/settlement status is granted."""
    text = extract_source_text(raw, media_type)
    return {"schema_version": TEXT_REPLAY_SCHEMA, "media_type": media_type, "encoding": "utf-8",
            "extractor": EXTRACTORS[media_type], "text_sha256": hashlib.sha256(text).hexdigest(),
            "text_bytes": len(text)}


def validate_text_replay(replay):
    _require(type(replay) is dict and set(replay) == REPLAY_FIELDS, "Invalid text replay descriptor fields")
    _require(replay["schema_version"] == TEXT_REPLAY_SCHEMA and replay["encoding"] == "utf-8"
             and type(replay["media_type"]) is str and replay["media_type"] in EXTRACTORS
             and replay["extractor"] == EXTRACTORS[replay["media_type"]], "Unsupported text replay version or format")
    _require(type(replay["text_sha256"]) is str and _SHA.fullmatch(replay["text_sha256"]) is not None,
             "Invalid extracted-text hash")
    _require(type(replay["text_bytes"]) is int and 0 < replay["text_bytes"] <= MAX_TEXT_BYTES,
             "Invalid extracted-text byte count")
    return replay


def validate_text_binding(binding, replay):
    """Validate a half-open UTF-8 byte span; backend replay proves its quotation."""
    validate_text_replay(replay)
    _require(type(binding) is dict and set(binding) == BINDING_FIELDS, "Invalid text source binding fields")
    start, end = binding["start"], binding["end"]
    _require(type(start) is int and type(end) is int and 0 <= start < end <= replay["text_bytes"],
             "Invalid text source byte span")
    _require(type(binding["source_value"]) is str and bool(binding["source_value"]), "An exact source quotation is required")
    try:
        quote = binding["source_value"].encode("utf-8")
    except UnicodeEncodeError as error:
        raise IntegrityError("Invalid UTF-8 source quotation") from error
    _require(len(quote) == end - start and len(quote) <= MAX_QUOTE_BYTES, "Quotation and byte span disagree")
    canonical(binding["meaning"])
    return binding


def replay_text_evidence(raw, evidence):
    """Replay RULES quotations from exact original bytes before trusting mappings.

    The caller still validates complete offer identity, normalized meanings,
    source clocks, registry admission and retention metadata independently.
    """
    _require(type(evidence) is dict and evidence.get("kind") == "RULES", "Text replay is restricted to RULES evidence")
    replay = evidence.get("text_replay")
    validate_text_replay(replay)
    _require(type(raw) is bytes and 0 < len(raw) <= MAX_RAW_BYTES, "Invalid bounded original text-source bytes")
    _require(type(evidence.get("raw_bytes")) is int and evidence["raw_bytes"] == len(raw)
             and evidence.get("raw_sha256") == hashlib.sha256(raw).hexdigest(), "Original source byte identity mismatch")
    text = extract_source_text(raw, replay["media_type"])
    _require(len(text) == replay["text_bytes"] and hashlib.sha256(text).hexdigest() == replay["text_sha256"],
             "Extracted text does not match the reviewed descriptor")
    bindings = evidence.get("bindings")
    _require(type(bindings) is dict and bool(bindings) and len(bindings) <= 64, "Bounded text source bindings required")
    for binding in bindings.values():
        validate_text_binding(binding, replay)
        _require(text[binding["start"]:binding["end"]] == binding["source_value"].encode("utf-8"),
                 "Retained source quotation contradicts its binding")
    return text
