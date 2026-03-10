# File: custom_app/custom_app/report/custom_profit_and_loss/custom_profit_and_loss.py
# -*- coding: utf-8 -*-

import copy

import frappe
from frappe import _
from erpnext.accounts.report.financial_statements import get_period_list


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
    accumulated_values = frappe.utils.cint(filters.get("accumulated_values"))
    include_default_book_entries = frappe.utils.cint(filters.get("include_default_book_entries", 1))
    show_ratio = frappe.utils.cint(filters.get("show_ratio"))

    periodicity = filters.get("periodicity") or "Yearly"
    selected_view = filters.get("selected_view") or "Report"

    if not from_fy or not to_fy:
        frappe.throw(_("From Fiscal Year and To Fiscal Year are mandatory"))

    period_list = get_period_list(
        from_fy,
        to_fy,
        None,
        None,
        "Fiscal Year",
        periodicity,
        accumulated_values=accumulated_values,
        company=company,
    )

    if not period_list:
        frappe.throw(_("No periods found for the selected filters"))

    report_from_date = period_list[0].from_date
    report_to_date = period_list[-1].to_date

    currency = frappe.get_cached_value("Company", company, "default_currency")
    columns = get_columns(period_list, currency, show_ratio)

    def period_key(p):
        return p.key

    def new_row(
        label,
        code=None,
        indent=0,
        is_group=1,
        account=None,
        account_number=None,
        parent_account=None,
        is_account=0,
        quote_label=False,
    ):
        display_label = f"'{label}'" if quote_label else label
        row = {
            "account": account or display_label,
            "code": code,
            "indent": indent,
            "is_group": is_group,
            "account_name": display_label,
            "account_number": account_number,
            "parent_account": parent_account,
            "from_date": report_from_date,
            "to_date": report_to_date,
            "is_account": is_account,
        }
        for p in period_list:
            row[period_key(p)] = 0.0
        return row

    def sum_into(target, source):
        for p in period_list:
            target[period_key(p)] += source.get(period_key(p), 0.0)

    def normalize_multiselect(value):
        if not value:
            return []
        if isinstance(value, str):
            return [v.strip() for v in value.split(",") if v.strip()]
        if isinstance(value, (list, tuple, set)):
            return [v for v in value if v]
        return [value]

    def gl_amounts_for_account(acc_name):
        root_type, report_type, acc_number = frappe.db.get_value(
            "Account", {"name": acc_name, "company": company}, ["root_type", "report_type", "account_number"], as_dict=False
        )
        credit_nature = root_type in ("Income",)
        out = {period_key(p): 0.0 for p in period_list}
        projects = normalize_multiselect(filters.get("project"))
        cost_centers = normalize_multiselect(filters.get("cost_center"))
        for p in period_list:
            from_date = p.from_date
            to_date = p.to_date

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

            if projects:
                conditions += " AND project IN %(projects)s"
                params["projects"] = tuple(projects)

            if cost_centers:
                conditions += " AND cost_center IN %(cost_centers)s"
                params["cost_centers"] = tuple(cost_centers)

            fb = filters.get("finance_book")

            if fb:
                if include_default_book_entries:
                    # include default (empty) entries along with selected finance book
                    conditions += " AND (finance_book = %(finance_book)s OR finance_book IS NULL OR finance_book = '')"
                else:
                    conditions += " AND finance_book = %(finance_book)s"
                params["finance_book"] = fb
            else:
                # no finance book selected: only default book entries
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
            out[period_key(p)] = val
        return out

    def format_account_label(account_number, account_name, fallback):
        if account_number:
            if account_name:
                return f"{account_number} - {account_name}"
            return str(account_number)
        return account_name or fallback

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
            label = format_account_label(ch.account_number, ch.account_name, ch.name)
            r = new_row(
                label=label,
                indent=indent,
                is_group=1 if ch.is_group else 0,
                account=ch.name,
                account_number=ch.account_number,
                parent_account=ch.parent_account,
                is_account=1,
            )

            if ch.is_group:
                # build subtree first and sum children into group
                sub_rows = build_account_tree(ch.name, indent=indent + 1)
                for sr in sub_rows:
                    sum_into(r, sr)
                leaf_accounts = [
                    sr.get("account")
                    for sr in sub_rows
                    if sr.get("is_account") and not sr.get("is_group")
                ]
                if leaf_accounts:
                    r["accounts"] = list(dict.fromkeys(leaf_accounts))
                rows.append(r)
                rows.extend(sub_rows)
            else:
                vals = gl_amounts_for_account(ch.name)
                for p in period_list:
                    r[period_key(p)] = vals[period_key(p)]
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
        leaf_accounts = [
            r.get("account")
            for r in rows
            if r.get("is_account") and not r.get("is_group")
        ]
        if leaf_accounts:
            parent_row["accounts"] = list(dict.fromkeys(leaf_accounts))
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
    r10 = new_row(_(u"3. Doanh thu thuần về bán hàng và cung cấp dịch vụ"), code="10", indent=0, is_group=0, quote_label=True)
    for p in period_list:
        r10[period_key(p)] = r01[period_key(p)] - r02[period_key(p)]
    data.append(r10)

    # 4. Giá vốn hàng bán (group root is account_number = 632)
    r11 = new_row(_(u"4. Giá vốn hàng bán"), code="11", indent=0, is_group=1)
    data.append(r11)
    data.extend(add_group_by_account_number(632, r11, indent=1))

    # 5. Lợi nhuận gộp
    r20 = new_row(_(u"5. Lợi nhuận gộp về bán hàng và cung cấp dịch vụ"), code="20", indent=0, is_group=0, quote_label=True)
    for p in period_list:
        r20[period_key(p)] = r10[period_key(p)] - r11[period_key(p)]
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
    r30 = new_row(_(u"10. Lợi nhuận thuần từ hoạt động kinh doanh"), code="30", indent=0, is_group=0, quote_label=True)
    for p in period_list:
        r30[period_key(p)] = r20[period_key(p)] + (r21[period_key(p)] - r22[period_key(p)]) - (r25[period_key(p)] + r26[period_key(p)])
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
    r40 = new_row(_(u"13. Lợi nhuận khác"), code="40", indent=0, is_group=0, quote_label=True)
    for p in period_list:
        r40[period_key(p)] = r31[period_key(p)] - r32[period_key(p)]
    data.append(r40)

    # 14. Tổng lợi nhuận trước thuế
    r50 = new_row(_(u"14. Tổng lợi nhuận kế toán trước thuế"), code="50", indent=0, is_group=0, quote_label=True)
    for p in period_list:
        r50[period_key(p)] = r30[period_key(p)] + r40[period_key(p)]
    data.append(r50)

    # Lọc bỏ account con có tất cả giá trị = 0, nhưng giữ account cha
    filtered_data = []
    for r in data:
        if r.get("is_group"):
            filtered_data.append(r)
        else:
            has_value = any(r[period_key(p)] != 0 for p in period_list)
            if has_value:
                filtered_data.append(r)

    if accumulated_values:
        for r in filtered_data:
            running = 0.0
            for p in period_list:
                running += r.get(period_key(p), 0.0) or 0.0
                r[period_key(p)] = running

    # Tính tỷ trọng nếu bật
    if show_ratio:
        revenue_row = next((r for r in filtered_data if r.get("code") == "01"), None)
        if revenue_row:
            for r in filtered_data:
                for p in period_list:
                    base_val = revenue_row.get(period_key(p), 0)
                    if base_val:
                        ratio = (r.get(period_key(p), 0) / base_val) * 100
                    else:
                        ratio = 0
                    r[f"ratio_{period_key(p)}"] = ratio

    if selected_view == "Growth":
        apply_growth_view(filtered_data, period_list)
    elif selected_view == "Margin":
        apply_margin_view(filtered_data, period_list)

    chart = get_chart_data(filters, columns, filtered_data, currency, accumulated_values, period_list)
    report_summary, primitive_summary = get_report_summary(period_list, filtered_data, currency, accumulated_values)
    return columns, filtered_data, None, chart, report_summary, primitive_summary


