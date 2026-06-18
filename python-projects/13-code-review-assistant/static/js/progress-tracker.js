/**
 * Progress Tracker Component
 * Real-time progress updates for long-running tasks using SSE or polling
 */

class ProgressTracker {
    /**
     * Create a new ProgressTracker instance
     * @param {string} taskId - The ID of the task to track
     * @param {Object} options - Configuration options
     */
    constructor(taskId, options = {}) {
        this.taskId = taskId;
        this.options = {
            updateMethod: options.updateMethod || 'sse', // 'sse' or 'polling'
            pollingInterval: options.pollingInterval || 2000, // ms
            onProgress: options.onProgress || null,
            onComplete: options.onComplete || null,
            onError: options.onError || null,
            showToast: options.showToast !== false,
            progressBarId: options.progressBarId || null,
            ...options
        };

        this.eventSource = null;
        this.pollingTimer = null;
        this.isTracking = false;
        this.currentProgress = 0;
        this.status = 'pending';
    }

    /**
     * Start tracking progress
     */
    start() {
        if (this.isTracking) {
            console.warn('Progress tracking already started for task:', this.taskId);
            return;
        }

        this.isTracking = true;

        if (this.options.updateMethod === 'sse') {
            this.startSSE();
        } else {
            this.startPolling();
        }

        // Show initial progress if progress bar is specified
        if (this.options.progressBarId) {
            this.updateProgressBar(0, 'Starting...');
        }

        if (this.options.showToast) {
            this.showToast('Task started', 'info');
        }
    }

    /**
     * Start Server-Sent Events connection
     */
    startSSE() {
        const url = `/api/tasks/${this.taskId}/progress`;

        this.eventSource = new EventSource(url);

        this.eventSource.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                this.handleProgressUpdate(data);
            } catch (error) {
                console.error('Error parsing SSE data:', error);
            }
        };

        this.eventSource.onerror = (error) => {
            console.error('SSE connection error:', error);
            this.eventSource.close();

            // Fallback to polling
            console.log('Falling back to polling...');
            this.options.updateMethod = 'polling';
            this.startPolling();
        };

        // Add specific event handlers
        this.eventSource.addEventListener('progress', (event) => {
            const data = JSON.parse(event.data);
            this.handleProgressUpdate(data);
        });

        this.eventSource.addEventListener('complete', (event) => {
            const data = JSON.parse(event.data);
            this.handleComplete(data);
        });

        this.eventSource.addEventListener('error', (event) => {
            const data = JSON.parse(event.data);
            this.handleError(data);
        });
    }

    /**
     * Start polling for progress updates
     */
    startPolling() {
        this.pollingTimer = setInterval(async () => {
            try {
                const response = await fetch(`/api/tasks/${this.taskId}/status`);

                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                }

                const data = await response.json();
                this.handleProgressUpdate(data);

                // Stop polling if task is complete or failed
                if (data.status === 'completed' || data.status === 'failed') {
                    this.stopPolling();
                }
            } catch (error) {
                console.error('Polling error:', error);
                this.handleError({ error: error.message });
            }
        }, this.options.pollingInterval);
    }

    /**
     * Stop polling
     */
    stopPolling() {
        if (this.pollingTimer) {
            clearInterval(this.pollingTimer);
            this.pollingTimer = null;
        }
    }

    /**
     * Handle progress update
     * @param {Object} data - Progress data
     */
    handleProgressUpdate(data) {
        this.currentProgress = data.progress || 0;
        this.status = data.status || 'in_progress';

        // Update progress bar
        if (this.options.progressBarId) {
            this.updateProgressBar(this.currentProgress, data.message || '');
        }

        // Call custom progress handler
        if (this.options.onProgress) {
            this.options.onProgress(data);
        }

        // Check if complete
        if (data.status === 'completed') {
            this.handleComplete(data);
        } else if (data.status === 'failed' || data.status === 'error') {
            this.handleError(data);
        }
    }

    /**
     * Handle task completion
     * @param {Object} data - Completion data
     */
    handleComplete(data) {
        this.stop();

        if (this.options.progressBarId) {
            this.updateProgressBar(100, 'Complete!');
            setTimeout(() => {
                this.hideProgressBar();
            }, 2000);
        }

        if (this.options.showToast) {
            this.showToast('Task completed successfully!', 'success');
        }

        if (this.options.onComplete) {
            this.options.onComplete(data);
        }
    }

    /**
     * Handle error
     * @param {Object} data - Error data
     */
    handleError(data) {
        this.stop();

        if (this.options.progressBarId) {
            this.updateProgressBar(this.currentProgress, 'Error occurred');
            this.setProgressBarError();
        }

        if (this.options.showToast) {
            this.showToast(data.error || 'Task failed', 'error');
        }

        if (this.options.onError) {
            this.options.onError(data);
        }
    }

    /**
     * Stop tracking
     */
    stop() {
        this.isTracking = false;

        if (this.eventSource) {
            this.eventSource.close();
            this.eventSource = null;
        }

        this.stopPolling();
    }

    /**
     * Update progress bar
     * @param {number} progress - Progress percentage (0-100)
     * @param {string} message - Status message
     */
    updateProgressBar(progress, message) {
        if (!this.options.progressBarId) return;

        const container = document.getElementById(this.options.progressBarId);
        if (!container) return;

        // Create or update progress bar
        let progressBar = container.querySelector('.progress-bar');
        if (!progressBar) {
            container.innerHTML = `
                <div class="progress-container">
                    <div class="progress-header">
                        <span class="progress-message">Initializing...</span>
                        <span class="progress-percentage">0%</span>
                    </div>
                    <div class="progress-bar-wrapper">
                        <div class="progress-bar" style="width: 0%"></div>
                    </div>
                </div>
            `;
            progressBar = container.querySelector('.progress-bar');
        }

        // Update progress
        progressBar.style.width = `${progress}%`;
        container.querySelector('.progress-percentage').textContent = `${Math.round(progress)}%`;
        container.querySelector('.progress-message').textContent = message;

        // Show container if hidden
        container.style.display = 'block';
    }

    /**
     * Set progress bar to error state
     */
    setProgressBarError() {
        if (!this.options.progressBarId) return;

        const container = document.getElementById(this.options.progressBarId);
        if (!container) return;

        const progressBar = container.querySelector('.progress-bar');
        if (progressBar) {
            progressBar.classList.add('progress-bar-error');
        }
    }

    /**
     * Hide progress bar
     */
    hideProgressBar() {
        if (!this.options.progressBarId) return;

        const container = document.getElementById(this.options.progressBarId);
        if (container) {
            container.style.display = 'none';
        }
    }

    /**
     * Show toast notification
     * @param {string} message - Toast message
     * @param {string} type - Toast type (info, success, error, warning)
     */
    showToast(message, type = 'info') {
        if (window.showNotification) {
            window.showNotification(message, type);
        } else {
            // Fallback: create simple toast
            const toast = document.createElement('div');
            toast.className = `toast toast-${type}`;
            toast.textContent = message;
            toast.style.cssText = `
                position: fixed;
                top: 20px;
                right: 20px;
                padding: 15px 25px;
                background: ${type === 'success' ? '#10b981' : type === 'error' ? '#ef4444' : type === 'warning' ? '#f59e0b' : '#3b82f6'};
                color: white;
                border-radius: 8px;
                box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
                z-index: 10000;
                font-size: 14px;
                font-weight: 500;
                animation: slideIn 0.3s ease-out;
            `;

            document.body.appendChild(toast);

            setTimeout(() => {
                toast.style.animation = 'slideOut 0.3s ease-in';
                setTimeout(() => toast.remove(), 300);
            }, 3000);
        }
    }

    /**
     * Get current progress
     * @returns {number} Current progress percentage
     */
    getProgress() {
        return this.currentProgress;
    }

    /**
     * Get current status
     * @returns {string} Current status
     */
    getStatus() {
        return this.status;
    }
}

