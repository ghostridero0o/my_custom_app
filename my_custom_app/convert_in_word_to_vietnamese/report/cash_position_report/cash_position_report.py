import frappe
from frappe import _
from erpnext.accounts.utils import get_balance_on
import json

@frappe.whitelist()
def execute(filters=None):
    filters = frappe._dict(filters or {})
    columns = get_columns(filters)
    data = get_data(filters)
    
    return columns, data

def get_columns(filters):
    columns = [
        {
            "label": _("Account"),
            "fieldtype": "Data",  # Chuyển sang fieldtype "Data" thay vì "Link"
            "fieldname": "account",
            "width": 400,
        },
        {
            "label": _("Currency"),
            "fieldtype": "Link",
            "fieldname": "currency",
            "options": "Currency",
            "hidden": 0,
            "width": 100,
        },
        {
            "label": _("Balance"),
            "fieldtype": "Currency",
            "fieldname": "balance",
            "options": "currency",
            "width": 300,
        },
    ]
    return columns

def get_conditions(filters):
    conditions = {}

    # Lọc các tài khoản có account_type = "Cash" hoặc "Bank" và disabled = 0
    conditions["account_type"] = ["in", ["Cash", "Bank"]]
    conditions["disabled"] = 0  # Lọc bỏ các tài khoản có disabled = 1

    if filters.company:
        conditions["company"] = filters.company

    return conditions

def get_data(filters):
    data = []
    conditions = get_conditions(filters)

    # Lấy tất cả tài khoản có account_type = "Cash" hoặc "Bank", sắp xếp theo parent_account, name
    accounts = frappe.db.get_all(
        "Account",
        fields=["name", "account_currency", "is_group", "parent_account"],
        filters=conditions,
        order_by="parent_account, name",  # Sắp xếp theo parent_account trước, sau đó là tài khoản
    )

    # Chia các tài khoản thành 2 nhóm: nhóm 1 (is_group = 1) và nhóm 2 (is_group = 0)
    group_1 = [account for account in accounts if account['is_group'] == 1]  # Nhóm tài khoản nhóm
    group_2 = [account for account in accounts if account['is_group'] == 0]  # Nhóm tài khoản con

    # Tạo một dictionary để nhóm các tài khoản con theo parent_account
    grouped_accounts = {}
    for account in group_2:
        parent_account = account.get("parent_account")
        if parent_account not in grouped_accounts:
            grouped_accounts[parent_account] = []
        grouped_accounts[parent_account].append(account)

    # Duyệt qua tài khoản nhóm (group_1) và tài khoản con (group_2)
    total_balance_all = 0  # Tổng cộng cho tất cả các tài khoản con

    for account in group_1:
        row = {
            "account": account["name"],  # Tài khoản nhóm
            "balance": get_balance_on(account["name"], date=filters.report_date),
            "currency": account["account_currency"]
        }
        data.append(row)

        # Thêm các tài khoản con thuộc về account (parent_account)

        if account["name"] in grouped_accounts:
            for child_account in grouped_accounts[account["name"]]:
                # Thêm padding (thụt lề) cho tài khoản con sử dụng HTML
                row = {
                    "account": '<div style="padding-left: 20px;">' + child_account["name"] + '</div>',  # Thêm thụt lề cho tài khoản con
                    "balance": get_balance_on(child_account["name"], date=filters.report_date),
                    "currency": child_account["account_currency"]
                }
                data.append(row)

                # Cộng dồn số dư của các tài khoản con vào tổng số dư của nhóm
                total_balance_all += row["balance"]  # Cộng dồn vào tổng cộng tất cả các tài khoản con

        
    # Thêm dòng tổng cộng ở cuối báo cáo để tính tổng tất cả tài khoản con
    total_row_all = {
        "account": "<b>Tổng cộng</b>",  # Dòng tổng cộng cho tất cả các tài khoản con
        "balance": total_balance_all,
        "currency": "VND"  # Hoặc bạn có thể thay thế bằng đơn vị tiền tệ phù hợp
    }
    data.append(total_row_all)

    return data
