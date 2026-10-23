import frappe
from frappe.utils import flt


def execute(filters=None):
    filters = frappe._dict(filters or {})
    if filters.get("project") and not isinstance(filters.get("project"), list):
        filters.project = frappe.parse_json(filters.get("project"))

    columns = get_columns()
    data = []

    if filters.view_type == "Cash Flow":
        data = get_cash_flow_data(filters)
    elif filters.view_type == "Profit and Loss":
        data = get_profit_and_loss_data(filters)

    return columns, data


def get_columns():
    return [
        {"label": "Posting Date", "fieldname": "posting_date", "fieldtype": "Date", "width": 100},
        {"label": "Account", "fieldname": "account", "fieldtype": "Link", "options": "Account", "width": 180},
        {"label": "Amount", "fieldname": "amount", "fieldtype": "Currency", "width": 120},
        {"label": "Cost Center", "fieldname": "cost_center", "fieldtype": "Link", "options": "Cost Center", "width": 140},
        {"label": "Remarks", "fieldname": "remarks", "fieldtype": "Data", "width": 200},
        {"label": "Voucher Type", "fieldname": "voucher_type", "fieldtype": "Data", "width": 120},
        {"label": "Voucher Subtype", "fieldname": "voucher_subtype", "fieldtype": "Data", "width": 120},
        {"label": "Voucher No", "fieldname": "voucher_no", "fieldtype": "Dynamic Link", "options": "voucher_type", "width": 150},
        {"label": "Against Account", "fieldname": "against", "fieldtype": "Data", "width": 180},
        {"label": "Party Type", "fieldname": "party_type", "fieldtype": "Link", "options": "Party Type", "width": 120},
        {"label": "Party", "fieldname": "party", "fieldtype": "Dynamic Link", "options": "party_type", "width": 180},
    ]


def get_common_filters(filters):
    common_filters = {
        "posting_date": ["between", [filters.from_date, filters.to_date]],
        "company": filters.company,
        "is_cancelled": 0
    }

    if filters.get("finance_book"):
        common_filters["finance_book"] = filters.finance_book
    if filters.get("project"):
        common_filters["project"] = ["in", filters.project]
    if filters.get("cost_center"):
        common_filters["cost_center"] = filters.cost_center
    if filters.get("voucher_type"):
        common_filters["voucher_type"] = filters.voucher_type
    if filters.get("voucher_subtype"):
        common_filters["voucher_subtype"] = filters.voucher_subtype

    return common_filters


