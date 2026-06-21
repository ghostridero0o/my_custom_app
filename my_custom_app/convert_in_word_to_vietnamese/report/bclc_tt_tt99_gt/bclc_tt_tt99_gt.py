import copy

import frappe
from frappe import _
from frappe.utils import cstr, flt

from erpnext.accounts.doctype.accounting_dimension.accounting_dimension import (
	get_accounting_dimensions,
	get_dimension_with_children,
)
from erpnext.accounts.report.financial_statements import (
	get_cost_centers_with_children,
	get_data,
	get_period_list,
)
from erpnext.accounts.report.profit_and_loss_statement.profit_and_loss_statement import (
	get_net_profit_loss,
)

from my_custom_app.convert_in_word_to_vietnamese.report.bclc_tt_tt99_tt.bclc_tt_tt99_tt import (
	get_account_map,
	get_account_number,
	get_cash_balance,
	get_cash_voucher_entries,
	get_period_closing_condition,
	split_csv,
	startswith_any,
)


CASH_PREFIXES = ("111", "112")
SETTINGS_DOCTYPE = "BCLC TT GT Settings"
FX_REVALUATION_VOUCHER_TYPES = ("Exchange Rate Revaluation", "Exchange Gain Or Loss")
FX_REVALUATION_KEYWORDS = (
	"exchange rate revaluation",
	"exchange gain or loss",
	"unrealized",
	"revaluation",
	"đánh giá lại",
	"danh gia lai",
	"chênh lệch tỷ giá",
	"chenh lech ty gia",
)

CF_INDIRECT_MAPPING = {
	"cash": ["111", "112"],
	"ms02_depreciation": ["6234", "6274", "6414"],
	"ms03_provision": ["352", "6426"],
	"ms04_fx_unrealized": ["413", "515", "635"],
	"ms05_investing_financial_gain_loss": ["515", "5117", "711", "7115", "715", "811", "6351"],
	"ms06_borrowing_cost": ["6352"],
	"ms07_other_adjustment": ["356"],
	"ms09_receivables": ["131", "136", "138", "1410", "1412", "244", "3389"],
	"ms10_inventory": ["150", "1501", "151", "152", "1531", "1534", "154", "1551", "1561"],
	"ms11_payables": [
		"133",
		"3311",
		"3318",
		"3341",
		"3342",
		"3348",
		"3349",
		"3351",
		"3331",
		"33311",
		"33312",
		"3335",
		"3337",
		"33381",
		"33382",
		"3339",
		"3383",
		"3388",
		"3531",
		"1411",
	],
	"ms11_exclude": ["3334", "3389", "3411", "3412", "343", "1413"],
	"ms12_prepaid": ["242"],
	"ms13_trading_securities": [],
	"ms14_interest_paid": ["6352"],
	"ms15_cit_paid": ["3334", "821"],
	"ms21_asset_purchase": [
		"2110",
		"2111",
		"2112",
		"2113",
		"2118",
		"2119",
		"2121",
		"2122",
		"2131",
		"2138",
		"2411",
		"2412",
		"2413",
		"2414",
	],
	"ms22_asset_disposal_receipt": ["211", "212", "213"],
	"ms23_lending_out": ["1283"],
	"ms24_lending_collection": ["1283"],
	"ms25_capital_investment": [],
	"ms26_capital_investment_collection": [],
	"ms27_interest_dividend_received": ["515"],
	"ms31_owner_capital_received": ["41111", "4112", "4118"],
	"ms32_owner_capital_returned": ["41111", "4112", "4118"],
	"ms33_borrowing_received": ["3411", "3412", "3431"],
	"ms34_loan_principal_paid": ["3411", "3431"],
	"ms35_finance_lease_paid": ["3412"],
	"ms36_dividend_paid": ["4211", "4212", "3388"],
}

