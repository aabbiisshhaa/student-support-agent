import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.tools import registry
from src.tools.ticket_tool import TicketCategory, TicketPriority, get_ticket

TICKET_ID_PATTERN = re.compile(r"^TCK-\d{6}$")


class IsolatedDatabaseTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.workspace = tempfile.TemporaryDirectory()
        self.addCleanup(self.workspace.cleanup)

        database_url = "sqlite:///" + (Path(self.workspace.name) / "tickets.db").as_posix()
        environment = patch.dict(os.environ, {"DATABASE_URL": database_url})
        environment.start()
        self.addCleanup(environment.stop)

    def ticket_params(self, **overrides) -> dict:
        params = {
            "student_id": "2300712345",
            "summary": "Cannot open the student portal",
            "original_message": "I cannot open the student portal since Monday.",
            "category": "administrative",
            "priority": "medium",
            "student_confirmed": True,
        }
        params.update(overrides)
        return params


class TestExecutionWhitelist(unittest.TestCase):
    def test_only_the_two_approved_tools_are_registered(self) -> None:
        self.assertEqual(registry.list_tools(), ("create_support_ticket", "get_course_schedule"))

    def test_registered_tool_names_report_as_registered(self) -> None:
        self.assertTrue(registry.is_registered("get_course_schedule"))
        self.assertTrue(registry.is_registered("create_support_ticket"))

    def test_an_unlisted_tool_name_is_rejected_before_anything_runs(self) -> None:
        with self.assertRaises(registry.UnknownToolError):
            registry.execute("delete_all_tickets", {})

    def test_a_hallucinated_tool_name_never_reaches_any_function(self) -> None:
        with self.assertRaises(registry.UnknownToolError):
            registry.execute("os.system", {"command": "rm -rf /"})

    def test_registering_the_same_name_twice_is_rejected(self) -> None:
        with self.assertRaises(registry.ToolRegistryError):
            registry.register(registry.tool_spec("get_course_schedule"))


class TestParameterSchemaBoundary(IsolatedDatabaseTestCase):
    def test_an_unexpected_parameter_is_rejected(self) -> None:
        with self.assertRaises(registry.ToolParameterError):
            registry.execute(
                "get_course_schedule",
                {"student_id": "2300712345", "admin_override": True},
            )

    def test_a_missing_required_parameter_is_rejected(self) -> None:
        with self.assertRaises(registry.ToolParameterError):
            registry.execute("get_course_schedule", {})

    def test_wrong_typed_parameter_is_rejected_before_the_tool_runs(self) -> None:
        with self.assertRaises(registry.ToolParameterError):
            registry.execute("get_course_schedule", {"student_id": 2300712345})

    def test_a_none_value_for_a_required_parameter_is_rejected(self) -> None:
        with self.assertRaises(registry.ToolParameterError):
            registry.execute("get_course_schedule", {"student_id": None})

    def test_an_optional_parameter_may_be_omitted(self) -> None:
        result = registry.execute("get_course_schedule", {"student_id": "2300712345"})

        self.assertTrue(result)

    def test_an_optional_parameter_may_be_explicitly_none(self) -> None:
        result = registry.execute(
            "get_course_schedule", {"student_id": "2300712345", "course_code": None}
        )

        self.assertTrue(result)

    def test_ticket_parameters_outside_the_schema_are_rejected(self) -> None:
        with self.assertRaises(registry.ToolParameterError):
            registry.execute(
                "create_support_ticket",
                self.ticket_params(bypass_validation=True),
            )


class TestMutationGuard(IsolatedDatabaseTestCase):
    def test_write_tool_is_blocked_when_student_confirmed_is_false(self) -> None:
        with self.assertRaises(registry.ToolMutationGuardError):
            registry.execute(
                "create_support_ticket",
                self.ticket_params(student_confirmed=False),
            )

        self.assertIsNone(get_ticket("TCK-000001"))

    def test_write_tool_runs_once_student_confirmed_is_true(self) -> None:
        ticket = registry.execute("create_support_ticket", self.ticket_params())

        self.assertRegex(ticket["ticket_id"], TICKET_ID_PATTERN)
        self.assertEqual(get_ticket(ticket["ticket_id"]), ticket)

    def test_read_only_tool_has_no_confirmation_requirement(self) -> None:
        spec = registry.tool_spec("get_course_schedule")

        self.assertFalse(spec.mutates_database)
        self.assertIsNone(spec.confirmation_param)

    def test_write_tool_is_marked_as_mutating_with_a_confirmation_gate(self) -> None:
        spec = registry.tool_spec("create_support_ticket")

        self.assertTrue(spec.mutates_database)
        self.assertEqual(spec.confirmation_param, "student_confirmed")


class TestRegistryToolWiring(IsolatedDatabaseTestCase):
    def test_get_course_schedule_round_trips_through_the_registry(self) -> None:
        result = registry.execute(
            "get_course_schedule", {"student_id": "2300712345", "course_code": "BSE4104"}
        )

        self.assertEqual({entry["course_code"] for entry in result}, {"BSE4104"})

    def test_create_support_ticket_accepts_enum_members(self) -> None:
        ticket = registry.execute(
            "create_support_ticket",
            self.ticket_params(category=TicketCategory.POLICY, priority=TicketPriority.HIGH),
        )

        self.assertEqual(ticket["category"], "policy")
        self.assertEqual(ticket["priority"], "high")

    def test_invalid_student_id_still_surfaces_the_tool_s_own_error(self) -> None:
        with self.assertRaises(Exception) as caught:
            registry.execute("get_course_schedule", {"student_id": "!!"})

        self.assertIn("Invalid student_id", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
