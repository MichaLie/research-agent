"""
Configuration for Research Paper Analyzer
==========================================
Central configuration including model selection, limits, and API keys.
"""

import os
from pathlib import Path

# =============================================================================
# MODEL CONFIGURATION
# =============================================================================

# Use Claude Opus 4.5 for best analysis quality
DEFAULT_MODEL = "claude-opus-4-5-20250514"

# Alternative models (for cost-sensitive use cases)
FAST_MODEL = "claude-sonnet-4-20250514"
HAIKU_MODEL = "claude-haiku-4-20250514"

# =============================================================================
# DIRECTORIES
# =============================================================================

BASE_DIR = Path(__file__).parent
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "analyses"
DATABASE_DIR = BASE_DIR / "data"

# Create directories
UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)
DATABASE_DIR.mkdir(exist_ok=True)

DATABASE_PATH = DATABASE_DIR / "analyses.db"

# =============================================================================
# SECURITY LIMITS
# =============================================================================

MAX_FILE_SIZE_MB = 50  # Maximum PDF file size
MAX_TEXT_LENGTH = 100000  # Maximum characters to process
MAX_UPLOADS_PER_HOUR = 20  # Rate limiting
ALLOWED_EXTENSIONS = {'.pdf'}

# =============================================================================
# API KEYS (optional - for enhanced features)
# =============================================================================

# Semantic Scholar API (free, no key needed for basic use)
SEMANTIC_SCHOLAR_API_URL = "https://api.semanticscholar.org/graph/v1"
SEMANTIC_SCHOLAR_API_KEY = os.environ.get("SEMANTIC_SCHOLAR_API_KEY", "")

# =============================================================================
# ANALYSIS SETTINGS
# =============================================================================

# Chunking settings for long papers
CHUNK_SIZE = 30000  # Characters per chunk
CHUNK_OVERLAP = 2000  # Overlap between chunks

# Citation extraction patterns
CITATION_PATTERNS = [
    r'\b(10\.\d{4,}/[^\s]+)\b',  # DOI pattern
    r'arXiv:\d{4}\.\d{4,5}',  # arXiv ID
    r'PMID:\s*\d+',  # PubMed ID
    r'PMC\d+',  # PubMed Central ID
]

# =============================================================================
# WEB UI SETTINGS
# =============================================================================

FLASK_HOST = "0.0.0.0"
FLASK_PORT = 5000
FLASK_DEBUG = False
