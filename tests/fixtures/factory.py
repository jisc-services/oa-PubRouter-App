"""
Fixtures for testing:
 - accounts (organisation & user)
 - notifications
"""
from copy import deepcopy
from uuid import uuid4
from werkzeug.security import generate_password_hash
from router.shared.models.account import AccOrg, AccUser, AccRepoMatchParams
from router.shared.models.sword_out import SwordDepositRecord,  DEPOSITED, FAILED   # values imported in tests

DEFAULT_PWD = "aPassw0rd"
HASH_PWD = generate_password_hash(DEFAULT_PWD)
LIVE_DEL_DATE = "2023-06-22T16:13:54Z"

# Has admin key for integration tests.
PUBLISHER_ACCOUNT = {
    "note": "",
    "api_key": "fake_publisher_test",
    "updated": "2017-06-22T16:13:54Z",
    "role": "P",
    "status": 0,
    "contact_email": "live_fake@test_pub.com",
    "publisher_data": {
        "embargo": [{"type": "", "duration": "12"}],
        "license": [
            {
                "type": "default",
                "title": "Sage Default Licence",
                "version": "beta 0.1",
                "url": "https://default.sagepub.com/default"
            }
        ],
        "peer_reviewed": True,
        "reports": {
            "format": "C",
            "emails": ["report-recipient@apublisher.com", "another@publisher.com"]
        }
    },
    # "created": "2016-05-25T11:17:29Z"
}

REPO_ACCOUNT = {
    "note": "",
    # "api_key": "bfde0060-6892-4bd4-8917-2a233bca6353",
    "api_key": "49d3df32-67d5-4c8c-98e3-789a083e1e574",
    "updated": "2017-06-22T16:13:54Z",
    "role": "R",
    "status": 1,
    "repository_data": {
        "sword": {
            "username": "sword",
            "password": "pass1",
            "collection": "http://sword/1"
        },
        "repository_info": {
            "url": "http://someurl.com",
            "xml_format": "dspace",
            "software": "dspace",
            "packaging": "http://purl.org/net/sword/package/SimpleZip"
        },
        "max_pub_age": 999,
        "duplicates": {
            "level_h": 5,     # Harvested Duplicates with some discernible difference
            "level_p": 6,   # Publisher Duplicates with some discernible difference or a PDF
            "emails": [],
            "meta_format": "xml"
        }
    },
    # "created": "2016-05-25T11:17:29Z"
}

ADMIN_ACCOUNT = {
    "note": "",
    "api_key": "bfde0060-6892-4bd4-8917-2a233bca6353",
    "updated": "2017-06-22T16:13:54Z",
    "role": "A",
    # "created": "2016-05-25T11:17:29Z"
}

REPO_CONFIG = {
    "name_variants": [".*"],
    "domains": [".*"]
}

# Commented out values are set by the `_make_user_account` function, other values may be overridden
USER_ACCOUNT = {
    # "id": 0,
    # "created": "2016-05-25T11:17:29Z",
    "last_success": None,
    "last_failed": None,
    # "uuid": None,
    # "acc_id": None,
    # "username": None,
    "user_email": "contact@test.com",
    # "surname": None,
    "forename": "Test",
    "org_role": "Top dog",
    # "role_code": None,
    "password": HASH_PWD,
    "failed_login_count": 0,
    "direct_login": True
}

API_USER_ACCOUNT = {
    "id": 0,
    "created": "2016-11-14T00:00:00Z",
    "last_success": None,
    "last_failed": None,
    "uuid": None,
    "acc_id": None,
    "username": "API-Key-user",
    "user_email": None,
    "surname": "API User",
    "forename": "The",
    "org_role": None,
    "role_code": "K",
    "password": None,
    "failed_login_count": 0
}

