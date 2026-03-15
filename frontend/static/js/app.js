// API Base URL
const API_BASE = window.location.origin;

// HTML escape helper to prevent XSS
function esc(str) {
    if (str == null) return '';
    const div = document.createElement('div');
    div.appendChild(document.createTextNode(String(str)));
    return div.innerHTML;
}

// State
let jobs = [];
let blocks = [];
let applications = [];
let lastTailorJobId = null;
let lastTailorBlockIds = [];
let lastTailorVersion = 'v1';

// Cookie helpers
function setCookie(name, value, days = 365) {
    const expires = new Date();
    expires.setTime(expires.getTime() + (days * 24 * 60 * 60 * 1000));
    document.cookie = `${name}=${value};expires=${expires.toUTCString()};path=/`;
}

function getCookie(name) {
    const nameEQ = name + "=";
    const ca = document.cookie.split(';');
    for (let i = 0; i < ca.length; i++) {
        let c = ca[i];
        while (c.charAt(0) === ' ') c = c.substring(1, c.length);
        if (c.indexOf(nameEQ) === 0) return c.substring(nameEQ.length, c.length);
    }
    return null;
}

function deleteCookie(name) {
    document.cookie = `${name}=;expires=Thu, 01 Jan 1970 00:00:00 UTC;path=/`;
}

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    initTabs();
    checkAPIStatus();
    initForms();
    initBlockSelector();
    initResetButton();
    loadJobs();
    loadBlocks();
    loadApplications();
    loadTemplates();
});

// Tab Management
function initTabs() {
    const tabButtons = document.querySelectorAll('.tab-button');
    const tabContents = document.querySelectorAll('.tab-content');

    tabButtons.forEach(button => {
        button.addEventListener('click', () => {
            const tabName = button.getAttribute('data-tab');

            // Update active states
            tabButtons.forEach(btn => btn.classList.remove('active'));
            tabContents.forEach(content => content.classList.remove('active'));

            button.classList.add('active');
            document.getElementById(tabName).classList.add('active');
        });
    });
}

// API Status Check
async function checkAPIStatus() {
    const statusEl = document.getElementById('api-status');
    try {
        const response = await fetch(`${API_BASE}/docs`);
        if (response.ok) {
            statusEl.textContent = 'Online';
            statusEl.className = 'status-indicator online';
        } else {
            statusEl.textContent = 'Offline';
            statusEl.className = 'status-indicator offline';
        }
    } catch (error) {
        statusEl.textContent = 'Offline';
        statusEl.className = 'status-indicator offline';
    }
}

// Form Initialization
function initForms() {
    // Intake Form
    document.getElementById('intake-form').addEventListener('submit', handleIntake);

    // Tailor Form
    document.getElementById('tailor-form').addEventListener('submit', handleTailor);

    // Upload Resume Form
    document.getElementById('upload-resume-form').addEventListener('submit', handleResumeUpload);

    // Capture Form
    document.getElementById('capture-form').addEventListener('submit', handleCapture);

    // Prefill Form
    document.getElementById('prefill-form').addEventListener('submit', handlePrefill);

    // Submit Form
    document.getElementById('submit-form').addEventListener('submit', handleSubmit);
}

// Block Selector Initialization
function initBlockSelector() {
    // Select All button
    document.getElementById('select-all-blocks').addEventListener('click', () => {
        const checkboxes = document.querySelectorAll('#block-selector input[type="checkbox"]');
        checkboxes.forEach(checkbox => checkbox.checked = true);
    });

    // Deselect All button
    document.getElementById('deselect-all-blocks').addEventListener('click', () => {
        const checkboxes = document.querySelectorAll('#block-selector input[type="checkbox"]');
        checkboxes.forEach(checkbox => checkbox.checked = false);
    });
}

// Reset Button Initialization
function initResetButton() {
    document.getElementById('reset-data-btn').addEventListener('click', handleResetData);
}

async function handleResetData() {
    if (!confirm('Are you sure you want to delete ALL resume blocks? This cannot be undone.')) {
        return;
    }

    try {
        const response = await fetch(`${API_BASE}/blocks`, {
            method: 'DELETE',
            cache: 'no-store',
        });

        if (!response.ok) {
            throw new Error('Failed to delete blocks');
        }

        const result = await response.json();

        // Delete the cookie and localStorage
        deleteCookie('jobace_has_resume');
        localStorage.removeItem('originalResumeText');

        // Force hard reload with cache-busting
        window.location.href = window.location.href.split('?')[0] + '?_=' + Date.now();
    } catch (error) {
        console.error('Reset error:', error);
        alert(`Error resetting data: ${error.message}`);
    }
}

// Intake Handler
async function handleIntake(e) {
    e.preventDefault();

    const url = document.getElementById('job-url').value;
    const force = document.getElementById('force-refresh').checked;
    const resultEl = document.getElementById('intake-result');
    const submitBtn = e.target.querySelector('button[type="submit"]');

    submitBtn.disabled = true;
    submitBtn.innerHTML = '<span class="spinner"></span> Capturing...';

    try {
        const response = await fetch(`${API_BASE}/intake`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url, force })
        });

        const data = await response.json();

        if (response.ok) {
            showResult(resultEl, 'success', `
                <strong>Job Captured Successfully!</strong>
                <br>Job ID: ${esc(data.job_id)}
                <br>Artifact Directory: ${esc(data.artifact_dir)}
            `);
            document.getElementById('intake-form').reset();
            loadJobs();
        } else {
            const errorMsg = data.detail ? (typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)) : 'Failed to capture job';
            showResult(resultEl, 'error', `Error: ${esc(errorMsg)}`);
        }
    } catch (error) {
        showResult(resultEl, 'error', `Network error: ${esc(error.message)}`);
    } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = 'Capture Job';
    }
}

