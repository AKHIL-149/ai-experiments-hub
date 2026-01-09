// Global variables
let selectedFile = null;
let selectedFileOCR = null;

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    setupDragAndDrop();
    setupEventListeners();
    loadCacheStats();
});

// Setup drag and drop for vision analysis
function setupDragAndDrop() {
    const dropZone = document.getElementById('dropZone');
    const fileInput = document.getElementById('fileInput');
    const dropZoneOCR = document.getElementById('dropZoneOCR');
    const fileInputOCR = document.getElementById('fileInputOCR');

    // Vision Analysis Drop Zone
    dropZone.addEventListener('click', () => fileInput.click());

    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.classList.add('drag-over');
    });

    dropZone.addEventListener('dragleave', () => {
        dropZone.classList.remove('drag-over');
    });

    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.classList.remove('drag-over');
        const file = e.dataTransfer.files[0];
        if (file && file.type.startsWith('image/')) {
            handleFileSelect(file);
        }
    });

    fileInput.addEventListener('change', (e) => {
        const file = e.target.files[0];
        if (file) {
            handleFileSelect(file);
        }
    });

    // OCR Drop Zone
    dropZoneOCR.addEventListener('click', () => fileInputOCR.click());

    dropZoneOCR.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZoneOCR.classList.add('drag-over');
    });

    dropZoneOCR.addEventListener('dragleave', () => {
        dropZoneOCR.classList.remove('drag-over');
    });

    dropZoneOCR.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZoneOCR.classList.remove('drag-over');
        const file = e.dataTransfer.files[0];
        if (file && file.type.startsWith('image/')) {
            handleFileSelectOCR(file);
        }
    });

    fileInputOCR.addEventListener('change', (e) => {
        const file = e.target.files[0];
        if (file) {
            handleFileSelectOCR(file);
        }
    });
}

// Setup other event listeners
function setupEventListeners() {
    // Temperature slider
    const tempSlider = document.getElementById('temperature');
    const tempValue = document.getElementById('tempValue');
    tempSlider.addEventListener('input', (e) => {
        tempValue.textContent = e.target.value;
    });
}

// Handle file selection for vision analysis
function handleFileSelect(file) {
    selectedFile = file;

    const dropZone = document.getElementById('dropZone');
    const imagePreview = document.getElementById('imagePreview');
    const previewImg = document.getElementById('previewImg');

    // Hide drop zone, show preview
    dropZone.style.display = 'none';
    imagePreview.style.display = 'block';

    // Load image preview
    const reader = new FileReader();
    reader.onload = (e) => {
        previewImg.src = e.target.result;
    };
    reader.readAsDataURL(file);
}

// Handle file selection for OCR
function handleFileSelectOCR(file) {
    selectedFileOCR = file;

    const dropZone = document.getElementById('dropZoneOCR');
    const imagePreview = document.getElementById('imagePreviewOCR');
    const previewImg = document.getElementById('previewImgOCR');

    dropZone.style.display = 'none';
    imagePreview.style.display = 'block';

    const reader = new FileReader();
    reader.onload = (e) => {
        previewImg.src = e.target.result;
    };
    reader.readAsDataURL(file);
}

// Clear image for vision analysis
function clearImage() {
    selectedFile = null;
    document.getElementById('dropZone').style.display = 'block';
    document.getElementById('imagePreview').style.display = 'none';
    document.getElementById('fileInput').value = '';
    document.getElementById('resultsContainer').style.display = 'none';
    document.getElementById('errorContainer').style.display = 'none';
}

// Clear image for OCR
function clearImageOCR() {
    selectedFileOCR = null;
    document.getElementById('dropZoneOCR').style.display = 'block';
    document.getElementById('imagePreviewOCR').style.display = 'none';
    document.getElementById('fileInputOCR').value = '';
    document.getElementById('ocrResultsContainer').style.display = 'none';
    document.getElementById('ocrErrorContainer').style.display = 'none';
}

// Analyze image
async function analyzeImage() {
    if (!selectedFile) {
        alert('Please select an image first');
        return;
    }

    const analyzeBtn = document.getElementById('analyzeBtn');
    const loadingSpinner = document.getElementById('loadingSpinner');
    const resultsContainer = document.getElementById('resultsContainer');
    const errorContainer = document.getElementById('errorContainer');

    // Show loading
    analyzeBtn.disabled = true;
    loadingSpinner.style.display = 'block';
    resultsContainer.style.display = 'none';
    errorContainer.style.display = 'none';

    // Prepare form data
    const formData = new FormData();
    formData.append('file', selectedFile);

    const customPrompt = document.getElementById('customPrompt').value;
    if (customPrompt) {
        formData.append('prompt', customPrompt);
    }

    const preset = document.getElementById('preset').value;
    if (preset) {
        formData.append('preset', preset);
    }

    formData.append('provider', document.getElementById('provider').value);
    formData.append('temperature', document.getElementById('temperature').value);
    formData.append('max_tokens', document.getElementById('maxTokens').value);
    formData.append('enable_cache', document.getElementById('enableCache').checked);

    try {
        const response = await fetch('/api/analyze', {
            method: 'POST',
            body: formData
        });

        const data = await response.json();

        if (data.success) {
            // Show results
            document.getElementById('resultText').textContent = data.result;

            // Show metadata
            const metadata = data.metadata;
            const metadataHtml = `
                <div class="d-flex flex-wrap gap-2">
                    <span class="badge bg-primary badge-custom">
                        ${metadata.format} ${metadata.dimensions}
                    </span>
                    <span class="badge bg-info badge-custom">
                        ${metadata.size_mb} MB
                    </span>
                    <span class="badge bg-success badge-custom">
                        ${metadata.provider}
                    </span>
                    ${metadata.preset ? `<span class="badge bg-warning badge-custom">Preset: ${metadata.preset}</span>` : ''}
                    ${data.cached ? '<span class="badge bg-secondary badge-custom">Cached</span>' : ''}
                </div>
            `;
            document.getElementById('metadata').innerHTML = metadataHtml;

            resultsContainer.style.display = 'block';
        } else {
            document.getElementById('errorText').textContent = data.error;
            errorContainer.style.display = 'block';
        }
    } catch (error) {
        document.getElementById('errorText').textContent = 'Network error: ' + error.message;
        errorContainer.style.display = 'block';
    } finally {
        analyzeBtn.disabled = false;
        loadingSpinner.style.display = 'none';
    }
}