def get_cash_flow_data(filters):
    accounts = frappe.get_all("Account", filters={"account_type": ["in", ["Cash", "Bank"]]}, pluck="name")
    if not accounts:
        return []

    common_filters = get_common_filters(filters)
    common_filters["account"] = ["in", accounts]
    common_filters["voucher_subtype"] = ["!=", "Internal Transfer"]

    entries = frappe.get_all("GL Entry",
        filters=common_filters,
        fields=[
            "posting_date", "account", "cost_center", "remarks", "voucher_type", "voucher_subtype",
            "voucher_no", "against", "party_type", "party", "debit", "credit"
        ],
        order_by="posting_date asc"
    )

    cash_in, cash_out = [], []
    for e in entries:
        row = {
            "posting_date": e.posting_date,
            "account": e.account,
            "cost_center": e.cost_center or "",
            "remarks": e.remarks or "",
            "voucher_type": e.voucher_type,
            "voucher_subtype": e.voucher_subtype or "",
            "voucher_no": e.voucher_no,
            "against": e.against or "",
            "party_type": e.party_type or "",
            "party": e.party or "",
        }

        if flt(e.debit) > 0:
            row["amount"] = flt(e.debit)
            cash_in.append(row.copy())
            
        if flt(e.credit) > 0:
            row["amount"] = flt(e.credit)
            cash_out.append(row.copy())

    total_in = sum(r["amount"] for r in cash_in)
    total_out = sum(r["amount"] for r in cash_out)

    supplemental_out = get_invoice_cash_out(filters, accounts)
    total_supplemental_out = sum(row["amount"] for row in supplemental_out)

    # ==== Các khoản giải ngân (3411, 3412) ====
    disburse_accounts = frappe.get_all("Account", filters={"account_number": ["in", ["3411", "3412"]]}, pluck="name")
    disburse = []
    total_disburse = 0

    if disburse_accounts:
        disburse_filters = get_common_filters(filters)
        disburse_filters["account"] = ["in", disburse_accounts]

        disburse_entries = frappe.get_all("GL Entry",
            filters=disburse_filters,
            fields=[
                "posting_date", "account", "cost_center", "remarks", "voucher_type", "voucher_subtype",
                "voucher_no", "against", "party_type", "party", "debit", "credit"
            ],
            order_by="posting_date asc"
        )

        for e in disburse_entries:
            amount = flt(e.credit) - flt(e.debit)
            if amount != 0:
                row = {
                    "posting_date": e.posting_date,
                    "account": e.account,
                    "cost_center": e.cost_center or "",
                    "remarks": e.remarks or "",
                    "voucher_type": e.voucher_type,
                    "voucher_subtype": e.voucher_subtype or "",
                    "voucher_no": e.voucher_no,
                    "against": e.against or "",
                    "party_type": e.party_type or "",
                    "party": e.party or "",
                    "amount": amount
                }
                disburse.append(row)
                total_disburse += amount

    # ==== Nhân công trực tiếp (6221, against chứa 3349) ====
    nhan_cong = []
    total_nhan_cong = 0
    nc_account = frappe.get_all(
    "Account",
    filters={
        "account_number": ["in", ["6221", "6271", "6421"]],
        "is_group": 0,
        "company": filters.company
    },
    pluck="name")

    if nc_account:
        nc_filters = get_common_filters(filters)
        nc_filters["account"] = ["in", nc_account]
        nc_filters["against"] = ["like", "%3349%"]
        frappe.logger().info(nc_filters)


        nc_entries = frappe.get_all("GL Entry",
            filters=nc_filters,
            fields=[
                "posting_date", "account", "cost_center", "remarks", "voucher_type", "voucher_subtype",
                "voucher_no", "against", "party_type", "party", "debit", "credit"
            ],
            order_by="posting_date asc"
        )

        for e in nc_entries:
            amount = flt(e.debit) - flt(e.credit)
            if amount != 0:
                row = {
                    "posting_date": e.posting_date,
                    "account": e.account,
                    "cost_center": e.cost_center or "",
                    "remarks": e.remarks or "",
                    "voucher_type": e.voucher_type,
                    "voucher_subtype": e.voucher_subtype or "",
                    "voucher_no": e.voucher_no,
                    "against": e.against or "",
                    "party_type": e.party_type or "",
                    "party": e.party or "",
                    "amount": amount
                }
                nhan_cong.append(row)
                total_nhan_cong += amount

    # ==== Assemble final report ====
    data = []

    if cash_in:
        data.append({"account": "<b>Cash In</b>", "amount": total_in, "remarks": "Total"})
        data.extend(cash_in)

    if cash_out:
        data.append({"account": "<b>Cash Out</b>", "amount": total_out, "remarks": "Total"})
        data.extend(cash_out)

    if supplemental_out:
        data.append({"account": "<b>Cash Out bổ sung từ Purchase Invoice</b>",
                     "amount": total_supplemental_out, "remarks": "Phân bổ thanh toán chưa có Project"})
        data.extend(supplemental_out)

    if disburse:
        data.append({"account": "<b>Các khoản giải ngân để thanh toán</b>", "amount": total_disburse, "remarks": "Tài khoản 3411/3412"})
        data.extend(disburse)

    if nhan_cong:
        data.append({"account": "<b>Nhân công trực tiếp</b>", "amount": total_nhan_cong, "remarks": "Tài khoản 6221 / 3349"})
        data.extend(nhan_cong)

    net_cash = total_in - total_out - total_supplemental_out - total_disburse - total_nhan_cong
    data.append({"account": "<b>Net Cash Flow</b>", "amount": net_cash, "remarks": "Cash In - Cash Out - Cash Out bổ sung - Giải ngân - Nhân công"})

    return data



def get_invoice_project_shares(invoice):
    """Allocate gross settlement by absolute item net value, including unassigned items.

    Header project is the fallback for items without a project. Tax and charges
    follow the same proportions; they are not counted as additional cash.
    """
    weights = {}
    for item in invoice.get("items", []):
        project = item.get("project") or invoice.get("project")
        weights[project] = weights.get(project, 0) + abs(flt(item.get("base_net_amount")))
    total = sum(weights.values())
    if not total:
        return {invoice.project: 1} if invoice.get("project") else {}
    return {project: weight / total for project, weight in weights.items() if project}