// Tailor Handler
async function handleTailor(e) {
    e.preventDefault();

    const jobId = parseInt(document.getElementById('select-job').value);

    // Get selected block IDs from checkboxes
    const selectedCheckboxes = document.querySelectorAll('#block-selector input[type="checkbox"]:checked');
    const blockIds = Array.from(selectedCheckboxes).map(cb => parseInt(cb.value));

    if (blockIds.length === 0) {
        const resultEl = document.getElementById('tailor-result');
        showResult(resultEl, 'error', 'Please select at least one resume block');
        return;
    }

    const resumeVersion = document.getElementById('resume-version').value || "v1";
    const resultEl = document.getElementById('tailor-result');
    const submitBtn = e.target.querySelector('button[type="submit"]');

    submitBtn.disabled = true;
    submitBtn.innerHTML = '<span class="spinner"></span> Generating...';

    try {
        const response = await fetch(`${API_BASE}/tailor`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                job_id: jobId,
                allowed_block_ids: blockIds,
                resume_version: resumeVersion
            })
        });

        const data = await response.json();

        if (response.ok) {
            const coverageCount = data.coverage.length;
            const uncoveredCount = data.uncovered.length;
            const totalKeywords = coverageCount + uncoveredCount;
            const coveragePercent = totalKeywords > 0 ? (coverageCount / totalKeywords * 100).toFixed(1) : 0;

            showResult(resultEl, 'success', `
                <strong>Resume Tailored Successfully!</strong>
                <br>Coverage: ${esc(coveragePercent)}% (${esc(coverageCount)} of ${esc(totalKeywords)} keywords covered)
                <br>Compliance: ${data.compliance_pass ? '✅ Pass' : '❌ Fail'}
                ${data.uncovered.length > 0 ? `<br><strong>Uncovered Keywords:</strong> ${esc(data.uncovered.join(', '))}` : ''}
            `);

            // Store tailor params for export
            lastTailorJobId = jobId;
            lastTailorBlockIds = blockIds;
            lastTailorVersion = resumeVersion;

            // Show full resume in preview section
            displayResumePreview(data.ats_text, data);
        } else {
            const errorMsg = data.detail ? (typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)) : 'Failed to tailor resume';
            showResult(resultEl, 'error', `Error: ${esc(errorMsg)}`);
        }
    } catch (error) {
        showResult(resultEl, 'error', `Network error: ${esc(error.message)}`);
    } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = 'Generate Tailored Resume';
    }
}

// Store full resume text and parsed data
let fullResumeText = '';
let originalResumeText = localStorage.getItem('originalResumeText') || '';
let fullResumeQuill = null;

// Track which blocks are selected for reassembled view
let selectedBlockIds = [];

// Resume Upload Handler - Parse and show immediately
async function handleResumeUpload(e) {
    e.preventDefault();

    const fileInput = document.getElementById('resume-file');
    const file = fileInput.files[0];
    const resultEl = document.getElementById('upload-result');
    const submitBtn = e.target.querySelector('button[type="submit"]');

    if (!file) {
        showResult(resultEl, 'error', 'Please select a file to upload');
        return;
    }

    submitBtn.disabled = true;
    submitBtn.innerHTML = '<span class="spinner"></span> Parsing Resume...';

    try {
        const formData = new FormData();
        formData.append('file', file);

        // Parse resume
        const response = await fetch(`${API_BASE}/parse-resume`, {
            method: 'POST',
            body: formData
        });

        const data = await response.json();

        // Debug: log the entire response
        console.log('Parse resume response:', data);
        console.log('Has original_text?', 'original_text' in data);
        console.log('original_text value:', data.original_text);

        if (response.ok) {
            // Clear existing blocks before saving new ones to prevent duplicates
            await fetch(`${API_BASE}/blocks`, {
                method: 'DELETE',
                cache: 'no-store',
            });

            // Save blocks to database immediately
            const confirmResponse = await fetch(`${API_BASE}/confirm-resume-blocks`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ blocks: data.blocks })
            });

            const confirmData = await confirmResponse.json();

            if (confirmResponse.ok) {
                // Set cookie
                setCookie('jobace_has_resume', 'true');

                // Show success
                showResult(resultEl, 'success', `
                    <strong>Resume Parsed Successfully!</strong>
                    <br>Sections Found: ${esc(data.parsing_summary?.total_sections || 0)}
                    <br>Blocks Created: ${esc(confirmData.blocks_saved)}
                `);

                // Store original resume text and persist it in localStorage
                originalResumeText = data.original_text || '';
                localStorage.setItem('originalResumeText', originalResumeText);
                console.log('Original text length:', originalResumeText.length);
                console.log('Original text preview:', originalResumeText.substring(0, 200));

                // Reload blocks from database
                await loadBlocks();

                // DON'T auto-populate reassembled text - user will select blocks manually
                fullResumeText = '';

                // Show side-by-side comparison (RIGHT pane will be empty until blocks are selected)
                showSideBySideComparison();

                // Show individual blocks editor
                renderResumeBlocksEditor();

                // Reset form
                document.getElementById('upload-resume-form').reset();
            } else {
                throw new Error(confirmData.detail || 'Failed to save blocks');
            }
        } else {
            const errorMsg = data.detail ? (typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)) : 'Failed to parse resume';
            showResult(resultEl, 'error', `Error: ${esc(errorMsg)}`);
        }
    } catch (error) {
        showResult(resultEl, 'error', `Error: ${esc(error.message)}`);
    } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = 'Upload & Parse Resume';
    }
}

