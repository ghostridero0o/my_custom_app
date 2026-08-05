frappe.query_reports["Custom Profit And Loss"] = {
    filters: [
        {
            fieldname: "company",
            label: __("Company"),
            fieldtype: "Link",
            options: "Company",
            reqd: 1,
            default: frappe.defaults.get_default("company")
        },
        {
            fieldname: "filter_based_on",
            label: __("Filter Based On"),
            fieldtype: "Select",
            options: ["Fiscal Year", "Date Range"],
            default: "Fiscal Year",
            reqd: 1,
            on_change: function () {
                const filter_based_on = frappe.query_report.get_filter_value("filter_based_on");
                if (
                    filter_based_on === "Date Range" &&
                    !frappe.query_report.get_filter_value("period_end_date")
                ) {
                    frappe.query_report.set_filter_value(
                        "period_end_date",
                        frappe.datetime.get_today()
                    );
                }
                frappe.query_report.toggle_filter_display(
                    "from_fiscal_year",
                    filter_based_on === "Date Range"
                );
                frappe.query_report.toggle_filter_display(
                    "to_fiscal_year",
                    filter_based_on === "Date Range"
                );
                frappe.query_report.toggle_filter_display(
                    "period_start_date",
                    filter_based_on === "Fiscal Year"
                );
                frappe.query_report.toggle_filter_display(
                    "period_end_date",
                    filter_based_on === "Fiscal Year"
                );
            }
        },
        {
            fieldname: "period_start_date",
            label: __("Start Date"),
            fieldtype: "Date",
            depends_on: "eval:doc.filter_based_on == 'Date Range'",
            mandatory_depends_on: "eval:doc.filter_based_on == 'Date Range'"
        },
        {
            fieldname: "period_end_date",
            label: __("End Date"),
            fieldtype: "Date",
            default: frappe.datetime.get_today(),
            depends_on: "eval:doc.filter_based_on == 'Date Range'",
            mandatory_depends_on: "eval:doc.filter_based_on == 'Date Range'"
        },
        {
            fieldname: "from_fiscal_year",
            label: __("From Fiscal Year"),
            fieldtype: "Link",
            options: "Fiscal Year",
            depends_on: "eval:doc.filter_based_on == 'Fiscal Year'",
            mandatory_depends_on: "eval:doc.filter_based_on == 'Fiscal Year'"
        },
        {
            fieldname: "to_fiscal_year",
            label: __("To Fiscal Year"),
            fieldtype: "Link",
            options: "Fiscal Year",
            default: new Date().getFullYear(),
            depends_on: "eval:doc.filter_based_on == 'Fiscal Year'",
            mandatory_depends_on: "eval:doc.filter_based_on == 'Fiscal Year'"
        },
        {
            fieldname: "project",
            label: __("Project"),
            fieldtype: "MultiSelectList",
            get_data: function (txt) {
                return frappe.db.get_link_options("Project", txt, {});
            },
            options: "Project"
        },
        {
            fieldname: "cost_center",
            label: __("Cost Center"),
            fieldtype: "MultiSelectList",
            get_data: function (txt) {
                return frappe.db.get_link_options("Cost Center", txt, {
                    company: frappe.query_report.get_filter_value("company")
                });
            },
            options: "Cost Center"
        },
        {
            fieldname: "finance_book",
            label: __("Finance Book"),
            fieldtype: "Link",
            options: "Finance Book"
        },
        {
            fieldname: "periodicity",
            label: __("Periodicity"),
            fieldtype: "Select",
            options: [
                { value: "Monthly", label: __("Monthly") },
                { value: "Quarterly", label: __("Quarterly") },
                { value: "Half-Yearly", label: __("Half-Yearly") },
                { value: "Yearly", label: __("Yearly") }
            ],
            default: "Yearly",
            reqd: 1
        },
        {
            fieldname: "selected_view",
            label: __("Select View"),
            fieldtype: "Select",
            options: [
                { value: "Report", label: __("Report View") },
                { value: "Growth", label: __("Growth View") },
                { value: "Margin", label: __("Margin View") }
            ],
            default: "Report",
            reqd: 1
        },
        {
            fieldname: "show_ratio",
            label: __("Hiện tỷ trọng"),
            fieldtype: "Check",
            default: 0
        },
        {
            fieldname: "accumulated_values",
            label: __("Accumulated Values"),
            fieldtype: "Check",
            default: 1
        },
        {
            fieldname: "include_default_book_entries",
            label: __("Include Default FB Entries"),
            fieldtype: "Check",
            default: 1
        }
    ],
    tree: true,
    name_field: "account",
    parent_field: "parent_account",
    initial_depth: 0,
    formatter: function(value, row, column, data, default_formatter) {
        const selected_view = frappe.query_report.get_filter_value("selected_view");
        const columns = frappe.query_report && frappe.query_report.columns ? frappe.query_report.columns : [];
        const first_period_col = columns.find(col => col && col.fieldtype === "Currency");
        const is_first_period = first_period_col && column.fieldname === first_period_col.fieldname;

        if (selected_view === "Growth" && data && column.fieldtype === "Currency") {
            if (is_first_period) {
                return default_formatter(value, row, column, data);
            }
            const growthPercent = data[column.fieldname];
            if (growthPercent === undefined || growthPercent === null) {
                return "NA";
            }
            let display = `${growthPercent >= 0 ? "+" : ""}${growthPercent}%`;
            let $value = $(`<span>${display}</span>`);
            if (growthPercent < 0) {
                $value.addClass("text-danger");
            } else {
                $value.addClass("text-success");
            }
            return $value.wrap("<p></p>").parent().html();
        }

        if (selected_view === "Margin" && data && column.fieldtype === "Currency") {
            const marginPercent = data[column.fieldname];
            if (marginPercent === undefined || marginPercent === null) {
                return "NA";
            }
            let $value = $(`<span>${marginPercent}%</span>`);
            if (marginPercent < 0) {
                $value.addClass("text-danger");
            } else {
                $value.addClass("text-success");
            }
            return $value.wrap("<p></p>").parent().html();
        }

        if (data && column.fieldname === "account") {
            value = data.account_name || value;

            if ((data.accounts && data.accounts.length) || (data.is_account && !data.is_group)) {
            column.link_onclick =
                "frappe.query_reports['Custom Profit And Loss'].open_general_ledger(" +
                JSON.stringify(data) +
                ")";
            }
            column.is_tree = true;
        }

        value = default_formatter(value, row, column, data);
        return value;
    },
    open_general_ledger: function (data) {
        if (!data || (!data.account && !(data.accounts && data.accounts.length))) {
            return;
        }

        frappe.route_options = {
            account: data.account || data.accounts,
            company: frappe.query_report.get_filter_value("company"),
            from_date: data.from_date,
            to_date: data.to_date,
            project: frappe.query_report.get_filter_value("project") || "",
            cost_center: frappe.query_report.get_filter_value("cost_center") || "",
            finance_book: frappe.query_report.get_filter_value("finance_book") || ""
        };

        frappe.set_route("query-report", "General Ledger");
    }
};
