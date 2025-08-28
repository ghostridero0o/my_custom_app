# File: custom_app/custom_app/report/custom_profit_and_loss/custom_profit_and_loss.py
# -*- coding: utf-8 -*-

import frappe
from frappe.utils import getdate
from frappe import _


def execute(filters=None):
    filters = filters or {}

    company = filters.get("company") or frappe.defaults.get_default("company")
    if not company:
        frappe.throw(_("Please select a Company"))

    # Fiscal year filters (Link to Fiscal Year)
    from_fy = filters.get("from_fiscal_year")
    to_fy = filters.get("to_fiscal_year")

    # extra filters
    project = filters.get("project")
    cost_center = filters.get("cost_center")
    finance_book = filters.get("finance_book")
    show_ratio = frappe.utils.cint(filters.get("show_ratio"))

    # resolve fiscal years to calendar years
    if from_fy:
        start_date = frappe.db.get_value("Fiscal Year", from_fy, "year_start_date")
        start_year = getdate(start_date).year if start_date else getdate().year
    else:
        start_year = getdate().year

    if to_fy:
        end_date = frappe.db.get_value("Fiscal Year", to_fy, "year_end_date")
        end_year = getdate(end_date).year if end_date else start_year
    else:
        end_year = start_year

    if end_year < start_year:
        frappe.throw(_("To Fiscal Year must not be earlier than From Fiscal Year"))

    years = list(range(start_year, end_year + 1))

    currency = frappe.get_cached_value("Company", company, "default_currency")
    columns = get_columns(years, currency, show_ratio)

    def yr_key(y):
        return f"y{y}"

    def new_row(label, code=None, indent=0, is_group=1, account=None, account_number=None, parent_account=None):
        row = {
            "account": label,
            "code": code,
            "indent": indent,
            "is_group": is_group,
            "account_name": account or label,
            "account_number": account_number,
            "parent_account": parent_account,
        }
        for y in years:
            row[yr_key(y)] = 0.0
        return row

    def sum_into(target, source):
        for y in years:
            target[yr_key(y)] += source.get(yr_key(y), 0.0)

    def gl_amounts_for_account(acc_name):
        root_type, report_type, acc_number = frappe.db.get_value(
            "Account", {"name": acc_name, "company": company}, ["root_type", "report_type", "account_number"], as_dict=False
        )
        credit_nature = root_type in ("Income",)
        out = {yr_key(y): 0.0 for y in years}
        for y in years:
            from_date = frappe.utils.get_first_day(f"{y}-01-01")
            to_date = frappe.utils.get_last_day(f"{y}-12-31")

            conditions = """
                company=%(company)s AND account=%(account)s AND is_cancelled=0
                AND posting_date BETWEEN %(from_date)s AND %(to_date)s
            """

            params = {
                "company": company,
                "account": acc_name,
                "from_date": from_date,
                "to_date": to_date,
            }

            if filters.get("project"):
                conditions += " AND project = %(project)s"
                params["project"] = filters["project"]

            if filters.get("cost_center"):
                conditions += " AND cost_center = %(cost_center)s"
                params["cost_center"] = filters["cost_center"]

            fb = filters.get("finance_book")

            if fb:
                # Nếu user chọn finance_book: lấy các bản ghi có finance_book = fb OR finance_book IS NULL/empty
                conditions += " AND (finance_book = %(finance_book)s OR finance_book IS NULL OR finance_book = '')"
                params["finance_book"] = fb
            else:
                # Nếu user không chọn finance_book: chỉ lấy các bản ghi không có finance_book (NULL hoặc empty)
                conditions += " AND (finance_book IS NULL OR finance_book = '')"
            res = frappe.db.sql(f"""
                SELECT COALESCE(SUM(credit),0) AS credit, COALESCE(SUM(debit),0) AS debit
                FROM `tabGL Entry`
                WHERE {conditions}
            """, params, as_dict=True)[0]

            if credit_nature:
                val = (res["credit"] - res["debit"]) or 0.0
            else:
                val = (res["debit"] - res["credit"]) or 0.0
            out[yr_key(y)] = val
        return out

    def build_account_tree(parent_account, indent=1):
        children = frappe.get_all(
            "Account",
            filters={
                "company": company,
                "parent_account": parent_account,
                "disabled": 0,
                "report_type": "Profit and Loss",
            },
            fields=["name", "account_name", "account_number", "is_group", "parent_account"],
            order_by="CAST(account_number AS UNSIGNED), account_number ASC",
        )

        rows = []
        for ch in children:
            r = new_row(
                label=ch.account_name or ch.name,
                indent=indent,
                is_group=1 if ch.is_group else 0,
                account=ch.name,
                account_number=ch.account_number,
                parent_account=ch.parent_account,
            )

            if ch.is_group:
                # build subtree first and sum children into group
                sub_rows = build_account_tree(ch.name, indent=indent + 1)
                for sr in sub_rows:
                    sum_into(r, sr)
                rows.append(r)
                rows.extend(sub_rows)
            else:
                vals = gl_amounts_for_account(ch.name)
                for y in years:
                    r[yr_key(y)] = vals[yr_key(y)]
                rows.append(r)

        return rows

    def add_group_by_account_number(parent_number, parent_row, indent=1):
        parent_account = frappe.db.get_value(
            "Account",
            {
                "company": company,
                "account_number": str(parent_number),
                "disabled": 0,
                "report_type": "Profit and Loss",
            },
            "name",
        )
        if not parent_account:
            return []

        rows = build_account_tree(parent_account, indent=indent)
        # sum only direct children (rows with same indent)
        for r in rows:
            if r["indent"] == indent:
                sum_into(parent_row, r)
        return rows

    data = []

    # 1. Doanh thu bán hàng
    r01 = new_row(_(u"1. Doanh thu bán hàng và cung cấp dịch vụ"), code="01", indent=0, is_group=1)
    data.append(r01)
    data.extend(add_group_by_account_number(511, r01, indent=1))

    # 2. Các khoản giảm trừ
    r02 = new_row(_(u"2. Các khoản giảm trừ doanh thu"), code="02", indent=0, is_group=1)
    data.append(r02)
    data.extend(add_group_by_account_number(521, r02, indent=1))

    # 3. Doanh thu thuần
    r10 = new_row(_(u"3. Doanh thu thuần về bán hàng và cung cấp dịch vụ"), code="10", indent=0, is_group=0)
    for y in years:
        r10[yr_key(y)] = r01[yr_key(y)] - r02[yr_key(y)]
    data.append(r10)

    # 4. Giá vốn hàng bán (group root is account_number = 632)
    r11 = new_row(_(u"4. Giá vốn hàng bán"), code="11", indent=0, is_group=1)
    data.append(r11)
    data.extend(add_group_by_account_number(632, r11, indent=1))

    # 5. Lợi nhuận gộp
    r20 = new_row(_(u"5. Lợi nhuận gộp về bán hàng và cung cấp dịch vụ"), code="20", indent=0, is_group=0)
    for y in years:
        r20[yr_key(y)] = r10[yr_key(y)] - r11[yr_key(y)]
    data.append(r20)

    # 6. Doanh thu hoạt động tài chính
    r21 = new_row(_(u"6. Doanh thu hoạt động tài chính"), code="21", indent=0, is_group=1)
    data.append(r21)
    data.extend(add_group_by_account_number(515, r21, indent=1))

    # 7. Chi phí tài chính
    r22 = new_row(_(u"7. Chi phí tài chính"), code="22", indent=0, is_group=1)
    data.append(r22)
    data.extend(add_group_by_account_number(635, r22, indent=1))

    # 8. Chi phí bán hàng
    r25 = new_row(_(u"8. Chi phí bán hàng"), code="25", indent=0, is_group=1)
    data.append(r25)
    data.extend(add_group_by_account_number(641, r25, indent=1))

    # 9. Chi phí quản lý doanh nghiệp
    r26 = new_row(_(u"9. Chi phí quản lý doanh nghiệp"), code="26", indent=0, is_group=1)
    data.append(r26)
    data.extend(add_group_by_account_number(642, r26, indent=1))

    # 10. Lợi nhuận thuần từ HĐKD
    r30 = new_row(_(u"10. Lợi nhuận thuần từ hoạt động kinh doanh"), code="30", indent=0, is_group=0)
    for y in years:
        r30[yr_key(y)] = r20[yr_key(y)] + (r21[yr_key(y)] - r22[yr_key(y)]) - (r25[yr_key(y)] + r26[yr_key(y)])
    data.append(r30)

    # 11. Thu nhập khác
    r31 = new_row(_(u"11. Thu nhập khác"), code="31", indent=0, is_group=1)
    data.append(r31)
    data.extend(add_group_by_account_number(7, r31, indent=1))

    # 12. Chi phí khác
    r32 = new_row(_(u"12. Chi phí khác"), code="32", indent=0, is_group=1)
    data.append(r32)
    data.extend(add_group_by_account_number(8, r32, indent=1))

    # 13. Lợi nhuận khác
    r40 = new_row(_(u"13. Lợi nhuận khác"), code="40", indent=0, is_group=0)
    for y in years:
        r40[yr_key(y)] = r31[yr_key(y)] - r32[yr_key(y)]
    data.append(r40)

    # 14. Tổng lợi nhuận trước thuế
    r50 = new_row(_(u"14. Tổng lợi nhuận kế toán trước thuế"), code="50", indent=0, is_group=0)
    for y in years:
        r50[yr_key(y)] = r30[yr_key(y)] + r40[yr_key(y)]
    data.append(r50)

    # Lọc bỏ account con có tất cả giá trị = 0, nhưng giữ account cha
    filtered_data = []
    for r in data:
        if r.get("is_group"):
            filtered_data.append(r)
        else:
            has_value = any(r[yr_key(y)] != 0 for y in years)
            if has_value:
                filtered_data.append(r)

    # Tính tỷ trọng nếu bật
    if show_ratio:
        revenue_row = next((r for r in filtered_data if r.get("code") == "01"), None)
        if revenue_row:
            for r in filtered_data:
                for y in years:
                    base_val = revenue_row.get(yr_key(y), 0)
                    if base_val:
                        ratio = (r.get(yr_key(y), 0) / base_val) * 100
                    else:
                        ratio = 0
                    r[f"ratio{y}"] = ratio

    chart = get_chart_data(filters, columns, filtered_data, currency)
    return columns, filtered_data, None, chart


