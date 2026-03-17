// Copyright (c) 2024, Amir Mansi and contributors
// For license information, please see license.txt

/**
 * Item Brand & UOM Control — Centralized Module
 * ===============================================
 * A single, reusable implementation of Item Brand / UOM filtering and
 * validation for all supported transaction DocTypes.
 *
 * Supported DocTypes (configured via DOCTYPE_CONFIG):
 *   Sales Order, Purchase Order, Delivery Note, Stock Entry,
 *   Work Order, BOM, Material Request
 *
 * How it works
 * ------------
 * 1. When a form loads, set_query filters are registered for the
 *    `custom_item_brand` and `uom` fields in each items child table.
 * 2. When `item_code` changes, item data is fetched from the server and
 *    cached in memory (allowed brands + allowed UOMs).
 * 3. When `custom_item_brand` changes the brand-specific UOM is
 *    auto-applied if one is defined on the Item's custom_brands table.
 * 4. Server-side validation (Python) enforces data integrity on save /
 *    submit independently of the UI layer.
 *
 * NOTE: If you have existing per-DocType Client Scripts for Purchase
 * Order (or any other DocType below) that implement the same Brand /
 * UOM logic, remove them to avoid duplicate event handlers. This
 * module supersedes those scripts.
 */

;(function () {
	"use strict";

	/**
	 * Supported DocType → child table configuration.
	 * Add an entry here to extend the system to a new DocType.
	 *
	 * @type {Object.<string, {table: string, child_doctype: string, brand_field: string}>}
	 */
	const DOCTYPE_CONFIG = {
		"Sales Order": {
			table: "items",
			child_doctype: "Sales Order Item",
			brand_field: "custom_item_brand",
		},
		"Purchase Order": {
			table: "items",
			child_doctype: "Purchase Order Item",
			brand_field: "custom_item_brand",
		},
		"Delivery Note": {
			table: "items",
			child_doctype: "Delivery Note Item",
			brand_field: "custom_item_brand",
		},
		"Material Request": {
			table: "items",
			child_doctype: "Material Request Item",
			brand_field: "custom_item_brand",
		},
		BOM: {
			table: "items",
			child_doctype: "BOM Item",
			brand_field: "custom_item_brand",
		},
		"Work Order": {
			table: "required_items",
			child_doctype: "Work Order Item",
			brand_field: "custom_item_brand",
		},
		"Stock Entry": {
			table: "items",
			child_doctype: "Stock Entry Detail",
			brand_field: "custom_item_brand",
		},
	};

	// -----------------------------------------------------------------------
	// In-memory cache: cdn (child row name) → { brands, uoms, item_doc }
	// This avoids storing data in hidden fields and eliminates the need for
	// extra database columns on each child table.
	// -----------------------------------------------------------------------

	/** @type {Object.<string, {brands: string[], uoms: string[], item_doc: object|null}>} */
	const _cache = {};

	/**
	 * Fetch item data from the server and store it in the cache.
	 *
	 * @param {string}        item_code
	 * @param {string}        cdn      - Child row name (cache key)
	 * @param {function|null} callback - Called with the cached entry when done
	 */
	function _fetchAndCache(item_code, cdn, callback) {
		frappe.db
			.get_doc("Item", item_code)
			.then(function (item_doc) {
				// Collect allowed brands from the custom_brands child table
				const brands = (item_doc.custom_brands || [])
					.map(function (d) {
						return d.brand;
					})
					.filter(Boolean);

				// Collect allowed UOMs: stock UOM + all conversion UOMs
				const uoms = item_doc.stock_uom ? [item_doc.stock_uom] : [];
				(item_doc.uoms || []).forEach(function (u) {
					if (u.uom && uoms.indexOf(u.uom) === -1) {
						uoms.push(u.uom);
					}
				});

				_cache[cdn] = {brands: brands, uoms: uoms, item_doc: item_doc};

				if (typeof callback === "function") {
					callback(_cache[cdn]);
				}
			})
			.catch(function () {
				// On fetch error keep empty cache so queries remain open
				_cache[cdn] = {brands: [], uoms: [], item_doc: null};
				if (typeof callback === "function") {
					callback(_cache[cdn]);
				}
			});
	}

	/**
	 * Return cached data for a row, or safe empty defaults.
	 *
	 * @param   {string} cdn
	 * @returns {{brands: string[], uoms: string[], item_doc: object|null}}
	 */
	function _getCached(cdn) {
		return _cache[cdn] || {brands: [], uoms: [], item_doc: null};
	}

	// -----------------------------------------------------------------------
	// Form-level helpers
	// -----------------------------------------------------------------------

	/**
	 * Register set_query filters on the parent form.
	 * Called on both `onload` and `refresh` so that filters are always active
	 * even after the form is reloaded from cache.
	 *
	 * @param {object}                               frm
	 * @param {{table: string, brand_field: string}} config
	 */
	function _setupFormQueries(frm, config) {
		const table = config.table;
		const brand_field = config.brand_field;

		// Brand field — restrict to brands defined on the Item
		frm.set_query(brand_field, table, function (doc, cdt, cdn) {
			const row = locals[cdt][cdn];
			if (!row || !row.item_code) {
				return {filters: [["Brand", "name", "=", "__no_item__"]]};
			}
			const data = _getCached(cdn);
			const list = data.brands.length ? data.brands : ["__no_brand__"];
			return {filters: [["Brand", "name", "in", list]]};
		});

		// UOM field — restrict to UOMs allowed for the Item
		frm.set_query("uom", table, function (doc, cdt, cdn) {
			const row = locals[cdt][cdn];
			if (!row || !row.item_code) return {};
			const data = _getCached(cdn);
			if (!data.uoms.length) return {};
			return {filters: [["UOM", "name", "in", data.uoms]]};
		});
	}

	/**
	 * Pre-populate the cache for all existing rows so that set_query filters
	 * work immediately when editing a previously-saved document.
	 *
	 * @param {object}             frm
	 * @param {{table: string}}    config
	 */
	function _preCacheRows(frm, config) {
		const rows = frm.doc[config.table] || [];
		rows.forEach(function (row) {
			if (row.item_code && !_cache[row.name]) {
				_fetchAndCache(row.item_code, row.name, null);
			}
		});
	}

	// -----------------------------------------------------------------------
	// Child row event handlers
	// -----------------------------------------------------------------------

	/**
	 * Handle item_code change:
	 *   – Fetch & cache item data so that set_query filters have fresh data.
	 *   – Clear the brand field when the selected brand is not valid for
	 *     the new item.
	 *
	 * @param {object}                                          frm
	 * @param {string}                                          cdt
	 * @param {string}                                          cdn
	 * @param {{table: string, brand_field: string}}            config
	 */
	function _onItemCodeChange(frm, cdt, cdn, config) {
		const row = locals[cdt][cdn];
		const brand_field = config.brand_field;

		if (!row || !row.item_code) {
			delete _cache[cdn];
			frappe.model.set_value(cdt, cdn, brand_field, "");
			return;
		}

		_fetchAndCache(row.item_code, cdn, function (data) {
			// Invalidate brand if it no longer belongs to the new item
			const current_brand = (locals[cdt][cdn] || {})[brand_field];
			if (
				current_brand &&
				data.brands.length > 0 &&
				data.brands.indexOf(current_brand) === -1
			) {
				frappe.model.set_value(cdt, cdn, brand_field, "");
			}
			frm.refresh_field(config.table);
		});
	}

	/**
	 * Handle custom_item_brand change:
	 *   – Auto-set the UOM to the brand-specific unit when one is defined
	 *     on the Item's custom_brands child table.
	 *
	 * @param {object}                         frm
	 * @param {string}                         cdt
	 * @param {string}                         cdn
	 * @param {{brand_field: string}}          config
	 */
	function _onBrandChange(frm, cdt, cdn, config) {
		const row = locals[cdt][cdn];
		if (!row || !row.item_code) return;

		const selected_brand = row[config.brand_field];
		if (!selected_brand) return;

		function _applyBrandUom(item_doc) {
			const brand_row = (item_doc.custom_brands || []).find(function (d) {
				return d.brand === selected_brand;
			});
			if (brand_row && brand_row.unit_definition_by_brand) {
				frappe.model.set_value(
					cdt,
					cdn,
					"uom",
					brand_row.unit_definition_by_brand
				);
			}
		}

		const cached = _getCached(cdn);
		if (cached.item_doc) {
			_applyBrandUom(cached.item_doc);
		} else {
			_fetchAndCache(row.item_code, cdn, function (data) {
				if (data.item_doc) _applyBrandUom(data.item_doc);
			});
		}
	}

	// -----------------------------------------------------------------------
	// Auto-register handlers for every configured DocType
	// -----------------------------------------------------------------------

	Object.keys(DOCTYPE_CONFIG).forEach(function (doctype) {
		const config = DOCTYPE_CONFIG[doctype];

		// Parent form events
		frappe.ui.form.on(doctype, {
			onload: function (frm) {
				_setupFormQueries(frm, config);
				_preCacheRows(frm, config);
			},
			refresh: function (frm) {
				_setupFormQueries(frm, config);
			},
		});

		// Child table events — build event map dynamically so that the
		// brand field name is used as the event key.
		const child_events = {
			item_code: function (frm, cdt, cdn) {
				_onItemCodeChange(frm, cdt, cdn, config);
			},
		};
		child_events[config.brand_field] = function (frm, cdt, cdn) {
			_onBrandChange(frm, cdt, cdn, config);
		};

		frappe.ui.form.on(config.child_doctype, child_events);
	});
})();
