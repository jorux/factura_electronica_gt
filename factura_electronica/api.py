# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import frappe
from frappe import _
from frappe.utils.file_manager import get_file_doc, upload
import requests
import xmltodict

from request_xml import construir_xml
from datetime import datetime, date
from guardar_factura import guardar_factura_electronica as guardar
from guardar_factura import actualizarTablas as actualizartb
from valida_errores import encuentra_errores as errores
from valida_errores import normalizar_texto

# Permite trabajar con acentos, ñ, simbolos, etc
import os, sys
reload(sys)
sys.setdefaultencoding('utf-8')

def validar_configuracion():
    """Permite verificar que exista una configuración validada para Factura Electrónica,
       retorna 1 de 3 opciones:
       1 : Una configuracion valida
       2 : Hay mas de una configuracion
       3 : No hay configuraciones"""
    # verifica que exista un documento validado, docstatus = 1 => validado
    if frappe.db.exists('Configuracion Factura Electronica', {'docstatus': 1}):

        configuracion_valida = frappe.db.get_values('Configuracion Factura Electronica',
                                                   filters={'docstatus': 1},
                                                   fieldname=['name'], as_dict=1)
        if (len(configuracion_valida) == 1):
            return (int(1), str(configuracion_valida[0]['name']))

        elif (len(configuracion_valida) > 1):
            return (int(2), 'Error 2')

    else:
        return (int(3), 'Error 3')

