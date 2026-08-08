# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt


import frappe
from frappe import _
from frappe.utils import flt

import erpnext

salary_slip = frappe.qb.DocType("Salary Slip")
salary_detail = frappe.qb.DocType("Salary Detail")
salary_component = frappe.qb.DocType("Salary Component")

MAIN_SALARY_COMPONENT_PREFIXES = ("lương",)
ALLOWANCE_AND_BONUS_COMPONENT_PREFIXES = (
	"phụ cấp",
	"thưởng",
	"bảo hiểm xã hội công ty đóng",
)
SOCIAL_INSURANCE_COMPONENT_PREFIXES = ("bảo hiểm xã hội",)


def execute(filters=None):
	if not filters:
		filters = {}

	currency = None
	if filters.get("currency"):
		currency = filters.get("currency")
	company_currency = erpnext.get_company_currency(filters.get("company"))

	salary_slips = get_salary_slips(filters, company_currency)
	if not salary_slips:
		return [], []

	if filters.get("project_cost_view"):
		project_cost_map, projects = get_project_costs(salary_slips, currency, company_currency)
		columns = get_project_cost_columns(projects)
		data = []
		for ss in salary_slips:
			row = {
				"salary_slip_id": ss.name,
				"employee": ss.employee,
				"employee_name": ss.employee_name,
				"department": ss.department,
				"designation": ss.designation,
				"company": ss.company,
				"currency": currency or company_currency,
			}
			for project in projects:
				row[project["fieldname"]] = project_cost_map.get(ss.name, {}).get(project["name"], 0.0)
			data.append(row)

		return columns, data

	earning_types, ded_types = get_earning_and_deduction_types(salary_slips)
	columns = get_columns(earning_types, ded_types, filters.get("summarize_view"))

	ss_earning_map = get_salary_slip_details(salary_slips, currency, company_currency, "earnings")
	ss_ded_map = get_salary_slip_details(salary_slips, currency, company_currency, "deductions")

	doj_map = get_employee_doj_map()

	data = []
	for ss in salary_slips:
		row = {
			"salary_slip_id": ss.name,
			"employee": ss.employee,
			"employee_name": ss.employee_name,
			"data_of_joining": doj_map.get(ss.employee),
			"branch": ss.branch,
			"department": ss.department,
			"designation": ss.designation,
			"company": ss.company,
			"start_date": ss.start_date,
			"end_date": ss.end_date,
			"leave_without_pay": ss.leave_without_pay,
			"absent_days": ss.absent_days,
			"present_days": ss.present_days,
			"payment_days": ss.payment_days,
			"currency": currency or company_currency,
			"total_loan_repayment": ss.total_loan_repayment,
			"custom_da_nhan_ck": ss.custom_da_nhan_ck,
			"custom_doi_tru": ss.custom_doi_tru,
		}

		update_column_width(ss, columns)

		for e in earning_types:
			row.update({frappe.scrub(e): ss_earning_map.get(ss.name, {}).get(e)})

		for d in ded_types:
			row.update({frappe.scrub(d): ss_ded_map.get(ss.name, {}).get(d)})

		if currency == company_currency:
			row.update(
				{
					"gross_pay": flt(ss.gross_pay) * flt(ss.exchange_rate),
					"total_deduction": (flt(ss.total_deduction) + flt(ss.total_loan_repayment))
					* flt(ss.exchange_rate),
					"net_pay": flt(ss.net_pay) * flt(ss.exchange_rate),
					"custom_da_nhan_ck": flt(ss.custom_da_nhan_ck) * flt(ss.exchange_rate),
					"custom_doi_tru": flt(ss.custom_doi_tru) * flt(ss.exchange_rate),
				}
			)

		else:
			row.update(
				{
					"gross_pay": ss.gross_pay,
					"total_deduction": flt(ss.total_deduction) + flt(ss.total_loan_repayment),
					"net_pay": ss.net_pay,
					"custom_da_nhan_ck": ss.custom_da_nhan_ck,
					"custom_doi_tru": ss.custom_doi_tru,
				}
			)

		if filters.get("summarize_view"):
			social_insurance = get_component_total(
				ss_ded_map.get(ss.name, {}), SOCIAL_INSURANCE_COMPONENT_PREFIXES
			)
			row.update(
				{
					"monthly_salary": get_component_total(
						ss_earning_map.get(ss.name, {}), MAIN_SALARY_COMPONENT_PREFIXES
					),
					"allowance_and_bonus": get_component_total(
						ss_earning_map.get(ss.name, {}), ALLOWANCE_AND_BONUS_COMPONENT_PREFIXES
					),
					"social_insurance": social_insurance,
					"advance_and_deduction": flt(row["total_deduction"]) - social_insurance,
				}
			)
			if flt(row["monthly_salary"]) and flt(ss.present_days):
				row["daily_salary"] = flt(row["monthly_salary"]) / flt(ss.present_days)

		data.append(row)

	return columns, data


