/**
 * Issue Detail Page JavaScript
 * Handles interactivity for the issue detail view
 */

/**
 * Toggle expandable sections (AI explanation, fix suggestions, refactoring)
 */
function toggleSection(sectionId) {
    const section = document.getElementById(sectionId);
    const header = section.previousElementSibling;
    const toggleIcon = header.querySelector('.toggle-icon');

    if (section.classList.contains('expanded')) {
        section.classList.remove('expanded');
        toggleIcon.textContent = '▶';
    } else {
        section.classList.add('expanded');
        toggleIcon.textContent = '▼';
    }
}

/**
 * Copy code snippet to clipboard
 */
function copyCode(elementId) {
    const codeElement = document.getElementById(elementId);
    const code = codeElement.textContent;

    navigator.clipboard.writeText(code).then(() => {
        // Show success feedback
        const btn = event.target;
        const originalText = btn.textContent;
        btn.textContent = '✓ Copied!';
        btn.style.background = '#10b981';

        setTimeout(() => {
            btn.textContent = originalText;
            btn.style.background = '';
        }, 2000);
    }).catch(err => {
        console.error('Failed to copy code:', err);
        showNotification('Failed to copy code', 'error');
    });
}

/**
 * Switch between unified and split diff views
 */
function showDiffMode(mode) {
    const unifiedView = document.getElementById('unified-diff');
    const splitView = document.getElementById('split-diff');
    const tabs = document.querySelectorAll('.diff-tab');

    if (mode === 'unified') {
        unifiedView.classList.add('active');
        splitView.classList.remove('active');
        tabs[0].classList.add('active');
        tabs[1].classList.remove('active');
    } else {
        splitView.classList.add('active');
        unifiedView.classList.remove('active');
        tabs[1].classList.add('active');
        tabs[0].classList.remove('active');
    }
}

/**
 * Accept a refactoring suggestion
 */
async function acceptRefactoring(refactoringId) {
    if (!confirm('Are you sure you want to accept this refactoring?')) {
        return;
    }

    try {
        const response = await fetch(`/api/refactorings/${refactoringId}/accept`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            credentials: 'same-origin'
        });

        if (!response.ok) {
            throw new Error('Failed to accept refactoring');
        }

        const data = await response.json();

        if (data.success) {
            showNotification('Refactoring accepted successfully!', 'success');
            // Update UI to show accepted state
            updateRefactoringStatus(refactoringId, 'accepted');
        } else {
            throw new Error(data.error || 'Failed to accept refactoring');
        }
    } catch (error) {
        console.error('Error accepting refactoring:', error);
        showNotification(error.message, 'error');
    }
}

/**
 * Reject a refactoring suggestion
 */
async function rejectRefactoring(refactoringId) {
    if (!confirm('Are you sure you want to reject this refactoring?')) {
        return;
    }

    try {
        const response = await fetch(`/api/refactorings/${refactoringId}/reject`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            credentials: 'same-origin'
        });

        if (!response.ok) {
            throw new Error('Failed to reject refactoring');
        }

        const data = await response.json();

        if (data.success) {
            showNotification('Refactoring rejected', 'info');
            // Update UI to show rejected state
            updateRefactoringStatus(refactoringId, 'rejected');
        } else {
            throw new Error(data.error || 'Failed to reject refactoring');
        }
    } catch (error) {
        console.error('Error rejecting refactoring:', error);
        showNotification(error.message, 'error');
    }
}

/**
 * Update refactoring status in the UI
 */
function updateRefactoringStatus(refactoringId, status) {
    const actions = document.querySelector('.refactoring-actions');
    const statusBadge = document.createElement('div');
    statusBadge.className = 'status-badge';
    statusBadge.style.cssText = 'padding: 10px 20px; border-radius: 6px; font-weight: 600; text-align: center;';

    if (status === 'accepted') {
        statusBadge.style.background = '#d1fae5';
        statusBadge.style.color = '#065f46';
        statusBadge.textContent = '✓ Accepted';
    } else if (status === 'rejected') {
        statusBadge.style.background = '#fee2e2';
        statusBadge.style.color = '#991b1b';
        statusBadge.textContent = '✗ Rejected';
    } else if (status === 'applied') {
        statusBadge.style.background = '#dbeafe';
        statusBadge.style.color = '#1e40af';
        statusBadge.textContent = '✓ Applied';
    }

    actions.innerHTML = '';
    actions.appendChild(statusBadge);
}

/**
 * Apply a suggested fix
 */
