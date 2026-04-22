"""
Fixtures for testing the API
"""
from copy import deepcopy


class APIFactory:
    """
    Class which provides access to the various fixtures used for testing the API
    """

    @classmethod
    def incoming_notification_dict(cls,
                                   with_content=False,
                                   bad=False,
                                   created_date=None,
                                   no_match_data=False,
                                   provider_route=None,
                                   note_vers=None,
                                   good_affs=False,
                                   no_links=False,
                                   set_auth_type=None,
                                   remove_auth_id=None
                                   ):
        """
        A dict representing a notification that may come in via the API

        :param with_content: Boolean - True: add packaging format in "content" field; False - no "content" field
        :param bad: Boolean - True: Use invalid notification dict; False: Use OK notification
        :param created_date: String - Created-date to set (or None)
        :param no_match_data: Boolean - True - delete data used for matching; Falose - leave notification as is
        :param provider_route: String - value to set "provider.route" to
        :param note_vers: String - Version of note to produce - set to "3" to produce ver3, otherwise leave empty
        :param good_affs: Boolean - True: set all author & contributor affiliations to a particular good set
        :param no_links: Boolean - True: Remove links & has_pdf flag from notification
        :param set_auth_type: String - Value to set author.type to (with the addition of a '-x' counter)
        :param remove_auth_id: String - Indicates whether to modify Author IDs -
                                        Values "all": Remove all author IDs; "orcid": Remove all ORCID IDs
        :return: notification dict (V3 or V4)
        """
        if bad:
            note = deepcopy(BAD_INCOMING)
        else:
            note = deepcopy(INCOMING_V4)

        if set_auth_type:
            x = 1
            for auth in note["metadata"]["author"]:
                auth["type"] = f"{set_auth_type}-{x}"
                x += 1
        if good_affs:
            for auth_contrib in ("author", "contributor"):
                for auth in note["metadata"][auth_contrib]:
                    auth["affiliations"] = deepcopy(OK_AFF_LIST)
        # For V3 notifications need to modify author & contributor affiliations and remove new fields
        if note_vers == "3":
            note["vers"] = "3"
            md = note["metadata"]
            # Replace affiliations list of dicts by affiliation string
            for auth_contrib in ("author", "contributor"):
                for auth in md[auth_contrib]:
                    aff_str = ""
                    for aff in auth["affiliations"]:
                        aff_str += aff.get("raw", "")
                    auth["affiliation"] = aff_str
                    del auth["affiliations"]
            del md["peer_reviewed"]
            del md["ack"]
            del md["article"]["e_num"]

        if remove_auth_id:
            # Remove ALL Auth IDs
            if remove_auth_id == "all":
                for auth in note["metadata"]["author"]:
                    del auth["identifier"]
            # Remove ALL ORCIDS
            elif remove_auth_id == "orcid":
                for auth in note["metadata"]["author"]:
                    # New IDs list are all those WITHOUT 'type' == 'orcid'
                    new_ids = [id_ for id_ in auth["identifier"] if id_["type"] != "orcid"]
                    auth["identifier"] = new_ids

        if created_date:
            if note_vers == "3":
                note["created_date"] = created_date
            else:
                note["created"] = created_date
        if with_content:
            note["content"] = {"packaging_format": "https://pubrouter.jisc.ac.uk/FilesAndJATS"}
        if no_match_data:
            for auth in note["metadata"]["author"]:
                # ZZZ remove "affiliation" when v3 no longer supported
                for field in ("identifier", "affiliation", "affiliations"):
                    if field in auth:
                        del auth[field]
            for fund in note["metadata"]["funding"]:
                if "grant_numbers" in fund:
                    del fund["grant_numbers"]
        if provider_route:
            note["provider"]["route"] = provider_route
        if no_links:
            del note["links"]
            del note["has_pdf"]

        return note

    @classmethod
    def outgoing_notification_dict(cls, with_content=False, note_vers=None):
        """
        A dict representing an outgoing notification (provider or not) that may go out via the API

        :param with_content: Boolean - True: add packaging format in "content" field; False - no "content" field
        :param note_vers: String - value of notification version (default above should be set to current API_VERSION config value)
        :return: notification dict (V3 or V4)
        """
        outgoing = cls.incoming_notification_dict(
            with_content=with_content, created_date="2015-02-02T00:00:00Z", note_vers=note_vers)
        outgoing["id"] = "123" if note_vers == "3" else 123
        outgoing["analysis_date"] = "2015-02-02T00:00:00Z"
        outgoing["metadata"]["license_ref"][0]["best"] = True
        return outgoing


OK_AFF_LIST = [
    {
        "identifier": [{"type": "ISNI", "id": "isni 1111 2222 3333"}, {"type": "ROR", "id": "ror-123"}],
        "org": "OK Aff org",
        "dept": "OK dept",
        "street": "OK street",
        "city": "Oxford",
        "state": "Oxfordshire",
        "postcode": "OX1 2OK",
        "country": "England",
        "country_code": "GB",
        "raw": "OK Aff org, OK dept, OK street, Oxford, Oxfordshire, OX1 2OK, England, ISNI: isni 1111 2222 3333, ROR: ror-123"
    }
]

