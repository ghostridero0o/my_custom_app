import frappe
from frappe import _
from frappe.utils import cstr, flt, getdate

from erpnext.accounts.doctype.accounting_dimension.accounting_dimension import (
	get_accounting_dimensions,
	get_dimension_with_children,
)
from erpnext.accounts.report.financial_statements import get_cost_centers_with_children, get_period_list


CASH_PREFIXES = ("111", "112", "113")

ROWS = [
	{"label": "I. Lưu chuyển tiền từ hoạt động kinh doanh", "section": 1},
	{"code": "01", "label": "1. Tiền thu từ bán hàng, cung cấp dịch vụ và doanh thu khác"},
	{"code": "02", "label": "2. Tiền chi trả cho người cung cấp hàng hóa và dịch vụ", "negative": 1},
	{"code": "03", "label": "3. Tiền chi trả cho người lao động", "negative": 1},
	{"code": "04", "label": "4. Chi phí đi vay đã trả", "negative": 1},
	{"code": "05", "label": "5. Thuế thu nhập doanh nghiệp đã nộp", "negative": 1},
	{"code": "06", "label": "6. Tiền thu khác từ hoạt động kinh doanh"},
	{"code": "07", "label": "7. Tiền chi khác cho hoạt động kinh doanh", "negative": 1},
	{"code": "20", "label": "Lưu chuyển tiền thuần từ hoạt động kinh doanh", "total": ["01", "02", "03", "04", "05", "06", "07"]},
	{},
	{"label": "II. Lưu chuyển tiền từ hoạt động đầu tư", "section": 1},
	{"code": "21", "label": "1. Tiền chi để mua sắm, xây dựng TSCĐ và các tài sản dài hạn khác", "negative": 1},
	{"code": "22", "label": "2. Tiền thu từ thanh lý, nhượng bán TSCĐ và các tài sản dài hạn khác"},
	{"code": "23", "label": "3. Tiền chi cho vay, mua các công cụ nợ của đơn vị khác", "negative": 1},
	{"code": "24", "label": "4. Tiền thu hồi cho vay, bán lại các công cụ nợ của đơn vị khác"},
	{"code": "25", "label": "5. Tiền chi đầu tư góp vốn vào đơn vị khác", "negative": 1},
	{"code": "26", "label": "6. Tiền thu hồi đầu tư góp vốn vào đơn vị khác"},
	{"code": "27", "label": "7. Tiền thu lãi cho vay, cổ tức và lợi nhuận được chia"},
	{"code": "30", "label": "Lưu chuyển tiền thuần từ hoạt động đầu tư", "total": ["21", "22", "23", "24", "25", "26", "27"]},
	{},
	{"label": "III. Lưu chuyển tiền từ hoạt động tài chính", "section": 1},
	{"code": "31", "label": "1. Tiền thu từ phát hành cổ phiếu, nhận vốn góp của chủ sở hữu"},
	{"code": "32", "label": "2. Tiền trả lại vốn góp cho các chủ sở hữu, mua lại cổ phiếu đã phát hành", "negative": 1},
	{"code": "33", "label": "3. Tiền thu từ đi vay"},
	{"code": "34", "label": "4. Tiền trả nợ gốc vay", "negative": 1},
	{"code": "35", "label": "5. Tiền trả nợ gốc thuê tài chính", "negative": 1},
	{"code": "36", "label": "6. Cổ tức, lợi nhuận đã trả cho chủ sở hữu", "negative": 1},
	{"code": "40", "label": "Lưu chuyển tiền thuần từ hoạt động tài chính", "total": ["31", "32", "33", "34", "35", "36"]},
	{},
	{"code": "50", "label": "Lưu chuyển tiền thuần trong kỳ (50 = 20+30+40)", "total": ["20", "30", "40"]},
	{"code": "60", "label": "Tiền và tương đương tiền đầu kỳ", "computed": "opening"},
	{"code": "61", "label": "Ảnh hưởng của thay đổi tỷ giá hối đoái quy đổi ngoại tệ", "computed": "exchange"},
	{"code": "70", "label": "Tiền và tương đương tiền cuối kỳ (70 = 50+60+61)", "computed": "closing"},
]