async function applyFix(issueId) {
    if (!confirm('Are you sure you want to apply this fix? This will modify the code file.')) {
        return;
    }

    try {
        const response = await fetch(`/api/issues/${issueId}/apply-fix`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            credentials: 'same-origin'
        });

        if (!response.ok) {
            throw new Error('Failed to apply fix');
        }

        const data = await response.json();

        if (data.success) {
            showNotification('Fix applied successfully!', 'success');
            // Optionally reload the page or update the UI
            setTimeout(() => {
                window.location.reload();
            }, 1500);
        } else {
            throw new Error(data.error || 'Failed to apply fix');
        }
    } catch (error) {
        console.error('Error applying fix:', error);
        showNotification(error.message, 'error');
    }
}

/**
 * Dismiss an issue
 */
async function dismissIssue(issueId) {
    if (!confirm('Are you sure you want to dismiss this issue?')) {
        return;
    }

    try {
        const response = await fetch(`/api/issues/${issueId}/dismiss`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            credentials: 'same-origin'
        });

        if (!response.ok) {
            throw new Error('Failed to dismiss issue');
        }

        const data = await response.json();

        if (data.success) {
            showNotification('Issue dismissed', 'success');
            // Redirect to issues list after a brief delay
            setTimeout(() => {
                window.location.href = '/issues';
            }, 1500);
        } else {
            throw new Error(data.error || 'Failed to dismiss issue');
        }
    } catch (error) {
        console.error('Error dismissing issue:', error);
        showNotification(error.message, 'error');
    }
}

/**
 * Create a GitHub issue from this code review issue
 */
async function createGithubIssue(issueId) {
    try {
        const response = await fetch(`/api/issues/${issueId}/create-github-issue`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            credentials: 'same-origin'
        });

        if (!response.ok) {
            // Parse error response to get detailed error message
            const errorData = await response.json().catch(() => ({}));
            const errorMessage = errorData.detail || 'Failed to create GitHub issue';
            throw new Error(errorMessage);
        }

        const data = await response.json();

        if (data.success && data.github_url) {
            showNotification('GitHub issue created!', 'success');
            // Open the GitHub issue in a new tab
            window.open(data.github_url, '_blank');
        } else {
            throw new Error(data.error || 'Failed to create GitHub issue');
        }
    } catch (error) {
        console.error('Error creating GitHub issue:', error);
        showNotification(error.message, 'error');
    }
}

/**
 * Share the issue (copy link to clipboard)
 */
function shareIssue(issueId) {
    const url = window.location.href;

    navigator.clipboard.writeText(url).then(() => {
        showNotification('Link copied to clipboard!', 'success');
    }).catch(err => {
        console.error('Failed to copy link:', err);
        showNotification('Failed to copy link', 'error');
    });
}

/**
 * Show notification toast
 */
function showNotification(message, type = 'info') {
    // Remove any existing notifications
    const existing = document.querySelector('.notification-toast');
    if (existing) {
        existing.remove();
    }

    const toast = document.createElement('div');
    toast.className = 'notification-toast';
    toast.textContent = message;

    // Set styles based on type
    const styles = {
        info: { background: '#3b82f6', color: 'white' },
        success: { background: '#10b981', color: 'white' },
        error: { background: '#dc2626', color: 'white' },
        warning: { background: '#f59e0b', color: 'white' }
    };

    const style = styles[type] || styles.info;
    toast.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        padding: 15px 25px;
        background: ${style.background};
        color: ${style.color};
        border-radius: 8px;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
        z-index: 10000;
        font-size: 14px;
        font-weight: 500;
        animation: slideIn 0.3s ease-out;
    `;

    document.body.appendChild(toast);

    // Auto-remove after 3 seconds
    setTimeout(() => {
        toast.style.animation = 'slideOut 0.3s ease-in';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

/**
 * Initialize page
 */
document.addEventListener('DOMContentLoaded', () => {
    // Set default diff view to unified
    const unifiedTab = document.querySelector('.diff-tab');
    if (unifiedTab) {
        unifiedTab.classList.add('active');
    }

    // Add keyboard shortcuts
    document.addEventListener('keydown', (e) => {
        // Escape key to go back
        if (e.key === 'Escape') {
            window.location.href = '/issues';
        }

        // Ctrl/Cmd + K to copy code
        if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
            e.preventDefault();
            const codeSnippet = document.getElementById('code-snippet');
            if (codeSnippet) {
                copyCode('code-snippet');
            }
        }
    });

    console.log('Issue detail page initialized');
});

// Add CSS animations
const style = document.createElement('style');
style.textContent = `
    @keyframes slideIn {
        from {
            transform: translateX(100%);
            opacity: 0;
        }
        to {
            transform: translateX(0);
            opacity: 1;
        }
    }

    @keyframes slideOut {
        from {
            transform: translateX(0);
            opacity: 1;
        }
        to {
            transform: translateX(100%);
            opacity: 0;
        }
    }
`;
document.head.appendChild(style);
