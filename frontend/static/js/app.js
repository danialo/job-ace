// API Base URL
const API_BASE = 'http://172.239.66.45:3000';

// State
let jobs = [];
let blocks = [];
let applications = [];

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    initTabs();
    checkAPIStatus();
    initForms();
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

    // Capture Form
    document.getElementById('capture-form').addEventListener('submit', handleCapture);

    // Prefill Form
    document.getElementById('prefill-form').addEventListener('submit', handlePrefill);

    // Submit Form
    document.getElementById('submit-form').addEventListener('submit', handleSubmit);
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
    const blockIds = document.getElementById('resume-blocks').value
        .split(',')
        .map(id => parseInt(id.trim()))
        .filter(id => !isNaN(id));
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
    const blocksList = document.getElementById('blocks-list');
    if (blocks.length === 0) {
        blocksList.innerHTML = '<p class="text-muted">Load resume blocks using: <code>job-ace load-blocks &lt;file.yaml&gt;</code></p>';
        return;
    }

    blocksList.innerHTML = blocks.map(block => `
        <div class="block-item">
            <h4>Block ${block.id}: ${block.category}</h4>
            <p><strong>Tags:</strong> ${block.tags.join(', ')}</p>
            <p>${block.text}</p>
        </div>
    `).join('');
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
            option.textContent = `${job.id}: ${job.title}`;
            select.appendChild(option);
        });
    });
}

// Show Result
function showResult(element, type, message) {
    element.className = `result-box ${type}`;
    element.innerHTML = message;
}
