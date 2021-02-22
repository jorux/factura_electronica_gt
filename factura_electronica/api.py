# Copyright (c) 2020, Si Hay Sistema and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

import json
from datetime import date, datetime

import frappe
import requests
import xmltodict
from frappe import _
from frappe.utils import get_site_name

from factura_electronica.utils.facelec_db import actualizarTablas as actualizartb
from factura_electronica.utils.facelec_db import guardar_factura_electronica as guardar
from factura_electronica.utils.facelec_generator import construir_xml
from factura_electronica.utils.fel_generator import FacturaElectronicaFEL
from factura_electronica.utils.utilities_facelec import encuentra_errores as errores
from factura_electronica.utils.utilities_facelec import normalizar_texto, validar_configuracion


def peticion_factura_electronica(datos_xml, url_servicio):
    '''Realiza la peticion al webservice SOAP de INFILE GFACE

       Parametros:
       -----------
       * datos_xml (xml string) : Estructura XML con la data para factura
                                  electronica
       Retornos: La respuesta de la peticion realizada a INFILE
    '''
    # Realizara la comunicacion al webservice
    try:
        headers = {'Content-Type': 'text/xml; charset=utf-8'}
        response = requests.post(url_servicio, data=datos_xml.encode('utf-8'), headers=headers, timeout=15)
    except:
        frappe.msgprint(_('''Tiempo de espera agotado para webservice, verificar conexion a internet
                          e intentar de nuevo: \n {}'''.format(frappe.get_traceback())))

    # Si hay algun error en la respuesta, lo capturara y mostrara
    try:
        respuesta_webservice = response.content
    except:
        frappe.msgprint(_('Error en la comunicacion no se recibieron datos de INFILE: {}'.format(frappe.get_traceback())))
    else:
        return respuesta_webservice


