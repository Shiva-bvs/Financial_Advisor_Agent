import os
import uuid
import datetime
import json
import pandas as pd
import matplotlib.pyplot as plt
from sqlalchemy import (
    create_engine, Column, String, Float, Integer, Boolean, DateTime, Date, ForeignKey, Text, func
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

Base = declarative_base()

# DB Path configuration
DB_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'Assets')
os.makedirs(DB_DIR, exist_ok=True)
DB_PATH = os.path.join(DB_DIR, 'upi_analytics.db')
ENGINE = create_engine(f"sqlite:///{DB_PATH}", echo=False, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=ENGINE)

# --- 1. Database Models ---

class Transaction(Base):
    __tablename__ = 'transactions'
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    merchant_id = Column(String(50), nullable=False, index=True)
    customer_id = Column(String(100), nullable=True)
    upi_id = Column(String(255), nullable=True)
    amount = Column(Float, nullable=False)
    currency = Column(String(3), default='INR')
    
    # Status tracking: initiated, pending, success, failed, refund
    status = Column(String(20), default='initiated', index=True)
    payment_app = Column(String(50), nullable=True) # google_pay, phonepe, paytm, whatsapp_pay, cred, bhim
    psp_provider = Column(String(50), nullable=True) # razorpay, billdesk, payu
    psp_reference_id = Column(String(100), unique=True, index=True)
    
    # Transaction flow timestamps
    initiated_at = Column(DateTime, default=datetime.datetime.utcnow)
    customer_authorized_at = Column(DateTime, nullable=True)
    cleared_by_npci_at = Column(DateTime, nullable=True)
    settled_at = Column(DateTime, nullable=True)
    
    # Financial breakdown
    gross_amount = Column(Float, nullable=True)
    psp_fee = Column(Float, default=0.0)
    payment_app_fee = Column(Float, default=0.0)
    gst_fee = Column(Float, default=0.0)
    net_amount_to_merchant = Column(Float, nullable=True)
    
    # Dispute & reversals
    is_disputed = Column(Boolean, default=False)
    dispute_raised_at = Column(DateTime, nullable=True)
    chargeback_amount = Column(Float, default=0.0)
    reversal_reason = Column(String(255), nullable=True)
    
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    reconciliations = relationship("SettlementReconciliation", back_populates="transaction")

    def to_dict(self):
        return {
            "id": self.id,
            "merchant_id": self.merchant_id,
            "customer_id": self.customer_id,
            "upi_id": self.upi_id,
            "amount": self.amount,
            "currency": self.currency,
            "status": self.status,
            "payment_app": self.payment_app,
            "psp_provider": self.psp_provider,
            "psp_reference_id": self.psp_reference_id,
            "initiated_at": self.initiated_at.isoformat() if self.initiated_at else None,
            "customer_authorized_at": self.customer_authorized_at.isoformat() if self.customer_authorized_at else None,
            "cleared_by_npci_at": self.cleared_by_npci_at.isoformat() if self.cleared_by_npci_at else None,
            "settled_at": self.settled_at.isoformat() if self.settled_at else None,
            "gross_amount": self.gross_amount,
            "psp_fee": self.psp_fee,
            "payment_app_fee": self.payment_app_fee,
            "gst_fee": self.gst_fee,
            "net_amount_to_merchant": self.net_amount_to_merchant,
            "is_disputed": self.is_disputed,
            "chargeback_amount": self.chargeback_amount,
            "reversal_reason": self.reversal_reason
        }