def execute(filters=None):
	filters = frappe._dict(filters or {})
	validate_filters(filters)

	period_list = get_period_list(
		filters.from_fiscal_year,
		filters.to_fiscal_year,
		filters.period_start_date,
		filters.period_end_date,
		filters.filter_based_on,
		filters.periodicity,
		company=filters.company,
	)
	company_currency = frappe.get_cached_value("Company", filters.company, "default_currency")
	account_map = get_account_map(filters.company)
	cash_accounts = get_cash_accounts(filters.company, account_map)
	period_values, period_accounts = get_period_values(filters, period_list, account_map, cash_accounts)
	data = build_data(period_list, period_values, company_currency, period_accounts, cash_accounts)
	columns = get_columns(period_list)
	chart = get_chart_data(period_list, period_values, company_currency)
	report_summary = get_report_summary(period_list, period_values, company_currency)

	return columns, data, None, chart, report_summary


@frappe.whitelist()
def add_to_financial_reports_workspace():
	workspace = frappe.get_doc("Workspace", "Financial Reports")
	for link in workspace.links:
		if link.link_type == "Report" and link.link_to == "BCLC-TT-TT99-TT":
			return "exists"

	workspace.append(
		"links",
		{
			"type": "Link",
			"label": "BCLC-TT-TT99-TT",
			"link_type": "Report",
			"link_to": "BCLC-TT-TT99-TT",
			"is_query_report": 1,
			"dependencies": "GL Entry",
			"hidden": 0,
			"onboard": 0,
			"link_count": 0,
		},
	)
	workspace.save(ignore_permissions=True)
	frappe.db.commit()

	return "added"


def validate_filters(filters):
	if not filters.get("company"):
		frappe.throw(_("Company is mandatory"))


def get_columns(period_list):
	columns = [
		{
			"fieldname": "section",
			"label": _("Chỉ tiêu"),
			"fieldtype": "Data",
			"width": 430,
		},
		{
			"fieldname": "code",
			"label": _("Mã số"),
			"fieldtype": "Data",
			"width": 80,
		},
		{
			"fieldname": "explanation",
			"label": _("Thuyết minh"),
			"fieldtype": "Data",
			"width": 110,
		},
	]

	for period in period_list:
		columns.append(
			{
				"fieldname": period["key"],
				"label": period["label"],
				"fieldtype": "Currency",
				"options": "currency",
				"width": 140,
			}
		)

	if len(period_list) > 1:
		columns.append(
			{
				"fieldname": "total",
				"label": _("Tổng cộng"),
				"fieldtype": "Currency",
				"options": "currency",
				"width": 140,
			}
		)

	return columns


def get_period_values(filters, period_list, account_map, cash_accounts):
	values = {row["code"]: {period["key"]: 0 for period in period_list} for row in ROWS if row.get("code")}
	period_accounts = {
		row["code"]: {"all": set(), **{period["key"]: set() for period in period_list}}
		for row in ROWS
		if row.get("code")
	}

	for period in period_list:
		period_key = period["key"]
		cash_flow_details = get_cash_flow_details_by_code(filters, period, account_map, cash_accounts)

		for detail in cash_flow_details:
			code = detail.cash_flow_code
			values[code][period_key] = flt(values[code][period_key] + detail.cash_flow_amount)
			period_accounts[code][period_key].add(detail.account)
			period_accounts[code]["all"].add(detail.account)

		for row in ROWS:
			if row.get("total"):
				values[row["code"]][period_key] = flt(sum(values[code][period_key] for code in row["total"]))

		opening = get_cash_balance(filters, period["from_date"], cash_accounts, before_date=True)
		closing = get_cash_balance(filters, period["to_date"], cash_accounts)
		net_change = values["50"][period_key]

		values["60"][period_key] = opening
		values["70"][period_key] = closing
		values["61"][period_key] = flt(closing - opening - net_change, 2)

	for code, account_map_by_period in period_accounts.items():
		for key, accounts in account_map_by_period.items():
			period_accounts[code][key] = sorted(accounts)

	return values, period_accounts


def build_data(period_list, period_values, currency, period_accounts, cash_accounts):
	data = []
	current_section = None
	period_ranges = {
		period["key"]: {"from_date": period["from_date"], "to_date": period["to_date"]}
		for period in period_list
	}

	for row in ROWS:
		if not row:
			data.append({})
			continue

		out = {
			"section": row["label"],
			"code": row.get("code"),
			"explanation": "",
			"currency": currency,
			"indent": 0 if row.get("section") else 1,
			"from_date": period_list[0]["from_date"],
			"to_date": period_list[-1]["to_date"],
			"period_ranges": period_ranges,
		}

		if row.get("section"):
			out["is_group"] = 1
			current_section = row["label"]
		else:
			if not row.get("total") and row.get("computed") not in ("opening", "exchange", "closing"):
				out["parent_section"] = current_section
				out["accounts"] = sorted(cash_accounts)
				out["period_accounts"] = {
					period["key"]: period_accounts.get(row["code"], {}).get(period["key"], [])
					for period in period_list
				}
			total = 0
			for period in period_list:
				amount = flt(period_values[row["code"]][period["key"]])
				out[period["key"]] = amount
				total += amount
			out["total"] = total

		data.append(out)

	return data