// Show Preview Modal with parsed resume blocks
function showPreviewModal(data) {
    const modal = document.getElementById('preview-blocks-modal');
    const metadataEl = document.getElementById('preview-metadata');
    const parsingInfoEl = document.getElementById('preview-parsing-info');
    const blocksListEl = document.getElementById('preview-blocks-list');

    // Display metadata
    if (data.metadata && Object.keys(data.metadata).length > 0) {
        let metadataHTML = '<h4>Contact Information</h4>';
        for (const [key, value] of Object.entries(data.metadata)) {
            if (value) {
                metadataHTML += `<p><strong>${esc(key)}:</strong> ${esc(value)}</p>`;
            }
        }
        metadataEl.innerHTML = metadataHTML;
        metadataEl.style.display = 'block';
    } else {
        metadataEl.style.display = 'none';
    }

    // Display parsing info
    if (data.parsing_summary) {
        const summary = data.parsing_summary;
        parsingInfoEl.innerHTML = `
            <p><strong>Parsing Summary:</strong></p>
            <p>Total Sections: ${esc(summary.total_sections || 0)}</p>
            <p>Total Blocks: ${esc(summary.total_blocks || 0)}</p>
            <p>Model Used: ${esc(summary.model_used || 'N/A')}</p>
        `;
        parsingInfoEl.style.display = 'block';
    } else {
        parsingInfoEl.style.display = 'none';
    }

    // Display blocks
    let blocksHTML = '';
    data.blocks.forEach((block, index) => {
        blocksHTML += `
            <div class="preview-block-item" data-index="${index}">
                <div class="preview-block-header">
                    <div class="preview-block-meta">
                        <div class="preview-block-category">${esc(block.category)}</div>
                        <div class="preview-block-tags">
                            ${block.tags.map(tag => `<span class="preview-block-tag">${esc(tag)}</span>`).join('')}
                        </div>
                    </div>
                    <div class="preview-block-actions">
                        <button class="btn-icon" onclick="editPreviewBlock(${index})" title="Edit">✏️ Edit</button>
                        <button class="btn-icon btn-delete" onclick="deletePreviewBlock(${index})" title="Delete">🗑️ Delete</button>
                    </div>
                </div>
                <div class="preview-block-content" id="block-content-${index}">${esc(block.content)}</div>
            </div>
        `;
    });

    blocksListEl.innerHTML = blocksHTML;

    // Show modal
    modal.classList.remove('hidden');
}

// Close Preview Modal
function closePreviewModal() {
    const modal = document.getElementById('preview-blocks-modal');
    modal.classList.add('hidden');
    parsedResumeData = null;
}

// Delete a block from preview (doesn't affect database, only preview)
function deletePreviewBlock(index) {
    if (!parsedResumeData) return;

    if (confirm('Remove this block from the preview?')) {
        parsedResumeData.blocks.splice(index, 1);
        showPreviewModal(parsedResumeData);
    }
}

// Edit a block in preview (inline editing)
function editPreviewBlock(index) {
    if (!parsedResumeData) return;

    const block = parsedResumeData.blocks[index];
    const blockEl = document.querySelector(`.preview-block-item[data-index="${index}"]`);
    const contentEl = document.getElementById(`block-content-${index}`);

    // Create inline editing form
    const editFormHTML = `
        <div class="inline-edit-form">
            <div class="form-group">
                <label>Category:</label>
                <select id="edit-category-${index}" class="inline-edit-input">
                    <option value="summary" ${block.category === 'summary' ? 'selected' : ''}>Summary</option>
                    <option value="experience" ${block.category === 'experience' ? 'selected' : ''}>Experience</option>
                    <option value="education" ${block.category === 'education' ? 'selected' : ''}>Education</option>
                    <option value="skills" ${block.category === 'skills' ? 'selected' : ''}>Skills</option>
                    <option value="projects" ${block.category === 'projects' ? 'selected' : ''}>Projects</option>
                    <option value="certifications" ${block.category === 'certifications' ? 'selected' : ''}>Certifications</option>
                    <option value="awards" ${block.category === 'awards' ? 'selected' : ''}>Awards</option>
                    <option value="other" ${block.category === 'other' ? 'selected' : ''}>Other</option>
                </select>
            </div>
            <div class="form-group">
                <label>Tags (comma-separated):</label>
                <input type="text" id="edit-tags-${index}" class="inline-edit-input" value="${block.tags.join(', ')}">
            </div>
            <div class="form-group">
                <label>Content:</label>
                <textarea id="edit-content-${index}" class="inline-edit-input" rows="10">${block.content}</textarea>
            </div>
            <div class="inline-edit-actions">
                <button class="btn btn-secondary" onclick="cancelEditPreviewBlock(${index})">Cancel</button>
                <button class="btn btn-primary" onclick="saveEditPreviewBlock(${index})">Save</button>
            </div>
        </div>
    `;

    contentEl.innerHTML = editFormHTML;
}

// Cancel editing a block in preview
function cancelEditPreviewBlock(index) {
    if (!parsedResumeData) return;
    showPreviewModal(parsedResumeData);
}

// Save edited block in preview
function saveEditPreviewBlock(index) {
    if (!parsedResumeData) return;

    const category = document.getElementById(`edit-category-${index}`).value;
    const tagsInput = document.getElementById(`edit-tags-${index}`).value;
    const content = document.getElementById(`edit-content-${index}`).value;

    // Update the block data
    parsedResumeData.blocks[index] = {
        category: category,
        tags: tagsInput.split(',').map(t => t.trim()).filter(t => t),
        content: content
    };

    // Re-render preview
    showPreviewModal(parsedResumeData);
}

// Confirm and save blocks to database
async function confirmBlocks() {
    if (!parsedResumeData || !parsedResumeData.blocks || parsedResumeData.blocks.length === 0) {
        alert('No blocks to save');
        return;
    }

    const confirmBtn = document.querySelector('#preview-blocks-modal .btn-primary');
    confirmBtn.disabled = true;
    confirmBtn.innerHTML = '<span class="spinner"></span> Saving...';

    try {
        const response = await fetch(`${API_BASE}/confirm-resume-blocks`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ blocks: parsedResumeData.blocks })
        });

        const data = await response.json();

        if (response.ok) {
            // Set cookie to track that user has uploaded data
            setCookie('jobace_has_resume', 'true');

            // Close preview modal
            closePreviewModal();

            // Show success message
            const resultEl = document.getElementById('upload-result');
            showResult(resultEl, 'success', `
                <strong>Resume Blocks Saved Successfully!</strong>
                <br>Blocks Saved: ${esc(data.blocks_saved)}
                <br>Block IDs: ${esc(data.block_ids.join(', '))}
            `);

            // Refresh blocks list
            await loadBlocks();

            // Render the blocks editor with Quill
            await renderResumeBlocksEditor();

            // Update block selector for Tailor Resume tab
            renderBlockSelector(data.block_ids);

            // Stay on Resume Intake tab to show the editor
            // (already on the tab since upload happened there)
        } else {
            const errorMsg = data.detail ? (typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)) : 'Failed to save blocks';
            alert(`Error: ${errorMsg}`);
        }
    } catch (error) {
        alert(`Network error: ${error.message}`);
    } finally {
        confirmBtn.disabled = false;
        confirmBtn.textContent = 'Confirm & Save Blocks';
    }
}

