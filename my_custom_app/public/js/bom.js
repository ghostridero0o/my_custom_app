frappe.ui.form.on("BOM", {
    refresh(frm) {
        if (frm.doc.docstatus === 0 && frm.perm?.[0]?.write) {
            frm.add_custom_button(__("Lọc vật tư theo Project"), () => show_project_stock_picker(frm));
        }
    },
});

function show_project_stock_picker(frm) {
    if (!frm.doc.company) {
        frappe.msgprint(__("Vui lòng chọn Company trên BOM trước."));
        return;
    }
    let dialog;
    let request_id = 0;
    let loading = false;
    let adding = false;
    let stock_rows = [];
    let show_remaining = false;
    const render_stock = () => {
        const rows = stock_rows.map(stock => ({...stock, __checked: 0,
            actual_qty: show_remaining ? bom_remaining_stock(frm.doc, stock) : stock.actual_qty}));
        dialog.fields_dict.stock.df.data = rows;
        dialog.fields_dict.stock.grid.refresh();
        dialog.fields_dict.status.$wrapper.text(rows.length
            ? (show_remaining ? __("Số lượng còn lại = tồn kho − số lượng trong BOM theo Item và Warehouse.")
                : __("Có {0} dòng tồn kho. Tích ô ở tiêu đề bảng để chọn tất cả.", [rows.length]))
            : __("Không có vật tư tồn dương phù hợp với bộ lọc."));
    };
    const reload = async () => {
        if (!dialog || adding) return;
        const current_request = ++request_id;
        loading = true;
        stock_rows = [];
        dialog.get_primary_btn().prop("disabled", true);
        dialog.fields_dict.stock.df.data = [];
        dialog.fields_dict.stock.grid.refresh();
        dialog.fields_dict.status.$wrapper.text(__("Đang lấy tồn kho…"));
        try {
            const response = await frappe.call({
                method: "my_custom_app.controllers.bom.get_project_stock",
                args: {
                    company: frm.doc.company,
                    project: dialog.get_value("project"),
                    item_group: dialog.get_value("item_group"),
                    warehouse: dialog.get_value("warehouse"),
                    exclude_item: frm.doc.item,
                },
            });
            if (current_request !== request_id) return;
            stock_rows = (response.message || []).map(row => ({...row}));
            render_stock();
        } catch (error) {
            if (current_request === request_id) {
                dialog.fields_dict.status.$wrapper.text(__("Không tải được tồn kho. Vui lòng thử lại."));
            }
        } finally {
            if (current_request === request_id) {
                loading = false;
                dialog.get_primary_btn().prop("disabled", false);
            }
        }
    };
    dialog = new frappe.ui.Dialog({
        title: __("Lọc vật tư theo Project"),
        size: "extra-large",
        fields: [
            {fieldname: "project", label: "Project", fieldtype: "Link", options: "Project",
                default: frm.doc.project, get_query: () => ({filters: {company: frm.doc.company}}), onchange: reload},
            {fieldtype: "Column Break"},
            {fieldname: "item_group", label: "Item Group", fieldtype: "MultiSelectList", options: "Item Group",
                get_data: txt => frappe.db.get_link_options("Item Group", txt), onchange: reload},
            {fieldtype: "Column Break"},
            {fieldname: "warehouse", label: "Warehouse", fieldtype: "MultiSelectList", options: "Warehouse",
                get_data: txt => frappe.db.get_link_options("Warehouse", txt, {company: frm.doc.company}), onchange: reload},
            {fieldtype: "Section Break"},
            {fieldname: "update_quantity", label: __("Cập nhật số lượng"), fieldtype: "Button",
                click: () => {
                    if (loading || adding) return;
                    show_remaining = true;
                    render_stock();
                }},
            {fieldname: "status", fieldtype: "HTML"},
            {fieldname: "stock", fieldtype: "Table", cannot_add_rows: true, cannot_delete_rows: true,
                in_place_edit: false, data: [], fields: [
                    {fieldname: "item_code", label: "Item ID", fieldtype: "Link", options: "Item", in_list_view: 1, read_only: 1, columns: 2},
                    {fieldname: "item_name", label: "Item Name", fieldtype: "Data", in_list_view: 1, read_only: 1, columns: 2},
                    {fieldname: "item_group", label: "Item Group", fieldtype: "Link", options: "Item Group", in_list_view: 1, read_only: 1, columns: 2},
                    {fieldname: "warehouse", label: "Warehouse", fieldtype: "Link", options: "Warehouse", in_list_view: 1, read_only: 1, columns: 2},
                    {fieldname: "stock_uom", label: "Stock UOM", fieldtype: "Link", options: "UOM", in_list_view: 1, read_only: 1, columns: 1},
                    {fieldname: "actual_qty", label: "Actual Qty", fieldtype: "Float", in_list_view: 1, read_only: 1, columns: 1},
                ]},
            {fieldtype: "HTML", options: `<p class="text-muted">${__("Để trống Project để xem tất cả. Số lượng là tồn theo Project, chưa trừ giữ chỗ. Bấm Cập nhật số lượng để trừ lượng đã có trong BOM; chọn thêm sẽ bổ sung phần còn lại. Dòng không có kho dùng kho nguồn mặc định của BOM.")}</p>`},
        ],
        secondary_action_label: __("Thoát"),
        secondary_action: () => { if (!adding) dialog.hide(); },
        primary_action_label: __("Thêm vào BOM Items"),
        primary_action: async () => {
            if (loading || adding) return;
            const selected = dialog.fields_dict.stock.grid.get_selected_children()
                .map(stock => {
                    const original = stock_rows.find(row => row.item_code === stock.item_code && row.warehouse === stock.warehouse);
                    return {...stock, actual_qty: show_remaining && original
                        ? bom_remaining_stock(frm.doc, original) : stock.actual_qty};
                }).filter(stock => Number(stock.actual_qty) > 0);
            if (!selected.length) {
                frappe.msgprint(__("Vui lòng chọn ít nhất một dòng vật tư có số lượng lớn hơn 0."));
                return;
            }
            adding = true;
            dialog.get_primary_btn().prop("disabled", true);
            try {
                // Fetch standard BOM metadata/rates before changing any child rows.
                const prepared = [];
                for (const stock of selected) {
                    const existing = (frm.doc.items || []).find(item => item.item_code === stock.item_code
                        && (item.source_warehouse || frm.doc.default_source_warehouse) === stock.warehouse);
                    const quantity = Number(stock.actual_qty) + (show_remaining && existing
                        ? Number(existing.qty || 0) * Number(existing.conversion_factor || 1) : 0);
                    const response = await frappe.call({
                        doc: frm.doc, method: "get_bom_material_detail",
                        args: {company: frm.doc.company, item_code: stock.item_code, bom_no: "",
                            qty: quantity, stock_qty: quantity,
                            uom: stock.stock_uom, stock_uom: stock.stock_uom, conversion_factor: 1,
                            source_warehouse: stock.warehouse, fetch_rate: true},
                    });
                    prepared.push({stock, existing, quantity, details: response.message || {}});
                }
                for (const {stock, existing, quantity, details} of prepared) {
                    const row = existing || frm.add_child("items");
                    Object.assign(row, details, {item_code: stock.item_code, item_name: stock.item_name,
                        source_warehouse: stock.warehouse, stock_uom: stock.stock_uom, uom: stock.stock_uom,
                        conversion_factor: 1, qty: quantity, stock_qty: quantity});
                    if (frappe.meta.get_docfield(row.doctype, "item_group", row.name)) row.item_group = stock.item_group;
                }
                erpnext.bom.calculate_rm_cost(frm.doc);
                erpnext.bom.calculate_total(frm.doc);
                frm.dirty();
                frm.refresh_field("items");
                render_stock();
                frappe.show_alert({message: __("Đã cập nhật {0} dòng vật tư vào BOM.", [selected.length]), indicator: "green"});
            } finally {
                adding = false;
                dialog.get_primary_btn().prop("disabled", false);
            }
        },
    });
    dialog.show();
    reload();
}

function bom_remaining_stock(bom, stock) {
    const used = (bom.items || []).reduce((total, item) => {
        if (item.item_code !== stock.item_code ||
            (item.source_warehouse || bom.default_source_warehouse) !== stock.warehouse) return total;
        return total + Number(item.qty || 0) * Number(item.conversion_factor || 1);
    }, 0);
    return Math.max(0, Number((Number(stock.actual_qty) - used).toFixed(9)));
}
