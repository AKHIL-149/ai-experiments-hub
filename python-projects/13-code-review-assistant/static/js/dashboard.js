/**
 * Dashboard Enhancements
 * Health score cards, trend charts, and activity feeds
 */

/**
 * Health Score Calculator
 * Calculates overall code health based on various metrics
 */
class HealthScoreCalculator {
    /**
     * Calculate health score from metrics
     * @param {Object} metrics - Code metrics
     * @returns {Object} Health score data
     */
    static calculate(metrics) {
        const {
            total_issues = 0,
            critical_issues = 0,
            error_issues = 0,
            warning_issues = 0,
            info_issues = 0,
            files_analyzed = 0,
            lines_of_code = 0,
            test_coverage = 0,
            complexity_average = 0
        } = metrics;

        let score = 100;

        // Deduct points for issues
        score -= critical_issues * 10;
        score -= error_issues * 5;
        score -= warning_issues * 2;
        score -= info_issues * 0.5;

        // Deduct points for complexity
        if (complexity_average > 10) {
            score -= (complexity_average - 10) * 2;
        }

        // Bonus points for test coverage
        if (test_coverage > 80) {
            score += 5;
        } else if (test_coverage < 50) {
            score -= 10;
        }

        // Ensure score is between 0 and 100
        score = Math.max(0, Math.min(100, score));

        // Determine grade
        let grade, color, status;
        if (score >= 90) {
            grade = 'A';
            color = '#10b981';
            status = 'Excellent';
        } else if (score >= 80) {
            grade = 'B';
            color = '#3b82f6';
            status = 'Good';
        } else if (score >= 70) {
            grade = 'C';
            color = '#f59e0b';
            status = 'Fair';
        } else if (score >= 60) {
            grade = 'D';
            color = '#ef4444';
            status = 'Poor';
        } else {
            grade = 'F';
            color = '#dc2626';
            status = 'Critical';
        }

        return {
            score: Math.round(score),
            grade,
            color,
            status,
            metrics: {
                issues: total_issues,
                criticalIssues: critical_issues,
                linesOfCode: lines_of_code,
                testCoverage: test_coverage,
                complexity: complexity_average
            }
        };
    }
}

/**
 * Health Score Card Component
 */
class HealthScoreCard {
    constructor(containerId, options = {}) {
        this.container = document.getElementById(containerId);
        this.options = options;
    }

    render(healthData) {
        if (!this.container) return;

        const { score, grade, color, status, metrics } = healthData;

        this.container.innerHTML = `
            <div class="health-score-card">
                <div class="health-score-header">
                    <h3>Code Health</h3>
                    <span class="health-status" style="color: ${color}">${status}</span>
                </div>
                <div class="health-score-display">
                    <div class="score-circle" style="border-color: ${color}">
                        <span class="score-value">${score}</span>
                        <span class="score-grade">${grade}</span>
                    </div>
                    <div class="score-bar-container">
                        <div class="score-bar" style="width: ${score}%; background: ${color}"></div>
                    </div>
                </div>
                <div class="health-metrics">
                    <div class="metric">
                        <span class="metric-label">Issues</span>
                        <span class="metric-value">${metrics.issues}</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">Critical</span>
                        <span class="metric-value metric-critical">${metrics.criticalIssues}</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">Lines of Code</span>
                        <span class="metric-value">${this.formatNumber(metrics.linesOfCode)}</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">Test Coverage</span>
                        <span class="metric-value">${metrics.testCoverage}%</span>
                    </div>
                </div>
            </div>
        `;
    }

    formatNumber(num) {
        if (num >= 1000000) {
            return (num / 1000000).toFixed(1) + 'M';
        } else if (num >= 1000) {
            return (num / 1000).toFixed(1) + 'K';
        }
        return num.toString();
    }
}

/**
 * Issue Trend Chart
 * Visualizes issue trends over time using Chart.js
 */
class IssueTrendChart {
    constructor(canvasId, options = {}) {
        this.canvas = document.getElementById(canvasId);
        this.chart = null;
        this.options = {
            title: options.title || 'Issue Trends',
            days: options.days || 30,
            ...options
        };
    }

    render(trendData) {
        if (!this.canvas || !window.Chart) {
            console.error('Canvas element or Chart.js not found');
            return;
        }

        const ctx = this.canvas.getContext('2d');

        // Destroy existing chart
        if (this.chart) {
            this.chart.destroy();
        }

        // Prepare data
        const labels = trendData.map(d => d.date);
        const datasets = [
            {
                label: 'Critical',
                data: trendData.map(d => d.critical || 0),
                borderColor: '#dc2626',
                backgroundColor: 'rgba(220, 38, 38, 0.1)',
                tension: 0.4
            },
            {
                label: 'Error',
                data: trendData.map(d => d.error || 0),
                borderColor: '#ef4444',
                backgroundColor: 'rgba(239, 68, 68, 0.1)',
                tension: 0.4
            },
            {
                label: 'Warning',
                data: trendData.map(d => d.warning || 0),
                borderColor: '#f59e0b',
                backgroundColor: 'rgba(245, 158, 11, 0.1)',
                tension: 0.4
            },
            {
                label: 'Info',
                data: trendData.map(d => d.info || 0),
                borderColor: '#3b82f6',
                backgroundColor: 'rgba(59, 130, 246, 0.1)',
                tension: 0.4
            }
        ];

        this.chart = new Chart(ctx, {
            type: 'line',
            data: {
                labels,
                datasets
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: true,
                        position: 'top'
                    },
                    title: {
                        display: true,
                        text: this.options.title
                    },
                    tooltip: {
                        mode: 'index',
                        intersect: false
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: {
                            precision: 0
                        }
                    }
                },
                interaction: {
                    mode: 'nearest',
                    axis: 'x',
                    intersect: false
                }
            }
        });
    }

    update(newData) {
        if (!this.chart) {
            this.render(newData);
            return;
        }

        const labels = newData.map(d => d.date);
        this.chart.data.labels = labels;
        this.chart.data.datasets[0].data = newData.map(d => d.critical || 0);
        this.chart.data.datasets[1].data = newData.map(d => d.error || 0);
        this.chart.data.datasets[2].data = newData.map(d => d.warning || 0);
        this.chart.data.datasets[3].data = newData.map(d => d.info || 0);
        this.chart.update();
    }

    destroy() {
        if (this.chart) {
            this.chart.destroy();
            this.chart = null;
        }
    }
}

