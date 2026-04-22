#!/usr/bin/env python
"""
Extract all JATS XML files from zip files in Router's Store (/Incoming/store) and place it in a separate directory:
/Incoming/XML where it can be analysed.

"""
import os
from lxml import etree
from zipfile import ZipFile
from octopus.lib.data import decode_non_xml_html_entities, UTF8_BYTES

xml_dir = '/Incoming/XML'
store_root = '/Incoming/store'
if not os.path.exists(store_root):
    print(f"\n**** ERROR: directory '{store_root}' does not exist.\n")
    exit(1)


log_fname = os.path.join("/tmp", "xml_analysis.txt")
log_file = open(log_fname, "w", encoding="utf-8")

try:
    os.mkdir(xml_dir)
except Exception as e:
    msg = f"Cannot create directory {xml_dir}."
    print(msg)

def analyse_xml(etree_root):
    """
    Function that performs analysis of XML
    """
    pass

# Loop through '/Incoming/store'
for note_dir in os.listdir(store_root):
    note_id = os.path.basename(note_dir)

    zip_file = os.path.join(store_root, note_dir, 'ArticleFilesJATS.zip')
    if not os.path.exists(zip_file):
        log_file.write(f"Zip file not found {zip_file}\n")
        continue

    with ZipFile(zip_file, "r") as in_zip_file:
        for zip_info in in_zip_file.infolist():
            fpath = zip_info.filename
            fname = os.path.basename(fpath)
            # Got our XML flie
            if fname.endswith(".xml"):
                # Write XML file from zip file to temp location
                xml_string = in_zip_file.read(zip_info)

                try:
                    etree_root = etree.fromstring(xml_string)
                except etree.XMLSyntaxError as e:
                    # There were problems with parsing the XML - use the recover parser and unescape html entities
                    # to see if we can now parse it
                    try:
                        etree_root = etree.XML(decode_non_xml_html_entities(xml_string, UTF8_BYTES),
                                               etree.XMLParser(recover=True, encoding="utf-8"))
                    except Exception as ee:
                        e = ee  # Overwrite original exception value

                    if etree_root is not None:
                        log_file.write(f"Processing {fname} - Unable to parse XML 1st attempt, succeeded after 2nd. Initial Syntax Error: {str(e)}\n")
                    else:
                        log_file.write(f"Processing {fname} - Failed to parse XML on 2nd attempt - Syntax Error: {str(e)}\n")

                except Exception as e:
                    log_file.write(f"Processing {fname} - Failed to parse XML on 1st attempt - {repr(e)}.\n")
                
                if etree_root is None:
                    break
                    
                out_fname = os.path.join(xml_dir, f"{note_id}_{fname}")
                with open(out_fname, "wb", encoding='utf-8') as xmlfile:
                    try:
                        xmlfile.write(etree.tostring(etree_root, pretty_print=True))
                    except Exception as e:
                        log_file.write(f"Processing {fname} - Can't write formatted XML - {str(e)}\n")
                        xmlfile.write(xml_string)
                log_file.write(f"Created XML file {out_fname}\n")

                analyse_xml(etree_root)
                break

log_file.close()