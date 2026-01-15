import frappe
from frappe import _


def execute(filters=None):
    filters = frappe._dict(filters or {})
    validate_filters(filters)

    columns = get_columns()
    data = get_data(filters)

    return columns, data


def validate_filters(filters):
    missing = []
    for field in ["company", "from_date", "to_date"]:
        if not filters.get(field):
            missing.append(field)

    if missing:
        frappe.throw(_("Missing required filters: {0}").format(", ".join(missing)))


def get_columns():
    return [
        {
            "label": _("Date"),
            "fieldname": "transaction_date",
            "fieldtype": "Date",
            "width": 110,
        },
        {
            "label": _("Sales Order"),
            "fieldname": "sales_order",
            "fieldtype": "Link",
            "options": "Sales Order",
            "width": 180,
        },
        {
            "label": _("Customer Name"),
            "fieldname": "customer_name",
            "fieldtype": "Data",
            "width": 180,
        },
        {
            "label": _("Project Name"),
            "fieldname": "project_name",
            "fieldtype": "Data",
            "width": 180,
        },
        {
            "label": _("Item"),
            "fieldname": "item",
            "fieldtype": "Link",
            "options": "Item",
            "width": 160,
        },
        {
            "label": _("BOMs"),
            "fieldname": "boms",
            "fieldtype": "Data",
            "width": 200,
        },
        {
            "label": _("Cost Center"),
            "fieldname": "cost_center",
            "fieldtype": "Link",
            "options": "Cost Center",
            "width": 160,
        },
    ]


def get_data(filters):
    conditions = []
    if filters.get("cost_center"):
        conditions.append("soi.cost_center = %(cost_center)s")
    if filters.get("project"):
        conditions.append("so.project = %(project)s")
    if filters.get("item"):
        conditions.append("soi.item_code = %(item)s")
    if filters.get("item_group"):
        conditions.append("item.item_group = %(item_group)s")

    condition_sql = ""
    if conditions:
        condition_sql = " AND " + " AND ".join(conditions)

    query = f"""
        SELECT
            so.transaction_date,
            so.name AS sales_order,
            so.customer_name,
            so.project,
            p.project_name,
            soi.item_code,
            soi.cost_center
        FROM `tabSales Order` so
        INNER JOIN `tabSales Order Item` soi
            ON soi.parent = so.name
            AND soi.parenttype = 'Sales Order'
        LEFT JOIN `tabProject` p ON p.name = so.project
        LEFT JOIN `tabItem` item ON item.name = soi.item_code
        WHERE so.docstatus = 1
            AND so.company = %(company)s
            AND so.transaction_date BETWEEN %(from_date)s AND %(to_date)s
            {condition_sql}
        ORDER BY so.transaction_date DESC, so.name DESC, soi.idx ASC
    """

    rows = frappe.db.sql(query, filters, as_dict=True)
    item_codes = [row.item_code for row in rows if row.item_code]
    boms_by_item = get_boms_by_item(item_codes)

    data = []
    last_sales_order = None
    for row in rows:
        project_name = row.project_name or row.project
        is_same_order = row.sales_order == last_sales_order
        data.append(
            {
                "transaction_date": None if is_same_order else row.transaction_date,
                "sales_order": None if is_same_order else row.sales_order,
                "customer_name": None if is_same_order else row.customer_name,
                "project_name": project_name,
                "item": row.item_code,
                "boms": ", ".join(boms_by_item.get(row.item_code, [])),
                "cost_center": row.cost_center,
            }
        )
        last_sales_order = row.sales_order

    return data


def get_boms_by_item(item_codes):
    if not item_codes:
        return {}

    boms = frappe.db.get_all(
        "BOM",
        fields=["name", "item", "is_default", "modified"],
        filters={
            "item": ["in", list(set(item_codes))],
            "is_active": 1,
            "docstatus": 1,
        },
        order_by="is_default desc, modified desc",
    )

    boms_by_item = {}
    for bom in boms:
        boms_by_item.setdefault(bom.item, []).append(bom.name)

    return boms_by_item
