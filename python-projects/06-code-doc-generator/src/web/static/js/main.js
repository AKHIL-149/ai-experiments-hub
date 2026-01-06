/**
 * Code Documentation Generator - Main JavaScript
 * Version: 0.7.2
 * Handles form submission, file upload, drag-and-drop, and API interactions
 */

// ===== Global State =====
let selectedFile = null;

// ===== DOM Elements =====
const docGenForm = document.getElementById('docGenForm');
const uploadArea = document.getElementById('uploadArea');
const fileInput = document.getElementById('fileInput');
const fileInfo = document.getElementById('fileInfo');
const fileName = document.getElementById('fileName');
const codeInput = document.getElementById('codeInput');
const languageSelect = document.getElementById('languageSelect');
const formatSelect = document.getElementById('formatSelect');
const useAI = document.getElementById('useAI');
const aiOptions = document.getElementById('aiOptions');
const providerSelect = document.getElementById('providerSelect');
const modelInput = document.getElementById('modelInput');
const generateBtn = document.getElementById('generateBtn');
const progressArea = document.getElementById('progressArea');
const progressText = document.getElementById('progressText');
const errorArea = document.getElementById('errorArea');
const errorText = document.getElementById('errorText');

// ===== Event Listeners =====
document.addEventListener('DOMContentLoaded', function() {
    initializeEventListeners();
    loadSavedSettings();
});

function initializeEventListeners() {
    // Form submission
    if (docGenForm) {
        docGenForm.addEventListener('submit', handleFormSubmit);
    }

    // File upload area
    if (uploadArea) {
        uploadArea.addEventListener('click', () => fileInput.click());
        uploadArea.addEventListener('dragover', handleDragOver);
        uploadArea.addEventListener('dragleave', handleDragLeave);
        uploadArea.addEventListener('drop', handleDrop);
    }

    // File input change
    if (fileInput) {
        fileInput.addEventListener('change', handleFileSelect);
    }

    // AI toggle
    if (useAI && aiOptions) {
        useAI.addEventListener('change', function() {
            aiOptions.style.display = this.checked ? 'block' : 'none';
        });
    }

    // Auto-save settings
    if (formatSelect) formatSelect.addEventListener('change', saveSettings);
    if (providerSelect) providerSelect.addEventListener('change', saveSettings);
    if (useAI) useAI.addEventListener('change', saveSettings);

    // Tab switching - clear file when switching to paste
    const pasteTab = document.getElementById('paste-tab');
    if (pasteTab) {
        pasteTab.addEventListener('click', function() {
            selectedFile = null;
            if (fileInfo) fileInfo.classList.add('d-none');
        });
    }

    // Auto-detect language from code
    if (codeInput) {
        codeInput.addEventListener('input', debounce(autoDetectLanguage, 500));
    }
}

// ===== File Upload Handlers =====
function handleDragOver(e) {
    e.preventDefault();
    e.stopPropagation();
    uploadArea.classList.add('dragover');
}

function handleDragLeave(e) {
    e.preventDefault();
    e.stopPropagation();
    uploadArea.classList.remove('dragover');
}

function handleDrop(e) {
    e.preventDefault();
    e.stopPropagation();
    uploadArea.classList.remove('dragover');

    const files = e.dataTransfer.files;
    if (files.length > 0) {
        const file = files[0];
        if (isValidCodeFile(file)) {
            selectedFile = file;
            displayFileInfo(file);
        } else {
            showError('Please upload a valid code file (.py, .js, .ts, .java)');
        }
    }
}

function handleFileSelect(e) {
    const file = e.target.files[0];
    if (file) {
        if (isValidCodeFile(file)) {
            selectedFile = file;
            displayFileInfo(file);
        } else {
            showError('Please upload a valid code file (.py, .js, .ts, .java)');
        }
    }
}

function displayFileInfo(file) {
    if (fileName && fileInfo) {
        fileName.textContent = file.name;
        fileInfo.classList.remove('d-none');

        // Auto-detect language from file extension
        const ext = file.name.split('.').pop().toLowerCase();
        const langMap = {
            'py': 'python',
            'js': 'javascript',
            'ts': 'typescript',
            'java': 'java'
        };
        if (langMap[ext] && languageSelect) {
            languageSelect.value = langMap[ext];
        }
    }
}

function isValidCodeFile(file) {
    const validExtensions = ['.py', '.js', '.ts', '.java'];
    return validExtensions.some(ext => file.name.toLowerCase().endsWith(ext));
}

