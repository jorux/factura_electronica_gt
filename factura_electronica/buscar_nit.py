import frappe

def buscar_nombre (doc, method):
    """
    Busca el nombre con la API de INFILE
    """
    try:
        # Your custom logic here
        # Example: Accessing Sales Invoice data
        llave = frappe.db.sql("SELECT `tabConfiguracion Factura Electronica`.`llave_ws` AS `llave_ws`FROM`tabConfiguracion Factura Electronica`WHERE`tabConfiguracion Factura Electronica`.`docstatus` = 1")
        frappe.log_error(f", llave: {llave}, nit {doc.nit_face_customer}", "Sales Invoice On Submit Info")

        #Add here the code that interacts with the guatemalan electronical invoice system.
        #For example, sending the invoice data to the API.

    except Exception as e:
        frappe.log_error(f"Error in custom script: {e}", "Sales Invoice On Submit Error")