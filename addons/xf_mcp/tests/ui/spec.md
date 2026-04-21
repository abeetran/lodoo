# UI Test Spec — xf_mcp

## Module Overview

MCP Server for Odoo — native implementation of the Model Context Protocol server inside Odoo. Exposes tools, resources,
and prompts to AI assistants over Streamable HTTP transport. Provides admin configuration for tools, resources, model
access overrides, prompts, and monitoring via sessions/audit logs.

## Test Scenarios

### Scenario 1: Browse and Review MCP Tools (Configuration)

**Goal:** Verify the Tools list/form views load correctly with pre-loaded demo data.

**Preconditions:**

- Module installed with demo data
- Logged in as: admin (MCP Admin group)

**Steps:**

| #   | Action                                         | Expected Result                      |
| --- | ---------------------------------------------- | ------------------------------------ |
| 1   | Login as admin                                 | Home screen visible                  |
| 2   | Navigate to MCP Server > Configuration > Tools | List view shows pre-configured tools |
| 3   | Screenshot list view                           | —                                    |
| 4   | Open first tool record                         | Form opens with fields populated     |
| 5   | Screenshot form                                | —                                    |
| 6   | Go back to list                                | List view shown                      |
| 7   | Filter by category "CRUD"                      | Only CRUD tools shown                |
| 8   | Screenshot filtered list                       | —                                    |
| 9   | Clear search                                   | All tools visible again              |

**Field Data:** N/A (reads existing records)

---

### Scenario 2: Browse and Review MCP Resources

**Goal:** Verify the Resources list/form views load correctly with pre-loaded data.

**Preconditions:**

- Module installed with demo data
- Logged in as: admin

**Steps:**

| #   | Action                                             | Expected Result                          |
| --- | -------------------------------------------------- | ---------------------------------------- |
| 1   | Navigate to MCP Server > Configuration > Resources | List view shows pre-configured resources |
| 2   | Screenshot list view                               | —                                        |
| 3   | Open first resource record                         | Form opens with fields populated         |
| 4   | Screenshot form                                    | —                                        |
| 5   | Go back to list                                    | List view shown                          |

**Field Data:** N/A (reads existing records)

---

### Scenario 3: Browse and Review MCP Prompts

**Goal:** Verify the Global Prompts list/form and My Prompts views.

**Preconditions:**

- Module installed with demo data
- Logged in as: admin

**Steps:**

| #   | Action                                            | Expected Result            |
| --- | ------------------------------------------------- | -------------------------- |
| 1   | Navigate to MCP Server > Prompts > Global Prompts | List view loads            |
| 2   | Screenshot global prompts list                    | —                          |
| 3   | Click New to create a prompt                      | Empty form opens           |
| 4   | Fill name = "/test-prompt"                        | Field accepts value        |
| 5   | Fill title = "Test Prompt"                        | Field accepts value        |
| 6   | Fill description = "A test prompt for UI testing" | Field accepts value        |
| 7   | Fill message_template = "Hello {name}!"           | Field accepts value        |
| 8   | Add argument line: name = "name", required = True | Argument row added         |
| 9   | Screenshot filled form                            | —                          |
| 10  | Click Save                                        | Record saved, no errors    |
| 11  | Screenshot saved form                             | —                          |
| 12  | Navigate to MCP Server > Prompts > My Prompts     | My Prompts list view loads |
| 13  | Screenshot my prompts                             | —                          |

**Field Data:**

- `name`: "/test-prompt"
- `title`: "Test Prompt"
- `description`: "A test prompt for UI testing"
- `message_template`: "Hello {name}!"
- `argument`: name="name", required=True

---

### Scenario 4: Browse Model Access Overrides

**Goal:** Verify the Model Access list/form views.

**Preconditions:**

- Module installed
- Logged in as: admin

**Steps:**

| #   | Action                                                | Expected Result                |
| --- | ----------------------------------------------------- | ------------------------------ |
| 1   | Navigate to MCP Server > Configuration > Model Access | List view loads (may be empty) |
| 2   | Screenshot list view                                  | —                              |
| 3   | Click New                                             | Empty form opens               |
| 4   | Select model_id = "res.partner"                       | Model selected from dropdown   |
| 5   | Toggle permissions (read=True, write=False)           | Checkboxes update              |
| 6   | Screenshot form                                       | —                              |
| 7   | Click Save                                            | Record saved, no errors        |
| 8   | Screenshot saved form                                 | —                              |

**Field Data:**

- `model_id`: "res.partner"
- `read_access`: True
- `write_access`: False
- `create_access`: True
- `delete_access`: False

---

### Scenario 5: Browse Monitoring — Sessions and Audit Logs

**Goal:** Verify Sessions and Audit Logs views load correctly.

**Preconditions:**

- Module installed
- Logged in as: admin

**Steps:**

| #   | Action                                           | Expected Result            |
| --- | ------------------------------------------------ | -------------------------- |
| 1   | Navigate to MCP Server > Monitoring > Sessions   | Sessions list view loads   |
| 2   | Screenshot sessions list                         | —                          |
| 3   | Navigate to MCP Server > Monitoring > Audit Logs | Audit logs list view loads |
| 4   | Screenshot audit logs list                       | —                          |
| 5   | Switch to graph view                             | Graph view loads           |
| 6   | Screenshot graph view                            | —                          |

**Field Data:** N/A (reads existing records)

---

### Scenario 6: Settings — MCP Configuration

**Goal:** Verify MCP settings page loads and fields are editable.

**Preconditions:**

- Module installed
- Logged in as: admin

**Steps:**

| #   | Action                                              | Expected Result                     |
| --- | --------------------------------------------------- | ----------------------------------- |
| 1   | Navigate to Settings > MCP Server settings          | Settings form loads with MCP fields |
| 2   | Screenshot settings                                 | —                                   |
| 3   | Toggle MCP Server enabled                           | Checkbox toggles                    |
| 4   | Verify default values visible (rate limit=60, etc.) | Fields show defaults                |
| 5   | Click Save                                          | Settings saved                      |

**Field Data:** N/A (reads existing configuration)
