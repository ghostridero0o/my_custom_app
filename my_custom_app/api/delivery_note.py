import frappe
from frappe import _
from frappe.utils import flt


def _get_delivery_note_and_sales_order(delivery_note, sales_order):
	dn = frappe.get_doc("Delivery Note", delivery_note)
	so = frappe.get_doc("Sales Order", sales_order)

	if dn.docstatus != 1 or dn.is_return:
		frappe.throw(_("Only submitted, non-return Delivery Notes can be linked."))
	if so.docstatus != 1 or so.status in {"Closed", "Cancelled"}:
		frappe.throw(_("Sales Order must be submitted and open."))
	if dn.company != so.company or dn.customer != so.customer:
		frappe.throw(_("Delivery Note and Sales Order must have the same Company and Customer."))

	return dn, so


def _get_matching_rows(delivery_note, sales_order):
	dn, so = _get_delivery_note_and_sales_order(delivery_note, sales_order)

	available_qty = {
		row.name: flt(row.qty) - flt(row.delivered_qty)
		for row in so.items
		if not row.delivered_by_supplier
	}
	so_rows_by_item = {}
	for row in so.items:
		if row.delivered_by_supplier:
			continue
		so_rows_by_item.setdefault((row.item_code, row.uom), []).append(row)

	matches = []
	for row in dn.items:
		if row.against_sales_order or row.so_detail:
			matches.append(
				frappe._dict(
					{
						"delivery_note_item": row.name,
						"item_code": row.item_code,
						"uom": row.uom,
						"qty": row.qty,
						"sales_order": row.against_sales_order,
						"sales_order_item": row.so_detail,
						"status": _("Linked"),
						"is_linked": True,
						"can_link": False,
					}
				)
			)
			continue

		candidates = so_rows_by_item.get((row.item_code, row.uom), [])
		match = next((candidate for candidate in candidates if available_qty[candidate.name] >= flt(row.qty)), None)
		status = _("Matched")
		if not candidates:
			status = _("No matching Sales Order item")
		elif not match:
			status = _("Insufficient quantity remaining")

		if match:
			available_qty[match.name] -= flt(row.qty)

		matches.append(
			frappe._dict(
				{
					"delivery_note_item": row.name,
					"item_code": row.item_code,
					"uom": row.uom,
					"qty": row.qty,
					"sales_order": so.name if match else None,
					"sales_order_item": match.name if match else None,
					"status": status,
					"is_linked": False,
					"can_link": bool(match),
				}
			)
		)

	return dn, so, matches


@frappe.whitelist()
def get_sales_order_link_preview(delivery_note, sales_order):
	frappe.has_permission("Delivery Note", "read", delivery_note, throw=True)
	frappe.has_permission("Sales Order", "read", sales_order, throw=True)

	_, _, matches = _get_matching_rows(delivery_note, sales_order)
	linkable_count = sum(1 for row in matches if row.can_link)
	linked_count = sum(1 for row in matches if row.is_linked)
	unmatched_count = len(matches) - linkable_count - linked_count
	return {
		"rows": matches,
		"can_link": linkable_count > 0,
		"linkable_count": linkable_count,
		"linked_count": linked_count,
		"unmatched_count": unmatched_count,
	}


@frappe.whitelist()
def link_submitted_delivery_note_to_sales_order(delivery_note, sales_order):
	dn, so, matches = _get_matching_rows(delivery_note, sales_order)
	frappe.has_permission("Delivery Note", "submit", dn.name, throw=True)
	frappe.has_permission("Sales Order", "submit", so.name, throw=True)

	linkable_rows = [row for row in matches if row.can_link]
	if not linkable_rows:
		frappe.throw(_("There are no matched, unlinked Delivery Note items to link."))

	for row in linkable_rows:
		frappe.db.set_value(
			"Delivery Note Item",
			row.delivery_note_item,
			{"against_sales_order": so.name, "so_detail": row.sales_order_item},
			update_modified=False,
		)

	dn.reload()
	dn.update_prevdoc_status()
	dn.update_billing_status()
	frappe.db.commit()

	return {"linked_count": len(linkable_rows)}