class AccountFactory:

    @classmethod
    def _make_org_account(cls, org_dict, prefix, live_or_del=None, save=True):
        org_data = deepcopy(org_dict)
        # Make Live
        if live_or_del is True:
            org_data["live_date"] = LIVE_DEL_DATE
        # Make Deleted
        elif live_or_del is False:
            org_data["deleted_date"] = LIVE_DEL_DATE
        org_name = f"{prefix}_Org_{str(uuid4())[:8]}"
        org_data["org_name"] = org_name
        org_acc = AccOrg(org_data)
        if save:
            org_acc.insert()
        return org_acc

    @staticmethod
    def _make_user_account(org_acc, username, surname, role_code, is_deleted=False, password=None):
        user_data = deepcopy(USER_ACCOUNT)
        user_data["acc_id"] = org_acc.id
        user_data["username"] = username
        user_data["surname"] = surname
        user_data["role_code"] = role_code
        # Make Deleted
        if is_deleted:
            user_data["deleted"] = LIVE_DEL_DATE
        user_acc = AccUser(user_data)
        if password:
            user_acc.set_password(password)
        user_acc.insert()   # THis will set the account created, ID & UUID values
        user_acc.acc_org = org_acc
        return user_acc

    @staticmethod
    def _make_api_account(org_acc):
        """
        Make an API user account - NB. NO database record is created for API users.
        @param org_acc:
        @return:
        """
        user_data = deepcopy(API_USER_ACCOUNT)
        user_data["acc_id"] = org_acc.id
        user_data["uuid"] = org_acc.uuid
        user_acc = AccUser(user_data)
        user_acc.acc_org = org_acc
        return user_acc

    @classmethod
    def _make_all_user_ac_types(cls, org_acc, password=None):
        # API-key user account (DON'T create database record for API-key user)
        api_user = cls._make_api_account(org_acc)

        # Admin user account
        admin_user = cls._make_user_account(org_acc, f"admin_{org_acc.uuid[:12]}", "Admin User", "A", password=password)

        # Standard user account
        std_user = cls._make_user_account(org_acc, f"std_{org_acc.uuid[:12]}", "Standard User", "S", password=password)

        # Read-only user account
        ro_user = cls._make_user_account(org_acc, f"ro_{org_acc.uuid[:12]}", "ReadOnly User", "R", password=password)

        return org_acc, admin_user, api_user, std_user, ro_user

    @classmethod
    def deleted_account(cls, org_only=True):
        org_acc = cls._make_org_account(REPO_ACCOUNT, "deleted", live_or_del=False)
        if org_only:
            return org_acc
        else:
            return cls._make_all_user_ac_types(org_acc)

    @classmethod
    def admin_account(cls, org_only=True):
        org_acc =  cls._make_org_account(ADMIN_ACCOUNT, "admin")
        if org_only:
            return org_acc
        else:
            return cls._make_all_user_ac_types(org_acc)

    @classmethod
    def repo_account(cls,
                     live=True,
                     org_name=None,
                     sword_dict=None,
                     sword_username_pwd_collection_list=None,
                     repo_status=None,
                     repo_xml_format=None,
                     matching_config=None,
                     duplicates_dict=None,
                     password=None,
                     save=True,
                     org_only=True):
        if live:
            org_acc = cls._make_org_account(REPO_ACCOUNT, "live", live_or_del=True, save=False)
        else:
            org_acc = cls._make_org_account(REPO_ACCOUNT, "test", save=False)
        if org_name is not None:
            org_acc.org_name = org_name
        if sword_dict or sword_username_pwd_collection_list or repo_status or duplicates_dict or repo_xml_format:
            repo_data = org_acc.repository_data
            if sword_dict:
                repo_data.sword_data = sword_dict
            if sword_username_pwd_collection_list:
                repo_data.add_sword_credentials(*sword_username_pwd_collection_list)
            if repo_status:
                repo_data.status = repo_status
            if duplicates_dict:
                if duplicates_dict.get("level_h") is not None:
                    repo_data.dups_level_harv = duplicates_dict["level_h"]
                if duplicates_dict.get("level_p") is not None:
                    repo_data.dups_level_pub = duplicates_dict["level_p"]
                if duplicates_dict.get("emails"):
                    repo_data.dups_emails = duplicates_dict["emails"]
                if duplicates_dict.get("meta_format"):
                    repo_data.dups_meta_format = duplicates_dict["meta_format"]
            if repo_xml_format:
                repo_data.repository_xml_format = repo_xml_format
        if save or matching_config:
            org_acc.insert()

        if matching_config:
            if matching_config is True:
                matching_config = REPO_CONFIG
            match_params = AccRepoMatchParams({"id": org_acc.id, "matching_config": matching_config})
            match_params.insert()

        if org_only:
            return org_acc
        else:
            return cls._make_all_user_ac_types(org_acc, password=password)

    @classmethod
    def publisher_account(cls, live=True, password=None, org_only=True):
        if live:
            org_acc = cls._make_org_account(PUBLISHER_ACCOUNT, "live_pub", live_or_del=True)
        else:
            org_acc =  cls._make_org_account(PUBLISHER_ACCOUNT, "test_pub")
        if org_only:
            return org_acc
        else:
            return cls._make_all_user_ac_types(org_acc, password=password)

    @classmethod
    def add_config(cls, acc, matching_config=None):
        acc.repository_data.max_pub_age = 100
        acc.update()

        if matching_config is None:
            matching_config = deepcopy(REPO_CONFIG)
        match_params = AccRepoMatchParams({"id": acc.id, "matching_config": matching_config})
        match_params.insert()

    @classmethod
    def create_all_account_types(cls, org_only=True):
        # Return number of Org Acs & number of user Acs created in database
        cls.deleted_account(org_only=org_only)
        cls.admin_account(org_only=org_only)
        cls.repo_account(live=True, org_only=org_only)
        cls.publisher_account(live=True, org_only=org_only)
        cls.publisher_account(live=False, org_only=org_only)
        cls.repo_account(live=False, org_only=org_only)
        # Number of Org accounts, Number of user Acs created in database (3 per Organisation: Admin, ReadOnly, Standard)
        # Note that API user accounts are never persisted in database.
        return 6, 0 if org_only else 18


