// Copyright (c) 2024, Amir Mansi and contributors
// For license information, please see license.txt

/**
 * Advanced Inventory Dimension Report
 * ------------------------------------
 * Client-side filter configuration for the Script Report.
 * Mirrors a Dynamics 365 Finance-style parameter panel with:
 *   - Yes/No dimension toggles
 *   - Multi-select filters for Items, Warehouses, Brands, Batches
 *   - Date range filters
 *   - "Generate PDF" action button
 */

frappe.query_reports["Advanced Inventory Dimension Report"] = {
	filters: [
		// ----------------------------------------------------------------
		// Company
		// ----------------------------------------------------------------
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
			reqd: 1,
		},

		// ----------------------------------------------------------------
		// Date parameters
		// ----------------------------------------------------------------
		{
			fieldname: "as_of_date",
			label: __("As of Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
		},

		// ----------------------------------------------------------------
		// Multi-select filters
		// ----------------------------------------------------------------
		{
			fieldname: "items",
			label: __("Items"),
			fieldtype: "MultiSelectList",
			get_data: function (txt) {
				return frappe.db.get_link_options("Item", txt);
			},
		},
		{
			fieldname: "warehouses",
			label: __("Warehouses"),
			fieldtype: "MultiSelectList",
			get_data: function (txt) {
				return frappe.db.get_link_options("Warehouse", txt);
			},
		},
		{
			fieldname: "brands",
			label: __("Brands"),
			fieldtype: "MultiSelectList",
			get_data: function (txt) {
				return frappe.db.get_link_options("Brand", txt);
			},
		},
		{
			fieldname: "batches",
			label: __("Batches"),
			fieldtype: "MultiSelectList",
			get_data: function (txt) {
				return frappe.db.get_link_options("Batch", txt);
			},
		},

		// ----------------------------------------------------------------
		// Dimension toggles  (Yes / No)
		// ----------------------------------------------------------------
		{
			fieldname: "show_warehouse",
			label: __("Show Warehouse"),
			fieldtype: "Select",
			options: "Yes\nNo",
			default: "Yes",
		},
		{
			fieldname: "show_batch",
			label: __("Show Batch"),
			fieldtype: "Select",
			options: "Yes\nNo",
			default: "Yes",
		},
		{
			fieldname: "show_brand",
			label: __("Show Brand"),
			fieldtype: "Select",
			options: "Yes\nNo",
			default: "Yes",
		},
		{
			fieldname: "show_item_group",
			label: __("Show Item Group"),
			fieldtype: "Select",
			options: "Yes\nNo",
			default: "No",
		},
	],

	// ----------------------------------------------------------------
	// Formatter — highlight negative qty in red
	// ----------------------------------------------------------------
	formatter: function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "qty_on_hand" && flt(data["qty_on_hand"]) < 0) {
			value = `<span style="color:red">${value}</span>`;
		}
		return value;
	},

	// ----------------------------------------------------------------
	// Custom buttons
	// ----------------------------------------------------------------
	onload: function (report) {
		report.page.add_inner_button(__("Generate PDF"), function () {
			_generate_pdf(report);
		});
	},
};

// -----------------------------------------------------------------------
// PDF generation
// -----------------------------------------------------------------------

function _generate_pdf(report) {
	const filters = report.get_filter_values(true);
	if (!filters) return;

	frappe.call({
		method: "sh_erp_cost_dept.inventory_management.report.advanced_inventory_dimension_report.advanced_inventory_dimension_report.generate_pdf_report",
		args: {filters: filters},
		callback: function (r) {
			if (r.message) {
				const w = window.open();
				w.document.open();
				w.document.write(r.message);
				w.document.close();
				setTimeout(() => w.print(), 800);
			}
		},
	});
}
