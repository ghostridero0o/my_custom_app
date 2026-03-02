import frappe
from frappe.desk.query_report import run as run_query_report
from my_custom_app.api.ai_filter_normalizer import normalize_filters
from my_custom_app.api.account_resolver import resolve_account_concept


def _safe_int(x, default=0):
    try:
        return int(x)
    except Exception:
        return default


def _pluck_value(row: dict, key: str):
    # key like "dec_2025" or "jan_2026"... may not exist
    if not isinstance(row, dict):
        return None
    return row.get(key)


def _extract_pl_summary(columns, data):
    """
    Profit and Loss Statement in ERPNext usually contains special rows:
    - "'Tổng số Thu nhập (Có)'"   -> total income
    - "'Tổng số chi tiêu (Nợ)'"   -> total expense
    - "'lợi nhuận của năm'"       -> net profit
    We will extract value for the only fiscal year column, e.g. dec_2025.
    """
    summary = {
        "total_income": None,
        "total_expense": None,
        "net_profit": None,
        "year_column": None,
    }

    if not columns or not data:
        return summary

    # Find the main numeric column (e.g. dec_2025)
    year_field = None
    for c in columns:
        if isinstance(c, dict) and c.get("fieldtype") == "Currency":
            fn = c.get("fieldname")
            if fn and fn != "currency":
                year_field = fn
                break

    summary["year_column"] = year_field
    if not year_field:
        return summary

    for row in data:
        if not isinstance(row, dict):
            continue
        acc = (row.get("account") or row.get("account_name") or "").strip().lower()

        val = _pluck_value(row, year_field)
        if val is None:
            continue

        if "tổng số thu nhập" in acc:
            summary["total_income"] = val
        elif "tổng số chi tiêu" in acc:
            summary["total_expense"] = val
        elif "lợi nhuận của năm" in acc:
            summary["net_profit"] = val

    return summary


def _shrink_rows(report_name: str, columns, data, max_rows: int = 120):
    """
    Reduce payload to avoid Raven freezing.
    - Keep summary rows always
    - Keep lower indent rows first
    """
    if not data:
        return data

    # For P&L: keep lines indent <= 2 + summary lines + first N
    if report_name == "Profit and Loss Statement":
        keep = []
        summary_markers = ("tổng số thu nhập", "tổng số chi tiêu", "lợi nhuận của năm")
        for row in data:
            if not isinstance(row, dict):
                continue
            acc = (row.get("account") or row.get("account_name") or "").strip().lower()
            indent = row.get("indent")
            try:
                indent = float(indent) if indent is not None else 999
            except Exception:
                indent = 999

            if any(m in acc for m in summary_markers):
                keep.append(row)
            elif indent <= 2:
                keep.append(row)

        # If still too big, hard cut
        if len(keep) > max_rows:
            keep = keep[:max_rows]
        return keep

    # Default: hard cut
    return data[:max_rows]


@frappe.whitelist()
def search_link(doctype: str, txt: str = "", filters=None, limit: int = 20):
    if not doctype:
        frappe.throw("doctype is required")

    if filters and isinstance(filters, str):
        filters = frappe.parse_json(filters)

    fn = frappe.get_attr("frappe.desk.search.search_link")
    return fn(
        doctype=doctype,
        txt=txt or "",
        filters=filters,
        page_length=_safe_int(limit, 20),
    )


@frappe.whitelist()
def run_erpnext_report(
    report_name: str = None,
    filters=None,
    user_text: str = None,
    limit: int = 200,
    ignore_prepared_report: bool = True,
):
    """
    Run any ERPNext report and return:
    - summary (when possible, esp. P&L)
    - filters_used
    - columns
    - data (shrunk to avoid Raven freeze)
    """
    if not report_name:
        frappe.throw("report_name is required")

    # Route all cash flow requests to your custom report (never use standard Cash Flow)
    text = (user_text or "").lower()
    if report_name in ("Cash Flow", "Cash Flow Statement") or "dòng tiền" in text or "cash flow" in text:
        report_name = "Custom Cash Flow"

    # Normalize filters from context
    filters = normalize_filters(
        report_name=report_name,
        user_text=user_text or "",
        filters=filters,
    )

    out = run_query_report(
        report_name=report_name,
        filters=filters,
        ignore_prepared_report=ignore_prepared_report,
    ) or {}

    columns = out.get("columns") or []
    data = out.get("result") or out.get("data") or []

    # Safety limit (still apply, but shrink first to avoid huge payload)
    limit = _safe_int(limit, 200)
    if limit <= 0:
        limit = 200

    # Shrink payload so Raven won't hang
    data_small = _shrink_rows(report_name, columns, data, max_rows=min(max(limit, 50), 200))

    # Extract key figures for P&L so bot won't hallucinate "no data"
    summary = None
    if report_name == "Profit and Loss Statement":
        summary = _extract_pl_summary(columns, data)

    result = {
        "report_name": report_name,
        "filters_used": filters,
        "summary": summary,             # <-- cực quan trọng
        "columns": columns,
        "data": data_small,
        "row_count": len(data),
        "returned_rows": len(data_small),
    }

    # Return in Raven-friendly wrapper
    return {
        "success": True,
        "message": result,
        "row_count": result["row_count"],
        "returned_rows": result["returned_rows"],
    }
