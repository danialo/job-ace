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

// Resume Upload Handler
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
    submitBtn.innerHTML = '<span class="spinner"></span> Uploading & Processing...';

    try {
        const formData = new FormData();
        formData.append('file', file);

        const response = await fetch(`${API_BASE}/upload-resume`, {
            method: 'POST',
            body: formData
        });

        const data = await response.json();

        if (response.ok) {
            // Set cookie to track that user has uploaded data
            setCookie('jobace_has_resume', 'true');

            showResult(resultEl, 'success', `
                <strong>Resume Uploaded Successfully!</strong>
                <br>Filename: ${data.filename}
                <br>Blocks Loaded: ${data.blocks_loaded}
                <br>Block IDs: ${data.block_ids.join(', ')}
                ${data.metadata.name ? `<br>Name: ${data.metadata.name}` : ''}
                ${data.metadata.email ? `<br>Email: ${data.metadata.email}` : ''}
            `);
            document.getElementById('upload-resume-form').reset();

            // Refresh blocks list and auto-select the new blocks
            await loadBlocks();
            renderBlockSelector(data.block_ids);

            // Switch to the Tailor Resume tab to show the auto-selected blocks
            const tailorTab = document.querySelector('.tab-button[data-tab="tailor"]');
            if (tailorTab) {
                tailorTab.click();
            }
        } else {
            const errorMsg = data.detail ? (typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)) : 'Failed to upload resume';
            showResult(resultEl, 'error', `Error: ${errorMsg}`);
        }
    } catch (error) {
        showResult(resultEl, 'error', `Network error: ${error.message}`);
    } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = 'Upload & Load Resume';
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

// Load Blocks
async function loadBlocks() {
    try {
        const response = await fetch(`${API_BASE}/blocks`);
        if (response.ok) {
            blocks = await response.json();
            displayBlocks();
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

// Add edit form handler on load
document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('edit-block-form').addEventListener('submit', handleEditSubmit);
});
