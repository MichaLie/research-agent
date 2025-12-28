"""
Enhanced PDF Extraction Module
==============================
Extracts text, tables, figures, and metadata from PDFs.
"""

import re
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field

import fitz  # PyMuPDF


@dataclass
class ExtractedPaper:
    """Container for extracted paper content."""
    filename: str
    file_hash: str
    text: str
    title: Optional[str] = None
    authors: Optional[str] = None
    abstract: Optional[str] = None
    sections: Dict[str, str] = field(default_factory=dict)
    tables: List[Dict[str, Any]] = field(default_factory=list)
    figures: List[Dict[str, Any]] = field(default_factory=list)
    references: List[str] = field(default_factory=list)
    doi: Optional[str] = None
    arxiv_id: Optional[str] = None
    page_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


def compute_file_hash(filepath: Path) -> str:
    """Compute SHA256 hash of a file."""
    sha256 = hashlib.sha256()
    with open(filepath, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            sha256.update(chunk)
    return sha256.hexdigest()


def extract_pdf(pdf_path: Path) -> ExtractedPaper:
    """
    Extract comprehensive content from a PDF.

    Returns:
        ExtractedPaper with text, metadata, tables, and more.
    """
    doc = fitz.open(pdf_path)
    file_hash = compute_file_hash(pdf_path)

    # Initialize result
    result = ExtractedPaper(
        filename=pdf_path.name,
        file_hash=file_hash,
        text="",
        page_count=len(doc),
        metadata=dict(doc.metadata) if doc.metadata else {}
    )

    # Extract text page by page with structure
    all_text_parts = []
    all_blocks = []

    for page_num, page in enumerate(doc, 1):
        # Get text with layout preservation
        text = page.get_text("text")
        if text.strip():
            all_text_parts.append(f"--- Page {page_num} ---\n{text}")

        # Get text blocks for structure analysis
        blocks = page.get_text("dict")["blocks"]
        for block in blocks:
            if "lines" in block:  # Text block
                block_text = ""
                for line in block["lines"]:
                    for span in line["spans"]:
                        block_text += span["text"]
                    block_text += "\n"
                all_blocks.append({
                    "page": page_num,
                    "type": "text",
                    "text": block_text.strip(),
                    "bbox": block["bbox"],
                    "font_size": _get_dominant_font_size(block)
                })
            elif "image" in block:  # Image block
                result.figures.append({
                    "page": page_num,
                    "bbox": block["bbox"],
                    "width": block.get("width", 0),
                    "height": block.get("height", 0)
                })

        # Extract tables (heuristic-based)
        tables = _extract_tables_from_page(page, page_num)
        result.tables.extend(tables)

    result.text = "\n\n".join(all_text_parts)

    # Extract metadata
    _extract_paper_metadata(result, all_blocks)

    # Extract references section
    result.references = _extract_references(result.text)

    # Extract DOI and arXiv ID
    result.doi = _extract_doi(result.text)
    result.arxiv_id = _extract_arxiv_id(result.text)

    doc.close()
    return result


def _get_dominant_font_size(block: Dict) -> float:
    """Get the most common font size in a text block."""
    sizes = []
    for line in block.get("lines", []):
        for span in line.get("spans", []):
            sizes.append(span.get("size", 12))
    return max(set(sizes), key=sizes.count) if sizes else 12


def _extract_tables_from_page(page, page_num: int) -> List[Dict[str, Any]]:
    """
    Extract tables from a page using heuristic detection.

    This uses layout analysis to detect table-like structures.
    """
    tables = []

    # Get text blocks with positions
    blocks = page.get_text("dict")["blocks"]

    # Look for aligned text that might be tables
    # This is a simplified heuristic - production would use more sophisticated detection

    text_blocks = [b for b in blocks if "lines" in b]

    # Group blocks by vertical position (rows)
    rows = {}
    for block in text_blocks:
        y_center = (block["bbox"][1] + block["bbox"][3]) / 2
        y_key = round(y_center / 10) * 10  # Group by 10-point ranges

        if y_key not in rows:
            rows[y_key] = []
        rows[y_key].append(block)

    # Detect table regions (multiple aligned columns)
    for y_key, row_blocks in rows.items():
        if len(row_blocks) >= 3:  # At least 3 columns suggests a table
            # Check if blocks are horizontally aligned (table row)
            x_positions = sorted([b["bbox"][0] for b in row_blocks])
            if len(x_positions) >= 3:
                # Likely a table row
                row_text = " | ".join([
                    _get_block_text(b).strip()
                    for b in sorted(row_blocks, key=lambda b: b["bbox"][0])
                ])
                if row_text.strip():
                    tables.append({
                        "page": page_num,
                        "type": "table_row",
                        "content": row_text,
                        "y_position": y_key
                    })

    return tables


def _get_block_text(block: Dict) -> str:
    """Extract text from a block."""
    text = ""
    for line in block.get("lines", []):
        for span in line.get("spans", []):
            text += span.get("text", "")
        text += " "
    return text


def _extract_paper_metadata(result: ExtractedPaper, blocks: List[Dict]):
    """Extract title, authors, and abstract from paper structure."""

    # Find title (usually largest font on first page)
    first_page_blocks = [b for b in blocks if b["page"] == 1 and b["type"] == "text"]

    if first_page_blocks:
        # Sort by font size (descending) and position (ascending)
        sorted_blocks = sorted(
            first_page_blocks,
            key=lambda b: (-b["font_size"], b["bbox"][1])
        )

        # Title is likely the first large text
        if sorted_blocks:
            result.title = sorted_blocks[0]["text"].strip()

            # Authors often follow title with smaller font
            if len(sorted_blocks) > 1:
                potential_authors = sorted_blocks[1]["text"].strip()
                # Simple heuristic: authors line usually has commas or "and"
                if "," in potential_authors or " and " in potential_authors.lower():
                    result.authors = potential_authors

    # Extract abstract
    abstract_match = re.search(
        r'(?:^|\n)\s*(?:ABSTRACT|Abstract)\s*[:\n]?\s*(.+?)(?=\n\s*(?:INTRODUCTION|Introduction|1\.|Keywords|KEYWORDS))',
        result.text,
        re.DOTALL | re.IGNORECASE
    )
    if abstract_match:
        result.abstract = abstract_match.group(1).strip()[:2000]  # Limit length


def _extract_references(text: str) -> List[str]:
    """Extract reference entries from the paper."""
    references = []

    # Find references section
    ref_match = re.search(
        r'(?:^|\n)\s*(?:REFERENCES|References|BIBLIOGRAPHY|Bibliography)\s*\n(.+?)(?:\n\s*(?:APPENDIX|Appendix|$))',
        text,
        re.DOTALL | re.IGNORECASE
    )

    if ref_match:
        ref_text = ref_match.group(1)

        # Split by reference numbers or bullets
        # Pattern: [1], 1., (1), etc.
        ref_entries = re.split(r'\n\s*(?:\[\d+\]|\d+\.|\(\d+\))\s*', ref_text)

        for entry in ref_entries:
            entry = entry.strip()
            if entry and len(entry) > 20:  # Minimum reference length
                references.append(entry[:500])  # Limit length

    return references[:100]  # Limit total references


def _extract_doi(text: str) -> Optional[str]:
    """Extract DOI from paper text."""
    doi_pattern = r'(?:doi[:\s]*|https?://(?:dx\.)?doi\.org/)?(10\.\d{4,}/[^\s\]>]+)'
    match = re.search(doi_pattern, text, re.IGNORECASE)
    if match:
        doi = match.group(1)
        # Clean up common trailing characters
        doi = re.sub(r'[.,;:\]>]+$', '', doi)
        return doi
    return None


def _extract_arxiv_id(text: str) -> Optional[str]:
    """Extract arXiv ID from paper text."""
    arxiv_pattern = r'arXiv:(\d{4}\.\d{4,5}(?:v\d+)?)'
    match = re.search(arxiv_pattern, text, re.IGNORECASE)
    return match.group(1) if match else None


def extract_citations_from_text(text: str) -> List[Dict[str, Any]]:
    """
    Extract citation identifiers from paper text.

    Returns list of citations with DOIs, arXiv IDs, PMIDs found.
    """
    citations = []

    # DOIs
    doi_pattern = r'(10\.\d{4,}/[^\s\]>,]+)'
    for match in re.finditer(doi_pattern, text):
        doi = re.sub(r'[.,;:\]>]+$', '', match.group(1))
        citations.append({"type": "doi", "id": doi, "doi": doi})

    # arXiv IDs
    arxiv_pattern = r'arXiv:(\d{4}\.\d{4,5}(?:v\d+)?)'
    for match in re.finditer(arxiv_pattern, text, re.IGNORECASE):
        citations.append({"type": "arxiv", "id": match.group(1), "arxiv_id": match.group(1)})

    # PMIDs
    pmid_pattern = r'PMID[:\s]*(\d+)'
    for match in re.finditer(pmid_pattern, text, re.IGNORECASE):
        citations.append({"type": "pmid", "id": match.group(1), "pmid": match.group(1)})

    # Deduplicate
    seen = set()
    unique_citations = []
    for cit in citations:
        key = (cit["type"], cit["id"])
        if key not in seen:
            seen.add(key)
            unique_citations.append(cit)

    return unique_citations


def chunk_text(text: str, chunk_size: int = 30000, overlap: int = 2000) -> List[str]:
    """
    Split text into overlapping chunks for processing long papers.

    Args:
        text: Full paper text
        chunk_size: Target size per chunk
        overlap: Overlap between chunks

    Returns:
        List of text chunks
    """
    if len(text) <= chunk_size:
        return [text]

    chunks = []
    start = 0

    while start < len(text):
        end = start + chunk_size

        # Try to break at paragraph boundary
        if end < len(text):
            # Look for paragraph break near the end
            break_point = text.rfind('\n\n', start + chunk_size - overlap, end)
            if break_point > start:
                end = break_point

        chunks.append(text[start:end])
        start = end - overlap

    return chunks


def format_paper_for_analysis(paper: ExtractedPaper) -> str:
    """
    Format extracted paper content for analysis.

    Returns formatted text including metadata, tables, etc.
    """
    parts = []

    # Header with metadata
    parts.append(f"# {paper.title or paper.filename}")
    parts.append("")

    if paper.authors:
        parts.append(f"**Authors:** {paper.authors}")
    if paper.doi:
        parts.append(f"**DOI:** {paper.doi}")
    if paper.arxiv_id:
        parts.append(f"**arXiv:** {paper.arxiv_id}")
    parts.append(f"**Pages:** {paper.page_count}")
    parts.append("")

    # Abstract
    if paper.abstract:
        parts.append("## Abstract")
        parts.append(paper.abstract)
        parts.append("")

    # Main text
    parts.append("## Full Text")
    parts.append(paper.text)

    # Tables summary
    if paper.tables:
        parts.append("")
        parts.append("## Detected Tables")
        for i, table in enumerate(paper.tables[:10], 1):  # Limit tables
            parts.append(f"**Table {i} (Page {table['page']}):** {table['content'][:200]}")

    # Figures summary
    if paper.figures:
        parts.append("")
        parts.append(f"## Figures: {len(paper.figures)} detected")

    return "\n".join(parts)
