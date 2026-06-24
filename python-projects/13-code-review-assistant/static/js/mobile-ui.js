/**
 * Mobile UI Manager
 * Handles mobile-specific interactions and touch gestures
 */

class MobileUIManager {
    constructor() {
        this.isMobile = window.innerWidth <= 768;
        this.isTablet = window.innerWidth > 768 && window.innerWidth <= 1024;
        this.touchStartX = 0;
        this.touchStartY = 0;
        this.touchEndX = 0;
        this.touchEndY = 0;

        this.init();
    }

    init() {
        this.setupResponsiveListeners();
        this.setupMobileNavigation();
        this.setupFilterPanel();
        this.setupTouchGestures();
        this.setupBottomSheet();
        this.setupPullToRefresh();
        this.preventZoom();
    }

    /**
     * Setup responsive event listeners
     */
    setupResponsiveListeners() {
        window.addEventListener('resize', () => {
            this.isMobile = window.innerWidth <= 768;
            this.isTablet = window.innerWidth > 768 && window.innerWidth <= 1024;
            this.handleResize();
        });

        // Handle orientation change
        window.addEventListener('orientationchange', () => {
            setTimeout(() => this.handleResize(), 100);
        });
    }

    /**
     * Handle resize events
     */
    handleResize() {
        // Close mobile navigation if switching to desktop
        if (!this.isMobile) {
            const navMenu = document.querySelector('.nav-menu');
            const filterPanel = document.querySelector('.filter-panel');

            if (navMenu) navMenu.classList.remove('active');
            if (filterPanel) filterPanel.classList.remove('active');
        }

        // Adjust chart heights on mobile
        if (this.isMobile) {
            this.adjustChartHeights();
        }
    }

    /**
     * Setup mobile navigation
     */
    setupMobileNavigation() {
        const navToggle = document.querySelector('.nav-toggle');
        const navMenu = document.querySelector('.nav-menu');

        if (navToggle && navMenu) {
            navToggle.addEventListener('click', () => {
                navMenu.classList.toggle('active');
                navToggle.classList.toggle('active');

                // Animate hamburger icon
                navToggle.querySelectorAll('span').forEach((span, index) => {
                    if (navToggle.classList.contains('active')) {
                        if (index === 0) span.style.transform = 'rotate(45deg) translate(5px, 5px)';
                        if (index === 1) span.style.opacity = '0';
                        if (index === 2) span.style.transform = 'rotate(-45deg) translate(7px, -6px)';
                    } else {
                        span.style.transform = 'none';
                        span.style.opacity = '1';
                    }
                });
            });

            // Close menu when clicking outside
            document.addEventListener('click', (e) => {
                if (this.isMobile && !navToggle.contains(e.target) && !navMenu.contains(e.target)) {
                    navMenu.classList.remove('active');
                    navToggle.classList.remove('active');
                    navToggle.querySelectorAll('span').forEach(span => {
                        span.style.transform = 'none';
                        span.style.opacity = '1';
                    });
                }
            });
        }
    }

    /**
     * Setup mobile filter panel
     */
    setupFilterPanel() {
        const filterToggle = document.querySelector('.filter-toggle-mobile');
        const filterPanel = document.querySelector('.filter-panel');
        const filterClose = document.querySelector('.filter-close');
        const filterBackdrop = document.querySelector('.filter-backdrop');

        if (filterToggle && filterPanel) {
            filterToggle.addEventListener('click', () => {
                filterPanel.classList.add('active');
                if (filterBackdrop) filterBackdrop.classList.add('active');
                document.body.style.overflow = 'hidden';
            });

            const closeFilter = () => {
                filterPanel.classList.remove('active');
                if (filterBackdrop) filterBackdrop.classList.remove('active');
                document.body.style.overflow = '';
            };

            if (filterClose) {
                filterClose.addEventListener('click', closeFilter);
            }

            if (filterBackdrop) {
                filterBackdrop.addEventListener('click', closeFilter);
            }
        }
    }

    /**
     * Setup touch gesture handlers
     */
    setupTouchGestures() {
        // Swipe detection
        document.addEventListener('touchstart', (e) => {
            this.touchStartX = e.changedTouches[0].screenX;
            this.touchStartY = e.changedTouches[0].screenY;
        }, { passive: true });

        document.addEventListener('touchend', (e) => {
            this.touchEndX = e.changedTouches[0].screenX;
            this.touchEndY = e.changedTouches[0].screenY;
            this.handleSwipe();
        }, { passive: true });

        // Add swipe support to swipeable elements
        const swipeableElements = document.querySelectorAll('.swipeable');
        swipeableElements.forEach(element => {
            this.addSwipeSupport(element);
        });
    }

