frappe.ui.form.on("Raven Accounting Request", {
	refresh(frm) {
		const labels = {
			"Awaiting User": ["Chờ tạo bút toán", "orange"],
			Created: ["Đã tạo bút toán nháp", "blue"],
			Submitted: ["Hoàn tất tạo bút toán", "green"],
			Cancelled: ["Bút toán bị hủy", "red"],
			Ignored: ["Đã bỏ qua", "gray"],
			Failed: ["Tạo bút toán thất bại", "red"],
		};
		const [label, color] = labels[frm.doc.status] || [frm.doc.status, "gray"];
		frm.page.set_indicator(label, color);

		if (["Awaiting User", "Editing", "Failed"].includes(frm.doc.status)) {
			frm.add_custom_button(__("Tạo Bút Toán"), () => open_accounting_dialog(frm)).addClass("btn-primary");
			const should_open_dialog = new URLSearchParams(window.location.search).get("open_accounting_dialog") === "1";
			if (should_open_dialog && !frm.__accounting_dialog_opened) {
				frm.__accounting_dialog_opened = true;
				const clean_url = `${window.location.pathname}${window.location.hash}`;
				window.history.replaceState({}, "", clean_url);
				setTimeout(() => open_accounting_dialog(frm), 0);
			}
		}
		if (frm.doc.target_doctype && frm.doc.target_document) {
			frm.add_custom_button(__("Mở chứng từ"), () => {
				frappe.set_route("Form", frm.doc.target_doctype, frm.doc.target_document);
			});
		}
	},
});

