"""Offline synthetic source replay checks; no provider requests or admission."""
from copy import deepcopy
import hashlib
import unittest
from unittest.mock import patch

from multisport_lab.integrity import IntegrityError
from multisport_lab import source_evidence as source


def evidence(raw, media_type, quotation):
    text = source.extract_source_text(raw, media_type)
    quote = quotation.encode("utf-8")
    start = text.index(quote)
    return {"kind": "RULES", "raw_bytes": len(raw), "raw_sha256": hashlib.sha256(raw).hexdigest(),
            "text_replay": source.make_text_replay(raw, media_type),
            "bindings": {"settlement_terms.dnp": {"start": start, "end": start + len(quote),
                         "source_value": quotation, "meaning": "Synthetic reviewed DNP meaning."}}}


class SourceEvidenceTests(unittest.TestCase):
    def test_html_quote_replays_original_bytes_without_a_json_summary(self):
        raw = (b'<!DOCTYPE html><html><head><title>Not body rules</title><style>voids all</style></head>'
               b'<body><h1>Synthetic Rules</h1><p>No appearance <b>voids</b> this selection.</p>'
               b'<script>document.write("wins")</script><!-- pays every entry -->'
               b'<template>always wins</template><p>Pushes&nbsp;&amp; ties return stakes.</p></body></html>')
        item = evidence(raw, "text/html", "No appearance voids this selection.")
        actual = source.replay_text_evidence(raw, item)
        self.assertEqual(actual, b'Synthetic Rules No appearance voids this selection. Pushes & ties return stakes.')
        self.assertNotEqual(item["raw_sha256"], item["text_replay"]["text_sha256"])
        self.assertEqual(source.make_text_replay(raw, "text/html"), item["text_replay"])

    def test_plain_text_preserves_crlf_and_unicode_byte_offsets(self):
        raw = "Synthetic café rules:\r\nNo appearance voids.\r\n".encode("utf-8")
        item = evidence(raw, "text/plain", "No appearance voids.")
        self.assertEqual(source.replay_text_evidence(raw, item), raw)
        binding = item["bindings"]["settlement_terms.dnp"]
        self.assertEqual(binding["start"], len("Synthetic café rules:\r\n".encode("utf-8")))
        unicode_item = evidence(raw, "text/plain", "café")
        self.assertEqual(source.replay_text_evidence(raw, unicode_item), raw)
        bad = deepcopy(unicode_item)
        bad["bindings"]["settlement_terms.dnp"]["start"] += 1
        bad["bindings"]["settlement_terms.dnp"]["end"] += 1
        with self.assertRaisesRegex(IntegrityError, "quotation contradicts"):
            source.replay_text_evidence(raw, bad)

    def test_original_hash_and_length_reject_equivalent_visible_markup(self):
        raw = b"<p>No appearance voids.</p>"
        item = evidence(raw, "text/html", "No appearance voids.")
        changed = b"<div>No appearance voids.</div>"
        self.assertEqual(source.extract_source_text(raw, "text/html"), source.extract_source_text(changed, "text/html"))
        for invalid in (changed, raw + b"\n"):
            with self.assertRaisesRegex(IntegrityError, "Original source byte identity"):
                source.replay_text_evidence(invalid, item)
        bad = deepcopy(item); bad["raw_bytes"] = True
        with self.assertRaises(IntegrityError):
            source.replay_text_evidence(raw, bad)

    def test_text_hash_and_quote_must_both_replay(self):
        raw = b"No appearance voids. An appearance qualifies."
        item = evidence(raw, "text/plain", "No appearance voids.")
        bad = deepcopy(item); bad["text_replay"]["text_sha256"] = "0" * 64
        with self.assertRaisesRegex(IntegrityError, "reviewed descriptor"):
            source.replay_text_evidence(raw, bad)
        bad = deepcopy(item)
        bad["bindings"]["settlement_terms.dnp"]["source_value"] = "No appearance wins!."
        with self.assertRaises(IntegrityError):
            source.replay_text_evidence(raw, bad)
        bad = deepcopy(item)
        bad["bindings"]["settlement_terms.dnp"].update(start=1, end=21)
        with self.assertRaises(IntegrityError):
            source.replay_text_evidence(raw, bad)

    def test_format_is_explicit_versioned_and_only_for_rules(self):
        raw = b"No appearance voids."
        item = evidence(raw, "text/plain", "No appearance voids.")
        for key, value in (("schema_version", "future-version"), ("media_type", "application/json"),
                           ("encoding", "latin-1"), ("extractor", "html-static-text-v1"),
                           ("text_bytes", True), ("text_bytes", 0)):
            bad = deepcopy(item); bad["text_replay"][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(IntegrityError):
                source.replay_text_evidence(raw, bad)
        for kind in ("CONTRACT_VIEW", "PLAYER_IDENTITY"):
            bad = deepcopy(item); bad["kind"] = kind
            with self.assertRaisesRegex(IntegrityError, "restricted to RULES"):
                source.replay_text_evidence(raw, bad)
        bad = deepcopy(item); bad["text_replay"]["normalized_source_json"] = {}
        with self.assertRaises(IntegrityError):
            source.replay_text_evidence(raw, bad)

    def test_html_exclusions_boundaries_and_unsupported_markup(self):
        raw = (b'<main><p>Full <b>game</b> only.</p><div hidden>fake payout</div>'
               b'<span aria-hidden="true">hidden auxiliary text</span><p>Includes overtime.</p></main>')
        self.assertEqual(source.extract_source_text(raw, "text/html"), b"Full game only. Includes overtime.")
        invalid = (b"<p>Rules", b"<p><b>Rules</p></b>", b"<div/>Rules", b"<script/>Rules",
                   b'<p id="x" id="y">Rules</p>', b'<meta charset="latin-1"><p>Rules</p>',
                   b'<meta http-equiv="content-type" content="text/html; charset=windows-1252"><p>Rules</p>',
                   b'<?xml version="1.0"?><p>Rules</p>', b"<script>secret rules</script>")
        for body in invalid:
            with self.subTest(body=body), self.assertRaises(IntegrityError):
                source.extract_source_text(body, "text/html")

    def test_byte_node_depth_and_quote_limits_fail_closed(self):
        with self.assertRaises(IntegrityError):
            source.extract_source_text(b"x" * (source.MAX_RAW_BYTES + 1), "text/plain")
        with patch.object(source, "MAX_TEXT_BYTES", 8), self.assertRaises(IntegrityError):
            source.extract_source_text(b"<p>Too many characters.</p>", "text/html")
        with patch.object(source, "MAX_HTML_NODES", 3), self.assertRaises(IntegrityError):
            source.extract_source_text(b"<p>One</p><p>Two</p>", "text/html")
        with patch.object(source, "MAX_HTML_DEPTH", 2), self.assertRaises(IntegrityError):
            source.extract_source_text(b"<div><section><p>Deep</p></section></div>", "text/html")
        raw = b"x" * (source.MAX_QUOTE_BYTES + 1)
        item = evidence(raw, "text/plain", raw.decode())
        with self.assertRaises(IntegrityError):
            source.replay_text_evidence(raw, item)

    def test_invalid_encoding_controls_and_mixed_binding_shapes_fail(self):
        for raw in (b"", b"\xff", b"\xef\xbb\xbfRules", b"Rules\x00void"):
            for media in ("text/html", "text/plain"):
                with self.subTest(raw=raw, media=media), self.assertRaises(IntegrityError):
                    source.extract_source_text(raw, media)
        raw = b"No appearance voids."
        item = evidence(raw, "text/plain", "No appearance voids.")
        for mutation in (lambda b: b.update(pointer="/rules"), lambda b: b.update(start=True),
                         lambda b: b.update(end=-1), lambda b: b.update(source_value="\ud800")):
            bad = deepcopy(item); mutation(bad["bindings"]["settlement_terms.dnp"])
            with self.assertRaises(IntegrityError):
                source.replay_text_evidence(raw, bad)


if __name__ == "__main__":
    unittest.main()
