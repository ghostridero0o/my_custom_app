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

	frappe.call({
		method: 'my_custom_app.controllers.utils.get_additional_salary_components',
		args: {
			employee: frm.doc.employee
		}
	}).then(r => {
		const data = r.message || {};
		const components = data.components || [];

		if (!data.has_assignment) {
			frappe.msgprint(__('No Salary Structure assigned to this Employee.'));
		}

		frm.set_query('salary_component', () => ({
			filters: {
				name: ['in', components]
			}
		}));
	}).catch(() => {
		frm.set_query('salary_component', () => ({
			filters: {
				name: ['in', []]
			}
		}));
	});
}