class SettlementBatch(Base):
    __tablename__ = 'settlement_batches'
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    merchant_id = Column(String(50), nullable=False, index=True)
    batch_date = Column(Date, nullable=False, index=True)
    psp_provider = Column(String(50), nullable=False)
    
    total_transactions = Column(Integer, default=0)
    total_gross = Column(Float, default=0.0)
    total_fees = Column(Float, default=0.0)
    total_net = Column(Float, default=0.0)
    
    # Settlement proof
    utr = Column(String(50), unique=True, index=True) # Unique Transaction Reference from bank
    bank_settlement_time = Column(DateTime, nullable=True)
    bank_balance_before = Column(Float, default=0.0)
    bank_balance_after = Column(Float, default=0.0)
    
    status = Column(String(20), default='pending') # pending, partially_settled, settled
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    reconciliations = relationship("SettlementReconciliation", back_populates="batch")

    def to_dict(self):
        return {
            "id": self.id,
            "merchant_id": self.merchant_id,
            "batch_date": self.batch_date.isoformat() if self.batch_date else None,
            "psp_provider": self.psp_provider,
            "total_transactions": self.total_transactions,
            "total_gross": self.total_gross,
            "total_fees": self.total_fees,
            "total_net": self.total_net,
            "utr": self.utr,
            "bank_settlement_time": self.bank_settlement_time.isoformat() if self.bank_settlement_time else None,
            "bank_balance_before": self.bank_balance_before,
            "bank_balance_after": self.bank_balance_after,
            "status": self.status
        }


class SettlementReconciliation(Base):
    __tablename__ = 'settlement_reconciliation'
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    transaction_id = Column(String(36), ForeignKey('transactions.id'), nullable=False)
    settlement_batch_id = Column(String(36), ForeignKey('settlement_batches.id'), nullable=False)
    
    status = Column(String(20), default='matched') # matched, unmatched, mismatch
    variance_amount = Column(Float, default=0.0)
    notes = Column(Text, nullable=True)
    verified_at = Column(DateTime, default=datetime.datetime.utcnow)

    transaction = relationship("Transaction", back_populates="reconciliations")
    batch = relationship("SettlementBatch", back_populates="reconciliations")

    def to_dict(self):
        return {
            "id": self.id,
            "transaction_id": self.transaction_id,
            "settlement_batch_id": self.settlement_batch_id,
            "status": self.status,
            "variance_amount": self.variance_amount,
            "notes": self.notes,
            "verified_at": self.verified_at.isoformat() if self.verified_at else None
        }


class FeeRule(Base):
    __tablename__ = 'fee_rules'
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    psp_provider = Column(String(50), nullable=False)
    payment_app = Column(String(50), nullable=True)
    amount_range_start = Column(Float, default=0.0)
    amount_range_end = Column(Float, default=1000000.0)
    psp_fee_percentage = Column(Float, default=0.0) # e.g., 0.015 for 1.5%
    psp_fee_fixed = Column(Float, default=0.0)
    payment_app_fee_percentage = Column(Float, default=0.0)
    payment_app_fee_fixed = Column(Float, default=0.0)
    effective_from = Column(Date, nullable=True)
    effective_until = Column(Date, nullable=True)


# --- 2. Database Initialization & Data Seeding ---

def init_db():
    Base.metadata.create_all(bind=ENGINE)
    seed_data_if_empty()

