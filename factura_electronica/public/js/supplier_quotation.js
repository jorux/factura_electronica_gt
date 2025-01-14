//console.log("Hello world from Supplier Quotation");
import { valNit } from "./facelec.js";

/* Supplier Quotation (Presupuesto Proveedor) ------------------------------------------------------------------------------------------------------- */
function supplier_quotation_each_item(frm, cdt, cdn) {
  // console.log("Recalculando... Supplier Quotation");
  if (cdt === "Supplier Quotation Item") {
    sq_get_special_tax_by_item(frm, cdt, cdn);
    shs_supplier_quotation_calculation(frm, cdt, cdn);

    sq_total_by_item_type(frm);
  } else {
    cdt = "Supplier Quotation Item";
    // Si no es una fila especifica, se iteran todas y se realizan los calculos
    frm.refresh_field("items");
    frm.doc.items.forEach((item_row, index) => {
      cdn = item_row.name;

      sq_get_special_tax_by_item(frm, cdt, cdn);
      shs_supplier_quotation_calculation(frm, cdt, cdn);
    });
    sq_total_by_item_type(frm);
  }
}

/**
 * @summary Vuelve a calcular los totales de FUEL, GOODS, SERVICES e IVA
 * @param {object} frm - Objeto que contiene todas las propiedades del doctype
 */
function sq_total_by_item_type(frm) {
  // console.log("calculo totales")
  let fix_gt_tax_fuel = 0;
  let fix_gt_tax_goods = 0;
  let fix_gt_tax_services = 0;
  let fix_gt_tax_iva = 0;

  $.each(frm.doc.items || [], function (i, d) {
    fix_gt_tax_fuel += flt(d.shs_spq_gt_tax_net_fuel_amt);
    fix_gt_tax_goods += flt(d.shs_spq_gt_tax_net_goods_amt);
    fix_gt_tax_services += flt(d.shs_spq_gt_tax_net_services_amt);
    fix_gt_tax_iva += flt(d.shs_spq_sales_tax_for_this_row);
  });

  cur_frm.set_value("shs_spq_gt_tax_fuel", fix_gt_tax_fuel);
  frm.refresh_field("shs_spq_gt_tax_fuel");

  cur_frm.set_value("shs_spq_gt_tax_goods", fix_gt_tax_goods);
  frm.refresh_field("shs_spq_gt_tax_goods");

  cur_frm.set_value("shs_spq_gt_tax_services", fix_gt_tax_services);
  frm.refresh_field("shs_spq_gt_tax_services");

  cur_frm.set_value("shs_spq_total_iva", fix_gt_tax_iva);
  frm.refresh_field("shs_spq_total_iva");
}

/**
 * @summary Obtiene las cuenta configuradas y monto de impuestos especiales de X item en caso sea de tipo Combustible
 * @param {object} frm - Objeto que contiene todas las propiedades del doctype
 * @param {object} row - Objeto que contiene todas las propiedades de la fila de items que se este manipulando
 */
function sq_get_special_tax_by_item(frm, cdt, cdn) {
  let row = frappe.get_doc(cdt, cdn);

  frm.refresh_field("items");
  if (row.shs_spq_is_fuel && row.item_code) {
    // Peticion para obtener el monto, cuenta venta de impuesto especial de combustible
    // en funcion de item_code y la compania
    frappe.call({
      method: "factura_electronica.api.get_special_tax",
      args: {
        item_code: row.item_code,
        company: frm.doc.company,
      },
      callback: (r) => {
        // Si existe una cuenta configurada para el item
        if (r.message.facelec_tax_rate_per_uom_selling_account) {
          // on success
          frappe.model.set_value(row.doctype, row.name, "shs_spq_tax_rate_per_uom", flt(r.message.facelec_tax_rate_per_uom));
          frappe.model.set_value(
            row.doctype,
            row.name,
            "shs_spq_tax_rate_per_uom_account",
            r.message.facelec_tax_rate_per_uom_selling_account || ""
          );
          frm.refresh_field("items");
        } else {
          // Si no esta configurado el impuesto especial para el item
          frappe.show_alert(
            {
              message: __(
                `El item ${row.item_code}, Fila ${row.idx} de Tipo Combustible.
                     No tiene configuradas las cuentas y monto para Impuesto especiales, por favor configurelo
                     para que se realicen correctamente los calculos o si no es un producto de tipo combustible cambielo a Bien o Servicio`
              ),
              indicator: "red",
            },
            120
          );
        }
      },
    });

    return;
    // Si no es item de tipo combustible
  } else {
    frappe.model.set_value(row.doctype, row.name, "shs_spq_tax_rate_per_uom", flt(0));
    frappe.model.set_value(row.doctype, row.name, "shs_spq_tax_rate_per_uom_account", "");
    frm.refresh_field("items");
  }
}

