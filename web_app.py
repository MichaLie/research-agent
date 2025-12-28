#!/usr/bin/env python3
"""
Research Paper Analysis - Web UI
================================
A drag & drop interface for analyzing research papers with Claude Opus 4.5.

Features:
- Single paper analysis with multiple prompt types
- Batch upload and analysis
- Paper comparison mode
- Citation extraction and enrichment
- Analysis history with SQLite persistence
- Rate limiting and file size limits

Usage:
    python web_app.py
    Then open http://localhost:5000 in your browser
"""

import asyncio
import os
from datetime import datetime
from pathlib import Path
from threading import Thread
from functools import wraps

from flask import Flask, render_template_string, request, jsonify, send_file

from claude_agent_sdk import query, ClaudeAgentOptions, AssistantMessage, ResultMessage

from config import (
    DEFAULT_MODEL,
    UPLOAD_DIR,
    OUTPUT_DIR,
    MAX_FILE_SIZE_MB,
    MAX_TEXT_LENGTH,
    MAX_UPLOADS_PER_HOUR,
    FLASK_HOST,
    FLASK_PORT,
    FLASK_DEBUG,
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
)
from database import (
    save_paper,
    save_analysis,
    update_analysis,
    get_analysis,
    list_analyses,
    save_citations,
    get_citations,
    get_paper_by_hash,
    get_paper,
    check_rate_limit,
    save_comparison,
)
from semantic_scholar import batch_enrich_citations

app = Flask(__name__)

# In-memory store for active analyses (for real-time updates)
active_analyses = {}


def get_client_ip():
    """Get client IP address."""
    return request.headers.get('X-Forwarded-For', request.remote_addr)


async def run_analysis(pdf_path: Path, analysis_id: str, prompt_type: str = "default"):
    """Run the analysis agent and collect results."""
    active_analyses[analysis_id] = {
        "status": "extracting",
        "content": "",
        "filename": pdf_path.name,
        "started": datetime.now().isoformat(),
        "model": DEFAULT_MODEL,
    }

    try:
        # Extract PDF content
        paper = extract_pdf(pdf_path)
        formatted_text = format_paper_for_analysis(paper)

        # Save paper to database
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

        # Extract and enrich citations
        citations = extract_citations_from_text(paper.text)
        if citations:
            citations = batch_enrich_citations(citations, max_enrichments=10)
            save_citations(paper_id, citations)

        active_analyses[analysis_id]["paper_id"] = paper_id
        active_analyses[analysis_id]["title"] = paper.title
        active_analyses[analysis_id]["doi"] = paper.doi
        active_analyses[analysis_id]["citations_count"] = len(citations)

        # Save analysis record
        save_analysis(
            analysis_id=analysis_id,
            paper_id=paper_id,
            status="analyzing",
            model_used=DEFAULT_MODEL,
            prompt_type=prompt_type,
        )

        active_analyses[analysis_id]["status"] = "analyzing"

        # Handle long papers with chunking
        text = formatted_text
        if len(text) > MAX_TEXT_LENGTH:
            chunks = chunk_text(text, 30000)
            text = chunks[0]
            text += f"\n\n[Note: Long paper truncated. Showing {len(text):,} of {len(formatted_text):,} characters.]"

        # Build prompt
        prompt = get_prompt(prompt_type)
        full_prompt = f"Analyze this research paper:\n\n{text}\n\n{prompt}"

        # Run analysis with Opus 4.5
        content_parts = []
        async for message in query(
            prompt=full_prompt,
            options=ClaudeAgentOptions(
                model=DEFAULT_MODEL,
                allowed_tools=["WebSearch", "WebFetch"],
                permission_mode="acceptEdits"
            )
        ):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if hasattr(block, "text") and block.text:
                        content_parts.append(block.text)
                        active_analyses[analysis_id]["content"] = "\n\n".join(content_parts)

        # Save final result
        final_content = "\n\n".join(content_parts)

        # Save to markdown file
        output_file = OUTPUT_DIR / f"{pdf_path.stem}_analysis.md"
        md_content = f"""# Analysis: {paper.title or pdf_path.name}

**Model:** {DEFAULT_MODEL}
**Generated:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
**Prompt Type:** {prompt_type}
{f"**DOI:** {paper.doi}" if paper.doi else ""}

---

{final_content}
"""
        output_file.write_text(md_content, encoding="utf-8")

        # Update database
        update_analysis(
            analysis_id=analysis_id,
            status="complete",
            content=final_content,
        )

        active_analyses[analysis_id]["status"] = "complete"
        active_analyses[analysis_id]["content"] = final_content
        active_analyses[analysis_id]["output_file"] = str(output_file)

    except Exception as e:
        active_analyses[analysis_id]["status"] = "error"
        active_analyses[analysis_id]["error"] = str(e)
        update_analysis(
            analysis_id=analysis_id,
            status="error",
            error_message=str(e),
        )