class AccRepoMatchingParamsFactory:
    pass

class NotificationFactory:
    """
    Class which provides access to the various fixtures used for testing the notifications
    """

    @classmethod
    def unrouted_notification(cls, no_id_or_created=False, note_vers=None, provider_rank=1):
        """
        A basic unrouted notification

        :param no_id_or_created: Boolean - True: Remove "id" and "created" elements;
                                            False: Leave "id" & "created" as defined in BASE_NOTIFICATION_V3
        :param note_vers: String - value of notification version (default above should be set to current API_VERSION config value)
        :param provider_rank: Integer - 1: Publisher provider; 2: Harvester provider; 3: Harvester provider
        :return: notification (V3 or V4)
        """
        base = deepcopy(BASE_NOTIFICATION_V4)
        # If rank is for a Harvested notification
        if provider_rank > 1:
            base["provider"] = PROVIDER_HARV.copy()
            base["provider"]["rank"] = provider_rank
        # For V3 notifications need to modify author & contributor affiliations and remove new fields
        if note_vers == "3":
            base["vers"] = "3"
            md = base["metadata"]
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

        if no_id_or_created:
            del base["id"]
            del base["created"]
        else:
            base["type"] = "U"  # Unrouted notification

        return base

    @classmethod
    def routed_notification(cls, no_id_or_created=False, note_vers=None):
        """
        A routed notification

        :param no_id_or_created: Boolean - True: Remove "id" and "created" elements;
                                            False: Leave "id" & "created" as defined in BASE_NOTIFICATION_V3
        :param note_vers: String - value of notification version (default above should be set to current API_VERSION config value)
        :return: notification dict
        """
        base = cls.unrouted_notification(no_id_or_created=no_id_or_created, note_vers=note_vers)
        if not no_id_or_created:
            base["type"] = "R"  # Routed notification
        base["links"] += deepcopy(ROUTED_LINKS)
        base.update(deepcopy(ROUTING_INFO))
        return base

    @classmethod
    def routing_metadata(cls, required_field=None):
        """
        Routing metadata

        :return: routing metadata dict
        """
        if required_field:
            rout_metadata = deepcopy(BAD_ROUTING_METADATA)
            if required_field == "domain":
                rout_metadata["emails"] = ["email@ucl.ac.uk"]
            else:
                rout_metadata[required_field] = GOOD_ROUTING_METADATA[required_field]
        else:
            rout_metadata = deepcopy(GOOD_ROUTING_METADATA)
        return rout_metadata

    @classmethod
    def notification_metadata(cls, note_vers=None):
        """
        Notification metadata

        :param note_vers: String - value of notification version (default above should be set to current API_VERSION config value)
        :return: notification metadata dict
        """
        base = deepcopy(ALT_METADATA_V4)
        # For V3 notifications need to modify author & contributor affiliations and remove new fields
        if note_vers == "3":
            md = base["metadata"]
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
        return base

