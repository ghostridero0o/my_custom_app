import frappe
from frappe.utils import flt

def execute(filters=None):
    filters = frappe._dict(filters or {})
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
        {"label": "Remarks", "fieldname": "remarks", "fieldtype": "Data", "width": 200},
        {"label": "Voucher Type", "fieldname": "voucher_type", "fieldtype": "Data", "width": 120},
        {"label": "Voucher Subtype", "fieldname": "voucher_subtype", "fieldtype": "Data", "width": 120},
        {"label": "Voucher No", "fieldname": "voucher_no", "fieldtype": "Dynamic Link", "options": "voucher_type", "width": 150},
        {"label": "Against Account", "fieldname": "against", "fieldtype": "Data", "width": 180},
        {"label": "Party Type", "fieldname": "party_type", "fieldtype": "Link", "options": "Party Type", "width": 120},
        {"label": "Party", "fieldname": "party", "fieldtype": "Dynamic Link", "options": "party_type", "width": 180},
    ]


def get_common_filters(filters):
    """Tạo filter chung, bỏ qua các giá trị None hoặc rỗng"""
    common_filters = {
        "posting_date": ["between", [filters.from_date, filters.to_date]],
        "company": filters.company,
        "is_cancelled": 0,  # Chỉ lấy các bản ghi chưa bị hủy
    }
    
    # Chỉ thêm filter nếu có giá trị
    if filters.get("finance_book"):
        common_filters["finance_book"] = filters.finance_book
    if filters.get("project"):
        common_filters["project"] = filters.project
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

    entries = frappe.get_all("GL Entry",
        filters=common_filters,
        fields=[
            "posting_date", "account", "remarks", "voucher_type", "voucher_subtype",
            "voucher_no", "against", "party_type", "party", "debit", "credit"
        ],
        order_by="posting_date asc"
    )

    cash_in, cash_out = [], []
    for e in entries:
        # Khởi tạo row cơ bản
        row = {
            "posting_date": e.posting_date,
            "account": e.account,
            "remarks": e.remarks or "",
            "voucher_type": e.voucher_type,
            "voucher_subtype": e.voucher_subtype or "",
            "voucher_no": e.voucher_no,
            "against": e.against or "",
            "party_type": e.party_type or "",
            "party": e.party or "",
        }

        # Xử lý debit (tiền vào)
        if flt(e.debit) > 0:
            row["amount"] = flt(e.debit)
            cash_in.append(row.copy())
        
        # Xử lý credit (tiền ra)
        if flt(e.credit) > 0:
            row["amount"] = flt(e.credit)
            cash_out.append(row.copy())

    total_in = sum(r["amount"] for r in cash_in)
    total_out = sum(r["amount"] for r in cash_out)

    data = []
    
    # Thêm header và dữ liệu Cash In
    if cash_in:
        data.append({"account": "<b>Cash In</b>", "amount": total_in, "remarks": "Total"})
        data.extend(cash_in)
    
    # Thêm header và dữ liệu Cash Out
    if cash_out:
        data.append({"account": "<b>Cash Out</b>", "amount": total_out, "remarks": "Total"})
        data.extend(cash_out)
    
    # Thêm tổng kết
    data.append({"account": "<b>Net Cash Flow</b>", "amount": total_in - total_out, "remarks": "Cash In - Cash Out"})

    return data


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
            "posting_date", "account", "remarks", "voucher_type", "voucher_subtype",
            "voucher_no", "against", "party_type", "party", "debit", "credit"
        ],
        order_by="posting_date asc"
    )

    income, expense = [], []
    for e in entries:
        root_type = account_map.get(e.account)
        
        # Tính amount theo logic kế toán
        if root_type == "Income":
            amount = flt(e.credit) - flt(e.debit)
        elif root_type == "Expense":
            amount = flt(e.debit) - flt(e.credit)
        else:
            continue  # Bỏ qua nếu không phải Income hoặc Expense
        
        # Chỉ thêm vào nếu có amount
        if amount != 0:
            row = {
                "posting_date": e.posting_date,
                "account": e.account,
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
    
    # Thêm header và dữ liệu Income
    if income:
        data.append({"account": "<b>Doanh thu</b>", "amount": total_income, "remarks": "Total"})
        data.extend(income)
    
    # Thêm header và dữ liệu Expense
    if expense:
        data.append({"account": "<b>Chi phí</b>", "amount": total_expense, "remarks": "Total"})
        data.extend(expense)
    
    # Thêm tổng kết
    data.append({"account": "<b>Lợi nhuận/Lỗ</b>", "amount": total_income - total_expense, "remarks": "Doanh thu - Chi phí"})

    return data