def run_async_analysis(pdf_path: Path, analysis_id: str, prompt_type: str = "default"):
    """Run async analysis in a thread."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(run_analysis(pdf_path, analysis_id, prompt_type))
    loop.close()


# =============================================================================
# HTML TEMPLATE
# =============================================================================

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Research Paper Analyzer - Opus 4.5</title>
    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #f8fafc 0%, #e2e8f0 100%);
            min-height: 100vh;
            color: #1e293b;
        }
        .container { max-width: 1400px; margin: 0 auto; padding: 2rem; }

        header {
            text-align: center;
            margin-bottom: 2rem;
        }
        h1 {
            font-size: 2.5rem;
            background: linear-gradient(90deg, #7c3aed, #ec4899);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 0.5rem;
        }
        .subtitle {
            color: #64748b;
            font-size: 1rem;
        }
        .model-badge {
            display: inline-block;
            background: rgba(124, 58, 237, 0.1);
            border: 1px solid #7c3aed;
            color: #7c3aed;
            padding: 0.25rem 0.75rem;
            border-radius: 20px;
            font-size: 0.8rem;
            margin-top: 0.5rem;
        }

        .main-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 2rem;
        }
        @media (max-width: 1024px) {
            .main-grid { grid-template-columns: 1fr; }
        }

        .panel {
            background: #ffffff;
            border-radius: 16px;
            padding: 1.5rem;
            border: 1px solid #e2e8f0;
            box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1);
        }
        .panel-title {
            font-size: 1.2rem;
            margin-bottom: 1rem;
            display: flex;
            align-items: center;
            gap: 0.5rem;
            color: #334155;
        }

        .drop-zone {
            border: 2px dashed #7c3aed;
            border-radius: 12px;
            padding: 3rem 2rem;
            text-align: center;
            transition: all 0.3s ease;
            cursor: pointer;
            background: #faf5ff;
        }
        .drop-zone:hover, .drop-zone.dragover {
            border-color: #6d28d9;
            background: #f3e8ff;
        }
        .drop-zone-icon { font-size: 3rem; margin-bottom: 1rem; }
        .drop-zone input { display: none; }

        .options-row {
            display: flex;
            gap: 1rem;
            margin-top: 1rem;
            flex-wrap: wrap;
        }
        .option-group { flex: 1; min-width: 200px; }
        .option-group label {
            display: block;
            font-size: 0.85rem;
            color: #64748b;
            margin-bottom: 0.5rem;
        }
        select, input[type="text"] {
            width: 100%;
            padding: 0.75rem;
            border-radius: 8px;
            border: 1px solid #cbd5e1;
            background: #ffffff;
            color: #1e293b;
            font-size: 1rem;
        }
        select:focus, input:focus {
            outline: none;
            border-color: #7c3aed;
            box-shadow: 0 0 0 3px rgba(124, 58, 237, 0.1);
        }

        .btn {
            padding: 0.75rem 1.5rem;
            border-radius: 8px;
            border: none;
            font-size: 1rem;
            cursor: pointer;
            transition: all 0.2s;
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
        }
        .btn-primary {
            background: linear-gradient(90deg, #7c3aed, #ec4899);
            color: white;
        }
        .btn-primary:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 20px rgba(124, 58, 237, 0.4);
        }
        .btn-secondary {
            background: #f1f5f9;
            color: #475569;
            border: 1px solid #cbd5e1;
        }
        .btn-secondary:hover { background: #e2e8f0; }

        .status {
            padding: 1rem;
            border-radius: 8px;
            margin: 1rem 0;
            display: none;
        }
        .status.visible { display: block; }
        .status.analyzing {
            background: #f3e8ff;
            border: 1px solid #7c3aed;
            color: #6d28d9;
        }
        .status.complete {
            background: #dcfce7;
            border: 1px solid #22c55e;
            color: #166534;
        }
        .status.error {
            background: #fee2e2;
            border: 1px solid #ef4444;
            color: #dc2626;
        }

        .result-content {
            background: #f8fafc;
            border-radius: 12px;
            padding: 1.5rem;
            max-height: 60vh;
            overflow-y: auto;
            line-height: 1.7;
            border: 1px solid #e2e8f0;
        }
        .result-content h1, .result-content h2, .result-content h3 {
            color: #7c3aed;
            margin-top: 1.5rem;
            margin-bottom: 0.75rem;
        }
        .result-content h1 { font-size: 1.5rem; }
        .result-content h2 { font-size: 1.25rem; }
        .result-content p { margin-bottom: 1rem; }
        .result-content ul, .result-content ol {
            margin-left: 1.5rem;
            margin-bottom: 1rem;
        }
        .result-content table {
            width: 100%;
            border-collapse: collapse;
            margin: 1rem 0;
        }
        .result-content th, .result-content td {
            border: 1px solid #e2e8f0;
            padding: 0.5rem;
            text-align: left;
        }
        .result-content th { background: #f3e8ff; color: #6d28d9; }
        .result-content blockquote {
            border-left: 3px solid #7c3aed;
            padding-left: 1rem;
            margin: 1rem 0;
            color: #64748b;
            background: #faf5ff;
        }
        .result-content code {
            background: #f1f5f9;
            padding: 0.2rem 0.4rem;
            border-radius: 4px;
            font-family: monospace;
            color: #7c3aed;
        }

        .history-list {
            max-height: 300px;
            overflow-y: auto;
        }
        .history-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 0.75rem;
            background: #f8fafc;
            border-radius: 8px;
            margin-bottom: 0.5rem;
            cursor: pointer;
            transition: background 0.2s;
            border: 1px solid #e2e8f0;
        }
        .history-item:hover { background: #f3e8ff; border-color: #7c3aed; }
        .history-item-title { font-weight: 500; color: #334155; }
        .history-item-meta { font-size: 0.8rem; color: #64748b; }

        .spinner {
            display: inline-block;
            width: 16px;
            height: 16px;
            border: 2px solid #e2e8f0;
            border-radius: 50%;
            border-top-color: #7c3aed;
            animation: spin 1s linear infinite;
        }
        @keyframes spin { to { transform: rotate(360deg); } }

        .citations-panel {
            margin-top: 1rem;
            padding: 1rem;
            background: #f8fafc;
            border-radius: 8px;
            border: 1px solid #e2e8f0;
        }
        .citation-item {
            padding: 0.5rem 0;
            border-bottom: 1px solid #e2e8f0;
        }
        .citation-item:last-child { border-bottom: none; }

        .tabs {
            display: flex;
            gap: 0.5rem;
            margin-bottom: 1rem;
        }
        .tab {
            padding: 0.5rem 1rem;
            border-radius: 8px;
            cursor: pointer;
            background: #f1f5f9;
            color: #475569;
            transition: all 0.2s;
        }
        .tab:hover { background: #e2e8f0; }
        .tab.active {
            background: #7c3aed;
            color: white;
        }

        .chat-section {
            margin-top: 1.5rem;
            border-top: 1px solid #e2e8f0;
            padding-top: 1rem;
        }
        .chat-messages {
            max-height: 300px;
            overflow-y: auto;
            margin-bottom: 1rem;
            padding: 1rem;
            background: #f8fafc;
            border-radius: 8px;
            border: 1px solid #e2e8f0;
        }
        .chat-message {
            margin-bottom: 1rem;
            padding: 0.75rem 1rem;
            border-radius: 12px;
        }
        .chat-message.user {
            background: #7c3aed;
            color: white;
            margin-left: 20%;
        }
        .chat-message.assistant {
            background: #ffffff;
            border: 1px solid #e2e8f0;
            margin-right: 10%;
        }
        .chat-message.assistant p { margin-bottom: 0.5rem; }
        .chat-message.assistant p:last-child { margin-bottom: 0; }
        .chat-input-row {
            display: flex;
            gap: 0.5rem;
        }
        .chat-input-row input {
            flex: 1;
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>Research Paper Analyzer</h1>
            <p class="subtitle">Deep analysis powered by Claude</p>
            <span class="model-badge">🧠 Opus 4.5</span>
        </header>

        <div class="main-grid">
            <div class="left-column">
                <div class="panel">
                    <div class="panel-title">📄 Upload Paper</div>

                    <div class="drop-zone" id="dropZone">
                        <div class="drop-zone-icon">📄</div>
                        <div>Drag & drop PDF here<br><small>or click to select (max """ + str(MAX_FILE_SIZE_MB) + """MB)</small></div>
                        <input type="file" id="fileInput" accept=".pdf" multiple>
                    </div>

                    <div class="options-row">
                        <div class="option-group">
                            <label>Analysis Type</label>
                            <select id="promptType">
                                <option value="default">Full Analysis (4 stages)</option>
                                <option value="quick">Quick Summary</option>
                                <option value="methodology">Methodology Focus</option>
                                <option value="contradictions">Critical Analysis</option>
                                <option value="brutal">Brutal Critic (Reviewer 2 Mode)</option>
                            </select>
                        </div>
                    </div>

                    <div class="status" id="status"></div>
                </div>

                <div class="panel" style="margin-top: 1rem;">
                    <div class="panel-title">📚 Analysis History</div>
                    <div class="history-list" id="historyList">
                        <div style="color: #a1a1aa; text-align: center; padding: 2rem;">
                            Loading history...
                        </div>
                    </div>
                </div>
            </div>

            <div class="right-column">
                <div class="panel" id="resultPanel" style="display: none;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem;">
                        <div class="panel-title" id="resultTitle">📊 Analysis Result</div>
                        <button class="btn btn-secondary" id="exportBtn">📥 Export</button>
                    </div>

                    <div class="tabs">
                        <div class="tab active" data-tab="analysis">Analysis</div>
                        <div class="tab" data-tab="citations">Citations</div>
                        <div class="tab" data-tab="metadata">Metadata</div>
                    </div>

                    <div id="analysisTab" class="result-content"></div>
                    <div id="citationsTab" class="result-content" style="display: none;"></div>
                    <div id="metadataTab" class="result-content" style="display: none;"></div>

                    <div class="chat-section" id="chatSection" style="display: none;">
                        <div class="panel-title" style="margin-top: 1.5rem;">💬 Chat About This Paper</div>
                        <div class="chat-messages" id="chatMessages"></div>
                        <div class="chat-input-row">
                            <input type="text" id="chatInput" placeholder="Ask a follow-up question about this paper..." />
                            <button class="btn btn-primary" id="chatSendBtn">Send</button>
                        </div>
                    </div>
                </div>

                <div class="panel" id="welcomePanel">
                    <div style="text-align: center; padding: 3rem; color: #a1a1aa;">
                        <div style="font-size: 4rem; margin-bottom: 1rem;">🔬</div>
                        <h2 style="color: #e4e4e7; margin-bottom: 1rem;">Welcome to Research Paper Analyzer</h2>
                        <p>Upload a PDF to get started with AI-powered paper analysis.</p>
                        <div style="margin-top: 2rem; text-align: left; max-width: 400px; margin-left: auto; margin-right: auto;">
                            <p><strong>Features:</strong></p>
                            <ul style="margin-top: 0.5rem; margin-left: 1.5rem;">
                                <li>Multi-stage deep analysis</li>
                                <li>Citation extraction & enrichment</li>
                                <li>Literature search suggestions</li>
                                <li>Multiple analysis modes</li>
                                <li>Persistent history</li>
                            </ul>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        const dropZone = document.getElementById('dropZone');
        const fileInput = document.getElementById('fileInput');
        const promptType = document.getElementById('promptType');
        const status = document.getElementById('status');
        const resultPanel = document.getElementById('resultPanel');
        const welcomePanel = document.getElementById('welcomePanel');
        const analysisTab = document.getElementById('analysisTab');
        const citationsTab = document.getElementById('citationsTab');
        const metadataTab = document.getElementById('metadataTab');
        const exportBtn = document.getElementById('exportBtn');
        const historyList = document.getElementById('historyList');

        let currentAnalysisId = null;
        let currentData = null;
        const chatSection = document.getElementById('chatSection');
        const chatMessages = document.getElementById('chatMessages');
        const chatInput = document.getElementById('chatInput');
        const chatSendBtn = document.getElementById('chatSendBtn');

        // Tab switching
        document.querySelectorAll('.tab').forEach(tab => {
            tab.addEventListener('click', () => {
                document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
                tab.classList.add('active');

                const tabName = tab.dataset.tab;
                analysisTab.style.display = tabName === 'analysis' ? 'block' : 'none';
                citationsTab.style.display = tabName === 'citations' ? 'block' : 'none';
                metadataTab.style.display = tabName === 'metadata' ? 'block' : 'none';
            });
        });

        // Drag & drop
        dropZone.addEventListener('click', () => fileInput.click());
        dropZone.addEventListener('dragover', e => { e.preventDefault(); dropZone.classList.add('dragover'); });
        dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));
        dropZone.addEventListener('drop', e => {
            e.preventDefault();
            dropZone.classList.remove('dragover');
            const file = e.dataTransfer.files[0];
            if (file && file.type === 'application/pdf') uploadFile(file);
        });
        fileInput.addEventListener('change', () => {
            if (fileInput.files[0]) uploadFile(fileInput.files[0]);
        });

        async function uploadFile(file) {
            // Check file size
            if (file.size > """ + str(MAX_FILE_SIZE_MB * 1024 * 1024) + """) {
                showStatus('error', 'File too large. Maximum size is """ + str(MAX_FILE_SIZE_MB) + """MB.');
                return;
            }

            const formData = new FormData();
            formData.append('file', file);
            formData.append('prompt_type', promptType.value);

            showStatus('analyzing', '<span class="spinner"></span> Uploading and analyzing with Opus 4.5...');
            welcomePanel.style.display = 'none';
            resultPanel.style.display = 'block';
            analysisTab.innerHTML = '<div style="text-align: center; padding: 2rem;"><span class="spinner"></span> Extracting PDF content...</div>';

            try {
                const response = await fetch('/upload', { method: 'POST', body: formData });
                const data = await response.json();

                if (data.error) {
                    showStatus('error', data.error);
                    return;
                }

                currentAnalysisId = data.analysis_id;
                pollStatus();
            } catch (error) {
                showStatus('error', 'Upload failed: ' + error.message);
            }
        }

        async function pollStatus() {
            if (!currentAnalysisId) return;

            try {
                const response = await fetch(`/status/${currentAnalysisId}`);
                const data = await response.json();
                currentData = data;

                if (data.status === 'extracting') {
                    showStatus('analyzing', '<span class="spinner"></span> Extracting PDF content...');
                    analysisTab.innerHTML = '<div style="text-align: center; padding: 2rem;"><span class="spinner"></span> Extracting text, tables, and citations...</div>';
                    setTimeout(pollStatus, 1000);
                } else if (data.status === 'analyzing') {
                    showStatus('analyzing', '<span class="spinner"></span> Analyzing with Claude Opus 4.5...');
                    if (data.content) {
                        analysisTab.innerHTML = marked.parse(data.content);
                    }
                    setTimeout(pollStatus, 2000);
                } else if (data.status === 'complete') {
                    showStatus('complete', '✅ Analysis complete!');
                    analysisTab.innerHTML = marked.parse(data.content);
                    document.getElementById('resultTitle').textContent = '📊 ' + (data.title || data.filename);

                    // Update citations tab
                    if (data.citations_count > 0) {
                        citationsTab.innerHTML = `<p><strong>${data.citations_count} citations extracted</strong></p><p>Citation enrichment via Semantic Scholar API.</p>`;
                    } else {
                        citationsTab.innerHTML = '<p>No citation identifiers found in this paper.</p>';
                    }

                    // Update metadata tab
                    metadataTab.innerHTML = `
                        <p><strong>File:</strong> ${data.filename}</p>
                        ${data.title ? `<p><strong>Title:</strong> ${data.title}</p>` : ''}
                        ${data.doi ? `<p><strong>DOI:</strong> ${data.doi}</p>` : ''}
                        <p><strong>Model:</strong> ${data.model}</p>
                        <p><strong>Analyzed:</strong> ${data.started}</p>
                    `;

                    // Enable chat
                    chatSection.style.display = 'block';
                    chatMessages.innerHTML = '<div style="color: #64748b; text-align: center;">Ask follow-up questions about this paper...</div>';

                    loadHistory();
                } else if (data.status === 'error') {
                    showStatus('error', 'Error: ' + data.error);
                }
            } catch (error) {
                showStatus('error', 'Status check failed: ' + error.message);
            }
        }

        function showStatus(type, message) {
            status.className = `status visible ${type}`;
            status.innerHTML = message;
        }

        exportBtn.addEventListener('click', () => {
            if (!currentData || !currentData.content) return;

            const blob = new Blob([`# Analysis: ${currentData.title || currentData.filename}\\n\\n${currentData.content}`], { type: 'text/markdown' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = (currentData.filename || 'analysis').replace('.pdf', '_analysis.md');
            a.click();
            URL.revokeObjectURL(url);
        });

        async function loadHistory() {
            try {
                const response = await fetch('/history');
                const data = await response.json();

                if (data.analyses && data.analyses.length > 0) {
                    historyList.innerHTML = data.analyses.map(a => `
                        <div class="history-item" onclick="loadAnalysis('${a.analysis_id}')">
                            <div>
                                <div class="history-item-title">${a.title || a.filename || 'Unknown'}</div>
                                <div class="history-item-meta">${a.prompt_type} • ${a.started_at?.split('T')[0] || 'Unknown date'}</div>
                            </div>
                            <div class="history-item-meta">${a.status}</div>
                        </div>
                    `).join('');
                } else {
                    historyList.innerHTML = '<div style="color: #a1a1aa; text-align: center; padding: 2rem;">No analyses yet</div>';
                }
            } catch (e) {
                historyList.innerHTML = '<div style="color: #a1a1aa; text-align: center; padding: 2rem;">Failed to load history</div>';
            }
        }

        async function loadAnalysis(analysisId) {
            try {
                const response = await fetch(`/analysis/${analysisId}`);
                const data = await response.json();

                if (data.content) {
                    currentData = data;
                    currentAnalysisId = analysisId;
                    welcomePanel.style.display = 'none';
                    resultPanel.style.display = 'block';
                    analysisTab.innerHTML = marked.parse(data.content);
                    document.getElementById('resultTitle').textContent = '📊 ' + (data.title || data.filename || 'Analysis');
                    showStatus('complete', '✅ Loaded from history');

                    // Enable chat
                    chatSection.style.display = 'block';
                    chatMessages.innerHTML = '<div style="color: #64748b; text-align: center;">Ask follow-up questions about this paper...</div>';
                }
            } catch (e) {
                showStatus('error', 'Failed to load analysis');
            }
        }

        // Chat functionality
        chatSendBtn.addEventListener('click', sendChat);
        chatInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') sendChat();
        });

        async function sendChat() {
            const question = chatInput.value.trim();
            if (!question || !currentData) return;

            // Add user message
            const userMsg = document.createElement('div');
            userMsg.className = 'chat-message user';
            userMsg.textContent = question;
            chatMessages.innerHTML = '';  // Clear placeholder if present
            chatMessages.appendChild(userMsg);
            chatInput.value = '';

            // Add loading indicator
            const loadingMsg = document.createElement('div');
            loadingMsg.className = 'chat-message assistant';
            loadingMsg.innerHTML = '<span class="spinner"></span> Thinking...';
            chatMessages.appendChild(loadingMsg);
            chatMessages.scrollTop = chatMessages.scrollHeight;

            try {
                const response = await fetch('/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        analysis_id: currentAnalysisId,
                        question: question
                    })
                });
                const data = await response.json();

                loadingMsg.innerHTML = marked.parse(data.response || data.error || 'No response');
                chatMessages.scrollTop = chatMessages.scrollHeight;
            } catch (error) {
                loadingMsg.innerHTML = 'Error: ' + error.message;
            }
        }

        // Load history on page load
        loadHistory();
    </script>
</body>
</html>
"""


