# -*- coding: utf-8 -*-
# Copyright (c) 2017, Frappe and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

import frappe
from frappe import _
from frappe.model.document import Document


class ConfiguracionFacturaElectronica(Document):
    pass
# es-GT: Se hace whitelist o abre permiso para permitir llamados Asincronicos desde el navegador del usuario
# en-US: Whitelisting the function to permit Asyncrhonous calls from the user's web browser
# es-GT: Esta funcion obtiene el contenido del campo "Naming Series" configurada por el usuario para "Sale Invoice". (Las series configuradas por el usuario para Facturas de Venta)
# es-GT: Luego de obtenerlas, se separan las series por cada linea, usando el indicador de escape de nueva linea: "\n"
# es-GT: Retorna cada una de las series como lista o diccionario FIXME (No estoy seguro!)
# en-US: This function obtains the contents of "Naming Series" field for "Sales Invoice", a field which lists the series configured by the user.
# en-US: After obtaining them, the series are separated by each new line, using the new line excape character "\n"
# en-US: Returns the naming_series as a list or dictionary. FIXME (Not sure!)
@frappe.whitelist()
def series_sales_invoice():
    naming_series = frappe.get_meta("Sales Invoice").get_field("naming_series").options or ""
    naming_series = naming_series.split("\n")
    #out = naming_series[0] or (naming_series[1] if len(naming_series) > 1 else None)

    return naming_series

@frappe.whitelist()
def series_factura_especial():
    series = frappe.get_meta("Purchase Invoice").get_field("naming_series").options or ""
    series = series.split('\n')

    return series


@frappe.whitelist()
def get_phrases_fel(code_type):
    series = frappe.get_meta("Frases FEL").get_field("name").options or ""
    series = series.split('\n')

    return series
