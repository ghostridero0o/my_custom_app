import frappe
from frappe import _
from frappe.utils import flt, getdate

@frappe.whitelist()
def execute(filters=None):
    if not filters:
        filters = {}

    # Lấy giá trị mặc định cho fiscal_year và company nếu không có trong filters
    fiscal_year = filters.get("fiscal_year", get_current_fiscal_year())  # Lấy năm tài chính hiện tại
    company = filters.get("company", frappe.defaults.get_user_default("Company"))  # Lấy công ty mặc định của hệ thống
    project = filters.get("project")  # Lấy giá trị project từ filters nếu có

    # Kiểm tra nếu không có giá trị fiscal_year
    if not fiscal_year:
        frappe.throw(_("Fiscal Year is required."))  # Kiểm tra nếu không có giá trị fiscal_year

    # Kiểm tra nếu không có giá trị company
    if not company:
        frappe.throw(_("Company is required."))  # Kiểm tra nếu không có giá trị company

    # Lấy các cột cho báo cáo
    columns = get_columns()

    # Lấy danh sách các Cost Center cho công ty
    
    cost_centers = get_cost_centers(filters, company)
    
    # Lấy dữ liệu cho từng Cost Center và Account
    data = []
    for cost_center in cost_centers:
        # Lọc dữ liệu theo cost_center từ filter
        if filters.get('cost_center') and filters.get('cost_center') != cost_center:
            continue
        
        cost_center_data = get_cost_center_data(cost_center, fiscal_year, project)
        if cost_center_data:
            data.extend(cost_center_data)

    return columns, data

def get_columns():
    return [
        {
            "label": _("Cost Center"),
            "fieldtype": "Link",
            "fieldname": "cost_center",
            "options": "Cost Center",
            "width": 300,
        },
        {
            "label": _("Account"),
            "fieldname": "account",
            "fieldtype": "Link",
            "options": "Account",
            "width": 500,
        },
        {
            "label": _("Balance"),
            "fieldname": "balance",
            "fieldtype": "Currency",
            "width": 300,
        }
    ]

def get_cost_centers(filters, company):
    # Lấy danh sách các Cost Center từ hệ thống cho công ty
    return frappe.db.sql_list(
        """
        SELECT name
        FROM `tabCost Center`
        WHERE company = %s
        """, 
        company
    )

def get_cost_center_data(cost_center, fiscal_year, project=None):
    # Truy vấn và lấy dữ liệu từ GL Entry liên quan đến Cost Center với báo cáo chỉ tài khoản Profit and Loss
    query = """
        SELECT
            je.account,
            a.root_type,
            SUM(
                CASE
                    WHEN a.root_type = 'Income' THEN je.credit_in_account_currency - je.debit_in_account_currency
                    WHEN a.root_type = 'Expense' THEN je.debit_in_account_currency - je.credit_in_account_currency
                    ELSE 0
                END
            ) AS balance
        FROM
            `tabGL Entry` je
        INNER JOIN
            `tabAccount` a ON je.account = a.name
        WHERE
            je.cost_center = %s
            AND je.fiscal_year = %s
            AND je.is_cancelled = 0
            AND a.report_type = 'Profit and Loss'
            AND je.is_opening = 'No'
    """

    if project:
        query += " AND je.project = %s"

    query += """
        GROUP BY
            je.account, a.root_type
    """

    if project:
        data = frappe.db.sql(query, (cost_center, fiscal_year, project), as_dict=True)
    else:
        data = frappe.db.sql(query, (cost_center, fiscal_year), as_dict=True)

    result = []
    for row in data:
        result.append({
            "cost_center": cost_center,
            "account": row["account"],
            "balance": flt(row["balance"]),
            "root_type": row["root_type"]  # Ensure root_type is part of the result
        })

    return result

def get_current_fiscal_year():
    # Lấy năm tài chính hiện tại từ bảng `tabFiscal Year`
    current_date = getdate()  # Lấy ngày hiện tại
    fiscal_year = frappe.db.get_value(
        "Fiscal Year",
        {"year_start_date": ("<=", current_date), "year_end_date": (">=", current_date)},
        "name"
    )
    
    if not fiscal_year:
        frappe.throw(_("No fiscal year found for the current date."))  # Nếu không tìm thấy năm tài chính
    return fiscal_year