def seed_data_if_empty():
    session = SessionLocal()
    try:
        if session.query(Transaction).count() > 0:
            return # Already seeded
            
        # 1. Seed Fee Rules
        rules = [
            FeeRule(
                psp_provider='razorpay', payment_app='all',
                amount_range_start=0, amount_range_end=2000,
                psp_fee_percentage=0.0, psp_fee_fixed=0.0,
                payment_app_fee_percentage=0.0, payment_app_fee_fixed=0.0
            ),
            FeeRule(
                psp_provider='razorpay', payment_app='all',
                amount_range_start=2000.01, amount_range_end=100000,
                psp_fee_percentage=0.009, psp_fee_fixed=2.0, # 0.9% + ₹2
                payment_app_fee_percentage=0.0, payment_app_fee_fixed=0.0
            ),
            FeeRule(
                psp_provider='billdesk', payment_app='all',
                amount_range_start=0, amount_range_end=100000,
                psp_fee_percentage=0.0075, psp_fee_fixed=1.5,
                payment_app_fee_percentage=0.0, payment_app_fee_fixed=0.0
            ),
            FeeRule(
                psp_provider='payu', payment_app='all',
                amount_range_start=0, amount_range_end=100000,
                psp_fee_percentage=0.008, psp_fee_fixed=1.8,
                payment_app_fee_percentage=0.0, payment_app_fee_fixed=0.0
            )
        ]
        session.add_all(rules)
        session.commit()

        # 2. Seed Realistic Indian Merchant Transactions across 7 days
        merchant_id = "MERCHANT_001"
        apps = ["google_pay", "phonepe", "paytm", "whatsapp_pay", "cred"]
        psps = ["razorpay", "billdesk", "payu"]
        vpa_handles = {"google_pay": "okhdfcbank", "phonepe": "ybl", "paytm": "paytm", "whatsapp_pay": "waaxis", "cred": "cred"}
        
        today = datetime.date.today()
        seeded_txns = []
        batches = []
        reconciliations = []

        base_balance = 540000.00 # Starting bank balance ₹5,40,000

        for day_offset in range(6, -1, -1):
            batch_date = today - datetime.timedelta(days=day_offset)
            batch_psps = ["razorpay", "billdesk"]
            
            for psp in batch_psps:
                batch_gross = 0.0
                batch_fees = 0.0
                batch_net = 0.0
                batch_txns = []
                
                # Create 4-7 transactions per batch
                num_txns = 5 if day_offset > 0 else 4
                for idx in range(num_txns):
                    app = apps[(day_offset + idx) % len(apps)]
                    amount = float([450, 1250, 3400, 850, 5200, 2499, 15000, 950][(idx + day_offset) % 8])
                    
                    # Calculate fee logic
                    psp_pct = 0.009 if psp == 'razorpay' else 0.0075
                    fixed_fee = 2.0 if amount > 2000 else 0.0
                    calc_psp_fee = (amount * psp_pct) + fixed_fee if amount > 2000 else 0.0
                    app_fee = 0.0
                    gst_fee = round((calc_psp_fee + app_fee) * 0.18, 2)
                    total_fee = round(calc_psp_fee + app_fee + gst_fee, 2)
                    net_amount = round(amount - total_fee, 2)
                    
                    # Status determination
                    is_today = (day_offset == 0)
                    if is_today and idx == 3:
                        status = "pending" # pending customer authorization or settlement
                        cleared_at = None
                        settled_at = None
                    elif is_today and idx == 2:
                        status = "failed"
                        cleared_at = None
                        settled_at = None
                    else:
                        status = "success"
                        cleared_at = datetime.datetime.combine(batch_date, datetime.time(10 + idx, 15))
                        settled_at = datetime.datetime.combine(batch_date + datetime.timedelta(days=1), datetime.time(6, 30)) if not is_today else None

                    cust_phone = f"98765{day_offset}{idx}321"
                    txn_id = str(uuid.uuid4())
                    ref_id = f"pay_{psp[:3]}_{batch_date.strftime('%Y%m%d')}_{idx}_{uuid.uuid4().hex[:6]}"
                    
                    txn = Transaction(
                        id=txn_id,
                        merchant_id=merchant_id,
                        customer_id=f"cust_{cust_phone}",
                        upi_id=f"user{idx}@{vpa_handles[app]}",
                        amount=amount,
                        currency="INR",
                        status=status,
                        payment_app=app,
                        psp_provider=psp,
                        psp_reference_id=ref_id,
                        initiated_at=datetime.datetime.combine(batch_date, datetime.time(9 + idx, 5)),
                        customer_authorized_at=datetime.datetime.combine(batch_date, datetime.time(9 + idx, 6)) if status != 'failed' else None,
                        cleared_by_npci_at=cleared_at,
                        settled_at=settled_at,
                        gross_amount=amount,
                        psp_fee=round(calc_psp_fee, 2),
                        payment_app_fee=round(app_fee, 2),
                        gst_fee=gst_fee,
                        net_amount_to_merchant=net_amount,
                        is_disputed=(day_offset == 4 and idx == 1),
                        dispute_raised_at=datetime.datetime.combine(batch_date, datetime.time(18, 0)) if (day_offset == 4 and idx == 1) else None,
                        chargeback_amount=amount if (day_offset == 4 and idx == 1) else 0.0,
                        reversal_reason="User raised unrecognized mandate dispute" if (day_offset == 4 and idx == 1) else ("Bank server timeout" if status == 'failed' else None)
                    )
                    session.add(txn)
                    batch_txns.append(txn)
                    
                    if status == "success":
                        batch_gross += amount
                        batch_fees += total_fee
                        batch_net += net_amount
                
                # Only create settlement batches for previous days or completed batches
                if day_offset > 0:
                    batch_id = str(uuid.uuid4())
                    utr = f"UTR{batch_date.strftime('%Y%m%d')}{psp.upper()[:3]}{idx}992"
                    bank_before = base_balance
                    bank_after = round(base_balance + batch_net, 2)
                    base_balance = bank_after
                    
                    batch = SettlementBatch(
                        id=batch_id,
                        merchant_id=merchant_id,
                        batch_date=batch_date,
                        psp_provider=psp,
                        total_transactions=len([t for t in batch_txns if t.status == 'success']),
                        total_gross=round(batch_gross, 2),
                        total_fees=round(batch_fees, 2),
                        total_net=round(batch_net, 2),
                        utr=utr,
                        bank_settlement_time=datetime.datetime.combine(batch_date + datetime.timedelta(days=1), datetime.time(6, 30)),
                        bank_balance_before=bank_before,
                        bank_balance_after=bank_after,
                        status="settled"
                    )
                    session.add(batch)
                    
                    for t in batch_txns:
                        if t.status == "success":
                            rec = SettlementReconciliation(
                                id=str(uuid.uuid4()),
                                transaction_id=t.id,
                                settlement_batch_id=batch_id,
                                status="matched",
                                variance_amount=0.0,
                                notes="Automated UTR bank match verified via NPCI batch.",
                                verified_at=datetime.datetime.combine(batch_date + datetime.timedelta(days=1), datetime.time(7, 0))
                            )
                            session.add(rec)
                elif day_offset == 0:
                    # Current day pending batch
                    batch_id = str(uuid.uuid4())
                    batch = SettlementBatch(
                        id=batch_id,
                        merchant_id=merchant_id,
                        batch_date=batch_date,
                        psp_provider=psp,
                        total_transactions=len([t for t in batch_txns if t.status == 'success']),
                        total_gross=round(batch_gross, 2),
                        total_fees=round(batch_fees, 2),
                        total_net=round(batch_net, 2),
                        utr=None,
                        bank_settlement_time=None,
                        bank_balance_before=base_balance,
                        bank_balance_after=base_balance,
                        status="pending"
                    )
                    session.add(batch)

        session.commit()
    except Exception as e:
        session.rollback()
        print(f"Error seeding UPI data: {e}")
    finally:
        session.close()


