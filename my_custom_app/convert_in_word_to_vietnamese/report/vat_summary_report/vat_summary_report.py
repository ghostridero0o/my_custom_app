import frappe
from frappe.utils import getdate

def execute(filters=None):
    filters = frappe._dict(filters or {})

    if not filters.get("company") or not filters.get("date"):
        return get_columns(), []

    company = filters.get("company")
    to_date = getdate(filters.get("date"))

    columns = get_columns()
    data = []

    # DÒNG 1: VAT phải nộp đầu kỳ
    opening = frappe.db.get_all("Hoa Don Ra Vao",
        filters={
            "docstatus": 1,
            "company": company,
            "is_opening": 1,
            "opening_date": ["<=", to_date]
        },
        order_by="opening_date desc",
        limit=1,
        fields=["name", "opening_date", "vat_opening"]
    )

    if not opening:
        data.append({
            "invoice_no": "VAT phải nộp đầu kỳ",
            "vat": 0,
            "invoice_date": "",
            "posting_date": "",
            "voucher_no": "",
            "indent": 0
        })
        return columns, data

    opening_doc = opening[0]
    opening_vat = opening_doc.vat_opening or 0
    opening_date = opening_doc.opening_date
    opening_name = opening_doc.name

    data.append({
        "posting_date": "",
        "invoice_no": "VAT phải nộp đầu kỳ",
        "invoice_date": opening_date,
        "vat": opening_vat,
        "voucher_no": opening_name,
        "indent": 0
    })

    # DÒNG 2: Hóa Đơn Đầu Ra
    sales = frappe.get_all("Hoa Don Ra Vao",
        filters={
            "docstatus": 1,
            "company": company,
            "party": "Customer",
            "is_opening": 0,
            "invoice_date": ["between", [opening_date, to_date]]
        },
        fields=[
            "name", "posting_date", "invoice_date", "vat", "tax_rate", "customer_name",
            "invoice_out_no", "total", "grand_total"
        ]
    )
    sales_total = sum(row.vat or 0 for row in sales)

    data.append({
        "invoice_no": "Hóa Đơn Đầu Ra",
        "vat": sales_total,
        "indent": 0,
        "expandable": 1
    })

    for row in sales:
        data.append({
            "posting_date": row.posting_date,
            "invoice_no": row.invoice_out_no or "",
            "invoice_date": row.invoice_date,
            "vat": row.vat,
            "vat_rate": row.tax_rate,
            "total": row.total,
            "grand_total": row.grand_total,
            "partner_name": row.customer_name,
            "voucher_no": row.name,
            "indent": 1
        })

    # DÒNG 3: Hóa Đơn Đầu Vào
    purchases = frappe.get_all("Hoa Don Ra Vao",
        filters={
            "docstatus": 1,
            "company": company,
            "party": "Supplier",
            "is_opening": 0,
            "invoice_date": ["between", [opening_date, to_date]]
        },
        fields=[
            "name", "posting_date", "invoice_date", "vat", "tax_rate", "supplier_name",
            "invoice_in_no", "total", "grand_total"
        ]
    )
    purchase_total = sum(row.vat or 0 for row in purchases)

    data.append({
        "invoice_no": "Hóa Đơn Đầu Vào",
        "vat": purchase_total,
        "indent": 0,
        "expandable": 1
    })

    for row in purchases:
        data.append({
            "posting_date": row.posting_date,
            "invoice_no": row.invoice_in_no or "",
            "invoice_date": row.invoice_date,
            "vat": row.vat,
            "vat_rate": row.tax_rate,
            "total": row.total,
            "grand_total": row.grand_total,
            "partner_name": row.supplier_name,
            "voucher_no": row.name,
            "indent": 1
        })

    # DÒNG 4: VAT phải nộp cuối kỳ
    closing_vat = opening_vat + sales_total - purchase_total
    data.append({
        "invoice_no": "VAT phải nộp cuối kỳ",
        "vat": closing_vat,
        "indent": 0
    })

    return columns, data


def get_columns():
    return [
        {"label": "Posting Date", "fieldname": "posting_date", "fieldtype": "Date", "width": 120},
        {"label": "Invoice No", "fieldname": "invoice_no", "fieldtype": "Data", "width": 200},
        {"label": "Invoice Date", "fieldname": "invoice_date", "fieldtype": "Date", "width": 120},
        {"label": "VAT", "fieldname": "vat", "fieldtype": "Currency", "width": 120},
        {"label": "VAT Rate", "fieldname": "vat_rate", "fieldtype": "Float", "width": 100},
        {"label": "Total", "fieldname": "total", "fieldtype": "Currency", "width": 120},
        {"label": "Grand Total", "fieldname": "grand_total", "fieldtype": "Currency", "width": 130},
        {"label": "Tên Đối Tác", "fieldname": "partner_name", "fieldtype": "Data", "width": 150},
        {"label": "Voucher No", "fieldname": "voucher_no", "fieldtype": "Link", "options": "Hoa Don Ra Vao", "width": 170}
    ]