    /**
     * Handle swipe gestures
     */
    handleSwipe() {
        const swipeThreshold = 50;
        const deltaX = this.touchEndX - this.touchStartX;
        const deltaY = this.touchEndY - this.touchStartY;

        if (Math.abs(deltaX) > Math.abs(deltaY) && Math.abs(deltaX) > swipeThreshold) {
            if (deltaX > 0) {
                this.onSwipeRight();
            } else {
                this.onSwipeLeft();
            }
        } else if (Math.abs(deltaY) > swipeThreshold) {
            if (deltaY > 0) {
                this.onSwipeDown();
            } else {
                this.onSwipeUp();
            }
        }
    }

    /**
     * Add swipe support to element
     */
    addSwipeSupport(element) {
        let startX = 0;
        let currentX = 0;

        element.addEventListener('touchstart', (e) => {
            startX = e.touches[0].clientX;
        }, { passive: true });

        element.addEventListener('touchmove', (e) => {
            currentX = e.touches[0].clientX;
            const diff = currentX - startX;

            if (Math.abs(diff) > 10) {
                element.style.transform = `translateX(${diff}px)`;
            }
        }, { passive: true });

        element.addEventListener('touchend', () => {
            const diff = currentX - startX;

            if (Math.abs(diff) > 100) {
                // Trigger action
                element.dispatchEvent(new CustomEvent('swipe', {
                    detail: { direction: diff > 0 ? 'right' : 'left' }
                }));
            }

            // Reset position
            element.style.transform = '';
        }, { passive: true });
    }

    /**
     * Swipe gesture handlers
     */
    onSwipeLeft() {
        // Can be used to navigate forward or close panels
        const filterPanel = document.querySelector('.filter-panel');
        if (filterPanel && filterPanel.classList.contains('active')) {
            filterPanel.classList.remove('active');
            document.querySelector('.filter-backdrop')?.classList.remove('active');
        }
    }

    onSwipeRight() {
        // Can be used to navigate back or open panels
        if (this.isMobile && window.history.length > 1) {
            // Optional: implement swipe-to-go-back
        }
    }

    onSwipeDown() {
        // Can be used for pull-to-refresh
    }

    onSwipeUp() {
        // Can be used to dismiss bottom sheets
        const bottomSheet = document.querySelector('.bottom-sheet.active');
        if (bottomSheet) {
            bottomSheet.classList.remove('active');
        }
    }

    /**
     * Setup bottom sheet functionality
     */
    setupBottomSheet() {
        const bottomSheets = document.querySelectorAll('.bottom-sheet');

        bottomSheets.forEach(sheet => {
            const handle = sheet.querySelector('.bottom-sheet-handle');

            if (handle) {
                let startY = 0;
                let currentY = 0;

                handle.addEventListener('touchstart', (e) => {
                    startY = e.touches[0].clientY;
                }, { passive: true });

                handle.addEventListener('touchmove', (e) => {
                    currentY = e.touches[0].clientY;
                    const diff = currentY - startY;

                    if (diff > 0) {
                        sheet.style.transform = `translateY(${diff}px)`;
                    }
                }, { passive: true });

                handle.addEventListener('touchend', () => {
                    const diff = currentY - startY;

                    if (diff > 100) {
                        sheet.classList.remove('active');
                    }

                    sheet.style.transform = '';
                }, { passive: true });
            }
        });
    }

