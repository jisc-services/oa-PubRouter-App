from octopus.lib import dataobj
from router.shared.mysql_dao import ContentLogDAO


class ContentLog(dataobj.DataObj, ContentLogDAO):
    """
    Saves details in database of each content retrieval.
    {
        "id" : "<unique persistent id>",
        "created" : "<date record created>",
        "acc_id" : "<ID of user ac that requested the content>",
        "note_id": "<the ID of notification the requested content is associated with>",
        "filename": "<the requested filename if any>",
        "source" : "<one of store, proxy, notfound>",
    }
    """

    # @property
    # def acc_id(self):
    #     return self._get_single("acc_id")
    #
    # @acc_id.setter
    # def acc_id(self, id):
    #     self._set_single("acc_id", id, coerce=dataobj.to_int)
    #
    # @property
    # def note_id(self):
    #     return self._get_single("note_id")
    #
    # @note_id.setter
    # def note_id(self, id):
    #     self._set_single("note_id", id, coerce=dataobj.to_int)
    #
    # @property
    # def filename(self):
    #     return self._get_single("filename")
    #
    # @filename.setter
    # def filename(self, filename):
    #     self._set_single("filename", filename)
    #
    # @property
    # def source(self):
    #     return self._get_single("source")
    #
    # @source.setter
    # def source(self, source):
    #     self._set_single("source", source)