def get_cash_flow_detail_entries(filters):
	filters = frappe._dict(filters or {})
	account_map = get_account_map(filters.company)
	cash_accounts = get_cash_accounts(filters.company, account_map)
	period = frappe._dict(
		{
			"from_date": getdate(filters.from_date),
			"to_date": getdate(filters.to_date),
		}
	)
	return get_cash_flow_details_by_code(filters, period, account_map, cash_accounts, filters.get("cash_flow_code"))


def get_cash_flow_by_code(filters, period, account_map):
	amounts = {}
	cash_accounts = get_cash_accounts(filters.company, account_map)
	for detail in get_cash_flow_details_by_code(filters, period, account_map, cash_accounts):
		code = detail.cash_flow_code
		amounts[code] = flt(amounts.get(code, 0) + detail.cash_flow_amount)

	return amounts


def get_cash_flow_details_by_code(filters, period, account_map, cash_accounts, cash_flow_code=None):
	details = []
	voucher_entries = get_cash_voucher_entries(filters, period, cash_accounts)
	account_filter = get_list_filter(filters.get("account"))

	for entries in voucher_entries.values():
		all_cash_entries = [entry for entry in entries if entry.account in cash_accounts]
		non_cash_entries = [entry for entry in entries if entry.account not in cash_accounts]

		if not non_cash_entries:
			continue

		cash_entries = all_cash_entries
		if account_filter:
			cash_entries = [entry for entry in cash_entries if entry.account in account_filter]
		net_cash_movement = flt(sum(flt(entry.debit) - flt(entry.credit) for entry in cash_entries))

		for cash_entry in cash_entries:
			cash_amount = flt(cash_entry.debit) - flt(cash_entry.credit)
			if not cash_amount:
				continue

			direction = "inflow" if cash_amount > 0 else "outflow"
			counter_entries = get_counter_entries(cash_amount, non_cash_entries)
			allocated = allocate_cash_amount(abs(cash_amount), counter_entries)

			if not allocated:
				if not non_cash_entries and not net_cash_movement:
					continue
				code = "06" if direction == "inflow" else "07"
				if not cash_flow_code or code == cash_flow_code:
					details.append(
						make_cash_flow_detail_row(
							cash_entry, None, code, direction, abs(cash_amount), account_map
						)
					)
				continue

			for counter_entry, amount in allocated:
				code = classify_cash_flow(direction, get_account_number(counter_entry.account, account_map))
				if not code:
					continue
				if cash_flow_code and code != cash_flow_code:
					continue
				details.append(
					make_cash_flow_detail_row(cash_entry, counter_entry, code, direction, amount, account_map)
				)

	return details


def make_cash_flow_detail_row(cash_entry, counter_entry, code, direction, amount, account_map):
	signed_amount = flt(amount if direction == "inflow" else -amount)
	debit = flt(amount if direction == "inflow" else 0)
	credit = flt(amount if direction == "outflow" else 0)

	row = frappe._dict(cash_entry.copy())
	row.update(
		{
			"account": cash_entry.account,
			"against": counter_entry.account if counter_entry else cash_entry.get("against"),
			"cash_flow_code": code,
			"cash_flow_amount": signed_amount,
			"debit": debit,
			"credit": credit,
			"debit_in_account_currency": debit,
			"credit_in_account_currency": credit,
			"account_currency": cash_entry.get("account_currency"),
			"remarks": cash_entry.get("remarks"),
		}
	)

	return row


