import frappe
from frappe import _
from frappe.utils import flt, now_datetime


def _tree_filters(doctype, name):
    if not name:
        return {}
    doc = frappe.get_doc(doctype, name)
    doc.check_permission('read')
    return {'lft': ['>=', doc.lft], 'rgt': ['<=', doc.rgt]}


def _selected_names(value):
    if not value:
        return []
    if isinstance(value, str):
        value = frappe.parse_json(value) if value.lstrip().startswith('[') else [value]
    return list(dict.fromkeys(name for name in value if name))


def _tree_names(doctype, selections, filters=None):
    names = set()
    for selection in selections or [None]:
        query_filters = dict(filters or {})
        query_filters.update(_tree_filters(doctype, selection))
        names.update(frappe.get_list(doctype, filters=query_filters, pluck='name', limit_page_length=0))
    return sorted(names)


@frappe.whitelist()
def get_project_stock(company, project=None, item_group=None, warehouse=None, exclude_item=None, source_doctype="BOM"):
    """Current positive ledger balance, with normal user permissions applied.

    Project is taken from Stock Ledger Entry, exactly as in Stock Balance Project.
    An empty project means all projects, including unassigned movements.
    """
    if source_doctype not in ('BOM', 'Stock Entry'):
        frappe.throw(_('Unsupported source document.'))
    frappe.has_permission(source_doctype, 'read', throw=True)
    frappe.has_permission('Stock Ledger Entry', 'read', throw=True)
    if not company:
        frappe.throw(_('Please select a Company first.'))
    frappe.get_doc('Company', company).check_permission('read')
    if project:
        project_doc = frappe.get_doc('Project', project)
        project_doc.check_permission('read')
        if project_doc.company and project_doc.company != company:
            frappe.throw(_('Project must belong to the BOM company.'))

    warehouses = _tree_names('Warehouse', _selected_names(warehouse),
                             {'company': company, 'is_group': 0})
    if not warehouses:
        return []

    item_filters = {'disabled': 0, 'is_stock_item': 1, 'has_variants': 0}
    if exclude_item:
        item_filters['name'] = ['!=', exclude_item]
    selected_groups = _selected_names(item_group)
    if selected_groups:
        groups = _tree_names('Item Group', selected_groups)
        if not groups:
            return []
        item_filters['item_group'] = ['in', groups]
    items = frappe.get_list('Item', filters=item_filters,
                           fields=['name', 'item_name', 'item_group', 'stock_uom'], limit_page_length=0)
    item_map = {item.name: item for item in items}
    if not item_map:
        return []

    filters = {'company': company, 'is_cancelled': 0, 'docstatus': ['<', 2],
               'posting_datetime': ['<=', now_datetime()],
               'warehouse': ['in', warehouses], 'item_code': ['in', list(item_map)]}
    if project:
        filters['project'] = project
    balances = frappe.get_list('Stock Ledger Entry', filters=filters,
                               fields=['item_code', 'warehouse', {'SUM': 'actual_qty', 'as': 'actual_qty'}],
                               group_by='item_code, warehouse', order_by='item_code asc, warehouse asc',
                               limit_page_length=0)
    return positive_stock_rows(balances, item_map)


def positive_stock_rows(balances, item_map):
    rows = []
    for balance in balances:
        qty = flt(balance.actual_qty)
        if qty <= 0 or balance.item_code not in item_map:
            continue
        item = item_map[balance.item_code]
        rows.append({'item_code': balance.item_code, 'item_name': item.item_name,
                     'item_group': item.item_group, 'warehouse': balance.warehouse,
                     'stock_uom': item.stock_uom, 'actual_qty': qty})
    return rows
