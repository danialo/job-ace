// API Base URL
const API_BASE = window.location.origin;

// State
let jobs = [];
let blocks = [];
let applications = [];

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

        // Delete the cookie
        deleteCookie('jobace_has_resume');

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
                <br>Job ID: ${data.job_id}
                <br>Artifact Directory: ${data.artifact_dir}
            `);
            document.getElementById('intake-form').reset();
            loadJobs();
        } else {
            const errorMsg = data.detail ? (typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)) : 'Failed to capture job';
            showResult(resultEl, 'error', `Error: ${errorMsg}`);
        }
    } catch (error) {
        showResult(resultEl, 'error', `Network error: ${error.message}`);
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
                <br>Coverage: ${coveragePercent}% (${coverageCount} of ${totalKeywords} keywords covered)
                <br>Compliance: ${data.compliance_pass ? '✅ Pass' : '❌ Fail'}
                <br><br><strong>Resume Text:</strong>
                <pre>${data.ats_text.substring(0, 800)}${data.ats_text.length > 800 ? '...' : ''}</pre>
                ${data.uncovered.length > 0 ? `<br><strong>Uncovered Keywords:</strong> ${data.uncovered.join(', ')}` : ''}
            `);
        } else {
            const errorMsg = data.detail ? (typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)) : 'Failed to tailor resume';
            showResult(resultEl, 'error', `Error: ${errorMsg}`);
        }
    } catch (error) {
        showResult(resultEl, 'error', `Network error: ${error.message}`);
    } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = 'Generate Tailored Resume';
    }
}

// Store parsed resume data globally for preview modal
let parsedResumeData = null;

// Resume Upload Handler - NEW: Preview flow before saving
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

        // NEW: Use /parse-resume endpoint (preview only, doesn't save)
        const response = await fetch(`${API_BASE}/parse-resume`, {
            method: 'POST',
            body: formData
        });

        const data = await response.json();

        if (response.ok) {
            // Store parsed data globally
            parsedResumeData = data;

            // Hide upload result
            resultEl.classList.add('hidden');

            // Show preview modal
            showPreviewModal(data);

            // Reset form
            document.getElementById('upload-resume-form').reset();
        } else {
            const errorMsg = data.detail ? (typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)) : 'Failed to parse resume';
            showResult(resultEl, 'error', `Error: ${errorMsg}`);
        }
    } catch (error) {
        showResult(resultEl, 'error', `Network error: ${error.message}`);
    } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = 'Upload & Load Resume';
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
                metadataHTML += `<p><strong>${key}:</strong> ${value}</p>`;
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
            <p>Total Sections: ${summary.total_sections || 0}</p>
            <p>Total Blocks: ${summary.total_blocks || 0}</p>
            <p>Model Used: ${summary.model_used || 'N/A'}</p>
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
                        <div class="preview-block-category">${block.category}</div>
                        <div class="preview-block-tags">
                            ${block.tags.map(tag => `<span class="preview-block-tag">${tag}</span>`).join('')}
                        </div>
                    </div>
                    <div class="preview-block-actions">
                        <button class="btn-icon" onclick="editPreviewBlock(${index})" title="Edit">✏️ Edit</button>
                        <button class="btn-icon btn-delete" onclick="deletePreviewBlock(${index})" title="Delete">🗑️ Delete</button>
                    </div>
                </div>
                <div class="preview-block-content" id="block-content-${index}">${block.content}</div>
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
                <br>Blocks Saved: ${data.blocks_saved}
                <br>Block IDs: ${data.block_ids.join(', ')}
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
        <pre>job-ace capture ${jobId}</pre>
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
                <br>Apply URL: ${data.apply_url}
                <br>Fields: ${data.fields.length}
                <br>Uploads: ${data.uploads.length}
                <pre>${JSON.stringify(data, null, 2)}</pre>
            `);
        } else {
            const errorMsg = data.detail ? (typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)) : 'Failed to generate prefill plan';
            showResult(resultEl, 'error', `Error: ${errorMsg}`);
        }
    } catch (error) {
        showResult(resultEl, 'error', `Network error: ${error.message}`);
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
                <br>Application ID: ${data.application_id}
                <br>Status: ${data.status}
                <br>Applied At: ${new Date(data.applied_at).toLocaleString()}
            `);
            document.getElementById('submit-form').reset();
            loadApplications();
        } else {
            const errorMsg = data.detail ? (typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)) : 'Failed to log submission';
            showResult(resultEl, 'error', `Error: ${errorMsg}`);
        }
    } catch (error) {
        showResult(resultEl, 'error', `Network error: ${error.message}`);
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
            <h4>${job.title || 'Untitled Job'}</h4>
            <p><strong>Company:</strong> ${job.company}</p>
            <p><strong>Location:</strong> ${job.location || 'N/A'}</p>
            <p><strong>Job ID:</strong> ${job.id}</p>
            <p><strong>URL:</strong> <a href="${job.url}" target="_blank">${job.url}</a></p>
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

            // If blocks exist, also render the blocks editor on Resume Intake tab
            if (blocks.length > 0) {
                renderResumeBlocksEditor();
            }
        }
    } catch (error) {
        console.error('Failed to load blocks:', error);
    }
}

function displayBlocks() {
    // Update the blocks list display
    const blocksList = document.getElementById('blocks-list');
    if (blocks.length === 0) {
        blocksList.innerHTML = '<p class="text-muted">Upload a resume above or use CLI: <code>job-ace load-blocks &lt;file.yaml&gt;</code></p>';
    } else {
        blocksList.innerHTML = blocks.map(block => `
            <div class="block-item">
                <h4>Block ${block.id}: ${block.category}</h4>
                <p><strong>Tags:</strong> ${block.tags.join(', ')}</p>
                <p>${block.text}</p>
            </div>
        `).join('');
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
            <h4>${app.job_title}</h4>
            <p><strong>Status:</strong> ${app.status}</p>
            <p><strong>Applied:</strong> ${new Date(app.applied_at).toLocaleString()}</p>
            <p><strong>Job ID:</strong> ${app.job_id}</p>
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

        // Refresh UI
        renderBlockSelector();
        displayBlocks();

        alert(`Block ${blockId} deleted successfully!`);
    } catch (error) {
        console.error('Delete error:', error);
        alert(`Error deleting block: ${error.message}`);
    }
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

    // Render each category section
    for (const [category, categoryBlocks] of Object.entries(blocksByCategory)) {
        const section = document.createElement('div');
        section.className = 'resume-block-category-section';
        section.innerHTML = `
            <div class="category-section-header">
                <h4 class="category-section-title">${category}</h4>
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
            blockEditor.innerHTML = `
                <div class="block-editor-header">
                    <div class="block-editor-meta">
                        <div class="block-editor-tags">
                            ${block.tags.map(tag => `<span class="block-editor-tag">${tag}</span>`).join('')}
                        </div>
                    </div>
                    <div class="block-editor-actions">
                        <button class="btn-save" onclick="saveBlockContent(${block.id})">💾 Save</button>
                        <button class="btn-delete" onclick="deleteBlockFromEditor(${block.id})">🗑️ Delete</button>
                    </div>
                </div>
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

                    // Set initial content
                    quill.root.innerHTML = block.text;

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

    // Get content from Quill
    const content = quill.root.innerHTML;

    try {
        const response = await fetch(`${API_BASE}/blocks/${blockId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                text: content
            })
        });

        if (response.ok) {
            // Update local blocks array
            const block = blocks.find(b => b.id === blockId);
            if (block) {
                block.text = content;
            }

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

// Add edit form handler on load
document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('edit-block-form').addEventListener('submit', handleEditSubmit);
});
