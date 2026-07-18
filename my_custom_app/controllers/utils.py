import frappe
from erpnext.accounts.report.financial_statements import sort_accounts


@frappe.whitelist()
def get_children(doctype, parent, company, is_root=False):
	from erpnext.accounts.report.financial_statements import sort_accounts

	parent_fieldname = "parent_" + frappe.scrub(doctype)
	fields = ["name as value", "is_group as expandable", "disabled"]
	filters = [["docstatus", "<", 2], ["disabled", "=", 0]]

	filters.append([f'ifnull(`{parent_fieldname}`,"")', "=", "" if is_root else parent])

	if is_root:
		fields += ["root_type", "report_type", "account_currency"] if doctype == "Account" else []
		filters.append(["company", "=", company])

	else:
		fields += ["root_type", "account_currency"] if doctype == "Account" else []
		fields += [parent_fieldname + " as parent"]

	acc = frappe.get_list(doctype, fields=fields, filters=filters)

	if doctype == "Account":
		sort_accounts(acc, is_root, key="value")

	return acc


@frappe.whitelist()
def get_additional_salary_components(employee):
	deduction_components = frappe.get_all(
		"Salary Component",
		filters={"type": "Deduction"},
		pluck="name",
		limit=500,
	)

	if not employee:
		return {
			"components": list(dict.fromkeys(filter(None, deduction_components))),
			"has_assignment": False,
		}

	assignments = frappe.get_all(
		"Salary Structure Assignment",
		filters={
			"employee": employee,
			"docstatus": 1,
		},
		fields=["salary_structure"],
		order_by="from_date desc",
		limit=1,
	)

	if not assignments:
		return {
			"components": list(dict.fromkeys(filter(None, deduction_components))),
			"has_assignment": False,
		}

	structure_components = frappe.get_all(
		"Salary Detail",
		filters={
			"parenttype": "Salary Structure",
			"parentfield": "earnings",
			"parent": assignments[0].salary_structure,
		},
		pluck="salary_component",
	)

	combined = list(dict.fromkeys(filter(None, [*deduction_components, *structure_components])))

	return {
		"components": combined,
		"has_assignment": True,
	}
