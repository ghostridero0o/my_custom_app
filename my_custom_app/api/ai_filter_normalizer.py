# -*- coding: utf-8 -*-
import re
import calendar
from datetime import date
import frappe


def _last_day_of_month(y: int, m: int) -> str:
    last_day = calendar.monthrange(y, m)[1]
    return f"{y:04d}-{m:02d}-{last_day:02d}"


def _first_day_of_month(y: int, m: int) -> str:
    return f"{y:04d}-{m:02d}-01"


def _parse_time_context_vi(user_text: str):
    """
    Parse Vietnamese time context:
    - "năm nay", "tháng này", "quý này"
    - "năm 2025"
    - "tháng 3/2026", "tháng 3"
    - "quý 1", "q1"
    Returns: (year:int|None, month:int|None, quarter:int|None)
    """
    text = (user_text or "").strip().lower()
    today = date.today()

    year = None
    month = None
    quarter = None

    # explicit year: 20xx
    m_year = re.search(r"\b(20\d{2})\b", text)
    if m_year:
        year = int(m_year.group(1))

    # month: "tháng 3", "thang 03", "tháng 3/2026"
    m_month = re.search(r"(?:tháng|thang)\s*(\d{1,2})(?:\s*/\s*(20\d{2}))?\b", text)
    if m_month:
        month = int(m_month.group(1))
        if m_month.group(2) and not year:
            year = int(m_month.group(2))

    # quarter: "quý 1", "q1"
    m_quarter = re.search(r"(?:quý|q)\s*(\d)\b", text)
    if m_quarter:
        quarter = int(m_quarter.group(1))

    # relative phrases
    if "năm nay" in text and not year:
        year = today.year

    if "tháng này" in text and not month:
        month = today.month
        if not year:
            year = today.year

    if "quý này" in text and not quarter:
        quarter = (today.month - 1) // 3 + 1
        if not year:
            year = today.year

    # If month/quarter given but no year -> current year
    if (month or quarter) and not year:
        year = today.year

    return year, month, quarter


def normalize_time_filters(user_text: str, filters: dict) -> dict:
    """
    Infer time range for typical reports that use from_date/to_date.
    Fills: from_date, to_date, periodicity (default Monthly)
    """
    if not filters:
        filters = {}

    # If user already gave dates, don't override
    if filters.get("from_date") and filters.get("to_date"):
        filters.setdefault("periodicity", "Monthly")
        return filters

    year, month, quarter = _parse_time_context_vi(user_text)
    today = date.today()

    # Apply inferred range
    if quarter and year:
        q_start = (quarter - 1) * 3 + 1
        q_end = q_start + 2
        filters["from_date"] = _first_day_of_month(year, q_start)
        filters["to_date"] = _last_day_of_month(year, q_end)
        filters.setdefault("periodicity", "Monthly")
        return filters

    if month and year:
        filters["from_date"] = _first_day_of_month(year, month)
        filters["to_date"] = _last_day_of_month(year, month)
        filters.setdefault("periodicity", "Monthly")
        return filters

    if year:
        filters["from_date"] = f"{year:04d}-01-01"
        filters["to_date"] = f"{year:04d}-12-31"
        filters.setdefault("periodicity", "Monthly")
        return filters

    # default current month
    y, m = today.year, today.month
    filters["from_date"] = _first_day_of_month(y, m)
    filters["to_date"] = _last_day_of_month(y, m)
    filters.setdefault("periodicity", "Monthly")
    return filters


def _set_include_default_entries(filters: dict, default_val=1):
    """
    Support both keys across ERPNext versions/customizations:
    - include_default_book_entries
    - include_default_fb_entries
    """
    if "include_default_book_entries" in filters:
        val = filters.get("include_default_book_entries")
    elif "include_default_fb_entries" in filters:
        val = filters.get("include_default_fb_entries")
    else:
        val = default_val

    filters["include_default_book_entries"] = val
    filters["include_default_fb_entries"] = val


def _normalize_profit_and_loss(user_text: str, filters: dict) -> dict:
    """
    Your ERPNext P&L expects Fiscal Year fields:
    - filter_based_on="Fiscal Year"
    - from_fiscal_year, to_fiscal_year
    - periodicity="Yearly"
    - selected_view="Report"
    - accumulated_values=1
    - include_default_book_entries=1 (and keep fb alias too)
    """
    year, month, quarter = _parse_time_context_vi(user_text)
    today = date.today()

    # If user explicitly passed fiscal year fields, keep them
    fy_from = filters.get("from_fiscal_year")
    fy_to = filters.get("to_fiscal_year")

    # map legacy year keys if present
    if filters.get("start_year") and not fy_from:
        fy_from = str(filters.get("start_year"))
    if filters.get("end_year") and not fy_to:
        fy_to = str(filters.get("end_year"))

    # If year parsed from text, prefer it
    if year:
        fy_from = fy_from or str(year)
        fy_to = fy_to or str(year)
    else:
        fy_from = fy_from or str(today.year)
        fy_to = fy_to or str(today.year)

    # Enforce P&L mode
    filters["filter_based_on"] = "Fiscal Year"
    filters["from_fiscal_year"] = str(fy_from)
    filters["to_fiscal_year"] = str(fy_to)

    # ensure view + periodicity
    filters.setdefault("periodicity", "Yearly")
    filters.setdefault("selected_view", "Report")

    # toggles
    filters.setdefault("accumulated_values", 1)
    _set_include_default_entries(filters, default_val=1)

    # Remove conflicting date keys to avoid ERPNext returning empty
    for k in ("from_date", "to_date", "period_start_date", "period_end_date", "start_year", "end_year"):
        filters.pop(k, None)

    # Some deployments also use these UI keys; keep if user provided, otherwise ignore
    # filters.setdefault("selected_view", "Report") already.

    return filters


