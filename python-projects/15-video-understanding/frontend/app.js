// Configuration - use same origin to avoid CORS/tracking prevention
const API_BASE_URL = window.location.origin.includes(':8000') ? window.location.origin : 'http://localhost:8000';
const WS_BASE_URL = API_BASE_URL.replace('http://', 'ws://').replace('https://', 'wss://');
let currentVideo = null;
let ws = null;

// ============================================================================
// Initialization
// ============================================================================

document.addEventListener('DOMContentLoaded', () => {
    initializeApp();
    setupEventListeners();
    loadServerStatus();
    loadVideos();
});

function initializeApp() {
    // Setup navigation
    document.querySelectorAll('.nav-link').forEach(link => {
        link.addEventListener('click', (e) => {
            e.preventDefault();
            const page = link.dataset.page;
            navigateToPage(page);
        });
    });

    // Setup upload tabs
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const tab = btn.dataset.tab;
            switchUploadTab(tab);
        });
    });

    // File input
    const fileInput = document.getElementById('file-input');
    if (fileInput) {
        fileInput.addEventListener('change', handleFileSelect);
    }

    // Drag and drop
    const dropzone = document.getElementById('dropzone');
    if (dropzone) {
        dropzone.addEventListener('dragover', (e) => {
            e.preventDefault();
            dropzone.style.borderColor = 'var(--primary-color)';
        });

        dropzone.addEventListener('dragleave', () => {
            dropzone.style.borderColor = 'var(--border-color)';
        });

        dropzone.addEventListener('drop', (e) => {
            e.preventDefault();
            dropzone.style.borderColor = 'var(--border-color)';

            const files = e.dataTransfer.files;
            if (files.length > 0) {
                document.getElementById('file-input').files = files;
                handleFileSelect({ target: { files } });
            }
        });
    }
}

function setupEventListeners() {
    // Search on Enter key
    const searchQuery = document.getElementById('search-query');
    if (searchQuery) {
        searchQuery.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                performSearch();
            }
        });
    }
}

// ============================================================================
// Navigation
// ============================================================================

function navigateToPage(pageName) {
    // Update nav links
    document.querySelectorAll('.nav-link').forEach(link => {
        link.classList.toggle('active', link.dataset.page === pageName);
    });

    // Update pages
    document.querySelectorAll('.page').forEach(page => {
        page.classList.toggle('active', page.id === `${pageName}-page`);
    });

    // Load data if needed
    if (pageName === 'videos') {
        loadVideos();
    }
}

function switchUploadTab(tab) {
    // Update buttons
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.tab === tab);
    });

    // Update content
    document.querySelectorAll('.tab-content').forEach(content => {
        content.classList.toggle('active', content.id === `${tab}-tab`);
    });
}

// ============================================================================
// API Functions
// ============================================================================

async function apiCall(endpoint, options = {}) {
    try {
        const response = await fetch(`${API_BASE_URL}${endpoint}`, {
            ...options,
            headers: {
                'Content-Type': 'application/json',
                ...options.headers,
            },
        });

        if (!response.ok) {
            const error = await response.json().catch(() => ({ error: 'Unknown error' }));
            throw new Error(error.message || error.detail || 'Request failed');
        }

        return await response.json();
    } catch (error) {
        console.error('API Error:', error);
        showToast(error.message, 'error');
        throw error;
    }
}

// ============================================================================
// Server Status
// ============================================================================

async function loadServerStatus() {
    try {
        const health = await apiCall('/health');
        const info = await apiCall('/api/info');

        document.getElementById('server-status').textContent = health.status;
        document.getElementById('api-version').textContent = health.version;

        // Get video count
        const videos = await apiCall('/api/videos');
        document.getElementById('video-count').textContent = videos.total;

        showToast('Connected to server', 'success');
    } catch (error) {
        document.getElementById('server-status').textContent = 'Offline';
        document.getElementById('api-version').textContent = 'N/A';
        showToast('Server is offline', 'error');
    }
}

// ============================================================================
// File Upload
// ============================================================================

function handleFileSelect(event) {
    const file = event.target.files[0];
    if (file) {
        document.getElementById('file-preview').style.display = 'flex';
        document.getElementById('file-name').textContent = file.name;
        document.getElementById('dropzone').style.display = 'none';
    }
}

function clearFile() {
    document.getElementById('file-input').value = '';
    document.getElementById('file-preview').style.display = 'none';
    document.getElementById('dropzone').style.display = 'block';
}

