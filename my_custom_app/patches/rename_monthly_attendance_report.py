import frappe


OLD_REPORT_NAME = "Bang Cham Cong Thang"
NEW_REPORT_NAME = "Bảng Chấm Công Tháng"


def execute():
	# The database collation can treat the accented and unaccented names as
	# equivalent. Read the stored value and compare it exactly before renaming.
	stored_name = frappe.db.get_value("Report", {"name": OLD_REPORT_NAME}, "name")
	if stored_name == OLD_REPORT_NAME:
		frappe.rename_doc("Report", OLD_REPORT_NAME, NEW_REPORT_NAME, force=True)
