#!/usr/bin/env python3
"""
Research Paper Analysis Agent
=============================
A multi-stage agent that analyzes PDFs, performs deep reasoning,
and proactively suggests follow-up literature searches.

Uses Claude Opus 4.5 for best analysis quality.

Usage:
    python agent.py                     # Analyze PDFs in ./papers
    python agent.py /path/to/papers     # Analyze PDFs in custom directory
    python agent.py paper.pdf           # Analyze a single PDF
    python agent.py --batch papers/     # Batch analyze multiple PDFs
    python agent.py --compare a.pdf b.pdf  # Compare two papers
"""

import asyncio
import sys
from pathlib import Path
from typing import List, Optional

from claude_agent_sdk import query, ClaudeAgentOptions, AssistantMessage, ResultMessage

from config import (
    DEFAULT_MODEL,
    MAX_TEXT_LENGTH,
    CHUNK_SIZE,
    OUTPUT_DIR,
)
from pdf_extractor import (
    extract_pdf,
    format_paper_for_analysis,
    chunk_text,
    extract_citations_from_text,
)
from prompts import (
    RESEARCH_ANALYSIS_PROMPT,
    get_prompt,
    format_comparison_prompt,
    format_batch_prompt,
)
from database import (
    save_paper,
    save_analysis,
    update_analysis,
    save_citations,
    get_paper_by_hash,
)
from semantic_scholar import batch_enrich_citations


def process_pdf(pdf_path: Path) -> dict:
    """
    Process a PDF file and extract all content.

    Returns dict with paper info and extracted text.
    """
    print(f"📄 Processing: {pdf_path.name}")

    # Check if already processed
    from pdf_extractor import compute_file_hash
    file_hash = compute_file_hash(pdf_path)
    existing = get_paper_by_hash(file_hash)

    if existing:
        print(f"   ✓ Already in database (ID: {existing['id']})")
        return {
            "paper_id": existing["id"],
            "filename": existing["filename"],
            "title": existing.get("title"),
            "text": existing.get("text_content", ""),
            "cached": True,
        }

    # Extract content
    paper = extract_pdf(pdf_path)
    formatted_text = format_paper_for_analysis(paper)

    print(f"   ✓ Extracted: {len(paper.text):,} chars, {paper.page_count} pages")
    if paper.title:
        print(f"   ✓ Title: {paper.title[:60]}...")
    if paper.doi:
        print(f"   ✓ DOI: {paper.doi}")

    # Extract and enrich citations
    citations = extract_citations_from_text(paper.text)
    if citations:
        print(f"   ✓ Found {len(citations)} citation identifiers")
        # Enrich first 10 citations with Semantic Scholar
        citations = batch_enrich_citations(citations, max_enrichments=10)

    # Save to database
    paper_id = save_paper(
        filename=paper.filename,
        filepath=str(pdf_path),
        text_content=paper.text,
        file_hash=paper.file_hash,
        title=paper.title,
        authors=paper.authors,
        abstract=paper.abstract,
        page_count=paper.page_count,
        doi=paper.doi,
        arxiv_id=paper.arxiv_id,
    )

    if citations:
        save_citations(paper_id, citations)

    return {
        "paper_id": paper_id,
        "filename": paper.filename,
        "title": paper.title,
        "authors": paper.authors,
        "abstract": paper.abstract,
        "text": formatted_text,
        "citations": citations,
        "cached": False,
    }


async def analyze_single_paper(
    paper_info: dict,
    prompt_type: str = "default",
    verbose: bool = True,
) -> str:
    """
    Analyze a single paper with the specified prompt type.

    Returns the analysis content.
    """
    from datetime import datetime

    analysis_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{paper_info['filename']}"

    # Save analysis record
    save_analysis(
        analysis_id=analysis_id,
        paper_id=paper_info["paper_id"],
        status="analyzing",
        model_used=DEFAULT_MODEL,
        prompt_type=prompt_type,
    )

    # Prepare prompt
    prompt = get_prompt(prompt_type)

    # Handle long papers with chunking
    text = paper_info["text"]
    if len(text) > MAX_TEXT_LENGTH:
        print(f"   ⚠️  Paper exceeds {MAX_TEXT_LENGTH:,} chars, using chunking...")
        chunks = chunk_text(text, CHUNK_SIZE)
        text = chunks[0]  # Use first chunk for main analysis
        text += f"\n\n[Note: This is a long paper. Showing first {len(text):,} of {len(paper_info['text']):,} characters.]"

    full_prompt = f"Analyze this research paper:\n\n{text}\n\n{prompt}"

    # Run analysis with Opus 4.5
    content_parts = []

    try:
        async for message in query(
            prompt=full_prompt,
            options=ClaudeAgentOptions(
                model=DEFAULT_MODEL,
                allowed_tools=[
                    "Read",
                    "Glob",
                    "Grep",
                    "WebSearch",
                    "WebFetch",
                    "Write",
                ],
                permission_mode="default"
            )
        ):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if hasattr(block, "text") and block.text:
                        content_parts.append(block.text)
                        if verbose:
                            print(block.text)
                    elif hasattr(block, "name") and verbose:
                        print(f"\n🔧 Using tool: {block.name}")

            elif isinstance(message, ResultMessage):
                if message.subtype == "success" and verbose:
                    print("\n✅ Analysis complete!")
                elif message.subtype == "error":
                    print(f"\n❌ Error: {message}")

        # Update analysis record
        final_content = "\n\n".join(content_parts)
        update_analysis(
            analysis_id=analysis_id,
            status="complete",
            content=final_content,
        )

        # Save to file
        output_file = OUTPUT_DIR / f"{Path(paper_info['filename']).stem}_analysis.md"
        output_file.write_text(
            f"# Analysis: {paper_info.get('title', paper_info['filename'])}\n\n"
            f"**Model:** {DEFAULT_MODEL}\n"
            f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"---\n\n{final_content}",
            encoding="utf-8"
        )
        print(f"\n📝 Saved to: {output_file}")

        return final_content

    except Exception as e:
        update_analysis(
            analysis_id=analysis_id,
            status="error",
            error_message=str(e),
        )
        raise