def get_earning_and_deduction_types(salary_slips):
	salary_component_and_type = {_("Earning"): [], _("Deduction"): []}

	for salary_component in get_salary_components(salary_slips):
		component_type = get_salary_component_type(salary_component)
		salary_component_and_type[_(component_type)].append(salary_component)

	return sorted(salary_component_and_type[_("Earning")]), sorted(salary_component_and_type[_("Deduction")])


def get_component_total(component_map, component_prefixes):
	return sum(
		flt(amount)
		for component, amount in component_map.items()
		if component.strip().casefold().startswith(component_prefixes)
	)


def get_project_costs(salary_slips, currency, company_currency):
	"""Allocate earnings to projects using the same Salary Slip percentages as Payroll Entry."""
	employee_project = frappe.qb.DocType("Employee Project")
	salary_slip_names = [ss.name for ss in salary_slips]

	project_cost_rows = (
		frappe.qb.from_(salary_slip)
		.join(salary_detail)
		.on(salary_slip.name == salary_detail.parent)
		.join(employee_project)
		.on(salary_slip.name == employee_project.parent)
		.select(
			salary_slip.name.as_("salary_slip"),
			salary_slip.exchange_rate,
			salary_detail.amount,
			employee_project.project,
			employee_project.percentage,
		)
		.where(
			(salary_slip.name.isin(salary_slip_names))
			& (salary_detail.parentfield == "earnings")
			& (employee_project.project.isnotnull())
			& (employee_project.project != "")
			& (
				(salary_detail.do_not_include_in_total == 0)
				| (
					(salary_detail.do_not_include_in_total == 1)
					& (salary_detail.do_not_include_in_accounts == 0)
				)
			)
		)
	).run(as_dict=True)

	project_cost_map = {}
	project_names = set()
	for row in project_cost_rows:
		amount = flt(row.amount) * flt(row.percentage) / 100
		if not amount:
			continue
		if currency == company_currency:
			amount *= flt(row.exchange_rate) or 1
		project_cost_map.setdefault(row.salary_slip, {}).setdefault(row.project, 0.0)
		project_cost_map[row.salary_slip][row.project] += amount
		project_names.add(row.project)

	project_labels = dict(
		frappe.get_all(
			"Project",
			filters={"name": ["in", list(project_names)]},
			fields=["name", "project_name"],
			as_list=True,
		)
	)
	projects = []
	for index, project in enumerate(
		sorted(project_names, key=lambda name: (project_labels.get(name) or name).casefold()),
		start=1,
	):
		projects.append(
			{
				"name": project,
				"label": project_labels.get(project) or project,
				"fieldname": f"project_cost_{index}",
			}
		)
	return project_cost_map, projects


def get_project_cost_columns(projects):
	columns = [
		{
			"label": _("Salary Slip ID"),
			"fieldname": "salary_slip_id",
			"fieldtype": "Link",
			"options": "Salary Slip",
			"width": 150,
		},
		{
			"label": _("Mã nhân viên"),
			"fieldname": "employee",
			"fieldtype": "Link",
			"options": "Employee",
			"width": 120,
		},
		{
			"label": _("Tên nhân viên"),
			"fieldname": "employee_name",
			"fieldtype": "Data",
			"width": 140,
		},
		{
			"label": _("Phòng ban"),
			"fieldname": "department",
			"fieldtype": "Link",
			"options": "Department",
			"width": 120,
		},
		{
			"label": _("Chức danh"),
			"fieldname": "designation",
			"fieldtype": "Link",
			"options": "Designation",
			"width": 120,
		},
		{
			"label": _("Công ty"),
			"fieldname": "company",
			"fieldtype": "Link",
			"options": "Company",
			"width": 120,
		},
	]
	for project in projects:
		columns.append(
			{
				"label": project["label"],
				"fieldname": project["fieldname"],
				"fieldtype": "Currency",
				"options": "currency",
				"width": 140,
			}
		)
	columns.append(
		{
			"label": _("Currency"),
			"fieldname": "currency",
			"fieldtype": "Data",
			"options": "Currency",
			"hidden": 1,
		}
	)
	return columns