async function open_accounting_dialog(frm) {
	let response;
	try {
		response = await frappe.call({
			method: "my_custom_app.api.accounting_request.get_request",
			args: { name: frm.doc.name },
			freeze: true,
		});
	} catch (error) {
		frappe.msgprint({
			title: __("Không thể mở form tạo bút toán"),
			message: error?.message || __("Vui lòng kiểm tra quyền người dùng và cấu hình Raven Accounting."),
			indicator: "red",
		});
		return;
	}
	const data = response.message;
	let available_modes = data.available_mode_of_payments || [];
	let dialog;

	const sync_internal_transfer_account = async () => {
		if (
			dialog.get_value("document_type") !== "Payment Entry" ||
			dialog.get_value("transaction_type") !== "Internal Transfer"
		) {
			return;
		}
		const company = dialog.get_value("company");
		const mode_of_payment = dialog.get_value("mode_of_payment");
		if (!company || !mode_of_payment) {
			dialog.set_value("paid_from", "");
			return;
		}
		const result = await frappe.call({
			method: "my_custom_app.api.accounting_request.get_mode_of_payment_default_account",
			args: { company, mode_of_payment },
		});
		if (
			dialog.get_value("company") === company &&
			dialog.get_value("mode_of_payment") === mode_of_payment
		) {
			dialog.set_value("paid_from", result.message || "");
		}
	};

	const update_company_filters = async () => {
		const company = dialog.get_value("company");
		dialog.set_value("mode_of_payment", "");
		dialog.set_value("expense_account", "");
		dialog.set_value("cost_center", "");
		dialog.set_value("paid_from", "");
		dialog.set_value("paid_to", "");
		dialog.set_value("debit_account", "");
		dialog.set_value("credit_account", "");
		if (!company) {
			available_modes = [];
			return;
		}
		const result = await frappe.call({
			method: "my_custom_app.raven.settings.get_company_accounting_defaults",
			args: { company },
		});
		const defaults = result.message || {};
		available_modes = defaults.available_mode_of_payments || [];
		dialog.set_value("mode_of_payment", defaults.mode_of_payment || "");
		dialog.set_value("cost_center", defaults.cost_center || "");
		await sync_internal_transfer_account();
	};

	dialog = new frappe.ui.Dialog({
		title: __("Tạo bút toán từ Raven"),
		size: "large",
		fields: [
			{ fieldname: "document_type", fieldtype: "Select", label: __("Loại chứng từ"), options: "Petty Expense\nPayment Entry\nJournal Entry", reqd: 1 },
			{ fieldname: "company", fieldtype: "Link", label: __("Công ty"), options: "Company", reqd: 1, onchange: update_company_filters },
			{ fieldname: "posting_date", fieldtype: "Date", label: __("Ngày hạch toán"), reqd: 1 },
			{ fieldname: "amount", fieldtype: "Currency", label: __("Số tiền"), options: data.currency || "VND", reqd: 1 },
			{ fieldname: "mode_of_payment", fieldtype: "Link", label: __("Phương thức thanh toán"), options: "Mode of Payment", depends_on: "eval:doc.document_type != 'Journal Entry'", onchange: sync_internal_transfer_account, get_query: () => ({ filters: [["Mode of Payment", "enabled", "=", 1], ["Mode of Payment", "name", "in", available_modes]] }) },
			{ fieldname: "petty_section", fieldtype: "Section Break", label: __("Petty Expense"), depends_on: "eval:doc.document_type == 'Petty Expense'" },
			{ fieldname: "expense_account", fieldtype: "Link", label: __("Tài khoản chi phí"), options: "Account", depends_on: "eval:doc.document_type == 'Petty Expense'", get_query: () => ({ filters: { company: dialog.get_value("company"), is_group: 0 } }) },
			{ fieldname: "cost_center", fieldtype: "Link", label: __("Trung tâm chi phí"), options: "Cost Center", depends_on: "eval:doc.document_type == 'Petty Expense'", get_query: () => ({ filters: { company: dialog.get_value("company"), is_group: 0 } }) },
			{ fieldname: "payment_section", fieldtype: "Section Break", label: __("Payment Entry"), depends_on: "eval:doc.document_type == 'Payment Entry'" },
			{ fieldname: "transaction_type", fieldtype: "Select", label: __("Loại thanh toán"), options: "Pay\nReceive\nInternal Transfer", depends_on: "eval:doc.document_type == 'Payment Entry'", reqd: 1, onchange: sync_internal_transfer_account },
			{ fieldname: "party_type", fieldtype: "Select", label: __("Loại đối tượng"), options: "\nCustomer\nSupplier\nEmployee", depends_on: "eval:doc.document_type == 'Payment Entry' && doc.transaction_type != 'Internal Transfer'" },
			{ fieldname: "party", fieldtype: "Dynamic Link", label: __("Đối tượng"), options: "party_type", depends_on: "eval:doc.document_type == 'Payment Entry' && doc.transaction_type != 'Internal Transfer'" },
			{ fieldname: "paid_from", fieldtype: "Link", label: __("Tài khoản chuyển đi"), options: "Account", read_only: 1, description: __("Tự động lấy từ tài khoản mặc định của Phương thức thanh toán."), depends_on: "eval:doc.document_type == 'Payment Entry' && doc.transaction_type == 'Internal Transfer'" },
			{ fieldname: "paid_to", fieldtype: "Link", label: __("Tài khoản nhận"), options: "Account", depends_on: "eval:doc.document_type == 'Payment Entry' && doc.transaction_type == 'Internal Transfer'", get_query: () => ({ filters: { company: dialog.get_value("company"), is_group: 0 } }) },
			{ fieldname: "reference_no", fieldtype: "Data", label: __("Số tham chiếu"), depends_on: "eval:doc.document_type == 'Payment Entry'" },
			{ fieldname: "reference_date", fieldtype: "Date", label: __("Ngày tham chiếu"), depends_on: "eval:doc.document_type == 'Payment Entry'" },
			{ fieldname: "journal_section", fieldtype: "Section Break", label: __("Journal Entry"), depends_on: "eval:doc.document_type == 'Journal Entry'" },
			{ fieldname: "debit_account", fieldtype: "Link", label: __("Tài khoản Nợ"), options: "Account", depends_on: "eval:doc.document_type == 'Journal Entry'", get_query: () => ({ filters: { company: dialog.get_value("company"), is_group: 0 } }) },
			{ fieldname: "credit_account", fieldtype: "Link", label: __("Tài khoản Có"), options: "Account", depends_on: "eval:doc.document_type == 'Journal Entry'", get_query: () => ({ filters: { company: dialog.get_value("company"), is_group: 0 } }) },
			{ fieldname: "description", fieldtype: "Small Text", label: __("Diễn giải"), reqd: 1 },
		],
		primary_action_label: __("Tạo chứng từ nháp"),
		primary_action: async (values) => {
			const amount_control = dialog.get_field("amount");
			values.amount = flt(
				amount_control.$input.val(),
				null,
				amount_control.get_number_format(),
			);
			const result = await frappe.call({
				method: "my_custom_app.api.accounting_request.create_entry",
				args: { name: frm.doc.name, values },
				freeze: true,
				freeze_message: __("Đang tạo chứng từ nháp..."),
			});
			dialog.hide();
			frappe.show_alert({ message: __("Đã tạo bút toán nháp"), indicator: "green" });
			await frm.reload_doc();
			if (result.message?.doctype && result.message?.document) {
				frappe.set_route("Form", result.message.doctype, result.message.document);
			}
		},
	});

	dialog.show();
	dialog.set_values({
		document_type: data.document_type || "Petty Expense",
		company: data.company,
		posting_date: data.posting_date,
		amount: data.amount,
		mode_of_payment: data.mode_of_payment,
		expense_account: data.expense_account,
		cost_center: data.cost_center,
		transaction_type: ["Pay", "Receive", "Internal Transfer"].includes(data.transaction_type) ? data.transaction_type : "Pay",
		party_type: data.party_type,
		party: data.party,
		paid_from: data.paid_from,
		paid_to: data.paid_to,
		reference_no: data.reference_no,
		reference_date: data.reference_date || data.posting_date,
		debit_account: data.debit_account,
		credit_account: data.credit_account,
		description: data.description,
	});
	await sync_internal_transfer_account();
}
