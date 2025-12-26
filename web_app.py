#!/usr/bin/env python3
"""
Research Paper Analysis - Web UI
================================
A simple drag & drop interface for analyzing research papers.

Usage:
    python web_app.py
    Then open http://localhost:5000 in your browser
"""

import asyncio
import os
from datetime import datetime
from pathlib import Path
from threading import Thread

import fitz  # PyMuPDF
from flask import Flask, render_template_string, request, jsonify, send_file

from claude_agent_sdk import query, ClaudeAgentOptions, AssistantMessage, ResultMessage
from prompts import RESEARCH_ANALYSIS_PROMPT

app = Flask(__name__)

# Store analysis results
analyses = {}

# Directories
UPLOAD_DIR = Path(__file__).parent / "uploads"
OUTPUT_DIR = Path(__file__).parent / "analyses"
UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)


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


async def run_analysis(pdf_path: Path, analysis_id: str):
    """Run the analysis agent and collect results."""
    analyses[analysis_id] = {
        "status": "extracting",
        "content": "",
        "filename": pdf_path.name,
        "started": datetime.now().isoformat()
    }

    try:
        # Extract text from PDF
        text = extract_text_from_pdf(pdf_path)
        text_file = UPLOAD_DIR / f"{pdf_path.stem}.txt"
        text_file.write_text(text, encoding="utf-8")

        analyses[analysis_id]["status"] = "analyzing"

        # Build prompt
        context = f"Analyze this research paper:\n\n{text[:50000]}"  # Limit text size
        full_prompt = f"{context}\n\n{RESEARCH_ANALYSIS_PROMPT}"

        # Run analysis
        content_parts = []
        async for message in query(
            prompt=full_prompt,
            options=ClaudeAgentOptions(
                allowed_tools=["WebSearch", "WebFetch"],
                permission_mode="acceptEdits"
            )
        ):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if hasattr(block, "text") and block.text:
                        content_parts.append(block.text)
                        analyses[analysis_id]["content"] = "\n\n".join(content_parts)

        # Save to markdown file
        output_file = OUTPUT_DIR / f"{pdf_path.stem}_analysis.md"
        final_content = "\n\n".join(content_parts)

        md_content = f"""# Analysis: {pdf_path.name}

**Generated:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

---

{final_content}
"""
        output_file.write_text(md_content, encoding="utf-8")

        analyses[analysis_id]["status"] = "complete"
        analyses[analysis_id]["content"] = final_content
        analyses[analysis_id]["output_file"] = str(output_file)

    except Exception as e:
        analyses[analysis_id]["status"] = "error"
        analyses[analysis_id]["error"] = str(e)


