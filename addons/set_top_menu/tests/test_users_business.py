import xml.etree.ElementTree as ET

from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestUsersBusiness(TransactionCase):
    def _business_page(self):
        view = self.env.ref("set_top_menu.view_users_form_business")
        page = ET.fromstring(view.arch_db).find(".//page[@name='business']")
        self.assertIsNotNone(page)
        return page

    def _user(self, login, **extra):
        values = {
            "name": login,
            "login": login,
            "employee_code": "NV-%s" % login,
        }
        values.update(extra)
        return self.env["res.users"].create(values)

    def test_business_tab_structure(self):
        page = self._business_page()
        self.assertEqual(page.get("string"), "Nghiệp vụ")
        groups = {
            group.get("string"): group
            for group in page.findall("group")
        }
        self.assertEqual(
            set(groups),
            {
                "Vai trò nghiệp vụ",
                "Vận chuyển",
                "Sơ chế/Chế biến",
            },
        )
        roles = [
            field.get("name")
            for field in groups["Vai trò nghiệp vụ"].findall("field")
        ]
        self.assertEqual(
            roles,
            ["business_owner", "business_processor", "business_transporter"],
        )
        transport = groups["Vận chuyển"]
        self.assertEqual(
            transport.get("invisible"), "not business_transporter"
        )
        transport_fields = {
            field.get("name"): field
            for field in transport.findall("field")
        }
        self.assertEqual(
            set(transport_fields), {"transport_vehicle", "transport_plate"}
        )
        self.assertEqual(
            transport_fields["transport_plate"].get("required"),
            "business_transporter",
        )
        self.assertIsNone(
            transport_fields["transport_vehicle"].get("required")
        )
        processing = groups["Sơ chế/Chế biến"]
        self.assertEqual(
            processing.get("invisible"), "not business_processor"
        )
        frames = {
            group.get("string"): group
            for group in processing.findall("group")
        }
        self.assertEqual(
            set(frames),
            {
                "Giấy khám sức khỏe",
                "Giấy chứng nhận tập huấn kiến thức ATTP",
            },
        )
        health_fields = {
            field.get("name"): field
            for field in frames["Giấy khám sức khỏe"].findall("field")
        }
        for name in (
            "health_cert_number",
            "health_cert_date",
            "health_cert_expiry",
        ):
            self.assertEqual(
                health_fields[name].get("required"), "business_processor"
            )
        self.assertIsNone(health_fields["health_cert_place"].get("required"))
        training_fields = {
            field.get("name"): field
            for field in frames["Giấy chứng nhận tập huấn kiến thức ATTP"]
            .findall("field")
        }
        for name in ("food_safety_cert_number", "food_safety_issue_date"):
            self.assertEqual(
                training_fields[name].get("required"), "business_processor"
            )
        self.assertIsNone(
            training_fields["food_safety_issuer"].get("required")
        )

    def test_employee_info_on_main_form(self):
        view = self.env.ref("set_top_menu.view_users_form_employee_code")
        spec = ET.fromstring(view.arch_db)
        self.assertEqual(spec.get("position"), "after")
        self.assertIn("oe_title", spec.get("expr"))
        group = spec.find("group[@name='employee_info']")
        self.assertIsNotNone(group)
        self.assertEqual(group.get("string"), "Thông tin nhân viên")
        fields = {
            field.get("name"): field for field in group.findall("field")
        }
        self.assertEqual(
            list(fields),
            [
                "employee_code",
                "job_position",
                "birth_date",
                "identity_number",
                "contact_phone",
                "contact_address",
            ],
        )
        self.assertEqual(fields["employee_code"].get("required"), "1")

    def test_business_role_required(self):
        with self.assertRaises(ValidationError):
            self._user("nv_role_001")
        user = self._user("nv_role_002", business_owner=True)
        self.assertTrue(user.business_owner)
        with self.assertRaises(ValidationError):
            user.write({"business_owner": False})

    def test_employee_code_required(self):
        with self.assertRaises(ValidationError):
            self._user(
                "nv_code_001",
                business_owner=True,
                employee_code=False,
            )
        user = self._user("nv_code_002", business_owner=True)
        with self.assertRaises(ValidationError):
            user.write({"employee_code": False})
        auto = (
            self.env["res.users"]
            .with_context(set_top_menu_skip_user_checks=True)
            .create({"name": "NV SSO", "login": "nv_sso_001"})
        )
        self.assertFalse(auto.employee_code)

    def test_transporter_requires_plate(self):
        with self.assertRaises(ValidationError):
            self._user("nv_vc_001", business_transporter=True)
        user = self._user(
            "nv_vc_002",
            business_transporter=True,
            transport_vehicle="Xe tải lạnh",
            transport_plate="29H-123.45",
        )
        self.assertEqual(user.transport_plate, "29H-123.45")

    def test_processor_requires_certificates(self):
        with self.assertRaises(ValidationError):
            self._user("nv_cb_001", business_processor=True)
        with self.assertRaises(ValidationError):
            self._user(
                "nv_cb_002",
                business_processor=True,
                health_cert_number="SK-001",
                health_cert_place="BV X",
                health_cert_date="2026-01-10",
                health_cert_expiry="2027-01-10",
            )
        user = self._user(
            "nv_cb_003",
            business_processor=True,
            health_cert_number="SK-001",
            health_cert_place="BV X",
            health_cert_date="2026-01-10",
            health_cert_expiry="2027-01-10",
            food_safety_cert_number="ATTP-001",
            food_safety_issue_date="2026-02-01",
            food_safety_issuer="Chi cục ATVSTP",
        )
        self.assertEqual(user.food_safety_cert_number, "ATTP-001")

    def test_owner_and_multi_roles(self):
        owner = self._user("nv_cs_001", business_owner=True)
        self.assertTrue(owner.business_owner)
        multi = self._user(
            "nv_all_001",
            business_owner=True,
            business_processor=True,
            business_transporter=True,
            transport_plate="30A-999.99",
            health_cert_number="SK-002",
            health_cert_date="2026-01-10",
            health_cert_expiry="2027-01-10",
            food_safety_cert_number="ATTP-002",
            food_safety_issue_date="2026-02-01",
        )
        self.assertTrue(
            multi.business_owner
            and multi.business_processor
            and multi.business_transporter
        )
