"""
Semantic Scholar API Integration
================================
Fetch paper metadata, citations, and related papers from Semantic Scholar.
"""

import time
import urllib.request
import urllib.parse
import json
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

from config import SEMANTIC_SCHOLAR_API_URL, SEMANTIC_SCHOLAR_API_KEY


@dataclass
class PaperInfo:
    """Paper information from Semantic Scholar."""
    paper_id: str
    title: str
    authors: List[str]
    year: Optional[int]
    abstract: Optional[str]
    venue: Optional[str]
    citation_count: int
    doi: Optional[str]
    arxiv_id: Optional[str]
    url: str
    fields_of_study: List[str]


def _make_request(endpoint: str, params: Optional[Dict] = None) -> Optional[Dict]:
    """Make a request to Semantic Scholar API."""
    url = f"{SEMANTIC_SCHOLAR_API_URL}/{endpoint}"

    if params:
        url += "?" + urllib.parse.urlencode(params)

    headers = {"Accept": "application/json"}
    if SEMANTIC_SCHOLAR_API_KEY:
        headers["x-api-key"] = SEMANTIC_SCHOLAR_API_KEY

    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode())
    except Exception as e:
        print(f"Semantic Scholar API error: {e}")
        return None


def search_papers(
    query: str,
    limit: int = 10,
    year_range: Optional[tuple] = None,
    fields_of_study: Optional[List[str]] = None,
) -> List[PaperInfo]:
    """
    Search for papers on Semantic Scholar.

    Args:
        query: Search query
        limit: Maximum results to return
        year_range: Optional (start_year, end_year) tuple
        fields_of_study: Optional list of fields to filter by

    Returns:
        List of PaperInfo objects
    """
    params = {
        "query": query,
        "limit": min(limit, 100),
        "fields": "paperId,title,authors,year,abstract,venue,citationCount,externalIds,url,s2FieldsOfStudy"
    }

    if year_range:
        params["year"] = f"{year_range[0]}-{year_range[1]}"

    if fields_of_study:
        params["fieldsOfStudy"] = ",".join(fields_of_study)

    data = _make_request("paper/search", params)

    if not data or "data" not in data:
        return []

    results = []
    for paper in data["data"]:
        results.append(_parse_paper(paper))

    return results


def get_paper_by_doi(doi: str) -> Optional[PaperInfo]:
    """Get paper info by DOI."""
    endpoint = f"paper/DOI:{doi}"
    params = {
        "fields": "paperId,title,authors,year,abstract,venue,citationCount,externalIds,url,s2FieldsOfStudy"
    }

    data = _make_request(endpoint, params)
    return _parse_paper(data) if data else None


def get_paper_by_arxiv(arxiv_id: str) -> Optional[PaperInfo]:
    """Get paper info by arXiv ID."""
    endpoint = f"paper/arXiv:{arxiv_id}"
    params = {
        "fields": "paperId,title,authors,year,abstract,venue,citationCount,externalIds,url,s2FieldsOfStudy"
    }

    data = _make_request(endpoint, params)
    return _parse_paper(data) if data else None


def get_paper_citations(paper_id: str, limit: int = 20) -> List[PaperInfo]:
    """Get papers that cite this paper."""
    endpoint = f"paper/{paper_id}/citations"
    params = {
        "limit": min(limit, 100),
        "fields": "paperId,title,authors,year,abstract,venue,citationCount,externalIds,url"
    }

    data = _make_request(endpoint, params)

    if not data or "data" not in data:
        return []

    results = []
    for item in data["data"]:
        if "citingPaper" in item:
            results.append(_parse_paper(item["citingPaper"]))

    return results


def get_paper_references(paper_id: str, limit: int = 20) -> List[PaperInfo]:
    """Get papers referenced by this paper."""
    endpoint = f"paper/{paper_id}/references"
    params = {
        "limit": min(limit, 100),
        "fields": "paperId,title,authors,year,abstract,venue,citationCount,externalIds,url"
    }

    data = _make_request(endpoint, params)

    if not data or "data" not in data:
        return []

    results = []
    for item in data["data"]:
        if "citedPaper" in item:
            results.append(_parse_paper(item["citedPaper"]))

    return results