@frappe.whitelist()
def generar_factura_electronica(serie_factura, nombre_cliente, pre_se):
    '''Verifica que todos los datos esten correctos para realizar una
       peticion a INFILE y generar la factura electronica

       Parametros
       ----------
       * serie_factura (str) : Serie de la factura
       * nombre_cliente (str) : Nombre del cliente
       * pre_se (str) : Prefijo de la serie
    '''

    serie_original_factura = str(serie_factura)
    nombre_del_cliente = str(nombre_cliente)
    prefijo_serie = str(pre_se)

    # Verifica que exista una configuracion validada para Factura Electronicaa
    validar_config = validar_configuracion()

    # Si es igual a 1, hay una configuracion valida
    if validar_config[0] == 1:
        # Verifica si existe una factura con la misma serie, evita duplicadas
        if frappe.db.exists('Envios Facturas Electronicas', {'numero_dte': serie_original_factura}):
            factura_electronica = frappe.db.get_values('Envios Facturas Electronicas',
                                                    filters={'numero_dte': serie_original_factura},
                                                    fieldname=['serie_factura_original', 'cae', 'numero_dte'],
                                                    as_dict=1)
            frappe.msgprint(_('''
            <b>AVISO:</b> La Factura ya fue generada Anteriormente <b>{}</b>
            '''.format(str(factura_electronica[0]['numero_dte']))))

            dte_factura = str(factura_electronica[0]['numero_dte'])

            return dte_factura

        elif frappe.db.exists('Envio FEL', {'serie_para_factura': serie_original_factura}):
            factura_electronica = frappe.db.get_values('Envio FEL',
                                                    filters={'serie_para_factura': serie_original_factura},
                                                    fieldname=['serie_para_factura'],
                                                    as_dict=1)
            frappe.msgprint(_('''
            <b>AVISO:</b> La Factura ya fue generada Anteriormente <b>{}</b>
            '''.format(str(factura_electronica[0]['serie_para_factura']))))

            dte_factura = str(factura_electronica[0]['serie_para_factura'])

            return dte_factura

        else:  # Si no existe se creara
            nombre_config_validada = str(validar_config[1])
            # Verificacion regimen GFACE
            if validar_config[2] == 'GFACE':
                # VERIFICACION EXISTENCIA SERIES CONFIGURADAS, EN CONFIGURACION FACTURA ELECTRONICA
                if frappe.db.exists('Configuracion Series', {'parent': nombre_config_validada, 'serie': prefijo_serie}):
                    series_configuradas = frappe.db.get_values('Configuracion Series',
                                                                filters={'parent': nombre_config_validada, 'serie': prefijo_serie},
                                                                fieldname=['fecha_resolucion', 'estado_documento',
                                                                            'tipo_documento', 'serie', 'secuencia_infile',
                                                                            'numero_resolucion', 'codigo_sat'], as_dict=1)


                    url_configurada = frappe.db.get_values('Configuracion Factura Electronica',
                                                        filters={'name': nombre_config_validada},
                                                        fieldname=['url_listener', 'descargar_pdf_factura_electronica',
                                                                'url_descarga_pdf'], as_dict=1)

                    # Verificacion regimen GFACE
                    # CONTRUCCION XML Y PETICION A WEBSERVICE
                    try:
                        xml_factura = construir_xml(serie_original_factura, nombre_del_cliente, prefijo_serie, series_configuradas, nombre_config_validada)
                    except:
                        frappe.msgprint(_('Error crear xml para factura electronica: {}'.format(frappe.get_traceback())))
                    else:
                        url = str(url_configurada[0]['url_listener'])
                        tiempo_enviado = datetime.now()
                        respuesta_infile = peticion_factura_electronica(xml_factura, url)
                        # Usar para debug
                        # with open('reci.xml', 'w') as f:
                        #     f.write(str(respuesta_infile))

                    # VALIDACION RESPUESTA
                    try:
                        # xmltodic parsea la respuesta por parte de INFILE
                        documento_descripcion = xmltodict.parse(respuesta_infile)
                        # En la descripcion se encuentra el mensaje, si el documento electronico se realizo con exito
                        descripciones = (documento_descripcion['S:Envelope']['S:Body']['ns2:registrarDteResponse']['return']['descripcion'])
                    except:
                        frappe.msgprint(_('''Error: INFILE no pudo recibir los datos: {0} \n {1}'''.format(str(respuesta_infile), frappe.get_traceback())))
                    else:
                        # La funcion errores se encarga de verificar si existen errores o si la
                        # generacion de factura electronica fue exitosa
                        errores_diccionario = errores(descripciones)

                        if (len(errores_diccionario) > 0):
                            try:
                                # Si el mensaje indica que la factura electronica se genero con exito se procede
                                # a guardar la respuesta de INFILE en la DB
                                if ((str(errores_diccionario['Mensaje']).lower()) == 'dte generado con exito'):

                                    cae_fac_electronica = guardar(respuesta_infile, serie_original_factura, tiempo_enviado)
                                    # frappe.msgprint(_('FACTURA GENERADA CON EXITO'))
                                    # el archivo rexpuest.xml se encuentra en la ruta, /home/frappe/frappe-bench/sites

                                    # USAR PARA DEBUG
                                    # with open('respuesta_infile.xml', 'w') as recibidoxml:
                                    #     recibidoxml.write(str(respuesta_infile))
                                    #     recibidoxml.close()

                                    # es-GT:  Esta funcion es la nueva funcion para actualizar todas las tablas en las cuales puedan aparecer.
                                    numero_dte_correcto = actualizartb(serie_original_factura)
                                    # Funcion para descargar y guardar pdf factura electronica
                                    descarga_pdf = guardar_pdf_servidor(numero_dte_correcto, cae_fac_electronica)

                                    # Este dato sera capturado por Js actualizando la url
                                    return numero_dte_correcto
                            except:
                                frappe.msgprint(_('''
                                AVISOS <span class="label label-default" style="font-size: 16px">{}</span>
                                '''.format(str(len(errores_diccionario))) + ' VERIFIQUE SU MANUAL'))

                                for llave in errores_diccionario:
                                    frappe.msgprint(_('''
                                    <span class="label label-warning" style="font-size: 14px">{}</span>
                                    '''.format(str(llave)) + ' = ' + str(errores_diccionario[llave])))

                                frappe.msgprint(_('NO GENERADA: {}'.format(frappe.get_traceback())))


                else:
                    frappe.msgprint(_('''La serie utilizada en esta factura no esta configurada para Facturas Electronicas.
                                        Por favor configura la serie <b>{0}</b> en
                                        <a href='#List/Configuracion Factura Electronica'><b>Configuracion Factura Electronica</b></a>
                                        e intenta de nuevo.
                                    '''.format(prefijo_serie)))

            # Verificacion regimen FEL
            if validar_config[2] == 'FEL':
                if frappe.db.exists('Configuracion Series FEL', {'parent': nombre_config_validada, 'serie': prefijo_serie}):
                    series_configuradas_fel = frappe.db.get_values('Configuracion Series FEL',
                                                                    filters={'parent': nombre_config_validada, 'serie': prefijo_serie},
                                                                    fieldname=['tipo_documento'], as_dict=1)

                    url_configurada = frappe.db.get_values('Configuracion Factura Electronica',
                                                        filters={'name': nombre_config_validada},
                                                        fieldname=['url_listener', 'descargar_pdf_factura_electronica',
                                                                'url_descarga_pdf'], as_dict=1)
                    est = ''
                    try:
                        factura_electronica = FacturaElectronicaFEL(serie_original_factura, nombre_del_cliente, nombre_config_validada, series_configuradas_fel)
                        est = factura_electronica.generar_facelec()
                        if est['status'] == 'OK':
                            # frappe.msgprint(_('Ok Generada'+str(est)))
                            serie_ok = frappe.db.get_value('Envio FEL', {'name': est['uuid']}, 'serie_para_factura')
                            # return est['uuid']
                            return serie_ok
                        else:
                            # return est
                            frappe.msgprint(_(str(est['detalle_errores_facelec'])))
                    except:
                        frappe.msgprint(_('No se puedo generar la factura electronica: '+(est['detalle_errores_facelec'])))

                else:
                    frappe.msgprint(_('''La serie utilizada en esta factura no esta configurada para Facturas Electronicas.
                                        Por favor configura la serie <b>{0}</b> en
                                        <a href='#List/Configuracion Factura Electronica'><b>Configuracion Factura Electronica</b></a>
                                        e intenta de nuevo.
                                    '''.format(prefijo_serie)))

    elif validar_config[0] == 2:
        frappe.msgprint(_('''Existe más de una configuración para factura electrónica.
                             Verifique que solo exista una validada en
                             <a href='#List/Configuracion Factura Electronica'><b>Configuracion Factura Electronica</b></a>'''))

    elif validar_config[0] == 3:
        frappe.msgprint(_('''No se encontró una configuración válida. Verifique que exista una configuración validada en
                             <a href='#List/Configuracion Factura Electronica'><b>Configuracion Factura Electronica</b></a>'''))


