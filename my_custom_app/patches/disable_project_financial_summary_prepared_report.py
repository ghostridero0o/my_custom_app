import frappe


def execute():
	"""Run Project Financial Summary directly instead of using prepared results."""
	frappe.db.set_value(
		"Report",
		"Project Financial Summary",
		"prepared_report",
		0,
		update_modified=False,
	)