def get_recommended_papers(paper_id: str, limit: int = 10) -> List[PaperInfo]:
    """Get recommended papers based on a source paper."""
    endpoint = f"recommendations/v1/papers/forpaper/{paper_id}"
    params = {
        "limit": min(limit, 100),
        "fields": "paperId,title,authors,year,abstract,venue,citationCount,externalIds,url,s2FieldsOfStudy"
    }

    data = _make_request(endpoint, params)

    if not data or "recommendedPapers" not in data:
        return []

    results = []
    for paper in data["recommendedPapers"]:
        results.append(_parse_paper(paper))

    return results


def enrich_citation(citation: Dict[str, Any]) -> Dict[str, Any]:
    """
    Enrich a citation with Semantic Scholar metadata.

    Args:
        citation: Citation dict with doi, arxiv_id, or pmid

    Returns:
        Enriched citation dict
    """
    paper_info = None

    # Try DOI first
    if citation.get("doi"):
        paper_info = get_paper_by_doi(citation["doi"])
        time.sleep(0.1)  # Rate limiting

    # Try arXiv ID
    if not paper_info and citation.get("arxiv_id"):
        paper_info = get_paper_by_arxiv(citation["arxiv_id"])
        time.sleep(0.1)

    if paper_info:
        citation.update({
            "title": paper_info.title,
            "authors": ", ".join(paper_info.authors),
            "year": paper_info.year,
            "venue": paper_info.venue,
            "citation_count": paper_info.citation_count,
            "semantic_scholar_id": paper_info.paper_id,
            "abstract": paper_info.abstract,
        })

    return citation


def batch_enrich_citations(citations: List[Dict[str, Any]], max_enrichments: int = 20) -> List[Dict[str, Any]]:
    """
    Enrich multiple citations with Semantic Scholar metadata.

    Args:
        citations: List of citation dicts
        max_enrichments: Maximum number to enrich (rate limiting)

    Returns:
        List of enriched citations
    """
    enriched = []

    for i, citation in enumerate(citations):
        if i < max_enrichments:
            citation = enrich_citation(citation)
            time.sleep(0.2)  # Rate limiting between requests
        enriched.append(citation)

    return enriched


def _parse_paper(data: Dict) -> PaperInfo:
    """Parse API response into PaperInfo."""
    external_ids = data.get("externalIds", {}) or {}

    authors = []
    for author in data.get("authors", []) or []:
        if isinstance(author, dict):
            authors.append(author.get("name", "Unknown"))
        else:
            authors.append(str(author))

    fields = []
    for field in data.get("s2FieldsOfStudy", []) or []:
        if isinstance(field, dict):
            fields.append(field.get("category", ""))
        else:
            fields.append(str(field))

    return PaperInfo(
        paper_id=data.get("paperId", ""),
        title=data.get("title", "Unknown"),
        authors=authors,
        year=data.get("year"),
        abstract=data.get("abstract"),
        venue=data.get("venue"),
        citation_count=data.get("citationCount", 0) or 0,
        doi=external_ids.get("DOI"),
        arxiv_id=external_ids.get("ArXiv"),
        url=data.get("url", ""),
        fields_of_study=fields,
    )


def format_paper_info(paper: PaperInfo) -> str:
    """Format paper info for display."""
    parts = [f"**{paper.title}**"]

    if paper.authors:
        authors_str = ", ".join(paper.authors[:5])
        if len(paper.authors) > 5:
            authors_str += f" et al. ({len(paper.authors)} authors)"
        parts.append(f"*{authors_str}*")

    meta = []
    if paper.year:
        meta.append(str(paper.year))
    if paper.venue:
        meta.append(paper.venue)
    if paper.citation_count:
        meta.append(f"{paper.citation_count} citations")
    if meta:
        parts.append(" | ".join(meta))

    if paper.abstract:
        parts.append(f"\n{paper.abstract[:300]}...")

    if paper.doi:
        parts.append(f"\nDOI: {paper.doi}")
    if paper.url:
        parts.append(f"URL: {paper.url}")

    return "\n".join(parts)