def get_columns(years, currency, show_ratio=False):
    columns = [
        {"label": _("Account"), "fieldname": "account", "fieldtype": "Data", "width": 320},
        {"label": _("Mã số"), "fieldname": "code", "fieldtype": "Data", "width": 70},
    ]
    for y in years:
        columns.append({
            "label": str(y),
            "fieldname": f"y{y}",
            "fieldtype": "Currency",
            "options": currency,
            "width": 130,
        })
        if show_ratio:
            columns.append({
                "label": _(f"Tỷ trọng {y} (%)"),
                "fieldname": f"ratio{y}",
                "fieldtype": "Percent",
                "width": 100,
            })
    return columns
def get_chart_data(filters, columns, data, currency):
    # Lấy nhãn từ cột (bắt đầu từ năm đầu tiên, bỏ cột tỷ trọng)
    labels = [
        c.get("label") for c in columns
        if c.get("fieldtype") in ("Currency", "Percent")
        and not c.get("label").startswith("Tỷ trọng")
    ]

    # Các dòng cần vẽ
    revenue = next((d for d in data if d.get("code") == "01"), None)   # Doanh thu bán hàng
    cogs = next((d for d in data if d.get("code") == "11"), None)      # Giá vốn
    gross_profit = next((d for d in data if d.get("code") == "20"), None)  # Lợi nhuận gộp
    profit = next((d for d in data if d.get("code") == "50"), None)    # Lợi nhuận trước thuế

    revenue_data, cogs_data, gross_profit_data, profit_data = [], [], [], []

    for c in columns:
        fn = c.get("fieldname")
        if fn and fn.startswith("y"):
            if revenue:
                revenue_data.append(revenue.get(fn))
            if cogs:
                cogs_data.append(cogs.get(fn))
            if gross_profit:
                gross_profit_data.append(gross_profit.get(fn))
            if profit:
                profit_data.append(profit.get(fn))

    datasets = []
    if revenue_data:
        datasets.append({"name": _("Doanh thu"), "values": revenue_data})
    if cogs_data:
        datasets.append({"name": _("Giá vốn"), "values": cogs_data})
    if gross_profit_data:
        datasets.append({"name": _("Lợi nhuận gộp"), "values": gross_profit_data})
    if profit_data:
        datasets.append({"name": _("Lợi nhuận trước thuế"), "values": profit_data})

    chart = {"data": {"labels": labels, "datasets": datasets}, "type": "bar"}
    chart["fieldtype"] = "Currency"
    chart["options"] = "currency"
    chart["currency"] = currency

    return chart