def get_columns(period_list, currency, show_ratio=False):
    columns = [
        {"label": _("Account"), "fieldname": "account", "fieldtype": "Link", "options": "Account", "width": 320},
        {"label": _("Mã số"), "fieldname": "code", "fieldtype": "Data", "width": 70},
    ]
    for p in period_list:
        columns.append({
            "label": p.label,
            "fieldname": p.key,
            "fieldtype": "Currency",
            "options": currency,
            "width": 130,
        })
        if show_ratio:
            columns.append({
                "label": _(f"Tỷ trọng {p.label} (%)"),
                "fieldname": f"ratio_{p.key}",
                "fieldtype": "Percent",
                "width": 100,
            })
    return columns


def apply_growth_view(data, period_list):
    if not data or not period_list:
        return

    keys = [p.key for p in period_list]
    data_copy = copy.deepcopy(data)

    for row_idx, row in enumerate(data_copy):
        for idx, key in enumerate(keys):
            current_val = row.get(key)
            if current_val is None:
                data[row_idx][key] = None
                continue

            if idx == 0:
                data[row_idx][key] = None
                continue

            prev_val = row.get(keys[idx - 1])
            growth = 0
            if prev_val == 0 and current_val > 0:
                growth = 100
            elif prev_val:
                growth = (current_val - prev_val) / prev_val * 100

            data[row_idx][key] = round(growth, 2)