# The matching routing metadata fields (each field matches the relevant repository configuration)
GOOD_ROUTING_METADATA = {
    "emails": ["goodemail@gmail.com"],
    "affiliations": ["Cottage Labs", "Edinburgh Univerisity", "UCL", "with embedded url http://www.ed.ac.uk like that"],
    "orcids": ["0000-0002-0136-3706"],
    "postcodes": ["SW1 0AA", "EH23 5TZ"],
    "grants": ["BB/34/juwef"],
    "org_ids": ["ROR:ror-1234", "ISNI:isni111122223333"]
}

# These metadata fields will all fail to match the repository configuration
BAD_ROUTING_METADATA = {
    "emails": ["bademail.com"],
    "affiliations": ["badaff"],
    "orcids": ["badid"],
    "postcodes": ["badpostcode"],
    "grants": ["badgrant"],
    "org_ids": ["badorg_id"]
}

# A link object that can be grafted in to notifications
ROUTED_LINKS = [{
        "type": "package",
        "format": "application/zip",
        "cloc": "",
        "access": "router",
        "packaging": "https://pubrouter.jisc.ac.uk/FilesAndJATS"
    }, {
        "type": "package",
        "format": "application/zip",
        "access": "router",
        "cloc": "ArticleFilesJATS.zip",
        "packaging": "http://purl.org/net/sword/package/SimpleZip"
    }, {
        "type": "unpackaged",
        "format": "application/zip",
        "access": "special",
        "packaging": "http://purl.org/net/sword/package/SimpleZip",
        "cloc": "eprints-rioxx/non-pdf-files.zip"
    }, {
        "type": "unpackaged",
        "format": "application/pdf",
        "access": "special",
        "cloc": "eprints-rioxx/article-1.pdf"
    }
]

# The routing info that can be grafted into a notification to make it routed
ROUTING_INFO = {
    "analysis_date": "2015-02-02T00:00:00Z",
    "repositories": [1, 2, 3]
}

# Publisher provider
PROVIDER_PUB = {
    "id": 9,
    "route": "ftp",
    "agent": "pub-name/0.1",
    "rank": 1
}
# Harvester provider
PROVIDER_HARV = {
    "agent": "Harvester",
    "harv_id": 6,
    "rank": 3,
    "route": "harv"
}