# Example incoming notification
INCOMING_V4 = {
    "vers": "4",
    "category": 'A',
    "has_pdf": True,
    "event": "accepted",
    "provider": {
        "agent": "pub-name/0.1"
    },
    "links": [
        {
            "type": "splash",
            "format": "text/html",
            "url": "http://example.com/article/1"
        },
        {
            "type": "fulltext",
            "format": "application/pdf",
            "url": "http://example.com/article/1/pdf"
        }
    ],
    "metadata": {
        "journal": {
            "title": "Journal of Important Things",
            "abbrev_title": "Abbreviated Alternative Article",
            "volume": "Volume-num",
            "issue": "Issue-num",
            "publisher": ["Journal of Important Things"],
            "identifier": [
                {"type": "other", "id": "over there"}
            ]
        },
        "article": {
            "title": "Alternative Article",
            "subtitle": ["Alternative Article SUBtitle"],
            "type": "paper",
            "version": "VOR",
            "start_page": "Start-pg",
            "end_page": "End-pg",
            "page_range": "Page-range",
            "num_pages": "Total-pages",
            "e_num": "e-Location",
            "language": ["eng"],
            "abstract": "Abstract of the work ",
            "identifier": [
                {"type": "doi", "id": "10.pp/jit.1"},
                {"type": "url", "id": "http://jit.com/1"}
            ],
            "subject": ["arts", "medicine", "literature"]
        },
        "author": [{
            "type": "corresp",
            "name": {
                "firstname": "Richard",
                "surname": "Jones",
                "fullname": "Richard Jones",
                "suffix": "Sr."
            },
            "organisation_name": "Potty Labs",
            "identifier": [
                {"type": "orcid", "id": "0000-0002-4797-908X"},
                {"type": "email", "id": "richard@example.com  "}
            ],
            "affiliations": [
                {
                    "identifier": [{"type": "ISNI", "id": "isni 1111 2222 3333"}, {"type": "ROR", "id": "ror-123"}],
                    "org": "Cottage Labs org",
                    "dept": "Moonshine dept",
                    "street": "Lame street",
                    "city": "Cardiff",
                    "state": "Gwent",
                    "postcode": "HP3 9AA",
                    "country": "England",
                    "country_code": "GB",
                    "raw": "Cottage Labs org, Moonshine dept, Lame street, Cardiff, Gwent, HP3 9AA, England, ISNI: isni 1111 2222 3333, ROR: ror-123"
                },
                {
                    "identifier": [{"type": "ROR", "id": "ror-456"}],
                    "org": "Another org",
                    "street": "Another street",
                    "city": "Another City",
                    "postcode": "CC1 2AA",
                    "country": "England",
                    "country_code": "GB",
                    "raw": "Another org, Another street, Another city, CC1 2AA, England, ROR: ror-456"
                }
            ]
        }, {
            "type": "author",
            "name": {
                "firstname": "Dave",
                "surname": "Spiegel",
                "fullname": "Dave Spiegel",
                "suffix": "Suff"
            },
            "organisation_name": "Auth org name",
            "identifier": [{
                "type": "orcid",
                "id": "editor's orcid"
            }, {
                "type": "email",
                "id": "editor's email address"
            }
            ],
            "affiliations": [{"raw": "University of Life"}]
        }
        ],
        "contributor": [{
            "type": "editor",
            "name": {
                "firstname": "Pepe",
                "surname": "Smith",
                "fullname": "Pepe Smith",
                "suffix": "contrib-suffix"
            },
            "organisation_name": "Contrib org name",
            "identifier": [{
                "type": "orcid",
                "id": "1002-48612-25020"
            }, {
                "type": "email",
                "id": "editor@email.com"
            }
            ],
            "affiliations": [{"raw": "University of Bristol"}]
        }],
        "accepted_date": "2014-09-01",
        "publication_date": {
            "publication_format": "electronic",
            "date": "2015-01-01",
            "year": "2015",
            "month": "01",
            "day": "01",
            "season": "Winter"
        },
        "history_date": [{
            "date_type": "submitted",
            "date": "2014-07-03"
        }],
        "publication_status": "Published",
        "funding": [
            {
                "name": "Rotary Club of Eureka",
                "identifier": [
                    {"type": "ringgold", "id": " rot-club-eurek "},
                    {"type": "doi", "id": "  http://dx.doi.org/10.13039/100008650 "},
                    {"type": "isni", "id": "  asdf-ghtk "}
                ],
                "grant_numbers": [" BB 34 juwef"]
            },
            {
                "name": "EPSRC",
                "identifier": [
                    {"type": "ringgold", "id": " askjdhfasdf "}
                ],
                "grant_numbers": [" EP/34/juwef ", "EP/99/arkle"]
            }
        ],
        "embargo": {
            "end": "2016-01-01",
            "start": "2015-01-01",
            "duration": "12"
        },
        "license_ref": [{
            "title": "name of licence",
            "type": "type",
            "url": "https://creativecommons.org/licenses/by/4.0/",
            "version": "version",
            "start": "2016-01-01"
        }
        ],
        "peer_reviewed": True,
        "ack": "Some acknowledgement text"
    }
}

