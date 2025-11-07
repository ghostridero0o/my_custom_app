frappe.query_reports["Cash Position Report"] = {
    filters: [
        {
            fieldname: "company",
            label: __("Company"),
            fieldtype: "Link",
            options: "Company",
            default: frappe.defaults.get_user_default("Company"),
        },
        {
            fieldname: "report_date",
            label: __("Date"),
            fieldtype: "Date",
            default: frappe.datetime.get_today(),
            reqd: 1,
            on_change: function() {
                frappe.query_report.refresh(); // 👈 Tự refresh khi đổi ngày
            }
        },
        {
            fieldname: "currency",
            label: __("Currency"),
            fieldtype: "Link",
            options: "Currency",
            default: "VND",
        }
    ],

    "onload": function(report) {
        report.refresh();

        

        // Lỗi khi gọi phương thức chưa đúng, hãy đảm bảo đường dẫn chính xác đến phương thức đã whitelist
        frappe.call({
            method: 'my_custom_app.convert_in_word_to_vietnamese.report.cash_position_report.cash_position_report.execute',  // Đảm bảo đúng đường dẫn
            args: { filters: filters },
            callback: function(response) {
                var report_data = response.message;

                var columns = [
                    { fieldname: 'account', label: 'Account', fieldtype: 'Link', options: 'Account' },
                    { fieldname: 'balance', label: 'Balance', fieldtype: 'Currency', options: 'currency' },
                    { fieldname: 'currency', label: 'Currency', fieldtype: 'Link', options: 'Currency' }
                ];

                var data = report_data.map(function(row) {
                    return {
                        'account': row.account,
                        'balance': row.balance,
                        'currency': row.currency
                    };
                });

                var dialog = new frappe.ui.Dialog({
                    title: 'Account Balance Report',
                    fields: columns,
                    primary_action_label: 'Close'
                });

                dialog.set_values(data);
                dialog.show();
            }
        });
    }
};