def run_async_analysis(pdf_path: Path, analysis_id: str):
    """Run async analysis in a thread."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(run_analysis(pdf_path, analysis_id))
    loop.close()


HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Research Paper Analyzer</title>
    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
    <style>
        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            background: linear-gradient(135deg, #f5f7fa 0%, #e4e8ec 100%);
            min-height: 100vh;
            color: #2d3748;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
            padding: 2rem;
        }
        h1 {
            text-align: center;
            margin-bottom: 2rem;
            font-size: 2.5rem;
            background: linear-gradient(90deg, #667eea, #764ba2);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        .drop-zone {
            border: 3px dashed #cbd5e0;
            border-radius: 20px;
            padding: 4rem 2rem;
            text-align: center;
            background: rgba(255,255,255,0.7);
            transition: all 0.3s ease;
            cursor: pointer;
            margin-bottom: 2rem;
        }
        .drop-zone:hover, .drop-zone.dragover {
            border-color: #667eea;
            background: rgba(102, 126, 234, 0.1);
            transform: scale(1.01);
        }
        .drop-zone-icon {
            font-size: 4rem;
            margin-bottom: 1rem;
        }
        .drop-zone-text {
            font-size: 1.2rem;
            color: #4a5568;
        }
        .drop-zone input {
            display: none;
        }
        .status {
            text-align: center;
            padding: 1rem;
            border-radius: 10px;
            margin-bottom: 1rem;
            display: none;
        }
        .status.visible {
            display: block;
        }
        .status.extracting {
            background: rgba(255, 193, 7, 0.15);
            border: 1px solid #d69e2e;
            color: #744210;
        }
        .status.analyzing {
            background: rgba(102, 126, 234, 0.15);
            border: 1px solid #667eea;
            color: #434190;
        }
        .status.complete {
            background: rgba(72, 187, 120, 0.15);
            border: 1px solid #48bb78;
            color: #276749;
        }
        .status.error {
            background: rgba(245, 101, 101, 0.15);
            border: 1px solid #f56565;
            color: #c53030;
        }
        .result-container {
            background: white;
            border-radius: 15px;
            padding: 2rem;
            display: none;
            box-shadow: 0 4px 20px rgba(0,0,0,0.1);
        }
        .result-container.visible {
            display: block;
        }
        .result-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 1.5rem;
            padding-bottom: 1rem;
            border-bottom: 1px solid #e2e8f0;
        }
        .result-title {
            font-size: 1.3rem;
            color: #667eea;
        }
        .export-btn {
            background: linear-gradient(90deg, #667eea, #764ba2);
            color: white;
            border: none;
            padding: 0.75rem 1.5rem;
            border-radius: 8px;
            font-size: 1rem;
            cursor: pointer;
            transition: transform 0.2s, box-shadow 0.2s;
        }
        .export-btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 20px rgba(102, 126, 234, 0.4);
        }
        .result-content {
            background: #f7fafc;
            border-radius: 10px;
            padding: 1.5rem;
            max-height: 70vh;
            overflow-y: auto;
            line-height: 1.7;
            color: #2d3748;
        }
        .result-content h1, .result-content h2, .result-content h3 {
            color: #553c9a;
            margin-top: 1.5rem;
            margin-bottom: 0.75rem;
        }
        .result-content h1 { font-size: 1.8rem; }
        .result-content h2 { font-size: 1.4rem; }
        .result-content h3 { font-size: 1.2rem; }
        .result-content p { margin-bottom: 1rem; }
        .result-content ul, .result-content ol {
            margin-left: 1.5rem;
            margin-bottom: 1rem;
        }
        .result-content li { margin-bottom: 0.5rem; }
        .result-content table {
            width: 100%;
            border-collapse: collapse;
            margin: 1rem 0;
        }
        .result-content th, .result-content td {
            border: 1px solid #e2e8f0;
            padding: 0.75rem;
            text-align: left;
        }
        .result-content th {
            background: rgba(102, 126, 234, 0.1);
            color: #553c9a;
        }
        .result-content blockquote {
            border-left: 3px solid #667eea;
            padding-left: 1rem;
            margin: 1rem 0;
            color: #718096;
            background: #edf2f7;
            padding: 1rem;
            border-radius: 0 8px 8px 0;
        }
        .result-content code {
            background: #edf2f7;
            padding: 0.2rem 0.4rem;
            border-radius: 4px;
            font-family: 'Monaco', 'Menlo', monospace;
            color: #553c9a;
        }
        .spinner {
            display: inline-block;
            width: 20px;
            height: 20px;
            border: 2px solid rgba(102, 126, 234, 0.3);
            border-radius: 50%;
            border-top-color: #667eea;
            animation: spin 1s linear infinite;
            margin-right: 0.5rem;
        }
        @keyframes spin {
            to { transform: rotate(360deg); }
        }
        .files-list {
            margin-top: 2rem;
            padding-top: 1rem;
            border-top: 1px solid #e2e8f0;
        }
        .files-list h3 {
            color: #4a5568;
            margin-bottom: 1rem;
        }
        .file-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 0.75rem 1rem;
            background: white;
            border-radius: 8px;
            margin-bottom: 0.5rem;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }
        .file-item a {
            color: #667eea;
            text-decoration: none;
        }
        .file-item a:hover {
            text-decoration: underline;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Research Paper Analyzer</h1>

        <div class="drop-zone" id="dropZone">
            <div class="drop-zone-icon">📄</div>
            <div class="drop-zone-text">
                Drag & drop a PDF here<br>
                <small>or click to select</small>
            </div>
            <input type="file" id="fileInput" accept=".pdf">
        </div>

        <div class="status" id="status"></div>

        <div class="result-container" id="resultContainer">
            <div class="result-header">
                <div class="result-title" id="resultTitle">Analysis Result</div>
                <button class="export-btn" id="exportBtn">Export as Markdown</button>
            </div>
            <div class="result-content" id="resultContent"></div>
        </div>

        <div class="files-list" id="filesList"></div>
    </div>

    <script>
        const dropZone = document.getElementById('dropZone');
        const fileInput = document.getElementById('fileInput');
        const status = document.getElementById('status');
        const resultContainer = document.getElementById('resultContainer');
        const resultTitle = document.getElementById('resultTitle');
        const resultContent = document.getElementById('resultContent');
        const exportBtn = document.getElementById('exportBtn');

        let currentAnalysisId = null;
        let currentFilename = null;
        let currentMarkdown = null;

        // Drag & drop handlers
        dropZone.addEventListener('click', () => fileInput.click());

        dropZone.addEventListener('dragover', (e) => {
            e.preventDefault();
            dropZone.classList.add('dragover');
        });

        dropZone.addEventListener('dragleave', () => {
            dropZone.classList.remove('dragover');
        });

        dropZone.addEventListener('drop', (e) => {
            e.preventDefault();
            dropZone.classList.remove('dragover');
            const file = e.dataTransfer.files[0];
            if (file && file.type === 'application/pdf') {
                uploadFile(file);
            }
        });

        fileInput.addEventListener('change', () => {
            if (fileInput.files[0]) {
                uploadFile(fileInput.files[0]);
            }
        });

        async function uploadFile(file) {
            const formData = new FormData();
            formData.append('file', file);

            currentFilename = file.name;
            showStatus('extracting', 'Uploading and extracting text from PDF...');
            resultContainer.classList.remove('visible');

            try {
                const response = await fetch('/upload', {
                    method: 'POST',
                    body: formData
                });
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

                if (data.status === 'extracting') {
                    showStatus('extracting', '<span class="spinner"></span> Extracting text from PDF...');
                    setTimeout(pollStatus, 1000);
                } else if (data.status === 'analyzing') {
                    showStatus('analyzing', '<span class="spinner"></span> Analyzing paper with Claude...');
                    if (data.content) {
                        showResult(data.content);
                    }
                    setTimeout(pollStatus, 2000);
                } else if (data.status === 'complete') {
                    showStatus('complete', 'Analysis complete!');
                    showResult(data.content);
                    currentMarkdown = data.content;
                    loadFilesList();
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

        function showResult(markdown) {
            resultTitle.textContent = `Analysis: ${currentFilename}`;
            resultContent.innerHTML = marked.parse(markdown);
            resultContainer.classList.add('visible');
        }

        exportBtn.addEventListener('click', () => {
            if (!currentMarkdown) return;

            const blob = new Blob([`# Analysis: ${currentFilename}\\n\\n${currentMarkdown}`],
                                  { type: 'text/markdown' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = currentFilename.replace('.pdf', '_analysis.md');
            a.click();
            URL.revokeObjectURL(url);
        });

        async function loadFilesList() {
            try {
                const response = await fetch('/files');
                const data = await response.json();

                if (data.files && data.files.length > 0) {
                    const filesList = document.getElementById('filesList');
                    filesList.innerHTML = '<h3>Previous Analyses</h3>' +
                        data.files.map(f => `
                            <div class="file-item">
                                <a href="/download/${f}">${f}</a>
                            </div>
                        `).join('');
                }
            } catch (e) {}
        }

        loadFilesList();
    </script>
</body>
</html>
"""


@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)


@app.route('/upload', methods=['POST'])
def upload():
    if 'file' not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files['file']
    if not file.filename.endswith('.pdf'):
        return jsonify({"error": "Only PDF files are supported"}), 400

    # Save the file
    pdf_path = UPLOAD_DIR / file.filename
    file.save(pdf_path)

    # Generate analysis ID
    analysis_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{pdf_path.stem}"

    # Start analysis in background thread
    thread = Thread(target=run_async_analysis, args=(pdf_path, analysis_id))
    thread.start()

    return jsonify({"analysis_id": analysis_id})


@app.route('/status/<analysis_id>')
def get_status(analysis_id):
    if analysis_id not in analyses:
        return jsonify({"error": "Analysis not found"}), 404
    return jsonify(analyses[analysis_id])


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


if __name__ == '__main__':
    print("\n" + "=" * 50)
    print("Research Paper Analyzer")
    print("=" * 50)
    print("\nOpen http://localhost:5000 in your browser")
    print("Drag & drop a PDF to analyze it\n")
    app.run(debug=False, port=5000)
