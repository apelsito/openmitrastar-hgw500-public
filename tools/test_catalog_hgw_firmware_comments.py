"""Meaningful synthetic lexical/byte preservation and HTML injection tests."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from catalog_hgw_firmware_comments import catalog, scan_comments


class CommentCatalogTests(unittest.TestCase):
    def test_quotes_escapes_raw_strings_and_comments(self):
        source = b'const char *url="https://example.test/* no */";\nchar q=\'"\';\nchar slash=\'/\'; /* yes */\nconst char *s="escaped \\\" // no";\nconst char *r=R"tag(//no /*no*/ ")tag"; // yes2\n'
        spans = scan_comments(source)
        self.assertEqual([source[s["offset"]:s["end_offset"]] for s in spans], [b"/* yes */", b"// yes2"])
        self.assertEqual([s["line"] for s in spans], [3, 5])

    def test_spliced_delimiters_and_crlf(self):
        source = b'/\\\r\n/ joined\\\r\n comment\r\n/\\\n* block *\\\n/\n'
        spans = scan_comments(source)
        self.assertEqual([source[s["offset"]:s["end_offset"]] for s in spans], [b'/\\\r\n/ joined\\\r\n comment', b'/\\\n* block *\\\n/'])
        self.assertEqual([(s["line"], s["end_line"]) for s in spans], [(1, 3), (4, 6)])

    def test_non_utf8_and_unterminated(self):
        source = b'// \xff\n/* unfinished\r\n'
        spans = scan_comments(source)
        self.assertTrue(spans[0]["terminated"])
        self.assertFalse(spans[1]["terminated"])
        self.assertEqual(spans[1]["end_offset"], len(source))

    def test_adjacent_empty_comments_and_eof(self):
        source = b'/**//*x*///tail'
        spans = scan_comments(source)
        self.assertEqual([s["bytes"] for s in spans], [4, 5, 6])

    def test_block_trailing_splice_and_cpp_digit_separator(self):
        source = b"int count=1'000; /*exact*/\\\n int next=2; //tail\n"
        spans = scan_comments(source)
        self.assertEqual([source[s["offset"]:s["end_offset"]] for s in spans], [b"/*exact*/", b"//tail"])

    def test_prefixed_character_is_not_numeric_separator(self):
        source = b"wchar_t c=L'a'; //wide\nint hex=0xA'B; //hex\nchar16_t d=u'z'; /*utf*/\n"
        spans = scan_comments(source)
        self.assertEqual([source[s["offset"]:s["end_offset"]] for s in spans], [b"//wide", b"//hex", b"/*utf*/"])

    def test_catalog_exact_bytes_safe_page_and_immutable_output(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            src = root / "src"
            src.mkdir()
            source = b'// </pre></article><script>evil()</script>\r\n/* espa\xf1ol ``` */\n'
            (src / "one.c").write_bytes(source)
            (src / "binary.bin").write_bytes(b"// not scanned")
            before = hashlib.sha256(source).hexdigest()
            output = root / "evidence"
            summary = catalog(root, [src], output)
            self.assertEqual(summary["comment_count"], 2)
            self.assertEqual(summary["file_count"], 2)
            records = json.loads((output / "comments.json").read_text(encoding="utf-8"))["comments"]
            stream = (output / "comments.raw.bin").read_bytes()
            for record in records:
                raw = source[record["offset"]:record["end_offset"]]
                self.assertEqual(stream[record["raw_stream_offset"]:record["raw_stream_offset"] + record["bytes"]], raw)
                self.assertEqual(hashlib.sha256(raw).hexdigest(), record["sha256"])
            page = (output / "index.html").read_text(encoding="utf-8")
            self.assertNotIn("<script>evil()</script>", page)
            self.assertIn("&lt;script&gt;evil()&lt;/script&gt;", page)
            self.assertEqual(page.count("<script>"), 1)
            self.assertEqual(hashlib.sha256((src / "one.c").read_bytes()).hexdigest(), before)
            with self.assertRaises(FileExistsError):
                catalog(root, [src], output)

    def test_output_cannot_be_inside_source(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            src = root / "src"
            src.mkdir()
            with self.assertRaises(ValueError):
                catalog(root, [src], src / "output")


if __name__ == "__main__":
    unittest.main()