// Calculos para Cotizacion de proveedor
function shs_supplier_quotation_calculation(frm, cdt, cdn) {
  let item_row = frappe.get_doc(cdt, cdn);
  // console.log("Calculando...", row.item_code, "indice", row.idx);

  frm.refresh_field("items");

  let this_company_sales_tax_var = 0;
  const taxes_tbl = frm.doc.taxes || [];

  // Valida si la compania tiene carga una tabla de impuestos
  if (taxes_tbl.length > 0) {
    this_company_sales_tax_var = taxes_tbl[0].rate;
  } else {
    // Muestra una notificacion para cargar una tabla de impuestos
    frappe.show_alert(
      {
        message: __(
          "Tabla de impuestos no se encuentra cargada, por favor agregarla para que los calculos se generen correctamente"
        ),
        indicator: "red",
      },
      400
    );

    this_company_sales_tax_var = 0;
    return;
  }

  let amount_minus_excise_tax = 0;
  let other_tax_amount = 0;
  let net_fuel = 0;
  let net_services = 0;
  let net_goods = 0;
  let tax_for_this_row = 0;

  other_tax_amount = flt(item_row.shs_spq_tax_rate_per_uom * item_row.qty * item_row.conversion_factor);
  frappe.model.set_value(item_row.doctype, item_row.name, "shs_spq_other_tax_amount", other_tax_amount);

  //OJO!  No s epuede utilizar stock_qty en los calculos, debe de ser qty a puro tubo!
  amount_minus_excise_tax = flt(
    item_row.qty * item_row.rate - item_row.qty * item_row.conversion_factor * item_row.shs_spq_tax_rate_per_uom
  );
  frappe.model.set_value(item_row.doctype, item_row.name, "shs_spq_amount_minus_excise_tax", amount_minus_excise_tax);

  if (item_row.shs_spq_is_fuel && item_row.item_code) {
    net_services = 0;
    net_goods = 0;
    net_fuel = flt(item_row.shs_spq_amount_minus_excise_tax / (1 + this_company_sales_tax_var / 100));
    frappe.model.set_value(item_row.doctype, item_row.name, "shs_spq_gt_tax_net_fuel_amt", flt(net_fuel));

    tax_for_this_row = flt(item_row.shs_spq_gt_tax_net_fuel_amt * (this_company_sales_tax_var / 100));
    frappe.model.set_value(item_row.doctype, item_row.name, "shs_spq_sales_tax_for_this_row", tax_for_this_row);

    // Los campos de bienes y servicios se resetean a 0
    frappe.model.set_value(item_row.doctype, item_row.name, "shs_spq_gt_tax_net_goods_amt", flt(net_goods));
    frappe.model.set_value(item_row.doctype, item_row.name, "shs_spq_gt_tax_net_services_amt", flt(net_services));
  }

  tax_for_this_row = 0;
  if (item_row.shs_spq_is_good && item_row.item_code) {
    net_services = 0;
    net_fuel = 0;
    net_goods = flt(item_row.shs_spq_amount_minus_excise_tax / (1 + this_company_sales_tax_var / 100));
    frappe.model.set_value(item_row.doctype, item_row.name, "shs_spq_gt_tax_net_goods_amt", flt(net_goods));

    tax_for_this_row = flt(item_row.shs_spq_gt_tax_net_goods_amt * (this_company_sales_tax_var / 100));
    frappe.model.set_value(item_row.doctype, item_row.name, "shs_spq_sales_tax_for_this_row", flt(tax_for_this_row));

    // Los campos de servicios y combustibles se resetean a 0
    frappe.model.set_value(item_row.doctype, item_row.name, "shs_spq_gt_tax_net_services_amt", flt(net_services));
    frappe.model.set_value(item_row.doctype, item_row.name, "shs_spq_gt_tax_net_fuel_amt", flt(net_fuel));
  }

  if (item_row.shs_spq_is_service && item_row.item_code) {
    net_fuel = 0;
    net_goods = 0;
    net_services = flt(item_row.shs_spq_amount_minus_excise_tax / (1 + this_company_sales_tax_var / 100));
    frappe.model.set_value(item_row.doctype, item_row.name, "shs_spq_gt_tax_net_services_amt", flt(net_services));

    tax_for_this_row = flt(item_row.shs_spq_gt_tax_net_services_amt * (this_company_sales_tax_var / 100));
    frappe.model.set_value(item_row.doctype, item_row.name, "shs_spq_sales_tax_for_this_row", flt(tax_for_this_row));

    // Los campos de bienes y combustibles se resetean a 0
    frappe.model.set_value(item_row.doctype, item_row.name, "shs_spq_gt_tax_net_goods_amt", flt(net_goods));
    frappe.model.set_value(item_row.doctype, item_row.name, "shs_spq_gt_tax_net_fuel_amt", flt(net_fuel));
  }

  frm.refresh_field("items");
}