# =============================================================================
# ROUTES
# =============================================================================

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)


@app.route('/upload', methods=['POST'])
def upload():
    # Rate limiting
    if not check_rate_limit(get_client_ip(), "upload", MAX_UPLOADS_PER_HOUR):
        return jsonify({"error": f"Rate limit exceeded. Max {MAX_UPLOADS_PER_HOUR} uploads per hour."}), 429

    if 'file' not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files['file']
    if not file.filename.endswith('.pdf'):
        return jsonify({"error": "Only PDF files are supported"}), 400

    # Check file size
    file.seek(0, 2)
    size = file.tell()
    file.seek(0)
    if size > MAX_FILE_SIZE_MB * 1024 * 1024:
        return jsonify({"error": f"File too large. Maximum size is {MAX_FILE_SIZE_MB}MB."}), 400

    # Save the file
    pdf_path = UPLOAD_DIR / file.filename
    file.save(pdf_path)

    # Get prompt type
    prompt_type = request.form.get('prompt_type', 'default')

    # Generate analysis ID
    analysis_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{pdf_path.stem}"

    # Start analysis in background thread
    thread = Thread(target=run_async_analysis, args=(pdf_path, analysis_id, prompt_type))
    thread.start()

    return jsonify({"analysis_id": analysis_id})


