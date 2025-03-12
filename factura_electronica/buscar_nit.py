import frappe

def buscar_nombre (doc, method):
    """
    Busca el nombre con la API de INFILE
    """
    try:
        # Your custom logic here
        frappe.log_error(f"Custom script executed for Sales Invoice: {doc.name}", "Sales Invoice On Submit")
        # Example: Accessing Sales Invoice data
        llave = frappe.db.get_value('Configuracion Factura Electronica', {'name': self.__config_name}, 'llave_ws')
        nit_company = str(frappe.db.get_value('Company', {'name': self.dat_fac[0]['company']}, 'nit_face_company').replace('-', '')).upper().strip()

        frappe.log_error(f"Customer: {customer}, llave: {llave}, nit {nit_company}", "Sales Invoice On Submit Info")

        #Add here the code that interacts with the guatemalan electronical invoice system.
        #For example, sending the invoice data to the API.

    except Exception as e:
        frappe.log_error(f"Error in custom script: {e}", "Sales Invoice On Submit Error")