/**
 * @summary Calculador de montos para generar documentos electronicos
 * @param {Object} frm - Propiedades del Doctype
 */
function supplier_quotation_calc(frm) {
  frappe.call({
    method: "factura_electronica.utils.calculator.supplier_quotation_calculator",
    args: {
      invoice_name: frm.doc.name,
    },
    freeze: true,
    freeze_message: __("Calculating") + " 📄📄📄",
    callback: (r) => {
      frm.reload_doc();
      // console.log("Supplier Quotation Calculated");
      // frm.save();
    },
    error: (r) => {
      // on error
      // console.log("Supplier Quotation Calculated Error");
    },
  });
  frm.reload_doc();
}

frappe.ui.form.on("Supplier Quotation", {
  onload_post_render: function (frm, cdt, cdn) {},
  shs_spq_nit: function (frm) {
    // Funcion para validar NIT: Se ejecuta cuando exista un cambio en el campo de NIT
    // valNit(frm.doc.shs_spq_nit, frm.doc.supplier, frm);
  },
  discount_amount: function (frm) {
    // Trigger Monto de descuento
    var tax_before_calc = frm.doc.shs_spq_total_iva;
    // es-GT: Este muestra el IVA que se calculo por medio de nuestra aplicación.
    var discount_amount_net_value = frm.doc.discount_amount / (1 + cur_frm.doc.taxes[0].rate / 100);

    if (isNaN(discount_amount_net_value) || discount_amount_net_value == undefined) {
    } else {
      // console.log("El descuento parece ser un numero definido, calculando con descuento.");
      discount_amount_tax_value = discount_amount_net_value * (cur_frm.doc.taxes[0].rate / 100);
      // console.log("El IVA del descuento es:" + discount_amount_tax_value);
      frm.doc.shs_spq_total_iva = frm.doc.shs_spq_total_iva - discount_amount_tax_value;
      // console.log("El IVA ya sin el iva del descuento es ahora:" + frm.doc.facelec_total_iva);
    }
  },
  before_save: function (frm, cdt, cdn) {
    // supplier_quotation_each_item(frm, cdt, cdn);
  },
  // Se ejecuta despues de guardar el doc
  after_save: function (frm, cdt, cdn) {
    supplier_quotation_calc(frm);
  },
  validate: function (frm, cdt, cdn) {
    // supplier_quotation_each_item(frm, cdt, cdn);

    let taxes = frm.doc.taxes || [];
    if (taxes.length == 0) {
      // Muestra una notificacion para cargar una tabla de impuestos
      frappe.show_alert(
        {
          message: __(
            "Tabla de impuestos no se encuentra cargada, por favor agregarla para que los calculos se generen correctamente"
          ),
          indicator: "red",
        },
        400
      );
    }
  },
});

// frappe.ui.form.on("Supplier Quotation Item", {
//   before_items_remove: function (frm) {
//     sq_total_by_item_type(frm);
//   },
//   items_move: function (frm) {
//     sq_total_by_item_type(frm);
//   },
//   items_remove: function (frm, cdt, cdn) {
//     sq_total_by_item_type(frm);
//   },
//   // NOTA: SI el proceso se realentiza al momento de agregar/duplicar filas comentar este bloque de codigo
//   items_add: function (frm, cdt, cdn) {
//     supplier_quotation_each_item(frm, cdt, cdn);
//   },
//   item_code: function (frm, cdt, cdn) {
//     supplier_quotation_each_item(frm, cdt, cdn);
//   },
//   qty: function (frm, cdt, cdn) {
//     supplier_quotation_each_item(frm, cdt, cdn);
//   },
//   conversion_factor: function (frm, cdt, cdn) {
//     supplier_quotation_each_item(frm, cdt, cdn);
//   },
//   rate: function (frm, cdt, cdn) {
//     supplier_quotation_each_item(frm, cdt, cdn);
//   },
// });

/* ----------------------------------------------------------------------------------------------------------------- */