def update_column_width(ss, columns):
	columns_by_fieldname = {column["fieldname"]: column for column in columns}
	if ss.branch is not None and "branch" in columns_by_fieldname:
		columns_by_fieldname["branch"].update({"width": 120})
	if ss.department is not None and "department" in columns_by_fieldname:
		columns_by_fieldname["department"].update({"width": 120})
	if ss.designation is not None and "designation" in columns_by_fieldname:
		columns_by_fieldname["designation"].update({"width": 120})
	if ss.leave_without_pay is not None and "leave_without_pay" in columns_by_fieldname:
		columns_by_fieldname["leave_without_pay"].update({"width": 120})


def get_columns(earning_types, ded_types, summarize_view=False):
	columns = [
		{
			"label": _("Salary Slip ID"),
			"fieldname": "salary_slip_id",
			"fieldtype": "Link",
			"options": "Salary Slip",
			"width": 150,
		},
		{
			"label": _("Mã nhân viên"),
			"fieldname": "employee",
			"fieldtype": "Link",
			"options": "Employee",
			"width": 120,
		},
		{
			"label": _("Tên nhân viên"),
			"fieldname": "employee_name",
			"fieldtype": "Data",
			"width": 140,
		},
		{
			"label": _("Date of Joining"),
			"fieldname": "data_of_joining",
			"fieldtype": "Date",
			"width": 80,
		},
		{
			"label": _("Branch"),
			"fieldname": "branch",
			"fieldtype": "Link",
			"options": "Branch",
			"width": -1,
		},
		{
			"label": _("Phòng ban"),
			"fieldname": "department",
			"fieldtype": "Link",
			"options": "Department",
			"width": -1,
		},
		{
			"label": _("Chức danh"),
			"fieldname": "designation",
			"fieldtype": "Link",
			"options": "Designation",
			"width": 120,
		},
		{
			"label": _("Công ty"),
			"fieldname": "company",
			"fieldtype": "Link",
			"options": "Company",
			"width": 120,
		},
		{
			"label": _("Start Date"),
			"fieldname": "start_date",
			"fieldtype": "Data",
			"width": 80,
		},
		{
			"label": _("End Date"),
			"fieldname": "end_date",
			"fieldtype": "Data",
			"width": 80,
		},
		{
			"label": _("Nghỉ không lương"),
			"fieldname": "leave_without_pay",
			"fieldtype": "Float",
			"width": 50,
		},
		{
			"label": _("Vắng mặt"),
			"fieldname": "absent_days",
			"fieldtype": "Float",
			"width": 50,
		},
		{
			"label": _("Payment Days"),
			"fieldname": "payment_days",
			"fieldtype": "Float",
			"width": 120,
		},
		{
			"label": _("Số ngày công"),
			"fieldname": "present_days",
			"fieldtype": "Float",
			"width": 120,
		},
	]
	if summarize_view:
		columns.insert(
			next(index for index, column in enumerate(columns) if column["fieldname"] == "present_days"),
			{
				"label": _("Lương/ngày"),
				"fieldname": "daily_salary",
				"fieldtype": "Currency",
				"options": "currency",
				"width": 120,
			},
		)
		columns.extend(
			[
				{
					"label": _("Lương tháng"),
					"fieldname": "monthly_salary",
					"fieldtype": "Currency",
					"options": "currency",
					"width": 120,
				},
				{
					"label": _("Phụ cấp + thưởng"),
					"fieldname": "allowance_and_bonus",
					"fieldtype": "Currency",
					"options": "currency",
					"width": 120,
				},
				{
					"label": _("Tổng thu nhập"),
					"fieldname": "gross_pay",
					"fieldtype": "Currency",
					"options": "currency",
					"width": 120,
				},
				{
					"label": _("Bảo hiểm xã hội"),
					"fieldname": "social_insurance",
					"fieldtype": "Currency",
					"options": "currency",
					"width": 120,
				},
				{
					"label": _("Tạm ứng + giảm trừ"),
					"fieldname": "advance_and_deduction",
					"fieldtype": "Currency",
					"options": "currency",
					"width": 120,
				},
				{
					"label": _("Tổng giảm trừ"),
					"fieldname": "total_deduction",
					"fieldtype": "Currency",
					"options": "currency",
					"width": 120,
				},
				{
					"label": _("Thực lĩnh"),
					"fieldname": "net_pay",
					"fieldtype": "Currency",
					"options": "currency",
					"width": 120,
				},
				{
					"label": _("Đã Nhận CK"),
					"fieldname": "custom_da_nhan_ck",
					"fieldtype": "Currency",
					"options": "currency",
					"width": 120,
				},
				{
					"label": _("Đối trừ"),
					"fieldname": "custom_doi_tru",
					"fieldtype": "Currency",
					"options": "currency",
					"width": 120,
				},
				{
					"label": _("Currency"),
					"fieldtype": "Data",
					"fieldname": "currency",
					"options": "Currency",
					"hidden": 1,
				},
			]
		)
		return [
			column
			for column in columns
			if column["fieldname"]
			not in {"data_of_joining", "branch", "leave_without_pay", "absent_days", "payment_days"}
		]

	for earning in earning_types:
		columns.append(
			{
				"label": earning,
				"fieldname": frappe.scrub(earning),
				"fieldtype": "Currency",
				"options": "currency",
				"width": 120,
			}
		)

	columns.append(
		{
			"label": _("Tổng thu nhập"),
			"fieldname": "gross_pay",
			"fieldtype": "Currency",
			"options": "currency",
			"width": 120,
		}
	)

	for deduction in ded_types:
		columns.append(
			{
				"label": deduction,
				"fieldname": frappe.scrub(deduction),
				"fieldtype": "Currency",
				"options": "currency",
				"width": 120,
			}
		)

	columns.extend(
		[
			{
				"label": _("Tạm ứng"),
				"fieldname": "total_loan_repayment",
				"fieldtype": "Currency",
				"options": "currency",
				"width": 120,
			},
			{
				"label": _("Tổng giảm trừ"),
				"fieldname": "total_deduction",
				"fieldtype": "Currency",
				"options": "currency",
				"width": 120,
			},
			{
				"label": _("Thực lĩnh"),
				"fieldname": "net_pay",
				"fieldtype": "Currency",
				"options": "currency",
				"width": 120,
			},
			{
				"label": _("Đã Nhận CK"),
				"fieldname": "custom_da_nhan_ck",
				"fieldtype": "Currency",
				"options": "currency",
				"width": 120,
			},
			{
				"label": _("Đối trừ"),
				"fieldname": "custom_doi_tru",
				"fieldtype": "Currency",
				"options": "currency",
				"width": 120,
			},
			{
				"label": _("Currency"),
				"fieldtype": "Data",
				"fieldname": "currency",
				"options": "Currency",
				"hidden": 1,
			},
		]
	)
	return columns


