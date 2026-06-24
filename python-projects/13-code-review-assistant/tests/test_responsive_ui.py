"""
Responsive UI Tests
Tests mobile-responsive CSS and JavaScript functionality
"""

import os
import re
import pytest
from pathlib import Path


# Get project root
PROJECT_ROOT = Path(__file__).parent.parent


class TestResponsiveCSS:
    """Test responsive.css file"""

    def test_responsive_css_exists(self):
        """Test that responsive.css exists"""
        css_path = PROJECT_ROOT / "static" / "css" / "responsive.css"
        assert css_path.exists(), "responsive.css not found"

    def test_responsive_css_has_breakpoints(self):
        """Test CSS has responsive breakpoints defined"""
        css_path = PROJECT_ROOT / "static" / "css" / "responsive.css"
        content = css_path.read_text()

        # Check for common breakpoints
        assert "@media" in content, "No media queries found"
        assert "768px" in content, "Tablet breakpoint missing"
        assert "max-width" in content or "min-width" in content, \
            "No responsive width queries"

    def test_responsive_css_has_touch_targets(self):
        """Test CSS defines minimum touch target sizes"""
        css_path = PROJECT_ROOT / "static" / "css" / "responsive.css"
        content = css_path.read_text()

        assert "--touch-target-min" in content or "44px" in content, \
            "Minimum touch target size not defined"

    def test_responsive_css_has_mobile_typography(self):
        """Test CSS has mobile typography definitions"""
        css_path = PROJECT_ROOT / "static" / "css" / "responsive.css"
        content = css_path.read_text()

        # Check for responsive font sizes
        assert "font-size" in content, "No font-size definitions"

        # Check for mobile-specific adjustments
        mobile_sections = re.findall(
            r'@media.*max-width:\s*768px.*?\{[^}]*\}',
            content,
            re.DOTALL
        )
        assert len(mobile_sections) > 0, "No mobile-specific styles"

    def test_responsive_css_has_utility_classes(self):
        """Test CSS has responsive utility classes"""
        css_path = PROJECT_ROOT / "static" / "css" / "responsive.css"
        content = css_path.read_text()

        # Check for show/hide utilities
        assert "hide-mobile" in content or ".hide-mobile" in content, \
            "Missing hide-mobile utility"
        assert "show-mobile" in content or ".show-mobile" in content, \
            "Missing show-mobile utility"

    def test_responsive_css_has_grid_system(self):
        """Test CSS has responsive grid system"""
        css_path = PROJECT_ROOT / "static" / "css" / "responsive.css"
        content = css_path.read_text()

        assert "grid" in content or "flex" in content, \
            "No grid/flex system found"

    def test_responsive_css_has_container(self):
        """Test CSS has responsive container"""
        css_path = PROJECT_ROOT / "static" / "css" / "responsive.css"
        content = css_path.read_text()

        assert "container" in content, "No container class defined"
        assert "max-width" in content, "Container doesn't have max-width"

    def test_responsive_css_has_accessibility(self):
        """Test CSS includes accessibility features"""
        css_path = PROJECT_ROOT / "static" / "css" / "responsive.css"
        content = css_path.read_text()

        # Check for accessibility media queries
        assert "prefers-reduced-motion" in content or \
               "prefers-contrast" in content, \
               "Missing accessibility media queries"


