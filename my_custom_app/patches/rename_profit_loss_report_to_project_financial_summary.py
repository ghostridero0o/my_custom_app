import frappe


OLD_REPORT_NAME = "Profit Loss Report"
NEW_REPORT_NAME = "Project Financial Summary"


def execute():
	if not frappe.db.exists("Report", OLD_REPORT_NAME):
		return

	if frappe.db.exists("Report", NEW_REPORT_NAME):
		frappe.delete_doc("Report", OLD_REPORT_NAME, ignore_permissions=True)
		return

	frappe.rename_doc("Report", OLD_REPORT_NAME, NEW_REPORT_NAME, force=True)
