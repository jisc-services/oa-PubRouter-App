"""
Eprints models for SWORD2:

* Eprints RIOXXplus XML - see XML doc here: https://github.com/jisc-services/Public-Documentation/blob/development/PublicationsRouter/sword-out/EPrints-RIOXX-XML.md

* EPrints Vanilla XML - see XML documentation here: https://wiki.eprints.org/w/XML_Export_Format

"""
from sword2.models import SwordModel

# --- EPRINTS RIOXXplus XML --- #

class EprintsRioxxPlus(SwordModel):
    """
    Class for Eprints RIOXXplus XML structure.

    Note: The rioxxterms namespace URI used here is NOT correct - it should be
          http://www.rioxx.net/schema/v2.0/rioxxterms/. However, the EPrints RIOXXplus 2 Perl plugin, which is installed
          on many EPrints repositories, uses the URI specified below and will categorise deposits as 'other' unless this
          value is used.
    """
    all_namespaces = {
        "dcterms": "http://purl.org/dc/terms/",
        "pr": "http://pubrouter.jisc.ac.uk/rioxxplus/",
        "rioxxterms": "http://www.rioxx.net/schema/v2.0/rioxx/",
        "ali": "http://www.niso.org/schemas/ali/1.0/"
    }

    _namespaces = all_namespaces

    def __init__(self, alt_root=None, data=None, new_ver=False):
        """
        Initialise class
        :param alt_root: Alternative root element (if not specified then default "entry" will be used)
        :param data: optional XML data to instantiate the class from
        :param new_ver: boolean indicates if pr namespace is to be adjusted to "v2.0" - TRANSITIONAL code

        NB. In due course when TRANSITIONAL code is removed, the `all_namespaces` dict should be initialised with the
        "pr": "http://pubrouter.jisc.ac.uk/rioxxplus/v2.0/"
        """
        # TRANSITIONAL code - If new version of RIOXXplus XML
        pr_ns = "http://pubrouter.jisc.ac.uk/rioxxplus/v2.0/" if new_ver else "http://pubrouter.jisc.ac.uk/rioxxplus/"
        EprintsRioxxPlus.all_namespaces["pr"] = pr_ns
        EprintsRioxxPlus._namespaces["pr"] = pr_ns
        # END-TRANSITIONAL CODE

        # Set default root to <entry> if none supplied
        if alt_root is None:
            alt_root = "entry"
        EprintsRioxxPlus._root = EprintsRioxxPlus.tagname_to_namespaced_tagname(alt_root)

        super(EprintsRioxxPlus, self).__init__(data)



# --- EPRINTS Vanilla XML --- #

class EprintsVanilla(SwordModel):
    """
    Class for Eprints Vanilla XML structure
    """
    all_namespaces = {
        "ep": "http://eprints.org/ep2/data/2.0"
    }

    _namespaces = {
        None: "http://eprints.org/ep2/data/2.0"
    }

    def __init__(self, alt_root=None, data=None):
        if alt_root is None:
            alt_root = "ep:eprints"
        EprintsVanilla._root = EprintsVanilla.tagname_to_namespaced_tagname(alt_root)

        super(EprintsVanilla, self).__init__(data)