def apply_margin_view(data, period_list):
    if not data or not period_list:
        return

    base_row = next((r for r in data if r.get("code") == "01"), None)
    if not base_row:
        return

    keys = [p.key for p in period_list]
    data_copy = copy.deepcopy(data)
    base_copy = copy.deepcopy(base_row)

    for row_idx, row in enumerate(data_copy):
        for key in keys:
            base_val = base_copy.get(key)
            curr_val = row.get(key)

            if curr_val is None or not base_val or base_val <= 0:
                data[row_idx][key] = None
                continue

            data[row_idx][key] = round((curr_val / base_val) * 100, 2)


def get_chart_data(filters, columns, data, currency, accumulated_values=False, period_list=None):
    # Lấy nhãn theo period_list (bỏ qua cột tỷ trọng)
    labels = [p.label for p in period_list] if period_list else []

    # Các dòng cần vẽ
    revenue = next((d for d in data if d.get("code") == "01"), None)   # Doanh thu bán hàng
    cogs = next((d for d in data if d.get("code") == "11"), None)      # Giá vốn
    gross_profit = next((d for d in data if d.get("code") == "20"), None)  # Lợi nhuận gộp
    profit = next((d for d in data if d.get("code") == "50"), None)    # Lợi nhuận trước thuế

    revenue_data, cogs_data, gross_profit_data, profit_data = [], [], [], []

    if period_list:
        for p in period_list:
            key = p.key
            if revenue:
                revenue_data.append(revenue.get(key))
            if cogs:
                cogs_data.append(cogs.get(key))
            if gross_profit:
                gross_profit_data.append(gross_profit.get(key))
            if profit:
                profit_data.append(profit.get(key))

    datasets = []
    if revenue_data:
        datasets.append({"name": _("Doanh thu"), "values": revenue_data})
    if cogs_data:
        datasets.append({"name": _("Giá vốn"), "values": cogs_data})
    if gross_profit_data:
        datasets.append({"name": _("Lợi nhuận gộp"), "values": gross_profit_data})
    if profit_data:
        datasets.append({"name": _("Lợi nhuận trước thuế"), "values": profit_data})

    chart = {"data": {"labels": labels, "datasets": datasets}}
    chart["type"] = "line" if accumulated_values else "bar"
    chart["fieldtype"] = "Currency"
    chart["options"] = "currency"
    chart["currency"] = currency

    return chart


def get_report_summary(period_list, data, currency, accumulated_values=False):
    data_by_code = {d.get("code"): d for d in data if d.get("code")}
    r01 = data_by_code.get("01")  # Doanh thu bán hàng
    r02 = data_by_code.get("02")  # Các khoản giảm trừ
    r11 = data_by_code.get("11")  # Giá vốn
    r21 = data_by_code.get("21")  # Doanh thu hoạt động tài chính
    r22 = data_by_code.get("22")  # Chi phí tài chính
    r25 = data_by_code.get("25")  # Chi phí bán hàng
    r26 = data_by_code.get("26")  # Chi phí quản lý doanh nghiệp
    r31 = data_by_code.get("31")  # Thu nhập khác
    r32 = data_by_code.get("32")  # Chi phí khác
    r50 = data_by_code.get("50")  # Tổng lợi nhuận trước thuế

    def get_val(row, key):
        if not row:
            return 0.0
        return row.get(key, 0.0) or 0.0

    def calc_for_period(key):
        total_income = (
            get_val(r01, key)
            - get_val(r02, key)
            + get_val(r21, key)
            + get_val(r31, key)
        )
        total_expense = (
            get_val(r11, key)
            + get_val(r22, key)
            + get_val(r25, key)
            + get_val(r26, key)
            + get_val(r32, key)
        )
        net_profit = get_val(r50, key) if r50 else (total_income - total_expense)
        return total_income, total_expense, net_profit

    if not period_list:
        return None, None

    if accumulated_values:
        total_income, total_expense, net_profit = calc_for_period(period_list[-1].key)
    else:
        total_income = total_expense = net_profit = 0.0
        for p in period_list:
            ti, te, np = calc_for_period(p.key)
            total_income += ti
            total_expense += te
            net_profit += np

    report_summary = [
        {"value": total_income, "label": _("Total Income"), "datatype": "Currency", "currency": currency},
        {"type": "separator", "value": "-"},
        {"value": total_expense, "label": _("Total Expense"), "datatype": "Currency", "currency": currency},
        {"type": "separator", "value": "=", "color": "blue"},
        {
            "value": net_profit,
            "indicator": "Green" if net_profit > 0 else "Red",
            "label": _("Net Profit"),
            "datatype": "Currency",
            "currency": currency,
        },
    ]

    return report_summary, net_profit