// Capture Handler
async function handleCapture(e) {
    e.preventDefault();

    const jobId = parseInt(document.getElementById('capture-job').value);
    const resultEl = document.getElementById('capture-result');

    showResult(resultEl, 'success', `
        <strong>Form Capture</strong>
        <br>Use the CLI to capture form schema:
        <pre>job-ace capture ${esc(jobId)}</pre>
        <br>This feature requires browser automation and is best run from the command line.
    `);
}

// Prefill Handler
async function handlePrefill(e) {
    e.preventDefault();

    const jobId = parseInt(document.getElementById('prefill-job').value);
    const resultEl = document.getElementById('prefill-result');
    const submitBtn = e.target.querySelector('button[type="submit"]');

    submitBtn.disabled = true;
    submitBtn.innerHTML = '<span class="spinner"></span> Generating...';

    try {
        const response = await fetch(`${API_BASE}/prefill-plan`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ job_id: jobId })
        });

        const data = await response.json();

        if (response.ok) {
            showResult(resultEl, 'success', `
                <strong>Prefill Plan Generated!</strong>
                <br>Apply URL: ${esc(data.apply_url)}
                <br>Fields: ${esc(data.fields.length)}
                <br>Uploads: ${esc(data.uploads.length)}
                <pre>${esc(JSON.stringify(data, null, 2))}</pre>
            `);
        } else {
            const errorMsg = data.detail ? (typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)) : 'Failed to generate prefill plan';
            showResult(resultEl, 'error', `Error: ${esc(errorMsg)}`);
        }
    } catch (error) {
        showResult(resultEl, 'error', `Network error: ${esc(error.message)}`);
    } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = 'Generate Prefill Plan';
    }
}

// Submit Handler
async function handleSubmit(e) {
    e.preventDefault();

    const jobId = parseInt(document.getElementById('submit-job').value);
    const confirmationId = document.getElementById('confirmation-id').value || null;
    const confirmationText = document.getElementById('confirmation-text').value || null;
    const screenshotPath = document.getElementById('screenshot-path').value || null;
    const resultEl = document.getElementById('submit-result');
    const submitBtn = e.target.querySelector('button[type="submit"]');

    submitBtn.disabled = true;
    submitBtn.innerHTML = '<span class="spinner"></span> Logging...';

    try {
        const response = await fetch(`${API_BASE}/log-submit`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                job_id: jobId,
                confirmation_id: confirmationId,
                confirmation_text: confirmationText,
                screenshot_path: screenshotPath
            })
        });

        const data = await response.json();

        if (response.ok) {
            showResult(resultEl, 'success', `
                <strong>Application Logged Successfully!</strong>
                <br>Application ID: ${esc(data.application_id)}
                <br>Status: ${esc(data.status)}
                <br>Applied At: ${esc(new Date(data.applied_at).toLocaleString())}
            `);
            document.getElementById('submit-form').reset();
            loadApplications();
        } else {
            const errorMsg = data.detail ? (typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)) : 'Failed to log submission';
            showResult(resultEl, 'error', `Error: ${esc(errorMsg)}`);
        }
    } catch (error) {
        showResult(resultEl, 'error', `Network error: ${esc(error.message)}`);
    } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = 'Log Submission';
    }
}

// Load Jobs
async function loadJobs() {
    try {
        const response = await fetch(`${API_BASE}/jobs`);
        if (response.ok) {
            jobs = await response.json();
            displayJobs();
            updateJobSelects();
        }
    } catch (error) {
        console.error('Failed to load jobs:', error);
    }
}

function displayJobs() {
    const jobsList = document.getElementById('jobs-list');
    if (jobs.length === 0) {
        jobsList.innerHTML = '<p class="text-muted">No jobs captured yet. Add one above!</p>';
        return;
    }

    jobsList.innerHTML = jobs.map(job => `
        <div class="job-item">
            <h4>${esc(job.title || 'Untitled Job')}</h4>
            <p><strong>Company:</strong> ${esc(job.company)}</p>
            <p><strong>Location:</strong> ${esc(job.location || 'N/A')}</p>
            <p><strong>Job ID:</strong> ${esc(job.id)}</p>
            <p><strong>URL:</strong> <a href="${esc(job.url)}" target="_blank">${esc(job.url)}</a></p>
        </div>
    `).join('');
}

// Load Blocks - Only if cookie indicates user has uploaded resume
async function loadBlocks() {
    // Check if user has uploaded a resume (cookie-based)
    const hasResume = getCookie('jobace_has_resume');

    if (!hasResume) {
        // No cookie = no resume uploaded, show empty state
        blocks = [];
        displayBlocks();
        return;
    }

    // Cookie exists, load blocks from database
    try {
        const response = await fetch(`${API_BASE}/blocks`);
        if (response.ok) {
            blocks = await response.json();
            displayBlocks();

            // If blocks exist, show both editors on Resume Intake tab
            if (blocks.length > 0) {
                // DON'T auto-populate - user will select blocks to include
                fullResumeText = '';

                // Show comparison if we have original text (persisted in localStorage)
                if (originalResumeText) {
                    showSideBySideComparison();
                }

                // Show individual blocks editor
                renderResumeBlocksEditor();
            }
        }
    } catch (error) {
        console.error('Failed to load blocks:', error);
    }
}

function displayBlocks() {
    // Update the blocks list display (element may not exist in current layout)
    const blocksList = document.getElementById('blocks-list');
    if (blocksList) {
        if (blocks.length === 0) {
            blocksList.innerHTML = '<p class="text-muted">Upload a resume above or use CLI: <code>job-ace load-blocks &lt;file.yaml&gt;</code></p>';
        } else {
            blocksList.innerHTML = blocks.map(block => `
                <div class="block-item">
                    <h4>Block ${esc(block.id)}: ${esc(block.category)}</h4>
                    <p><strong>Tags:</strong> ${esc(block.tags.join(', '))}</p>
                    <p>${esc(block.text)}</p>
                </div>
            `).join('');
        }
    }

    // Update the block selector
    renderBlockSelector();
}