# --- 3. Operational & Analytics Functions ---

def get_transaction_analytics(merchant_id="MERCHANT_001", status=None, date_from=None, date_to=None):
    session = SessionLocal()
    try:
        query = session.query(Transaction).filter(Transaction.merchant_id == merchant_id)
        if status and status.lower() != 'all':
            query = query.filter(Transaction.status == status.lower())
        if date_from:
            query = query.filter(Transaction.initiated_at >= date_from)
        if date_to:
            query = query.filter(Transaction.initiated_at <= date_to)
            
        txns = query.order_by(Transaction.initiated_at.desc()).all()
        return [t.to_dict() for t in txns]
    finally:
        session.close()

def get_settlement_summary(merchant_id="MERCHANT_001", date_from=None, date_to=None):
    session = SessionLocal()
    try:
        query = session.query(SettlementBatch).filter(SettlementBatch.merchant_id == merchant_id)
        if date_from:
            query = query.filter(SettlementBatch.batch_date >= date_from)
        if date_to:
            query = query.filter(SettlementBatch.batch_date <= date_to)
        batches = query.order_by(SettlementBatch.batch_date.desc()).all()
        return [b.to_dict() for b in batches]
    finally:
        session.close()

def get_reconciliation_report(merchant_id="MERCHANT_001"):
    session = SessionLocal()
    try:
        recs = session.query(
            SettlementReconciliation, Transaction, SettlementBatch
        ).join(
            Transaction, SettlementReconciliation.transaction_id == Transaction.id
        ).join(
            SettlementBatch, SettlementReconciliation.settlement_batch_id == SettlementBatch.id
        ).filter(
            Transaction.merchant_id == merchant_id
        ).order_by(SettlementReconciliation.verified_at.desc()).all()
        
        report = []
        for rec, txn, batch in recs:
            report.append({
                "reconciliation_id": rec.id,
                "transaction_id": txn.id,
                "psp_reference_id": txn.psp_reference_id,
                "amount": txn.amount,
                "net_amount": txn.net_amount_to_merchant,
                "batch_id": batch.id,
                "batch_date": batch.batch_date.isoformat() if batch.batch_date else None,
                "utr": batch.utr,
                "status": rec.status,
                "variance_amount": rec.variance_amount,
                "notes": rec.notes,
                "verified_at": rec.verified_at.isoformat() if rec.verified_at else None
            })
        return report
    finally:
        session.close()

