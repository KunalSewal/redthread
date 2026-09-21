"""Build the GraphRAG knowledge base: policy/pattern/regulatory chunks and closed-case embeddings.

    python scripts/build_knowledge.py --fetch   # download regulatory docs first (once)
    python scripts/build_knowledge.py           # chunk, embed, load into TigerGraph

Chunks: the README's fraud patterns, policy rules (one chunk per rule, so the agent can cite
"R6"), and guidance sections; regulatory PDFs/HTML split into ~180-word passages.
Vectors: every DocChunk and every ClosedCase (pattern + outcome + analyst notes).
"""

import argparse
import csv
import html
import logging
import re
import sys
import urllib.request
from pathlib import Path

import pandas as pd

from redthread import paths
from redthread.rag.embed import embed_passages
from redthread.rag.sources import SOURCES

sys.path.insert(0, str(Path(__file__).parent))
from setup_graph import load_file  # noqa: E402

log = logging.getLogger("build_knowledge")
REG_DIR = paths.ROOT / "docs" / "regulatory"
WORDS_PER_CHUNK, OVERLAP = 180, 30
MAX_CHUNKS_PER_DOC = 60  # ~11k words per document; see regulatory_chunks()


def fetch() -> None:
    REG_DIR.mkdir(parents=True, exist_ok=True)
    for name, (_, url) in SOURCES.items():
        target = REG_DIR / name
        if target.exists():
            continue
        # Some regulator sites reject a bare script user agent, so identify as a normal browser.
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/126.0 Safari/537.36 RedThread-research",
            "Accept": "text/html,application/xhtml+xml,application/pdf,*/*",
            "Accept-Language": "en-GB,en;q=0.9"})
        try:
            target.write_bytes(urllib.request.urlopen(req, timeout=90).read())
            log.info("downloaded %s", name)
        except (urllib.error.URLError, TimeoutError) as exc:
            # A publisher blocking automated download should not stop the knowledge base being built.
            target.unlink(missing_ok=True)
            log.warning("could not download %s (%s); continuing without it", name, exc)


def readme_chunks() -> list[dict]:
    """Pattern, rule and guidance sections from data/README.md, one chunk per unit of meaning."""
    text = (paths.DATA / "README.md").read_text(encoding="utf-8")
    chunks = []
    patterns = re.search(r"## The five known fraud patterns\n(.*?)\n## ", text, re.S).group(1)
    for m in re.finditer(r"\*\*(\d)\. ([^*]+)\*\*\s*(.+?)(?=\n\n\*\*\d\.|\Z)", patterns, re.S):
        chunks.append(_chunk("readme", f"Known pattern {m.group(1)}: {m.group(2).strip('.')}", m.group(3)))
    policy = text[text.index("# Fraud Policy"):text.index("# Answer Format")]
    for m in re.finditer(r"\*\*(R\d+)\. ([^*]+)\*\*\s*(.+?)(?=\n\n\*\*R\d+\.|\n###|\Z)", policy, re.S):
        chunks.append(_chunk("fraud_policy", f"Rule {m.group(1)}: {m.group(2).strip('.')}", m.group(3)))
    for m in re.finditer(r"### (\d[a-z]?\. [^\n]+)\n(.+?)(?=\n### |\Z)", policy, re.S):
        if m.group(1).startswith("3."):
            continue  # rules are chunked individually above
        chunks.append(_chunk("fraud_policy", f"Section {m.group(1)}", m.group(2)))
    things = re.search(r"## Things to know\n(.*?)\n## ", text, re.S).group(1)
    chunks.append(_chunk("readme", "Things to know", things))
    return chunks


def _chunk(source: str, section: str, content: str) -> dict:
    content = re.sub(r"\s+", " ", content).strip()
    return {"source": source, "section": section, "content": f"{section}. {content}"}


