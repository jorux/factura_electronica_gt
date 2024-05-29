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
    def __init__(self, actual_inv_name, invoice_code, naming_series):
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
        self.__naming_serie = naming_series
        self.__log_error = []
        self.__precision = get_currency_precision()
        self.__tiene_adenda = False

        # Datos del emisor
    def sender(self):
        """
        Valida y obtiene la data necesaria para la seccion de Emisor,
        entidad que emite la factura

        Returns:
            tuple: True/False, msj, msj
        """

        try:
            # De la factura obtenemos la compañia y direccion compañia emisora
            self.dat_fac = frappe.db.get_values('Sales Invoice', filters={'name': self.__inv_credit_note},
                                                fieldname=['company', 'company_address', 'nit_face_customer',
                                                           'customer_address', 'customer_name', 'total_taxes_and_charges',
                                                           'grand_total'], as_dict=1)
            if len(self.dat_fac) == 0:
                return False, f'''No se encontro ninguna factura con serie: {self.__inv_credit_note}.\
                                  Por favor valida los datos de la factura que deseas procesar'''


            # Obtenemos datos necesario de company: Nombre de compañia, nit
            dat_compania = frappe.db.get_values('Company', filters={'name': self.dat_fac[0]['company']},
                                                fieldname=['company_name', 'nit_face_company', 'tax_id'],
                                                as_dict=1)
            if len(dat_compania) == 0:
                return False, f'''No se encontraron datos para la compañia {self.dat_fac[0]["company_name"]}.
                                  Verifica que la factura que deseas procesar tenga una compañia valida'''


            # De la compañia, obtenemos direccion 1, email, codigo postal, departamento, municipio, pais
            dat_direccion = frappe.db.get_values('Address', filters={'name': self.dat_fac[0]['company_address']},
                                                 fieldname=['address_line1', 'email_id', 'pincode', 'county',
                                                            'state', 'city', 'country', 'facelec_establishment'],
                                                 as_dict=1)
            if len(dat_direccion) == 0:
                return False, f'No se encontro ninguna direccion de la compania {dat_compania[0]["company_name"]},\
                                verifica que exista una, con data en los campos address_line1, email_id, pincode, state,\
                                city, country, y vuelve a generar la factura'


            # LA ENTIDAD EMISORA SI O SI DEBE TENER ESTOS DATOS :D
            # Validacion de existencia en los campos de direccion, ya que son obligatorio por parte de la API FEL
            # Usaremos la primera que se encuentre
            for dire in dat_direccion[0]:
                if not dat_direccion[0][dire]:
                    return False, '''No se puede completar la operacion ya que el campo {} de la direccion de compania no\
                                     tiene data, por favor asignarle un valor e intentar de nuevo'''.format(str(dire))

            # Si en configuracion de factura electronica esta seleccionada la opcion de usar datos de prueba
            if frappe.db.get_value('Configuracion Factura Electronica',
                                  {'name': self.__config_name}, 'usar_datos_prueba') == 1:
                nom_comercial = frappe.db.get_value('Configuracion Factura Electronica',
                                                   {'name': self.__config_name}, 'nombre_empresa_prueba')

                # Si la compania es de un propietario
                if frappe.db.get_value('Configuracion Factura Electronica', {'name': self.__config_name}, 'is_individual'):
                    nombre_emisor = frappe.db.get_value('Configuracion Factura Electronica', {'name': self.__config_name}, 'facelec_name_of_owner')
                else:
                    nombre_emisor = nom_comercial

            # Aplica Si los datos son para producción
            else:
                nom_comercial = dat_compania[0]['company_name']

                # Si la compania es de un propietario
                if frappe.db.get_value('Configuracion Factura Electronica', {'name': self.__config_name}, 'is_individual'):
                    nombre_emisor = frappe.db.get_value('Configuracion Factura Electronica', {'name': self.__config_name}, 'facelec_name_of_owner')
                else:
                    nombre_emisor = dat_compania[0]['company_name']
                    
            self.emisor_data = {
                "@AfiliacionIVA": "GEN",
                "@CodigoEstablecimiento": dat_direccion[0]['facelec_establishment'],
                "@CorreoEmisor": dat_direccion[0]['email_id'],
                "@NITEmisor": str((dat_compania[0]['nit_face_company']).replace('-', '')).upper().strip(),
                "@NombreComercial": nom_comercial,
                "@NombreEmisor": nombre_emisor,
                "dte:DireccionEmisor": {
                    "dte:Direccion": dat_direccion[0]['address_line1'],
                    "dte:CodigoPostal": dat_direccion[0]['pincode'],  # Codig postal
                    "dte:Municipio": dat_direccion[0]['county'],  # Municipio
                    "dte:Departamento": dat_direccion[0]['state'],  # Departamento
                    "dte:Pais": frappe.db.get_value('Country', {'name': dat_direccion[0]['country']}, 'code').upper()  # CODIG PAIS
                }
            }
            return True, 'OK'

        except:
            return False, 'Proceso no completado, no se pudieron obtener todos los datos necesarios, verifica tener todos\
                           los campos necesario en Configuracion Factura Electronica. Mas detalles en: \n'+str(frappe.get_traceback())
    def receiver(self):
        """
        Validacion y generacion datos de Receptor (cliente)

        Returns:
            tuple: True/False, msj, msj
        """

        # Intentara obtener data de direccion cliente
        try:
            dat_direccion = frappe.db.get_values('Address', filters={'name': self.dat_fac[0]['customer_address']},
                                                 fieldname=['address_line1', 'email_id', 'pincode',
                                                            'state', 'city', 'country'], as_dict=1)    
        # Datos del receptor
            self.receptor_data = frappe.db.get_values('Address', filters={'name': self.dat_fac[0]['customer_address']},
                                                 fieldname=['address_line1', 'email_id', 'pincode',
                                                            'state', 'city', 'country'], as_dict=1)
            # NOTE: se quitara esta validacion para permitir usar valores default en caso no exista una direccion
            # o campos especificacion de direccion
            # if len(dat_direccion) == 0:
            #     return False, f'''No se encontro ninguna direccion para el cliente {self.dat_fac[0]["customer_name"]}.\
            #                       Por favor asigna un direccion y vuelve a intentarlo'''

            # # Validacion data direccion cliente
            # for dire in dat_direccion[0]:
            #     if dat_direccion[0][dire] is None or dat_direccion[0][dire] is '':
            #         return False, '''No se puede completar la operacion ya que el campo {} de la direccion del cliente {} no\
            #                          tiene data, por favor asignarle un valor e intentar de nuevo \
            #                       '''.format(str(dire), self.dat_fac[0]["customer_name"])

        # Items de la nota
            return True, 'OK'

        except:
            return False, 'No se pudo obtener data de los items en la factura {}, Error: {}'.format(self.__inv_credit_note, str(frappe.get_traceback()))

    def items(self):
        """
        Procesa todos los items de la factura aplicando calculos necesarios para la SAT

        Returns:
            tuple: True/False, msj, msj
        """

        try:
            i_fel = {}  # Guardara la seccion de items ok
            items_ok = []  # Guardara todos los items OK
    
            self.items = rappe.db.get_values('Sales Invoice Item', filters={'parent': str(self.__inv_credit_note)},
                                             fieldname=['item_name', 'qty', 'item_code', 'description',
                                                        'net_amount', 'base_net_amount', 'discount_percentage',
                                                        'discount_amount', 'price_list_rate', 'net_rate',
                                                        'stock_uom', 'serial_no', 'item_group', 'rate',
                                                        'amount', 'facelec_sales_tax_for_this_row',
                                                        'facelec_amount_minus_excise_tax', 'facelec_is_service',
                                                        'facelec_is_good', 'factelecis_fuel', 'facelec_si_is_exempt',
                                                        'facelec_other_tax_amount', 'facelec_three_digit_uom_code',
                                                        'facelec_gt_tax_net_fuel_amt', 'facelec_gt_tax_net_goods_amt',
                                                        'facelec_gt_tax_net_services_amt', 'facelec_is_discount',
                                                        'facelec_tax_rate_per_uom'], order_by='idx asc', as_dict=True)

            switch_item_description = frappe.db.get_value('Configuracion Factura Electronica', {'name': self.__config_name}, 'descripcion_item')

            # Obtenemos los impuesto cofigurados para x compañia en la factura
            self.__taxes_fact = frappe.db.get_values('Sales Taxes and Charges', filters={'parent': self.__inv_credit_note},
                                                     fieldname=['tax_name', 'taxable_unit_code', 'rate'], as_dict=True)

            # Verificamos la cantidad de items
            longitems = len(self.__dat_items)
            apply_oil_tax = False

            if longitems != 0:
                contador = 0  # Utilizado para enumerar las lineas en factura electronica

                # Si existe un solo item a facturar la iteracion se hara una vez, si hay mas lo contrario mas iteraciones
                for i in range(0, longitems):
                    obj_item = {}  # por fila

                    # detalle_stock = frappe.db.get_value('Item', {'name': self.__dat_items[i]['item_code']}, 'is_stock_item')
                    # # Validacion de Bien o Servicio, en base a detalle de stock
                    # if (int(detalle_stock) == 0):
                    #     obj_item["@BienOServicio"] = 'S'

                    # if (int(detalle_stock) == 1):
                    #     obj_item["@BienOServicio"] = 'B'
                     # Is Service, Is Good.  Si Is Fuel = Is Good. Si Is Exempt = Is Good.
                    if cint(self.__dat_items[i]['facelec_is_service']) == 1:
                        obj_item["@BienOServicio"] = 'S'

                    elif cint(self.__dat_items[i]['facelec_is_good']) == 1:
                        obj_item["@BienOServicio"] = 'B'

                    elif cint(self.__dat_items[i]['factelecis_fuel']) == 1:
                        obj_item["@BienOServicio"] = 'B'
                        apply_oil_tax = True

                    elif cint(self.__dat_items[i]['facelec_si_is_exempt']) == 1:
                        obj_item["@BienOServicio"] = 'B'

                    desc_item_fila = 0
                    if cint(self.__dat_items[i]['facelec_is_discount']) == 1:
                        desc_item_fila = self.__dat_items[i]['discount_amount']

                    if apply_oil_tax == True:
                        precio_uni = 0
                        precio_item = 0
                        desc_fila = 0

                        # Logica para validacion si aplica Descuento
                        desc_item_fila = 0
                        if cint(self.__dat_items[i]['facelec_is_discount']) == 1:
                            desc_item_fila = self.__dat_items[i]['discount_amount']

                        # Precio unitario, (sin aplicarle descuento)
                        # Al precio unitario se le suma el descuento que genera ERP, ya que es neceario enviar precio sin descuentos, en las operaciones restantes es neceario
                        # (Precio Unitario - Monto IDP) + Descuento
                        precio_uni = flt((self.__dat_items[i]['rate'] - self.__dat_items[i]['facelec_tax_rate_per_uom']) + desc_item_fila, self.__precision)

                        precio_item = flt(precio_uni * self.__dat_items[i]['qty'], self.__precision)

                        desc_fila = 0
                        desc_fila = flt(self.__dat_items[i]['qty'] * desc_item_fila, self.__precision)

                        contador += 1
                        description_to_item = self.__dat_items[i]['item_name'] if switch_item_description == "Nombre de Item" else self.__dat_items[i]['description']

                        obj_item["@NumeroLinea"] = contador
                        obj_item["dte:Cantidad"] = abs(float(self.__dat_items[i]['qty']))
                        obj_item["dte:UnidadMedida"] = self.__dat_items[i]['facelec_three_digit_uom_code']
                        obj_item["dte:Descripcion"] = remove_html_tags(description_to_item)  # description
                        obj_item["dte:PrecioUnitario"] = abs(flt(precio_uni, self.__precision))
                        obj_item["dte:Precio"] = abs(flt(precio_item, self.__precision)) # Correcto según el esquema XML)
                        obj_item["dte:Descuento"] = abs(flt(desc_fila, self.__precision))

                        # Agregamos los impuestos
                        # IVA e IDP
                        nombre_corto = str(frappe.db.get_value('Item', {'name': self.__dat_items[i]['item_code']}, 'tax_name'))
                        codigo_uni_gravable = frappe.db.get_value('Item', {'name': self.__dat_items[i]['item_code']}, 'taxable_unit_code')

                        obj_item["dte:Impuestos"] = {}
                        obj_item["dte:Impuestos"]["dte:Impuesto"] = [
                            {
                                "dte:NombreCorto": self.__taxes_fact[0]['tax_name'],
                                "dte:CodigoUnidadGravable": self.__taxes_fact[0]['taxable_unit_code'],
                                "dte:MontoGravable": abs(flt(self.__dat_items[i]['facelec_gt_tax_net_fuel_amt'], self.__precision)),  # net_amount
                                "dte:MontoImpuesto": abs(flt(self.__dat_items[i]['facelec_gt_tax_net_fuel_amt'] * (self.__taxes_fact[0]['rate']/100), self.__precision))
                            },
                            {
                                "dte:NombreCorto": nombre_corto,
                                "dte:CodigoUnidadGravable": codigo_uni_gravable,
                                "dte:CantidadUnidadesGravables": abs(float(self.__dat_items[i]['qty'])),
                                "dte:MontoImpuesto": abs(flt(self.__dat_items[i]['facelec_other_tax_amount'], self.__precision))
                            }
                        ]

                        obj_item["dte:Total"] = abs(flt(self.__dat_items[i]['amount'], self.__precision))

                    else:
                        # Calculo precio unitario
                        precio_uni = 0
                        precio_uni = flt(self.__dat_items[i]['rate'] + desc_item_fila, self.__precision)

                        # Calculo precio item
                        precio_item = 0
                        precio_item = flt(precio_uni * self.__dat_items[i]['qty'], self.__precision)

                        # Calculo descuento item
                        desc_fila = 0
                        # desc_fila = abs(float('{0:.3f}'.format(abs(self.__dat_items[i]['price_list_rate'] * self.__dat_items[i]['qty']) - abs(float(self.__dat_items[i]['amount'])))))
                        desc_fila = flt(self.__dat_items[i]['qty'] * desc_item_fila, self.__precision)

                        contador += 1
                        description_to_item = self.__dat_items[i]['item_name'] if switch_item_description == "Nombre de Item" else self.__dat_items[i]['description']

                        obj_item["@NumeroLinea"] = contador
                        obj_item["dte:Cantidad"] = abs(float(self.__dat_items[i]['qty']))
                        obj_item["dte:UnidadMedida"] = self.__dat_items[i]['facelec_three_digit_uom_code']
                        obj_item["dte:Descripcion"] = remove_html_tags(description_to_item)  #  self.__dat_items[i]['item_name']  # description
                        obj_item["dte:PrecioUnitario"] = flt(abs(precio_uni), self.__precision)
                        obj_item["dte:Precio"] = flt(abs(precio_item), self.__precision)
                        obj_item["dte:Total"] = abs(flt(self.__dat_items[i]['amount'], self.__precision))

                    apply_oil_tax = False
                    items_ok.append(obj_item)

            i_fel = {"dte:Item": items_ok}
            self.__d_items = i_fel
            return True, 'OK'

        except:
            return False, 'Proceso no completado, no se pudieron obtener todos los datos necesarios, verifica tener todos\
                           los campos necesario en Configuracion Factura Electronica. Mas detalles en: \n'+str(frappe.get_traceback())

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