async function uploadFile() {
    const fileInput = document.getElementById('file-input');
    const file = fileInput.files[0];

    if (!file) {
        showToast('Please select a file', 'error');
        return;
    }

    const title = document.getElementById('file-title').value || file.name;
    const description = document.getElementById('file-description').value;
    const autoProcess = document.getElementById('auto-process').checked;

    const formData = new FormData();
    formData.append('file', file);
    formData.append('title', title);
    formData.append('description', description);
    formData.append('auto_process', autoProcess);

    try {
        showProgress('Uploading video...');

        const response = await fetch(`${API_BASE_URL}/api/videos/upload`, {
            method: 'POST',
            body: formData,
        });

        const result = await response.json();

        if (response.ok) {
            showToast('Video uploaded successfully!', 'success');
            clearFile();

            if (autoProcess) {
                connectWebSocket(result.video_id);
            } else {
                hideProgress();
            }
        } else {
            throw new Error(result.detail || 'Upload failed');
        }
    } catch (error) {
        hideProgress();
        showToast(error.message, 'error');
    }
}

async function uploadYouTube() {
    const url = document.getElementById('youtube-url').value;
    const quality = document.getElementById('youtube-quality').value;

    if (!url) {
        showToast('Please enter a YouTube URL', 'error');
        return;
    }

    try {
        showProgress('Processing YouTube video...');

        const result = await apiCall('/api/videos/youtube', {
            method: 'POST',
            body: JSON.stringify({
                url,
                quality,
                auto_process: true,
            }),
        });

        showToast('YouTube video added!', 'success');
        document.getElementById('youtube-url').value = '';
        connectWebSocket(result.video_id);
    } catch (error) {
        hideProgress();
    }
}

async function uploadStream() {
    const url = document.getElementById('stream-url').value;

    if (!url) {
        showToast('Please enter a stream URL', 'error');
        return;
    }

    try {
        showProgress('Processing stream...');

        const result = await apiCall('/api/videos/stream', {
            method: 'POST',
            body: JSON.stringify({
                url,
                auto_process: true,
            }),
        });

        showToast('Stream video added!', 'success');
        document.getElementById('stream-url').value = '';
        connectWebSocket(result.video_id);
    } catch (error) {
        hideProgress();
    }
}

// ============================================================================
// WebSocket for Real-time Updates
// ============================================================================

function connectWebSocket(videoId) {
    const wsUrl = `${WS_BASE_URL}/api/ws/process/${videoId}`;

    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
        console.log('WebSocket connected');
        showToast('Connected to processing updates', 'info');
    };

    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        handleProcessingUpdate(data);
    };

    ws.onerror = (error) => {
        console.error('WebSocket error:', error);
        showToast('Connection error', 'error');
    };

    ws.onclose = () => {
        console.log('WebSocket closed');
    };
}

function handleProcessingUpdate(data) {
    const { event, stage, progress, message } = data;

    if (event === 'progress') {
        updateProgress(progress, message);
    } else if (event === 'stage_complete') {
        addStageComplete(stage, message);
    } else if (event === 'complete') {
        // Show completion state
        updateProgress(100, 'Processing complete! ✅');

        // Add final completion indicator
        const stagesDiv = document.getElementById('progress-stages');
        const completionEl = document.createElement('div');
        completionEl.className = 'stage complete';
        completionEl.innerHTML = `<i class="fas fa-check-circle"></i> <strong>${message}</strong>`;
        completionEl.style.color = 'var(--success-color)';
        completionEl.style.fontSize = '1.1rem';
        stagesDiv.appendChild(completionEl);

        showToast('Processing complete! ✅', 'success');

        // Hide after longer delay to show completion
        setTimeout(() => {
            hideProgress();
            loadVideos();
        }, 3000);

        if (ws) ws.close();
    } else if (event === 'error') {
        // Show error state
        updateProgress(progress || 0, `❌ Error: ${message}`);

        // Add error indicator
        const stagesDiv = document.getElementById('progress-stages');
        const errorEl = document.createElement('div');
        errorEl.className = 'stage';
        errorEl.innerHTML = `<i class="fas fa-times-circle"></i> <strong>Processing failed</strong>`;
        errorEl.style.color = 'var(--danger-color)';
        stagesDiv.appendChild(errorEl);

        showToast(`Error: ${message}`, 'error');

        // Hide after delay
        setTimeout(() => {
            hideProgress();
        }, 5000);

        if (ws) ws.close();
    }
}

