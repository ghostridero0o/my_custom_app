frappe.ui.form.off("Employee Attendance Tool", "mark_attendance");
frappe.ui.form.on("Employee Attendance Tool", {
	mark_attendance(frm) {
		const marked_employees = frm.employees_multicheck.get_checked_options();

		frappe.call({
			method: "hrms.hr.doctype.employee_attendance_tool.employee_attendance_tool.mark_employee_attendance",
			args: {
				employee_list: marked_employees,
				status: frm.doc.status,
				date: frm.doc.date,
				late_entry: frm.doc.late_entry,
				early_exit: frm.doc.early_exit,
				shift: frm.doc.shift,
				project: frm.doc.project, // ✅ gửi kèm trường project
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