@frappe.whitelist()
def generar_factura_electronica(serie_factura, nombre_cliente, pre_se):
    """Verifica que todo este correctamente configurado para realizar una peticion
    a INFILE para generar la factura electronica"""

    serie_original_factura = str(serie_factura)
    nombre_del_cliente = str(nombre_cliente)
    prefijo_serie = str(pre_se)

    validar_config = validar_configuracion()

    # Si cumple, procede a validar y generar factura electronica
    if (validar_config[0] == 1):
        # Verifica si existe ya una factura electronica con la misma serie, evita duplicacion
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
        else:
            nombre_config_validada = str(validar_config[1])
            # Verificacion existencia series configuradas, en Configuracion Factura Electronica
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

                # Funcion obtiene los datos necesarios y construye el xml
                construir_xml(serie_original_factura, nombre_del_cliente, prefijo_serie, series_configuradas, nombre_config_validada)

                try:
                    # Si existe problemas al abrir archivo XML anteriormente generado
                    # mostrara un error.
                    envio_datos = open('envio_request.xml', 'r').read()
                except:
                    frappe.msgprint(_('Error al abrir los datos XML. Comuniquese al No.'))
                else:
                    try:
                        # Si existe un error en la captura de tiempo del momento de envio mostrara un error
                        tiempo_enviado = datetime.now()
                    except:
                        frappe.msgprint(_('Error: No se puede capturar el momento de envio. Comuniquese al No.'))
                    else:
                        try:
                            # Si existe un problema con la comunicacion a INFILE o se sobrepasa el tiempo de espera
                            # Mostrara un error
                            # 2018-01-23 Se valido claramente que funciona el envío al servidor de INFILE
                            # URL de listener de INFILE FUNCIONA OK!!!
                            url = str(url_configurada[0]['url_listener'])
                            # CABECERAS: Indican el tipo de datos FUNCIONA OK!!!
                            headers = {"content-type": "text/xml"}
                            # FUNCIONA OK!!!
                            response = requests.post(url, data=envio_datos, headers=headers, timeout=10)
                            #respuesta = response.content
                        except:
                            frappe.msgprint(_('Error en la Comunicacion al servidor de INFILE. Verifique al PBX: +502 2208-2208'))
                        else:
                            try:
                                # Si no se recibe ningun dato del servidor de INFILE mostrara el error
                                # Guarda el contenido de la respuesta enviada por INFILE
                                respuesta = response.content
                            except:
                                frappe.msgprint(_('Error en la comunicacion no se recibieron datos de INFILE'))
                            else:
                                try:
                                    # xmltodic parsea la respuesta por parte de INFILE
                                    documento_descripcion = xmltodict.parse(respuesta)
                                    # En la descripcion se encuentra el mensaje, si el documento electronico se realizo con exito
                                    descripciones = (documento_descripcion['S:Envelope']['S:Body']['ns2:registrarDteResponse']['return']['descripcion'])
                                except:
                                    frappe.msgprint(_('''Error: INFILE no pudo recibir los datos:''' + respuesta))
                                else:
                                    # La funcion errores se encarga de verificar si existen errores o si la
                                    # generacion de factura electronica fue exitosa
                                    errores_diccionario = errores(descripciones)

                                    if (len(errores_diccionario) > 0):
                                        try:
                                            # Si el mensaje indica que la factura electronica se genero con exito se procede
                                            # a guardar la respuesta de INFILE en la DB
                                            if ((str(errores_diccionario['Mensaje']).lower()) == 'dte generado con exito'):

                                                cae_fac_electronica = guardar(respuesta, serie_original_factura, tiempo_enviado)
                                                # frappe.msgprint(_('FACTURA GENERADA CON EXITO'))
                                                # el archivo rexpuest.xml se encuentra en la ruta, /home/frappe/frappe-bench/sites

                                                with open('respuesta.xml', 'w') as recibidoxml:
                                                    recibidoxml.write(respuesta)
                                                    recibidoxml.close()

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

                                            frappe.msgprint(_('NO GENERADA'))

            else:
                frappe.msgprint(_('''La serie utilizada en esta factura no esta en la Configuracion de Factura Electronica.
                                    Por favor configura la serie <b>{0}</b> en <b>Configuracion Factura Electronica</b> e intenta de nuevo.
                                    '''.format(prefijo_serie)))

    # Si cumple, existe mas de una configuracion validada
    if (validar_config[0] == 2):
        frappe.msgprint(_('Existe más de una configuración para factura electrónica. Verifique que solo exista una validada'))
    # Si cumple, no existe configuracion validada
    if (validar_config[0] == 3):
        frappe.msgprint(_('No se encontró una configuración válida. Verifique que exista una configuración validada'))

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
    '''Descarga factura en servidor y registra en base de datos'''

    modalidad_configurada = validar_configuracion()
    ruta_archivo = 'site1.local/private/files/factura-electronica/'

    if modalidad_configurada[0] == 1:
        configuracion_factura = frappe.db.get_values('Configuracion Factura Electronica',
                                                    filters={'name': modalidad_configurada[1]},
                                                    fieldname=['url_listener', 'descargar_pdf_factura_electronica',
                                                               'url_descarga_pdf'], as_dict=1)

        url_archivo = configuracion_factura[0]['url_descarga_pdf'] + cae_de_factura_electronica

        if configuracion_factura[0]['descargar_pdf_factura_electronica'] == 'ACTIVAR':

            if not frappe.db.exists('File', {'file_name': (nombre_archivo + '.pdf')}):

                if os.path.exists(ruta_archivo):
                    descarga_archivo = os.system('curl -s -o {0}{1}.pdf {2}'.format(ruta_archivo, nombre_archivo, url_archivo))
                else:
                    frappe.create_folder(ruta_archivo)
                    descarga_archivo = os.system('curl -s -o {0}{1}.pdf {2}'.format(ruta_archivo, nombre_archivo, url_archivo))

                if descarga_archivo == 0:
                    bytes_archivo = os.path.getsize("site1.local/private/files/factura-electronica/{0}.pdf".format(nombre_archivo))

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
    '''Funcion para obtener los datos de impuestos dependiendo el tipo de cuenta recibido'''
    if frappe.db.exists('Account', {'name': name_account_tax_gt}):

        datos_cuenta = frappe.db.get_values('Account', filters={'name': name_account_tax_gt},
                                            fieldname=['tax_rate', 'name'], as_dict=1)

        return str(datos_cuenta[0]['tax_rate'])
    else:
        frappe.msgprint(_('No existe cuenta relacionada con el producto'))