function renderBlockSelector(autoSelectIds = []) {
    const selector = document.getElementById('block-selector');

    if (blocks.length === 0) {
        selector.innerHTML = '<p class="text-muted">No blocks available. Upload a resume above to get started.</p>';
        return;
    }

    // Group blocks by category
    const grouped = {};
    blocks.forEach(block => {
        const category = block.category || 'Other';
        if (!grouped[category]) {
            grouped[category] = [];
        }
        grouped[category].push(block);
    });

    // Build HTML for each category
    let html = '';
    Object.keys(grouped).sort().forEach(category => {
        html += `<div class="block-category">`;
        html += `<div class="block-category-header">${category}</div>`;

        grouped[category].forEach(block => {
            const isAutoSelected = autoSelectIds.includes(block.id);
            const checked = isAutoSelected ? 'checked' : '';

            html += `
                <div class="block-checkbox-item">
                    <input
                        type="checkbox"
                        id="block-${block.id}"
                        value="${block.id}"
                        ${checked}
                    >
                    <label for="block-${block.id}" class="block-checkbox-label">
                        <div class="block-checkbox-title">Block ${block.id}</div>
                        ${block.tags.length > 0 ? `<div class="block-checkbox-tags">Tags: ${block.tags.join(', ')}</div>` : ''}
                        <div class="block-checkbox-preview">${block.text}</div>
                    </label>
                    <div class="block-actions">
                        <button class="btn-icon" onclick="openEditModal(${block.id})" title="Edit block">Edit</button>
                        <button class="btn-icon btn-delete" onclick="deleteBlock(${block.id})" title="Delete block">Delete</button>
                    </div>
                </div>
            `;
        });

        html += `</div>`;
    });

    selector.innerHTML = html;
}

// Load Applications
async function loadApplications() {
    try {
        const response = await fetch(`${API_BASE}/applications`);
        if (response.ok) {
            applications = await response.json();
            displayApplications();
        }
    } catch (error) {
        console.error('Failed to load applications:', error);
    }
}

function displayApplications() {
    const appsList = document.getElementById('applications-list');
    if (applications.length === 0) {
        appsList.innerHTML = '<p class="text-muted">No applications logged yet.</p>';
        return;
    }

    appsList.innerHTML = applications.map(app => `
        <div class="app-item">
            <h4>${esc(app.job_title)}</h4>
            <p><strong>Status:</strong> ${esc(app.status)}</p>
            <p><strong>Applied:</strong> ${esc(new Date(app.applied_at).toLocaleString())}</p>
            <p><strong>Job ID:</strong> ${esc(app.job_id)}</p>
        </div>
    `).join('');
}

// Update Job Selects
function updateJobSelects() {
    const selects = [
        document.getElementById('select-job'),
        document.getElementById('capture-job'),
        document.getElementById('prefill-job'),
        document.getElementById('submit-job')
    ];

    selects.forEach(select => {
        // Keep the default option
        const defaultOption = select.querySelector('option[value=""]');
        select.innerHTML = '';
        select.appendChild(defaultOption);

        // Add job options if available
        jobs.forEach(job => {
            const option = document.createElement('option');
            option.value = job.id;
            option.textContent = `${job.id}: ${job.title || 'Untitled Job'}`;
            select.appendChild(option);
        });
    });
}

// Show Result
function showResult(element, type, message) {
    element.className = `result-box ${type}`;
    element.innerHTML = message;
}

// Block Management Functions
function openEditModal(blockId) {
    const block = blocks.find(b => b.id === blockId);
    if (!block) {
        alert('Block not found');
        return;
    }

    // Populate modal form
    document.getElementById('edit-block-id').value = block.id;
    document.getElementById('edit-block-category').value = block.category || 'other';
    document.getElementById('edit-block-tags').value = block.tags.join(', ');
    document.getElementById('edit-block-text').value = block.text;

    // Show modal
    document.getElementById('edit-block-modal').classList.remove('hidden');
}

function closeEditModal() {
    document.getElementById('edit-block-modal').classList.add('hidden');
    document.getElementById('edit-block-form').reset();
}