@app.route('/status/<analysis_id>')
def get_status(analysis_id):
    # Check active analyses first
    if analysis_id in active_analyses:
        return jsonify(active_analyses[analysis_id])

    # Check database
    db_analysis = get_analysis(analysis_id)
    if db_analysis:
        return jsonify(db_analysis)

    return jsonify({"error": "Analysis not found"}), 404


@app.route('/analysis/<analysis_id>')
def get_analysis_detail(analysis_id):
    db_analysis = get_analysis(analysis_id)
    if db_analysis:
        # Get paper info if available
        if db_analysis.get('paper_id'):
            paper = get_paper(db_analysis['paper_id'])
            if paper:
                db_analysis['title'] = paper.get('title')
                db_analysis['doi'] = paper.get('doi')
                db_analysis['filename'] = paper.get('filename')
        return jsonify(db_analysis)
    return jsonify({"error": "Analysis not found"}), 404


@app.route('/history')
def get_history():
    analyses = list_analyses(limit=50)
    return jsonify({"analyses": analyses})


@app.route('/files')
def list_files():
    files = [f.name for f in OUTPUT_DIR.glob("*.md")]
    return jsonify({"files": sorted(files, reverse=True)})


@app.route('/download/<filename>')
def download_file(filename):
    file_path = OUTPUT_DIR / filename
    if file_path.exists():
        return send_file(file_path, as_attachment=True)
    return jsonify({"error": "File not found"}), 404