/**
 * Toast Notification System
 * Global notification system for the application
 */
class ToastNotification {
    constructor() {
        this.container = null;
        this.toasts = [];
        this.maxToasts = 5;
    }

    /**
     * Initialize the toast container
     */
    init() {
        if (this.container) return;

        this.container = document.createElement('div');
        this.container.id = 'toast-container';
        this.container.className = 'toast-container';
        this.container.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            z-index: 10000;
            display: flex;
            flex-direction: column;
            gap: 10px;
        `;

        document.body.appendChild(this.container);
    }

    /**
     * Show a toast notification
     * @param {string} message - Toast message
     * @param {string} type - Toast type
     * @param {number} duration - Duration in ms
     */
    show(message, type = 'info', duration = 3000) {
        this.init();

        // Remove oldest toast if at max
        if (this.toasts.length >= this.maxToasts) {
            this.toasts[0].remove();
            this.toasts.shift();
        }

        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;

        const icons = {
            info: 'ℹ️',
            success: '✅',
            error: '❌',
            warning: '⚠️'
        };

        toast.innerHTML = `
            <span class="toast-icon">${icons[type] || icons.info}</span>
            <span class="toast-message">${message}</span>
            <button class="toast-close" onclick="this.parentElement.remove()">×</button>
        `;

        const colors = {
            info: '#3b82f6',
            success: '#10b981',
            error: '#ef4444',
            warning: '#f59e0b'
        };

        toast.style.cssText = `
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 15px 20px;
            background: ${colors[type]};
            color: white;
            border-radius: 8px;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
            font-size: 14px;
            font-weight: 500;
            animation: slideIn 0.3s ease-out;
            min-width: 300px;
            max-width: 400px;
        `;

        this.container.appendChild(toast);
        this.toasts.push(toast);

        // Auto-remove after duration
        if (duration > 0) {
            setTimeout(() => {
                toast.style.animation = 'slideOut 0.3s ease-in';
                setTimeout(() => {
                    toast.remove();
                    this.toasts = this.toasts.filter(t => t !== toast);
                }, 300);
            }, duration);
        }

        return toast;
    }
}

// Create global toast instance
const toast = new ToastNotification();

// Global notification function
window.showNotification = function(message, type = 'info', duration = 3000) {
    toast.show(message, type, duration);
};

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { ProgressTracker, ToastNotification };
}
