import os
import json
import datetime
from typing import Dict, Any, List, Optional
import pandas as pd

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq

def calculate_portfolio_allocation(
    risk_profile: str,
    investment_horizon: str,
    monthly_investible_surplus: float
) -> Dict[str, Any]:
    """
    Calculate deterministic asset allocation percentages and recommended monthly amounts.
    """
    risk_lower = risk_profile.lower()
    horizon_lower = investment_horizon.lower()

    if "conservative" in risk_lower or "defensive" in risk_lower:
        equity_pct = 30.0
        debt_pct = 50.0
        gold_pct = 10.0
        cash_pct = 10.0
        expected_cagr = 8.5
    elif "aggressive" in risk_lower or "growth" in risk_lower or "kiyosaki" in risk_lower:
        equity_pct = 70.0
        debt_pct = 15.0
        gold_pct = 5.0
        cash_pct = 10.0
        expected_cagr = 13.5
    else:  # Moderate / Balanced
        equity_pct = 55.0
        debt_pct = 30.0
        gold_pct = 5.0
        cash_pct = 10.0
        expected_cagr = 11.5

    # Adjust for short-term horizon
    if "short" in horizon_lower or "< 3" in horizon_lower or "1-3" in horizon_lower:
        equity_pct = max(10.0, equity_pct - 20.0)
        debt_pct = min(70.0, debt_pct + 15.0)
        cash_pct = min(20.0, cash_pct + 5.0)
        expected_cagr = max(7.0, expected_cagr - 2.5)

    surplus = max(1000.0, monthly_investible_surplus)
    
    # Concrete instrument recommendations (Indian context)
    instruments = [
        {
            "asset_class": "Equity Index & Large Cap",
            "allocation_pct": round(equity_pct * 0.6, 1),
            "monthly_amount": round(surplus * (equity_pct * 0.6) / 100.0, 2),
            "suggested_instruments": ["Nifty 50 Index Fund", "BSE Sensex Index Fund"],
            "expected_return": "12-14% CAGR",
            "rationale": "Core compounding engine with lowest expense ratios."
        },
        {
            "asset_class": "Active / Mid-Cap & Flexi-Cap",
            "allocation_pct": round(equity_pct * 0.4, 1),
            "monthly_amount": round(surplus * (equity_pct * 0.4) / 100.0, 2),
            "suggested_instruments": ["Parag Parikh Flexi Cap Fund", "Nifty Next 50 ETF"],
            "expected_return": "13-16% CAGR",
            "rationale": "High growth potential with diversified market-cap exposure."
        },
        {
            "asset_class": "Fixed Income, PPF & Debt",
            "allocation_pct": debt_pct,
            "monthly_amount": round(surplus * debt_pct / 100.0, 2),
            "suggested_instruments": ["Public Provident Fund (PPF 7.1%)", "Target Maturity Debt Index Funds", "Corporate Bond Fund"],
            "expected_return": "7.0-8.5% Safe Yield",
            "rationale": "Capital protection, risk mitigation, and sovereign tax-free interest."
        },
        {
            "asset_class": "Gold / Inflation Hedge",
            "allocation_pct": gold_pct,
            "monthly_amount": round(surplus * gold_pct / 100.0, 2),
            "suggested_instruments": ["Sovereign Gold Bonds (SGBs)", "Nippon Gold ETF"],
            "expected_return": "9-11% CAGR",
            "rationale": "Hedge against currency depreciation and equity drawdowns."
        },
        {
            "asset_class": "Liquid Emergency Reserve",
            "allocation_pct": cash_pct,
            "monthly_amount": round(surplus * cash_pct / 100.0, 2),
            "suggested_instruments": ["High-Yield Savings / Arbitrage Fund / Liquid Fund"],
            "expected_return": "6.5-7.2% Liquid",
            "rationale": "Immediate liquidity buffer preventing premature equity withdrawals."
        }
    ]

    # Projections over 5, 10, 20 years with monthly SIP compounding
    # FV = P * [((1 + r)^n - 1) / r] * (1 + r)
    r = (expected_cagr / 100.0) / 12.0
    projections = {}
    for yrs in [3, 5, 10, 15, 20]:
        n = yrs * 12
        fv = surplus * (((1 + r)**n - 1) / r) * (1 + r)
        invested = surplus * n
        projections[f"{yrs}_years"] = {
            "years": yrs,
            "total_invested": round(invested, 2),
            "estimated_future_value": round(fv, 2),
            "wealth_gain": round(fv - invested, 2)
        }

    return {
        "summary": {
            "equity_pct": equity_pct,
            "debt_pct": debt_pct,
            "gold_pct": gold_pct,
            "cash_pct": cash_pct,
            "expected_cagr": expected_cagr,
            "monthly_surplus_allocated": surplus
        },
        "instruments": instruments,
        "projections": projections
    }