@frappe.whitelist()
def obtenerConfiguracionManualAutomatica():
    '''Verifica la configuracion guardada ya sea Automatica o Manual, aplica para la generacion de
       facturas o la forma en que se guarda'''

    verificarModalidad = validar_configuracion()

    # Si la verificacion es igual a '1' se encontro una configuracion valida
    if (verificarModalidad[0] == 1):
        configuracion_fac = frappe.db.get_values('Configuracion Factura Electronica', filters={'name': verificarModalidad[1]},
                                                 fieldname=['generacion_factura'], as_dict=1)

        # Retorna la modalidad encontrada en la configuracion
        if (str(configuracion_fac[0]['generacion_factura']) == 'MANUAL'):
            return 'Manual'
        else:
            return 'Automatico'

    # SI la verificacion es igual a '2' existe mas de una configuracion validada, mostrara un mensaje
    # porque se requiere que solo una configuracion este validada
    if (verificarModalidad[0] == 2):
        frappe.msgprint(_('Existe más de una configuración para factura electrónica. Verifique que solo exista una validada'))

    # Si la verificacion es igual a '3' no existe ninguna configuracion validada
    if (verificarModalidad[0] == 3):
        frappe.msgprint(_('No se encontró una configuración válida. Verifique que exista una configuración validada'))


@frappe.whitelist()
def guardar_pdf_servidor(nombre_archivo, cae_de_factura_electronica):
    '''Descarga factura en servidor y registra en base de datos

    Parametros:
    ----------
    * nombre_archivo (str) : Nombre que describe el archivo
    * cae_de_factura_electronica (str) : CAE
    '''
    import os
    modalidad_configurada = validar_configuracion()
    nombre_de_sitio = get_site_name(frappe.local.site)
    ruta_archivo = '{0}/private/files/factura-electronica/'.format(nombre_de_sitio)

    # Verifica que exista un configuracion valida para factura electronica
    if modalidad_configurada[0] == 1:
        configuracion_factura = frappe.db.get_values('Configuracion Factura Electronica',
                                                    filters={'name': modalidad_configurada[1]},
                                                    fieldname=['url_listener', 'descargar_pdf_factura_electronica',
                                                               'url_descarga_pdf'], as_dict=1)

        url_archivo = configuracion_factura[0]['url_descarga_pdf'] + cae_de_factura_electronica

        # Verifica que la funcionalidad para descargar pdf automaticamente, este activa
        if configuracion_factura[0]['descargar_pdf_factura_electronica'] == 'ACTIVAR':

            # Si no existe registro en la base de datos procede a descargar y guardar
            if not frappe.db.exists('File', {'file_name': (nombre_archivo + '.pdf')}):

                # Verifica existencia ruta de archivo, si no existe la crea, si ya existe descarga el pdf en esa ruta
                if os.path.exists(ruta_archivo):
                    descarga_archivo = os.system('curl -s -o {0}{1}.pdf {2}'.format(ruta_archivo, nombre_archivo, url_archivo))
                else:
                    frappe.create_folder(ruta_archivo)
                    descarga_archivo = os.system('curl -s -o {0}{1}.pdf {2}'.format(ruta_archivo, nombre_archivo, url_archivo))

                # Cuando la descarga es exitosa retorna 0, por lo que si es existosa procede
                if descarga_archivo == 0:
                    # Obtiene el tamaño del archivo en bytes
                    bytes_archivo = os.path.getsize("{0}/private/files/factura-electronica/{1}.pdf".format(nombre_de_sitio, nombre_archivo))
                    # Guarda los datos en la base de datos
                    try:
                        nuevo_archivo = frappe.new_doc("File")
                        nuevo_archivo.docstatus = 0
                        nuevo_archivo.file_name = str(nombre_archivo) + '.pdf'
                        nuevo_archivo.file_url = '/private/files/factura-electronica/{0}.pdf'.format(nombre_archivo)
                        nuevo_archivo.attached_to_name = nombre_archivo
                        nuevo_archivo.file_size = bytes_archivo
                        nuevo_archivo.attached_to_doctype = 'Sales Invoice'
                        nuevo_archivo.is_home_folder = 0
                        nuevo_archivo.if_folder = 0
                        nuevo_archivo.folder = 'Home/attachments'
                        nuevo_archivo.is_private = 1
                        nuevo_archivo.old_parent = 'Home/attachments'
                        nuevo_archivo.save()
                    except:
                        frappe.msgprint(_('''Error no se pudo guardar PDF de la factura electronica en la
                                            base de datos. Intente de nuevo.'''))
                    else:
                        return 'ok'

                else:
                    frappe.msgprint(_('''No se pudo obtener el archivo pdf de la factura electronica.
                                        Por favor intente de nuevo.'''))
            # else:
            #     frappe.msgprint(_('EL PDF YA EXISTE ;)'))


@frappe.whitelist()
def get_data_tax_account(name_account_tax_gt):
    '''Funcion para obtener los datos de impuestos dependiendo el tipo de cuenta recibido

       Parametros:
       ----------
       * name_account_tax_gt (str) : Nombre de la cuenta
    '''
    if frappe.db.exists('Account', {'name': name_account_tax_gt}):

        datos_cuenta = frappe.db.get_values('Account', filters={'name': name_account_tax_gt},
                                            fieldname=['tax_rate', 'name'], as_dict=1)

        return str(datos_cuenta[0]['tax_rate'])
    else:
        frappe.msgprint(_('No existe cuenta relacionada con el producto'))


