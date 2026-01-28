// Meeting Summarizer Frontend - Phase 4

class MeetingSummarizer {
    constructor() {
        this.selectedFile = null;
        this.currentJobId = null;
        this.websocket = null;

        this.init();
    }

    init() {
        this.setupElements();
        this.setupEventListeners();
    }

    setupElements() {
        // File upload elements
        this.uploadArea = document.getElementById('uploadArea');
        this.fileInput = document.getElementById('fileInput');
        this.selectFileBtn = document.getElementById('selectFileBtn');
        this.fileInfo = document.getElementById('fileInfo');
        this.fileName = document.getElementById('fileName');
        this.fileSize = document.getElementById('fileSize');

        // Options
        this.summaryLevel = document.getElementById('summaryLevel');
        this.outputFormat = document.getElementById('outputFormat');
        this.language = document.getElementById('language');
        this.extractActions = document.getElementById('extractActions');
        this.extractTopics = document.getElementById('extractTopics');

        // Buttons
        this.analyzeBtn = document.getElementById('analyzeBtn');
        this.downloadBtn = document.getElementById('downloadBtn');
        this.newAnalysisBtn = document.getElementById('newAnalysisBtn');
        this.retryBtn = document.getElementById('retryBtn');

        // Sections
        this.progressSection = document.getElementById('progressSection');
        this.resultsSection = document.getElementById('resultsSection');
        this.errorSection = document.getElementById('errorSection');

        // Progress elements
        this.progressFill = document.getElementById('progressFill');
        this.progressText = document.getElementById('progressText');
        this.statusMessage = document.getElementById('statusMessage');

        // Results elements
        this.processingTime = document.getElementById('processingTime');
        this.estimatedCost = document.getElementById('estimatedCost');
        this.cacheHits = document.getElementById('cacheHits');
        this.summaryPreview = document.getElementById('summaryPreview');
        this.topicsList = document.getElementById('topicsList');
        this.actionsCount = document.getElementById('actionsCount');

        // Error elements
        this.errorMessage = document.getElementById('errorMessage');
    }

    setupEventListeners() {
        // File selection
        this.selectFileBtn.addEventListener('click', () => this.fileInput.click());
        this.fileInput.addEventListener('change', (e) => this.handleFileSelect(e));

        // Drag and drop
        this.uploadArea.addEventListener('dragover', (e) => {
            e.preventDefault();
            this.uploadArea.classList.add('drag-over');
        });

        this.uploadArea.addEventListener('dragleave', () => {
            this.uploadArea.classList.remove('drag-over');
        });

        this.uploadArea.addEventListener('drop', (e) => {
            e.preventDefault();
            this.uploadArea.classList.remove('drag-over');
            const file = e.dataTransfer.files[0];
            if (file) this.handleFile(file);
        });

        // Buttons
        this.analyzeBtn.addEventListener('click', () => this.startAnalysis());
        this.downloadBtn.addEventListener('click', () => this.downloadReport());
        this.newAnalysisBtn.addEventListener('click', () => this.resetUI());
        this.retryBtn.addEventListener('click', () => this.resetUI());
    }

    handleFileSelect(event) {
        const file = event.target.files[0];
        if (file) this.handleFile(file);
    }

    handleFile(file) {
        // Validate file type
        const allowedExtensions = ['.mp3', '.wav', '.webm', '.m4a', '.ogg', '.flac'];
        const fileExt = '.' + file.name.split('.').pop().toLowerCase();

        if (!allowedExtensions.includes(fileExt)) {
            this.showError(`Invalid file type. Allowed: ${allowedExtensions.join(', ')}`);
            return;
        }

        // Validate file size (500MB max)
        const maxSize = 500 * 1024 * 1024;
        if (file.size > maxSize) {
            this.showError('File too large. Maximum size: 500MB');
            return;
        }

        this.selectedFile = file;
        this.fileName.textContent = file.name;
        this.fileSize.textContent = this.formatFileSize(file.size);
        this.fileInfo.style.display = 'block';
        this.analyzeBtn.disabled = false;
    }

    formatFileSize(bytes) {
        if (bytes < 1024) return bytes + ' B';
        if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(2) + ' KB';
        return (bytes / (1024 * 1024)).toFixed(2) + ' MB';
    }

    async startAnalysis() {
        if (!this.selectedFile) return;

        try {
            this.analyzeBtn.disabled = true;
            this.analyzeBtn.textContent = 'Uploading...';

            // Upload file
            const formData = new FormData();
            formData.append('file', this.selectedFile);

            const uploadResponse = await fetch('/api/upload', {
                method: 'POST',
                body: formData
            });

            if (!uploadResponse.ok) {
                throw new Error('Upload failed');
            }

            const uploadData = await uploadResponse.json();
            this.currentJobId = uploadData.job_id;

            // Start analysis
            const options = {
                summary_level: this.summaryLevel.value,
                extract_actions: this.extractActions.checked,
                extract_topics: this.extractTopics.checked,
                output_format: this.outputFormat.value,
                language: this.language.value || null
            };

            const analyzeUrl = `/api/analyze/${this.currentJobId}?` + new URLSearchParams(
                Object.entries(options).filter(([_, v]) => v !== null)
            ).toString();

            const analyzeResponse = await fetch(analyzeUrl, { method: 'POST' });

            if (!analyzeResponse.ok) {
                throw new Error('Failed to start analysis');
            }

            // Show progress section
            this.showProgress();

            // Connect WebSocket for real-time updates
            this.connectWebSocket(this.currentJobId);

            // Poll for status
            this.pollJobStatus(this.currentJobId);

        } catch (error) {
            console.error('Analysis error:', error);
            this.showError(error.message);
            this.analyzeBtn.disabled = false;
            this.analyzeBtn.textContent = 'Start Analysis';
        }
    }

