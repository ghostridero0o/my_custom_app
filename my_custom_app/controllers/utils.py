import frappe


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
