"""Catalog exact C/C++ comment bytes in explicitly selected local source trees.

Source files are never changed or copied. The raw comment stream is authoritative;
Markdown and an escaped, searchable local HTML page are decoded views. No network,
device or firmware action occurs. Python standard library only.
"""
from __future__ import annotations

import argparse
from bisect import bisect_right
from datetime import datetime, timezone
import hashlib
import html
import json
from pathlib import Path
import re

SOURCE_SUFFIXES = {".c", ".h", ".cc", ".cpp", ".cxx", ".hpp", ".hh", ".hxx", ".inc", ".inl"}


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def logical_bytes(raw: bytes) -> tuple[bytes, list[int]]:
    """Apply C backslash-newline splicing while retaining physical byte offsets."""
    data = bytearray()
    offsets = []
    i = 0
    while i < len(raw):
        if raw[i] == 92:
            if raw[i + 1:i + 2] == b"\n":
                i += 2
                continue
            if raw[i + 1:i + 3] == b"\r\n":
                i += 3
                continue
        data.append(raw[i])
        offsets.append(i)
        i += 1
    return bytes(data), offsets


def scan_comments(raw: bytes) -> list[dict]:
    """Find // and /* */ outside C strings/chars and C++ raw string literals.

    Offset/end_offset use original bytes, zero-based and end-exclusive. Line
    continuations can form a delimiter or continue a // comment; its exact
    physical region is retained. All preprocessor branches are scanned.
    """
    data, offsets = logical_bytes(raw)
    newlines = [i for i, value in enumerate(raw) if value == 10]
    result = []
    i = 0
    while i < len(data):
        start = i
        kind = None
        terminated = True
        if data[i:i + 2] == b"//":
            kind = "line"
            end = data.find(b"\n", i + 2)
            i = len(data) if end < 0 else end
            # Exclude a physical CRLF terminator from the exact comment bytes.
            if end >= 0 and i > start and data[i - 1] == 13:
                i -= 1
        elif data[i:i + 2] == b"/*":
            kind = "block"
            end = data.find(b"*/", i + 2)
            terminated = end >= 0
            i = len(data) if end < 0 else end + 2
        elif data[i:i + 2] == b'R"':
            # C++ raw delimiters contain no whitespace, parentheses or slash
            # escape and are at most16characters. Prefixes u8/u/U/L need no
            # separate handling because the R itself is reached in normal state.
            opening = data.find(b"(", i + 2, min(len(data), i + 19))
            delimiter = data[i + 2:opening] if opening >= 0 else b""
            valid = opening >= 0 and not any(v in b" \t\r\n\v\f()\\" for v in delimiter)
            if valid:
                closing = data.find(b")" + delimiter + b'"', opening + 1)
                i = len(data) if closing < 0 else closing + len(delimiter) + 2
                continue
            i += 1
            continue
        elif data[i] == 39 and is_numeric_separator(data, i):
            # C++ numeric digit separator (including hexadecimal literals).
            i += 1
            continue
        elif data[i] in (34, 39):
            quote = data[i]
            i += 1
            while i < len(data):
                if data[i] == 92:
                    i += 2
                elif data[i] == quote:
                    i += 1
                    break
                elif data[i] in (10, 13):
                    # Malformed C literal: do not swallow later source lines.
                    break
                else:
                    i += 1
            continue
        else:
            i += 1
            continue
        if kind is not None:
            physical_start = offsets[start]
            physical_end = (offsets[i - 1] + 1) if kind == "block" and terminated else (offsets[i] if i < len(offsets) else len(raw))
            comment = raw[physical_start:physical_end]
            result.append({"kind": kind, "offset": physical_start,
                           "end_offset": physical_end,
                           "line": bisect_right(newlines, physical_start) + 1,
                           "end_line": bisect_right(newlines, max(physical_start, physical_end - 1)) + 1,
                           "bytes": len(comment), "sha256": sha(comment),
                           "terminated": terminated})
            if i < len(data) and data[i] == 13:
                i += 1
    return result


def is_numeric_separator(data: bytes, index: int) -> bool:
    if index < 1 or index + 1 >= len(data) or not chr(data[index + 1]).isalnum():
        return False
    start = index - 1
    while start >= 0 and (chr(data[start]).isalnum() or data[start] in b"_.'"):
        start -= 1
    return start + 1 < index and 48 <= data[start + 1] <= 57


