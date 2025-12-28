# Research Paper Analyzer

A powerful research paper analysis tool powered by **Claude Opus 4.5**. Upload PDFs via drag & drop web UI or CLI, and get comprehensive multi-stage analysis including methodology review, citation enrichment, and follow-up literature suggestions.

![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)
![Claude Opus 4.5](https://img.shields.io/badge/Claude-Opus%204.5-purple.svg)
![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)

## Features

- **Claude Opus 4.5** - Best-in-class reasoning for deep paper analysis
- **SQLite Persistence** - All analyses saved and searchable
- **Citation Enrichment** - Automatic DOI/arXiv extraction + Semantic Scholar metadata
- **Multiple Analysis Modes** - Full, Quick, Methodology, Critical analysis
- **Batch & Compare** - Analyze multiple papers or compare them side-by-side
- **Smart Chunking** - Handles very long papers without truncation
- **Rate Limiting** - Built-in security for API protection

## Analysis Pipeline

```
┌─────────────────────────────────────────────────────────────┐
│  STAGE 1: Extract & Summarize                               │
│  → Core thesis, methodology, findings, evidence quality     │
├─────────────────────────────────────────────────────────────┤
│  STAGE 2: Deep Reasoning (Opus 4.5)                         │
│  → Connections, contradictions, gaps, unstated assumptions  │
├─────────────────────────────────────────────────────────────┤
│  STAGE 3: Citation Analysis                                 │
│  → DOI/arXiv extraction, Semantic Scholar enrichment        │
├─────────────────────────────────────────────────────────────┤
│  STAGE 4: Research Directions                               │
│  → Proposes follow-up searches with rationale               │
└─────────────────────────────────────────────────────────────┘
```

## Prerequisites

- **Python 3.10+** (required by claude-agent-sdk)
- **Claude Code CLI** authenticated with your Anthropic account

## Installation

1. **Clone the repository:**
```bash
git clone https://github.com/MichaLie/research-agent.git
cd research-agent
```

2. **Install Python 3.10+ if needed:**
```bash
# macOS with Homebrew
brew install python@3.12

# Or download from python.org
```

3. **Install dependencies:**
```bash
python3.12 -m pip install -r requirements.txt
```

4. **Authenticate Claude Code CLI:**
```bash
claude
```

## Usage

### Web UI (Recommended)

```bash
./start.sh
```

Or manually:
```bash
python3.12 web_app.py
```

Open **http://localhost:5000** and drag & drop a PDF.

**Web UI Features:**
- Drag & drop PDF upload
- 4 analysis types (Full, Quick, Methodology, Critical)
- Real-time streaming results
- Citation extraction with metadata
- Analysis history sidebar
- Export to Markdown

### Command Line

```bash
# Analyze all PDFs in ./papers/
python3.12 agent.py

# Analyze PDFs in custom directory
python3.12 agent.py /path/to/papers

# Analyze a single PDF
python3.12 agent.py paper.pdf

# Batch analyze with triage
python3.12 agent.py --batch papers/

# Compare multiple papers
python3.12 agent.py --compare paper1.pdf paper2.pdf

# Use specific prompt type
python3.12 agent.py paper.pdf --prompt methodology
python3.12 agent.py paper.pdf --prompt quick
python3.12 agent.py paper.pdf --prompt contradictions
```

## Project Structure

```
research-agent/
├── agent.py              # CLI with Opus 4.5
├── web_app.py            # Web UI
├── config.py             # Central configuration
├── database.py           # SQLite persistence
├── pdf_extractor.py      # Enhanced PDF extraction
├── semantic_scholar.py   # Citation API integration
├── prompts.py            # Analysis prompts
├── start.sh              # Launch script
├── requirements.txt      # Dependencies
├── papers/               # Put your PDFs here (CLI mode)
├── uploads/              # Web UI uploads (auto-created)
├── output/               # Saved analyses (auto-created)
└── research_papers.db    # SQLite database (auto-created)
```

## Configuration

Edit `config.py` to customize:

```python
# Model (uses Opus 4.5 by default)
DEFAULT_MODEL = "claude-opus-4-5-20250514"

# Limits
MAX_FILE_SIZE_MB = 50
MAX_TEXT_LENGTH = 100000
MAX_UPLOADS_PER_HOUR = 20
CHUNK_SIZE = 30000
```

## Analysis Prompt Types

| Type | Description | Use Case |
|------|-------------|----------|
| `default` | Comprehensive 4-stage analysis | Deep understanding |
| `quick` | Fast triage summary | Literature review |
| `methodology` | Focus on research methods | Methods evaluation |
| `contradictions` | Find disagreements & gaps | Critical analysis |
| `comparison` | Compare multiple papers | Literature synthesis |
| `batch` | Triage multiple papers | Survey creation |

## Semantic Scholar Integration

The tool automatically:
1. Extracts DOIs, arXiv IDs, and PMIDs from paper text
2. Enriches citations with Semantic Scholar metadata
3. Shows citation counts, venues, and abstracts

To use the Semantic Scholar API with higher rate limits, set:
```python
# In config.py
SEMANTIC_SCHOLAR_API_KEY = "your-api-key"
```

## Database Schema

Papers and analyses are stored in SQLite (`research_papers.db`):

- **papers** - Uploaded PDFs with extracted text
- **analyses** - All analysis results
- **citations** - Extracted citations with metadata
- **comparisons** - Paper comparison results

## Troubleshooting

**"claude-agent-sdk not found"**
```bash
python3.12 -m pip install claude-agent-sdk
```

**"Requires Python 3.10+"**
```bash
brew install python@3.12
python3.12 -m pip install -r requirements.txt
```

**"Not authenticated"**
```bash
claude  # Follow the authentication prompts
```

**"Rate limit exceeded"**
Wait a few minutes or increase `MAX_UPLOADS_PER_HOUR` in config.py

## License

MIT License - feel free to use and modify!

## Acknowledgments

Built with:
- [Claude Opus 4.5](https://www.anthropic.com/claude) by Anthropic
- [Claude Agent SDK](https://github.com/anthropics/claude-agent-sdk-python)
- [PyMuPDF](https://pymupdf.readthedocs.io/) for PDF processing
- [Semantic Scholar API](https://www.semanticscholar.org/product/api) for citation data
- [Flask](https://flask.palletsprojects.com/) for the web UI