@frappe.whitelist()
def obtener_numero_resolucion(nombre_serie):
    '''Retorna el numero de resolucion en base la serie de Configuracion Electronica

    Parametros:
    ----------
    * nombre_serie (str) : Nombre de la serie para filtrar
    '''
    if frappe.db.exists('Configuracion Series', {'serie': nombre_serie, 'docstatus': 1}):
        numero_resolucion = frappe.db.get_values('Configuracion Series', filters={'serie': nombre_serie, 'docstatus': 1},
                                                 fieldname=['numero_resolucion'], as_dict=1)

        return str(numero_resolucion[0]['numero_resolucion'])


@frappe.whitelist()
def generar_tabla_html(tabla):
    """Funcion para generar tabla html + jinja, para mostrar impuestos por cada item

    Parametros:
    ----------
    * tabla (json) : Json con la data que desibe los impuestos
    """

    headers = [_("Item"), _("Unit Tax"), _("Qty"), _("Total Tax"), _("+"),
               _("Base Value"), _("+"), _("IVA"), _("="), _("Total")]
    mi_tabla = json.loads(tabla)
    longi = (len(mi_tabla))

    # # Retorna la tabla HTML lista para renderizar
    return frappe.render_template(
        "templates/sales_invoice_tax.html", dict(
            headers=headers,
            items_tax=mi_tabla,
            index=longi
        )
    )


@frappe.whitelist()
def generar_tabla_html_factura_compra(tabla):
    """Funcion para generar tabla html + jinja, para mostrar impuestos por
       cada item de Purchase Invoice.

       Parametros:
       ----------
       * tabla (json) : Json con la data que desibe los impuestos
    """

    headers = [_("Item"), _("Unit Tax"), _("Qty"), _("Total Tax"), _("+"),
               _("Base Value"), _("+"), _("IVA"), _("="), _("Total")]

    mi_tabla = json.loads(tabla)
    longi = (len(mi_tabla))

    # # Retorna la tabla HTML lista para renderizar
    return frappe.render_template(
        "templates/purchase_invoice_tax.html", dict(
            headers=headers,
            items_tax=mi_tabla,
            index=longi
        )
    )


# FACTURA ELECTRONICA API OLD GFACE
def generar_factura_electronica_api(serie_factura, nombre_cliente, pre_se):
    '''Funcion API PNE para generar Facturas Electronicas REST-API'''
    '''Verifica que todos los datos esten correctos para realizar una
       peticion a INFILE y generar la factura electronica

       Parametros
       ----------
       * serie_factura (str) : Serie de la factura
       * nombre_cliente (str) : Nombre del cliente
       * pre_se (str) : Prefijo de la serie
    '''

    serie_original_factura = str(serie_factura)
    nombre_del_cliente = str(nombre_cliente)
    prefijo_serie = str(pre_se)

    # Verifica que exista una configuracion validada para Factura Electronicaa
    validar_config = validar_configuracion()

    # Si es igual a 1, hay una configuracion valida
    if validar_config[0] == 1:
        # Verifica si existe una factura con la misma serie, evita duplicadas
        if frappe.db.exists('Envios Facturas Electronicas', {'numero_dte': serie_original_factura}):
            factura_electronica = frappe.db.get_values('Envios Facturas Electronicas',
                                                    filters={'numero_dte': serie_original_factura},
                                                    fieldname=['serie_factura_original', 'cae', 'numero_dte'],
                                                    as_dict=1)

            dte_factura = str(factura_electronica[0]['numero_dte'])

            return 'La factura ya fue generada, numero DTE ' + str(dte_factura)

        else:
            nombre_config_validada = str(validar_config[1])

            # VERIFICACION EXISTENCIA SERIES CONFIGURADAS, EN CONFIGURACION FACTURA ELECTRONICA
            if frappe.db.exists('Configuracion Series', {'parent': nombre_config_validada, 'serie': prefijo_serie}):
                series_configuradas = frappe.db.get_values('Configuracion Series',
                                                            filters={'parent': nombre_config_validada, 'serie': prefijo_serie},
                                                            fieldname=['fecha_resolucion', 'estado_documento',
                                                                        'tipo_documento', 'serie', 'secuencia_infile',
                                                                        'numero_resolucion', 'codigo_sat'], as_dict=1)

                url_configurada = frappe.db.get_values('Configuracion Factura Electronica',
                                                    filters={'name': nombre_config_validada},
                                                    fieldname=['url_listener', 'descargar_pdf_factura_electronica',
                                                              'url_descarga_pdf'], as_dict=1)


                # CONTRUCCION XML Y PETICION A WEBSERVICE
                try:
                    xml_factura = construir_xml(serie_original_factura, nombre_del_cliente, prefijo_serie, series_configuradas, nombre_config_validada)
                except:
                    return 'Error crear xml para factura electronica'
                else:
                    url = str(url_configurada[0]['url_listener'])
                    tiempo_enviado = datetime.now()
                    respuesta_infile = peticion_factura_electronica(xml_factura, url)


                # VALIDACION RESPUESTA
                try:
                    # xmltodic parsea la respuesta por parte de INFILE
                    documento_descripcion = xmltodict.parse(respuesta_infile)
                    # En la descripcion se encuentra el mensaje, si el documento electronico se realizo con exito
                    descripciones = (documento_descripcion['S:Envelope']['S:Body']['ns2:registrarDteResponse']['return']['descripcion'])
                except:
                    return 'Error: INFILE no pudo recibir los datos: ' + str(respuesta_infile)
                else:
                    # La funcion errores se encarga de verificar si existen errores o si la
                    # generacion de factura electronica fue exitosa
                    errores_diccionario = errores(descripciones)

                    if (len(errores_diccionario) > 0):
                        try:
                            # Si el mensaje indica que la factura electronica se genero con exito se procede
                            # a guardar la respuesta de INFILE en la DB
                            if ((str(errores_diccionario['Mensaje']).lower()) == 'dte generado con exito'):

                                cae_fac_electronica = guardar(respuesta_infile, serie_original_factura, tiempo_enviado)
                                # frappe.msgprint(_('FACTURA GENERADA CON EXITO'))
                                # el archivo rexpuest.xml se encuentra en la ruta, /home/frappe/frappe-bench/sites

                                with open('respuesta_infile.xml', 'w') as recibidoxml:
                                    recibidoxml.write(respuesta_infile)
                                    recibidoxml.close()

                                # es-GT:  Esta funcion es la nueva funcion para actualizar todas las tablas en las cuales puedan aparecer.
                                numero_dte_correcto = actualizartb(serie_original_factura)
                                # Funcion para descargar y guardar pdf factura electronica
                                descarga_pdf = guardar_pdf_servidor(numero_dte_correcto, cae_fac_electronica)

                                # Este dato sera capturado por Js actualizando la url
                                return {'DTE': numero_dte_correcto, 'CAE': cae_fac_electronica}
                        except:
                            diccionario_errores = {}
                            for llave in errores_diccionario:
                                diccionario_errores[str(llave)] = str(errores_diccionario[llave])

                            return diccionario_errores

            else:
                return ('''La serie utilizada en esta factura no esta en la Configuracion de Factura Electronica.
                           Por favor configura la serie <b>{0}</b> en <b>Configuracion Factura Electronica</b> e intenta de nuevo.
                        '''.format(prefijo_serie))

    elif validar_config[0] == 2:
        return 'Existe más de una configuración para factura electrónica. Verifique que solo exista una validada'

    elif validar_config[0] == 3:
        return 'No se encontró una configuración válida. Verifique que exista una configuración validada'