// Extract text with OCR
async function extractText() {
    if (!selectedFileOCR) {
        alert('Please select an image first');
        return;
    }

    const ocrBtn = document.getElementById('ocrBtn');
    const loadingSpinner = document.getElementById('loadingSpinnerOCR');
    const resultsContainer = document.getElementById('ocrResultsContainer');
    const errorContainer = document.getElementById('ocrErrorContainer');

    // Show loading
    ocrBtn.disabled = true;
    loadingSpinner.style.display = 'block';
    resultsContainer.style.display = 'none';
    errorContainer.style.display = 'none';

    // Prepare form data
    const formData = new FormData();
    formData.append('file', selectedFileOCR);
    formData.append('method', document.getElementById('ocrMethod').value);
    formData.append('language', document.getElementById('ocrLanguage').value);
    formData.append('provider', document.getElementById('ocrProvider').value);
    formData.append('fallback', document.getElementById('ocrFallback').checked);

    try {
        const response = await fetch('/api/ocr', {
            method: 'POST',
            body: formData
        });

        const data = await response.json();

        if (data.success) {
            // Show results
            document.getElementById('ocrResultText').textContent = data.text;

            // Show metadata
            const metadataHtml = `
                <div class="d-flex flex-wrap gap-2">
                    <span class="badge bg-primary badge-custom">
                        Method: ${data.method}
                    </span>
                    <span class="badge bg-info badge-custom">
                        Confidence: ${data.confidence}%
                    </span>
                    <span class="badge bg-success badge-custom">
                        Language: ${data.language}
                    </span>
                </div>
            `;
            document.getElementById('ocrMetadata').innerHTML = metadataHtml;

            resultsContainer.style.display = 'block';
        } else {
            document.getElementById('ocrErrorText').textContent = data.error;
            errorContainer.style.display = 'block';
        }
    } catch (error) {
        document.getElementById('ocrErrorText').textContent = 'Network error: ' + error.message;
        errorContainer.style.display = 'block';
    } finally {
        ocrBtn.disabled = false;
        loadingSpinner.style.display = 'none';
    }
}

// Copy results to clipboard
function copyResults() {
    const text = document.getElementById('resultText').textContent;
    navigator.clipboard.writeText(text).then(() => {
        alert('Results copied to clipboard!');
    });
}

// Copy OCR results to clipboard
function copyOCRResults() {
    const text = document.getElementById('ocrResultText').textContent;
    navigator.clipboard.writeText(text).then(() => {
        alert('Text copied to clipboard!');
    });
}

// Load cache statistics
async function loadCacheStats() {
    const statsLoading = document.getElementById('statsLoading');
    const statsContent = document.getElementById('statsContent');

    try {
        const response = await fetch('/api/cache/stats');
        const data = await response.json();

        if (data.success) {
            const stats = data.stats;

            document.getElementById('hitRate').textContent = stats.hit_rate_percent + '%';
            document.getElementById('totalRequests').textContent = stats.total_requests;
            document.getElementById('cacheSize').textContent = stats.cache_size_mb + ' MB';
            document.getElementById('costSavings').textContent = '$' + stats.cost_savings.total.toFixed(4);

            statsLoading.style.display = 'none';
            statsContent.style.display = 'block';
        }
    } catch (error) {
        console.error('Failed to load cache stats:', error);
    }
}

// Refresh stats
function refreshStats() {
    document.getElementById('statsContent').style.display = 'none';
    document.getElementById('statsLoading').style.display = 'block';
    loadCacheStats();
}

// Cleanup cache
async function cleanupCache() {
    if (!confirm('Clean up expired cache entries?')) return;

    try {
        const response = await fetch('/api/cache/cleanup', {
            method: 'POST'
        });
        const data = await response.json();

        if (data.success) {
            alert(`Removed ${data.removed} expired cache entries. Cache size: ${data.cache_size_mb} MB`);
            refreshStats();
        }
    } catch (error) {
        alert('Failed to cleanup cache: ' + error.message);
    }
}

// Clear cache
async function clearCache() {
    if (!confirm('Clear ALL cache entries? This cannot be undone.')) return;

    try {
        const response = await fetch('/api/cache/clear', {
            method: 'POST'
        });
        const data = await response.json();

        if (data.success) {
            alert('Cache cleared successfully!');
            refreshStats();
        }
    } catch (error) {
        alert('Failed to clear cache: ' + error.message);
    }
}