    /**
     * Setup pull-to-refresh functionality
     */
    setupPullToRefresh() {
        if (!this.isMobile) return;

        let pullToRefresh = document.querySelector('.pull-to-refresh');

        if (!pullToRefresh) {
            pullToRefresh = document.createElement('div');
            pullToRefresh.className = 'pull-to-refresh';
            pullToRefresh.innerHTML = '<div class="spinner"></div> Pull to refresh';
            document.body.prepend(pullToRefresh);
        }

        let startY = 0;
        let currentY = 0;
        let isPulling = false;

        document.addEventListener('touchstart', (e) => {
            if (window.scrollY === 0) {
                startY = e.touches[0].clientY;
                isPulling = true;
            }
        }, { passive: true });

        document.addEventListener('touchmove', (e) => {
            if (!isPulling) return;

            currentY = e.touches[0].clientY;
            const diff = currentY - startY;

            if (diff > 0 && window.scrollY === 0) {
                pullToRefresh.style.top = Math.min(diff - 60, 0) + 'px';
            }
        }, { passive: true });

        document.addEventListener('touchend', () => {
            if (!isPulling) return;

            const diff = currentY - startY;

            if (diff > 100) {
                pullToRefresh.classList.add('active');
                // Trigger refresh
                this.handleRefresh();
            }

            pullToRefresh.style.top = '-60px';
            isPulling = false;
        }, { passive: true });
    }

    /**
     * Handle refresh action
     */
    handleRefresh() {
        setTimeout(() => {
            window.location.reload();
        }, 500);
    }

    /**
     * Prevent accidental zoom on double-tap
     */
    preventZoom() {
        let lastTouchEnd = 0;
        document.addEventListener('touchend', (e) => {
            const now = Date.now();
            if (now - lastTouchEnd <= 300) {
                e.preventDefault();
            }
            lastTouchEnd = now;
        }, false);

        // Prevent zoom on input focus
        document.addEventListener('gesturestart', (e) => {
            e.preventDefault();
        });
    }

    /**
     * Adjust chart heights for mobile
     */
    adjustChartHeights() {
        const charts = document.querySelectorAll('.chart-container');
        charts.forEach(chart => {
            if (this.isMobile) {
                chart.style.height = '250px';
            } else {
                chart.style.height = '400px';
            }
        });
    }

    /**
     * Show mobile tooltip
     */
    showTooltip(text, duration = 3000) {
        const tooltip = document.createElement('div');
        tooltip.className = 'tooltip-mobile';
        tooltip.textContent = text;
        document.body.appendChild(tooltip);

        setTimeout(() => {
            tooltip.remove();
        }, duration);
    }

    /**
     * Show bottom sheet
     */
    showBottomSheet(content, options = {}) {
        let bottomSheet = document.querySelector('.bottom-sheet');

        if (!bottomSheet) {
            bottomSheet = document.createElement('div');
            bottomSheet.className = 'bottom-sheet';
            bottomSheet.innerHTML = `
                <div class="bottom-sheet-handle"></div>
                <div class="bottom-sheet-content"></div>
            `;
            document.body.appendChild(bottomSheet);
        }

        const contentDiv = bottomSheet.querySelector('.bottom-sheet-content');
        if (typeof content === 'string') {
            contentDiv.innerHTML = content;
        } else {
            contentDiv.innerHTML = '';
            contentDiv.appendChild(content);
        }

        bottomSheet.classList.add('active');

        // Setup backdrop
        let backdrop = document.querySelector('.bottom-sheet-backdrop');
        if (!backdrop) {
            backdrop = document.createElement('div');
            backdrop.className = 'bottom-sheet-backdrop';
            backdrop.style.cssText = `
                position: fixed;
                top: 0;
                left: 0;
                right: 0;
                bottom: 0;
                background: rgba(0,0,0,0.5);
                z-index: 999;
            `;
            document.body.appendChild(backdrop);
        }

        backdrop.addEventListener('click', () => {
            bottomSheet.classList.remove('active');
            backdrop.remove();
        });
    }

    /**
     * Check if device supports touch
     */
    isTouchDevice() {
        return 'ontouchstart' in window || navigator.maxTouchPoints > 0;
    }

    /**
     * Get viewport dimensions
     */
    getViewport() {
        return {
            width: Math.max(document.documentElement.clientWidth || 0, window.innerWidth || 0),
            height: Math.max(document.documentElement.clientHeight || 0, window.innerHeight || 0)
        };
    }

    /**
     * Check if element is in viewport
     */
    isInViewport(element) {
        const rect = element.getBoundingClientRect();
        const viewport = this.getViewport();

        return (
            rect.top >= 0 &&
            rect.left >= 0 &&
            rect.bottom <= viewport.height &&
            rect.right <= viewport.width
        );
    }
}

// Initialize mobile UI manager when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        window.mobileUI = new MobileUIManager();
    });
} else {
    window.mobileUI = new MobileUIManager();
}

// Export for use in other scripts
if (typeof module !== 'undefined' && module.exports) {
    module.exports = MobileUIManager;
}