@frappe.whitelist()
def obtener_serie_doc(opt):
    validar_config = validar_configuracion()

    if validar_config[0] == 1:
        nombre_config_validada = str(validar_config[1])

        if opt == 'credit':
            if frappe.db.exists('Configuracion Series', {'parent': nombre_config_validada,
                                                         'is_credit_note': 1,
                                                         'is_debit_note': 0}):

                series_configuradas = frappe.db.get_values('Configuracion Series',
                                                            filters={'parent': nombre_config_validada,
                                                                     'is_credit_note': 1,
                                                                     'is_debit_note': 0},
                                                            fieldname=['serie'], as_dict=1)

                return series_configuradas[0]['serie']

        if opt == 'debit':
            if frappe.db.exists('Configuracion Series', {'parent': nombre_config_validada,
                                                         'is_debit_note': 1,
                                                         'is_credit_note': 0}):

                series_configuradas = frappe.db.get_values('Configuracion Series',
                                                            filters={'parent': nombre_config_validada,
                                                                     'is_debit_note': 1,
                                                                     'is_credit_note': 0},
                                                            fieldname=['serie'], as_dict=1)

                return series_configuradas[0]['serie']


# FUNCION ESPECIAL PARA API - FEL
def facelec_api(serie_factura, nombre_cliente, pre_se):
    '''Verifica que todos los datos esten correctos para realizar una
       peticion a INFILE y generar la factura electronica

       Parametros
       ----------
       * serie_factura (str) : Serie de la factura
       * nombre_cliente (str) : Nombre del cliente
       * pre_se (str) : Prefijo de la serie
    '''

    serie_original_factura = str(serie_factura)
    nombre_del_cliente = str(nombre_cliente)
    prefijo_serie = str(pre_se)

    # Verifica que exista una configuracion validada para Factura Electronicaa
    validar_config = validar_configuracion()

    # Si es igual a 1, hay una configuracion valida
    if validar_config[0] == 1:
        # Verifica si existe una factura con la misma serie, evita duplicadas
        if frappe.db.exists('Envios Facturas Electronicas', {'numero_dte': serie_original_factura}):
            factura_electronica = frappe.db.get_values('Envios Facturas Electronicas',
                                                    filters={'numero_dte': serie_original_factura},
                                                    fieldname=['serie_factura_original', 'cae', 'numero_dte'],
                                                    as_dict=1)
            # return True, '''
            # <b>AVISO:</b> La Factura ya fue generada Anteriormente <b>{}</b>
            # '''.format(str(factura_electronica[0]['numero_dte']))
            return {
                "status": "OK",
                "cantidad_errores": 0,
                "detalle_errores_facelec": [],
                "uuid": str(factura_electronica[0]['numero_dte']),
                "descripcion": "La factura electronica ya fue generada anteriormente"
            }

        elif frappe.db.exists('Envio FEL', {'serie_para_factura': serie_original_factura}):
            factura_electronica = frappe.db.get_values('Envio FEL',
                                                    filters={'serie_para_factura': serie_original_factura},
                                                    fieldname=['serie_para_factura'],
                                                    as_dict=1)
            return {
                "status": "OK",
                "cantidad_errores": 0,
                "detalle_errores_facelec": [],
                "uuid": "",
                "descripcion": "La Factura ya fue generada Anteriormente con serie: "+str(factura_electronica[0]['serie_para_factura'])
            }
            # return True, "La Factura ya fue generada Anteriormente,"+str(factura_electronica[0]['serie_para_factura'])

        else:  # Si no existe se creara
            nombre_config_validada = str(validar_config[1])
            # Verificacion regimen GFACE
            if validar_config[2] == 'GFACE':
                return {
                    "status": "ERROR",
                    "cantidad_errores": 1,
                    "detalle_errores_facelec": ["GFACE no habilitado para API"],
                    "uuid": ""
                }
                # VERIFICACION EXISTENCIA SERIES CONFIGURADAS, EN CONFIGURACION FACTURA ELECTRONICA
                # if frappe.db.exists('Configuracion Series', {'parent': nombre_config_validada, 'serie': prefijo_serie}):
                #     series_configuradas = frappe.db.get_values('Configuracion Series',
                #                                                 filters={'parent': nombre_config_validada, 'serie': prefijo_serie},
                #                                                 fieldname=['fecha_resolucion', 'estado_documento',
                #                                                             'tipo_documento', 'serie', 'secuencia_infile',
                #                                                             'numero_resolucion', 'codigo_sat'], as_dict=1)


                #     url_configurada = frappe.db.get_values('Configuracion Factura Electronica',
                #                                         filters={'name': nombre_config_validada},
                #                                         fieldname=['url_listener', 'descargar_pdf_factura_electronica',
                #                                                 'url_descarga_pdf'], as_dict=1)

                #     # Verificacion regimen GFACE
                #     # CONTRUCCION XML Y PETICION A WEBSERVICE
                #     try:
                #         xml_factura = construir_xml(serie_original_factura, nombre_del_cliente, prefijo_serie, series_configuradas, nombre_config_validada)
                #     except:
                #         return 'Error crear xml para factura electronica: {}'.format(frappe.get_traceback())
                #     else:
                #         url = str(url_configurada[0]['url_listener'])
                #         tiempo_enviado = datetime.now()
                #         respuesta_infile = peticion_factura_electronica(xml_factura, url)
                #         # Usar para debug
                #         # with open('reci.xml', 'w') as f:
                #         #     f.write(str(respuesta_infile))

                #     # VALIDACION RESPUESTA
                #     try:
                #         # xmltodic parsea la respuesta por parte de INFILE
                #         documento_descripcion = xmltodict.parse(respuesta_infile)
                #         # En la descripcion se encuentra el mensaje, si el documento electronico se realizo con exito
                #         descripciones = (documento_descripcion['S:Envelope']['S:Body']['ns2:registrarDteResponse']['return']['descripcion'])
                #     except:
                #         return '''Error: INFILE no pudo recibir los datos: {0} \n {1}'''.format(str(respuesta_infile), frappe.get_traceback())
                #     else:
                #         # La funcion errores se encarga de verificar si existen errores o si la
                #         # generacion de factura electronica fue exitosa
                #         errores_diccionario = errores(descripciones)

                #         if (len(errores_diccionario) > 0):
                #             try:
                #                 # Si el mensaje indica que la factura electronica se genero con exito se procede
                #                 # a guardar la respuesta de INFILE en la DB
                #                 if ((str(errores_diccionario['Mensaje']).lower()) == 'dte generado con exito'):

                #                     cae_fac_electronica = guardar(respuesta_infile, serie_original_factura, tiempo_enviado)
                #                     # frappe.msgprint(_('FACTURA GENERADA CON EXITO'))
                #                     # el archivo rexpuest.xml se encuentra en la ruta, /home/frappe/frappe-bench/sites

                #                     # USAR PARA DEBUG
                #                     # with open('respuesta_infile.xml', 'w') as recibidoxml:
                #                     #     recibidoxml.write(str(respuesta_infile))
                #                     #     recibidoxml.close()

                #                     # es-GT:  Esta funcion es la nueva funcion para actualizar todas las tablas en las cuales puedan aparecer.
                #                     numero_dte_correcto = actualizartb(serie_original_factura)
                #                     # Funcion para descargar y guardar pdf factura electronica
                #                     descarga_pdf = guardar_pdf_servidor(numero_dte_correcto, cae_fac_electronica)

                #                     # Este dato sera capturado por Js actualizando la url
                #                     return numero_dte_correcto
                #             except:
                #                 for llave in errores_diccionario:
                #                     return '''
                #                     <span class="label label-warning" style="font-size: 14px">{}</span>
                #                     '''.format(str(llave)) + ' = ' + str(errores_diccionario[llave])

                #                 # frappe.msgprint(_('NO GENERADA: {}'.format(frappe.get_traceback())))


                # else:
                #     return '''La serie utilizada en esta factura no esta configurada para Facturas Electronicas.
                #                         Por favor configura la serie <b>{0}</b> en
                #                         <a href='#List/Configuracion Factura Electronica'><b>Configuracion Factura Electronica</b></a>
                #                         e intenta de nuevo.
                #                     '''.format(prefijo_serie)

            # Verificacion regimen FEL
            if validar_config[2] == 'FEL':
                if frappe.db.exists('Configuracion Series FEL', {'parent': nombre_config_validada, 'serie': prefijo_serie}):
                    series_configuradas_fel = frappe.db.get_values('Configuracion Series FEL',
                                                                    filters={'parent': nombre_config_validada, 'serie': prefijo_serie},
                                                                    fieldname=['tipo_documento'], as_dict=1)

                    url_configurada = frappe.db.get_values('Configuracion Factura Electronica',
                                                        filters={'name': nombre_config_validada},
                                                        fieldname=['url_listener', 'descargar_pdf_factura_electronica',
                                                                'url_descarga_pdf'], as_dict=1)
                    est = ''
                    try:
                        factura_electronica = FacturaElectronicaFEL(serie_original_factura, nombre_del_cliente, nombre_config_validada, series_configuradas_fel)
                        est = factura_electronica.generar_facelec()
                        if est['status'] != 'OK':
                            return {
                                "status": "ERROR",
                                "cantidad_errores": len(est['detalle_errores_facelec']),
                                "detalle_errores_facelec": est['detalle_errores_facelec'],
                                "uuid": ""
                            }
                        else:
                            return {
                                "status": "OK",
                                "cantidad_errores": 0,
                                "detalle_errores_facelec": [],
                                "uuid": est['uuid']
                            }
                    except:
                        # return False, 'No se pudo generar la factura electronica: '+(est)
                        return {
                            "status": "ERROR",
                            "cantidad_errores": 1,
                            "detalle_errores_facelec": [est],
                            "uuid": ""
                        }
                else:
                    # return False, '''La serie utilizada en esta factura no esta configurada para Facturas Electronicas.
                    #         Por favor configura la serie <b>{0}</b> en
                    #         <a href='#List/Configuracion Factura Electronica'><b>Configuracion Factura Electronica</b></a>
                    #         e intenta de nuevo.
                    #     '''.format(prefijo_serie)
                    return {
                        "status": "ERROR",
                        "cantidad_errores": 1,
                        "detalle_errores_facelec": ['''La serie utilizada en esta factura no esta configurada para Facturas Electronicas.
                            Por favor configura la serie <b>{0}</b> en
                            <a href='#List/Configuracion Factura Electronica'><b>Configuracion Factura Electronica</b></a>
                            e intenta de nuevo.
                        '''.format(prefijo_serie)],
                        "uuid": ""
                    }

    elif validar_config[0] == 2:
        return {
            "status": "ERROR",
            "cantidad_errores": 1,
            "detalle_errores_facelec": ['''Existe más de una configuración para factura electrónica.
                             Verifique que solo exista una validada en
                             <a href='#List/Configuracion Factura Electronica'><b>Configuracion Factura Electronica</b></a>'''],
            "uuid": ""
        }

    elif validar_config[0] == 3:
        return {
            "status": "ERROR",
            "cantidad_errores": 1,
            "detalle_errores_facelec": ['''No se encontró una configuración válida. Verifique que exista una configuración validada en
                             <a href='#List/Configuracion Factura Electronica'><b>Configuracion Factura Electronica</b></a>'''],
            "uuid": ""
        }