def get_salary_components(salary_slips):
	return (
		frappe.qb.from_(salary_detail)
		.where((salary_detail.amount != 0) & (salary_detail.parent.isin([d.name for d in salary_slips])))
		.select(salary_detail.salary_component)
		.distinct()
	).run(pluck=True)


def get_salary_component_type(salary_component):
	return frappe.db.get_value("Salary Component", salary_component, "type", cache=True)


def get_salary_slips(filters, company_currency):
	doc_status = {"Draft": 0, "Submitted": 1, "Cancelled": 2}

	query = frappe.qb.from_(salary_slip).select(salary_slip.star)

	if filters.get("docstatus"):
		query = query.where(salary_slip.docstatus == doc_status[filters.get("docstatus")])

	if filters.get("from_date"):
		query = query.where(salary_slip.start_date >= filters.get("from_date"))

	if filters.get("to_date"):
		query = query.where(salary_slip.end_date <= filters.get("to_date"))

	if filters.get("company"):
		query = query.where(salary_slip.company == filters.get("company"))

	if filters.get("employee"):
		query = query.where(salary_slip.employee == filters.get("employee"))

	if filters.get("currency") and filters.get("currency") != company_currency:
		query = query.where(salary_slip.currency == filters.get("currency"))

	if filters.get("department"):
		query = query.where(salary_slip.department == filters["department"])

	if filters.get("designation"):
		query = query.where(salary_slip.designation == filters["designation"])

	if filters.get("branch"):
		query = query.where(salary_slip.branch == filters["branch"])

	salary_slips = query.run(as_dict=1)

	return salary_slips or []


def get_employee_doj_map():
	employee = frappe.qb.DocType("Employee")

	result = (frappe.qb.from_(employee).select(employee.name, employee.date_of_joining)).run()

	return frappe._dict(result)


def get_salary_slip_details(salary_slips, currency, company_currency, component_type):
	salary_slips = [ss.name for ss in salary_slips]

	result = (
		frappe.qb.from_(salary_slip)
		.join(salary_detail)
		.on(salary_slip.name == salary_detail.parent)
		.where((salary_detail.parent.isin(salary_slips)) & (salary_detail.parentfield == component_type))
		.select(
			salary_detail.parent,
			salary_detail.salary_component,
			salary_detail.amount,
			salary_slip.exchange_rate,
		)
	).run(as_dict=1)

	ss_map = {}

	for d in result:
		ss_map.setdefault(d.parent, frappe._dict()).setdefault(d.salary_component, 0.0)
		if currency == company_currency:
			ss_map[d.parent][d.salary_component] += flt(d.amount) * flt(
				d.exchange_rate if d.exchange_rate else 1
			)
		else:
			ss_map[d.parent][d.salary_component] += flt(d.amount)

	return ss_map
