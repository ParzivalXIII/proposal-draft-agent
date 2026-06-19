"""Playwright smoke tests for the redesigned UI.

These tests verify critical paths of the daisyUI 5 + Alpine.js + HTMX redesign.
Precondition: The FastAPI server must be running at http://localhost:8000
"""

BASE_URL = "http://localhost:8000"


def _collect_errors(page):
    """Returns a list of console errors (excluding 404 navigation)."""
    errors = []
    page.on("console", lambda msg: errors.append(f"{msg.type}: {msg.text}")
            if msg.type == "error" and "404" not in msg.text else None)
    return errors


def test_01_page_loads(page):
    """1. Page loads without errors."""
    errors = _collect_errors(page)
    page.goto(f"{BASE_URL}/ui/")
    assert page.title() == "Proposal Draft Agent"
    assert len(errors) == 0, f"Console errors found: {errors}"
    # Verify navbar is rendered
    assert page.locator(".navbar").count() > 0
    # Verify "New Proposal" button exists
    assert page.get_by_role("button", name="New Proposal").count() > 0


def test_02_dark_mode_toggle(page):
    """2. Dark mode toggle works, persists across reload."""
    page.goto(f"{BASE_URL}/ui/")

    # Check initial theme
    initial_theme = page.evaluate("document.documentElement.dataset.theme")
    assert initial_theme == "consulting"

    # Toggle dark mode via Alpine.store directly (theme-controller checkbox
    # is inside a daisyUI swap label which intercepts Playwright clicks)
    page.evaluate("Alpine.store('theme').toggle()")
    page.wait_for_timeout(300)
    dark_theme = page.evaluate("document.documentElement.dataset.theme")
    assert dark_theme == "consulting-dark"

    # Reload and check persistence (cookie should have been set)
    page.reload()
    page.wait_for_timeout(300)
    reloaded_theme = page.evaluate("document.documentElement.dataset.theme")
    assert reloaded_theme == "consulting-dark"

    # Toggle back to light
    page.evaluate("Alpine.store('theme').toggle()")
    page.wait_for_timeout(300)
    assert page.evaluate("document.documentElement.dataset.theme") == "consulting"


def test_03_modal_form_opens_and_validates(page):
    """3. Modal form opens, validates, and closes."""
    page.goto(f"{BASE_URL}/ui/")

    # Open modal
    page.get_by_role("button", name="New Proposal").click()
    page.wait_for_timeout(300)

    # Modal should be visible
    modal = page.locator("#proposalModal")
    assert modal.is_visible()

    # Check form fields exist
    assert page.locator("input[name='client_name']").count() > 0
    assert page.locator("textarea[name='problem_description']").count() > 0
    assert page.locator("textarea[name='rough_scope']").count() > 0

    # Test validation: type short client name and blur
    client_input = page.locator("input[name='client_name']")
    client_input.fill("A")
    client_input.blur()
    page.wait_for_timeout(300)

    # Validation error should appear
    error_text = page.locator("text=Must be at least 2 characters")
    assert error_text.is_visible()

    # Close modal via Escape key (backdrop click may be intercepted by modal content)
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)
    assert not modal.is_visible()


def test_04_proposal_list_card_grid(page):
    """4. Proposal list renders as daisyUI card grid."""
    page.goto(f"{BASE_URL}/ui/")

    # The proposal list should be present
    assert page.locator("#proposal-list").count() > 0

    # There should be a grid container or individual cards
    grid = page.locator(".grid")
    assert grid.count() > 0


def test_05_page_heading_present(page):
    """5. Index page shows proper heading."""
    page.goto(f"{BASE_URL}/ui/")
    heading = page.locator("h1")
    assert heading.is_visible()
    assert heading.text_content() == "Proposals"


def test_06_detail_page_structure(page):
    """6. Detail page for a proposal has proper structure."""
    page.goto(f"{BASE_URL}/ui/")

    # Click on first proposal link if any exist
    view_links = page.locator("a:has-text('View Details')")
    if view_links.count() > 0:
        view_links.first.click()
        page.wait_for_timeout(500)

        # Detail page should have a card
        assert page.locator(".card").count() > 0

        # Should have stats component
        assert page.locator(".stats").count() > 0

        # Should have a back link
        back_link = page.locator("a:has-text('Back to proposals')")
        assert back_link.count() > 0

        # Should have status monitoring section
        assert page.locator("#proposal-status").count() > 0


def test_07_css_loads_daisyui_classes(page):
    """7. CSS loads properly with daisyUI classes."""
    page.goto(f"{BASE_URL}/ui/")

    # Verify daisyUI theme is applied (CSS custom property is computed)
    theme = page.evaluate("getComputedStyle(document.body).getPropertyValue('--color-primary')")
    assert theme is not None and theme != ""


def test_08_toast_container_exists(page):
    """8. Toast notification container is present."""
    page.goto(f"{BASE_URL}/ui/")

    # Toast container should be in the DOM
    toast = page.locator(".toast")
    assert toast.count() > 0
    # It should be positioned at bottom-right
    assert "toast-end" in (toast.get_attribute("class") or "")
    assert "toast-bottom" in (toast.get_attribute("class") or "")


def test_09_responsive_grid(page):
    """9. Grid layout is responsive with 1/2/3 columns."""
    page.set_viewport_size({"width": 1280, "height": 800})
    page.goto(f"{BASE_URL}/ui/")

    # Check grid classes
    grid = page.locator(".grid")
    if grid.count() > 0:
        class_attr = grid.get_attribute("class") or ""
        assert "grid-cols-1" in class_attr
        assert "md:grid-cols-2" in class_attr
        assert "lg:grid-cols-3" in class_attr


def test_10_no_console_errors(page):
    """10. Zero JavaScript errors on all main pages (excl 404 nav)."""
    errors = []

    # Check index page
    page.on("console", lambda msg: errors.append(f"{msg.type}: {msg.text}")
            if msg.type == "error" and "404" not in msg.text else None)
    page.goto(f"{BASE_URL}/ui/")
    page.wait_for_timeout(2000)  # Wait for Alpine/HTMX to initialize
    assert len(errors) == 0, f"Console errors on /ui/: {errors}"

    # Reset error collector for detail page
    errors.clear()
    # Navigate to a non-existent proposal (404 expected but not a JS error)
    page.goto(f"{BASE_URL}/ui/proposals/test-123")
    page.wait_for_timeout(1000)
    # 404 produces a resource error in console - we filter that out
    remaining = [e for e in errors if "404" not in e]
    assert len(remaining) == 0, f"Console errors on detail page: {remaining}"
