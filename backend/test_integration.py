import os
import sys
import json
import unittest

# Ensure UTF-8 output on Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

# Add backend directory to sys.path
backend_dir = os.path.dirname(os.path.abspath(__file__))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from App.upi_settlement_engine import (
    init_db,
    get_transaction_analytics,
    get_settlement_summary,
    get_reconciliation_report,
    get_merchant_kpi_summary,
    initiate_upi_payment,
    process_razorpay_webhook,
    process_settlement_webhook,
    generate_settlement_analytics_chart,
    Transaction,
    SettlementBatch,
    SettlementReconciliation,
    SessionLocal
)
from App.financial_agent import (
    initialize_agent,
    analyze_upi_settlements_and_transactions,
    check_merchant_settlement_batches,
    simulate_or_record_upi_transaction,
    analyze_spending_patterns,
    get_budget_recommendations,
    calculate_compound_interest
)
from fastapi.testclient import TestClient
from api import app

class TestFullProjectIntegration(unittest.TestCase):
    
    @classmethod
    def setUpClass(cls):
        print("\n" + "="*70)
        print(">> STARTING FULL SYSTEM INTEGRATION TEST SUITE")
        print("="*70)
        init_db()
        cls.client = TestClient(app)
        try:
            cls.agent = initialize_agent()
        except Exception as e:
            print(f"[Warning] Agent initialization: {e}")
            cls.agent = None


    # --- 1. Database & Settlement Engine Tests ---
    def test_01_db_and_seed_data(self):
        print("\n[Test 1] Verifying Database Models & Seed Data...")
        session = SessionLocal()
        try:
            txn_count = session.query(Transaction).count()
            batch_count = session.query(SettlementBatch).count()
            rec_count = session.query(SettlementReconciliation).count()
            
            self.assertGreater(txn_count, 0, "Transactions table should have seeded rows")
            self.assertGreater(batch_count, 0, "Settlement batches should have seeded rows")
            self.assertGreater(rec_count, 0, "Reconciliation records should exist")
            print(f"  [OK] Database Tables Populated: {txn_count} Txns, {batch_count} Batches, {rec_count} Reconciliations")
        finally:
            session.close()


    def test_02_merchant_kpis_and_queries(self):
        print("\n[Test 2] Testing Merchant KPI Aggregations & Query Filters...")
        kpis = get_merchant_kpi_summary("MERCHANT_001")
        self.assertIn("total_transactions", kpis)
        self.assertIn("total_gross_volume", kpis)
        self.assertIn("total_net_settled", kpis)
        self.assertGreater(kpis["total_transactions"], 0)
        self.assertGreater(kpis["total_gross_volume"], 0)
        
        all_txns = get_transaction_analytics("MERCHANT_001", status="all")
        success_txns = get_transaction_analytics("MERCHANT_001", status="success")
        self.assertGreaterEqual(len(all_txns), len(success_txns))
        
        batches = get_settlement_summary("MERCHANT_001")
        self.assertGreater(len(batches), 0)
        
        recs = get_reconciliation_report("MERCHANT_001")
        self.assertGreater(len(recs), 0)
        print(f"  [OK] KPIs Calculated: Gross = INR {kpis['total_gross_volume']:,.2f}, Net Settled = INR {kpis['total_net_settled']:,.2f}, Success Rate = {kpis['success_rate']}%")

    def test_03_payment_initiation_and_fee_math(self):
        print("\n[Test 3] Testing Dynamic UPI Payment Initiation & Fee Formulas...")
        amount = 5000.0
        txn = initiate_upi_payment(
            merchant_id="MERCHANT_001",
            amount=amount,
            customer_id="cust_integration_test",
            upi_id="tester@okhdfcbank",
            payment_app="google_pay",
            psp_provider="razorpay"
        )
        self.assertIsNotNone(txn["id"])
        self.assertTrue(txn["psp_reference_id"].startswith("pay_raz_"))
        self.assertEqual(txn["amount"], 5000.0)
        self.assertAlmostEqual(txn["psp_fee"], 47.0, places=1)
        self.assertAlmostEqual(txn["gst_fee"], 8.46, places=1)
        self.assertAlmostEqual(txn["net_amount_to_merchant"], 4944.54, places=1)
        print(f"  [OK] Payment Initiated: ID={txn['psp_reference_id']} | Gross=INR {txn['amount']} -> Net=INR {txn['net_amount_to_merchant']} (Fee+GST=INR {txn['psp_fee'] + txn['gst_fee']})")

    def test_04_webhook_lifecycle_handling(self):
        print("\n[Test 4] Testing Webhook Ingestion & Idempotent Transitions...")
        test_ref = "pay_raz_webhook_test_001"
        
        # 1. Webhook: payment.authorized
        auth_payload = {
            "event": "payment.authorized",
            "notes": {"merchant_id": "MERCHANT_001", "customer_id": "cust_test_wh"},
            "payment": {
                "entity": {
                    "id": test_ref,
                    "amount": 250000,
                    "fee": 2450,
                    "tax": 441,
                    "vpa": "payer@okhdfcbank",
                    "created_at": 1723800000
                }
            }
        }
        res_auth = process_razorpay_webhook("payment.authorized", auth_payload)
        self.assertEqual(res_auth["status"], "success")

        # 2. Webhook: payment.captured
        cap_payload = {
            "event": "payment.captured",
            "payment": {
                "entity": {
                    "id": test_ref,
                    "amount": 250000,
                    "fee": 2450,
                    "tax": 441,
                    "vpa": "payer@okhdfcbank"
                }
            }
        }
        res_cap = process_razorpay_webhook("payment.captured", cap_payload)
        self.assertEqual(res_cap["status"], "success")

        # 3. Webhook: settlement.processed
        settle_payload = {
            "event": "settlement.processed",
            "settlement": {
                "entity": {
                    "recipient_settlement_id": "MERCHANT_001",
                    "amount": 250000,
                    "fees": 2891,
                    "utr": "UTRTEST9988220011"
                }
            },
            "items": [{"payment_id": test_ref}]
        }
        res_settle = process_settlement_webhook("settlement.processed", settle_payload)
        self.assertEqual(res_settle["status"], "success")
        self.assertEqual(res_settle["utr"], "UTRTEST9988220011")
        print(f"  [OK] Webhooks Processed: Authorized -> Captured -> Settlement Batch Created (UTR: {res_settle['utr']})")

    def test_05_chart_generation(self):
        print("\n[Test 5] Testing 7-Day Settlement Chart Rendering...")
        chart_path = generate_settlement_analytics_chart("MERCHANT_001")
        self.assertIsNotNone(chart_path)
        self.assertTrue(os.path.exists(chart_path))
        self.assertGreater(os.path.getsize(chart_path), 1000)
        print(f"  [OK] Chart Rendered Successfully: {chart_path} ({os.path.getsize(chart_path)} bytes)")

    # --- 2. AI Agent & Tooling Tests ---
    def test_06_agent_tools(self):
        print("\n[Test 6] Testing AI Agent Financial & Settlement Tools...")
        
        # Test UPI Analytics Tool
        tool_upi_res = analyze_upi_settlements_and_transactions.invoke({"merchant_id": "MERCHANT_001"})
        self.assertIn("UPI TRANSACTION & SETTLEMENT SUMMARY", tool_upi_res)
        self.assertIn("Gross Transaction Volume", tool_upi_res)
        
        # Test Settlement Batches Tool
        tool_batch_res = check_merchant_settlement_batches.invoke({"merchant_id": "MERCHANT_001"})
        self.assertIn("BANK SETTLEMENT BATCHES", tool_batch_res)
        
        # Test Simulate UPI Transaction Tool
        tool_sim_res = simulate_or_record_upi_transaction.invoke({
            "merchant_id": "MERCHANT_001",
            "amount": 1200.0,
            "upi_id": "agent_test@ybl",
            "payment_app": "phonepe",
            "psp_provider": "billdesk"
        })
        self.assertIn("Transaction Initiated Successfully", tool_sim_res)
        
        # Test Spending Analyzer Tool
        expenses_data = json.dumps([
            {"category": "Dining Out", "amount": 1500},
            {"category": "Groceries", "amount": 4200},
            {"category": "Rent", "amount": 18000}
        ])
        spending_res = analyze_spending_patterns.invoke({"expenses_json": expenses_data})
        self.assertIn("Total Spent", spending_res)
        
        # Test Compound Interest Tool
        compound_res = calculate_compound_interest.invoke({"principal": 100000, "rate": 12, "time": 5})
        self.assertIn("future value", compound_res.lower())
        
        print("  [OK] All AI Agent Tools Executed Successfully with Valid Outputs")

    # --- 3. FastAPI REST Endpoints Tests ---
    def test_07_fastapi_endpoints(self):
        print("\n[Test 7] Testing All FastAPI REST Endpoints...")
        
        # 1. Transactions
        r = self.client.get("/api/analytics/transactions?merchant=MERCHANT_001&status=all")
        self.assertEqual(r.status_code, 200)
        self.assertIsInstance(r.json(), list)
        
        # 2. Settlement Summary
        r = self.client.get("/api/settlements/summary?merchant=MERCHANT_001")
        self.assertEqual(r.status_code, 200)
        self.assertIsInstance(r.json(), list)
        
        # 3. Reconciliation
        r = self.client.get("/api/settlements/reconciliation?merchant=MERCHANT_001")
        self.assertEqual(r.status_code, 200)
        self.assertIsInstance(r.json(), list)
        
        # 4. KPIs
        r = self.client.get("/api/upi/kpis?merchant=MERCHANT_001")
        self.assertEqual(r.status_code, 200)
        self.assertIn("total_gross_volume", r.json())
        
        # 5. Initiate Payment Endpoint
        r = self.client.post("/api/upi/initiate", json={
            "merchant_id": "MERCHANT_001",
            "amount": 3500.0,
            "customer_id": "cust_api_test",
            "upi_id": "user@paytm",
            "payment_app": "paytm",
            "psp_provider": "payu"
        })
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["amount"], 3500.0)
        
        # 6. Webhooks Endpoints
        r_wh1 = self.client.post("/webhooks/razorpay", json={
            "event": "payment.captured",
            "payment": {
                "entity": {
                    "id": "pay_api_test_001",
                    "amount": 100000,
                    "fee": 900,
                    "tax": 162
                }
            }
        })
        self.assertEqual(r_wh1.status_code, 200)
        
        r_wh2 = self.client.post("/webhooks/razorpay-settlement", json={
            "event": "settlement.processed",
            "settlement": {
                "entity": {
                    "recipient_settlement_id": "MERCHANT_001",
                    "amount": 100000,
                    "fees": 1062,
                    "utr": "UTRAPI998811"
                }
            }
        })
        self.assertEqual(r_wh2.status_code, 200)
        
        print("  [OK] All 7 FastAPI Endpoints Responded with HTTP 200 OK")

    # --- 4. Frontend & Static Assets Integrity ---
    def test_08_frontend_and_assets(self):
        print("\n[Test 8] Testing Frontend Files & Assets Integrity...")
        frontend_index = os.path.join(os.path.dirname(backend_dir), "frontend", "index.html")
        frontend_css = os.path.join(os.path.dirname(backend_dir), "frontend", "styles.css")
        
        self.assertTrue(os.path.exists(frontend_index), "index.html should exist")
        self.assertTrue(os.path.exists(frontend_css), "styles.css should exist")
        
        with open(frontend_index, "r", encoding="utf-8") as f:
            html_content = f.read()
            self.assertIn("upi-analytics", html_content)
            self.assertIn("kpi-volume", html_content)
            self.assertIn("settlement-batches-table", html_content)
            self.assertIn("/api/upi/initiate", html_content)

        with open(frontend_css, "r", encoding="utf-8") as f:
            css_content = f.read()
            self.assertIn(".upi-section", css_content)
            self.assertIn(".kpi-grid", css_content)
            
        print("  [OK] Frontend Assets, DOM Hooks & CSS Classes Verified")

if __name__ == "__main__":
    runner = unittest.TextTestRunner(verbosity=2)
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestFullProjectIntegration)
    res = runner.run(suite)
    if res.wasSuccessful():
        print("\n" + "="*70)
        print(">> ALL INTEGRATION TESTS PASSED SUCCESSFULLY! (100% HEALTHY)")
        print("="*70)
        sys.exit(0)
    else:
        print("\n" + "="*70)
        print(">> SOME INTEGRATION TESTS FAILED")
        print("="*70)
        sys.exit(1)