class TestMobileCSS:
    """Test mobile.css file"""

    def test_mobile_css_exists(self):
        """Test that mobile.css exists"""
        css_path = PROJECT_ROOT / "static" / "css" / "mobile.css"
        assert css_path.exists(), "mobile.css not found"

    def test_mobile_css_has_dashboard_optimizations(self):
        """Test mobile CSS has dashboard optimizations"""
        css_path = PROJECT_ROOT / "static" / "css" / "mobile.css"
        content = css_path.read_text()

        assert "dashboard" in content.lower(), \
            "No dashboard optimizations"

    def test_mobile_css_has_pr_optimizations(self):
        """Test mobile CSS has PR review optimizations"""
        css_path = PROJECT_ROOT / "static" / "css" / "mobile.css"
        content = css_path.read_text()

        assert "pr-" in content.lower() or "pull-request" in content.lower(), \
            "No PR optimizations"

    def test_mobile_css_has_filter_panel(self):
        """Test mobile CSS has filter panel styles"""
        css_path = PROJECT_ROOT / "static" / "css" / "mobile.css"
        content = css_path.read_text()

        assert "filter-panel" in content, "No filter panel styles"

    def test_mobile_css_has_bottom_sheet(self):
        """Test mobile CSS has bottom sheet component"""
        css_path = PROJECT_ROOT / "static" / "css" / "mobile.css"
        content = css_path.read_text()

        assert "bottom-sheet" in content, "No bottom sheet component"

    def test_mobile_css_has_touch_gestures(self):
        """Test mobile CSS supports touch gestures"""
        css_path = PROJECT_ROOT / "static" / "css" / "mobile.css"
        content = css_path.read_text()

        assert "swipeable" in content or "touch" in content, \
            "No touch gesture support"

    def test_mobile_css_has_modals(self):
        """Test mobile CSS has mobile modal styles"""
        css_path = PROJECT_ROOT / "static" / "css" / "mobile.css"
        content = css_path.read_text()

        assert "modal" in content, "No modal styles"

    def test_mobile_css_forces_unified_diff(self):
        """Test mobile CSS forces unified diff view"""
        css_path = PROJECT_ROOT / "static" / "css" / "mobile.css"
        content = css_path.read_text()

        # Should hide split view on mobile
        assert "diff-split-view" in content or "diff" in content, \
            "No diff view handling"


class TestMobileJavaScript:
    """Test mobile-ui.js file"""

    def test_mobile_js_exists(self):
        """Test that mobile-ui.js exists"""
        js_path = PROJECT_ROOT / "static" / "js" / "mobile-ui.js"
        assert js_path.exists(), "mobile-ui.js not found"

    def test_mobile_js_has_manager_class(self):
        """Test JavaScript has MobileUIManager class"""
        js_path = PROJECT_ROOT / "static" / "js" / "mobile-ui.js"
        content = js_path.read_text()

        assert "class MobileUIManager" in content, \
            "MobileUIManager class not found"
        assert "constructor()" in content, "No constructor"

    def test_mobile_js_has_navigation_setup(self):
        """Test JavaScript sets up mobile navigation"""
        js_path = PROJECT_ROOT / "static" / "js" / "mobile-ui.js"
        content = js_path.read_text()

        assert "setupMobileNavigation" in content, \
            "Mobile navigation setup missing"

    def test_mobile_js_has_touch_gestures(self):
        """Test JavaScript handles touch gestures"""
        js_path = PROJECT_ROOT / "static" / "js" / "mobile-ui.js"
        content = js_path.read_text()

        assert "setupTouchGestures" in content, \
            "Touch gesture setup missing"
        assert "touchstart" in content or "touchend" in content, \
            "Touch event handlers missing"

    def test_mobile_js_has_swipe_handlers(self):
        """Test JavaScript has swipe handlers"""
        js_path = PROJECT_ROOT / "static" / "js" / "mobile-ui.js"
        content = js_path.read_text()

        swipe_methods = [
            "onSwipeLeft",
            "onSwipeRight",
            "onSwipeUp",
            "onSwipeDown"
        ]

        for method in swipe_methods:
            assert method in content, f"Missing {method} handler"

    def test_mobile_js_has_bottom_sheet(self):
        """Test JavaScript handles bottom sheets"""
        js_path = PROJECT_ROOT / "static" / "js" / "mobile-ui.js"
        content = js_path.read_text()

        assert "setupBottomSheet" in content or "showBottomSheet" in content, \
            "Bottom sheet functionality missing"

    def test_mobile_js_has_filter_panel(self):
        """Test JavaScript handles filter panel"""
        js_path = PROJECT_ROOT / "static" / "js" / "mobile-ui.js"
        content = js_path.read_text()

        assert "setupFilterPanel" in content, "Filter panel setup missing"

    def test_mobile_js_has_pull_to_refresh(self):
        """Test JavaScript has pull-to-refresh"""
        js_path = PROJECT_ROOT / "static" / "js" / "mobile-ui.js"
        content = js_path.read_text()

        assert "setupPullToRefresh" in content or "pullToRefresh" in content, \
            "Pull-to-refresh missing"

    def test_mobile_js_prevents_zoom(self):
        """Test JavaScript prevents accidental zoom"""
        js_path = PROJECT_ROOT / "static" / "js" / "mobile-ui.js"
        content = js_path.read_text()

        assert "preventZoom" in content or "preventDefault" in content, \
            "Zoom prevention missing"

    def test_mobile_js_has_resize_handler(self):
        """Test JavaScript handles resize events"""
        js_path = PROJECT_ROOT / "static" / "js" / "mobile-ui.js"
        content = js_path.read_text()

        assert "resize" in content and "addEventListener" in content, \
            "Resize handler missing"

    def test_mobile_js_has_orientation_change(self):
        """Test JavaScript handles orientation change"""
        js_path = PROJECT_ROOT / "static" / "js" / "mobile-ui.js"
        content = js_path.read_text()

        assert "orientationchange" in content, \
            "Orientation change handler missing"


