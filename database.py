"""
Database Module for Research Paper Analyzer
============================================
SQLite persistence for analyses, papers, and citations.
"""

import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from contextlib import contextmanager

from config import DATABASE_PATH


def init_database():
    """Initialize the SQLite database with required tables."""
    with get_connection() as conn:
        cursor = conn.cursor()

        # Papers table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS papers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL,
                filepath TEXT,
                title TEXT,
                authors TEXT,
                abstract TEXT,
                text_content TEXT,
                page_count INTEGER,
                doi TEXT,
                arxiv_id TEXT,
                upload_date TEXT NOT NULL,
                file_hash TEXT UNIQUE
            )
        """)

        # Analyses table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS analyses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                analysis_id TEXT UNIQUE NOT NULL,
                paper_id INTEGER,
                status TEXT NOT NULL,
                content TEXT,
                model_used TEXT,
                prompt_type TEXT,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                error_message TEXT,
                tokens_used INTEGER,
                FOREIGN KEY (paper_id) REFERENCES papers(id)
            )
        """)

        # Citations table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS citations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                paper_id INTEGER NOT NULL,
                citation_text TEXT,
                doi TEXT,
                arxiv_id TEXT,
                pmid TEXT,
                title TEXT,
                authors TEXT,
                year INTEGER,
                venue TEXT,
                semantic_scholar_id TEXT,
                FOREIGN KEY (paper_id) REFERENCES papers(id)
            )
        """)

        # Comparisons table (for paper comparison feature)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS comparisons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                comparison_id TEXT UNIQUE NOT NULL,
                paper_ids TEXT NOT NULL,
                content TEXT,
                created_at TEXT NOT NULL
            )
        """)

        # Rate limiting table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS rate_limits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ip_address TEXT NOT NULL,
                action TEXT NOT NULL,
                timestamp TEXT NOT NULL
            )
        """)

        conn.commit()


@contextmanager
def get_connection():
    """Get a database connection with context management."""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


# =============================================================================
# PAPER OPERATIONS
# =============================================================================

def save_paper(
    filename: str,
    filepath: str,
    text_content: str,
    file_hash: str,
    title: Optional[str] = None,
    authors: Optional[str] = None,
    abstract: Optional[str] = None,
    page_count: Optional[int] = None,
    doi: Optional[str] = None,
    arxiv_id: Optional[str] = None,
) -> int:
    """Save a paper to the database. Returns paper ID."""
    with get_connection() as conn:
        cursor = conn.cursor()

        # Check if paper already exists (by hash)
        cursor.execute("SELECT id FROM papers WHERE file_hash = ?", (file_hash,))
        existing = cursor.fetchone()
        if existing:
            return existing['id']

        cursor.execute("""
            INSERT INTO papers (
                filename, filepath, title, authors, abstract, text_content,
                page_count, doi, arxiv_id, upload_date, file_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            filename, filepath, title, authors, abstract, text_content,
            page_count, doi, arxiv_id, datetime.now().isoformat(), file_hash
        ))
        conn.commit()
        return cursor.lastrowid


def get_paper(paper_id: int) -> Optional[Dict[str, Any]]:
    """Get a paper by ID."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM papers WHERE id = ?", (paper_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_paper_by_hash(file_hash: str) -> Optional[Dict[str, Any]]:
    """Get a paper by file hash."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM papers WHERE file_hash = ?", (file_hash,))
        row = cursor.fetchone()
        return dict(row) if row else None


def list_papers(limit: int = 50) -> List[Dict[str, Any]]:
    """List recent papers."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, filename, title, authors, upload_date, doi
            FROM papers ORDER BY upload_date DESC LIMIT ?
        """, (limit,))
        return [dict(row) for row in cursor.fetchall()]


# =============================================================================
# ANALYSIS OPERATIONS
# =============================================================================

