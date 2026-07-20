frappe.ui.form.on("Raven Accounting Settings", {
	setup(frm) {
		const grid = frm.fields_dict.channel_configurations.grid;
		grid.get_field("cost_center").get_query = (doc, cdt, cdn) => ({
			filters: { company: locals[cdt][cdn].company, is_group: 0 },
		});
		grid.get_field("mode_of_payment").get_query = (doc, cdt, cdn) => ({
			query: "my_custom_app.raven.settings.search_company_mode_of_payment",
			filters: { company: locals[cdt][cdn].company },
		});
	},
});

frappe.ui.form.on("Raven Accounting Channel Setting", {
	async company(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		for (const fieldname of ["mode_of_payment", "cost_center"]) {
			await frappe.model.set_value(cdt, cdn, fieldname, "");
		}
		if (!row.company) return;
		const response = await frappe.call({
			method: "my_custom_app.raven.settings.get_company_accounting_defaults",
			args: { company: row.company },
		});
		const defaults = response.message || {};
		if (!row.cash_account) {
			await frappe.model.set_value(cdt, cdn, "cash_account", defaults.cash_account || "");
		}
		await frappe.model.set_value(cdt, cdn, "cost_center", defaults.cost_center || "");
		await frappe.model.set_value(cdt, cdn, "mode_of_payment", defaults.mode_of_payment || "");
	},
});
