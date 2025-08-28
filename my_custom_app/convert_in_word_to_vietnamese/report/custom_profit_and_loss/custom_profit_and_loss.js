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
            fieldname: "from_fiscal_year",
            label: __("From Fiscal Year"),
            fieldtype: "Link",
            options: "Fiscal Year",
            reqd: 1
        },
        {
            fieldname: "to_fiscal_year",
            label: __("To Fiscal Year"),
            fieldtype: "Link",
            options: "Fiscal Year",
            default: new Date().getFullYear(),
            reqd: 1
        },
        {
            fieldname: "project",
            label: __("Project"),
            fieldtype: "Link",
            options: "Project"
        },
        {
            fieldname: "cost_center",
            label: __("Cost Center"),
            fieldtype: "Link",
            options: "Cost Center"
        },
        {
            fieldname: "finance_book",
            label: __("Finance Book"),
            fieldtype: "Link",
            options: "Finance Book"
        },
        {
            fieldname: "show_ratio",
            label: __("Hiện tỷ trọng"),
            fieldtype: "Check",
            default: 0
        }
    ],
    tree: true,
    name_field: "account",
    parent_field: "parent_account",
    initial_depth: 0,
    formatter: function(value, row, column, data, default_formatter) {
        value = default_formatter(value, row, column, data);
        return value;
    }
};