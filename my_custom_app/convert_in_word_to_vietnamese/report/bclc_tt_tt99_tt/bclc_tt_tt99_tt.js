frappe.query_reports["BCLC-TT-TT99-TT"] = $.extend({}, erpnext.financial_statements, {
	tree: false,
	name_field: "section",
	parent_field: null,
	formatter: function (value, row, column, data, default_formatter, filter) {
		value = default_formatter(value, row, column, data);

		if (data && data.is_group) {
			value = $(`<span>${value}</span>`).css("font-weight", "bold").wrap("<p></p>").parent().html();
		}

		if (!is_bclc_drillable(data, column)) {
			return value;
		}

		const fieldname = column.fieldname;
		const period = get_bclc_period(data, fieldname);
		const label = value || "";
		const route_options = get_bclc_gl_route_options(data, period);
		const encoded_options = encodeURIComponent(JSON.stringify(route_options));

		return `<a href="#" onclick="open_bclc_general_ledger('${encoded_options}'); return false;">${label}</a>`;
	},
});

erpnext.utils.add_dimensions("BCLC-TT-TT99-TT", 10);

frappe.query_reports["BCLC-TT-TT99-TT"]["filters"].splice(8, 1);

frappe.query_reports["BCLC-TT-TT99-TT"]["filters"].push({
	fieldname: "include_default_book_entries",
	label: __("Include Default FB Entries"),
	fieldtype: "Check",
	default: 1,
});

frappe.query_reports["BCLC-TT-TT99-TT"]["filters"].push({
	fieldname: "include_period_closing_voucher",
	label: __("Include Period Closing Voucher"),
	fieldtype: "Check",
	default: 0,
});

const BCLC_DRILLDOWN_CODES = new Set([
	"01",
	"02",
	"03",
	"04",
	"05",
	"06",
	"07",
	"21",
	"22",
	"23",
	"24",
	"25",
	"26",
	"27",
	"31",
	"32",
	"33",
	"34",
	"35",
	"36",
	"80",
]);

function is_bclc_drillable(data, column) {
	if (!data || !BCLC_DRILLDOWN_CODES.has(data.code)) {
		return false;
	}

	if (column.fieldname === "section" || column.fieldname === "total") {
		return true;
	}

	return Boolean(data.period_ranges && data.period_ranges[column.fieldname]);
}

function get_bclc_period(data, fieldname) {
	if (data.period_ranges && data.period_ranges[fieldname]) {
		return data.period_ranges[fieldname];
	}

	return {
		from_date: data.from_date,
		to_date: data.to_date,
	};
}

function get_bclc_gl_route_options(data, period) {
	const report = frappe.query_report;
	const route_options = {
		company: report.get_filter_value("company"),
		finance_book: report.get_filter_value("finance_book"),
		from_date: period.from_date,
		to_date: period.to_date,
		cash_flow_code: data.code,
		categorize_by: "Categorize by Voucher (Consolidated)",
		include_dimensions: 1,
		include_default_book_entries: report.get_filter_value("include_default_book_entries") ? 1 : 0,
		include_period_closing_voucher: report.get_filter_value("include_period_closing_voucher") ? 1 : 0,
		show_remarks: 1,
	};
	if (data.code !== "80") {
		route_options.account = get_bclc_accounts(data, period);
	}

	for (const filter of report.filters || []) {
		const fieldname = filter.df && filter.df.fieldname;
		if (!fieldname || fieldname in route_options) {
			continue;
		}

		const value = report.get_filter_value(fieldname);
		if (!value) {
			continue;
		}

		if (["cost_center", "project"].includes(fieldname) || filter.df.fieldtype === "MultiSelectList") {
			route_options[fieldname] = Array.isArray(value) ? value : [value];
		} else if (!["from_fiscal_year", "to_fiscal_year", "period_start_date", "period_end_date", "filter_based_on", "periodicity", "accumulated_values", "selected_view"].includes(fieldname)) {
			route_options[fieldname] = value;
		}
	}

	return route_options;
}

function get_bclc_accounts(data, period) {
	return data.accounts || [];
}

window.open_bclc_general_ledger = function (encoded_options) {
	frappe.route_options = JSON.parse(decodeURIComponent(encoded_options));
	frappe.set_route("query-report", "Custom General Ledger");
};