async def compare_papers(paper_infos: List[dict], verbose: bool = True) -> str:
    """Compare multiple papers."""
    print(f"\n📊 Comparing {len(paper_infos)} papers...")

    # Create summaries for comparison
    summaries = []
    for p in paper_infos:
        summaries.append({
            "title": p.get("title", p["filename"]),
            "summary": p.get("abstract", "")[:500] or "No abstract available"
        })

    prompt = format_comparison_prompt(summaries)

    # Include full text of all papers (truncated)
    combined_text = ""
    for p in paper_infos:
        combined_text += f"\n\n---\n\n## {p.get('title', p['filename'])}\n\n"
        combined_text += p["text"][:30000]  # Limit each paper

    full_prompt = f"{combined_text}\n\n{prompt}"

    content_parts = []

    async for message in query(
        prompt=full_prompt,
        options=ClaudeAgentOptions(
            model=DEFAULT_MODEL,
            allowed_tools=["WebSearch", "WebFetch"],
            permission_mode="default"
        )
    ):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if hasattr(block, "text") and block.text:
                    content_parts.append(block.text)
                    if verbose:
                        print(block.text)

    return "\n\n".join(content_parts)


async def batch_analyze(pdf_paths: List[Path], verbose: bool = True) -> str:
    """Batch analyze multiple papers with triage."""
    print(f"\n📚 Batch analyzing {len(pdf_paths)} papers...")

    # Process all PDFs
    paper_infos = []
    for pdf_path in pdf_paths:
        info = process_pdf(pdf_path)
        paper_infos.append(info)

    # Create batch prompt
    prompt = format_batch_prompt(paper_infos)

    # Include abstracts/summaries
    summaries_text = ""
    for p in paper_infos:
        summaries_text += f"\n\n### {p.get('title', p['filename'])}\n"
        if p.get("abstract"):
            summaries_text += p["abstract"][:1000]
        else:
            summaries_text += p["text"][:1000]

    full_prompt = f"{summaries_text}\n\n{prompt}"

    content_parts = []

    async for message in query(
        prompt=full_prompt,
        options=ClaudeAgentOptions(
            model=DEFAULT_MODEL,
            allowed_tools=["WebSearch", "WebFetch"],
            permission_mode="default"
        )
    ):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if hasattr(block, "text") and block.text:
                    content_parts.append(block.text)
                    if verbose:
                        print(block.text)

    return "\n\n".join(content_parts)


async def main_analyze(target: str = "./papers", prompt_type: str = "default"):
    """Main analysis entry point."""
    target_path = Path(target).resolve()

    if not target_path.exists():
        print(f"Error: {target} not found")
        sys.exit(1)

    print("=" * 60)
    print("🔬 RESEARCH PAPER ANALYSIS AGENT")
    print(f"   Model: {DEFAULT_MODEL}")
    print("=" * 60)
    print(f"📂 Target: {target_path}")
    print("=" * 60 + "\n")

    # Collect PDFs
    if target_path.is_file():
        pdfs = [target_path]
    else:
        pdfs = list(target_path.glob("*.pdf"))

    if not pdfs:
        print("No PDF files found.")
        return

    print(f"Found {len(pdfs)} PDF(s)\n")

    # Process each PDF
    for pdf_path in pdfs:
        paper_info = process_pdf(pdf_path)
        print()
        await analyze_single_paper(paper_info, prompt_type=prompt_type)
        print("\n" + "=" * 60 + "\n")


def main():
    """Entry point - parse args and run agent."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Research Paper Analysis Agent (Opus 4.5)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "target",
        nargs="?",
        default="./papers",
        help="PDF file or directory to analyze"
    )
    parser.add_argument(
        "--prompt", "-p",
        choices=["default", "quick", "methodology", "contradictions"],
        default="default",
        help="Analysis prompt type"
    )
    parser.add_argument(
        "--batch", "-b",
        action="store_true",
        help="Batch analyze with triage"
    )
    parser.add_argument(
        "--compare", "-c",
        nargs="+",
        help="Compare multiple PDFs"
    )

    args = parser.parse_args()

    try:
        if args.compare:
            # Compare mode
            pdf_paths = [Path(p) for p in args.compare]
            paper_infos = [process_pdf(p) for p in pdf_paths]
            asyncio.run(compare_papers(paper_infos))

        elif args.batch:
            # Batch mode
            target_path = Path(args.target)
            if target_path.is_dir():
                pdfs = list(target_path.glob("*.pdf"))
            else:
                pdfs = [target_path]
            asyncio.run(batch_analyze(pdfs))

        else:
            # Standard analysis
            asyncio.run(main_analyze(args.target, args.prompt))

    except KeyboardInterrupt:
        print("\n\n⏹️  Analysis interrupted by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        raise


if __name__ == "__main__":
    main()
