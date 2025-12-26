# Research Paper Analyzer

A drag & drop web interface for analyzing research papers using Claude AI. Upload a PDF and get a comprehensive multi-stage analysis including methodology review, critical gaps, and suggested follow-up literature searches.

![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)
![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)

## What It Does

```
┌─────────────────────────────────────────────────────────────┐
│  STAGE 1: Extract & Summarize                               │
│  → Core thesis, methodology, findings, evidence quality     │
├─────────────────────────────────────────────────────────────┤
│  STAGE 2: Deep Reasoning                                    │
│  → Connections, contradictions, gaps, unstated assumptions  │
├─────────────────────────────────────────────────────────────┤
│  STAGE 3: Research Directions                               │
│  → Proposes follow-up searches with rationale               │
├─────────────────────────────────────────────────────────────┤
│  STAGE 4: Interactive Exploration                           │
│  → Executes searches (with your approval) & synthesizes     │
└─────────────────────────────────────────────────────────────┘
```

## Prerequisites

- **Python 3.10+** (required by claude-agent-sdk)
- **Claude Code CLI** authenticated with your Anthropic account

## Installation

1. **Clone the repository:**
```bash
git clone https://github.com/YOUR_USERNAME/research-agent.git
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
This will guide you through authentication if needed.

## Usage

### Web UI (Recommended)

```bash
./start.sh
```

Or manually:
```bash
python3.12 web_app.py
```

Then open **http://localhost:5000** in your browser and drag & drop a PDF.

**Features:**
- Drag & drop PDF upload
- Real-time analysis progress
- Beautiful formatted results
- Export to Markdown
- View previous analyses

### Command Line

```bash
python3.12 agent.py                     # Analyze all PDFs in ./papers/
python3.12 agent.py /path/to/papers     # Analyze PDFs in custom directory
python3.12 agent.py paper.pdf           # Analyze a single PDF
```

## Project Structure

```
research-agent/
├── agent.py          # CLI version
├── web_app.py        # Web UI version
├── prompts.py        # Analysis prompts (customizable)
├── start.sh          # Launch script
├── requirements.txt  # Dependencies
├── papers/           # Put your PDFs here (CLI mode)
├── uploads/          # Web UI uploads (auto-created)
└── analyses/         # Saved analyses (auto-created)
```

## Customizing the Analysis

Edit `prompts.py` to customize the analysis. Available prompts:

- `RESEARCH_ANALYSIS_PROMPT` - Comprehensive 4-stage analysis (default)
- `QUICK_SUMMARY_PROMPT` - Fast triage mode
- `METHODOLOGY_FOCUS_PROMPT` - Deep dive on research methods
- `CONTRADICTION_FINDER_PROMPT` - Find disagreements between papers

To switch prompts, edit the import in `agent.py` or `web_app.py`:

```python
from prompts import METHODOLOGY_FOCUS_PROMPT as RESEARCH_ANALYSIS_PROMPT
```

## How It Works

1. PDFs are converted to text using PyMuPDF (handles large files)
2. Text is sent to Claude via the Claude Agent SDK
3. Claude analyzes using the configured prompt
4. Results stream in real-time and are saved as markdown

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

## License

MIT License - feel free to use and modify!

## Acknowledgments

Built with:
- [Claude Agent SDK](https://github.com/anthropics/claude-agent-sdk-python) by Anthropic
- [PyMuPDF](https://pymupdf.readthedocs.io/) for PDF processing
- [Flask](https://flask.palletsprojects.com/) for the web UI