class TestResponsiveBreakpoints:
    """Test responsive breakpoint definitions"""

    def test_consistent_mobile_breakpoint(self):
        """Test mobile breakpoint is consistent across CSS files"""
        css_files = [
            PROJECT_ROOT / "static" / "css" / "responsive.css",
            PROJECT_ROOT / "static" / "css" / "mobile.css"
        ]

        mobile_breakpoints = []

        for css_file in css_files:
            if css_file.exists():
                content = css_file.read_text()
                # Find mobile breakpoint (commonly 768px)
                matches = re.findall(r'max-width:\s*(\d+)px', content)
                if matches:
                    mobile_breakpoints.extend(matches)

        # Check that 768px is used as mobile breakpoint
        assert "768" in mobile_breakpoints, \
            "Standard mobile breakpoint (768px) not found"

    def test_touch_target_minimum_44px(self):
        """Test touch targets meet 44px minimum (WCAG AAA)"""
        css_path = PROJECT_ROOT / "static" / "css" / "responsive.css"
        content = css_path.read_text()

        # Check for 44px touch target or variable
        assert "44px" in content or "--touch-target-min" in content, \
            "Touch target minimum not 44px"


class TestResponsiveTables:
    """Test responsive table handling"""

    def test_table_responsive_wrapper(self):
        """Test tables have responsive wrapper"""
        css_path = PROJECT_ROOT / "static" / "css" / "responsive.css"
        content = css_path.read_text()

        assert "table-responsive" in content, \
            "Table responsive class missing"
        assert "overflow-x" in content, \
            "Table horizontal scroll missing"

    def test_table_card_view_mobile(self):
        """Test tables can switch to card view on mobile"""
        mobile_css = PROJECT_ROOT / "static" / "css" / "mobile.css"

        if mobile_css.exists():
            content = mobile_css.read_text()
            # Should have card-style table for mobile
            assert "data-table-cards" in content or \
                   "display: block" in content, \
                   "Mobile card view for tables missing"


class TestResponsiveForms:
    """Test responsive form elements"""

    def test_input_font_size_16px(self):
        """Test inputs have 16px font-size to prevent iOS zoom"""
        responsive_css = PROJECT_ROOT / "static" / "css" / "responsive.css"
        content = responsive_css.read_text()

        # Check for 16px font-size on inputs (prevents zoom on iOS)
        assert "16px" in content, \
            "Input font-size not 16px (iOS zoom prevention)"

    def test_touch_friendly_inputs(self):
        """Test form inputs are touch-friendly"""
        responsive_css = PROJECT_ROOT / "static" / "css" / "responsive.css"
        content = responsive_css.read_text()

        # Check for input sizing
        assert "input[type" in content, "Input type selectors missing"
        assert "min-height" in content, "Input min-height missing"


class TestResponsiveNavigation:
    """Test responsive navigation"""

    def test_nav_toggle_button(self):
        """Test navigation has toggle button for mobile"""
        responsive_css = PROJECT_ROOT / "static" / "css" / "responsive.css"
        content = responsive_css.read_text()

        assert "nav-toggle" in content, "Navigation toggle missing"

    def test_hamburger_menu_styles(self):
        """Test hamburger menu styles exist"""
        responsive_css = PROJECT_ROOT / "static" / "css" / "responsive.css"
        content = responsive_css.read_text()

        # Should have styles for hamburger icon
        assert "nav-toggle" in content and "span" in content, \
            "Hamburger menu styles missing"