    showProgress() {
        this.progressSection.style.display = 'block';
        this.resultsSection.style.display = 'none';
        this.errorSection.style.display = 'none';

        // Reset progress
        this.updateProgress(0, 'Starting...');
        this.resetStages();
    }

    resetStages() {
        const stages = ['validation', 'transcription', 'summarization', 'action_extraction', 'report_generation'];
        stages.forEach(stage => {
            const element = document.getElementById(`stage-${stage}`);
            if (element) {
                element.classList.remove('completed', 'in-progress', 'failed');
                element.querySelector('.stage-icon').textContent = '⏳';
            }
        });
    }

    updateProgress(percent, message) {
        this.progressFill.style.width = percent + '%';
        this.progressText.textContent = Math.round(percent) + '%';
        this.statusMessage.textContent = message || '';
    }

    updateStage(stageName, status) {
        const element = document.getElementById(`stage-${stageName}`);
        if (!element) return;

        element.classList.remove('completed', 'in-progress', 'failed');
        element.classList.add(status);

        const icon = element.querySelector('.stage-icon');
        if (status === 'completed') {
            icon.textContent = '✓';
        } else if (status === 'in-progress') {
            icon.textContent = '⏳';
        } else if (status === 'failed') {
            icon.textContent = '✗';
        }
    }

    connectWebSocket(jobId) {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/${jobId}`;

        this.websocket = new WebSocket(wsUrl);

        this.websocket.onmessage = (event) => {
            const data = JSON.parse(event.data);
            this.handleProgressUpdate(data);
        };

        this.websocket.onerror = (error) => {
            console.error('WebSocket error:', error);
        };

        this.websocket.onclose = () => {
            console.log('WebSocket closed');
        };
    }

    handleProgressUpdate(state) {
        const percent = state.progress_percent || 0;
        const currentStage = state.current_stage;
        const status = state.status;

        this.updateProgress(percent, `${currentStage || 'Processing'}...`);

        // Update stage indicators
        if (state.stages) {
            Object.keys(state.stages).forEach(stage => {
                const stageData = state.stages[stage];
                if (stageData.status === 'completed') {
                    this.updateStage(stage, 'completed');
                } else if (stageData.status === 'in_progress') {
                    this.updateStage(stage, 'in-progress');
                } else if (stageData.status === 'failed') {
                    this.updateStage(stage, 'failed');
                }
            });
        }

        // Check if completed or failed
        if (status === 'completed') {
            this.updateProgress(100, 'Completed!');
            setTimeout(() => this.showResults(), 1000);
        } else if (status === 'failed') {
            const error = state.errors && state.errors.length > 0
                ? state.errors[0].message
                : 'Processing failed';
            this.showError(error);
        }
    }

    async pollJobStatus(jobId, interval = 2000) {
        const poll = async () => {
            try {
                const response = await fetch(`/api/jobs/${jobId}`);
                if (!response.ok) return;

                const data = await response.json();

                if (data.status === 'completed') {
                    this.showResults();
                } else if (data.status === 'failed') {
                    this.showError(data.error || 'Processing failed');
                } else if (data.status === 'processing' || data.status === 'queued') {
                    setTimeout(poll, interval);
                }
            } catch (error) {
                console.error('Polling error:', error);
                setTimeout(poll, interval);
            }
        };

        setTimeout(poll, interval);
    }

    async showResults() {
        if (this.websocket) {
            this.websocket.close();
        }

        try {
            const response = await fetch(`/api/jobs/${this.currentJobId}`);
            const data = await response.json();

            if (data.status === 'completed') {
                this.progressSection.style.display = 'none';
                this.resultsSection.style.display = 'block';

                // Update stats
                const stats = data.result.statistics || {};
                this.processingTime.textContent = `${(stats.processing_time_seconds || 0).toFixed(1)}s`;
                this.estimatedCost.textContent = `$${(stats.total_cost_usd || 0).toFixed(4)}`;
                this.cacheHits.textContent = stats.cache_hits || 0;

                // Update summary
                this.summaryPreview.textContent = data.result.summary || 'No summary available';

                // Update topics
                const topics = data.result.topics || [];
                this.topicsList.innerHTML = topics.map(topic => `<li>${topic}</li>`).join('');

                // Update actions
                const actionCount = data.result.action_items_count || 0;
                this.actionsCount.textContent = `${actionCount} action items extracted`;
            }
        } catch (error) {
            console.error('Failed to load results:', error);
            this.showError('Failed to load results');
        }
    }

    showError(message) {
        this.progressSection.style.display = 'none';
        this.resultsSection.style.display = 'none';
        this.errorSection.style.display = 'block';
        this.errorMessage.textContent = message;

        if (this.websocket) {
            this.websocket.close();
        }
    }

    downloadReport() {
        if (!this.currentJobId) return;
        window.location.href = `/api/jobs/${this.currentJobId}/download`;
    }

    resetUI() {
        this.selectedFile = null;
        this.currentJobId = null;
        this.fileInput.value = '';
        this.fileInfo.style.display = 'none';
        this.analyzeBtn.disabled = true;
        this.analyzeBtn.textContent = 'Start Analysis';
        this.progressSection.style.display = 'none';
        this.resultsSection.style.display = 'none';
        this.errorSection.style.display = 'none';

        if (this.websocket) {
            this.websocket.close();
        }
    }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    new MeetingSummarizer();
});