async function handleEditSubmit(e) {
    e.preventDefault();

    const blockId = parseInt(document.getElementById('edit-block-id').value);
    const category = document.getElementById('edit-block-category').value;
    const tagsInput = document.getElementById('edit-block-tags').value;
    const text = document.getElementById('edit-block-text').value;

    // Convert comma-separated tags to proper format
    const tags = tagsInput.split(',').map(t => t.trim()).filter(t => t).join(',');

    try {
        const response = await fetch(`${API_BASE}/blocks/${blockId}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                category,
                tags,
                text,
            }),
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to update block');
        }

        const result = await response.json();

        // Update blocks array
        const index = blocks.findIndex(b => b.id === blockId);
        if (index !== -1) {
            blocks[index] = {
                id: result.id,
                category: result.category,
                tags: result.tags.split(',').filter(t => t),
                text: result.text,
            };
        }

        // Refresh UI
        renderBlockSelector();
        displayBlocks();

        // Close modal
        closeEditModal();

        alert(`Block ${blockId} updated successfully!`);
    } catch (error) {
        console.error('Edit error:', error);
        alert(`Error updating block: ${error.message}`);
    }
}

async function deleteBlock(blockId) {
    if (!confirm(`Are you sure you want to delete Block ${blockId}? This cannot be undone.`)) {
        return;
    }

    try {
        const response = await fetch(`${API_BASE}/blocks/${blockId}`, {
            method: 'DELETE',
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to delete block');
        }

        // Remove from blocks array
        const index = blocks.findIndex(b => b.id === blockId);
        if (index !== -1) {
            blocks.splice(index, 1);
        }

        // Remove from selected blocks
        const selectedIndex = selectedBlockIds.indexOf(blockId);
        if (selectedIndex !== -1) {
            selectedBlockIds.splice(selectedIndex, 1);
        }

        // Update reassembled view
        updateReassembledView();

        // Refresh UI
        renderBlockSelector();
        displayBlocks();

        alert(`Block ${blockId} deleted successfully!`);
    } catch (error) {
        console.error('Delete error:', error);
        alert(`Error deleting block: ${error.message}`);
    }
}

// Show Full Resume Editor with Quill
// Show Side by Side Comparison
function showSideBySideComparison() {
    const comparisonSection = document.getElementById('resume-comparison');
    const originalText = document.getElementById('original-resume-text');
    const reassembledText = document.getElementById('reassembled-resume-text');

    // Safety check - elements must exist
    if (!comparisonSection || !originalText || !reassembledText) {
        console.warn('Comparison elements not found in DOM');
        return;
    }

    // Set original text
    originalText.textContent = originalResumeText || '(Original text not available)';

    // Set reassembled text from blocks
    reassembledText.textContent = fullResumeText || '(No blocks to display)';

    // Show the section
    comparisonSection.classList.remove('hidden');
}

// Toggle block selection for reassembled view
function toggleBlockSelection(blockId) {
    const index = selectedBlockIds.indexOf(blockId);

    if (index === -1) {
        // Add to selection
        selectedBlockIds.push(blockId);
    } else {
        // Remove from selection
        selectedBlockIds.splice(index, 1);
    }

    // Update the reassembled view
    updateReassembledView();
}

// Update reassembled view with ONLY selected blocks
function updateReassembledView() {
    const reassembledText = document.getElementById('reassembled-resume-text');
    if (!reassembledText) return;

    // Only show blocks that are selected, in the order they appear in selectedBlockIds
    const selectedBlocks = selectedBlockIds
        .map(id => blocks.find(b => b.id === id))
        .filter(b => b); // Remove any undefined entries

    fullResumeText = selectedBlocks.map(b => b.text).join('\n\n');
    reassembledText.textContent = fullResumeText || '(No blocks selected)';
}

function showFullResumeEditor() {
    const editorSection = document.getElementById('full-resume-editor');
    const editorDiv = document.getElementById('full-resume-quill');

    // Show the section
    editorSection.classList.remove('hidden');

    // Initialize Quill if not already initialized
    if (!fullResumeQuill) {
        fullResumeQuill = new Quill('#full-resume-quill', {
            theme: 'snow',
            modules: {
                toolbar: [
                    ['bold', 'italic', 'underline'],
                    [{ 'header': [1, 2, 3, false] }],
                    [{ 'list': 'ordered'}, { 'list': 'bullet' }],
                    ['link'],
                    ['clean']
                ]
            }
        });
    }

    // Set the content (plain text)
    fullResumeQuill.setText(fullResumeText);
}

// Save Full Resume
async function saveFullResume() {
    if (!fullResumeQuill) {
        alert('Editor not initialized');
        return;
    }

    // Get plain text content from Quill
    const content = fullResumeQuill.getText().trim();

    // TODO: Add endpoint to save full resume text
    // For now, just show feedback
    alert('Full resume text updated! (Note: This currently updates the view only. Individual block saves are persistent.)');
    fullResumeText = content;
}

// Store Quill instances globally (indexed by block ID)
const quillEditors = {};

// Render Resume Blocks Editor with Quill
async function renderResumeBlocksEditor() {
    const container = document.getElementById('resume-blocks-container');
    const editorSection = document.getElementById('resume-blocks-editor');

    // Group blocks by category
    const blocksByCategory = {};
    blocks.forEach(block => {
        if (!blocksByCategory[block.category]) {
            blocksByCategory[block.category] = [];
        }
        blocksByCategory[block.category].push(block);
    });

    // Clear existing content
    container.innerHTML = '';

    // Auto-select all blocks by default
    selectedBlockIds = blocks.map(b => b.id);

    // Render each category section
    for (const [category, categoryBlocks] of Object.entries(blocksByCategory)) {
        const section = document.createElement('div');
        section.className = 'resume-block-category-section';
        section.innerHTML = `
            <div class="category-section-header">
                <h4 class="category-section-title">${esc(category)}</h4>
            </div>
            <div class="category-blocks" id="category-${category}"></div>
        `;

        container.appendChild(section);

        const categoryContainer = section.querySelector('.category-blocks');

        // Render each block in this category
        categoryBlocks.forEach(block => {
            const blockEditor = document.createElement('div');
            blockEditor.className = 'resume-block-editor';
            blockEditor.setAttribute('data-block-id', block.id);
            const isExperience = block.category === 'experience';
            const hasMetadata = isExperience && (block.job_title || block.company || block.start_date || block.end_date);
            const metadataHTML = isExperience ? `
                <div class="block-metadata-header">
                    <div class="block-metadata-fields">
                        <input type="text" class="meta-input meta-title" placeholder="Job Title" value="${esc(block.job_title || '')}" id="meta-title-${block.id}" />
                        <input type="text" class="meta-input meta-company" placeholder="Company" value="${esc(block.company || '')}" id="meta-company-${block.id}" />
                        <input type="text" class="meta-input meta-date" placeholder="Start" value="${esc(block.start_date || '')}" id="meta-start-${block.id}" />
                        <span class="meta-date-sep">–</span>
                        <input type="text" class="meta-input meta-date" placeholder="End" value="${esc(block.end_date || '')}" id="meta-end-${block.id}" />
                    </div>
                </div>
            ` : '';

            blockEditor.innerHTML = `
                <div class="block-editor-header">
                    <div class="block-editor-selection">
                        <input type="checkbox" id="select-block-${block.id}" onchange="toggleBlockSelection(${block.id})" checked />
                        <label for="select-block-${block.id}">Include in resume</label>
                    </div>
                    <div class="block-editor-actions">
                        <button class="btn-polish" onclick="polishBlock(${block.id})">✨ Polish</button>
                        <button class="btn-save" onclick="saveBlockContent(${block.id})">💾 Save</button>
                        <button class="btn-delete" onclick="deleteBlockFromEditor(${block.id})">🗑️ Delete</button>
                    </div>
                </div>
                ${metadataHTML}
                <div class="block-editor-content" id="editor-${block.id}"></div>
            `;

            categoryContainer.appendChild(blockEditor);

            // Initialize Quill editor for this block
            setTimeout(() => {
                const editorEl = document.getElementById(`editor-${block.id}`);
                if (editorEl) {
                    const quill = new Quill(`#editor-${block.id}`, {
                        theme: 'snow',
                        modules: {
                            toolbar: [
                                ['bold', 'italic', 'underline', 'strike'],
                                [{ 'header': [1, 2, 3, false] }],
                                [{ 'list': 'ordered'}, { 'list': 'bullet' }],
                                ['link'],
                                ['clean']
                            ]
                        }
                    });

                    // Set initial content — strip metadata header line if present
                    let blockText = block.text;
                    if (block.job_title || block.company) {
                        const lines = blockText.split('\n');
                        // Strip all spaces for comparison (PDF extraction splits words)
                        const firstNorm = (lines[0] || '').replace(/\s/g, '').toLowerCase();
                        const metaParts = [block.job_title, block.company, block.start_date, block.end_date]
                            .filter(Boolean).map(p => p.replace(/\s/g, '').toLowerCase());
                        if (metaParts.length && metaParts.every(p => firstNorm.includes(p))) {
                            blockText = lines.slice(1).join('\n').trim();
                        }
                    }
                    quill.setText(blockText);

                    // Store instance
                    quillEditors[block.id] = quill;
                }
            }, 100);
        });
    }

    // Show the editor section
    editorSection.classList.remove('hidden');
}

