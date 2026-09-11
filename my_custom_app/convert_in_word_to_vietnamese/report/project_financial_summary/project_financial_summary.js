frappe.query_reports["Project Financial Summary"] = {
    tree: true,
    name_field: "account",
    parent_field: "parent_account",
    initial_depth: 3,
    formatter: function (value, row, column, data, default_formatter) {
        if (column.fieldname === "account") {
            column.is_tree = true;

            const is_profit_and_loss =
                frappe.query_report.get_filter_value("view_type") === "Profit and Loss";
            const is_account_row = data && data.account && !data.is_total;

            column.link_onclick = null;
            if (is_profit_and_loss && is_account_row) {
                column.link_onclick =
                    "frappe.query_reports['Project Financial Summary'].open_custom_general_ledger(" +
                    JSON.stringify(data) +
                    ")";
            } else {
                column = Object.assign({}, column, {
                    fieldtype: "Data",
                    options: null,
                });
            }
        }

        value = default_formatter(value, row, column, data);
        if (data && (data.is_group || data.is_total)) {
            value = $(`<span>${value}</span>`)
                .css("font-weight", "bold")
                .wrap("<p></p>")
                .parent()
                .html();
        }
        return value;
    },
    open_custom_general_ledger: function (data) {
        if (!data || !data.account || data.is_total) {
            return;
        }

        const route_options = {
            company: frappe.query_report.get_filter_value("company"),
            from_date: frappe.query_report.get_filter_value("from_date"),
            to_date: frappe.query_report.get_filter_value("to_date"),
            account: [data.account],
            categorize_by: "Categorize by Voucher (Consolidated)",
            include_dimensions: 1,
            include_default_book_entries: 1,
        };

        const finance_book = frappe.query_report.get_filter_value("finance_book");
        const cost_center = frappe.query_report.get_filter_value("cost_center");
        if (finance_book) {
            route_options.finance_book = finance_book;
        }
        if (cost_center) {
            route_options.cost_center = [cost_center];
        }

        frappe.route_options = route_options;
        frappe.set_route("query-report", "Custom General Ledger");
    },
    filters: [
        {
            fieldname: "company",
            label: __("Company"),
            fieldtype: "Link",
            options: "Company",
            default: frappe.defaults.get_user_default("Company"),
            reqd: 1,
            on_change: function () {
                frappe.query_report.set_filter_value("project", []);
            },
        },
        {
            fieldname: "finance_book",
            label: __("Finance Book"),
            fieldtype: "Link",
            options: "Finance Book",
        },
        {
            fieldname: "fiscal_year",
            label: __("Fiscal Year"),
            fieldtype: "Link",
            options: "Fiscal Year",
            default: erpnext.utils.get_fiscal_year(frappe.datetime.get_today()),
            on_change: function (query_report) {
                const fiscal_year = query_report.get_values().fiscal_year;
                if (!fiscal_year) return;

                frappe.model.with_doc("Fiscal Year", fiscal_year, function () {
                    const fiscal_year_doc = frappe.model.get_doc("Fiscal Year", fiscal_year);
                    frappe.query_report.set_filter_value({
                        from_date: fiscal_year_doc.year_start_date,
                        to_date: fiscal_year_doc.year_end_date,
                    });
                });
            },
        },
        {
            fieldname: "from_date",
            label: __("From Date"),
            fieldtype: "Date",
            default: erpnext.utils.get_fiscal_year(frappe.datetime.get_today(), true)[1],
            reqd: 1,
        },
        {
            fieldname: "to_date",
            label: __("To Date"),
            fieldtype: "Date",
            default: erpnext.utils.get_fiscal_year(frappe.datetime.get_today(), true)[2],
            reqd: 1,
        },
        {
            fieldname: "project",
            label: __("Project"),
            fieldtype: "MultiSelectList",
            options: "Project",
            get_data: function (txt) {
                return frappe.db.get_link_options("Project", txt, {
                    company: frappe.query_report.get_filter_value("company"),
                });
            },
        },
        {
            fieldname: "hide_projects_below",
            label: __("Ẩn các công trình <"),
            fieldtype: "Check",
            default: 0,
        },
        {
            fieldname: "project_threshold",
            label: __("Ngưỡng"),
            fieldtype: "Select",
            options: [
                { value: "10000000", label: __("10 triệu") },
                { value: "50000000", label: __("50 triệu") },
                { value: "100000000", label: __("100 triệu") },
                { value: "300000000", label: __("300 triệu") },
                { value: "500000000", label: __("500 triệu") },
            ],
            default: "50000000",
        },
        {
            fieldname: "cost_center",
            label: __("Cost Center"),
            fieldtype: "Link",
            options: "Cost Center",
            get_query: function () {
                return {
                    filters: {
                        company: frappe.query_report.get_filter_value("company"),
                    },
                };
            },
        },
        {
            fieldname: "view_type",
            label: __("View Type"),
            fieldtype: "Select",
            options: ["Profit and Loss", "Cash Flow"],
            default: "Profit and Loss",
            reqd: 1,
        },
    ],
};
