import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import main


class ExpenseTrackerToolsTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.temp_dir.name) / "test-expenses.db")
        self.db_path_patcher = patch.object(main, "DB_PATH", self.db_path)
        self.db_path_patcher.start()
        main.init_db()

    def tearDown(self):
        self.db_path_patcher.stop()
        self.temp_dir.cleanup()

    def test_expense_crud_and_monthly_budget_status(self):
        async def exercise_tools():
            expense = await main.add_expense(
                "2026-02-28",
                25.5,
                "food",
                subcategory="groceries",
                note="weekly shop",
            )
            expense_id = expense["id"]
            await main.add_expense("2026-03-01", 100, "food")

            updated = await main.update_expense(
                expense_id,
                amount=30,
                note="updated",
            )
            self.assertEqual(updated["status"], "success")
            self.assertEqual(updated["expense"]["amount"], 30)

            await main.set_budget("2026-02", "food", 50)
            status = await main.budget_status("2026-02")
            self.assertEqual(status[0]["spent_amount"], 30)
            self.assertEqual(status[0]["remaining_amount"], 20)
            self.assertEqual(status[0]["percent_used"], 60)

            summary = await main.monthly_summary("2026-02")
            self.assertEqual(len(summary), 1)
            self.assertEqual(summary[0]["total_amount"], 30)
            self.assertEqual((await main.delete_expense(expense_id))["status"], "success")
            self.assertIsNone(await main.get_expense(expense_id))

        asyncio.run(exercise_tools())

    def test_rejects_invalid_values_and_date_ranges(self):
        async def exercise_tools():
            with self.assertRaises(ValueError):
                await main.add_expense("2026-02-30", 20, "food")
            with self.assertRaises(ValueError):
                await main.add_expense("2026-02-28", float("inf"), "food")
            with self.assertRaises(ValueError):
                await main.list_expenses("2026-03-01", "2026-02-01")

        asyncio.run(exercise_tools())


if __name__ == "__main__":
    unittest.main()
