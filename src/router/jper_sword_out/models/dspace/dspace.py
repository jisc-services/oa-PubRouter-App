"""
DSpace models for SWORD2:

* DSpace RIOXX XML - see XML doc here:
https://github.com/jisc-services/Public-Documentation/blob/master/PublicationsRouter/sword-out/DSpace-RIOXX-XML.md

* DSpace Vanilla XML - see XML documentation here: https://wiki.eprints.org/w/XML_Export_Format

"""
from sword2.models import SwordModel

# --- DSpace RIOXX XML --- #

class DspaceRioxx(SwordModel):
    """
    Class for DSpace RIOXX XML structure
    """
    all_namespaces = {
        "ali": "http://www.niso.org/schemas/ali/1.0/",
        "dcterms": "http://purl.org/dc/terms/",
        "rioxxterms": "http://www.rioxx.net/schema/v2.0/rioxx/",
        "pubr": "http://pubrouter.jisc.ac.uk/dspacerioxx/",
        None: "http://www.w3.org/2005/Atom"
    }
    _namespaces = all_namespaces
    _root = "entry"     # Root tag is <entry>

    def __init__(self, data=None):
        """
        Initialise class
        :param data: optional XML data to instantiate the class from
        """
        super(DspaceRioxx, self).__init__(data)


# --- DSpace Vanilla XML --- #

class DspaceVanilla(SwordModel):
    """
    Class for DSpace Vanilla XML structure
    """
    all_namespaces = {
        "dcterms": "http://purl.org/dc/terms/",
        "sword": "http://purl.org/net/sword/terms/",
        None: "http://www.w3.org/2005/Atom"
    }
    _namespaces = all_namespaces
    _root = "entry"     # Root tag is <entry>

    def __init__(self, data=None):
        """
        Initialise class
        :param data: optional XML data to instantiate the class from
        """
        super(DspaceVanilla, self).__init__(data)

