import os
import unittest
from pathlib import Path
from unittest.mock import patch

import main
from fastapi import HTTPException


class BackendUnitTests(unittest.TestCase):
    def test_addresses_are_validated_before_chain_reads(self):
        with self.assertRaises(HTTPException) as error:
            main.addr("not-an-address")
        self.assertEqual(error.exception.status_code, 400)

    def test_duplicate_events_are_ignored_and_checkpoint_persists(self):
        test_db = Path(main.ROOT) / "test_events.db"
        if test_db.exists():
            test_db.unlink()
        try:
            with patch.object(main, "DB", test_db):
                conn = main.db()
                row = ("0xtx", 0, 12068071, "TokensPurchased", "{}", 1700000000)
                self.assertEqual(conn.execute("INSERT OR IGNORE INTO events VALUES(?,?,?,?,?,?)", row).rowcount, 1)
                self.assertEqual(conn.execute("INSERT OR IGNORE INTO events VALUES(?,?,?,?,?,?)", row).rowcount, 0)
                conn.execute("INSERT OR REPLACE INTO checkpoint VALUES(1, ?)", (12068071,))
                conn.commit()
                conn.close()
                reopened = main.db()
                self.assertEqual(reopened.execute("SELECT COUNT(*) FROM events").fetchone()[0], 1)
                self.assertEqual(reopened.execute("SELECT last_block FROM checkpoint WHERE id=1").fetchone()[0], 12068071)
                reopened.close()
        finally:
            if test_db.exists():
                os.unlink(test_db)

    def test_demo_role_prioritizes_owner_and_accepts_verified_zero_balance(self):
        class Call:
            def __init__(self, value):
                self.value = value

            def call(self):
                return self.value

        class Function:
            def __init__(self, value):
                self.value = value

            def __call__(self, *args):
                return Call(self.value)

        class Contract:
            functions = type("Functions", (), {
                "owner": Function("0x0000000000000000000000000000000000000001"),
                "adminA": Function("0x0000000000000000000000000000000000000002"),
                "adminB": Function("0x0000000000000000000000000000000000000003"),
                "isVerified": Function(True),
                "balanceOf": Function(0),
                "approvalCount": Function(2),
            })()

        with patch.object(main, "require_chain", return_value=Contract()):
            owner = main.demo_role("0x0000000000000000000000000000000000000001")
            investor = main.demo_role("0x0000000000000000000000000000000000000004")
        self.assertEqual(owner["role"], "owner")
        self.assertEqual(investor["role"], "investor")

    def test_events_refreshes_index_before_returning_rows(self):
        test_db = Path(main.ROOT) / "test_events_refresh.db"
        if test_db.exists():
            test_db.unlink()
        try:
            with patch.object(main, "DB", test_db), patch.object(main, "sync_events_once", return_value=[]) as sync:
                self.assertEqual(main.events(limit=10), [])
                sync.assert_called_once_with()
        finally:
            if test_db.exists():
                os.unlink(test_db)


if __name__ == "__main__":
    unittest.main()