def decode(raw: bytes) -> tuple[str, str]:
    try:
        return raw.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        try:
            return raw.decode("cp1252"), "cp1252"
        except UnicodeDecodeError:
            return raw.decode("latin-1"), "latin-1"


def markdown_code(text: str) -> str:
    runs = re.findall(r"`+", text)
    fence = "`" * max(3, max((len(run) + 1 for run in runs), default=3))
    return fence + "text\n" + text + ("" if text.endswith("\n") else "\n") + fence


def source_files(root: Path, selected: list[Path]) -> list[Path]:
    files = set()
    for source in selected:
        source.relative_to(root)
        if source.is_symlink() or not source.exists():
            raise ValueError("source must exist and may not be a symlink: " + str(source))
        found = [source] if source.is_file() else source.rglob("*")
        for file in found:
            if file.is_symlink():
                raise ValueError("symlink is not admitted: " + str(file))
            if file.is_file():
                file.resolve().relative_to(root)
                files.add(file)
    return sorted(files, key=lambda p: p.relative_to(root).as_posix())


HTML_HEAD = '''<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; img-src 'none'; connect-src 'none'; base-uri 'none'">
<title>Comentarios originales del firmware HGW500</title>
<style>body{font:16px system-ui,sans-serif;margin:2rem auto;max-width:1100px;padding:0 1rem;background:#111827;color:#e5e7eb}h1{font-size:1.8rem}input{width:100%;box-sizing:border-box;padding:.8rem;font:inherit;background:#1f2937;color:#fff;border:1px solid #6b7280;border-radius:.4rem}article{border:1px solid #374151;border-radius:.4rem;padding:1rem;margin:1rem 0}h2{font-size:1rem;overflow-wrap:anywhere}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#0b1220;padding:1rem}small{overflow-wrap:anywhere;color:#a5b4fc}[hidden]{display:none}button{font:inherit;padding:.4rem;background:#374151;color:white;border:0;border-radius:.3rem}footer{color:#9ca3af;margin:2rem 0}</style>
</head><body><h1>Comentarios originales del firmware HGW500</h1>
<p>Vista local de comentarios conservados byte a byte. El archivo comments.raw.bin y el catálogo JSON contienen los bytes y posiciones verificables. Esta página no accede a la red ni al router.</p>
'''
HTML_END = '''<footer>Extracción léxica de C/C++. Incluye ramas inactivas del preprocesador. No interpreta trigraphs ni comentarios de otros lenguajes. Las vistas UTF-8/CP1252/Latin-1 no sustituyen a los bytes originales.</footer>
<script>
const search=document.getElementById('search');
const records=Array.from(document.querySelectorAll('article'));
const count=document.getElementById('count');
let timer;
search.addEventListener('input',()=>{clearTimeout(timer);timer=setTimeout(()=>{
const q=search.value.toLocaleLowerCase();let shown=0;
for(const record of records){const visible=record.textContent.toLocaleLowerCase().includes(q);record.hidden=!visible;if(visible)shown++;}
count.textContent=shown+' / '+records.length+' comentarios visibles';
},100);});
</script></body></html>
'''