def generate_ai_guru_wealth_plan(
    monthly_income: float,
    monthly_expenses: float,
    current_savings: float = 0.0,
    existing_debts: float = 0.0,
    risk_profile: str = "Moderate",
    investment_horizon: str = "7+ Years (Long Term)",
    primary_goal: str = "Wealth Creation & Compounding",
    preferred_philosophy: str = "Comprehensive Multi-Guru Synthesis"
) -> Dict[str, Any]:
    """
    Generate an in-depth AI-powered wealth management and investment advisory blueprint.
    Integrates quantitative portfolio math with LLM strategic analysis.
    """
    surplus = max(0.0, monthly_income - monthly_expenses)
    savings_rate = (surplus / monthly_income * 100.0) if monthly_income > 0 else 0.0
    
    # 1. Calculate deterministic allocation
    alloc = calculate_portfolio_allocation(risk_profile, investment_horizon, surplus)

    # 2. Prompt LLM for customized Guru reasoning and actionable strategy
    gemini_key = os.getenv("GEMINI_API_KEY")
    groq_key = os.getenv("GROQ_API_KEY")
    
    ai_synthesis = None

    prompt = f"""
You are the FinVista Chief AI Wealth Strategist and Senior Portfolio Architect.
Analyze this investor's financial profile and formulate a professional, highly actionable, personalized Wealth Management & Investment Strategy.

### Investor Financial Profile:
- Monthly Income: INR ₹{monthly_income:,.2f}
- Monthly Expenses: INR ₹{monthly_expenses:,.2f}
- Net Monthly Investible Surplus: INR ₹{surplus:,.2f} (Savings Rate: {savings_rate:.1f}%)
- Current Liquid Savings: INR ₹{current_savings:,.2f}
- Outstanding Debts: INR ₹{existing_debts:,.2f}
- Risk Tolerance Profile: {risk_profile}
- Investment Time Horizon: {investment_horizon}
- Primary Financial Milestone / Goal: {primary_goal}
- Chosen Financial Philosophy: {preferred_philosophy}

### Calculated Strategic Allocation:
- Equity: {alloc['summary']['equity_pct']}%
- Debt / PPF: {alloc['summary']['debt_pct']}%
- Gold: {alloc['summary']['gold_pct']}%
- Emergency Cash: {alloc['summary']['cash_pct']}%
- Estimated Portfolio CAGR: {alloc['summary']['expected_cagr']}%

Provide a comprehensive, direct, and structured advisory report in clean markdown with the following sections:
1. **Executive Strategy & Diagnostic Assessment**: Direct assessment of their savings rate and debt-to-surplus ratio.
2. **Guru Philosophical Synthesis**: How legendary principles (Buffett's moat & low-cost indexing, Kiyosaki's asset acquisition, Ramsey's debt freedom, Sethi's automated conscious spending) directly apply to their numbers.
3. **Actionable Portfolio Construction**: Specific monthly SIP breakdown in INR (₹) across Index funds, Flexi-cap, Debt/PPF, and Gold.
4. **Phased 12-Month Wealth Roadmap**: Exact steps for Month 1 (automation), Month 3 (emergency buffer), Month 6 (tax optimization via 80C/NPS), and Year 1 (portfolio rebalancing).
5. **Risk Mitigation & Downside Protection Rules**: Strict behavioral rules for bear markets and emergency management.
"""

    if gemini_key:
        try:
            llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", google_api_key=gemini_key)
            resp = llm.invoke([
                SystemMessage(content="You are an elite, certified AI Wealth Strategist and Portfolio Manager delivering rigorous, practical, high-value financial advisory."),
                HumanMessage(content=prompt)
            ])
            ai_synthesis = resp.content
        except Exception as e:
            pass

    if not ai_synthesis and groq_key:
        try:
            llm_groq = ChatGroq(model="llama-3.3-70b-versatile", groq_api_key=groq_key)
            resp = llm_groq.invoke([
                SystemMessage(content="You are an elite, certified AI Wealth Strategist delivering practical investment roadmaps."),
                HumanMessage(content=prompt)
            ])
            ai_synthesis = resp.content
        except Exception as e:
            pass

    # Expert Algorithmic Fallback if offline / API key missing
    if not ai_synthesis:
        ai_synthesis = f"""
### Executive Strategy & Diagnostic Assessment
- **Cash Flow Health**: Your monthly investible surplus of **₹{surplus:,.2f}** represents a **{savings_rate:.1f}% savings rate**. This provides a strong foundation for automated wealth compounding.
- **Debt & Liquidity Review**: Current savings of **₹{current_savings:,.2f}** should be calibrated against an emergency target of **₹{monthly_expenses * 6:,.2f}** (6 months expenses).

### {preferred_philosophy} Strategy Synthesis
1. **Warren Buffett Principle**: Focus on broad-market low-cost indexing (*Nifty 50*). Do not try to time macroeconomic market swings; invest continuously every single month.
2. **Robert Kiyosaki Cashflow Asset Rule**: Channel at least ₹{surplus * 0.7:,.2f}/month directly into acquiring income-producing assets (Equities & Dividend Growth Funds) before any lifestyle upgrades.
3. **Dave Ramsey Debt Snowball**: If you hold high-interest debts (₹{existing_debts:,.2f}), aggressively clear them before ramping up speculative investments.
4. **Ramit Sethi Conscious Automation**: Configure automatic SIP debits within 48 hours of salary credit so saving is effortless and guaranteed.

### Tailored Monthly Investment Roadmap (Total: ₹{surplus:,.2f}/month)
- **₹{surplus * (alloc['summary']['equity_pct'] * 0.6) / 100:,.2f}/mo** $\\rightarrow$ **Nifty 50 / Sensex Index Fund** (Core Large-Cap Compounder, ~12% CAGR)
- **₹{surplus * (alloc['summary']['equity_pct'] * 0.4) / 100:,.2f}/mo** $\\rightarrow$ **Flexi Cap / Mid Cap Fund** (High Alpha Growth, ~14% CAGR)
- **₹{surplus * alloc['summary']['debt_pct'] / 100:,.2f}/mo** $\\rightarrow$ **PPF (7.1% Tax-Free) / Corporate Debt Index** (Safe Capital Preservation)
- **₹{surplus * alloc['summary']['gold_pct'] / 100:,.2f}/mo** $\\rightarrow$ **Sovereign Gold Bonds / Gold ETF** (Inflation & Currency Hedge)
- **₹{surplus * alloc['summary']['cash_pct'] / 100:,.2f}/mo** $\\rightarrow$ **Liquid / Arbitrage Fund** (Emergency Liquidity Buffer)

### 12-Month Phased Execution Schedule
- **Month 1**: Establish automated SIP mandates on the 5th of every month.
- **Month 3**: Audit and top up Emergency Fund until 6 months of expenses are secured.
- **Month 6**: Optimize tax deductions via Section 80C (ELSS/PPF) and Section 80CCD(1B) NPS.
- **Month 12**: Annual portfolio rebalancing to maintain target {alloc['summary']['equity_pct']}/{alloc['summary']['debt_pct']} asset allocation.
"""

    return {
        "profile": {
            "monthly_income": monthly_income,
            "monthly_expenses": monthly_expenses,
            "monthly_surplus": surplus,
            "savings_rate": savings_rate,
            "current_savings": current_savings,
            "existing_debts": existing_debts,
            "risk_profile": risk_profile,
            "investment_horizon": investment_horizon,
            "primary_goal": primary_goal,
            "preferred_philosophy": preferred_philosophy
        },
        "allocation": alloc,
        "ai_synthesis": ai_synthesis,
        "generated_at": datetime.datetime.now().isoformat()
    }
