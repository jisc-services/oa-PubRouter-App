"""
Model objects used to represent interactions with repositories
"""
from octopus.lib import dataobj
from router.shared.mysql_dao import MatchProvenanceDAO


class MatchProvenance(dataobj.DataObj, MatchProvenanceDAO):
    """
    Class to represent a record of a match between a RepositoryConfig and a RoutingMetadata object

    See the core system model documentation for details on the JSON structure used by this model.
    """

    def __init__(self, raw=None):
        """
        Create a new instance of the MatchProvenance object, optionally around the
        raw python dictionary.

        If supplied, the raw dictionary will be validated against the allowed structure of this
        object, and an exception will be raised if it does not validate

        :param raw: python dict object containing the metadata
        """
        # struct = {
        #     "fields": {
        #         "created": {"coerce": "unicode"},
        #         "note_id": {"coerce": "integer"},
        #         "repo_id": {"coerce": "integer"}
        #     },
        #     "lists": {
        #         "provenance": {"contains": "object"}
        #     },
        #     "structs": {
        #         "provenance": {
        #             "fields": {
        #                 "source_field": {"coerce": "unicode"},
        #                 "term": {"coerce": "unicode"},
        #                 "notification_field": {"coerce": "unicode"},
        #                 "matched": {"coerce": "unicode"},
        #                 "explanation": {"coerce": "unicode"}
        #             }
        #         }
        #     }
        # }
        # self._add_struct(struct)
        super(MatchProvenance, self).__init__(raw=raw)

    @property
    def repo_id(self):
        """
        Repository id to which the match pertains

        :return: repository id
        """
        return self._get_single("repo_id")

    @repo_id.setter
    def repo_id(self, val):
        """
        Set the repository id to which the match pertains

        :param val: repository id
        """
        self._set_single("repo_id", val)

    @property
    def note_id(self):
        """
        Notification id to which the match pertains

        :return: notification id
        """
        return self._get_single("note_id")

    @note_id.setter
    def note_id(self, val):
        """
        Set the notification id to which the match pertains

        :param val: notification id
        """
        self._set_single("note_id", val)

    @property
    def provenance(self):
        """
        List of match provenance events for the combination of the repository id and notification id
        represented by this object

        Provenance records are of the following structure:

        ::

            {
                "source_field" : "<field from the configuration that matched>",
                "term" : "<term from the configuration that matched>",
                "notification_field" : "<field from the notification that matched>"
                "matched" : "<text from the notification routing metadata that matched>",
                "explanation" : "<any additional explanatory text to go with this match (e.g. description of levenstein criteria)>"
            }

        :return: list of provenance objects
        """
        return self._get_list("provenance")

    def add_provenance(self, source_field, term, notification_field, matched, explanation):
        """
        add a provenance record to the existing list of provenances

        :param source_field: the field from the repository configuration from which a match was drawn
        :param term: the text from the repository configuration which matched
        :param notification_field: the field from the notification that matched
        :param matched: the text from the notification that matched
        :param explanation: human readable description of the nature of the match
        """
        obj = {
            "source_field": source_field,
            "term": term,
            "notification_field": notification_field,
            "matched": matched,
            "explanation": explanation
        }
        self._add_to_list("provenance", obj)

    @classmethod
    def pull_by_notification(cls,  notification_id):
        return cls.pull_all(notification_id, pull_name="all_by_note_id")

    @classmethod
    def user_readable_match_param_type(cls, matching_param):
        """
        Takes matching parameter fields as defined internally, returns matching parameters as submitted by users
        For example, "name_variants" -> "Name Variant", etc..

        :param matching_param: internal matching parameter field value

        :return: human readable string of matching parameter
        """
        mapping = {
            "org_ids": "Organisation Id",
            "name_variants": "Name Variant",
            "postcodes": "Postcode",
            "domains": "Domain",
            "grants": "Grant Number",
            "author_orcids": "ORCID",
            "author_emails": "Author Email"
        }
        # get mapping
        param_type = mapping.get(matching_param)
        # If no mapping exists derive from internal field name - remove last char (s), replace underscore, capitalize
        if param_type is None:
            param_type = matching_param[:-1].replace("_", " ").capitalize()
        return param_type
