"""
Fixtures for testing repository features
"""
from copy import deepcopy


class RepositoryFactory:
    """
    Class for providing access to fixtures for testing repository features
    """

    @classmethod
    def repo_config(cls, spaces_in_org_ids=False):
        """
        Example repository config

        :param spaces_in_org_ids: Boolean - True - insert spaces into (some) organisation IDs; False (default) - no spaces
        :return: repository config
        """
        repo_config = deepcopy(REPO_CONFIG)
        if spaces_in_org_ids:
            repo_config["org_ids"] = ["ISNI:isni-12 34", "ISNI: isni 1111 2222 3333", "ROR: ror-123"]
        return repo_config

    @classmethod
    def match_provenance(cls):
        """
        Example match provenance

        :return: match provenance
        """
        return deepcopy(MATCH_PROV)

    @classmethod
    def useless_repo_config(cls):
        """
        Repository config which doesn't contain any useful data (but does contain data)

        :return: repo config
        """
        return deepcopy(USELESS_REPO_CONFIG)

    @classmethod
    def duplicate_repo_config(cls):
        """
        Repository config which contains duplicates, to be minimised by remove_redundancies
        
        :return: repo config
        """
        return deepcopy(DUPLICATE_REPO_CONFIG)

    @classmethod
    def invalid_repo_config(cls):
        # repository config which is invalid, should fail validation checks and raise errors
        return deepcopy(INVALID_CONFIG)


# repository config with no useful data
USELESS_REPO_CONFIG = {
    'domains': ["someunknowndomain.withsubdomain.com"],
    'name_variants': ["The Amazing University of Science, the Arts and Business (not to mention Medicine)"],
    'orcids': [],
    'emails': [],
    'postcodes': []
}

# Example repository config
REPO_CONFIG = {
    'domains': ["ucl.ac.uk", "unicollondon.ac.uk", "test.ac.uk", "aa_test.ac.uk"],
    'name_variants': ["UCL", "U.C.L", "University College"],
    'orcids': ["0000-0002-0136-3706"],
    'emails': ["goodemail@gmail.com"],
    'postcodes': ["SW1 0AA"],
    "grants": ["BB/34/juwef"],
    "org_ids": ["ISNI:isni-1234", "ISNI:isni111122223333", "ROR:ror-123"]

}

# Example repository config containing duplicate values
DUPLICATE_REPO_CONFIG = {
    'domains': ["ucl.ac.uk", "unicollondon.ac.uk", "unicollondon.ac.uk", "test.ac.uk", "aaa.test.ac.uk", "aa_test.ac.uk"],
    'name_variants': ["UCL", "University College", "U.C.L", "University College London", "UCL"],
    'orcids': ["0000-0002-0136-3706", "0000-0002-0136-3706"],
    'emails': ["goodemail@gmail.com", "duplicate@ucl.ac.uk", "duplicate@ucl.ac.uk"],
    'postcodes': ["SW1 0AA", "SW1 0AA"],
    "grants": ["BB/34/juwef", "BB/34/juwef"],
    "org_ids": ["ISNI:isni-1234", "ISNI:isni-1234", "ROR:ror-123", "ISNI:isni111122223333", "ROR:ror-123" ]
}

# invalid config example
INVALID_CONFIG = {
    'domains': [["should be a list"]],
    'name_variants': [{"shouldn't be a ": "dictionary"}]
}

# Example match provenance
MATCH_PROV = {
    'repo_id': 111,
    'note_id': 222,
    'provenance': [{
        "source_field": "postcode",
        "term": "SW1 0AA",
        "notification_field": "postcodes",
        "matched": "SW1 0AA",
        "explanation": "found matching postcodes"
    }, {
        "source_field": "author_orcids",
        "term": "0000-0002-0136-3706",
        "notification_field": "orcids",
        "matched": "0000-0002-0136-3706",
        "explanation": "'0000-0002-0136-3706' exactly matches '0000-0002-0136-3706'"
    }]
}
