"""
Native XML model for SWORD2:

Used to create XML directly from Router notification JSON dict
"""
from sword2.models import SwordModel


class Native(SwordModel):
    """
    Class for Native XML structure.

    """
    all_namespaces = {}
    _namespaces = all_namespaces
    _root = "entry"     # Root tag is <entry>

    def __init__(self, data=None):
        """
        Initialise class
        :param data: optional XML data to instantiate the class from
        """
        # Set default root to <entry> if none supplied
        # if alt_root is None:
        #     alt_root = "entry"
        # Native._root = self.tagname_to_namespaced_tagname(alt_root)

        super(Native, self).__init__(data)

