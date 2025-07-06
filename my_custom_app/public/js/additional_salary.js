frappe.ui.form.off('Additional Salary', 'employee');
frappe.ui.form.on('Additional Salary', {
	employee: function(frm) {
		if (frm.doc.employee) {
			frappe.run_serially([
				() => frm.trigger("get_employee_currency"),
				() => frm.trigger("set_company"),
				() => setup_salary_component_query(frm)  // thêm dòng này
			]);
		} else {
			frm.set_value("company", null);
		}
	}
});

function setup_salary_component_query(frm) {
	if (!frm.doc.employee) {
		frm.set_query('salary_component', () => ({}));
		return;
	}

	// 1. Lấy tất cả deduction component (không lọc company)
	frappe.db.get_list('Salary Component', {
		filters: { type: 'Deduction' },
		fields: ['name'],
		limit: 500
	}).then(deduction_result => {
		const deduction_components = deduction_result.map(r => r.name);

		// 2. Lấy Salary Structure Assignment
		frappe.db.get_list('Salary Structure Assignment', {
			filters: {
				employee: frm.doc.employee,
				docstatus: 1
			},
			fields: ['salary_structure'],
			order_by: 'from_date desc',
			limit: 1
		}).then(assignments => {
			if (!assignments.length) {
				frappe.msgprint(__('No Salary Structure assigned to this Employee.'));
				frm.set_query('salary_component', () => ({
					filters: { name: ['in', deduction_components] }
				}));
				return;
			}

			const structure = assignments[0].salary_structure;

			// 3. Lấy components từ Salary Structure
			frappe.db.get_doc('Salary Structure', structure).then(doc => {
				const structure_components = new Set();

				(doc.earnings || []).forEach(row => {
					if (row.salary_component) {
						structure_components.add(row.salary_component);
					}
				});

				const combined = [...new Set([
					...deduction_components,
					...structure_components
				])];

				frm.set_query('salary_component', () => ({
					filters: {
						name: ['in', combined]
					}
				}));
			});
		});
	});
}
