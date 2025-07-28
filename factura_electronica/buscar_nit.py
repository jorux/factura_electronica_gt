import frappe



import urllib.request


import urllib.parse


import json




@frappe.whitelist()
def buscar_nombre (doc, method):


    """


    Busca el nombre con la API de INFILE


    """


    if doc.es_dpi == False:


        try:


            # Your custom logic here


            # Example: Accessing Sales Invoice data


            result_llave = frappe.db.sql("SELECT `tabConfiguracion Factura Electronica`.`llave_ws` FROM `tabConfiguracion Factura Electronica` WHERE `tabConfiguracion Factura Electronica`.`docstatus` = 1")


            llave = result_llave[0][0] if result_llave else None #Extrae la llave, si no existe devuelve None.


            result_alias = frappe.db.sql("SELECT `tabConfiguracion Factura Electronica`.`Alias` FROM `tabConfiguracion Factura Electronica` WHERE `tabConfiguracion Factura Electronica`.`docstatus` = 1")


            alias = result_alias[0][0] if result_alias else None #Extrae el alias, si no existe devuelve None.


            nit = (doc.nit_face_customer).replace('-', '').upper().strip()


            


            payload = {


                "emisor_codigo": alias,


                "emisor_clave": llave,


                "nit_consulta": nit


            }


            payload_json = json.dumps(payload).encode('utf-8')


            #test


            # Configurar la solicitud POST


            url = "https://consultareceptores.feel.com.gt/rest/action"


            headers = {'Content-Type': 'application/json'}


            req = urllib.request.Request(url, data=payload_json, headers=headers)





            # Realizar la solicitud


            with urllib.request.urlopen(req) as response:


                response_json = json.loads(response.read().decode('utf-8'))

                frappe.log_error("'nit2'", response_json)
                # Extraer el nombre y asignarlo a doc.nombre_segun_sat


                if response_json and 'nombre' in response_json:


                    nombre = response_json['nombre']


                    frappe.db.set_value("Sales Invoice",{"name":doc.name},{"nombre_segun_sat":nombre})


                else:


                    frappe.log_error("La respuesta de la API no contiene el campo 'nombre'", "Error Extracción Nombre") #Log en caso de no existir nombre.
                    frappe.db.set_value("Sales Invoice",{"name":doc.name},{"nombre_segun_sat":customer_name})




            return response_json





        except Exception as e:


                frappe.log_error(f"Error al conectar con la API de FEL: {e}", "Buscar NIT")
                frappe.db.set_value("Sales Invoice",{"name":doc.name},{"nombre_segun_sat":"customer_name"})

                return None


    else:


        try:


            # Your custom logic here


            # Example: Accessing Sales Invoice data


            result_llave = frappe.db.sql("SELECT `tabConfiguracion Factura Electronica`.`llave_ws` FROM `tabConfiguracion Factura Electronica` WHERE `tabConfiguracion Factura Electronica`.`docstatus` = 1")


            llave = result_llave[0][0] if result_llave else None #Extrae la llave, si no existe devuelve None.


            result_alias = frappe.db.sql("SELECT `tabConfiguracion Factura Electronica`.`Alias` FROM `tabConfiguracion Factura Electronica` WHERE `tabConfiguracion Factura Electronica`.`docstatus` = 1")


            alias = result_alias[0][0] if result_alias else None #Extrae el alias, si no existe devuelve None.


            nit = (doc.nit_face_customer).replace('-', '').upper().strip()



            


            payload = {


                "emisor_codigo": alias,


                "emisor_clave": llave,


                "cui": nit


            }

            frappe.log_error(f"payload dpi", payload)
            payload_json = json.dumps(payload).encode('utf-8')





            # Configurar la solicitud POST


            url = "https://certificador.feel.com.gt/api/v2/servicios/externos/cui"


            headers = {'Content-Type': 'application/json'}


            req = urllib.request.Request(url, data=payload_json, headers=headers)





            # Realizar la solicitud


            with urllib.request.urlopen(req) as response:


                response_json = json.loads(response.read().decode('utf-8'))
                frappe.log_error("'nombre'", response_json)

                # Extraer el nombre y asignarlo a doc.nombre_segun_sat

                frappe.log_error(f"response dpi", response_json)
                if response_json and 'nombre' in response_json:


                    nombre = response_json['nombre']


                    frappe.db.set_value("Sales Invoice",{"name":doc.name},{"nombre_segun_sat":nombre})


                else:


                    frappe.log_error("La respuesta de la API no contiene el campo 'nombre'", "Error Extracción Nombre") #Log en caso de no existir nombre.

                    frappe.db.set_value("Sales Invoice",{"name":doc.name},{"nombre_segun_sat":"customer_name"})




            return response_json





        except Exception as e:


                frappe.log_error(f"Error al conectar con la API de FEL: {e}", "Buscar NIT")

                frappe.db.set_value("Sales Invoice",{"name":doc.name},{"nombre_segun_sat":"customer_name"})
                
                frappe.log_error("4")

                return None