def get_merchant_kpi_summary(merchant_id="MERCHANT_001"):
    session = SessionLocal()
    try:
        txns = session.query(Transaction).filter(Transaction.merchant_id == merchant_id).all()
        batches = session.query(SettlementBatch).filter(SettlementBatch.merchant_id == merchant_id).all()
        
        total_txns = len(txns)
        success_txns = [t for t in txns if t.status == 'success']
        pending_txns = [t for t in txns if t.status == 'pending']
        failed_txns = [t for t in txns if t.status == 'failed']
        disputed_txns = [t for t in txns if t.is_disputed]
        
        total_gross = sum(t.amount for t in txns if t.status == 'success')
        total_fees = sum(t.psp_fee + t.payment_app_fee + t.gst_fee for t in txns if t.status == 'success')
        total_net = sum(t.net_amount_to_merchant for t in txns if t.status == 'success')
        
        settled_batches = [b for b in batches if b.status == 'settled']
        pending_batches = [b for b in batches if b.status == 'pending']
        
        # Breakdown by PSP
        psp_breakdown = {}
        for t in success_txns:
            psp = t.psp_provider or 'unknown'
            if psp not in psp_breakdown:
                psp_breakdown[psp] = {"volume": 0.0, "fees": 0.0, "count": 0}
            psp_breakdown[psp]["volume"] += t.amount
            psp_breakdown[psp]["fees"] += (t.psp_fee + t.payment_app_fee + t.gst_fee)
            psp_breakdown[psp]["count"] += 1
            
        # Breakdown by Payment App
        app_breakdown = {}
        for t in txns:
            app = t.payment_app or 'unknown'
            app_breakdown[app] = app_breakdown.get(app, 0) + 1
            
        return {
            "merchant_id": merchant_id,
            "total_transactions": total_txns,
            "success_count": len(success_txns),
            "pending_count": len(pending_txns),
            "failed_count": len(failed_txns),
            "dispute_count": len(disputed_txns),
            "success_rate": round((len(success_txns) / total_txns * 100), 1) if total_txns > 0 else 0,
            "total_gross_volume": round(total_gross, 2),
            "total_fees_incurred": round(total_fees, 2),
            "total_net_settled": round(total_net, 2),
            "settled_batches_count": len(settled_batches),
            "pending_settlement_amount": round(sum(b.total_net for b in pending_batches), 2),
            "psp_breakdown": psp_breakdown,
            "app_breakdown": app_breakdown
        }
    finally:
        session.close()

