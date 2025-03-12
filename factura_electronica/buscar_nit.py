import frappe
import urllib.request
import urllib.parse
import json

def buscar_nombre (doc, method):
    """
    Busca el nombre con la API de INFILE
    """
    try:
        # Your custom logic here
        # Example: Accessing Sales Invoice data
        llave = frappe.db.sql("SELECT `tabConfiguracion Factura Electronica`.`llave_ws` FROM`tabConfiguracion Factura Electronica`WHERE`tabConfiguracion Factura Electronica`.`docstatus` = 1")
        alias = frappe.db.sql("SELECT `tabConfiguracion Factura Electronica`.`Alias` FROM`tabConfiguracion Factura Electronica`WHERE`tabConfiguracion Factura Electronica`.`docstatus` = 1")
        nit = doc.nit_face_customer
        
        payload = {
            "emisor_codigo": alias,
            "emisor_clave": llave,
            "nit_consulta": nit
        }
        payload_json = json.dumps(payload).encode('utf-8')
        frappe.log_error(f"Respuesta de la API FEL: ", {payload_json})

        # Configurar la solicitud POST
        url = "https://consultareceptores.feel.com.gt/rest/action"
        headers = {'Content-Type': 'application/json'}
        req = urllib.request.Request(url, data=payload_json, headers=headers)

        # Realizar la solicitud
        with urllib.request.urlopen(req) as response:
            response_json = json.loads(response.read().decode('utf-8'))
            frappe.log_error(f"Respuesta de la API FEL: {response_json}", "API FEL Respuesta")
            # Aquí podrías procesar la respuesta (response_json)
        return response_json

    except Exception as e:
            frappe.log_error(f"Error al conectar con la API de FEL: {e}", "Buscar NIT")
            return None