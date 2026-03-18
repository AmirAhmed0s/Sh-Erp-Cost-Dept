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

	// When from_warehouse changes, refresh from_batch query and stock warning
	from_warehouse(frm, cdt, cdn) {
		refresh_field("from_batch", cdn, "transfer_items");
		_check_stock_warning(frm, cdt, cdn);
	},

	// Auto-fill valuation_rate and UOM when from_brand changes
	from_brand(frm, cdt, cdn) {
		const row = locals[cdt][cdn];

		// Auto-fill valuation rate from SLE (brand-level weighted average)
		if (row.item_code && row.from_warehouse) {
			frappe.call({
				method: "sh_erp_cost_dept.inventory_management.doctype.multi_dimension_stock_transfer.multi_dimension_stock_transfer.get_brand_valuation_rate",
				args: {
					item_code: row.item_code,
					warehouse: row.from_warehouse,
					brand: row.from_brand,
					batch_no: row.from_batch,
				},
				callback(r) {
					if (r.message) {
						frappe.model.set_value(cdt, cdn, "valuation_rate", r.message);
					}
				},
			});
		}

		// Auto-fill UOM from unit_definition_by_brand
		if (row.item_code && row.from_brand) {
			frappe.db.get_doc("Item", row.item_code).then((item_doc) => {
				const brand_row = (item_doc.custom_brands || []).find(
					(b) => b.brand === row.from_brand
				);
				if (brand_row && brand_row.unit_definition_by_brand) {
					frappe.model.set_value(
						cdt,
						cdn,
						"uom",
						brand_row.unit_definition_by_brand
					);
				}
			});
		}
	},

	// Recalculate amount when qty or valuation_rate changes
	qty(frm, cdt, cdn) {
		_calculate_row_amount(frm, cdt, cdn);
		frm.trigger("calculate_totals");
		_check_stock_warning(frm, cdt, cdn);
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
 * Uses array-format filters which Frappe's Link field always respects.
 */
function _batch_query(item_code, warehouse) {
	if (!item_code) {
		return {filters: [["Batch", "name", "=", ""]]};
	}
	if (warehouse) {
		// Use server-side query to filter by positive stock in warehouse
		return {
			query: "sh_erp_cost_dept.inventory_management.doctype.multi_dimension_stock_transfer.multi_dimension_stock_transfer.get_batches_for_item_warehouse",
			filters: {item: item_code, warehouse: warehouse},
		};
	}
	// No warehouse — use array-format filter so Frappe honours it without a query fn
	return {
		filters: [["Batch", "item", "=", item_code]],
	};
}

function _calculate_row_amount(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	const amount = flt(row.qty) * flt(row.valuation_rate);
	frappe.model.set_value(cdt, cdn, "amount", amount);
}

/**
 * Shows a non-blocking orange warning if requested qty exceeds available stock.
 * Only runs in Draft (docstatus === 0) to avoid noise on submitted docs.
 */
function _check_stock_warning(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	if (!row.item_code || !row.from_warehouse || !flt(row.qty)) return;
	if (frm.doc.docstatus !== 0) return;

	frappe.call({
		method: "sh_erp_cost_dept.inventory_management.doctype.multi_dimension_stock_transfer.multi_dimension_stock_transfer.get_available_qty",
		args: {
			item_code: row.item_code,
			warehouse: row.from_warehouse,
			batch_no: row.from_batch || null,
			brand: row.from_brand || null,
		},
		callback(r) {
			const available = flt((r && r.message) || 0);
			if (flt(row.qty) > available) {
				frappe.show_alert(
					{
						message: __(
							"Row {0}: Available stock for {1} in {2} is {3} — requested {4}.",
							[
								row.idx,
								row.item_code,
								row.from_warehouse,
								available,
								row.qty,
							]
						),
						indicator: "orange",
					},
					7
				);
			}
		},
	});
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