def initiate_upi_payment(merchant_id, amount, customer_id, upi_id, payment_app="google_pay", psp_provider="razorpay"):
    session = SessionLocal()
    try:
        # Calculate fee
        psp_pct = 0.009 if psp_provider == 'razorpay' else 0.0075
        fixed_fee = 2.0 if amount > 2000 else 0.0
        psp_fee = round((amount * psp_pct) + fixed_fee if amount > 2000 else 0.0, 2)
        app_fee = 0.0
        gst_fee = round((psp_fee + app_fee) * 0.18, 2)
        total_fee = round(psp_fee + app_fee + gst_fee, 2)
        net_amount = round(amount - total_fee, 2)

        txn_id = str(uuid.uuid4())
        ref_id = f"pay_{psp_provider[:3]}_{datetime.date.today().strftime('%Y%m%d')}_{uuid.uuid4().hex[:8]}"

        txn = Transaction(
            id=txn_id,
            merchant_id=merchant_id,
            customer_id=customer_id,
            upi_id=upi_id,
            amount=amount,
            currency="INR",
            status="initiated",
            payment_app=payment_app,
            psp_provider=psp_provider,
            psp_reference_id=ref_id,
            initiated_at=datetime.datetime.utcnow(),
            gross_amount=amount,
            psp_fee=psp_fee,
            payment_app_fee=app_fee,
            gst_fee=gst_fee,
            net_amount_to_merchant=net_amount
        )
        session.add(txn)
        session.commit()
        return txn.to_dict()
    finally:
        session.close()

def process_razorpay_webhook(event: str, payload: dict):
    """
    Handle incoming Razorpay / PSP webhooks idempotently.
    Events: payment.authorized, payment.captured, payment.failed, refund.processed
    """
    session = SessionLocal()
    try:
        payment = payload.get("payment", {}).get("entity", {})
        ref_id = payment.get("id")
        if not ref_id:
            return {"status": "ignored", "reason": "No payment.id in payload"}

        txn = session.query(Transaction).filter(Transaction.psp_reference_id == ref_id).first()
        
        if not txn:
            # Create if initiated directly via PSP checkout
            amount = float(payment.get("amount", 0)) / 100.0
            txn = Transaction(
                id=str(uuid.uuid4()),
                merchant_id=payload.get("notes", {}).get("merchant_id", "MERCHANT_001"),
                customer_id=payload.get("notes", {}).get("customer_id", "cust_direct"),
                upi_id=payment.get("vpa", "customer@upi"),
                amount=amount,
                currency="INR",
                psp_provider="razorpay",
                psp_reference_id=ref_id,
                payment_app="google_pay" if "okhdfc" in payment.get("vpa", "") else "upi",
                initiated_at=datetime.datetime.utcfromtimestamp(payment.get("created_at", datetime.datetime.utcnow().timestamp())),
                gross_amount=amount,
                psp_fee=round(float(payment.get("fee", 0)) / 100.0, 2),
                gst_fee=round(float(payment.get("tax", 0)) / 100.0, 2),
                net_amount_to_merchant=round((float(payment.get("amount", 0)) - float(payment.get("fee", 0))) / 100.0, 2)
            )
            session.add(txn)

        if event == "payment.authorized":
            txn.status = "pending"
            txn.customer_authorized_at = datetime.datetime.utcnow()
        elif event == "payment.captured":
            txn.status = "success"
            txn.cleared_by_npci_at = datetime.datetime.utcnow()
        elif event == "payment.failed":
            txn.status = "failed"
            txn.reversal_reason = payment.get("error_description", "Payment authorization failed by bank")
        elif event == "refund.processed":
            txn.status = "refund"
            txn.reversal_reason = "Customer refund processed"

        session.commit()
        return {"status": "success", "event": event, "transaction_id": txn.id, "psp_reference_id": ref_id}
    except Exception as e:
        session.rollback()
        return {"status": "error", "error": str(e)}
    finally:
        session.close()

