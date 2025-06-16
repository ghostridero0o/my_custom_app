frappe.query_reports["Vat Summary Report"] = {
    filters: [
        {
            fieldname: "company",
            label: __("Company"),
            fieldtype: "Select",
            options: ["Phu Chau", "PC33"],
            reqd: 1,
            default: "Phu Chau"  // 👈 thêm dòng này
        },
        {
            fieldname: "date",
            label: __("Date"),
            fieldtype: "Date",
            reqd: 1,
            default: frappe.datetime.get_today()
        }
    ]
};
