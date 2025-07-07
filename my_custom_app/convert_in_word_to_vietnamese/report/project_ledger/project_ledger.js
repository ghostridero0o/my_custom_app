frappe.query_reports["Project Ledger"] = {
    filters: get_filters(),

    formatter: function(value, row, column, data, default_formatter) {
        if (column.fieldname === "account" && (
            value?.includes("Cash In") || 
            value?.includes("Cash Out") || 
            value?.includes("Doanh thu") || 
            value?.includes("Chi phí") || 
            value?.includes("Net Cash Flow") || 
            value?.includes("Lợi nhuận") ||
            value?.includes("Nhân công trực tiếp") // 👈 thêm dòng này
        )) {
            return default_formatter(value, row, column, data)
                .replace(/&lt;b&gt;/g, "<b>")
                .replace(/&lt;\/b&gt;/g, "</b>");
        }
        return default_formatter(value, row, column, data);
    }
};

function get_filters() {
    const today = frappe.datetime.get_today();
    const default_company = frappe.defaults.get_user_default("company");

    // fallback
    let filters = [
        {
            fieldname: "company",
            label: "Company",
            fieldtype: "Link",
            options: "Company",
            reqd: 1,
            default: default_company
        },
        {
            fieldname: "finance_book",
            label: "Finance Book",
            fieldtype: "Link",
            options: "Finance Book"
        },
        {
            fieldname: "from_date",
            label: "From Date",
            fieldtype: "Date",
            reqd: 1,
            default: today
        },
        {
            fieldname: "to_date",
            label: "To Date",
            fieldtype: "Date",
            reqd: 1,
            default: today // tạm thời, sẽ cập nhật bằng fiscal start sau
        },
        {
            fieldname: "project",
            label: "Project",
            fieldtype: "Link",
            options: "Project"
        },
        {
            fieldname: "cost_center",
            label: "Cost Center",
            fieldtype: "Link",
            options: "Cost Center"
        },
        {
            fieldname: "voucher_type",
            label: "Voucher Type",
            fieldtype: "Data"
        },
        {
            fieldname: "voucher_subtype",
            label: "Voucher Subtype",
            fieldtype: "Data"
        },
        {
            fieldname: "view_type",
            label: "View Type",
            fieldtype: "Select",
            options: ["Cash Flow", "Profit and Loss"],
            default: "Cash Flow",
            reqd: 1
        }
    ];

    // override to_date bằng ngày bắt đầu fiscal_year
    frappe.call({
        method: "erpnext.accounts.utils.get_fiscal_year",
        args: {
            date: today,
            company: default_company
        },
        async: false, // chạy đồng bộ để chắc chắn giá trị được gán trước khi render
        callback: function(r) {
            if (r.message) {
                const fiscal_start = r.message[1]; // YYYY-MM-DD
                filters.find(f => f.fieldname === "from_date").default = fiscal_start;
            }
        }
    });

    return filters;
}