def process_settlement_webhook(event: str, payload: dict):
    """
    Handle settlement.processed webhook.
    """
    session = SessionLocal()
    try:
        settlement = payload.get("settlement", {}).get("entity", {})
        merchant_id = settlement.get("recipient_settlement_id", "MERCHANT_001")
        gross = float(settlement.get("amount", 0)) / 100.0
        fees = float(settlement.get("fees", 0)) / 100.0
        net = gross - fees
        utr = settlement.get("utr", f"UTR{datetime.date.today().strftime('%Y%m%d')}RZP{uuid.uuid4().hex[:4]}")

        existing = session.query(SettlementBatch).filter(SettlementBatch.utr == utr).first()
        if existing:
            existing.total_gross = round(gross, 2)
            existing.total_fees = round(fees, 2)
            existing.total_net = round(net, 2)
            existing.status = "settled"
            session.commit()
            return {"status": "success", "batch_id": existing.id, "utr": utr, "net_settled": net}

        batch = SettlementBatch(
            id=str(uuid.uuid4()),
            merchant_id=merchant_id,
            batch_date=datetime.date.today(),
            psp_provider="razorpay",
            total_transactions=len(payload.get("items", [])),
            total_gross=round(gross, 2),
            total_fees=round(fees, 2),
            total_net=round(net, 2),
            utr=utr,
            bank_settlement_time=datetime.datetime.utcnow(),
            status="settled"
        )
        session.add(batch)
        session.commit()
        return {"status": "success", "batch_id": batch.id, "utr": utr, "net_settled": net}
    except Exception as e:
        session.rollback()
        return {"status": "error", "error": str(e)}
    finally:
        session.close()


def generate_settlement_analytics_chart(merchant_id="MERCHANT_001"):
    """
    Generates a 7-day settlement trend chart and saves it to Assets/settlement_trend.png.
    """
    batches = get_settlement_summary(merchant_id)
    if not batches:
        return None
        
    df = pd.DataFrame(batches)
    df['batch_date'] = pd.to_datetime(df['batch_date'])
    df = df.sort_values('batch_date')
    
    # Aggregate daily
    daily = df.groupby(df['batch_date'].dt.strftime('%b %d')).agg({
        'total_gross': 'sum',
        'total_fees': 'sum',
        'total_net': 'sum'
    }).reset_index()

    plt.figure(figsize=(10, 5))
    x = range(len(daily))
    width = 0.25
    
    plt.bar([i - width for i in x], daily['total_gross'], width=width, label='Gross Volume (INR)', color='#3b82f6')
    plt.bar(x, daily['total_fees'], width=width, label='Processing Fees (INR)', color='#ef4444')
    plt.bar([i + width for i in x], daily['total_net'], width=width, label='Net Settled (INR)', color='#10b981')

    plt.xticks(x, daily['batch_date'], rotation=15)
    plt.title(f'UPI 7-Day Settlement Trend & Payouts ({merchant_id})', fontsize=14, fontweight='bold', pad=15)
    plt.xlabel('Settlement Date', fontsize=11)
    plt.ylabel('Amount (INR)', fontsize=11)
    plt.legend(frameon=True, facecolor='white', framealpha=0.9)
    plt.grid(axis='y', linestyle='--', alpha=0.3)
    plt.tight_layout()

    chart_path = os.path.join(DB_DIR, 'settlement_trend.png')
    plt.savefig(chart_path, dpi=200)
    plt.close()
    return chart_path

# Auto-initialize on module load
init_db()

if __name__ == "__main__":
    print("UPI Settlement Engine initialized.")
    kpis = get_merchant_kpi_summary("MERCHANT_001")
    print(f"Merchant KPIs: Total Txns: {kpis['total_transactions']}, Gross: INR {kpis['total_gross_volume']}, Net Settled: INR {kpis['total_net_settled']}")
    chart = generate_settlement_analytics_chart("MERCHANT_001")
    print(f"Chart generated at: {chart}")

