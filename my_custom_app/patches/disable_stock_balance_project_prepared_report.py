import frappe


def execute():
	"""Run Stock Balance Project directly instead of using stale background results."""
	frappe.db.set_value(
		"Report",
		"Stock Balance Project",
		"prepared_report",
		0,
		update_modified=False,
	)
