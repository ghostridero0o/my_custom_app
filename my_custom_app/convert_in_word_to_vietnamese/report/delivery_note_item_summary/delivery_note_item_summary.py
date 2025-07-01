import frappe
from frappe.utils import flt

def execute(filters=None):
    view_mode = filters.get("view_mode", "By Item")
    if view_mode == "By Delivery Date":
        return get_data_by_delivery_date(filters)
    elif view_mode == "By Delivery Note":
        return get_data_by_delivery_note(filters)
    else:
        return get_data_by_item(filters)

def get_data_by_item(filters):
    columns = [
        {"label": "Item Code", "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 150},
        {"label": "Item Name", "fieldname": "item_name", "fieldtype": "Data", "width": 200},
        {"label": "Total Qty", "fieldname": "total_qty", "fieldtype": "Float", "width": 120},
        {"label": "Rate", "fieldname": "rate", "fieldtype": "Currency", "width": 100},
        {"label": "Total Amount", "fieldname": "total_amount", "fieldtype": "Currency", "width": 150},        
        
    ]

    conditions = " AND dn.docstatus = 1"
    if filters.get("company"):
        conditions += " AND dn.company = %(company)s"
    if filters.get("customer"):
        conditions += " AND dn.customer = %(customer)s"
    if filters.get("project"):
        conditions += " AND dni.project = %(project)s"

    data = frappe.db.sql(f"""
        SELECT
            dni.item_code,
            dni.item_name,
            SUM(dni.qty) AS total_qty,
            SUM(dni.amount) AS total_amount
        FROM `tabDelivery Note` dn
        JOIN `tabDelivery Note Item` dni ON dni.parent = dn.name
        WHERE 1=1 {conditions}
        GROUP BY dni.item_code
    """, filters, as_dict=1)

    for row in data:
        row["rate"] = flt(row["total_amount"]) / flt(row["total_qty"]) if row["total_qty"] else 0

    return columns, data

def get_data_by_delivery_date(filters):
    conditions = " AND dn.docstatus = 1"
    if filters.get("company"):
        conditions += " AND dn.company = %(company)s"
    if filters.get("customer"):
        conditions += " AND dn.customer = %(customer)s"
    if filters.get("project"):
        conditions += " AND dni.project = %(project)s"

    date_list = frappe.db.sql(f"""
        SELECT DISTINCT dn.posting_date
        FROM `tabDelivery Note` dn
        JOIN `tabDelivery Note Item` dni ON dni.parent = dn.name
        WHERE 1=1 {conditions}
        ORDER BY dn.posting_date DESC
    """, filters)

    date_list = [d[0].strftime('%d-%m-%Y') for d in date_list]

    columns = [
        {"label": "Item Code", "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 150},
        {"label": "Item Name", "fieldname": "item_name", "fieldtype": "Data", "width": 200},
    ] + [
        {"label": d, "fieldname": d, "fieldtype": "Float", "width": 120}
        for d in date_list
    ]

    raw_data = frappe.db.sql(f"""
        SELECT
            dni.item_code,
            dni.item_name,
            dn.posting_date,
            SUM(dni.qty) as qty
        FROM `tabDelivery Note` dn
        JOIN `tabDelivery Note Item` dni ON dni.parent = dn.name
        WHERE 1=1 {conditions}
        GROUP BY dni.item_code, dn.posting_date
    """, filters, as_dict=1)

    result_map = {}
    for row in raw_data:
        key = row.item_code
        posting_date = row.posting_date.strftime('%d-%m-%Y')
        if key not in result_map:
            result_map[key] = {
                "item_code": row.item_code,
                "item_name": row.item_name
            }
            for d in date_list:
                result_map[key][d] = 0
        result_map[key][posting_date] += row.qty

    return columns, list(result_map.values())

def get_data_by_delivery_note(filters):
    conditions = " AND dn.docstatus = 1"
    if filters.get("company"):
        conditions += " AND dn.company = %(company)s"
    if filters.get("customer"):
        conditions += " AND dn.customer = %(customer)s"
    if filters.get("project"):
        conditions += " AND dni.project = %(project)s"

    # Lấy danh sách Delivery Note theo thứ tự mới nhất
    dn_list = frappe.db.sql(f"""
        SELECT DISTINCT dn.name
        FROM `tabDelivery Note` dn
        JOIN `tabDelivery Note Item` dni ON dni.parent = dn.name
        WHERE 1=1 {conditions}
        ORDER BY dn.posting_date DESC
    """, filters)
    dn_list = [d[0] for d in dn_list]

    # Khai báo cột
    columns = [
        {"label": "Item Code", "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 150},
        {"label": "Item Name", "fieldname": "item_name", "fieldtype": "Data", "width": 200},
    ] + [
        {
            "label": dn,
            "fieldname": dn,
            "fieldtype": "HTML",  # Hiển thị link clickable
            "width": 150,
            "align": "right"
        }
        for dn in dn_list
    ]

    # Truy vấn dữ liệu số lượng theo từng Delivery Note
    raw_data = frappe.db.sql(f"""
        SELECT
            dni.item_code,
            dni.item_name,
            dn.name AS dn_name,
            SUM(dni.qty) AS qty
        FROM `tabDelivery Note` dn
        JOIN `tabDelivery Note Item` dni ON dni.parent = dn.name
        WHERE 1=1 {conditions}
        GROUP BY dni.item_code, dn.name
    """, filters, as_dict=1)

    # Dữ liệu tổng hợp theo item
    result_map = {}
    for row in raw_data:
        key = row.item_code
        dn_name = row.dn_name

        if key not in result_map:
            result_map[key] = {
                "item_code": row.item_code,
                "item_name": row.item_name
            }
            # Khởi tạo 0 cho tất cả DN
            for d in dn_list:
                result_map[key][d] = ""

        # Gán giá trị HTML link
        result_map[key][dn_name] = f"""
            <a href="/app/delivery-note/{dn_name}" target="_blank">{flt(row.qty)}</a>
        """

    return columns, list(result_map.values())

