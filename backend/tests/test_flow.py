"""真实 HTTP 跨模块闭环：导入、确认、修正、规则、报表、导出。"""
from __future__ import annotations

import tempfile
import unittest
import uuid
from dataclasses import replace
from pathlib import Path

from fastapi.testclient import TestClient

from app import models
from app.config import load_settings
from app.db import Base
from app.main import create_app
from app.security import hash_password


class LedgerFlowTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        settings = replace(load_settings(), database_url=f"sqlite+pysqlite:///{Path(self.tmp.name, 'flow.db').as_posix()}",
                           intelligence_provider="fallback-rules")
        self.app = create_app(settings)
        Base.metadata.create_all(self.app.state.engine)
        with self.app.state.session_factory() as db:
            db.add(models.User(id=str(uuid.uuid4()), username="flow", password_hash=hash_password("test-pass")))
            db.commit()
        self.client = TestClient(self.app)
        result = self.client.post("/api/auth/login", json={"username":"flow","password":"test-pass"})
        self.assertEqual(result.status_code, 200)
        self.headers = {"X-CSRF-Token":result.json()["csrf_token"]}

    def tearDown(self):
        self.client.close()
        self.app.state.engine.dispose()
        self.tmp.cleanup()

    def test_file_to_report_and_export(self):
        file = Path(__file__).parents[2] / "fixtures/real_format_samples/wechat_export_sample.csv"
        response = self.client.post("/api/imports", data={"source":"wechat","ingestion_method":"file"},
            files={"file":("wechat_export_sample.csv",file.read_bytes(),"text/csv")}, headers=self.headers)
        self.assertEqual(response.status_code, 202, response.text)
        batch = response.json()
        self.assertEqual(batch["status"], "pending_review")
        self.assertTrue(batch["rows"])
        draft = next(x for x in batch["rows"] if x["amount_fen"] and x["occurred_at"] and x["flow_type"])
        tx = {key:draft[key] for key in ("source_transaction_id","occurred_at","amount_fen","currency","flow_type","merchant","description","category")}
        body = {"request_id":str(uuid.uuid4()),"expected_version":batch["version"],
                "rows":[{"row_id":draft["row_id"],"transaction":tx,"allow_suspected_duplicate":True}]}
        path = f"/api/imports/{batch['id']}/confirm"
        confirmed = self.client.post(path, json=body, headers=self.headers)
        self.assertEqual(confirmed.status_code, 200, confirmed.text)
        replay = self.client.post(path, json=body, headers=self.headers)
        self.assertEqual(replay.json(), confirmed.json())
        self.assertEqual(confirmed.json()["created_count"], 1)
        result = self.client.get("/api/transactions")
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()["total"], 1)
        item = result.json()["items"][0]
        with self.app.state.session_factory() as db:
            stored = db.get(models.Transaction, item["id"])
            self.assertNotIn(item["merchant"], stored.encrypted_payload)
            batch_record = db.get(models.ImportBatch, batch["id"])
            self.assertNotIn("wechat_export_sample.csv", batch_record.encrypted_filename)
        patched = self.client.patch(f"/api/transactions/{item['id']}",
            json={"expected_version":item["version"],"changes":{"category":"shopping"},"remember_rule":True},
            headers=self.headers)
        self.assertEqual(patched.status_code, 200, patched.text)
        self.assertEqual(len(self.client.get("/api/classification-rules").json()["items"]), 1)
        second = self.client.post("/api/imports", data={"source":"wechat","ingestion_method":"file"},
            files={"file":("wechat_export_sample.csv",file.read_bytes(),"text/csv")}, headers=self.headers)
        self.assertEqual(second.status_code, 202, second.text)
        matches = [x for x in second.json()["rows"] if x["merchant"] == item["merchant"]]
        self.assertTrue(matches)
        self.assertEqual(matches[0]["classification_source"], "user_rule")
        self.assertEqual(matches[0]["category"], "shopping")
        month = tx["occurred_at"][:7]
        budget = self.client.put("/api/budgets", json={"month":month,
            "category":"shopping", "amount_fen":100}, headers=self.headers)
        self.assertEqual(budget.status_code, 200, budget.text)
        report = self.client.get("/api/reports/monthly",params={"month":month})
        self.assertEqual(report.status_code, 200, report.text)
        self.assertGreaterEqual(report.json()["totals"]["gross_expense_fen"], 0)
        self.assertEqual(next(x for x in report.json()["budgets"] if x["category"] == "shopping")["budget_fen"],100)
        filtered = self.client.get("/api/transactions",params={"category":"shopping"})
        self.assertEqual(filtered.json()["total"],1)
        csv = self.client.get("/api/exports/transactions.csv",params={"category":"shopping"})
        self.assertEqual(csv.status_code, 200, csv.text)
        self.assertIn("交易时间", csv.text)
        pdf = self.client.get("/api/exports/monthly.pdf", params={"month":month})
        self.assertEqual(pdf.status_code, 200, pdf.text[:200] if pdf.status_code != 200 else "")
        self.assertTrue(pdf.content.startswith(b"%PDF"))

    def test_user_cannot_read_another_batch(self):
        file = Path(__file__).parents[2] / "fixtures/real_format_samples/wechat_export_sample.csv"
        batch = self.client.post("/api/imports", data={"source":"wechat","ingestion_method":"file"},
            files={"file":("wechat_export_sample.csv",file.read_bytes(),"text/csv")}, headers=self.headers).json()
        with self.app.state.session_factory() as db:
            db.add(models.User(id=str(uuid.uuid4()), username="other", password_hash=hash_password("test-pass")))
            db.commit()
        other = TestClient(self.app)
        other.post("/api/auth/login", json={"username":"other","password":"test-pass"})
        self.assertEqual(other.get(f"/api/imports/{batch['id']}").status_code, 404)
        self.assertEqual(other.get(f"/api/imports/{batch['id']}/original").status_code, 404)
        other.close()
