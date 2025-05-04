frappe.query_reports["Profit Loss Report"] = {
    filters: [
        {
            fieldname: "fiscal_year",
            label: __("Fiscal Year"),
            fieldtype: "Link",
            options: "Fiscal Year",
            default: erpnext.utils.get_fiscal_year(frappe.datetime.get_today()),
            reqd: 1,
            on_change: function(query_report) {
                var fiscal_year = query_report.get_values().fiscal_year;
                if (!fiscal_year) {
                    return;
                }
                frappe.model.with_doc("Fiscal Year", fiscal_year, function(r) {
                    var fy = frappe.model.get_doc("Fiscal Year", fiscal_year);
                    frappe.query_report.set_filter_value({
                        from_date: fy.year_start_date,
                        to_date: fy.year_end_date,
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
            fieldname: "cost_center",  // Thêm filter Cost Center
            label: __("Cost Center"),
            fieldtype: "Link",
            options: "Cost Center",  // Liên kết với DocType "Cost Center"
            default: "",  // Có thể để mặc định là trống hoặc một giá trị nào đó
        }
    ],

    "onload": function(report) {
        // Khi báo cáo được tải, tự động gọi phương thức để lấy dữ liệu và hiển thị
        report.refresh();

        // Lấy giá trị bộ lọc đã chọn
       

        // Kiểm tra nếu bộ lọc 'from_date' và 'to_date' có giá trị
        if (!filters.from_date || !filters.to_date) {
            frappe.msgprint(__('Both From Date and To Date must be selected.'));
            return; // Dừng nếu thiếu một trong các giá trị
        }

        // Gọi phương thức từ server để lấy dữ liệu
        frappe.call({
            method: 'my_custom_app.convert_in_word_to_vietnamese.report.profit_loss_report.profit_loss_report.execute',
            args: { filters: filters },
            callback: function(response) {
                var report_data = response.message; // Dữ liệu trả về từ server
                var columns = [
                    { fieldname: 'account', label: 'Account', fieldtype: 'Data' },
                    { fieldname: 'account_title', label: 'Account Title', fieldtype: 'Data' },
                ];

                // Thêm cột cho từng Project
                var projects = Object.keys(report_data[0]).filter(key => key !== 'account' && key !== 'account_title');
                projects.forEach(function(project) {
                    columns.push({
                        fieldname: project,
                        label: project,
                        fieldtype: 'Data'
                    });
                });

                // Dữ liệu cho báo cáo
                var data = report_data.map(function(row) {
                    var row_data = { 'account': row.account, 'account_title': row.account_title };
                    projects.forEach(function(project) {
                        row_data[project] = row[project] ? row[project] : { revenue: 0, cogs: 0, profit_or_loss: 0 };
                    });
                    return row_data;
                });

                // Hiển thị báo cáo dưới dạng bảng
                var dialog = new frappe.ui.Dialog({
                    title: 'Profit and Loss Report',
                    fields: columns,
                    primary_action_label: 'Close'
                });

                dialog.set_values(data);
                dialog.show();
            }
        });
    }
};