/**
 * Issue Distribution Chart (Pie/Doughnut)
 */
class IssueDistributionChart {
    constructor(canvasId, options = {}) {
        this.canvas = document.getElementById(canvasId);
        this.chart = null;
        this.options = {
            type: options.type || 'doughnut',
            title: options.title || 'Issue Distribution',
            ...options
        };
    }

    render(distributionData) {
        if (!this.canvas || !window.Chart) {
            console.error('Canvas element or Chart.js not found');
            return;
        }

        const ctx = this.canvas.getContext('2d');

        if (this.chart) {
            this.chart.destroy();
        }

        this.chart = new Chart(ctx, {
            type: this.options.type,
            data: {
                labels: ['Critical', 'Error', 'Warning', 'Info'],
                datasets: [{
                    data: [
                        distributionData.critical || 0,
                        distributionData.error || 0,
                        distributionData.warning || 0,
                        distributionData.info || 0
                    ],
                    backgroundColor: [
                        '#dc2626',
                        '#ef4444',
                        '#f59e0b',
                        '#3b82f6'
                    ],
                    borderWidth: 2,
                    borderColor: '#ffffff'
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: true,
                        position: 'right'
                    },
                    title: {
                        display: true,
                        text: this.options.title
                    }
                }
            }
        });
    }
}

/**
 * Recent Activity Feed
 */
class ActivityFeed {
    constructor(containerId, options = {}) {
        this.container = document.getElementById(containerId);
        this.options = {
            maxItems: options.maxItems || 10,
            showTimestamps: options.showTimestamps !== false,
            ...options
        };
        this.activities = [];
    }

    render(activities) {
        if (!this.container) return;

        this.activities = activities.slice(0, this.options.maxItems);

        if (this.activities.length === 0) {
            this.container.innerHTML = `
                <div class="activity-feed-empty">
                    <span class="empty-icon">📭</span>
                    <p>No recent activity</p>
                </div>
            `;
            return;
        }

        const activityHTML = this.activities.map(activity => {
            const icon = this.getActivityIcon(activity.type);
            const timeAgo = this.options.showTimestamps ?
                `<span class="activity-time">${this.formatTimeAgo(activity.timestamp)}</span>` : '';

            return `
                <div class="activity-item" data-type="${activity.type}">
                    <div class="activity-icon">${icon}</div>
                    <div class="activity-content">
                        <div class="activity-title">${activity.title}</div>
                        <div class="activity-description">${activity.description}</div>
                        ${timeAgo}
                    </div>
                </div>
            `;
        }).join('');

        this.container.innerHTML = `
            <div class="activity-feed">
                ${activityHTML}
            </div>
        `;
    }

    addActivity(activity) {
        this.activities.unshift(activity);
        this.activities = this.activities.slice(0, this.options.maxItems);
        this.render(this.activities);
    }

    getActivityIcon(type) {
        const icons = {
            'issue_found': '🔍',
            'issue_fixed': '✅',
            'pr_reviewed': '👀',
            'refactoring_suggested': '🔧',
            'analysis_completed': '📊',
            'repo_added': '📁',
            'commit': '💾',
            'error': '❌',
            'warning': '⚠️',
            'default': '📌'
        };
        return icons[type] || icons.default;
    }

    formatTimeAgo(timestamp) {
        const now = new Date();
        const then = new Date(timestamp);
        const seconds = Math.floor((now - then) / 1000);

        if (seconds < 60) return 'just now';
        if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
        if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
        if (seconds < 604800) return `${Math.floor(seconds / 86400)}d ago`;
        return then.toLocaleDateString();
    }

    clear() {
        this.activities = [];
        this.render([]);
    }
}

/**
 * Dashboard Stats Cards
 */
class StatsCard {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
    }

    render(stats) {
        if (!this.container) return;

        const cards = stats.map(stat => `
            <div class="stat-card" style="border-left-color: ${stat.color || '#3b82f6'}">
                <div class="stat-icon" style="background: ${stat.color || '#3b82f6'}20">
                    ${stat.icon || '📊'}
                </div>
                <div class="stat-content">
                    <div class="stat-label">${stat.label}</div>
                    <div class="stat-value">${stat.value}</div>
                    ${stat.change ? `<div class="stat-change ${stat.change > 0 ? 'positive' : 'negative'}">
                        ${stat.change > 0 ? '↑' : '↓'} ${Math.abs(stat.change)}%
                    </div>` : ''}
                </div>
            </div>
        `).join('');

        this.container.innerHTML = cards;
    }
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        HealthScoreCalculator,
        HealthScoreCard,
        IssueTrendChart,
        IssueDistributionChart,
        ActivityFeed,
        StatsCard
    };
}
