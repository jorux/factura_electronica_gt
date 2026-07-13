// pos_extension.js
frappe.provide('factura_electronica');

$(document).on('app_ready', function() {
    if (frappe.get_route()[0] === 'point-of-sale') {
        setup_pos_fel_button();
    }
});

frappe.router.on('change', () => {
    if (frappe.get_route()[0] === 'point-of-sale') {
        setup_pos_fel_button();
    }
});

function setup_pos_fel_button() {
    // We use a MutationObserver to watch for the "Print Receipt" or similar button
    // in the POS success screen or past order summary.
    const observer = new MutationObserver((mutations) => {
        // Find the container with summary buttons
        const $summaryBtns = $('.summary-btns, .invoice-summary-wrapper .btn-group, .past-order-summary .btn-group, .receipt-section');
        
        if ($summaryBtns.length > 0 && $('#btn-view-fel').length === 0) {
            // We found a place to inject our button, let's inject it.
            // But we need the invoice name!
            // In POS, the current invoice is usually stored in the controller or in the DOM.
            // Let's try to extract it from the DOM. 
            // Often, the invoice name is in a header like `.invoice-name` or `.title`
            
            let btnHtml = `<button id="btn-view-fel" class="btn btn-secondary btn-sm" style="margin-top: 10px; width: 100%;">
                <i class="fa fa-file-pdf-o"></i> View FEL PDF
            </button>`;
            
            // Try to append it to the actions container
            if ($('.summary-btns').length > 0) {
                 $('.summary-btns').append(btnHtml);
            } else {
                 $summaryBtns.first().append(btnHtml);
            }

            $('#btn-view-fel').on('click', function() {
                // Find invoice name. It's typically stored in the controller's state or DOM.
                // We can fetch the latest POS invoice for this user if we can't find it in the DOM.
                let invoice_name = $('.invoice-name').text() || $('.title').text() || '';
                invoice_name = invoice_name.trim();

                if (!invoice_name) {
                    // Fallback: fetch the latest POS Invoice for the current user
                    frappe.call({
                        method: 'frappe.client.get_list',
                        args: {
                            doctype: 'POS Invoice',
                            filters: { owner: frappe.session.user, docstatus: 1 },
                            fields: ['name', 'numero_autorizacion_fel'],
                            order_by: 'creation desc',
                            limit_page_length: 1
                        },
                        callback: function(r) {
                            if (r.message && r.message.length > 0) {
                                let inv = r.message[0];
                                if (inv.numero_autorizacion_fel) {
                                    window.open("https://report.feel.com.gt/ingfacereport/ingfacereport_documento?uuid=" + inv.numero_autorizacion_fel);
                                } else {
                                    frappe.show_alert("No FEL Authorization Number found for the latest invoice.");
                                }
                            }
                        }
                    });
                } else {
                    // If we found the invoice name in DOM
                    frappe.db.get_value('POS Invoice', invoice_name, 'numero_autorizacion_fel')
                        .then(r => {
                            if (r && r.message && r.message.numero_autorizacion_fel) {
                                window.open("https://report.feel.com.gt/ingfacereport/ingfacereport_documento?uuid=" + r.message.numero_autorizacion_fel);
                            } else {
                                frappe.show_alert("No FEL Authorization Number found for this invoice.");
                            }
                        });
                }
            });
        }
    });

    // Start observing the POS app wrapper
    const posWrapper = document.getElementById('page-point-of-sale');
    if (posWrapper) {
        observer.observe(posWrapper, { childList: true, subtree: true });
    } else {
        // If not rendered yet, wait a bit
        setTimeout(() => {
            const wrapper = document.getElementById('page-point-of-sale');
            if (wrapper) {
                observer.observe(wrapper, { childList: true, subtree: true });
            }
        }, 2000);
    }
}
