# pylint: disable=broad-exception-caught,too-many-statements,except-pass
"""test_xf_mcp_screenshots.py — Description screenshots for xf_mcp

Captures 8 specific screenshots for the module's static/description/ folder.

Run:
  bash .claude/skills/odoo-ui-tests/scripts/run_ui_tests.sh \
       --script xf_mcp/tests/ui/test_xf_mcp_screenshots.py \
       --url http://localhost:17001 --db ehs
"""

from pathlib import Path

DESCRIPTION_DIR = Path(__file__).parents[2] / "static" / "description"


def _save(s, filename: str) -> None:
    """Save a full-page screenshot to the description folder with exact filename."""
    path = str(DESCRIPTION_DIR / filename)
    try:
        s.page.screenshot(path=path, full_page=True)
        s._ok(f"Screenshot → {filename}", path)
    except Exception as exc:  # noqa: BLE001
        s._fail(f"Screenshot → {filename}", err=str(exc))


def run(s):
    # ── Login ─────────────────────────────────────────────────────────────────
    if not s.login(db="ehs"):
        return

    # ── 1. Tools list ─────────────────────────────────────────────────────────
    s.go_to_action("xf_mcp.action_mcp_tool")
    if s.stopped:
        return
    s.wait(800)
    _save(s, "screenshot_01_tools_list.png")

    # ── 2. Tool form (first record) ───────────────────────────────────────────
    s.open_nth_record(0)
    s.wait(600)
    # Click the Input Schema tab to show JSON content
    s.click_tab("Input Schema")
    s.wait(400)
    _save(s, "screenshot_02_tool_form.png")
    s.go_back()
    s.wait(400)

    # ── 3. Resources list ─────────────────────────────────────────────────────
    s.go_to_action("xf_mcp.action_mcp_resource")
    if s.stopped:
        return
    s.wait(800)
    _save(s, "screenshot_03_resources_list.png")

    # ── 4. Global Prompts list ────────────────────────────────────────────────
    s.go_to_action("xf_mcp.action_mcp_prompt_global")
    if s.stopped:
        return
    s.wait(800)
    _save(s, "screenshot_04_prompts_list.png")

    # ── 5. Prompt form (first record, or New if empty) ────────────────────────
    # Try to open first record; if empty list, create one
    try:
        s.open_nth_record(0)
        s.wait(600)
        _save(s, "screenshot_05_prompt_form.png")
        s.go_back()
    except Exception:
        s.click_new()
        s.wait(400)
        s.fill_char("name", "odoo-assistant")
        s.fill_char("title", "Odoo Assistant")
        s.fill_text("description", "General assistant for Odoo ERP operations.")
        s.fill_text("message_template", "You are an Odoo ERP assistant. Help the user with: {task}")
        s.wait(400)
        _save(s, "screenshot_05_prompt_form.png")
        s.click_discard()
    s.wait(300)

    # ── 6. Access Control (Model Access list/form) ────────────────────────────
    s.go_to_action("xf_mcp.action_mcp_access")
    if s.stopped:
        return
    s.wait(800)
    # If list is empty, open New form to show the permission toggles
    results_before = len(s.results)
    s.open_nth_record(0)
    opened = len(s.results) > results_before and s.results[-1].get("passed", False)
    if not opened:
        s.click_new()
        s.wait(400)
        s.fill_many2one("model_id", "res.partner")
        s.wait(500)
    _save(s, "screenshot_06_access_control.png")
    s.click_discard()
    s.wait(300)

    # ── 7. Audit Logs list ────────────────────────────────────────────────────
    s.go_to_action("xf_mcp.action_mcp_audit_log")
    if s.stopped:
        return
    s.wait(800)
    _save(s, "screenshot_07_audit_log.png")

    # ── 8. Settings — MCP section ─────────────────────────────────────────────
    # Use ?debug=1 to force legacy hash routing instead of /odoo/settings (which 404s)
    try:
        s.page.goto(
            f"{s.base_url}/web?debug=1#action=base_setup.action_general_configuration",
            wait_until="domcontentloaded",
            timeout=15_000,
        )
        s.page.wait_for_selector(
            ".o_settings_container, .o_res_config_settings_view, "
            ".o_setting_left_pane, div[data-key='xf_mcp'], "
            ".o_settings_header",
            timeout=15_000,
        )
        s.wait(1500)
        # Click "MCP Server" tab in the settings left sidebar
        try:
            mcp_tab = s.page.locator("div.tab[data-key='xf_mcp'], .settings_tab [data-key='xf_mcp']").first
            mcp_tab.click(timeout=3000)
            s.wait(800)
        except Exception:
            pass
    except Exception:
        s.wait(2000)
    _save(s, "screenshot_08_settings.png")