def get_cash_voucher_entries(filters, period, cash_accounts):
	conditions, values = get_common_conditions(filters)
	values.update({"from_date": period["from_date"], "to_date": period["to_date"]})

	cash_accounts = list(cash_accounts)
	account_filter = get_list_filter(filters.get("account"))
	if account_filter:
		cash_accounts = [account for account in cash_accounts if account in account_filter]

	if not cash_accounts:
		return {}

	values["cash_accounts"] = cash_accounts

	voucher_refs = frappe.db.sql(
		f"""
		select distinct voucher_type, voucher_no
		from `tabGL Entry`
		where company = %(company)s
			and posting_date between %(from_date)s and %(to_date)s
			and is_cancelled = 0
			and voucher_type != 'Period Closing Voucher'
			and ifnull(is_opening, '') != 'Yes'
			and account in %(cash_accounts)s
			{conditions}
		""",
		values,
		as_dict=True,
	)

	if not voucher_refs:
		return {}

	values["voucher_nos"] = [d.voucher_no for d in voucher_refs]
	accounting_dimensions = get_accounting_dimensions()
	dimension_fields = ", ".join(accounting_dimensions) + "," if accounting_dimensions else ""
	entries = frappe.db.sql(
		f"""
		select
			name as gl_entry, posting_date, account, debit, credit,
			debit_in_account_currency, credit_in_account_currency,
			voucher_type, voucher_no, {dimension_fields}
			cost_center, project, against_voucher_type, against_voucher,
			against, party_type, party, account_currency, is_opening, creation, remarks
		from `tabGL Entry`
		where company = %(company)s
			and posting_date between %(from_date)s and %(to_date)s
			and is_cancelled = 0
			and voucher_type != 'Period Closing Voucher'
			and voucher_no in %(voucher_nos)s
		order by posting_date, voucher_type, voucher_no, name
		""",
		values,
		as_dict=True,
	)

	grouped = {}
	for entry in entries:
		grouped.setdefault((entry.voucher_type, entry.voucher_no), []).append(entry)

	return grouped


def get_common_conditions(filters):
	conditions = []
	values = {"company": filters.company}

	if filters.get("finance_book"):
		if filters.get("include_default_book_entries"):
			company_fb = frappe.get_cached_value("Company", filters.company, "default_finance_book")
			values.update({"finance_book": filters.finance_book, "company_fb": company_fb})
			conditions.append("and (finance_book in (%(finance_book)s, %(company_fb)s, '') or finance_book is null)")
		else:
			values["finance_book"] = cstr(filters.finance_book)
			conditions.append("and (finance_book in (%(finance_book)s, '') or finance_book is null)")

	if filters.get("project"):
		project = filters.project
		if isinstance(project, str):
			project = frappe.parse_json(project) if project.startswith("[") else [project]
		values["project"] = project
		conditions.append("and project in %(project)s")

	if filters.get("cost_center"):
		values["cost_center"] = get_cost_centers_with_children(filters.cost_center)
		conditions.append("and cost_center in %(cost_center)s")

	for dimension in get_accounting_dimensions(as_list=False):
		fieldname = dimension.fieldname
		if not filters.get(fieldname):
			continue

		if frappe.get_cached_value("DocType", dimension.document_type, "is_tree"):
			values[fieldname] = get_dimension_with_children(dimension.document_type, filters.get(fieldname))
			conditions.append(f"and {fieldname} in %({fieldname})s")
		else:
			values[fieldname] = filters.get(fieldname)
			conditions.append(f"and {fieldname} = %({fieldname})s")

	return "\n\t\t\t" + "\n\t\t\t".join(conditions) if conditions else "", values


def get_list_filter(value):
	if not value:
		return []

	if isinstance(value, str):
		return frappe.parse_json(value) if value.startswith("[") else [value]

	return value


def get_counter_entries(cash_amount, non_cash_entries):
	if cash_amount > 0:
		counter_entries = [entry for entry in non_cash_entries if flt(entry.credit) > flt(entry.debit)]
	else:
		counter_entries = [entry for entry in non_cash_entries if flt(entry.debit) > flt(entry.credit)]

	return counter_entries or non_cash_entries


def allocate_cash_amount(cash_amount, counter_entries):
	if not counter_entries:
		return []

	weights = [abs(flt(entry.debit) - flt(entry.credit)) for entry in counter_entries]
	total_weight = sum(weights)

	if not total_weight:
		share = flt(cash_amount / len(counter_entries))
		return [(entry, share) for entry in counter_entries]

	allocated = []
	remaining = cash_amount
	for index, entry in enumerate(counter_entries):
		if index == len(counter_entries) - 1:
			amount = remaining
		else:
			amount = flt(cash_amount * weights[index] / total_weight)
			remaining = flt(remaining - amount)
		allocated.append((entry, amount))

	return allocated


def classify_cash_flow(direction, account_number):
	if direction == "inflow":
		return classify_inflow(account_number)

	return classify_outflow(account_number)