@frappe.whitelist()
def enviar_correo(nombre):
    pass
    # from frappe.core.doctype.communication.email import make
    # msg="Hola Mundo {}".format(nombre)

    # try:
    #     make(doctype="Sales Invoice", name=nombre, subject="Factura Electronica", content=msg, recipients=['m.monroyc22@gmail.com'],
    #         send_email=True, sender="erp.sihaysistema@gmail.com")

    #     msg = """Email send successfully to Employee"""
    #     frappe.msgprint(msg)
    # except:
    #     frappe.msgprint("could not send")


@frappe.whitelist()
def validate_address(address_name):
    # Validacion extra, para ver si en verdad existe la direccion

    # Si no existe ninguna direccion con el nombre y el pais a Guatemala, es decir si aplica
    # exportacion
    if not frappe.db.exists('Address', {'name': str(address_name), 'country': 'Guatemala'}):
        # SI APLICA FACTURA INTERNACIONAL
        return True

    else:
        # NO APLICA FACTURA INTERNACIONAL
        return False


@frappe.whitelist()
def get_address(company):
    try:
        link_address = frappe.db.get_value('Dynamic Link', {'link_doctype': 'Company', 'parenttype': 'Address',
                                                            'link_name': str(company)}, 'parent')

        address = frappe.db.get_value('Address', {'name': link_address}, 'address_line1')

        return address

    except:
        return ''


