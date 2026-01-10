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

// ============================================================================
// IMAGE COMPARISON FUNCTIONS
// ============================================================================

let selectedFileCompare1 = null;
let selectedFileCompare2 = null;

// Setup comparison drop zones on page load
document.addEventListener('DOMContentLoaded', function() {
    setupComparisonDropZones();
    setupBatchDropZone();
});

function setupComparisonDropZones() {
    // First image
    const dropZone1 = document.getElementById('dropZoneCompare1');
    const fileInput1 = document.getElementById('fileInputCompare1');

    dropZone1.addEventListener('click', () => fileInput1.click());
    dropZone1.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone1.classList.add('drag-over');
    });
    dropZone1.addEventListener('dragleave', () => {
        dropZone1.classList.remove('drag-over');
    });
    dropZone1.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone1.classList.remove('drag-over');
        const file = e.dataTransfer.files[0];
        if (file && file.type.startsWith('image/')) {
            handleFileSelectCompare1(file);
        }
    });
    fileInput1.addEventListener('change', (e) => {
        const file = e.target.files[0];
        if (file) {
            handleFileSelectCompare1(file);
        }
    });

    // Second image
    const dropZone2 = document.getElementById('dropZoneCompare2');
    const fileInput2 = document.getElementById('fileInputCompare2');

    dropZone2.addEventListener('click', () => fileInput2.click());
    dropZone2.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone2.classList.add('drag-over');
    });
    dropZone2.addEventListener('dragleave', () => {
        dropZone2.classList.remove('drag-over');
    });
    dropZone2.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone2.classList.remove('drag-over');
        const file = e.dataTransfer.files[0];
        if (file && file.type.startsWith('image/')) {
            handleFileSelectCompare2(file);
        }
    });
    fileInput2.addEventListener('change', (e) => {
        const file = e.target.files[0];
        if (file) {
            handleFileSelectCompare2(file);
        }
    });
}

function handleFileSelectCompare1(file) {
    selectedFileCompare1 = file;
    const dropZone = document.getElementById('dropZoneCompare1');
    const imagePreview = document.getElementById('imagePreviewCompare1');
    const previewImg = document.getElementById('previewImgCompare1');

    dropZone.style.display = 'none';
    imagePreview.style.display = 'block';

    const reader = new FileReader();
    reader.onload = (e) => {
        previewImg.src = e.target.result;
    };
    reader.readAsDataURL(file);
}

function handleFileSelectCompare2(file) {
    selectedFileCompare2 = file;
    const dropZone = document.getElementById('dropZoneCompare2');
    const imagePreview = document.getElementById('imagePreviewCompare2');
    const previewImg = document.getElementById('previewImgCompare2');

    dropZone.style.display = 'none';
    imagePreview.style.display = 'block';

    const reader = new FileReader();
    reader.onload = (e) => {
        previewImg.src = e.target.result;
    };
    reader.readAsDataURL(file);
}

function clearImageCompare1() {
    selectedFileCompare1 = null;
    document.getElementById('dropZoneCompare1').style.display = 'block';
    document.getElementById('imagePreviewCompare1').style.display = 'none';
    document.getElementById('fileInputCompare1').value = '';
}

function clearImageCompare2() {
    selectedFileCompare2 = null;
    document.getElementById('dropZoneCompare2').style.display = 'block';
    document.getElementById('imagePreviewCompare2').style.display = 'none';
    document.getElementById('fileInputCompare2').value = '';
}