def classify_inflow(account_number):
	if startswith_any(account_number, ("411", "419")):
		return "31"
	if startswith_any(account_number, ("341", "343")):
		return "33"
	if startswith_any(account_number, ("211", "212", "213", "217", "214", "241", "242")):
		return "22"
	if startswith_any(account_number, ("128",)):
		return "24"
	if startswith_any(account_number, ("221", "222", "228")):
		return "26"
	if startswith_any(account_number, ("515", "1388")):
		return "27"
	if startswith_any(account_number, ("131", "511", "512", "3331", "3387")):
		return "01"

	return "06"


def classify_outflow(account_number):
	if startswith_any(account_number, ("411", "419")):
		return "32"
	if startswith_any(account_number, ("341", "343")):
		return "35" if startswith_any(account_number, ("3412",)) else "34"
	if startswith_any(account_number, ("421",)):
		return "36"
	if startswith_any(account_number, ("211", "212", "213", "217", "214", "241", "242")):
		return "21"
	if startswith_any(account_number, ("128",)):
		return "23"
	if startswith_any(account_number, ("221", "222", "228")):
		return "25"
	if startswith_any(account_number, ("334",)):
		return "03"
	if startswith_any(account_number, ("335", "635")):
		return "04"
	if startswith_any(account_number, ("3334",)):
		return "05"
	if startswith_any(account_number, ("331", "133", "151", "152", "153", "154", "155", "156", "157", "158", "611", "621", "622", "623", "627")):
		return "02"

	return "07"


def get_cash_balance(filters, date, cash_accounts, before_date=False):
	conditions, values = get_common_conditions(filters)
	values["date"] = getdate(date)
	values["cash_accounts"] = list(cash_accounts)

	if not values["cash_accounts"]:
		return 0

	if before_date:
		date_condition = "(posting_date < %(date)s or (posting_date = %(date)s and ifnull(is_opening, '') = 'Yes'))"
	else:
		date_condition = "posting_date <= %(date)s"

	balance = frappe.db.sql(
		f"""
		select sum(debit) - sum(credit)
		from `tabGL Entry`
		where company = %(company)s
			and {date_condition}
			and is_cancelled = 0
			and account in %(cash_accounts)s
			{conditions}
		""",
		values,
	)[0][0]

	return flt(balance)


def get_account_map(company):
	accounts = frappe.get_all(
		"Account",
		filters={"company": company},
		fields=["name", "account_number"],
	)
	return {account.name: cstr(account.account_number).replace(".", "").replace(" ", "") for account in accounts}


def get_cash_accounts(company, account_map):
	accounts = frappe.get_all(
		"Account",
		filters={"company": company},
		fields=["name", "account_number", "is_group", "lft", "rgt"],
		order_by="lft",
	)
	cash_roots = [
		account
		for account in accounts
		if startswith_any(get_account_number(account.name, account_map), CASH_PREFIXES)
	]

	cash_accounts = set()
	for account in accounts:
		if account.is_group:
			continue

		for root in cash_roots:
			if account.lft >= root.lft and account.rgt <= root.rgt:
				cash_accounts.add(account.name)
				break

	return cash_accounts


def get_account_number(account, account_map):
	return account_map.get(account) or cstr(account).split(" - ")[0].replace(".", "").replace(" ", "")


def is_cash_account(account, account_map):
	return startswith_any(get_account_number(account, account_map), CASH_PREFIXES)


def startswith_any(value, prefixes):
	return any(cstr(value).startswith(prefix) for prefix in prefixes)


def get_report_summary(period_list, period_values, currency):
	last_period = period_list[-1]["key"]
	return [
		{"value": period_values["20"][last_period], "label": _("LC tiền thuần từ HĐKD"), "datatype": "Currency", "currency": currency},
		{"value": period_values["30"][last_period], "label": _("LC tiền thuần từ HĐĐT"), "datatype": "Currency", "currency": currency},
		{"value": period_values["40"][last_period], "label": _("LC tiền thuần từ HĐTC"), "datatype": "Currency", "currency": currency},
		{"value": period_values["70"][last_period], "label": _("Tiền cuối kỳ"), "datatype": "Currency", "currency": currency},
	]


def get_chart_data(period_list, period_values, currency):
	return {
		"data": {
			"labels": [period["label"] for period in period_list],
			"datasets": [
				{"name": _("Hoạt động kinh doanh"), "values": [period_values["20"][period["key"]] for period in period_list]},
				{"name": _("Hoạt động đầu tư"), "values": [period_values["30"][period["key"]] for period in period_list]},
				{"name": _("Hoạt động tài chính"), "values": [period_values["40"][period["key"]] for period in period_list]},
			],
		},
		"type": "bar",
		"fieldtype": "Currency",
		"currency": currency,
	}
