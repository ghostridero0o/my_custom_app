import frappe

from erpnext.manufacturing.doctype.work_order.work_order import make_stock_entry as erpnext_make_stock_entry


@frappe.whitelist()
def make_stock_entry(work_order_id, purpose, qty=None, target_warehouse=None):
	"""Create a manufacturing Stock Entry using the Sales Order cost center."""
	stock_entry = erpnext_make_stock_entry(work_order_id, purpose, qty, target_warehouse)

	if purpose not in ("Material Transfer for Manufacture", "Manufacture"):
		return stock_entry

	sales_order = frappe.db.get_value("Work Order", work_order_id, "sales_order")
	if not sales_order:
		return stock_entry

	cost_center = frappe.db.get_value("Sales Order", sales_order, "cost_center")
	if cost_center:
		for item in stock_entry.get("items", []):
			item.cost_center = cost_center

	return stock_entry