async function compareImages() {
    if (!selectedFileCompare1 || !selectedFileCompare2) {
        alert('Please select both images to compare');
        return;
    }

    const compareBtn = document.getElementById('compareBtn');
    const loadingSpinner = document.getElementById('loadingSpinnerCompare');
    const resultsContainer = document.getElementById('compareResultsContainer');
    const errorContainer = document.getElementById('compareErrorContainer');

    // Show loading
    compareBtn.disabled = true;
    loadingSpinner.style.display = 'block';
    resultsContainer.style.display = 'none';
    errorContainer.style.display = 'none';

    // Prepare form data
    const formData = new FormData();
    formData.append('file1', selectedFileCompare1);
    formData.append('file2', selectedFileCompare2);
    formData.append('use_ai', document.getElementById('compareUseAI').checked);
    formData.append('mode', document.getElementById('compareMode').value);
    formData.append('provider', document.getElementById('compareProvider').value);

    try {
        const response = await fetch('/api/compare', {
            method: 'POST',
            body: formData
        });

        const data = await response.json();

        if (data.success) {
            displayComparisonResults(data.result);
            resultsContainer.style.display = 'block';
        } else {
            document.getElementById('compareErrorText').textContent = data.error;
            errorContainer.style.display = 'block';
        }
    } catch (error) {
        document.getElementById('compareErrorText').textContent = 'Network error: ' + error.message;
        errorContainer.style.display = 'block';
    } finally {
        compareBtn.disabled = false;
        loadingSpinner.style.display = 'none';
    }
}

function displayComparisonResults(result) {
    // Similarity score
    document.getElementById('similarityScore').textContent = result.similarity_score + '%';

    // Structural info
    const structural = result.structural;
    const structuralHTML = `
        <p><strong>Image 1:</strong> ${structural.image1.dimensions} | ${structural.image1.format}</p>
        <p><strong>Image 2:</strong> ${structural.image2.dimensions} | ${structural.image2.format}</p>
        <p><strong>Identical:</strong> ${result.identical ? '✅ Yes' : '❌ No'}</p>
        <p><strong>Same Dimensions:</strong> ${result.similar_dimensions ? '✅ Yes' : '❌ No'}</p>
        <p><strong>Same Aspect Ratio:</strong> ${structural.same_aspect_ratio ? '✅ Yes' : '❌ No'}</p>
    `;
    document.getElementById('structuralInfo').innerHTML = structuralHTML;

    // AI analysis if available
    if (result.ai_analysis && result.ai_analysis.analysis) {
        document.getElementById('aiAnalysisText').textContent = result.ai_analysis.analysis;
        document.getElementById('aiAnalysisCard').style.display = 'block';
    } else {
        document.getElementById('aiAnalysisCard').style.display = 'none';
    }
}

function copyCompareResults() {
    const result = document.getElementById('similarityScore').textContent + '\n\n';
    const structural = document.getElementById('structuralInfo').textContent;
    const aiAnalysis = document.getElementById('aiAnalysisText').textContent || '';

    const fullText = result + structural + '\n\n' + aiAnalysis;

    navigator.clipboard.writeText(fullText).then(() => {
        alert('Comparison results copied to clipboard!');
    });
}

// ============================================================================
// BATCH PROCESSING FUNCTIONS
// ============================================================================

let selectedBatchFiles = [];

function setupBatchDropZone() {
    const dropZone = document.getElementById('dropZoneBatch');
    const fileInput = document.getElementById('fileInputBatch');

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
        const files = Array.from(e.dataTransfer.files).filter(f => f.type.startsWith('image/'));
        if (files.length > 0) {
            handleBatchFilesSelect(files);
        }
    });
    fileInput.addEventListener('change', (e) => {
        const files = Array.from(e.target.files);
        if (files.length > 0) {
            handleBatchFilesSelect(files);
        }
    });
}

function handleBatchFilesSelect(files) {
    selectedBatchFiles = files;
    document.getElementById('batchFileCount').textContent = files.length;
    document.getElementById('batchFilesList').style.display = 'block';

    const container = document.getElementById('batchFilesContainer');
    container.innerHTML = '';

    files.forEach((file, index) => {
        const fileItem = document.createElement('div');
        fileItem.className = 'small mb-1';
        fileItem.textContent = `${index + 1}. ${file.name}`;
        container.appendChild(fileItem);
    });
}

function clearBatchFiles() {
    selectedBatchFiles = [];
    document.getElementById('batchFilesList').style.display = 'none';
    document.getElementById('fileInputBatch').value = '';
    document.getElementById('batchResultsContainer').style.display = 'none';
}