@frappe.whitelist()
def download_excel_purchase_ledger():
    """
    Permite descargar el excel con nombre Libro compras GT
    """
    frappe.local.response.filename = "Libro Compras.xlsx"
    with open("Libro Compras.xlsx", "rb") as fileobj:
        filedata = fileobj.read()
    frappe.local.response.filecontent = filedata
    frappe.local.response.type = "download"


@frappe.whitelist()
def download_excel_sales_ledger():
    """
    Permite descargar el excel con nombre Libro compras GT
    """
    frappe.local.response.filename = "Libro Ventas.xlsx"
    with open("Libro Ventas.xlsx", "rb") as fileobj:
        filedata = fileobj.read()
    frappe.local.response.filecontent = filedata
    frappe.local.response.type = "download"


@frappe.whitelist()
def invoice_exists(uuid):
    if frappe.db.exists('Envio FEL', {'name': uuid, 'status': 'Cancelled'}):
        return True
    else:
        return False


@frappe.whitelist()
def btn_activator(electronic_doc):
    try:
        status = validar_configuracion()
        if status[0] == 1:
            # Verifica si el doc electronico a generar esta activado en config facelec
            if frappe.db.exists('Configuracion Factura Electronica', {'name': status[1], electronic_doc: 1}):
                return True
            else:
                return False
    except:
        return False


