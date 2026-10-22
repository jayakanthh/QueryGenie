#!/usr/bin/env python3
"""
Open, local similarity check: how much of a document's wording also appears in a set of source documents.

It finds runs of N or more consecutive words that the document shares with each source (word n-gram
"shingles", the basis of most text-matching tools), ignoring case, punctuation and citation markers
such as [12]. It does not search the web: it only compares against the sources you give it, so use it
on the papers a document cites or builds on. A university checker (Turnitin / iThenticate) is what a
department counts; this one shows exactly which passages overlap, so they can be quoted or reworded.

    python scripts/similarity_check.py docs/paper/main.pdf --sources path/to/source_pdfs --words 8
    python scripts/similarity_check.py report.txt --sources a.pdf b.pdf notes.txt --words 6 --top 20

Sources and the document may be .pdf (needs `pdftotext` from poppler), .txt, .md or .tex.
The reference list of the document (everything after the last "References" heading) is excluded.
"""
import argparse
import os
import re
import subprocess
import sys


def read_text(path):
    if path.lower().endswith(".pdf"):
        return subprocess.run(["pdftotext", path, "-"], capture_output=True, text=True, check=True).stdout
    return open(path, encoding="utf-8", errors="ignore").read()


def words(text):
    text = re.sub(r"\[\d+(?:[,–-]\s*\d+)*\]", " ", text.lower())          # citation markers
    return re.findall(r"[a-z0-9]+", text)


def runs(doc, source, n):
    """Maximal runs of >= n consecutive words that appear in both token lists."""
    shingles = {tuple(source[i:i + n]) for i in range(len(source) - n + 1)}
    hits = [i for i in range(len(doc) - n + 1) if tuple(doc[i:i + n]) in shingles]
    spans = []
    for i in hits:
        if spans and i <= spans[-1][1] - n + 1:
            spans[-1][1] = i + n
        else:
            spans.append([i, i + n])
    return spans


def collect(paths):
    out = []
    for p in paths:
        if os.path.isdir(p):
            out += [os.path.join(p, f) for f in sorted(os.listdir(p)) if f.lower().endswith((".pdf", ".txt", ".md", ".tex"))]
        else:
            out.append(p)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("document")
    ap.add_argument("--sources", nargs="+", required=True, help="source files or folders to compare against")
    ap.add_argument("--words", type=int, default=8, help="minimum length of a shared run, in words (default 8)")
    ap.add_argument("--top", type=int, default=10, help="how many longest shared runs to print per source")
    args = ap.parse_args()

    text = read_text(args.document)
    cut = text.lower().rfind("references")
    doc = words(text[:cut] if cut > len(text) * 0.5 else text)
    print(f"{args.document}: {len(doc)} words compared (reference list excluded)\n")

    total_hits = 0
    for src in collect(args.sources):
        try:
            sw = words(read_text(src))
        except Exception as exc:  # noqa: BLE001
            print(f"  skipped {os.path.basename(src)}: {exc}"); continue
        spans = runs(doc, sw, args.words)
        covered = sum(b - a for a, b in spans)
        total_hits += len(spans)
        if not spans:
            print(f"  {os.path.basename(src):28s} no shared run of {args.words}+ words"); continue
        print(f"  {os.path.basename(src):28s} {len(spans)} shared run(s), {covered} words ({100 * covered / len(doc):.2f}% of the document)")
        for a, b in sorted(spans, key=lambda s: s[0] - s[1])[:args.top]:
            print(f"      [{b - a} words] {' '.join(doc[a:b])}")
    print(f"\nTotal shared runs of {args.words}+ words across all sources: {total_hits}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