# Example incoming notification with multiple validation failures
BAD_INCOMING = {
    "vers": "4",
    "category": 'A',
    "has_pdf": True,
    "event": "bad_event",
    "provider": {
        "agent": "pub/0.1",
        "ref": "asdfasdf"
    },
    "links": [
        {
            "type": "fulltext",
            "format": "application/pdf",
            "url": "https://test/url/test-article.pdf"
        },
        {
            "type": "fulltext",
            "format": "application/pdf",
        },

    ],
    "metadata": {
        "journal": {
            # "title": "Journal of Important Things",
            "abbrev_title": "Abbreviated Alternative Article",
            # "volume": "Volume-num",
            "issue": "Issue-num",
            "publisher": ["Journal of Important Things"],
            "identifier": [
                {"type": "other"}
            ]
        },
        "article": {
            "title": "",
            "subtitle": ["Alternative Article SUBtitle"],
            "type": "paper",
            "version": "",
            "start_page": "",
            "end_page": "End-pg",
            "page_range": "Page-range",
            "num_pages": "Total-pages",
            "language": ["eng"],
            "abstract": "Abstract of the work ",
            "identifier": [
                {"type": "doi", "id": "10.pp/jit.1"},
                {"type": "doi", "id": "Oops-second-DOI"},
                {"type": "url", "id": "http://jit.com/1"},
                {"type": "bad", "id": ""}
            ],
            "subject": ["arts", "medicine", "literature", ""]
        },
        "author": [{
            "type": "BAD",
            "name": {
                "firstname": "Richard",
                "surname": "Jones",
                "fullname": "Richard Jones",
                "suffix": "Sr.",
                "oops-name": "Urrgh"
            },
            "organisation_name": "",
            "identifier": [
                {"type": "orcid", "id": "0000-0002-4797-908X"},
                {"type": "email", "id": "richard@example.com  "},
                {"oops-id": "Urghh"}
            ],
            "affiliations": [{"raw": "Cottage Labs, HP3 9AA  "}]
        }, {
            "type": "corresp",
            "name": {
                "firstname": "Dave",
                "surname": "",
                "fullname": "Dave",
                "suffix": ""
            },
            "organisation_name": "",
            "identifier": [{
                "type": "orcid",
                "id": "editor's orcid"
            }, {
                "type": "email",
                "id": "editor's email address"
            }, {
                "type": "another"
            }
            ],
            "affiliations": []
        }, {
            "type": "author",
            "name": {
                "surname": "Maximillian",
                "suffix": ""
            },
            "organisation_name": "",
            "identifier": [{
                "type": "oops",
                "id": ""
            }, {
                "id": "editor's email address"
            }
            ],
        }],
        "contributor": [{
            "type": "editor",
            "name": {
                "firstname": "Pepe",
                "surname": "Smith",
                "fullname": "Pepe Smith",
                "suffix": ""
            },
            "identifier": [{
                "type": "orcid",
                "id": "1002-48612-25020"
            }, {
                "type": "email",
                "id": "editor@email.com"
            }
            ],
            "affiliations": [{"raw": "University of Bristol"}]
        },
        {
            "type": "",
            "name": {
                "firstname": "Pepe",
                "surname": "",
                "fullname": "Pepe Smith",
                "suffix": ""
            },
            "organisation_name": "Some org",
            "affiliations": []
        }],
        "accepted_date": "01-09-2014",
        "publication_date": {
            "publication_format": "BAD",
            "date": "2015-01-01",
            "year": "2014",
            "month": "",
            "day": "01"
            # , "season": ""
        },
        "history_date": [{
            "date_type": "submitted",
            "date": "2014-07-03"
        }
        ],
        "publication_status": "Published",
        "funding": [
            {
                "name": "Rotary Club of Eureka",
                "identifier": [
                    {"type": "ringgold", "id": " rot-club-eurek "},
                    {"type": "doi", "id": "  http://dx.doi.org/10.13039/100008650 "},
                    {"type": "isni", "id": "  asdf-ghtk "}
                ],
                "grant_numbers": [" BB 34 juwef"]
            },
            {
                # "name": "EPSRC",
                "identifier": [
                    {"type": "ringgold", "id": " askjdhfasdf "}
                ],
                "grant_numbers": [" EP/34/juwef "]
            }
        ],
        "embargo": {
            "end": "2016-01-01",
            "start": "2015-01-01",
            "duration": "12"
        },
        "license_ref": [{
            "title": "name of licence",
            "type": "type",
            "url": "https://creativecommons.org/licenses/by/4.0/",
            "version": "version",
        },
        {
            "title": "name of licence",
            "type": "type",
            "url": "url",
            "version": "version",
            "start": "01-01-2015",
        },
        {
            "title": "lic-title",
            "version": "lic-version",
            "type": "type"
        }
        ]
    }
}
