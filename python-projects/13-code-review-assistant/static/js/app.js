// Utility functions
const api = {
    async get(url) {
        const response = await fetch(url, {
            credentials: 'include'
        });
        return response.json();
    },

    async post(url, data) {
        const response = await fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            credentials: 'include',
            body: JSON.stringify(data)
        });
        return response.json();
    },

    async delete(url) {
        const response = await fetch(url, {
            method: 'DELETE',
            credentials: 'include'
        });
        return response.json();
    }
};

// Toast notifications
function showToast(message, type = 'info') {
    const messagesContainer = document.querySelector('.messages') || createMessagesContainer();

    const alert = document.createElement('div');
    alert.className = `alert alert-${type}`;
    alert.innerHTML = `
        ${message}
        <button class="alert-close" onclick="this.parentElement.remove()">&times;</button>
    `;

    messagesContainer.appendChild(alert);

    setTimeout(() => {
        alert.remove();
    }, 5000);
}

function createMessagesContainer() {
    const container = document.createElement('div');
    container.className = 'messages';
    document.body.appendChild(container);
    return container;
}

// Format dates
function formatDate(dateString) {
    if (!dateString) return 'N/A';
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    });
}

function formatRelativeTime(dateString) {
    if (!dateString) return 'N/A';
    const date = new Date(dateString);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return 'just now';
    if (diffMins < 60) return `${diffMins} min ago`;
    if (diffHours < 24) return `${diffHours} hours ago`;
    if (diffDays < 7) return `${diffDays} days ago`;
    return formatDate(dateString);
}

// Auto-dismiss alerts after 5 seconds
document.addEventListener('DOMContentLoaded', () => {
    const alerts = document.querySelectorAll('.alert');
    alerts.forEach(alert => {
        setTimeout(() => {
            alert.style.opacity = '0';
            setTimeout(() => alert.remove(), 300);
        }, 5000);
    });
});

// Form validation helper
function validateForm(formId, rules) {
    const form = document.getElementById(formId);
    if (!form) return false;

    let isValid = true;
    const errors = [];

    Object.keys(rules).forEach(fieldName => {
        const field = form.querySelector(`[name="${fieldName}"]`);
        const rule = rules[fieldName];

        if (rule.required && !field.value.trim()) {
            errors.push(`${fieldName} is required`);
            isValid = false;
        }

        if (rule.minLength && field.value.length < rule.minLength) {
            errors.push(`${fieldName} must be at least ${rule.minLength} characters`);
            isValid = false;
        }

        if (rule.pattern && !rule.pattern.test(field.value)) {
            errors.push(rule.message || `${fieldName} format is invalid`);
            isValid = false;
        }
    });

    if (!isValid) {
        showToast(errors[0], 'error');
    }

    return isValid;
}

// Loading state helper
function setLoading(button, isLoading, originalText = 'Submit') {
    if (isLoading) {
        button.disabled = true;
        button.dataset.originalText = button.textContent;
        button.textContent = 'Loading...';
    } else {
        button.disabled = false;
        button.textContent = button.dataset.originalText || originalText;
    }
}

// Job polling
async function pollJobStatus(jobId, onComplete, interval = 2000) {
    const checkStatus = async () => {
        try {
            const data = await api.get(`/api/jobs/${jobId}`);

            if (data.success) {
                const status = data.job.status;

                if (status === 'completed' || status === 'failed') {
                    onComplete(data.job);
                    return;
                }

                setTimeout(checkStatus, interval);
            }
        } catch (error) {
            console.error('Error polling job status:', error);
            showToast('Error checking job status', 'error');
        }
    };

    checkStatus();
}

// Debounce helper
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

// Copy to clipboard
async function copyToClipboard(text) {
    try {
        await navigator.clipboard.writeText(text);
        showToast('Copied to clipboard', 'success');
    } catch (error) {
        showToast('Failed to copy', 'error');
    }
}

// Confirm dialog
function confirmAction(message, onConfirm) {
    if (confirm(message)) {
        onConfirm();
    }
}

// Export utilities
window.app = {
    api,
    showToast,
    formatDate,
    formatRelativeTime,
    validateForm,
    setLoading,
    pollJobStatus,
    debounce,
    copyToClipboard,
    confirmAction
};
