# Copyright (c) 2020, Si Hay Sistema and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

import requests
import xmltodict

import frappe
from frappe import _, _dict

from reportlab.graphics.barcode import qr
from reportlab.graphics.shapes import Drawing
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.graphics.shapes import *
from reportlab.graphics import renderPDF
from reportlab.graphics import renderSVG

import xml.etree.ElementTree as ET

#----------------------------------------------------------------------
@frappe.whitelist()
def create_fel_svg_qrcode(authorization_number):
    """
    Create QR Code and return it as an svg string.
    Takes in variable for FEL Authorization Number for QR Code assembly on-the-fly
    SVG String currently is a simple string parsing technique, not a sophisticated XML parsing.
    """
    qr_code_url = 'https://report.feel.com.gt/ingfacereport/ingfacereport_documento?uuid=' + str(authorization_number)

    # We create a list with possible content options for the QR code.
    # This helps with quick changes during first production run.
    # qr_contents = ['https://fogliasana.com/','https://sihaysistema.com',qr_code_url]

    # Assign the colors
    # We use CMYK color assignment for print
    FSBluecmyk = colors.PCMYKColor(84.29,50.99,0,0)
    FSGreenCMYK = colors.PCMYKColor(60.83,0,95.9,0)

    unit = 300
    scaling_factor = 300.0
    # en_US:  First, we draw a QR code with the selected contents. For now it is a URL. Plan is to call a webpage which calls a Python method delivering data for that specific shipment.
    qr_code = qr.QrCodeWidget(qr_code_url,barFillColor=FSBluecmyk, x=0, y=0, barWidth=100, barHeight=100)
    # en_US: We get the bounds of the drawn QR Code. This will help resize.
    bounds = qr_code.getBounds() # Returns position x, position y, size x, size y
    # en_US: We set the width of the QR code drawing to the width bounds returned
    width = bounds[2] - bounds[0]
    # en_US: We set the width of the QR code drawing to the width bounds returned
    height = bounds[3] - bounds[1]
    # en_US: We create a drawing container with a specified size. We adjust the container to fit the QR Code, using the object size and a percentage amount
    qr1 = Drawing(120, 120)
    #qr1 = Drawing(unit, unit, transform=[(width/scaling_factor),0,0,(height/scaling_factor),0,0])

    # en_US: We add the QR code to the code container
    qr1.add(qr_code)

    # en_US: We draw contents of d container with QR Code, on canvas c, at x position, y position
    # renderSVG.draw(d, c, qr_code_x_pos_mm*mm, qr_code_y_pos_mm*mm)

    # We now draw the SVG to an SVG XML-based string
    svg_as_string = renderSVG.drawToString(qr1)
    # DEBUG ONLY, Save to a file.
    #renderSVG.drawToFile(qr1, 'QRCode.svg')

    # We now parse to XML, by passing to a string again, without the extra tags
    # yroot = ET.fromstring(svg_as_string)
    # print(svg_as_string)
    # print(myroot.tag)
    # print(myroot)

    # qr_svg_string = svg_as_string

    # do not return this, it's a mess!!
    # qr_svg_string = ET.tostring(myroot, encoding="utf-8", method="xml")

    # find position of first '>'
    # find position of second '>'
    # Erase everything before second '>'
    first = svg_as_string.find('>',0)
    second = svg_as_string.find('>',first+1)
    # print(first)
    # print(second)
    print(svg_as_string[second+2:])

    # We are slicing through this:
    '''
    <?xml version="1.0" encoding="utf-8"?>
    <!DOCTYPE svg PUBLIC '-//W3C//DTD SVG 1.0//EN' 'http://www.w3.org/TR/2001/REC-SVG-20010904/DTD/svg10.dtd'>
    <
    '''
    qr_svg_string = svg_as_string[second+2:]

    return qr_svg_string