# Example metadata section of a notification
ALT_METADATA_V4 = {
    "metadata": {
        "journal": {
            "title": "Journal of Important Things",
            "abbrev_title": "Abbreviated Alternative Article",
            "volume": "Volume-num",
            "issue": "Issue-num",
            "publisher": ["Journal of Important Things"],
            "identifier": [
                {"type": "other", "id": "over there"},
                {"type": "issn", "id": "1234-5678"},
                {"type": "eissn", "id": "1234-5678"},
            ]
        },
        "article": {
            "title": "Alternative Article",
            "subtitle": ["Alternative Article Subtitle"],
            "type": "paper",
            "version": "AAM",
            "start_page": "Start-pg",
            "end_page": "End-pg",
            "page_range": "Page-range",
            "num_pages": "Total-pages",
            "e_num": "e-Location",
            "language": ["eng"],
            "abstract": "Abstract of the work",
            "identifier": [
                {"type": "doi", "id": "55.aa/base.1"},
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
                "suffix": "AltMeta"
            },
            "organisation_name": "Alt Metadata Org",
            "identifier": [
                {"type": "orcid", "id": "0000-0002-0136-3706"},
                {"type": "email", "id": "alt_meta@alt_meta.com"}
            ],
            "affiliations": [{"raw": "Alt Metadata Affiliation"}]
        }, {
            "type": "author",
            "name": {
                "firstname": "Dave",
                "surname": "Spiegel",
                "fullname": "Dave Spiegel",
                "suffix": ""
            },
            "organisation_name": "",
            "identifier": [{
                "type": "orcid",
                "id": "authors's orcid"
            }, {
                "type": "email",
                "id": "author's email address"
            }],
            "affiliations": [{"raw": "University of Life"}]
        }],
        "contributor": [{
            "type": "editor",
            "name": {
                "firstname": "Pepe",
                "surname": "Smith",
                "fullname": "Pepe Smith",
                "suffix": ""
            },
            "organisation_name": "",
            "identifier": [{
                "type": "orcid",
                "id": "1002-48612-25020"
            }, {
                "type": "email",
                "id": "editor@email.com"
            }],
            "affiliations": [{"raw": "University of Bristol"}]
        }],
        "accepted_date": "2014-09-01",
        "publication_date": {
            "publication_format": "electronic",
            "date": "2015-01-01",
            "year": "2015",
            "month": "01",
            "day": "01"
            # ,"season": ""
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
                    {"type": "ringgold", "id": "rot-club-eurek"},
                    {"type": "doi", "id": "http://dx.doi.org/10.13039/100008650"},
                    {"type": "isni", "id": "asdf-ghtk"}
                ],
                "grant_numbers": ["BB/34/juwef"]
            },
            {
                "name": "EPSRC",
                "identifier": [
                    {"type": "ringgold", "id": "askjdhfasdf"}
                ],
                "grant_numbers": ["EP/34/juwef"]
            }
        ],
        "embargo": {
            "start": "2016-04-01",
            "end": "2022-04-01",
            "duration": "72"
        },
        "license_ref": [{
            "title": "name of licence",
            "type": "type",
            "url": "url",
            "version": "version",
            "start": "2016-01-01"
        },{
            "title": "Open licence",
            "type": "ccby",
            "url": "https://creativecommons.org/licenses/by/4.0/",
            "version": "1",
            "start": "2023-04-01"
        }],
        "peer_reviewed": True,
        "ack": "Some acknowledgement text"
    }
}