// ============================================================================
// Progress Display
// ============================================================================

function showProgress(message) {
    const progressDiv = document.getElementById('upload-progress');
    progressDiv.style.display = 'block';
    document.getElementById('progress-text').textContent = message;
    document.getElementById('progress-fill').style.width = '0%';
    document.getElementById('progress-stages').innerHTML = '';
}

function updateProgress(percent, message) {
    document.getElementById('progress-fill').style.width = `${percent}%`;
    document.getElementById('progress-text').textContent = message;
}

function addStageComplete(stage, message) {
    const stagesDiv = document.getElementById('progress-stages');
    const stageEl = document.createElement('div');
    stageEl.className = 'stage complete';
    stageEl.innerHTML = `<i class="fas fa-check-circle"></i> ${message}`;
    stagesDiv.appendChild(stageEl);
}

function hideProgress() {
    document.getElementById('upload-progress').style.display = 'none';
}

// ============================================================================
// Search
// ============================================================================

async function performSearch() {
    const query = document.getElementById('search-query').value;
    const searchType = document.getElementById('search-type').value;

    if (!query) {
        showToast('Please enter a search query', 'error');
        return;
    }

    const resultsDiv = document.getElementById('search-results');
    resultsDiv.innerHTML = '<div class="loading">Searching...</div>';

    try {
        let results;

        if (searchType === 'semantic') {
            results = await apiCall('/api/search/semantic', {
                method: 'POST',
                body: JSON.stringify({
                    query,
                    top_k: 10,
                }),
            });
        } else if (searchType === 'frames') {
            results = await apiCall('/api/search/frames', {
                method: 'POST',
                body: JSON.stringify({
                    query,
                    top_k: 10,
                }),
            });
        } else if (searchType === 'transcript') {
            results = await apiCall('/api/search/transcript', {
                method: 'POST',
                body: JSON.stringify({
                    query,
                    top_k: 10,
                }),
            });
        } else if (searchType === 'query') {
            results = await apiCall('/api/search/query', {
                method: 'POST',
                body: JSON.stringify({
                    question: query,
                }),
            });
            displayQueryResult(results);
            return;
        }

        displaySearchResults(results);
    } catch (error) {
        resultsDiv.innerHTML = '<div class="error">Search failed</div>';
    }
}

function displaySearchResults(data) {
    const resultsDiv = document.getElementById('search-results');

    if (data.results.length === 0) {
        resultsDiv.innerHTML = '<div class="no-results">No results found</div>';
        return;
    }

    const html = `
        <div class="results-header">
            <h3>Found ${data.total_results} results (${data.search_time_ms.toFixed(2)}ms)</h3>
        </div>
        ${data.results.map(result => `
            <div class="result-card">
                <div class="result-header">
                    <div>
                        <span class="result-badge">${result.result_type}</span>
                        <h4>${result.video_title}</h4>
                    </div>
                    <div>
                        <strong>Score:</strong> ${(result.similarity_score * 100).toFixed(1)}%
                    </div>
                </div>
                <p>${result.content}</p>
                <div class="result-meta">
                    <span><i class="fas fa-clock"></i> ${formatTime(result.timestamp)}</span>
                </div>
            </div>
        `).join('')}
    `;

    resultsDiv.innerHTML = html;
}

function displayQueryResult(data) {
    const resultsDiv = document.getElementById('search-results');

    const html = `
        <div class="query-result">
            <div class="result-card">
                <h3>Answer</h3>
                <p style="font-size: 1.125rem; margin: 1rem 0;">${data.answer}</p>
                <div style="margin-top: 1rem;">
                    <strong>Confidence:</strong> ${(data.confidence * 100).toFixed(1)}%
                </div>
                ${data.sources.length > 0 ? `
                    <div style="margin-top: 1.5rem;">
                        <h4>Sources:</h4>
                        ${data.sources.map(source => `
                            <div style="margin-top: 0.5rem; padding: 0.5rem; background: var(--bg-lighter); border-radius: 0.5rem;">
                                <div><strong>${source.source_type}</strong> @ ${formatTime(source.timestamp)}</div>
                                <div style="color: var(--text-muted);">${source.content.substring(0, 150)}...</div>
                            </div>
                        `).join('')}
                    </div>
                ` : ''}
            </div>
        </div>
    `;

    resultsDiv.innerHTML = html;
}

// ============================================================================
// Videos List
// ============================================================================