async function processBatch() {
    if (selectedBatchFiles.length === 0) {
        alert('Please select images to process');
        return;
    }

    const batchBtn = document.getElementById('batchBtn');
    const loadingSpinner = document.getElementById('loadingSpinnerBatch');
    const resultsContainer = document.getElementById('batchResultsContainer');
    const errorContainer = document.getElementById('batchErrorContainer');

    // Show loading
    batchBtn.disabled = true;
    loadingSpinner.style.display = 'block';
    resultsContainer.style.display = 'none';
    errorContainer.style.display = 'none';

    // Prepare form data
    const formData = new FormData();
    selectedBatchFiles.forEach(file => {
        formData.append('files', file);
    });

    const operation = document.getElementById('batchOperation').value;
    const provider = document.getElementById('batchProvider').value;
    const workers = document.getElementById('batchWorkers').value;

    formData.append('provider', provider);
    formData.append('workers', workers);

    let endpoint = '/api/batch-analyze';

    if (operation === 'analyze') {
        const preset = document.getElementById('batchPreset').value;
        if (preset) formData.append('preset', preset);
    } else {
        endpoint = '/api/batch-ocr';
    }

    try {
        const response = await fetch(endpoint, {
            method: 'POST',
            body: formData
        });

        const data = await response.json();

        if (data.success) {
            displayBatchResults(data);
            resultsContainer.style.display = 'block';
        } else {
            document.getElementById('batchErrorText').textContent = data.error;
            errorContainer.style.display = 'block';
        }
    } catch (error) {
        document.getElementById('batchErrorText').textContent = 'Network error: ' + error.message;
        errorContainer.style.display = 'block';
    } finally {
        batchBtn.disabled = false;
        loadingSpinner.style.display = 'none';
    }
}

let currentBatchResults = null;

function displayBatchResults(data) {
    currentBatchResults = data;

    // Summary stats
    document.getElementById('batchTotal').textContent = data.total_images;
    document.getElementById('batchSuccess').textContent = data.successful;
    document.getElementById('batchFailed').textContent = data.failed;
    document.getElementById('batchElapsedTime').textContent = data.elapsed_time.toFixed(2) + 's';

    // Results list
    const resultsList = document.getElementById('batchResultsList');
    resultsList.innerHTML = '';

    data.results.forEach((result, index) => {
        const resultItem = document.createElement('div');
        resultItem.className = 'border-bottom pb-2 mb-2';

        let resultText = '';
        if (result.text) {
            // OCR result
            resultText = result.text.substring(0, 200) + (result.text.length > 200 ? '...' : '');
        } else if (result.result) {
            // Vision analysis result
            resultText = result.result.substring(0, 200) + (result.result.length > 200 ? '...' : '');
        }

        resultItem.innerHTML = `
            <small class="text-muted">${index + 1}. ${result.name}</small>
            <p class="mb-0 small">${resultText}</p>
        `;
        resultsList.appendChild(resultItem);
    });

    // Errors if any
    if (data.errors && data.errors.length > 0) {
        data.errors.forEach((error, index) => {
            const errorItem = document.createElement('div');
            errorItem.className = 'border-bottom pb-2 mb-2 text-danger';
            errorItem.innerHTML = `
                <small>❌ ${error.name}</small>
                <p class="mb-0 small">${error.error}</p>
            `;
            resultsList.appendChild(errorItem);
        });
    }
}

function downloadBatchJSON() {
    if (!currentBatchResults) return;

    const dataStr = JSON.stringify(currentBatchResults, null, 2);
    const dataBlob = new Blob([dataStr], { type: 'application/json' });
    const url = URL.createObjectURL(dataBlob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `batch_results_${Date.now()}.json`;
    link.click();
}

function downloadBatchCSV() {
    if (!currentBatchResults) return;

    let csv = 'Index,Name,Result\n';

    currentBatchResults.results.forEach((result, index) => {
        const text = (result.text || result.result || '').replace(/"/g, '""');
        csv += `${index + 1},"${result.name}","${text}"\n`;
    });

    const dataBlob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(dataBlob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `batch_results_${Date.now()}.csv`;
    link.click();
}
