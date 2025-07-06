frappe.ui.form.off("Employee Incentive", "set_earning_component");
frappe.ui.form.on("Employee Incentive", {
    set_earning_component: function (frm) {
        if (!frm.doc.company) return;
    
        frm.set_query("salary_component", function () {
            return {
                filters: {
                    type: "earning",
                    company: frm.doc.company,
                    is_flexible_benefit: 1,  // thêm điều kiện này vào
                    disabled: 0              // tuỳ chọn, nếu cần lọc theo trạng thái active
                },
            };
        });
    },    
});