// Save block content from Quill editor
async function saveBlockContent(blockId) {
    const quill = quillEditors[blockId];
    if (!quill) {
        alert('Editor not found');
        return;
    }

    // Get plain text content from Quill (no HTML tags)
    const content = quill.getText().trim();

    try {
        const response = await fetch(`${API_BASE}/blocks/${blockId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                text: content,
                ...(document.getElementById(`meta-title-${blockId}`) && {
                    job_title: document.getElementById(`meta-title-${blockId}`).value || null,
                    company: document.getElementById(`meta-company-${blockId}`).value || null,
                    start_date: document.getElementById(`meta-start-${blockId}`).value || null,
                    end_date: document.getElementById(`meta-end-${blockId}`).value || null,
                })
            })
        });

        if (response.ok) {
            // Update local blocks array
            const block = blocks.find(b => b.id === blockId);
            if (block) {
                block.text = content;
                if (document.getElementById(`meta-title-${blockId}`)) {
                    block.job_title = document.getElementById(`meta-title-${blockId}`).value || null;
                    block.company = document.getElementById(`meta-company-${blockId}`).value || null;
                    block.start_date = document.getElementById(`meta-start-${blockId}`).value || null;
                    block.end_date = document.getElementById(`meta-end-${blockId}`).value || null;
                }
            }

            // Update the reassembled view if comparison is visible
            updateReassembledView();

            // Show success feedback
            const saveBtn = document.querySelector(`[data-block-id="${blockId}"] .btn-save`);
            const originalText = saveBtn.textContent;
            saveBtn.textContent = '✅ Saved!';
            saveBtn.style.background = '#10b981';

            setTimeout(() => {
                saveBtn.textContent = originalText;
                saveBtn.style.background = '';
            }, 2000);
        } else {
            const error = await response.json();
            alert(`Error saving block: ${error.detail || 'Unknown error'}`);
        }
    } catch (error) {
        alert(`Network error: ${error.message}`);
    }
}

// Polish block with LLM
async function polishBlock(blockId) {
    const polishBtn = document.querySelector(`[data-block-id="${blockId}"] .btn-polish`);
    const originalBtnText = polishBtn.textContent;

    polishBtn.disabled = true;
    polishBtn.textContent = '⏳ Polishing...';
    polishBtn.style.background = '#f59e0b';

    try {
        const response = await fetch(`${API_BASE}/blocks/${blockId}/polish`, {
            method: 'POST'
        });

        if (response.ok) {
            const data = await response.json();

            // Show comparison UI
            showImprovementComparison(blockId, data.original_text, data.improved_text);

            // Reset button
            polishBtn.textContent = originalBtnText;
            polishBtn.style.background = '';
            polishBtn.disabled = false;
        } else {
            const error = await response.json();
            alert(`Error improving block: ${error.detail || 'Unknown error'}`);
            polishBtn.textContent = originalBtnText;
            polishBtn.disabled = false;
            polishBtn.style.background = '';
        }
    } catch (error) {
        alert(`Network error: ${error.message}`);
        polishBtn.textContent = originalBtnText;
        polishBtn.disabled = false;
        polishBtn.style.background = '';
    }
}

// Show improvement comparison modal
function showImprovementComparison(blockId, originalText, improvedText) {
    // Create modal overlay
    const modal = document.createElement('div');
    modal.className = 'improvement-modal';
    modal.innerHTML = `
        <div class="improvement-modal-content">
            <div class="improvement-modal-header">
                <h3>Review Polish</h3>
                <button class="btn-close-modal" onclick="closeImprovementModal()">✕</button>
            </div>

            <div class="improvement-comparison">
                <div class="improvement-box">
                    <div class="improvement-box-header">
                        <h4>Original</h4>
                        <div class="improvement-box-actions">
                            <input type="checkbox" id="improvement-original-checkbox-${blockId}" onchange="toggleImprovementBlockSelection(${blockId})" />
                            <label for="improvement-original-checkbox-${blockId}">Include</label>
                            <button class="btn-save" onclick="saveImprovementVersion(${blockId}, 'original')">💾 Save</button>
                        </div>
                    </div>
                    <div id="improvement-original-${blockId}" class="improvement-editor"></div>
                </div>

                <div class="improvement-box">
                    <div class="improvement-box-header">
                        <h4>Polished</h4>
                        <div class="improvement-box-actions">
                            <input type="checkbox" id="improvement-improved-checkbox-${blockId}" onchange="toggleImprovementBlockSelection(${blockId})" />
                            <label for="improvement-improved-checkbox-${blockId}">Include</label>
                            <button class="btn-save" onclick="saveImprovementVersion(${blockId}, 'improved')">💾 Save</button>
                        </div>
                    </div>
                    <div id="improvement-improved-${blockId}" class="improvement-editor"></div>
                </div>
            </div>

            <div class="improvement-modal-actions">
                <button class="btn-cancel" onclick="closeImprovementModal()">Cancel</button>
            </div>
        </div>
    `;

    document.body.appendChild(modal);

    // Initialize Quill editors for both versions
    setTimeout(() => {
        const originalQuill = new Quill(`#improvement-original-${blockId}`, {
            theme: 'snow',
            modules: { toolbar: false }
        });
        originalQuill.setText(originalText);

        const improvedQuill = new Quill(`#improvement-improved-${blockId}`, {
            theme: 'snow',
            modules: { toolbar: false }
        });
        improvedQuill.setText(improvedText);

        // Sync checkbox state with main selection
        const isSelected = selectedBlockIds.includes(blockId);
        const originalCheckbox = document.getElementById(`improvement-original-checkbox-${blockId}`);
        const improvedCheckbox = document.getElementById(`improvement-improved-checkbox-${blockId}`);

        if (originalCheckbox) originalCheckbox.checked = isSelected;
        if (improvedCheckbox) improvedCheckbox.checked = isSelected;

        // Store references
        window.improvementComparison = {
            blockId,
            originalQuill,
            improvedQuill
        };
    }, 50);
}