@app.route('/chat', methods=['POST'])
def chat():
    """Handle follow-up questions about a paper."""
    data = request.get_json()
    analysis_id = data.get('analysis_id')
    question = data.get('question')

    if not analysis_id or not question:
        return jsonify({"error": "Missing analysis_id or question"}), 400

    # Get the analysis and paper content
    db_analysis = get_analysis(analysis_id)
    if not db_analysis:
        return jsonify({"error": "Analysis not found"}), 404

    paper_summary = ""
    if db_analysis.get('paper_id'):
        paper = get_paper(db_analysis['paper_id'])
        if paper:
            paper_summary = paper.get('text_content', '')[:15000]  # Limit context

    previous_analysis = db_analysis.get('content', '')[:8000]

    # Format chat prompt
    from prompts import format_chat_prompt
    chat_prompt = format_chat_prompt(paper_summary, previous_analysis, question)

    # Run chat query with Claude
    try:
        import asyncio
        from claude_agent_sdk import query, ClaudeAgentOptions, AssistantMessage

        async def get_response():
            content_parts = []
            async for message in query(
                prompt=chat_prompt,
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
            return "\\n\\n".join(content_parts)

        response = asyncio.run(get_response())
        return jsonify({"response": response})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# =============================================================================
# MAIN
# =============================================================================

if __name__ == '__main__':
    print("\n" + "=" * 60)
    print("Research Paper Analyzer")
    print(f"Model: {DEFAULT_MODEL}")
    print("=" * 60)
    print(f"\nOpen http://localhost:{FLASK_PORT} in your browser")
    print("Drag & drop a PDF to analyze it")
    print(f"Max file size: {MAX_FILE_SIZE_MB}MB")
    print(f"Rate limit: {MAX_UPLOADS_PER_HOUR} uploads/hour\n")

    app.run(host=FLASK_HOST, port=FLASK_PORT, debug=FLASK_DEBUG)
