#!/usr/bin/env python3
"""
Research Paper Analysis Agent
=============================
A multi-stage agent that analyzes PDFs, performs deep reasoning,
and proactively suggests follow-up literature searches.

Usage:
    python agent.py                     # Analyze PDFs in ./papers
    python agent.py /path/to/papers     # Analyze PDFs in custom directory
    python agent.py paper.pdf           # Analyze a single PDF
"""

import asyncio
import sys
from pathlib import Path

import fitz  # PyMuPDF

from claude_agent_sdk import query, ClaudeAgentOptions, AssistantMessage, ResultMessage

from prompts import RESEARCH_ANALYSIS_PROMPT


def extract_text_from_pdf(pdf_path: Path) -> str:
    """Extract text content from a PDF file."""
    doc = fitz.open(pdf_path)
    text_parts = []
    for page_num, page in enumerate(doc, 1):
        text = page.get_text()
        if text.strip():
            text_parts.append(f"--- Page {page_num} ---\n{text}")
    doc.close()
    return "\n\n".join(text_parts)


def preprocess_pdfs(target_path: Path) -> Path:
    """
    Convert PDFs to text files for processing.
    Returns path to directory containing extracted text files.
    """
    text_dir = target_path.parent / "papers_text"
    text_dir.mkdir(exist_ok=True)

    if target_path.is_file():
        pdfs = [target_path]
    else:
        pdfs = list(target_path.glob("*.pdf"))

    for pdf_path in pdfs:
        text_file = text_dir / f"{pdf_path.stem}.txt"
        if not text_file.exists() or text_file.stat().st_mtime < pdf_path.stat().st_mtime:
            print(f"📄 Extracting text from: {pdf_path.name}")
            text = extract_text_from_pdf(pdf_path)
            text_file.write_text(text, encoding="utf-8")
            print(f"   ✓ Saved to: {text_file.name} ({len(text):,} chars)")

    return text_dir


async def analyze_papers(target: str = "./papers"):
    """
    Main agent loop - analyzes PDFs and streams output.

    Args:
        target: Path to a PDF file or directory containing PDFs
    """
    target_path = Path(target).resolve()

    if not target_path.exists():
        print(f"Error: {target} not found")
        sys.exit(1)

    print("=" * 60)
    print("🔬 RESEARCH PAPER ANALYSIS AGENT")
    print("=" * 60)
    print(f"📂 Target: {target_path}")
    print("=" * 60 + "\n")

    # Preprocess PDFs to text files
    print("📋 Preprocessing PDFs...\n")
    text_dir = preprocess_pdfs(target_path)
    print(f"\n✓ Text files ready in: {text_dir}\n")

    context = f"Analyze all research papers in this directory: {text_dir}"
    full_prompt = f"{context}\n\n{RESEARCH_ANALYSIS_PROMPT}"

    try:
        async for message in query(
            prompt=full_prompt,
            options=ClaudeAgentOptions(
                allowed_tools=[
                    "Read",       # Read PDF contents
                    "Glob",       # Find PDF files
                    "Grep",       # Search within documents
                    "WebSearch",  # Search for related literature
                    "WebFetch",   # Fetch paper abstracts/details
                    "Write",      # Save analysis reports
                ],
                # "default" mode asks for approval before web searches
                # Change to "acceptEdits" to auto-approve everything except bash
                permission_mode="default"
            )
        ):
            handle_message(message)

    except KeyboardInterrupt:
        print("\n\n⏹️  Analysis interrupted by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        raise


def handle_message(message):
    """Process and display agent messages."""
    if isinstance(message, AssistantMessage):
        for block in message.content:
            if hasattr(block, "text") and block.text:
                print(block.text)
            elif hasattr(block, "name"):
                # Tool usage indicator
                print(f"\n🔧 Using tool: {block.name}")

    elif isinstance(message, ResultMessage):
        if message.subtype == "success":
            print("\n" + "=" * 60)
            print("✅ Analysis complete!")
            print("=" * 60)
        elif message.subtype == "error":
            print(f"\n❌ Error: {message}")


def main():
    """Entry point - parse args and run agent."""
    if len(sys.argv) > 1:
        target = sys.argv[1]
    else:
        target = "./papers"

    asyncio.run(analyze_papers(target))


if __name__ == "__main__":
    main()