// Close improvement modal
function closeImprovementModal() {
    const modal = document.querySelector('.improvement-modal');
    if (modal) {
        modal.remove();
    }
    window.improvementComparison = null;
}

// Toggle block selection from improvement modal
function toggleImprovementBlockSelection(blockId) {
    // Get the checkbox from the main block editor
    const mainCheckbox = document.getElementById(`select-block-${blockId}`);

    // Toggle the main checkbox
    if (mainCheckbox) {
        mainCheckbox.checked = !mainCheckbox.checked;
        // Trigger the main toggle function
        toggleBlockSelection(blockId);
    }
}

// Save a version from the improvement comparison
async function saveImprovementVersion(blockId, version) {
    if (!window.improvementComparison) return;

    // Get the text from the selected version
    const quill = version === 'original'
        ? window.improvementComparison.originalQuill
        : window.improvementComparison.improvedQuill;

    const text = quill.getText().trim();

    // Save to database
    try {
        const response = await fetch(`${API_BASE}/blocks/${blockId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text })
        });

        if (response.ok) {
            // Update main editor
            const mainQuill = quillEditors[blockId];
            if (mainQuill) {
                mainQuill.setText(text);
            }

            // Update local blocks array
            const block = blocks.find(b => b.id === blockId);
            if (block) {
                block.text = text;
            }

            // Update reassembled view if this block is selected
            updateReassembledView();

            // Show success
            alert('Block saved successfully!');

            // Close modal
            closeImprovementModal();
        } else {
            const error = await response.json();
            alert(`Error saving block: ${error.detail || 'Unknown error'}`);
        }
    } catch (error) {
        alert(`Network error: ${error.message}`);
    }
}

// Delete block from editor
async function deleteBlockFromEditor(blockId) {
    if (!confirm('Are you sure you want to delete this block? This cannot be undone.')) {
        return;
    }

    try {
        const response = await fetch(`${API_BASE}/blocks/${blockId}`, {
            method: 'DELETE'
        });

        if (response.ok) {
            // Remove Quill instance
            delete quillEditors[blockId];

            // Remove from blocks array
            const index = blocks.findIndex(b => b.id === blockId);
            if (index !== -1) {
                blocks.splice(index, 1);
            }

            // Remove from selected blocks
            const selectedIndex = selectedBlockIds.indexOf(blockId);
            if (selectedIndex !== -1) {
                selectedBlockIds.splice(selectedIndex, 1);
            }

            // Update reassembled view
            updateReassembledView();

            // Re-render editor
            await renderResumeBlocksEditor();

            // Update block selector in Tailor Resume tab
            renderBlockSelector();
        } else {
            const error = await response.json();
            alert(`Error deleting block: ${error.detail || 'Unknown error'}`);
        }
    } catch (error) {
        alert(`Network error: ${error.message}`);
    }
}

// Resume Preview Functions
let currentResumeText = '';
let currentResumeData = null;

function displayResumePreview(resumeText, metadata) {
    currentResumeText = resumeText;
    currentResumeData = metadata;

    const previewSection = document.getElementById('resume-preview-section');
    const previewText = document.getElementById('resume-preview-text');

    previewText.textContent = resumeText;
    previewSection.classList.remove('hidden');

    // Scroll to preview
    previewSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function copyResumeToClipboard() {
    if (!currentResumeText) {
        alert('No resume to copy');
        return;
    }

    navigator.clipboard.writeText(currentResumeText).then(() => {
        alert('Resume copied to clipboard!');
    }).catch(err => {
        console.error('Failed to copy:', err);
        alert('Failed to copy to clipboard');
    });
}

function downloadResume() {
    if (!currentResumeText) {
        alert('No resume to download');
        return;
    }

    const blob = new Blob([currentResumeText], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'resume_tailored_' + Date.now() + '.txt';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}

async function loadTemplates() {
    try {
        const response = await fetch(`${API_BASE}/templates`);
        if (!response.ok) return;
        const templates = await response.json();
        const selector = document.getElementById('template-selector');
        if (!selector || templates.length === 0) return;
        selector.innerHTML = '';
        templates.forEach(t => {
            const opt = document.createElement('option');
            opt.value = t.id;
            opt.textContent = t.name;
            selector.appendChild(opt);
        });
    } catch (e) {
        console.error('Failed to load templates:', e);
    }
}

async function downloadResumeAs(format) {
    if (!lastTailorJobId || !lastTailorBlockIds.length) {
        alert('Please tailor a resume first before downloading.');
        return;
    }

    const template = document.getElementById('template-selector')?.value || 'classic';

    try {
        const response = await fetch(`${API_BASE}/export`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                job_id: lastTailorJobId,
                block_ids: lastTailorBlockIds,
                template: template,
                format: format,
                resume_version: lastTailorVersion,
            })
        });

        if (!response.ok) {
            const err = await response.json();
            alert('Export failed: ' + (err.detail || 'Unknown error'));
            return;
        }

        const blob = await response.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        const ext = format === 'pdf' ? 'pdf' : 'docx';
        a.download = `resume_${lastTailorVersion}.${ext}`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    } catch (error) {
        alert('Export error: ' + error.message);
    }
}

// Add edit form handler on load
document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('edit-block-form').addEventListener('submit', handleEditSubmit);
});
