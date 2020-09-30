# -*- coding: utf-8 -*-
# Copyright (c) 2020, Si Hay Sistema and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.model.document import Document
import json


class VATDeclaration(Document):
    def before_cancel(self):
        """
        Se ejecuta al momento antes de cancelar un documento, por cada doctype
        donde se encuentre una referencia, actualizara el campo a un valor vacio
        """
        pass

    def on_cancel(self):
        """
        Se ejecuta al momento de cancelar un documento, por cada doctype
        donde se encuentre una referencia, actualizara el campo a un valor vacio
        """
        # Por cada declaracion
        for declaration in self.declaration_items:
            # Validacion extra, si existe
            if frappe.db.exists(declaration.get('link_doctype'), {'name': declaration.get('link_name')}):

                if declaration.get('link_doctype') == 'Sales Invoice':
                    frappe.db.sql(
                        f'''
                            UPDATE `tabSales Invoice` SET facelec_s_vat_declaration=""
                            WHERE name="{declaration.get('link_name')}"
                        ''')  # actualiza a un valor ""

                if declaration.get('link_doctype') == 'Purchase Invoice':
                    frappe.db.sql(
                    f'''
                        UPDATE `tabPurchase Invoice` SET facelec_p_vat_declaration=""
                        WHERE name="{declaration.get('link_name')}"
                    ''')  # actualiza a un valor ""

    def on_submit(self):
        """
        Se ejecuta cuando un documento se valida manualmente, actualizando las referencias en
        otros doctypes
        """
        # Por cada declaracion
        for declaration in self.declaration_items:
            # Validacion extra, si no existe
            if frappe.db.exists(declaration.get('link_doctype'), {'name': declaration.get('link_name')}):

                if declaration.get('link_doctype') == 'Sales Invoice':
                    frappe.db.sql(
                        f'''
                            UPDATE `tabSales Invoice` SET facelec_s_vat_declaration="{self.name}"
                            WHERE name="{declaration.get('link_name')}"
                        ''')  # actualiza a un valor ""

                if declaration.get('link_doctype') == 'Purchase Invoice':
                    frappe.db.sql(
                    f'''
                        UPDATE `tabPurchase Invoice` SET facelec_p_vat_declaration="{self.name}"
                        WHERE name="{declaration.get('link_name')}"
                    ''')  # actualiza a un valor ""


@frappe.whitelist()
def calculate_total(invoices):
    """
    Obtiene el total de todas las facturas que se esten trabajando en el doctype VAT Declaration,
    si existe algun error retorna 0, para no provocar confusion al usuario

    Args:
        invoices (list): Lista diccionarios de facturas cargadas en la tabla hija

    Returns:
        float: total
    """

    try:
        # NOTA: Siempre que queramos leer un array enviado por JS lo cargamos con loads
        invoice_list = json.loads(invoices)

        total = 0
        for invoice in invoice_list:  # Por cada factura
            doctype_inv = invoice.get('link_doctype')  # Puede ser Sales/Purchase Invoice

            # Acumulamos el grand total de cada factura iterada
            grand_total_inv = frappe.db.get_value(doctype_inv, {'name': invoice.get('link_name')}, 'grand_total') or 0
            total += grand_total_inv

        return total

    except:
        return 0
