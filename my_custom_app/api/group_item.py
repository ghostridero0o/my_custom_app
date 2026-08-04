import frappe


@frappe.whitelist()
def get_items(group_item):
	"""Return the child items configured for an Item Package."""
	if not frappe.has_permission("Item Package", "read", group_item):
		frappe.throw(frappe._("Not permitted"), frappe.PermissionError)

	doc = frappe.get_doc("Item Package", group_item)
	return [
		{
			"item_code": row.item_code,
			"item_name": row.item_name
			or frappe.get_cached_value("Item", row.item_code, "item_name"),
			"qty": row.qty,
			"description": row.description,
			"rate": row.rate,
			"uom": row.uom,
		}
		for row in doc.items
	]