# Example base notification which can be extended for other uses
BASE_NOTIFICATION_V4 = {
    "vers": "4",
    "id": 123,
    "created": "2016-11-14T00:00:00Z",
    "category": "A",
    "has_pdf": True,
    "event": "publication",
    "provider": PROVIDER_PUB.copy(),
    "content": {
        "packaging_format": "https://pubrouter.jisc.ac.uk/FilesAndJATS"
    },
    "links": [
        {
            "type": "splash",
            "format": "text/html",
            "access": "public",
            "url": "http://example.com/article/1"
        },
        {
            "type": "fulltext",
            "format": "application/pdf",
            "access": "public",
            "url": "http://example.com/article/1/pdf"
        }
    ],
    "metadata": {
        "journal": {
            "title": "Journal of Important Things",
            "abbrev_title": "Abbreviated version of journal  title",
            "volume": "Volume-num",
            "issue": "Issue-num",
            "publisher": ["Premier Publisher"],
            "identifier": [
                {"type": "issn", "id": "1234-5678"},
                {"type": "eissn", "id": "1234-5678"},
                {"type": "pissn", "id": "9876-5432"},
                {"type": "doi", "id": "10.pp/jit"}
            ]
        },
        "article": {
            "title": "Test Article",
            "subtitle": ["Test Article Subtitle"],
            "type": "article",
            "version": "AM",
            "start_page": "Start-pg",
            "end_page": "End-pg",
            "page_range": "Page-range",
            "num_pages": "Total-pages",
            "e_num": "e-Location",
            "language": ["eng"],
            "abstract": "Abstract of the work",
            "identifier": [
                {"type": "doi", "id": "55.aa/base.1"},
                {"type": "test", "id": "test-id"}
            ],
            "subject": ["science", "technology", "arts", "medicine"]
        },
        "author": [{
            "type": "corresp",
            "name": {
                "firstname": "Richard",
                "surname": "Jones",
                "fullname": "Richard Jones",
                "suffix": "Sr."
            },
            "organisation_name": "",
            "identifier": [{"type": "orcid", "id": "0000-0002-0136-3706"},
                           {"type": "email", "id": "richard@example.com"}],
            "affiliations": [{
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
            }]
        }, {
            "type": "author",
            "name": {
                "firstname": "Mark",
                "surname": "MacGillivray",
                "fullname": "Mark MacGillivray",
                "suffix": ""
            },
            "organisation_name": "",
            "identifier": [{"type": "orcid", "id": "0000-0002-4797-908X"},
                           {"type": "email", "id": "mark@example.com"}],
            "affiliations": [{"raw": "Cottage Labs, EH9 5TP"}]
        }],
        "contributor": [{
            "type": "editor",
            "name": {
                "firstname": "Manolo",
                "surname": "Williams",
                "fullname": "Manolo Williams",
                "suffix": ""
            },
            "organisation_name": "",
            "identifier": [{"type": "email", "id": "manolo@example.com"}],
            "affiliations": [{"raw": "Lalala Labs, BS1 8HD"}]
        }],
        "accepted_date": "2014-09-01",
        "publication_date": {
            "publication_format": "",
            "date": "2015-01-01"
            # ,"season": ""
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
                    {"type": "ringgold", "id": "rot-club-eurek"},
                    {"type": "doi", "id": "http://dx.doi.org/10.13039/100008650"}
                ],
                "grant_numbers": ["BB/34/juwef"]
            },
            {
                "name": "Wellcome Trust - doi, fundref, ror - all with no domain",
                "identifier": [
                    {"type": "doi", "id": "10.13039/100010269"},
                    {"type": "FundRef", "id": "100010269"},
                    {"type": "ror", "id": "029chgv08"},
                ],
                "grant_numbers": ["wellcome-grant"]
            }
        ],
        "embargo": {
            "start": "2016-04-01",
            "duration": "72"
        },
        "license_ref": [{
            "title": "Open licence",
            "type": "ccby",
            "url": "https://creativecommons.org/licenses/by/4.0/",
            "version": "1",
            "start": "2023-04-01"
        },{
            "title": "Embargo licence",
            "type": "embargo",
            "url": "http://url",
            "version": "1",
            "start": "2016-04-01"
        },{
            "title": "Open licence",
            "type": "ccbync",
            "url": "https://creativecommons.org/licenses/by-nc/4.0/",
            "version": "1",
            "start": "2022-04-01"
        }],
        "peer_reviewed": True,
        "ack": "Some acknowledgement text"
    }
}



class SwordFactory:
    """
    Class which provides access to the various fixtures used for testing the sword features
    """

    @classmethod
    def deposit_record(cls):
        """
        Example deposit record

        :return:
        """
        return deepcopy(DEPOSIT_RECORD)


    @classmethod
    def create_deposit_rec(cls, repo_id=1, note_id=1, metadata_status=None, content_status=None, completed_status=None, err_msg=None):
        data = {
            "id": None,
            "deposit_date": None,
            "repo_id": repo_id,
            "note_id": note_id,
            "metadata_status": metadata_status,
            "content_status": content_status,
            "completed_status": completed_status,
            "error_message": err_msg,
            "doi": "10.1136/test-doi-1234",
            "edit_iri": "http://pretend_repo.ac.uk/some/url/6789"
        }
        # Reload ensures that date set by database insert is returned in object
        return SwordDepositRecord(data).insert(reload=True)



DEPOSIT_RECORD = {
    "id" : 1,
    "deposit_date" : "1972-01-01T00:00:00Z",
    "repo_id" : 2,
    "note_id" : 123,
    "metadata_status" : DEPOSITED,
    "content_status" : None,
    "completed_status" : None,
    "error_message": None,
    "doi": "A_DOI/doi/111",
    "edit_iri": "http://pretend_repo.ac.uk/some/url/6789"
}