def _normalize_cash_flow(user_text: str, filters: dict) -> dict:
    """
    Cash Flow expects Date Range fields:
    - filter_based_on="Date Range"
    - period_start_date, period_end_date
    """
    # If user passed fiscal year fields, convert to date range
    if filters.get("from_fiscal_year") and not filters.get("period_start_date"):
        fy_start = frappe.get_cached_value("Fiscal Year", filters.get("from_fiscal_year"), "year_start_date")
        if fy_start:
            filters["period_start_date"] = fy_start
    if filters.get("to_fiscal_year") and not filters.get("period_end_date"):
        fy_end = frappe.get_cached_value("Fiscal Year", filters.get("to_fiscal_year"), "year_end_date")
        if fy_end:
            filters["period_end_date"] = fy_end

    # Map generic dates if provided
    if filters.get("from_date") and not filters.get("period_start_date"):
        filters["period_start_date"] = filters.get("from_date")
    if filters.get("to_date") and not filters.get("period_end_date"):
        filters["period_end_date"] = filters.get("to_date")

    # If still missing, infer from user_text (year/month/quarter)
    if not filters.get("period_start_date") or not filters.get("period_end_date"):
        inferred = normalize_time_filters(user_text=user_text, filters={})
        filters.setdefault("period_start_date", inferred.get("from_date"))
        filters.setdefault("period_end_date", inferred.get("to_date"))

    filters["filter_based_on"] = "Date Range"
    filters.setdefault("periodicity", "Yearly")

    # Remove conflicting keys to avoid ERPNext validation errors
    for k in ("from_fiscal_year", "to_fiscal_year", "from_date", "to_date", "start_year", "end_year"):
        filters.pop(k, None)

    return filters


def _normalize_balance_sheet(user_text: str, filters: dict) -> dict:
    """
    Balance Sheet expects Fiscal Year fields (same base as Financial Statements):
    - filter_based_on="Fiscal Year"
    - from_fiscal_year, to_fiscal_year
    - periodicity="Yearly"
    - selected_view="Report"
    - accumulated_values=1
    - include_default_book_entries=1 (and keep fb alias too)
    """
    year, month, quarter = _parse_time_context_vi(user_text)
    today = date.today()

    fy_from = filters.get("from_fiscal_year")
    fy_to = filters.get("to_fiscal_year")

    if filters.get("start_year") and not fy_from:
        fy_from = str(filters.get("start_year"))
    if filters.get("end_year") and not fy_to:
        fy_to = str(filters.get("end_year"))

    if year:
        fy_from = fy_from or str(year)
        fy_to = fy_to or str(year)
    else:
        fy_from = fy_from or str(today.year)
        fy_to = fy_to or str(today.year)

    filters["filter_based_on"] = "Fiscal Year"
    filters["from_fiscal_year"] = str(fy_from)
    filters["to_fiscal_year"] = str(fy_to)

    filters.setdefault("periodicity", "Yearly")
    filters.setdefault("selected_view", "Report")
    filters.setdefault("accumulated_values", 1)
    _set_include_default_entries(filters, default_val=1)

    for k in ("from_date", "to_date", "period_start_date", "period_end_date", "start_year", "end_year"):
        filters.pop(k, None)

    return filters


def normalize_filters(report_name: str, user_text: str, filters):
    """
    Entry point used by run_erpnext_report.
    - For P&L: enforce Fiscal Year filter set (as your working curl example).
    - For others: infer from_date/to_date.
    """
    if not filters:
        filters = {}

    if isinstance(filters, str):
        filters = frappe.parse_json(filters)

    # Ensure dict
    if not isinstance(filters, dict):
        filters = {}

    if report_name == "Profit and Loss Statement":
        return _normalize_profit_and_loss(user_text=user_text, filters=filters)

    if report_name == "Balance Sheet":
        return _normalize_balance_sheet(user_text=user_text, filters=filters)

    if report_name in ("Cash Flow", "Custom Cash Flow"):
        return _normalize_cash_flow(user_text=user_text, filters=filters)

    # fallback: reports using from_date/to_date
    filters = normalize_time_filters(user_text=user_text, filters=filters)

    # many query reports accept view key; harmless if unused
    filters.setdefault("selected_view", "Report")
    return filters
