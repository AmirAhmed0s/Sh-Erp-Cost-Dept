// Copyright (c) 2024, Amir Mansi and contributors
// For license information, please see license.txt

frappe.ui.form.on("Multi Dimension Stock Transfer", {
	refresh(frm) {
		frm.trigger("set_item_queries");
	},

	set_item_queries(frm) {
		// Set queries for child table fields via item_code
	},
});

// -----------------------------------------------------------------------
// Child table events
// -----------------------------------------------------------------------
frappe.ui.form.on("Multi Dimension Transfer Item", {
	// When item_code changes, reset dimension fields and refresh queries
	item_code(frm, cdt, cdn) {
		const row = locals[cdt][cdn];

		// Reset dimension fields
		frappe.model.set_value(cdt, cdn, "from_brand", "");
		frappe.model.set_value(cdt, cdn, "to_brand", "");
		frappe.model.set_value(cdt, cdn, "from_batch", "");
		frappe.model.set_value(cdt, cdn, "to_batch", "");
		frappe.model.set_value(cdt, cdn, "uom", "");

		if (!row.item_code) return;

		// Fetch default UOM
		frappe.db.get_value("Item", row.item_code, "stock_uom", (r) => {
			if (r && r.stock_uom) {
				frappe.model.set_value(cdt, cdn, "uom", r.stock_uom);
			}
		});

		// Refresh set_query for brand and batch fields
		refresh_field("from_brand", cdn, "transfer_items");
		refresh_field("to_brand", cdn, "transfer_items");
		refresh_field("from_batch", cdn, "transfer_items");
		refresh_field("to_batch", cdn, "transfer_items");
	},

	// When from_warehouse changes, refresh from_batch query
	from_warehouse(frm, cdt, cdn) {
		refresh_field("from_batch", cdn, "transfer_items");
	},

	// Recalculate amount when qty or valuation_rate changes
	qty(frm, cdt, cdn) {
		_calculate_row_amount(frm, cdt, cdn);
		frm.trigger("calculate_totals");
	},

	valuation_rate(frm, cdt, cdn) {
		_calculate_row_amount(frm, cdt, cdn);
		frm.trigger("calculate_totals");
	},

	// ------------------------------------------------------------------ #
	// set_query for from_brand
	// ------------------------------------------------------------------ #
	form_render(frm, cdt, cdn) {
		const row = locals[cdt][cdn];

		frm.fields_dict["transfer_items"].grid.get_row(cdn).get_field(
			"from_brand"
		).get_query = function () {
			return _brand_query(row.item_code);
		};

		frm.fields_dict["transfer_items"].grid.get_row(cdn).get_field(
			"to_brand"
		).get_query = function () {
			return _brand_query(row.item_code);
		};

		frm.fields_dict["transfer_items"].grid.get_row(cdn).get_field(
			"from_batch"
		).get_query = function () {
			return _batch_query(row.item_code, row.from_warehouse);
		};

		frm.fields_dict["transfer_items"].grid.get_row(cdn).get_field(
			"to_batch"
		).get_query = function () {
			return _batch_query(row.item_code, null);
		};
	},
});

// -----------------------------------------------------------------------
// Helpers
// -----------------------------------------------------------------------

/**
 * Returns a set_query object that limits Brand options to those
 * defined in the Item's custom_brands child table.
 */
function _brand_query(item_code) {
	if (!item_code) {
		return {filters: [["Brand", "name", "=", ""]]};
	}
	return {
		query:
			"sh_erp_cost_dept.inventory_management.doctype.multi_dimension_stock_transfer.multi_dimension_stock_transfer.get_brands_for_item",
		filters: {item_code: item_code},
	};
}

/**
 * Returns a set_query that limits Batch options to batches
 * belonging to the item and (optionally) available in the warehouse.
 */
function _batch_query(item_code, warehouse) {
	if (!item_code) {
		return {filters: [["Batch", "item", "=", ""]]};
	}
	const filters = {item: item_code};
	if (warehouse) filters["warehouse"] = warehouse;
	return {
		filters: filters,
		query: warehouse
			? "sh_erp_cost_dept.inventory_management.doctype.multi_dimension_stock_transfer.multi_dimension_stock_transfer.get_batches_for_item_warehouse"
			: null,
	};
}

function _calculate_row_amount(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	const amount = flt(row.qty) * flt(row.valuation_rate);
	frappe.model.set_value(cdt, cdn, "amount", amount);
}

frappe.ui.form.on("Multi Dimension Stock Transfer", {
	calculate_totals(frm) {
		let total_qty = 0;
		let total_amount = 0;
		(frm.doc.transfer_items || []).forEach((r) => {
			total_qty += flt(r.qty);
			total_amount += flt(r.amount);
		});
		frm.set_value("total_qty", total_qty);
		frm.set_value("total_amount", total_amount);
	},
});
