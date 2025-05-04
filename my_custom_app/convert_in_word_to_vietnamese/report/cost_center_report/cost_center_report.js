frappe.query_reports["Cost Center Report"] = {
    filters: get_filters(),
    formatter: function (value, row, column, data, default_formatter) {
        value = default_formatter(value, row, column, data);

        // Đổi màu cho cột balance nếu root_type = 'Income' thì màu đỏ, 'Expense' màu xanh
        if (column.fieldname === "balance") {
            if (data["root_type"] === "Income") {
                value = "<span style='color:red'>" + value + "</span>";
            } else if (data["root_type"] === "Expense") {
                value = "<span style='color:green'>" + value + "</span>";
            }
        }

        // Đổi màu cho cột Account nếu root_type = 'Income' thì màu đỏ, 'Expense' màu xanh
        if (column.fieldname === "account") {
            if (data["root_type"] === "Income") {
                value = "<span style='color:red'>" + value + "</span>";  // Màu đỏ cho Income
            } else if (data["root_type"] === "Expense") {
                value = "<span style='color:green'>" + value + "</span>";  // Màu xanh cho Expense
            }
        }


        return value;
    },
};
function get_filters() {
    let filters = [
        {
            fieldname: "fiscal_year",
            label: __("Fiscal Year"),
            fieldtype: "Link",
            options: "Fiscal Year",
            default: erpnext.utils.get_fiscal_year(frappe.datetime.get_today()), // Set default fiscal year
            reqd: 1,
        },
        {
            fieldname: "company",
            label: __("Company"),
            fieldtype: "Link",
            options: "Company",
            default: frappe.defaults.get_user_default("Company"), // Set default company
            reqd: 1,
        },
        {
            fieldname: "cost_center",
            label: __("Cost Center"),
            fieldtype: "Link",
            options: "Cost Center",
            reqd: 0,
        },
        {
            fieldname: "project",
            label: __("Project"),
            fieldtype: "Link",
            options: "Project",
            reqd: 0,            
        },
    ];

    return filters;
}
