# Copyright (c) 2020, Si Hay Sistema and contributors
# For license information, please see license.txt

# Copyright (c) 2020, Si Hay Sistema and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

import base64
import datetime
import json
import frappe
import requests
import xmltodict
from frappe import _, _dict
from frappe.utils import cint, flt, get_datetime, nowdate, nowtime

from factura_electronica.utils.utilities_facelec import get_currency_precision, remove_html_tags

# EN RESUMEN, ES DEVOLUCION DESDE SALES INVOICE sin iva
class ElectronicAbonoNote:
    def __init__(self, actual_inv_name, invoice_code, conf_name, naming_series, emisor_data, receptor_data, items):
        """__init__
        Constructor de la clase, las propiedades iniciadas como privadas

        Args:
            actual_inv_name (str): Nombre actual de la factura
            invoice_code (str): Serie original de la factura
            conf_name (str): Nombre configuracion para factura electronica
            naming_series (str): Serie de nombres
            emisor_data (dict): Datos del emisor
            receptor_data (dict): Datos del receptor
            items (list): Lista de items
        """
        self.__actual_inv_name = actual_inv_name
        self.__invoice_code = invoice_code  # HACE REFERENCIA A LA FACT FEL
        self.__config_name = conf_name
        self.__naming_serie = naming_series
        self.__log_error = []
        self.__precision = get_currency_precision()
        self.__tiene_adenda = False

        # Datos del emisor
        self.emisor_data = emisor_data

        # Datos del receptor
        self.receptor_data = receptor_data

        # Items de la nota
        self.items = items

    def build_abono_note(self):
        """
        Valida las dependencias necesarias, para construir XML desde un JSON
        para ser firmado certificado por la SAT y finalmente generar factura electronica

        Returns:
            tuple: True/False, msj, msj
        """
        try:
            # 1 Validamos la data antes de construir
            status_validate = self.validate()

            if status_validate[0]:
                # 2 - Asignacion y creacion base peticion para luego ser convertida a XML
                self.__base_peticion = {
                    "dte:GTDocumento": {
                        "@xmlns:ds": "http://www.w3.org/2000/09/xmldsig#",
                        "@xmlns:dte": "http://www.sat.gob.gt/dte/fel/0.2.0",
                        "@xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
                        "dte:SAT": {
                            "@ClaseDocumento": "dte",
                            "dte:DTE": {
                                "@ID": "DatosCertificados",
                                "dte:DatosEmision": {
                                    "@ID": "DatosEmision",
                                    "dte:DatosGenerales": {
                                        "@CodigoMoneda": self.emisor_data.get('CodigoMoneda', 'GTQ'),
                                        "@FechaHoraEmision": datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S-06:00"),
                                        "@Tipo": "NABN"
                                    },
                                    "dte:Emisor": {
                                        "@AfiliacionIVA": self.emisor_data.get('AfiliacionIVA', 'GEN'),
                                        "@CodigoEstablecimiento": self.emisor_data.get('CodigoEstablecimiento', '1'),
                                        "@NITEmisor": self.emisor_data.get('NITEmisor', '9000000000K'),
                                        "@NombreComercial": self.emisor_data.get('NombreComercial', 'INFILE, SOCIEDAD ANONIMA'),
                                        "@NombreEmisor": self.emisor_data.get('NombreEmisor', 'INFILE, SOCIEDAD ANONIMA'),
                                        "dte:DireccionEmisor": {
                                            "dte:Direccion": self.emisor_data.get('Direccion', 'CUIDAD'),
                                            "dte:CodigoPostal": self.emisor_data.get('CodigoPostal', '01010'),
                                            "dte:Municipio": self.emisor_data.get('Municipio', 'GUATEMALA'),
                                            "dte:Departamento": self.emisor_data.get('Departamento', 'GUATEMALA'),
                                            "dte:Pais": self.emisor_data.get('Pais', 'GT')
                                        }
                                    },
                                    "dte:Receptor": {
                                        "@IDReceptor": self.receptor_data.get('IDReceptor', 'CF'),
                                        "@NombreReceptor": self.receptor_data.get('NombreReceptor', 'CONSUMIDOR FINAL'),
                                        "dte:DireccionReceptor": {
                                            "dte:Direccion": self.receptor_data.get('Direccion', 'CUIDAD'),
                                            "dte:CodigoPostal": self.receptor_data.get('CodigoPostal', '01010'),
                                            "dte:Municipio": self.receptor_data.get('Municipio', 'GUATEMALA'),
                                            "dte:Departamento": self.receptor_data.get('Departamento', 'GUATEMALA'),
                                            "dte:Pais": self.receptor_data.get('Pais', 'GT')
                                        }
                                    },
                                    "dte:Items": {
                                        "dte:Item": [
                                            {
                                                "@BienOServicio": item.get('BienOServicio', 'B'),
                                                "@NumeroLinea": str(index + 1),
                                                "dte:Cantidad": "{:.2f}".format(item.get('Cantidad', 1.00)),
                                                "dte:UnidadMedida": item.get('UnidadMedida', 'UNI'),
                                                "dte:Descripcion": item.get('Descripcion', 'SIN DESCRIPCION'),
                                                "dte:PrecioUnitario": "{:.2f}".format(item.get('PrecioUnitario', 0.00)),
                                                "dte:Precio": "{:.2f}".format(item.get('Precio', 0.00)),
                                                "dte:Descuento": "{:.2f}".format(item.get('Descuento', 0.00)),
                                                "dte:Total": "{:.2f}".format(item.get('Total', 0.00))
                                            } for index, item in enumerate(self.items)
                                        ]
                                    },
                                    "dte:Totales": {
                                        "dte:GranTotal": "{:.2f}".format(sum(item.get('Total', 0.00) for item in self.items))
                                    }
                                }
                            }
                        }
                    }
                }
                # Convertir la petición a XML
                xml_data = xmltodict.unparse(self.__base_peticion, pretty=True)
                # Aquí puedes agregar el código para enviar el XML a la SAT y manejar la respuesta

                return True, "Nota de abono construida correctamente", xml_data
            else:
                return False, "Error en la validación de los datos", status_validate[1]

        except Exception as e:
            frappe.log_error(message=str(e), title="Error en la construcción de la nota de abono")
            return False, "Ocurrió un error en la construcción de la nota de abono", str(e)

    def validate(self):
        """
        Realiza las validaciones necesarias antes de construir la nota de abono

        Returns:
            tuple: True/False, mensaje de validación
        """
        # Aquí puedes agregar tus validaciones personalizadas
        return True, "Validación exitosa"