@frappe.whitelist()
def calculations(obj_sales_invoice):
    """
    Aplicador de calculos universal

    Args:
        obj_sales_invoice (Object): Objeto de la clase Sales Invoice

    Returns:
        Object: Objeto de la clase Sales Invoice modificado con calculos correspondientes
    """

    # TODO: WIP: ADAPTAR ESCENARIO IDP

    sales_invoice = obj_sales_invoice
    taxes = sales_invoice.taxes
    # Obtiene monto impuesto
    rate_iva = taxes[0].rate

    try:
        total_iva_factura = 0
        # Calculos
        for item in sales_invoice.items:
            # Aplica para impuestos, en caso sea diferente sera 0
            rate_per_uom = item.facelec_tax_rate_per_uom or 0
            this_row_tax_amount = (item.qty) * rate_per_uom
            this_row_taxable_amount = ((item.rate) * (item.qty)) - ((item.qty) * rate_per_uom)

            item.facelec_other_tax_amount = rate_per_uom * ((item.qty) * 1)
            item.facelec_amount_minus_excise_tax = ((item.qty * item.rate) - (item.qty * rate_per_uom))

            # calculos para combustible
            if (item.facelecis_fuel):
                item.facelec_gt_tax_net_fuel_amt = (item.facelec_amount_minus_excise_tax) / (1 + (rate_iva / 100))
                item.facelec_sales_tax_for_this_row = (item.facelec_gt_tax_net_fuel_amt) * (rate_iva / 100)

            # calculos para bienes
            if (item.facelec_is_good):
                item.facelec_gt_tax_net_goods_amt = (item.facelec_amount_minus_excise_tax) / (1 + (rate_iva / 100))
                item.facelec_sales_tax_for_this_row = (item.facelec_gt_tax_net_goods_amt) * (rate_iva / 100)

            # # calculos para servicios
            if (item.facelec_is_service):
                item.facelec_gt_tax_net_services_amt = (item.facelec_amount_minus_excise_tax) / (1 + (rate_iva / 100))
                item.facelec_sales_tax_for_this_row = (item.facelec_gt_tax_net_services_amt) * (rate_iva / 100)

        for item_iva in sales_invoice.items:
            total_iva_factura += item_iva.facelec_sales_tax_for_this_row

        sales_invoice.shs_total_iva_fac = total_iva_factura

    except:
        return False, f'Ocurrio un problema al aplicar los calculos, asegurese de tener correctamente configurados los items, mas detalles en: {frappe.get_traceback()} '

    else:
        return True, 'OK'


@frappe.whitelist()
def pos_calculations(doc, event):
    try:
        sales_invoice = frappe.get_doc('Sales Invoice', {'name': doc.name})
        taxes = sales_invoice.taxes
        # Obtiene monto impuesto
        rate_iva = taxes[0].rate

        rate_per_uom = 0
        this_row_tax_amount = 0
        facelec_other_tax_amount = 0
        this_row_taxable_amount = 0
        facelec_amount_minus_excise_tax = 0
        facelec_gt_tax_net_fuel_amt = 0
        facelec_gt_tax_net_goods_amt = 0
        facelec_gt_tax_net_services_amt = 0
        facelec_sales_tax_for_this_row = 0
        TOTAL_IVA_FACT = 0

        # Calculos
        for item in sales_invoice.items:
            # Aplica para impuestos, en caso sea diferente sera 0
            rate_per_uom = item.facelec_tax_rate_per_uom or 0
            this_row_tax_amount = (item.qty) * rate_per_uom
            this_row_taxable_amount = ((item.rate) * (item.qty)) - ((item.qty) * rate_per_uom)

            facelec_other_tax_amount = rate_per_uom * ((item.qty) * 1)
            facelec_amount_minus_excise_tax = ((item.qty * item.rate) - (item.qty * rate_per_uom))

            # calculos para combustible
            if (item.factelecis_fuel):
                facelec_gt_tax_net_fuel_amt = (facelec_amount_minus_excise_tax) / (1 + (rate_iva / 100))
                facelec_sales_tax_for_this_row = (facelec_gt_tax_net_fuel_amt) * (rate_iva / 100)
                TOTAL_IVA_FACT += facelec_sales_tax_for_this_row

            # calculos para bienes
            if (item.facelec_is_good):
                facelec_gt_tax_net_goods_amt = (facelec_amount_minus_excise_tax) / (1 + (rate_iva / 100))
                facelec_sales_tax_for_this_row = (facelec_gt_tax_net_goods_amt) * (rate_iva / 100)
                TOTAL_IVA_FACT += facelec_sales_tax_for_this_row

            # # calculos para servicios
            if (item.facelec_is_service):
                facelec_gt_tax_net_services_amt = (facelec_amount_minus_excise_tax) / (1 + (rate_iva / 100))
                facelec_sales_tax_for_this_row = (facelec_gt_tax_net_services_amt) * (rate_iva / 100)
                TOTAL_IVA_FACT += facelec_sales_tax_for_this_row

            frappe.db.set_value('Sales Invoice Item', {'parent': doc.name}, {
                'facelec_other_tax_amount': facelec_other_tax_amount,
                'facelec_amount_minus_excise_tax': facelec_amount_minus_excise_tax,
                'facelec_gt_tax_net_fuel_amt': facelec_gt_tax_net_fuel_amt,
                'facelec_sales_tax_for_this_row': facelec_sales_tax_for_this_row,
                'facelec_gt_tax_net_goods_amt': facelec_gt_tax_net_goods_amt,
                'facelec_gt_tax_net_services_amt': facelec_gt_tax_net_services_amt,
            })

        with open('debug-pos.txt', 'w') as f:
            f.write(str(TOTAL_IVA_FACT))

        frappe.db.set_value('Sales Invoice', doc.name, 'shs_total_iva_fac', TOTAL_IVA_FACT, update_modified=True)

    except:
        with open('debug-pos-error.txt', 'w') as f:
            f.write(str(frappe.get_traceback()))
