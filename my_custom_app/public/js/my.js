frappe.ui.form.off("Employee Attendance Tool", "mark_full_day_attendance");

frappe.ui.form.on("Employee Attendance Tool", {
	mark_full_day_attendance(frm, employees_to_mark_full_day, employees_to_mark_half_day) {
		frappe.call({
			method: "hrms.hr.doctype.employee_attendance_tool.employee_attendance_tool.mark_employee_attendance",
			args: {
				employee_list: employees_to_mark_full_day,
				status: frm.doc.status,
				date: frm.doc.date,
				late_entry: frm.doc.late_entry,
				early_exit: frm.doc.early_exit,
				shift: frm.doc.shift,
				mark_half_day: employees_to_mark_half_day.length ? true : false,
				half_day_status: frm.doc.half_day_status,
				half_day_employee_list: employees_to_mark_half_day,
				project: frm.doc.project,   // ✅ gửi thêm project
			},
			freeze: true,
			freeze_message: __("Marking Attendance"),
		}).then((r) => {
			if (!r.exc) {
				frappe.show_alert({
					message: __("Attendance marked successfully"),
					indicator: "green",
				});
				frm.refresh();
			}
		});
	}
});