ROWS = [
	{"label": "I. Lưu chuyển tiền từ hoạt động kinh doanh", "section": 1},
	{
		"code": "01",
		"label": "1. Lợi nhuận trước thuế",
		"computed": "profit_before_tax",
		"prefixes": ("5", "6", "7", "8"),
		"exclude_prefixes": ("821",),
	},
	{"label": "2. Điều chỉnh cho các khoản", "section": 1},
	{"code": "02", "label": "- Khấu hao TSCĐ và BĐSĐT", "computed": "depreciation", "prefixes": tuple(CF_INDIRECT_MAPPING["ms02_depreciation"]), "requires_finance_book": 1},
	{"code": "03", "label": "- Các khoản dự phòng", "computed": "balance_change", "prefixes": tuple(CF_INDIRECT_MAPPING["ms03_provision"]), "change_sign": "closing_minus_opening"},
	{"code": "04", "label": "- Lãi, lỗ chênh lệch tỷ giá hối đoái do đánh giá lại các khoản mục tiền tệ có gốc ngoại tệ", "computed": "fx_unrealized", "prefixes": tuple(CF_INDIRECT_MAPPING["ms04_fx_unrealized"])},
	{
		"code": "05",
		"label": "- Lãi, lỗ từ hoạt động đầu tư, tài chính",
		"computed": "investment_finance_gain_loss",
		"prefixes": tuple(CF_INDIRECT_MAPPING["ms05_investing_financial_gain_loss"]),
		"exclude_prefixes": ("8119",),
	},
	{"code": "06", "label": "- Chi phí đi vay", "computed": "period_activity", "prefixes": tuple(CF_INDIRECT_MAPPING["ms06_borrowing_cost"])},
	{"code": "07", "label": "- Các khoản điều chỉnh khác", "computed": "period_activity", "prefixes": tuple(CF_INDIRECT_MAPPING["ms07_other_adjustment"])},
	{"code": "08", "label": "3. Lợi nhuận từ hoạt động kinh doanh trước thay đổi vốn lưu động", "total": ["01", "02", "03", "04", "05", "06", "07"]},
	{"label": "II. Thay đổi vốn lưu động", "section": 1},
	{"code": "09", "label": "- Tăng, giảm các khoản phải thu", "computed": "balance_change", "prefixes": tuple(CF_INDIRECT_MAPPING["ms09_receivables"]), "change_sign": "opening_minus_closing"},
	{"code": "10", "label": "- Tăng, giảm hàng tồn kho", "computed": "balance_change", "prefixes": tuple(CF_INDIRECT_MAPPING["ms10_inventory"]), "change_sign": "opening_minus_closing"},
	{"code": "11", "label": "- Tăng, giảm các khoản phải trả (Không kể lãi vay phải trả, thuế thu nhập doanh nghiệp phải nộp)", "computed": "balance_change", "prefixes": tuple(CF_INDIRECT_MAPPING["ms11_payables"]), "exclude_prefixes": tuple(CF_INDIRECT_MAPPING["ms11_exclude"]), "change_sign": "closing_minus_opening"},
	{"code": "12", "label": "- Tăng, giảm chi phí trả trước", "computed": "balance_change", "prefixes": tuple(CF_INDIRECT_MAPPING["ms12_prepaid"]), "change_sign": "opening_minus_closing"},
	{"code": "13", "label": "- Tăng, giảm chứng khoán kinh doanh", "computed": "balance_change", "prefixes": tuple(CF_INDIRECT_MAPPING["ms13_trading_securities"]), "change_sign": "opening_minus_closing"},
	{"code": "14", "label": "- Chi phí đi vay đã trả", "computed": "cash_filtered_account_activity", "negative": 1, "prefixes": tuple(CF_INDIRECT_MAPPING["ms14_interest_paid"])},
	{"code": "15", "label": "- Thuế thu nhập doanh nghiệp đã nộp", "computed": "cash_flow", "direction": "outflow", "prefixes": tuple(CF_INDIRECT_MAPPING["ms15_cit_paid"])},
	{"code": "16", "label": "- Tiền thu khác từ hoạt động kinh doanh", "computed": "cash_linked_credit_activity", "prefixes": ("515", "711", "7115", "715")},
	{"code": "17", "label": "- Tiền chi khác cho hoạt động kinh doanh", "computed": "cash_linked_debit_activity", "negative": 1, "prefixes": ("6351", "811"), "exclude_prefixes": ("8119",)},
	{"code": "20", "label": "Lưu chuyển tiền thuần từ hoạt động kinh doanh", "total": ["08", "09", "10", "11", "12", "13", "14", "15", "16", "17"]},
	{},
	{"label": "III. Lưu chuyển tiền từ hoạt động đầu tư", "section": 1},
	{"code": "21", "label": "1. Tiền chi mua sắm, xây dựng TSCĐ và tài sản dài hạn", "computed": "asset_purchase_balance_change", "prefixes": tuple(CF_INDIRECT_MAPPING["ms21_asset_purchase"])},
	{"code": "22", "label": "2. Tiền thu thanh lý, nhượng bán TSCĐ", "computed": "cash_flow", "direction": "inflow", "prefixes": tuple(CF_INDIRECT_MAPPING["ms22_asset_disposal_receipt"])},
	{"code": "23", "label": "3. Tiền chi cho vay, mua công cụ nợ", "computed": "cash_flow", "direction": "outflow", "prefixes": tuple(CF_INDIRECT_MAPPING["ms23_lending_out"])},
	{"code": "24", "label": "4. Tiền thu hồi cho vay", "computed": "cash_flow", "direction": "inflow", "prefixes": tuple(CF_INDIRECT_MAPPING["ms24_lending_collection"])},
	{"code": "25", "label": "5. Tiền chi đầu tư góp vốn vào đơn vị khác", "computed": "cash_flow", "direction": "outflow", "prefixes": tuple(CF_INDIRECT_MAPPING["ms25_capital_investment"])},
	{"code": "26", "label": "6. Tiền thu hồi đầu tư góp vốn", "computed": "cash_flow", "direction": "inflow", "prefixes": tuple(CF_INDIRECT_MAPPING["ms26_capital_investment_collection"])},
	{"code": "27", "label": "7. Thu lãi cho vay, cổ tức và lợi nhuận được chia", "computed": "cash_flow", "direction": "inflow", "prefixes": tuple(CF_INDIRECT_MAPPING["ms27_interest_dividend_received"])},
	{"code": "30", "label": "Lưu chuyển tiền thuần từ hoạt động đầu tư", "total": ["21", "22", "23", "24", "25", "26", "27"]},
	{},
	{"label": "IV. Lưu chuyển tiền từ hoạt động tài chính", "section": 1},
	{"code": "31", "label": "1. Tiền thu từ nhận vốn góp", "computed": "account_movement", "movement": "credit", "prefixes": tuple(CF_INDIRECT_MAPPING["ms31_owner_capital_received"])},
	{"code": "32", "label": "2. Tiền trả lại vốn góp", "computed": "account_movement", "movement": "debit", "negative": 1, "prefixes": tuple(CF_INDIRECT_MAPPING["ms32_owner_capital_returned"])},
	{"code": "33", "label": "3. Tiền thu từ đi vay", "computed": "account_movement", "movement": "credit", "prefixes": tuple(CF_INDIRECT_MAPPING["ms33_borrowing_received"])},
	{"code": "34", "label": "4. Tiền trả nợ gốc vay", "computed": "account_movement", "movement": "debit", "negative": 1, "prefixes": tuple(CF_INDIRECT_MAPPING["ms34_loan_principal_paid"])},
	{"code": "35", "label": "5. Tiền trả nợ gốc thuê tài chính", "computed": "account_movement", "movement": "debit", "negative": 1, "prefixes": tuple(CF_INDIRECT_MAPPING["ms35_finance_lease_paid"])},
	{"code": "36", "label": "6. Cổ tức, lợi nhuận đã trả cho chủ sở hữu", "computed": "debit_activity", "negative": 1, "prefixes": tuple(CF_INDIRECT_MAPPING["ms36_dividend_paid"])},
	{"code": "40", "label": "Lưu chuyển tiền thuần từ hoạt động tài chính", "total": ["31", "32", "33", "34", "35", "36"]},
	{},
	{"label": "V. Tổng hợp cuối báo cáo", "section": 1},
	{"code": "50", "label": "Lưu chuyển tiền thuần trong kỳ", "total": ["20", "30", "40"]},
	{"code": "60", "label": "Tiền và tương đương tiền đầu kỳ", "computed": "opening", "prefixes": tuple(CF_INDIRECT_MAPPING["cash"])},
	{"code": "61", "label": "Ảnh hưởng thay đổi tỷ giá", "computed": "exchange"},
	{"code": "70", "label": "Tiền và tương đương tiền cuối kỳ", "computed": "closing"},
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
	cash_accounts = get_indirect_cash_accounts(filters.company, account_map)
	rows = get_indirect_rows()
	period_values, period_accounts = get_period_values(filters, period_list, account_map, cash_accounts, rows)
	data = build_data(period_list, period_values, company_currency, period_accounts, rows)

	return get_columns(period_list), data, None, get_chart_data(period_list, period_values, company_currency), get_report_summary(period_list, period_values, company_currency)


@frappe.whitelist()
def add_to_financial_reports_workspace():
	workspace = frappe.get_doc("Workspace", "Financial Reports")
	for link in workspace.links:
		if link.link_type == "Report" and link.link_to == "BCLC-TT-TT99-GT":
			return "exists"

	workspace.append(
		"links",
		{
			"type": "Link",
			"label": "BCLC-TT-TT99-GT",
			"link_type": "Report",
			"link_to": "BCLC-TT-TT99-GT",
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
		{"fieldname": "section", "label": _("Chỉ tiêu"), "fieldtype": "Data", "width": 430},
		{"fieldname": "code", "label": _("Mã số"), "fieldtype": "Data", "width": 80},
		{"fieldname": "explanation", "label": _("Thuyết minh"), "fieldtype": "Data", "width": 110},
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
		columns.append({"fieldname": "total", "label": _("Tổng cộng"), "fieldtype": "Currency", "options": "currency", "width": 140})
	return columns


def get_period_values(filters, period_list, account_map, cash_accounts, rows):
	values = {row["code"]: {period["key"]: 0 for period in period_list} for row in rows if row.get("code")}
	period_accounts = {
		row["code"]: {"all": set(), **{period["key"]: set() for period in period_list}}
		for row in rows
		if row.get("code")
	}

	for period in period_list:
		period_key = period["key"]
		for row in rows:
			if not row.get("code") or row.get("total"):
				continue
			amount, accounts = get_row_value(filters, period, row, account_map, cash_accounts)
			values[row["code"]][period_key] = flt(amount)
			period_accounts[row["code"]][period_key].update(accounts)
			period_accounts[row["code"]]["all"].update(accounts)

		for row in rows:
			if row.get("total"):
				values[row["code"]][period_key] = flt(sum(values[code][period_key] for code in row["total"]))
				for code in row["total"]:
					period_accounts[row["code"]][period_key].update(period_accounts.get(code, {}).get(period_key, []))
					period_accounts[row["code"]]["all"].update(period_accounts.get(code, {}).get("all", []))

		opening = get_cash_balance(filters, period["from_date"], cash_accounts, before_date=True, period_end_date=period["to_date"])
		closing = get_cash_balance(filters, period["to_date"], cash_accounts)
		net_change = values["50"][period_key]

		values["60"][period_key] = opening
		values["70"][period_key] = closing
		values["61"][period_key] = flt(closing - opening - net_change, 2)
		period_accounts["60"][period_key].update(cash_accounts)
		period_accounts["60"]["all"].update(cash_accounts)
		period_accounts["70"][period_key].update(cash_accounts)
		period_accounts["70"]["all"].update(cash_accounts)
		period_accounts["61"][period_key].update(cash_accounts)
		period_accounts["61"]["all"].update(cash_accounts)

	for code, account_map_by_period in period_accounts.items():
		for key, accounts in account_map_by_period.items():
			period_accounts[code][key] = sorted(accounts)

	return values, period_accounts


def get_row_value(filters, period, row, account_map, cash_accounts):
	method = row.get("computed")
	if method == "profit_before_tax":
		return get_profit_before_tax(filters, period, account_map, row)
	if method == "depreciation":
		return get_depreciation(filters, period, account_map, row)
	if method == "balance_change":
		return get_balance_change(filters, period, account_map, row)
	if method == "period_activity":
		return get_period_activity(filters, period, account_map, row)
	if method == "credit_activity":
		return get_credit_activity(filters, period, account_map, row)
	if method == "debit_activity":
		return get_debit_activity(filters, period, account_map, row)
	if method == "cash_linked_credit_activity":
		return get_cash_linked_credit_activity(filters, period, account_map, cash_accounts, row)
	if method == "cash_linked_debit_activity":
		return get_cash_linked_debit_activity(filters, period, account_map, cash_accounts, row)
	if method == "fx_unrealized":
		return get_fx_unrealized(filters, period, account_map, row)
	if method == "investment_finance_gain_loss":
		return get_investment_finance_gain_loss(filters, period, account_map, row)
	if method == "borrowing_cost":
		return get_borrowing_cost(filters, period, account_map, row)
	if method == "asset_purchase_balance_change":
		return get_asset_purchase_balance_change(filters, period, account_map, row)
	if method == "account_movement":
		return get_account_movement(filters, period, account_map, row)
	if method == "cash_filtered_account_activity":
		return get_cash_filtered_account_activity(filters, period, account_map, cash_accounts, row)
	if method == "cash_flow":
		return get_mapped_cash_flow(filters, period, row, account_map, cash_accounts)
	return 0, []


def build_data(period_list, period_values, currency, period_accounts, rows):
	data = []
	current_section = None
	period_ranges = {
		period["key"]: {"from_date": period["from_date"], "to_date": period["to_date"]}
		for period in period_list
	}
	for row in rows:
		if not row:
			data.append({})
			continue

		out = {
			"section": row["label"],
			"code": row.get("code"),
			"explanation": "",
			"currency": currency,
			"indent": 0 if row.get("section") else 1,
			"is_group": 1 if row.get("section") else 0,
			"from_date": period_list[0]["from_date"],
			"to_date": period_list[-1]["to_date"],
			"period_ranges": period_ranges,
		}
		if row.get("section"):
			current_section = row["label"]
		else:
			out["parent_section"] = current_section
			out["accounts"] = period_accounts.get(row.get("code"), {}).get("all", [])
			out["period_accounts"] = {
				period["key"]: period_accounts.get(row.get("code"), {}).get(period["key"], [])
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


def get_profit_before_tax(filters, period, account_map, row):
	pl_filters = copy.copy(filters)
	pl_filters.accumulated_values = 0
	income = get_data(filters.company, "Income", "Credit", [period], filters=pl_filters, accumulated_values=0, ignore_closing_entries=True)
	expense = get_data(filters.company, "Expense", "Debit", [period], filters=pl_filters, accumulated_values=0, ignore_closing_entries=True)
	net_profit_loss = get_net_profit_loss(income, expense, [period], filters.company)
	amount = flt(net_profit_loss.get(period["key"])) if net_profit_loss else 0

	excluded_accounts = get_leaf_accounts(filters.company, account_map, {"prefixes": row.get("exclude_prefixes")})
	if excluded_accounts:
		entries = get_period_sums(filters, period, excluded_accounts)
		amount = flt(amount + sum(flt(entry.debit) - flt(entry.credit) for entry in entries))

	accounts = get_profit_and_loss_accounts(filters.company, account_map, row.get("prefixes") or ())
	return amount, accounts


def get_depreciation(filters, period, account_map, row):
	if row.get("requires_finance_book") and not filters.get("finance_book"):
		return 0, []

	accounts = get_leaf_accounts(filters.company, account_map, row)
	if accounts:
		entries = get_period_sums(filters, period, accounts, strict_finance_book=True)
		return flt(sum(flt(entry.debit) - flt(entry.credit) for entry in entries)), accounts

	fallback_accounts = get_leaf_accounts(filters.company, account_map, {"prefixes": row.get("fallback_prefixes")})
	entries = get_period_sums(filters, period, fallback_accounts, strict_finance_book=True)
	return flt(sum(flt(entry.debit) - flt(entry.credit) for entry in entries)), fallback_accounts


def get_balance_change(filters, period, account_map, row):
	accounts = get_leaf_accounts(filters.company, account_map, row)
	entries = get_period_sums(filters, period, accounts)
	period_change = flt(sum(flt(entry.debit) - flt(entry.credit) for entry in entries))
	return flt(-period_change), accounts


def get_period_activity(filters, period, account_map, row):
	accounts = get_leaf_accounts(filters.company, account_map, row)
	entries = get_period_sums(filters, period, accounts)
	return flt(sum(flt(entry.debit) - flt(entry.credit) for entry in entries)), accounts


def get_credit_activity(filters, period, account_map, row):
	accounts = get_leaf_accounts(filters.company, account_map, row)
	entries = get_period_sums(filters, period, accounts)
	return flt(sum(flt(entry.credit) - flt(entry.debit) for entry in entries)), accounts


def get_debit_activity(filters, period, account_map, row):
	accounts = get_leaf_accounts(filters.company, account_map, row)
	entries = get_period_sums(filters, period, accounts)
	amount = sum(flt(entry.debit) - flt(entry.credit) for entry in entries)
	return flt(-amount if row.get("negative") else amount), accounts


def get_cash_linked_credit_activity(filters, period, account_map, cash_accounts, row):
	accounts = get_leaf_accounts(filters.company, account_map, row)
	entries = get_cash_filtered_account_activity_entries(
		filters,
		period["from_date"],
		period["to_date"],
		accounts,
		cash_accounts,
	)
	return flt(sum(flt(entry.credit) - flt(entry.debit) for entry in entries)), accounts


def get_cash_linked_debit_activity(filters, period, account_map, cash_accounts, row):
	accounts = get_leaf_accounts(filters.company, account_map, row)
	entries = get_cash_filtered_account_activity_entries(
		filters,
		period["from_date"],
		period["to_date"],
		accounts,
		cash_accounts,
	)
	amount = sum(flt(entry.debit) - flt(entry.credit) for entry in entries)
	return flt(-amount if row.get("negative") else amount), accounts


def get_fx_unrealized(filters, period, account_map, row):
	accounts = get_leaf_accounts(filters.company, account_map, row)
	entries = get_fx_unrealized_entries(filters, period["from_date"], period["to_date"], accounts, account_map)
	return flt(sum(flt(entry.debit) - flt(entry.credit) for entry in entries)), accounts


def get_investment_finance_gain_loss(filters, period, account_map, row):
	accounts = get_leaf_accounts(filters.company, account_map, row)
	if not accounts:
		return 0, []

	account_roots = {
		account.name: account.root_type
		for account in frappe.get_all("Account", filters={"name": ("in", accounts)}, fields=["name", "root_type"])
	}
	entries = get_period_sums(filters, period, accounts)
	net_gain = 0
	for entry in entries:
		root_type = account_roots.get(entry.account)
		if root_type == "Income":
			net_gain += flt(entry.credit) - flt(entry.debit)
		elif root_type == "Expense":
			net_gain -= flt(entry.debit) - flt(entry.credit)

	return flt(-net_gain), accounts

def get_borrowing_cost(filters, period, account_map, row):
	accounts = get_leaf_accounts(filters.company, account_map, row, prefer_keywords=True)
	entries = get_period_sums(filters, period, accounts)
	return flt(sum(flt(entry.debit) - flt(entry.credit) for entry in entries)), accounts


def get_asset_purchase_balance_change(filters, period, account_map, row):
	accounts = get_leaf_accounts(filters.company, account_map, row)
	entries = get_period_sums(filters, period, accounts)
	asset_change = flt(sum(flt(entry.debit) - flt(entry.credit) for entry in entries))
	return flt(-max(asset_change, 0)), accounts


def get_account_movement(filters, period, account_map, row):
	accounts = get_leaf_accounts(filters.company, account_map, row)
	entries = get_account_movement_entries(
		filters,
		period["from_date"],
		period["to_date"],
		accounts,
		row.get("movement"),
	)
	if row.get("movement") == "credit":
		amount = sum(max(flt(entry.credit) - flt(entry.debit), 0) for entry in entries)
	else:
		amount = sum(max(flt(entry.debit) - flt(entry.credit), 0) for entry in entries)

	return flt(-amount if row.get("negative") else amount), accounts


def get_cash_filtered_account_activity(filters, period, account_map, cash_accounts, row):
	accounts = get_leaf_accounts(filters.company, account_map, row)
	entries = get_cash_filtered_account_activity_entries(
		filters,
		period["from_date"],
		period["to_date"],
		accounts,
		cash_accounts,
	)
	amount = sum(flt(entry.debit) - flt(entry.credit) for entry in entries)
	return flt(-amount if row.get("negative") else amount), accounts


def get_bclc_gt_detail_entries(filters):
	account_map = get_account_map(filters.company)
	row = next((row for row in get_indirect_rows() if row.get("code") == filters.get("bclc_gt_code")), None)
	if row and row.get("computed") == "fx_unrealized":
		accounts = get_leaf_accounts(filters.company, account_map, row)
		filter_accounts = get_list_filter(filters.get("account"))
		if filter_accounts:
			accounts = [account for account in accounts if account in filter_accounts]
		return get_fx_unrealized_entries(filters, filters.from_date, filters.to_date, accounts, account_map)

	if row and row.get("computed") == "cash_filtered_account_activity":
		accounts = get_leaf_accounts(filters.company, account_map, row)
		filter_accounts = get_list_filter(filters.get("account"))
		if filter_accounts:
			accounts = [account for account in accounts if account in filter_accounts]
		cash_accounts = get_indirect_cash_accounts(filters.company, account_map)
		return get_cash_filtered_account_activity_entries(filters, filters.from_date, filters.to_date, accounts, cash_accounts)

	if row and row.get("computed") in ("cash_linked_credit_activity", "cash_linked_debit_activity"):
		accounts = get_leaf_accounts(filters.company, account_map, row)
		filter_accounts = get_list_filter(filters.get("account"))
		if filter_accounts:
			accounts = [account for account in accounts if account in filter_accounts]
		cash_accounts = get_indirect_cash_accounts(filters.company, account_map)
		return get_cash_filtered_account_activity_entries(filters, filters.from_date, filters.to_date, accounts, cash_accounts)

	if row and row.get("computed") == "cash_flow":
		accounts = get_leaf_accounts(filters.company, account_map, row)
		filter_accounts = get_list_filter(filters.get("account"))
		if filter_accounts:
			accounts = [account for account in accounts if account in filter_accounts]
		cash_accounts = get_indirect_cash_accounts(filters.company, account_map)
		period = {"from_date": filters.from_date, "to_date": filters.to_date}
		return get_cash_flow_detail_entries(filters, period, row, cash_accounts, accounts)

	if not row or row.get("computed") != "account_movement":
		return []

	accounts = get_leaf_accounts(filters.company, account_map, row)
	filter_accounts = get_list_filter(filters.get("account"))
	if filter_accounts:
		accounts = [account for account in accounts if account in filter_accounts]
	if not accounts:
		return []

	return get_account_movement_entries(filters, filters.from_date, filters.to_date, accounts, row.get("movement"))


def get_cash_flow_detail_entries(filters, period, row, cash_accounts, counter_accounts):
	if not cash_accounts or not counter_accounts:
		return []

	entries_by_voucher = get_cash_counter_entries(filters, period, cash_accounts, counter_accounts)
	detail_entries = []
	for entries in entries_by_voucher.values():
		amount = get_cash_flow_amount_for_voucher(entries, row.get("direction"), cash_accounts, counter_accounts)
		if not amount:
			continue

		if row.get("direction") == "inflow":
			detail_entries.extend(
				entry
				for entry in entries
				if entry.account in counter_accounts and flt(entry.credit) > flt(entry.debit)
			)
		elif row.get("direction") == "outflow":
			detail_entries.extend(
				entry
				for entry in entries
				if entry.account in counter_accounts and flt(entry.debit) > flt(entry.credit)
			)

	return detail_entries


def get_cash_filtered_account_activity_entries(filters, from_date, to_date, accounts, cash_accounts):
	if not accounts or not cash_accounts:
		return []

	conditions, values = get_common_conditions(filters)
	values.update(
		{
			"from_date": from_date,
			"to_date": to_date,
			"accounts": accounts,
			"cash_accounts": list(cash_accounts),
		}
	)
	voucher_refs = frappe.db.sql(
		f"""
		select distinct voucher_type, voucher_no
		from `tabGL Entry`
		where company = %(company)s
			and posting_date between %(from_date)s and %(to_date)s
			and is_cancelled = 0
			{get_period_closing_condition(filters)}
			and ifnull(is_opening, '') != 'Yes'
			and account in %(cash_accounts)s
			{conditions}
		""",
		values,
		as_dict=True,
	)
	if not voucher_refs:
		return []

	values["voucher_pairs"] = [(d.voucher_type, d.voucher_no) for d in voucher_refs]
	accounting_dimensions = get_accounting_dimensions()
	dimension_fields = ", ".join(accounting_dimensions) + "," if accounting_dimensions else ""
	return frappe.db.sql(
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
			{get_period_closing_condition(filters)}
			and ifnull(is_opening, '') != 'Yes'
			and account in %(accounts)s
			and (voucher_type, voucher_no) in %(voucher_pairs)s
			{conditions}
		order by posting_date, voucher_type, voucher_no, name
		""",
		values,
		as_dict=True,
	)


def get_fx_unrealized_entries(filters, from_date, to_date, accounts, account_map):
	if not accounts:
		return []

	fx_equity_accounts = [
		account
		for account in accounts
		if startswith_any(get_account_number(account, account_map), ("413",))
	]
	conditions, values = get_common_conditions(filters)
	values.update(
		{
			"from_date": from_date,
			"to_date": to_date,
			"accounts": accounts,
			"fx_equity_accounts": fx_equity_accounts or ["__no_413_accounts__"],
			"fx_voucher_types": FX_REVALUATION_VOUCHER_TYPES,
		}
	)
	keyword_conditions = []
	for index, keyword in enumerate(FX_REVALUATION_KEYWORDS):
		key = f"fx_keyword_{index}"
		values[key] = f"%{keyword}%"
		keyword_conditions.append(f"lower(concat_ws(' ', remarks, against, voucher_no)) like %({key})s")

	accounting_dimensions = get_accounting_dimensions()
	dimension_fields = ", ".join(accounting_dimensions) + "," if accounting_dimensions else ""
	return frappe.db.sql(
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
			{get_period_closing_condition(filters)}
			and ifnull(is_opening, '') != 'Yes'
			and account in %(accounts)s
			and (
				account in %(fx_equity_accounts)s
				or voucher_type in %(fx_voucher_types)s
				or voucher_subtype in %(fx_voucher_types)s
				or {" or ".join(keyword_conditions)}
			)
			{conditions}
		order by posting_date, voucher_type, voucher_no, name
		""",
		values,
		as_dict=True,
	)


def get_account_movement_entries(filters, from_date, to_date, accounts, movement):
	if not accounts:
		return []

	conditions, values = get_common_conditions(filters)
	values.update({"from_date": from_date, "to_date": to_date, "accounts": accounts})
	movement_condition = "and credit > debit" if movement == "credit" else "and debit > credit"
	accounting_dimensions = get_accounting_dimensions()
	dimension_fields = ", ".join(accounting_dimensions) + "," if accounting_dimensions else ""

	return frappe.db.sql(
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
			{get_period_closing_condition(filters)}
			and ifnull(is_opening, '') != 'Yes'
			and account in %(accounts)s
			{movement_condition}
			{conditions}
		order by posting_date, voucher_type, voucher_no, name
		""",
		values,
		as_dict=True,
	)


def get_list_filter(value):
	if not value:
		return []
	if isinstance(value, str):
		return frappe.parse_json(value) if value.startswith("[") else [value]
	return value


def get_mapped_cash_flow(filters, period, row, account_map, cash_accounts):
	counter_accounts = get_leaf_accounts(filters.company, account_map, row)
	if not counter_accounts:
		return 0, []

	entries_by_voucher = get_cash_counter_entries(filters, period, cash_accounts, counter_accounts)
	amount = 0
	for entries in entries_by_voucher.values():
		amount += get_cash_flow_amount_for_voucher(entries, row.get("direction"), cash_accounts, counter_accounts)

	return flt(amount), counter_accounts


def get_cash_flow_amount_for_voucher(entries, direction, cash_accounts, counter_accounts):
	cash_movement = sum(flt(entry.debit) - flt(entry.credit) for entry in entries if entry.account in cash_accounts)
	counter_debit = sum(max(flt(entry.debit) - flt(entry.credit), 0) for entry in entries if entry.account in counter_accounts)
	counter_credit = sum(max(flt(entry.credit) - flt(entry.debit), 0) for entry in entries if entry.account in counter_accounts)

	if direction == "inflow":
		return flt(min(max(cash_movement, 0), counter_credit))
	if direction == "outflow":
		return flt(-min(max(-cash_movement, 0), counter_debit))
	return 0


def get_cash_counter_entries(filters, period, cash_accounts, counter_accounts):
	cash_filters = copy.copy(filters)
	cash_filters.account = None
	voucher_entries = get_cash_voucher_entries(cash_filters, period, cash_accounts)
	if not voucher_entries:
		return {}

	return {
		voucher: entries
		for voucher, entries in voucher_entries.items()
		if any(entry.account in counter_accounts for entry in entries)
	}


def get_indirect_rows():
	custom_rules = get_custom_gt_mapping_rules()
	if not custom_rules:
		return ROWS

	rules_by_code = {}
	for rule in custom_rules:
		rules_by_code.setdefault(rule.code, []).append(rule)

	rows = []
	for row in ROWS:
		if not row or not row.get("code") or row.get("code") not in rules_by_code:
			rows.append(row)
			continue

		primary_rule = rules_by_code[row["code"]][0]
		merged = dict(row)
		fixed_row_codes = ("04", "06", "14", "16", "17", "21", "31", "32", "33", "34", "35", "36")
		merged["computed"] = row.get("computed") if row["code"] in fixed_row_codes else primary_rule.computed or row.get("computed")
		merged["direction"] = primary_rule.direction or row.get("direction")
		merged["change_sign"] = primary_rule.change_sign or row.get("change_sign")
		if row["code"] in fixed_row_codes:
			merged["accounts"] = row.get("accounts") or ()
			merged["prefixes"] = row.get("prefixes") or ()
			merged["exclude_prefixes"] = row.get("exclude_prefixes") or ()
			merged["account_types"] = row.get("account_types") or ()
			merged["root_types"] = row.get("root_types") or ()
			merged["name_keywords"] = row.get("name_keywords") or ()
			merged["exclude_name_keywords"] = row.get("exclude_name_keywords") or ()
		else:
			merged["accounts"] = tuple(rule.account for rule in rules_by_code[row["code"]] if rule.account)
			merged["prefixes"] = tuple(prefix for rule in rules_by_code[row["code"]] for prefix in rule.prefixes)
			merged["exclude_prefixes"] = tuple(prefix for rule in rules_by_code[row["code"]] for prefix in rule.exclude_prefixes)
			merged["account_types"] = tuple(account_type for rule in rules_by_code[row["code"]] for account_type in rule.account_types)
			merged["root_types"] = tuple(root_type for rule in rules_by_code[row["code"]] for root_type in rule.root_types)
			merged["name_keywords"] = tuple(keyword for rule in rules_by_code[row["code"]] for keyword in rule.name_keywords)
			merged["exclude_name_keywords"] = tuple(keyword for rule in rules_by_code[row["code"]] for keyword in rule.exclude_name_keywords)
			apply_current_default_for_legacy_gt_rule(row, merged)
		rows.append(merged)

	return rows


def apply_current_default_for_legacy_gt_rule(default_row, merged_row):
	legacy_prefixes = {
		"16": ("138", "3388", "3531", "711", "715"),
		"17": ("138", "3388", "3531", "811", "8119"),
	}
	code = default_row.get("code")
	if code not in legacy_prefixes:
		return

	if set(merged_row.get("prefixes") or ()) != set(legacy_prefixes[code]):
		return

	merged_row["prefixes"] = default_row.get("prefixes") or ()
	merged_row["exclude_prefixes"] = default_row.get("exclude_prefixes") or ()


def get_custom_gt_mapping_rules():
	if not is_bclc_gt_settings_available():
		return []

	settings = frappe.get_single(SETTINGS_DOCTYPE)
	if not settings.enabled or not settings.enable_custom_mapping:
		return []

	rules = []
	for row in settings.account_rules:
		if not row.enabled:
			continue

		rules.append(
			frappe._dict(
				{
					"code": row.cash_flow_code,
					"computed": get_computed_method(row.calculation_method),
					"direction": "inflow" if row.direction == "Inflow" else "outflow" if row.direction == "Outflow" else None,
					"change_sign": get_change_sign(row.change_sign),
					"account": row.account,
					"prefixes": tuple(split_csv(row.account_prefix)),
					"exclude_prefixes": tuple(split_csv(row.exclude_account_prefix)),
					"account_types": tuple(split_csv(row.account_type)),
					"root_types": tuple(split_csv(row.root_type)),
					"name_keywords": tuple(split_csv(row.name_keywords)),
					"exclude_name_keywords": tuple(split_csv(row.exclude_name_keywords)),
					"priority": row.priority or 100,
				}
			)
		)

	return sorted([rule for rule in rules if rule.code], key=lambda rule: rule.priority)


def get_computed_method(method):
	return {
		"Profit Before Tax": "profit_before_tax",
		"Depreciation": "depreciation",
		"Balance Change": "balance_change",
		"Period Activity": "period_activity",
		"Credit Activity": "credit_activity",
		"Debit Activity": "debit_activity",
		"FX Unrealized": "fx_unrealized",
		"Investment/Finance Gain Loss": "investment_finance_gain_loss",
		"Borrowing Cost": "borrowing_cost",
		"Account Movement": "account_movement",
		"Cash Filtered Account Activity": "cash_filtered_account_activity",
		"Cash Flow": "cash_flow",
	}.get(method)


def get_change_sign(change_sign):
	return {
		"Debit - Credit": "closing_minus_opening",
		"Closing - Opening": "closing_minus_opening",
		"Credit - Debit": "opening_minus_closing",
		"Opening - Closing": "opening_minus_closing",
	}.get(change_sign)


def get_indirect_cash_accounts(company, account_map):
	accounts = frappe.get_all(
		"Account",
		filters={"company": company, "disabled": 0},
		fields=["name", "account_number", "is_group", "lft", "rgt"],
		order_by="lft",
	)
	custom_cash_accounts = get_custom_indirect_cash_accounts(company, accounts, account_map)
	if custom_cash_accounts:
		return custom_cash_accounts

	return {
		account.name
		for account in accounts
		if not account.is_group and startswith_any(get_account_number(account.name, account_map), CASH_PREFIXES)
	}


def get_custom_indirect_cash_accounts(company, accounts, account_map):
	if not is_bclc_gt_settings_available():
		return set()

	settings = frappe.get_single(SETTINGS_DOCTYPE)
	if not settings.enabled:
		return set()

	configured_rows = [
		row
		for row in settings.cash_accounts
		if row.enabled and (not row.company or row.company == company) and (row.account or row.account_prefix)
	]
	if not configured_rows:
		return set()

	accounts_by_name = {account.name: account for account in accounts}
	cash_accounts = set()

	for row in configured_rows:
		if row.account:
			account = accounts_by_name.get(row.account)
			if not account:
				continue
			if account.is_group:
				cash_accounts.update(
					account.name
					for account in accounts
					if not account.is_group and account.lft >= accounts_by_name[row.account].lft and account.rgt <= accounts_by_name[row.account].rgt
				)
			else:
				cash_accounts.add(account.name)

		for prefix in split_csv(row.account_prefix):
			for account in accounts:
				if not account.is_group and startswith_any(get_account_number(account.name, account_map), (prefix,)):
					cash_accounts.add(account.name)

	return cash_accounts


def get_leaf_accounts(company, account_map, row, prefer_keywords=False):
	accounts = frappe.get_all(
		"Account",
		filters={"company": company, "is_group": 0, "disabled": 0},
		fields=["name", "account_number", "account_name", "account_type", "root_type", "report_type"],
		order_by="lft",
	)
	configured_accounts = set(row.get("accounts") or ())
	prefixes = tuple(row.get("prefixes") or ())
	exclude_prefixes = tuple(row.get("exclude_prefixes") or ())
	account_types = tuple(row.get("account_types") or ())
	root_types = tuple(row.get("root_types") or ())
	name_keywords = tuple(row.get("name_keywords") or ())
	exclude_name_keywords = tuple(row.get("exclude_name_keywords") or ())

	matched = []
	for account in accounts:
		account_number = get_account_number(account.name, account_map)
		if is_matching_account(
			account,
			account_number,
			configured_accounts,
			prefixes,
			exclude_prefixes,
			account_types,
			root_types,
			name_keywords,
			exclude_name_keywords,
		):
			matched.append(account.name)

	if prefer_keywords and name_keywords:
		keyword_accounts = [
			account.name
			for account in accounts
			if is_matching_account(
				account,
				get_account_number(account.name, account_map),
				configured_accounts,
				prefixes,
				exclude_prefixes,
				account_types,
				root_types,
				name_keywords,
				exclude_name_keywords,
			)
		]
		if keyword_accounts:
			return keyword_accounts

	return matched


def is_matching_account(account, account_number, configured_accounts, prefixes, exclude_prefixes, account_types, root_types, name_keywords, exclude_name_keywords):
	if configured_accounts or prefixes:
		matches_identity = account.name in configured_accounts or startswith_any(account_number, prefixes)
		if not matches_identity:
			return False
	if not configured_accounts and not prefixes and not account_types and not root_types and not name_keywords:
		return False
	if exclude_prefixes and startswith_any(account_number, exclude_prefixes):
		return False
	if account_types and account.account_type not in account_types:
		return False
	if root_types and account.root_type not in root_types:
		return False
	if name_keywords and not has_name_keyword(account, name_keywords):
		return False
	if exclude_name_keywords and has_name_keyword(account, exclude_name_keywords):
		return False
	return True


def has_name_keyword(account, keywords):
	account_text = " ".join(
		cstr(part).lower()
		for part in [account.name, account.account_name, account.report_type]
		if part
	)
	return any(cstr(keyword).lower() in account_text for keyword in keywords)


def is_bclc_gt_settings_available():
	try:
		return frappe.db.exists("DocType", SETTINGS_DOCTYPE)
	except Exception:
		return False


def get_profit_and_loss_accounts(company, account_map, prefixes):
	accounts = frappe.get_all(
		"Account",
		filters={"company": company, "is_group": 0, "disabled": 0, "report_type": "Profit and Loss"},
		fields=["name"],
		order_by="lft",
	)
	return [
		account.name
		for account in accounts
		if startswith_any(get_account_number(account.name, account_map), prefixes)
	]


def get_period_sums(filters, period, accounts, strict_finance_book=False):
	if not accounts:
		return []

	conditions, values = get_common_conditions(filters, strict_finance_book=strict_finance_book)
	values.update({"from_date": period["from_date"], "to_date": period["to_date"], "accounts": accounts})
	return frappe.db.sql(
		f"""
		select account, sum(debit) as debit, sum(credit) as credit
		from `tabGL Entry`
		where company = %(company)s
			and posting_date between %(from_date)s and %(to_date)s
			and is_cancelled = 0
			{get_period_closing_condition(filters)}
			and ifnull(is_opening, '') != 'Yes'
			and account in %(accounts)s
			{conditions}
		group by account
		""",
		values,
		as_dict=True,
	)


def get_common_conditions(filters, strict_finance_book=False):
	conditions = []
	values = {"company": filters.company}

	if strict_finance_book and filters.get("finance_book"):
		values["finance_book"] = cstr(filters.finance_book)
		conditions.append("and finance_book = %(finance_book)s")
	elif filters.get("finance_book"):
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