def save_analysis(
    analysis_id: str,
    paper_id: int,
    status: str,
    model_used: str,
    prompt_type: str = "default",
    content: Optional[str] = None,
) -> int:
    """Save an analysis to the database. Returns analysis ID."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO analyses (
                analysis_id, paper_id, status, content, model_used,
                prompt_type, started_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            analysis_id, paper_id, status, content, model_used,
            prompt_type, datetime.now().isoformat()
        ))
        conn.commit()
        return cursor.lastrowid


def update_analysis(
    analysis_id: str,
    status: Optional[str] = None,
    content: Optional[str] = None,
    error_message: Optional[str] = None,
    tokens_used: Optional[int] = None,
):
    """Update an existing analysis."""
    with get_connection() as conn:
        cursor = conn.cursor()

        updates = []
        params = []

        if status:
            updates.append("status = ?")
            params.append(status)
            if status == "complete":
                updates.append("completed_at = ?")
                params.append(datetime.now().isoformat())
        if content:
            updates.append("content = ?")
            params.append(content)
        if error_message:
            updates.append("error_message = ?")
            params.append(error_message)
        if tokens_used:
            updates.append("tokens_used = ?")
            params.append(tokens_used)

        if updates:
            params.append(analysis_id)
            cursor.execute(f"""
                UPDATE analyses SET {', '.join(updates)}
                WHERE analysis_id = ?
            """, params)
            conn.commit()


def get_analysis(analysis_id: str) -> Optional[Dict[str, Any]]:
    """Get an analysis by ID."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM analyses WHERE analysis_id = ?", (analysis_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def list_analyses(limit: int = 50) -> List[Dict[str, Any]]:
    """List recent analyses with paper info."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT a.*, p.filename, p.title
            FROM analyses a
            LEFT JOIN papers p ON a.paper_id = p.id
            ORDER BY a.started_at DESC LIMIT ?
        """, (limit,))
        return [dict(row) for row in cursor.fetchall()]


# =============================================================================
# CITATION OPERATIONS
# =============================================================================

def save_citations(paper_id: int, citations: List[Dict[str, Any]]):
    """Save extracted citations for a paper."""
    with get_connection() as conn:
        cursor = conn.cursor()
        for cit in citations:
            cursor.execute("""
                INSERT INTO citations (
                    paper_id, citation_text, doi, arxiv_id, pmid,
                    title, authors, year, venue, semantic_scholar_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                paper_id,
                cit.get('citation_text'),
                cit.get('doi'),
                cit.get('arxiv_id'),
                cit.get('pmid'),
                cit.get('title'),
                cit.get('authors'),
                cit.get('year'),
                cit.get('venue'),
                cit.get('semantic_scholar_id'),
            ))
        conn.commit()


def get_citations(paper_id: int) -> List[Dict[str, Any]]:
    """Get citations for a paper."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM citations WHERE paper_id = ?", (paper_id,))
        return [dict(row) for row in cursor.fetchall()]


# =============================================================================
# RATE LIMITING
# =============================================================================

def check_rate_limit(ip_address: str, action: str, max_per_hour: int) -> bool:
    """Check if an action is rate limited. Returns True if allowed."""
    with get_connection() as conn:
        cursor = conn.cursor()

        # Count actions in the last hour
        one_hour_ago = datetime.now().isoformat()[:13]  # Rough hour check
        cursor.execute("""
            SELECT COUNT(*) as count FROM rate_limits
            WHERE ip_address = ? AND action = ? AND timestamp > ?
        """, (ip_address, action, one_hour_ago))

        count = cursor.fetchone()['count']

        if count >= max_per_hour:
            return False

        # Record this action
        cursor.execute("""
            INSERT INTO rate_limits (ip_address, action, timestamp)
            VALUES (?, ?, ?)
        """, (ip_address, action, datetime.now().isoformat()))
        conn.commit()

        return True


# =============================================================================
# COMPARISON OPERATIONS
# =============================================================================

def save_comparison(comparison_id: str, paper_ids: List[int], content: str):
    """Save a paper comparison."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO comparisons (comparison_id, paper_ids, content, created_at)
            VALUES (?, ?, ?, ?)
        """, (comparison_id, json.dumps(paper_ids), content, datetime.now().isoformat()))
        conn.commit()


def get_comparison(comparison_id: str) -> Optional[Dict[str, Any]]:
    """Get a comparison by ID."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM comparisons WHERE comparison_id = ?", (comparison_id,))
        row = cursor.fetchone()
        if row:
            result = dict(row)
            result['paper_ids'] = json.loads(result['paper_ids'])
            return result
        return None


# Initialize database on import
init_database()