def get_invoice_cash_out(filters, cash_accounts):
    """Supplement only unassigned cash GL rows omitted by the project filter.

    Payment Entry references supply invoice allocation, while GL credit supplies
    actual cash in company currency. Never add invoice face value to cash flow.
    Non-cash settlements and advances without invoice references stay excluded.
    """
    if not filters.get("project"):
        return []

    gl_filters = get_common_filters(filters)
    gl_filters.pop("project", None)
    gl_filters.update({
        "account": ["in", cash_accounts],
        "voucher_type": "Payment Entry",
        "voucher_subtype": ["!=", "Internal Transfer"],
        "project": ["is", "not set"],
        "credit": [">", 0],
    })
    if filters.get("voucher_type") and filters.voucher_type != "Payment Entry":
        return []

    entries = frappe.get_all("GL Entry", filters=gl_filters, fields=[
        "posting_date", "account", "cost_center", "remarks", "voucher_type",
        "voucher_subtype", "voucher_no", "against", "party_type", "party", "credit",
    ], order_by="posting_date asc, name asc")
    payments, invoices = {}, {}
    rows = []
    for entry in entries:
        if entry.voucher_no not in payments:
            payments[entry.voucher_no] = frappe.get_doc("Payment Entry", entry.voucher_no)
        payment = payments[entry.voucher_no]
        if payment.docstatus != 1 or payment.payment_type != "Pay" or payment.party_type != "Supplier":
            continue

        # Positive references share actual cash; reserve the unallocated advance.
        # Credit notes reduce settlement, rather than generating extra cash out.
        positive_total = sum(max(flt(ref.allocated_amount), 0) for ref in payment.references)
        denominator = max(positive_total + max(flt(payment.unallocated_amount), 0),
                          flt(payment.received_amount))
        if denominator <= 0:
            continue
        for ref in payment.references:
            if ref.reference_doctype != "Purchase Invoice" or flt(ref.allocated_amount) <= 0:
                continue
            if ref.reference_name not in invoices:
                invoices[ref.reference_name] = frappe.get_doc("Purchase Invoice", ref.reference_name)
            invoice = invoices[ref.reference_name]
            if invoice.docstatus != 1 or invoice.company != filters.company or invoice.get("is_return"):
                continue
            shares = get_invoice_project_shares(invoice)
            for project, share in shares.items():
                if project not in filters.project:
                    continue
                amount = flt(entry.credit) * flt(ref.allocated_amount) / denominator * share
                if amount <= 0:
                    continue
                row = dict(entry)
                row.pop("credit", None)
                row["amount"] = amount
                row["remarks"] = "Purchase Invoice: {0}; Project: {1}. {2}".format(
                    invoice.name, project, entry.remarks or "")
                rows.append(row)
    return rows


def get_profit_and_loss_data(filters):
    accounts = frappe.get_all("Account", filters={"report_type": "Profit and Loss"}, fields=["name", "root_type"])
    if not accounts:
        return []

    account_map = {a.name: a.root_type for a in accounts}
    account_names = list(account_map.keys())

    common_filters = get_common_filters(filters)
    common_filters["account"] = ["in", account_names]

    entries = frappe.get_all("GL Entry",
        filters=common_filters,
        fields=[
            "posting_date", "account", "cost_center", "remarks", "voucher_type", "voucher_subtype",
            "voucher_no", "against", "party_type", "party", "debit", "credit"
        ],
        order_by="posting_date asc"
    )

    income, expense = [], []
    for e in entries:
        root_type = account_map.get(e.account)

        if root_type == "Income":
            amount = flt(e.credit) - flt(e.debit)
        elif root_type == "Expense":
            amount = flt(e.debit) - flt(e.credit)
        else:
            continue

        if amount != 0:
            row = {
            "posting_date": e.posting_date,
            "account": e.account,
            "cost_center": e.cost_center or "",
            "remarks": e.remarks or "",
            "voucher_type": e.voucher_type,
            "voucher_subtype": e.voucher_subtype or "",
            "voucher_no": e.voucher_no,
            "against": e.against or "",
                "party_type": e.party_type or "",
                "party": e.party or "",
                "amount": amount
            }

            if root_type == "Income":
                income.append(row)
            elif root_type == "Expense":
                expense.append(row)

    total_income = sum(r["amount"] for r in income)
    total_expense = sum(r["amount"] for r in expense)

    data = []

    if income:
        data.append({"account": "<b>Doanh thu</b>", "amount": total_income, "remarks": "Total"})
        data.extend(income)

    if expense:
        data.append({"account": "<b>Chi phí</b>", "amount": total_expense, "remarks": "Total"})
        data.extend(expense)

    data.append({"account": "<b>Lợi nhuận/Lỗ</b>", "amount": total_income - total_expense, "remarks": "Doanh thu - Chi phí"})

    return data
