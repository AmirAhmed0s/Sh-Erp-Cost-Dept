// Copyright (c) 2024, Amir Mansi and contributors
// For license information, please see license.txt

/**
 * User Assignment Control
 * -----------------------
 * Provides a modern card-style UI for the manager field and dynamic
 * visibility of the Allowed DocTypes child table based on Apply Scope.
 */

frappe.ui.form.on("User Assignment Control", {
	refresh(frm) {
		frm.trigger("render_manager_card");
		frm.trigger("toggle_doctypes_section");
	},

	apply_scope(frm) {
		frm.trigger("toggle_doctypes_section");
	},

	manager(frm) {
		frm.trigger("render_manager_card");
	},

	// ------------------------------------------------------------------ //
	// Show/hide Allowed DocTypes section based on Apply Scope
	// ------------------------------------------------------------------ //
	toggle_doctypes_section(frm) {
		const is_custom = frm.doc.apply_scope === "Custom Selection";
		frm.toggle_display("allowed_doctypes_section", is_custom);
		frm.toggle_display("allowed_doctypes", is_custom);
	},

	// ------------------------------------------------------------------ //
	// Render a highlighted card for the Manager field
	// ------------------------------------------------------------------ //
	render_manager_card(frm) {
		// Remove any existing card
		frm.fields_dict["manager"].$wrapper
			.find(".manager-highlight-card")
			.remove();

		if (!frm.doc.manager) return;

		const full_name = frm.doc.manager_full_name || frm.doc.manager;
		const avatar_letter = (full_name || "?")[0].toUpperCase();

		const card_html = `
			<div class="manager-highlight-card" style="
				display: flex;
				align-items: center;
				gap: 12px;
				background: linear-gradient(135deg, #e8f4fd 0%, #d1ecf1 100%);
				border: 1px solid #bee5eb;
				border-radius: 10px;
				padding: 12px 16px;
				margin-top: 8px;
				box-shadow: 0 2px 6px rgba(0,0,0,0.06);
			">
				<div style="
					width: 42px;
					height: 42px;
					border-radius: 50%;
					background: linear-gradient(135deg, #17a2b8, #138496);
					display: flex;
					align-items: center;
					justify-content: center;
					color: #fff;
					font-size: 18px;
					font-weight: 700;
					flex-shrink: 0;
				">${avatar_letter}</div>
				<div>
					<div style="font-weight: 700; font-size: 14px; color: #0c5460;">
						${frappe.utils.escape_html(full_name)}
					</div>
					<div style="font-size: 12px; color: #6c757d; margin-top: 2px;">
						${frappe.utils.escape_html(frm.doc.manager)}
					</div>
				</div>
				<div style="margin-left:auto;">
					<span style="
						background: ${frm.doc.is_active ? "#28a745" : "#dc3545"};
						color: #fff;
						font-size: 11px;
						padding: 3px 10px;
						border-radius: 12px;
						font-weight: 600;
					">${frm.doc.is_active ? __("Active") : __("Inactive")}</span>
				</div>
			</div>`;

		frm.fields_dict["manager"].$wrapper.append(card_html);
	},
});