def document_text(path: Path) -> str:
    if path.suffix == ".pdf":
        from pypdf import PdfReader

        return "\n".join(page.extract_text() or "" for page in PdfReader(path).pages)
    raw = path.read_text(encoding="utf-8", errors="ignore")
    raw = re.sub(r"(?is)<(script|style|nav|header|footer)[^>]*>.*?</\1>", " ", raw)
    main = re.search(r"(?is)<main[^>]*>(.*?)</main>", raw)
    return html.unescape(re.sub(r"(?s)<[^>]+>", " ", main.group(1) if main else raw))


def regulatory_chunks() -> list[dict]:
    """Chunk each regulatory document, capped so one very large file cannot swamp retrieval.

    The OFAC SDN list is 2.7 million words of sanctioned names, which would be ~18,000 chunks of
    pure noise for a dataset with no counterparty names in it. The cap keeps each document's opening
    material — for the SDN list, the part that explains what it is and how it is used.
    """
    chunks = []
    for name, (title, _) in SOURCES.items():
        path = REG_DIR / name
        if not path.exists():
            log.warning("missing %s; run with --fetch", name)
            continue
        words = re.sub(r"\s+", " ", document_text(path)).split()
        step = WORDS_PER_CHUNK - OVERLAP
        before = len(chunks)
        for i, start in enumerate(range(0, max(len(words) - OVERLAP, 1), step)):
            if len(chunks) - before >= MAX_CHUNKS_PER_DOC:
                break
            body = " ".join(words[start:start + WORDS_PER_CHUNK])
            if len(body) > 200:
                chunks.append({"source": name, "section": f"{title} (part {i + 1})", "content": body})
        capped = " (capped)" if len(chunks) - before >= MAX_CHUNKS_PER_DOC else ""
        log.info("%-45s %8d words -> %3d chunks%s", name, len(words), len(chunks) - before, capped)
    return chunks


def closed_case_text(cases: pd.DataFrame) -> list[str]:
    return [f"{r.outcome.replace('_', ' ')}; pattern {r.pattern}. {r.analyst_notes}" for r in cases.itertuples()]


def write_vectors(path: Path, ids: list[str], vectors: list[list[float]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for vid, vec in zip(ids, vectors, strict=True):
            fh.write(f"{vid}|{','.join(f'{v:.6f}' for v in vec)}\n")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    parser = argparse.ArgumentParser()
    parser.add_argument("--fetch", action="store_true", help="download regulatory documents first")
    parser.add_argument("--no-load", action="store_true", help="build files only; do not load into TigerGraph")
    args = parser.parse_args()
    if args.fetch:
        fetch()

    chunks = pd.DataFrame(readme_chunks() + regulatory_chunks())
    chunks.insert(0, "chunk_id", [f"DOC-{i:05d}" for i in range(1, len(chunks) + 1)])
    chunk_csv = paths.PROCESSED / "doc_chunks.csv"
    chunks.to_csv(chunk_csv, index=False, quoting=csv.QUOTE_NONNUMERIC)
    from_readme = chunks.source.isin(["readme", "fraud_policy"]).sum()
    log.info("%d chunks (%d from README policy/patterns)", len(chunks), from_readme)
    doc_vectors = embed_passages(chunks.content.tolist())
    write_vectors(paths.PROCESSED / "doc_chunk_emb.txt", chunks.chunk_id.tolist(), doc_vectors)

    cases = pd.read_csv(paths.CLOSED_CASES_CSV, usecols=["case_id", "outcome", "pattern", "analyst_notes"])
    case_vectors = embed_passages(closed_case_text(cases))
    write_vectors(paths.PROCESSED / "closed_case_emb.txt", cases.case_id.tolist(), case_vectors)

    if args.no_load:
        return
    log.info("doc chunks: %s", load_file("load_doc_chunks", chunk_csv))
    for job, name in [("load_doc_chunk_emb", "doc_chunk_emb.txt"), ("load_closed_case_emb", "closed_case_emb.txt")]:
        # Vector files: "<id>|<v1,v2,...>", no header.
        log.info("%s: %s", name, load_file(job, paths.PROCESSED / name, sep="|", has_header=False))


if __name__ == "__main__":
    main()