async function loadVideos() {
    const videosDiv = document.getElementById('videos-list');
    videosDiv.innerHTML = '<div class="loading">Loading videos...</div>';

    try {
        const data = await apiCall('/api/videos');

        if (data.total === 0) {
            videosDiv.innerHTML = '<div class="no-results">No videos yet. Upload your first video!</div>';
            return;
        }

        const html = data.videos.map(video => `
            <div class="video-card" onclick="showVideoDetails('${video.video_id}')">
                <div class="video-thumbnail">
                    <i class="fas fa-film" style="font-size: 3rem; color: var(--text-muted);"></i>
                </div>
                <div class="video-info">
                    <div class="video-title">${video.title}</div>
                    <div class="video-meta">
                        <span><i class="fas fa-clock"></i> ${formatTime(video.duration_seconds)}</span>
                        <span class="video-status status-${video.processing_status}">
                            ${video.processing_status}
                        </span>
                    </div>
                </div>
            </div>
        `).join('');

        videosDiv.innerHTML = html;
    } catch (error) {
        videosDiv.innerHTML = '<div class="error">Failed to load videos</div>';
    }
}

async function showVideoDetails(videoId) {
    try {
        const video = await apiCall(`/api/videos/${videoId}`);

        const modal = document.getElementById('video-modal');
        const details = document.getElementById('video-details');

        details.innerHTML = `
            <h2>${video.title}</h2>
            ${video.description ? `<p>${video.description}</p>` : ''}

            <div style="margin-top: 2rem;">
                <h3>Video Information</h3>
                <div style="margin-top: 1rem;">
                    <div><strong>Duration:</strong> ${formatTime(video.duration_seconds)}</div>
                    <div><strong>Status:</strong> ${video.processing_status}</div>
                    <div><strong>Source:</strong> ${video.source_type}</div>
                    <div><strong>Created:</strong> ${new Date(video.created_at).toLocaleString()}</div>
                </div>
            </div>

            <div style="margin-top: 2rem; display: flex; gap: 1rem;">
                <button class="btn btn-primary" onclick="viewSummary('${videoId}')">
                    <i class="fas fa-file-alt"></i> View Summary
                </button>
                <button class="btn btn-primary" onclick="viewHighlights('${videoId}')">
                    <i class="fas fa-star"></i> View Highlights
                </button>
                <button class="btn btn-sm" onclick="deleteVideo('${videoId}')">
                    <i class="fas fa-trash"></i> Delete
                </button>
            </div>
        `;

        modal.classList.add('active');
    } catch (error) {
        showToast('Failed to load video details', 'error');
    }
}

function closeVideoModal() {
    document.getElementById('video-modal').classList.remove('active');
}

async function viewSummary(videoId) {
    try {
        const summary = await apiCall(`/api/videos/${videoId}/summary`);
        alert(`Summary:\n\n${summary.content}`);
    } catch (error) {
        showToast('Summary not available yet', 'error');
    }
}

async function viewHighlights(videoId) {
    try {
        const highlights = await apiCall(`/api/videos/${videoId}/highlights`);
        alert(`Found ${highlights.total_highlights} highlights`);
    } catch (error) {
        showToast('Highlights not available yet', 'error');
    }
}

async function deleteVideo(videoId) {
    if (!confirm('Are you sure you want to delete this video?')) {
        return;
    }

    try {
        await apiCall(`/api/videos/${videoId}`, {
            method: 'DELETE',
        });

        showToast('Video deleted', 'success');
        closeVideoModal();
        loadVideos();
    } catch (error) {
        showToast('Failed to delete video', 'error');
    }
}

// ============================================================================
// Utilities
// ============================================================================

function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;

    const icon = type === 'success' ? 'check-circle' :
                 type === 'error' ? 'exclamation-circle' :
                 'info-circle';

    toast.innerHTML = `
        <i class="fas fa-${icon}"></i>
        <span>${message}</span>
    `;

    container.appendChild(toast);

    setTimeout(() => {
        toast.remove();
    }, 5000);
}

function formatTime(seconds) {
    if (!seconds) return '0:00';

    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);

    if (hours > 0) {
        return `${hours}:${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    }
    return `${minutes}:${secs.toString().padStart(2, '0')}`;
}

// Close modal on outside click
window.onclick = function(event) {
    const modal = document.getElementById('video-modal');
    if (event.target === modal) {
        closeVideoModal();
    }
}