// ===== Form Submission =====
async function handleFormSubmit(e) {
    e.preventDefault();

    // Validate input
    const activeTab = document.querySelector('.nav-link.active').id;
    const isUploadTab = activeTab === 'upload-tab';

    if (isUploadTab && !selectedFile) {
        showError('Please select a file to upload');
        return;
    }

    if (!isUploadTab && !codeInput.value.trim()) {
        showError('Please paste some code');
        return;
    }

    // Show progress
    showProgress('Preparing your code...');
    hideError();

    try {
        // Prepare form data
        const formData = new FormData();

        if (isUploadTab && selectedFile) {
            formData.append('file', selectedFile);
        } else {
            formData.append('code', codeInput.value);
        }

        // Add other form fields
        formData.append('language', languageSelect.value);
        formData.append('format', formatSelect.value);
        formData.append('provider', providerSelect.value);
        formData.append('model', modelInput.value || '');
        formData.append('use_ai', useAI.checked);

        // Update progress
        updateProgress('Parsing code structure...');

        // Make API request
        const response = await fetch('/api/generate', {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to generate documentation');
        }

        // Update progress
        updateProgress('Generating documentation...');

        const result = await response.json();

        // Hide progress
        hideProgress();

        // Handle result
        if (result.status === 'success') {
            // Redirect to results page or display inline
            displayResults(result);
        } else {
            throw new Error(result.message || 'Unknown error occurred');
        }

    } catch (error) {
        hideProgress();
        showError(error.message);
        console.error('Error:', error);
    }
}

// ===== Progress Handlers =====
function showProgress(message) {
    if (progressArea && progressText) {
        progressText.textContent = message;
        progressArea.classList.remove('d-none');
        if (generateBtn) generateBtn.disabled = true;
    }
}

function updateProgress(message) {
    if (progressText) {
        progressText.textContent = message;
    }
}

function hideProgress() {
    if (progressArea && generateBtn) {
        progressArea.classList.add('d-none');
        generateBtn.disabled = false;
    }
}

// ===== Error Handlers =====
function showError(message) {
    if (errorArea && errorText) {
        errorText.textContent = message;
        errorArea.classList.remove('d-none');

        // Auto-hide after 5 seconds
        setTimeout(hideError, 5000);
    }
}

function hideError() {
    if (errorArea) {
        errorArea.classList.add('d-none');
    }
}

// ===== Results Display =====
function displayResults(result) {
    // Create a form to submit to results page
    const form = document.createElement('form');
    form.method = 'POST';
    form.action = '/results';

    // Add result data as hidden fields
    const fields = {
        code: result.code || '',
        documentation: result.documentation || '',
        raw_documentation: result.raw_documentation || result.documentation || '',
        format: result.format || 'markdown',
        language: result.language || 'python',
        ai_enhanced: result.ai_enhanced || false,
        stats: JSON.stringify(result.stats || {}),
        metadata: JSON.stringify(result.metadata || {})
    };

    for (const [key, value] of Object.entries(fields)) {
        const input = document.createElement('input');
        input.type = 'hidden';
        input.name = key;
        input.value = value;
        form.appendChild(input);
    }

    document.body.appendChild(form);
    form.submit();
}

// ===== Language Auto-Detection =====
function autoDetectLanguage() {
    if (!codeInput || !languageSelect) return;
    if (languageSelect.value !== 'auto') return; // User manually selected

    const code = codeInput.value.trim();
    if (code.length < 10) return;

    // Simple heuristics for language detection
    let detectedLang = 'python'; // default

    // Python indicators
    if (code.includes('def ') || code.includes('import ') || code.includes('class ') && code.includes(':')) {
        detectedLang = 'python';
    }
    // JavaScript/TypeScript indicators
    else if (code.includes('function ') || code.includes('const ') || code.includes('let ') || code.includes('=>')) {
        detectedLang = 'javascript';
        if (code.includes('interface ') || code.includes(': string') || code.includes(': number')) {
            detectedLang = 'typescript';
        }
    }
    // Java indicators
    else if (code.includes('public class ') || code.includes('private ') || code.includes('System.out.println')) {
        detectedLang = 'java';
    }

    // Update language select if still on auto
    if (languageSelect.value === 'auto') {
        languageSelect.value = detectedLang;
    }
}

// ===== Settings Persistence =====
function saveSettings() {
    const settings = {
        format: formatSelect ? formatSelect.value : 'markdown',
        provider: providerSelect ? providerSelect.value : 'ollama',
        useAI: useAI ? useAI.checked : true
    };

    localStorage.setItem('docGenSettings', JSON.stringify(settings));
}

function loadSavedSettings() {
    const saved = localStorage.getItem('docGenSettings');
    if (saved) {
        try {
            const settings = JSON.parse(saved);

            if (formatSelect && settings.format) {
                formatSelect.value = settings.format;
            }

            if (providerSelect && settings.provider) {
                providerSelect.value = settings.provider;
            }

            if (useAI && typeof settings.useAI !== 'undefined') {
                useAI.checked = settings.useAI;
                if (aiOptions) {
                    aiOptions.style.display = settings.useAI ? 'block' : 'none';
                }
            }
        } catch (e) {
            console.error('Failed to load saved settings:', e);
        }
    }
}

// ===== Utility Functions =====
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// ===== Health Check =====
async function checkAPIHealth() {
    try {
        const response = await fetch('/api/health');
        const data = await response.json();
        console.log('API Health:', data);
        return data.status === 'healthy';
    } catch (error) {
        console.error('API health check failed:', error);
        return false;
    }
}

// Run health check on page load
if (document.getElementById('docGenForm')) {
    checkAPIHealth().then(healthy => {
        if (!healthy) {
            console.warn('API may not be fully operational');
        }
    });
}

// ===== Export for use in templates =====
window.docGen = {
    handleFormSubmit,
    showError,
    hideError,
    showProgress,
    hideProgress,
    displayResults,
    checkAPIHealth
};