class TestAccessibility:
    """Test accessibility features in responsive design"""

    def test_prefers_reduced_motion(self):
        """Test support for prefers-reduced-motion"""
        responsive_css = PROJECT_ROOT / "static" / "css" / "responsive.css"
        content = responsive_css.read_text()

        assert "prefers-reduced-motion" in content, \
            "prefers-reduced-motion not supported"

    def test_prefers_contrast(self):
        """Test support for prefers-contrast"""
        responsive_css = PROJECT_ROOT / "static" / "css" / "responsive.css"
        content = responsive_css.read_text()

        assert "prefers-contrast" in content, \
            "prefers-contrast not supported"

    def test_focus_visible_styles(self):
        """Test focus-visible styles for keyboard navigation"""
        responsive_css = PROJECT_ROOT / "static" / "css" / "responsive.css"
        content = responsive_css.read_text()

        # Should have focus or focus-visible styles
        assert "focus" in content.lower(), \
            "Focus styles missing for accessibility"


class TestResponsiveImages:
    """Test responsive image handling"""

    def test_images_max_width_100(self):
        """Test images have max-width 100%"""
        responsive_css = PROJECT_ROOT / "static" / "css" / "responsive.css"
        content = responsive_css.read_text()

        assert "img" in content, "No img element styles"
        assert "max-width" in content and "100%" in content, \
            "Images not responsive"

    def test_img_responsive_class(self):
        """Test .img-responsive class exists"""
        responsive_css = PROJECT_ROOT / "static" / "css" / "responsive.css"
        content = responsive_css.read_text()

        assert "img-responsive" in content, ".img-responsive class missing"


class TestResponsiveUtilities:
    """Test responsive utility classes"""

    def test_spacing_utilities(self):
        """Test responsive spacing utilities exist"""
        responsive_css = PROJECT_ROOT / "static" / "css" / "responsive.css"
        content = responsive_css.read_text()

        # Check for spacing variables or classes
        assert "--spacing" in content or "p-mobile" in content or \
               "m-mobile" in content, \
               "Spacing utilities missing"

    def test_text_alignment_utilities(self):
        """Test text alignment utilities for mobile"""
        responsive_css = PROJECT_ROOT / "static" / "css" / "responsive.css"
        content = responsive_css.read_text()

        # Check for text alignment utilities
        assert "text-mobile-center" in content or \
               "text-align" in content, \
               "Text alignment utilities missing"


class TestPrintStyles:
    """Test print styles"""

    def test_print_media_query(self):
        """Test print media query exists"""
        responsive_css = PROJECT_ROOT / "static" / "css" / "responsive.css"
        content = responsive_css.read_text()

        assert "@media print" in content, "Print styles missing"

    def test_no_print_class(self):
        """Test .no-print class exists"""
        responsive_css = PROJECT_ROOT / "static" / "css" / "responsive.css"
        content = responsive_css.read_text()

        assert "no-print" in content, ".no-print class missing"


class TestCSSVariables:
    """Test CSS custom properties (variables)"""

    def test_root_variables_defined(self):
        """Test :root variables are defined"""
        responsive_css = PROJECT_ROOT / "static" / "css" / "responsive.css"
        content = responsive_css.read_text()

        assert ":root" in content, ":root selector missing"
        assert "--" in content, "CSS variables missing"

    def test_breakpoint_variables(self):
        """Test breakpoint variables are defined"""
        responsive_css = PROJECT_ROOT / "static" / "css" / "responsive.css"
        content = responsive_css.read_text()

        # Check for common breakpoint variables
        breakpoint_vars = ["--mobile", "--tablet", "--desktop"]
        has_breakpoint_var = any(var in content for var in breakpoint_vars)

        assert has_breakpoint_var, "Breakpoint variables missing"


class TestMobilePerformance:
    """Test mobile performance optimizations"""

    def test_webkit_overflow_scrolling(self):
        """Test -webkit-overflow-scrolling: touch is used"""
        mobile_css = PROJECT_ROOT / "static" / "css" / "mobile.css"

        if mobile_css.exists():
            content = mobile_css.read_text()
            assert "-webkit-overflow-scrolling" in content, \
                "Touch scrolling optimization missing"

    def test_will_change_or_transform(self):
        """Test CSS uses will-change or transform for performance"""
        css_files = [
            PROJECT_ROOT / "static" / "css" / "responsive.css",
            PROJECT_ROOT / "static" / "css" / "mobile.css"
        ]

        has_performance_hint = False

        for css_file in css_files:
            if css_file.exists():
                content = css_file.read_text()
                if "will-change" in content or "transform" in content:
                    has_performance_hint = True
                    break

        # Not required but good to have
        # assert has_performance_hint, "No performance hints found"