def catalog(root: Path, selected: list[Path], output: Path) -> dict:
    root = root.resolve()
    if any(path.is_symlink() for path in selected):
        raise ValueError("selected source root may not be a symlink")
    selected = [path.resolve() for path in selected]
    output = output.resolve()
    for path in selected:
        path.relative_to(root)
        if output == path or path in output.parents:
            raise ValueError("output must be outside every selected source tree")
    if output.exists():
        raise FileExistsError("immutable output already exists: " + str(output))
    files = source_files(root, selected)
    output.mkdir(parents=True, exist_ok=False)
    rows = []
    records = []
    stream_offset = 0
    headings = ["# Comentarios originales del firmware HGW500\n",
                "Fuentes conservados sin cambios. Los offsets son bytes originales, cero-based, con fin exclusivo. `comments.raw.bin` es la representación exacta; esta vista decodificada no sustituye a los bytes.\n"]
    articles = []
    with (output / "comments.raw.bin").open("wb") as stream:
        for file in files:
            raw = file.read_bytes()
            name = file.relative_to(root).as_posix()
            extracted = scan_comments(raw) if file.suffix.lower() in SOURCE_SUFFIXES else []
            rows.append({"path": name, "bytes": len(raw), "sha256": sha(raw),
                         "comment_scanner": "C_CPP_LEXICAL" if file.suffix.lower() in SOURCE_SUFFIXES else "NOT_SCANNED_UNSUPPORTED_LANGUAGE",
                         "comments": len(extracted)})
            for comment in extracted:
                blob = raw[comment["offset"]:comment["end_offset"]]
                text, encoding = decode(blob)
                record = {"id": len(records) + 1, "path": name, **comment,
                          "raw_stream_offset": stream_offset, "decoded_encoding": encoding,
                          "text": text}
                stream.write(blob)
                stream_offset += len(blob)
                records.append(record)
                label = name + ":" + str(comment["line"])
                headings.append("\n## " + html.escape(label, quote=True) + "\n\nBytes `" + str(comment["offset"]) + ".." + str(comment["end_offset"]) + "`; SHA256 `" + comment["sha256"] + "`; decodificación `" + encoding + "`.\n\n" + markdown_code(text) + "\n")
                articles.append('<article id="comment-' + str(record["id"]) + '"><h2>' + html.escape(label, quote=True) + '</h2><small>Bytes ' + str(comment["offset"]) + '..' + str(comment["end_offset"]) + ' · ' + encoding + ' · SHA256 ' + comment["sha256"] + '</small><pre>' + html.escape(text, quote=True) + '</pre></article>')
            if sha(file.read_bytes()) != rows[-1]["sha256"]:
                raise RuntimeError("source changed during extraction: " + name)
    result = {"schema": "openmitrastar.hgw-comments/v1", "status": "PASS_EXACT_COMMENT_CATALOG",
              "created_utc": datetime.now(timezone.utc).isoformat(),
              "root": str(root), "source_roots": [p.relative_to(root).as_posix() for p in selected],
              "catalog_tool_sha256": sha(Path(__file__).read_bytes()),
              "hardware_accessed": False, "source_files_modified": False,
              "files": rows, "file_count": len(rows), "comment_count": len(records),
              "raw_comment_bytes": stream_offset, "raw_comment_sha256": sha((output / "comments.raw.bin").read_bytes()),
              "unterminated_comments": sum(not r["terminated"] for r in records),
              "limits": ["C/C++ lexical comments only; all preprocessor branches included", "No trigraph translation or preprocessing/include expansion", "Non-source file hashes are catalogued, their content is not published", "Decoded pages are views; exact raw bytes remain authoritative"]}
    # Recheck every selected file after the complete extraction, not just each
    # individual read. New files or removals are also rejected.
    if source_files(root, selected) != files:
        raise RuntimeError("selected source membership changed during extraction")
    for row, file in zip(rows, files):
        if sha(file.read_bytes()) != row["sha256"]:
            raise RuntimeError("source changed before completion: " + row["path"])
    (output / "comments.json").write_text(json.dumps({"schema": result["schema"], "comments": records}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    (output / "COMMENTS.md").write_text("\n".join(headings), encoding="utf-8", newline="\n")
    controls = '<p>' + str(len(rows)) + ' archivos · ' + str(len(records)) + ' comentarios · ' + str(stream_offset) + ' bytes exactos</p><label for="search">Buscar texto, fichero, línea o hash</label><input id="search" type="search" placeholder="Buscar comentarios…"><p id="count">' + str(len(records)) + ' / ' + str(len(records)) + ' comentarios visibles</p>'
    (output / "index.html").write_text(HTML_HEAD + controls + "\n".join(articles) + HTML_END, encoding="utf-8", newline="\n")
    (output / "manifest.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    artifacts = {name: sha((output / name).read_bytes()) for name in ("comments.raw.bin", "comments.json", "COMMENTS.md", "index.html", "manifest.json")}
    (output / "artifact-hashes.json").write_text(json.dumps(artifacts, indent=2) + "\n", encoding="utf-8", newline="\n")
    return {key: result[key] for key in ("status", "file_count", "comment_count", "raw_comment_bytes", "unterminated_comments", "hardware_accessed", "source_files_modified")}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, action="append", required=True,
                        help="Repeat for explicitly selected source subtrees; relative to --root")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    selected = [path if path.is_absolute() else args.root / path for path in args.source_root]
    print(json.dumps(catalog(args.root, selected, args.output), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
