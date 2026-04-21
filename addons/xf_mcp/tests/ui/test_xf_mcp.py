# pylint: disable=broad-exception-caught,too-many-return-statements,too-many-statements
"""test_xf_mcp.py — UI test scenario for xf_mcp module

Run:
  bash .claude/skills/odoo-ui-tests/scripts/run_ui_tests.sh \
       --script xf_mcp/tests/ui/test_xf_mcp.py \
       --url http://localhost:17001 --db ehs
"""


def run(s):
    # ---------------------------------------------------------------
    # Scenario 1: Browse and Review MCP Tools (Configuration)
    # ---------------------------------------------------------------
    if not s.login(db="ehs"):
        return

    s.go_to_action("xf_mcp.action_mcp_tool")
    if s.stopped:
        return
    s.screenshot("01_tools_list")

    # Open first tool record
    s.open_nth_record(0)
    s.screenshot("02_tool_form")
    s.go_back()

    # Filter by category CRUD
    s.filter_by("CRUD")
    s.screenshot("03_tools_filtered_crud")
    s.clear_search()

    # ---------------------------------------------------------------
    # Scenario 2: Browse and Review MCP Resources
    # ---------------------------------------------------------------
    s.go_to_action("xf_mcp.action_mcp_resource")
    if s.stopped:
        return
    s.screenshot("04_resources_list")

    s.open_nth_record(0)
    s.screenshot("05_resource_form")
    s.go_back()

    # ---------------------------------------------------------------
    # Scenario 3: Browse and Review MCP Prompts
    # ---------------------------------------------------------------
    s.go_to_action("xf_mcp.action_mcp_prompt_global")
    if s.stopped:
        return
    s.screenshot("06_global_prompts_list")

    # Create a new global prompt
    s.click_new()
    s.fill_char("name", "/test-prompt")
    s.fill_char("title", "Test Prompt")
    s.fill_text("description", "A test prompt for UI testing")
    s.fill_text("message_template", "Hello {name}!")
    s.screenshot("07_prompt_form_filled")

    # Add argument line
    s.o2m_add_line("argument_ids")
    s.o2m_cell_fill_char("argument_ids", "name", "name")
    s.screenshot("08_prompt_with_argument")

    s.click_save()
    s.screenshot("09_prompt_saved")

    # My Prompts
    s.go_to_action("xf_mcp.action_mcp_prompt_my")
    if s.stopped:
        return
    s.screenshot("10_my_prompts_list")

    # ---------------------------------------------------------------
    # Scenario 4: Browse Model Access Overrides
    # ---------------------------------------------------------------
    s.go_to_action("xf_mcp.action_mcp_access")
    if s.stopped:
        return
    s.screenshot("11_access_list")

    s.click_new()
    s.fill_many2one("model_id", "res.partner")
    s.set_checkbox("read_access", True)
    s.set_checkbox("write_access", False)
    s.set_checkbox("create_access", True)
    s.set_checkbox("delete_access", False)
    s.screenshot("12_access_form_filled")
    s.click_save()
    s.screenshot("13_access_saved")

    # ---------------------------------------------------------------
    # Scenario 5: Monitoring — Sessions and Audit Logs
    # ---------------------------------------------------------------
    s.go_to_action("xf_mcp.action_mcp_session")
    if s.stopped:
        return
    s.screenshot("14_sessions_list")

    s.go_to_action("xf_mcp.action_mcp_audit_log")
    if s.stopped:
        return
    s.screenshot("15_audit_logs_list")

    s.switch_view("graph")
    s.screenshot("16_audit_logs_graph")

    # ---------------------------------------------------------------
    # Scenario 6: Settings — MCP Configuration
    # ---------------------------------------------------------------
    # Navigate to Odoo settings page via direct URL (settings uses a
    # non-standard view controller that go_to_action cannot detect).
    step = "Navigate → Settings"
    s._announce(step)
    try:
        s.page.goto(
            f"{s.base_url}/web#action=base.res_config_setting_act_window",
            wait_until="domcontentloaded",
            timeout=15_000,
        )
        s.page.wait_for_load_state("domcontentloaded")
        s.page.wait_for_timeout(2_000)
        s._ok(step, s._shot("settings_page"))
    except Exception as exc:
        s._fail(step, s._shot("settings_err"), str(exc))
    s.screenshot("17_settings")
