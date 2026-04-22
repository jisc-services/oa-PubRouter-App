"""
Fixtures for testing notifications
"""

import os
from builtins import range
from builtins import object
from copy import deepcopy
from octopus.lib import dates, paths
from router.shared.models.note import RoutedNotification

# Relative Path to test resources directory
RESOURCES = paths.rel2abs(__file__, "..", "resources")


# Example API error
LIST_ERROR = {
    "error": "request failed"
}

### Sample base notification ###
UNROUTED_NOTIFICATION = {
    "vers": "4",
    "id": 1234,
    "created": "2016-11-14T15:27:02Z",
    "event": "publication",
    "type": "U",
    "provider": {
        "id": 8,
        "agent": "Wiley Fox",
        "route": "ftp",
        "rank": 1
    },
    "content": {
        "packaging_format": "https://pubrouter.jisc.ac.uk/FilesAndJATS"
    },
    "links": [
        {
            "type": "splash",
            "access": "public",
            "format": "text/html",
            "url": "http://external_domain.com/some/url"
        },
        {
            "type": "fulltext",
            "access": "router",
            "format": "application/pdf",
            "cloc": "testfile.pdf"
        }
    ],
    "metadata": {
        "journal": {
            "title": "Journal of Important Things",
            "abbrev_title": "Abbreviated version of journal  title",
            "volume": "Volume-number",
            "issue": "Issue-number",
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
            "type": "research-article",
            "version": "AAM",
            "start_page": "Start-pg",
            "end_page": "End-pg",
            "page_range": "Page-range",
            "num_pages": "Total-pages",
            "e_num": "e-Location",
            "language": ["en"],
            "abstract": "Abstract of the work. Sed ut perspiciatis unde omnis iste natus error sit voluptatem accusantium doloremque laudantium, totam rem aperiam, eaque ipsa quae ab illo inventore veritatis et quasi architecto beatae vitae dicta sunt explicabo.",
            "identifier": [
                {"type": "doi",
                 "id": "55.aa/base.1"
                 },
                {
                    "id": "pub-15-51689",
                    "type": "publisher-id"
                }
            ],
            "subject": ["Science", "New Technology", "Medicine"]
        },
        "author": [
            {
                "type": "corresp",
                "name": {
                    "firstname": "Richard",
                    "surname": "Jones",
                    "fullname": "Richard Jones",
                    "suffix": ""
                },
                "organisation_name": "Grottage Labs",
                "identifier": [
                    {
                        "type": "orcid",
                        "id": "3333-0000-1111-2222"
                    }, {
                        "type": "email",
                        "id": "richard@example.com"
                    }
                ],
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
            },
            {
                "type": "author",
                "name": {
                    "firstname": "Mark",
                    "surname": "MacGillivray",
                    "fullname": "Mark MacGillivray"
                },
                "organisation_name": "",
                "identifier": [{
                    "type": "orcid",
                    "id": "1111-2222-3333-0000"
                }, {
                    "type": "email",
                    "id": "mark@example.com"
                }
                ],
                "affiliations": [{"raw": "Cottage Labs, EH9 5TP"}]
            },
            {
                "identifier": [
                    {
                        "id": "0000-0001-7744-0424",
                        "type": "orcid"
                    }
                ],
                "affiliations": [{"raw": "Department of Microbiology and Parasitology, Faculty of Medicine and Health Sciences, Universiti Putra Malaysia, Serdang, Selangor, Malaysia"}],
                "name": {
                    "firstname": "Kuan-Meng",
                    "surname": "Soo",
                    "fullname": "Soo, Kuan-Meng"
                },
                "type": "author"
            }, {
                "organisation_name": "Author organisation only (no name)",
                "affiliations": [{"raw": "Org name only"}],
                "type": "author"
            }
        ],
        "contributor": [{
            "type": "editor",
            "name": {
                "firstname": "Manolo",
                "surname": "Williams",
                "fullname": "Manolo Williams"
            },
            "organisation_name": "ACME Org Name",
            "identifier": [{
                "type": "email",
                "id": "manolo@example.com"
            }
            ],
            "affiliations": [{"raw": "Lalala Labs, BS1 8HD"}]
        }, {
            "type": "reviewer",
            "organisation_name": "Contributor organisation only",
            "identifier": [{
                "type": "email",
                "id": "contrib-org@example.com"
            }
            ],
            "affiliations": [{"raw": "Lalalalala Labs, BS1 8HD"}]
        }],
        "accepted_date": "2014-09-01",
        "publication_date": {
            "publication_format": "electronic",
            "date": "2015-01-05",
            "year": "2015",
            "month": "01",
            "day": "05",
            "season": ""
        },
        "history_date": [
            {
                "date": "2013-12-02",
                "date_type": "received"
            },
            {
                "date": "2014",
                "date_type": "collection"
            },
            {
                "date": "2014-03-01",
                "date_type": "accepted"
            },
            {
                "date": "2015-01-05",
                "date_type": "epub"
            }
        ],
        "publication_status": "Published",
        "funding": [
            {
                "identifier": [
                    {
                        "id": "http://dx.doi.org/10.13039/501100003093",
                        "type": "funder-id"
                    }
                ],
                "name": "Ministry of Higher Education, Malaysia",
                "grant_numbers": [
                    "LR001/2011A"
                ]
            },
            {
                "name": "Rotary Club of Eureka",
                "identifier": [
                    {"type": "ringgold", "id": "rot-club-eurek"},
                    {"type": "Fundref", "id": "10.13039/100008650"}
                ],
                "grant_numbers": ["BB/34/juwef", "BB/35/juwef"]
            }
        ],
        "embargo": {
            "start": "",
            "end": "2015-07-05",
            "duration": "180"
        },
        "license_ref": [
            {
                "start": "2015-07-05",
                "url": "https://creativecommons.org/licenses/by/4.0/",
                "title": "This is an open access article distributed in accordance with the Creative Commons Attribution 4.0 Unported (CC BY 4.0) license, which permits others to copy, redistribute, remix, transform and build upon this work for any purpose, provided the original work is properly cited, a link to the licence is given, and indication of whether changes were made. See: https://creativecommons.org/licenses/by/4.0/.",
                "type": "open-access",
                "version": "4.0"
            },
            {
                "title": "licence title",
                "type": "restricted",
                "url": "http://license-url",
                "version": "1",
                "start": "2022-01-02"
            }
        ],
        "peer_reviewed": True,
        "ack": "Some acknowledgement text"
    }
}

### Sample Routed notification ###
ROUTED = deepcopy(UNROUTED_NOTIFICATION)
ROUTED["analysis_date"] = "2020-03-13T17:57:19Z"
ROUTED["type"] = "R"
ROUTED["repositories"] = []
ROUTED["links"] += [
    {
        "type": "package",
        "access": "router",
        "format": "application/zip",
        "cloc": "ArticleFilesJATS.zip",
        "packaging": "http://purl.org/net/sword/package/SimpleZip"
    },
    {
        "type": "package",
        "access": "router",
        "format": "application/zip",
        "cloc": "",
        "packaging": "https://pubrouter.jisc.ac.uk/FilesAndJATS"
    }
]

DUPLICATES_DIFF = [{
    'old_date': "2020-01-10T12:40:10Z",
    'curr_bits': 68448944058,
    'old_bits': 25434193914,
    'n_auth': 0,
    'n_orcid': 0,
    'n_fund': 3,
    'n_fund_id': 1,
    'n_grant': 2,
    'n_lic': 1,
    'n_cont': 1,
    'n_hist': 1
}, {
    'old_date': "2020-03-13T17:57:19Z",
    'curr_bits': 68448944062,
    'old_bits': 67874250554,
    'n_auth': 0,
    'n_orcid': 5,
    'n_fund': 0,
    'n_fund_id': 2,
    'n_grant': 2,
    'n_lic': 0,
    'n_cont': 1,
    'n_hist': 1
}]


class NotificationFactory(object):
    """
    Class which provides access to the various fixtures used for testing the notifications
    """


    @classmethod
    def routed_note_obj_list(cls, num_recs, ids=None, analysis_dates=None, article_title=None):
        """
        :param num_recs: Int - number of records to create
        :param ids: List or Int - List of Id values or first Id value to assign to created records - If an Int is provided, then
                this will be incremented for each notification created, e.g. if ids=222, and num_recs=3 then Ids of
                created recs will be: 222, 223, 224,
        :param analysis_dates: List of analysis dates to apply to created records
        :param article_title: String - Title of article
        """
        note_list = []
        ids_list = isinstance(ids, list)
        for i in range(num_recs):
            note = RoutedNotification(ROUTED)
            if article_title:
                note.article_title = article_title + str(i)
            if ids is not None:
                note.id = ids[i] if ids_list else ids + i
            if analysis_dates is not None:
                note.analysis_date = analysis_dates[i]
            note_list.append(note)
        return note_list


    @classmethod
    def notification_list(cls, since=None, since_id=None, page=1, page_size=10, total_recs=1, ids=None, analysis_dates=None, article_title=None):
        """
        Example notification list

        :param since: since date for list
        :param since_id: since ID for list (returns all notifications having a larger ID value
        :param page: page number of list
        :param page_size: number of results in list
        :param total_recs: simulated total number of notifications retrieved
        :param ids: ids of notifications to be included
        :param analysis_dates: analysis dates of notifications; should be same length as ids, as they will be tied up
        :param article_title: The article title to give to the test notification
        :return:
        """
        outgoing_notification = RoutedNotification(ROUTED).make_outgoing().data
        note_list = []
        # If total recs is more than needed to fill current page, then num notifications on current page is the page size
        # Otherwise num notifications on current page is total records minus the num needed to fill all preceding pages
        num_notifications_on_current_page = page_size if page * page_size <= total_recs else total_recs - ((page - 1) * page_size)
        for i in range(num_notifications_on_current_page):
            note = deepcopy(outgoing_notification)
            if article_title:
                note["metadata"]["article"]["title"] = article_title + str(i)
            if ids is not None:
                note["id"] = ids[i]
            if analysis_dates is not None:
                note["analysis_date"] = analysis_dates[i]
            note_list.append(note)
        return {
            "since": since,
            "since_id": since_id,
            "page": page,
            "pageSize": page_size,
            "timestamp": dates.now_str(),
            "total": total_recs,
            "notifications": note_list
        }


    @classmethod
    def error_response(cls):
        """
        JPER API error response

        :return: error response
        """
        return deepcopy(LIST_ERROR)


    @classmethod
    def routed_notification(cls, acc_id, article_title=None, duplicates=False, no_links=False):
        """
        Routed notification

        :return: routed notification Obj (after saving)
        """
        new_routed = deepcopy(ROUTED)
        del new_routed["id"]
        del new_routed["metadata"]["history_date"]
        new_routed["repositories"].append(acc_id)
        new_routed["analysis_date"] = dates.now_str()
        if article_title:
            new_routed["metadata"]["article"]["title"] = article_title
        if duplicates:
            new_routed["dup_diffs"] = deepcopy(DUPLICATES_DIFF)
        if no_links:
            new_routed["links"] = []
        routed = RoutedNotification(new_routed)
        # routed.insert()
        routed.save_newly_routed()
        return routed


    @classmethod
    def outgoing_notification(cls, article_title=None, duplicates=False):
        """
        Example outgoing notification

        :param article_title: Title of test article
        :param duplicates: Boolean - whether to include DUPLICATES_DIFF in notification
        :return: OutgoingNotification object
        """
        note = RoutedNotification(ROUTED)
        if duplicates:
            note.dup_diffs = deepcopy(DUPLICATES_DIFF)
        if article_title:
            note.article_title = article_title
        # note.insert()
        outgoing = note.make_outgoing()
        return outgoing

    @classmethod
    def special_character_notification(cls, title_prefix=""):
        """
        Example special character notification

        :param title_prefix: Prefix to title of test article
        :return: Notification
        """
        special =  RoutedNotification(ROUTED)
        special.article_title = title_prefix + "Special character article [\u00a0](\u2062)"
        special.article_abstract = special.article_abstract + " Special char [\u00a0](\u2062)"
        return special

    @classmethod
    def example_package_path(cls):
        """
        Path to binary file which can be used for testing

        :return:
        """
        return os.path.join(RESOURCES, "example.zip")

class MockNoteScroller:
    def __init__(self, num_notes=None, note_ids=None, exc_to_raise=None, raise_exc_after=None, stop_after=None):
        self._note_list = [] if num_notes is None else NotificationFactory.routed_note_obj_list(num_notes, ids=note_ids)
        self._exc_to_raise = exc_to_raise
        self._raise_exc_after = raise_exc_after
        self._stop_after = stop_after

    def create_mock_note_scroller_obj(self):
        _note_list = self._note_list
        _exc_to_raise = self._exc_to_raise
        _raise_exc_after = self._raise_exc_after
        _stop_after = self._stop_after

        def mock_scroller_obj(*args, **kwargs):
            class X:
                def __init__(self, *args, **kwargs):
                    self.popped = 0
                    self.note_list = []

                def __enter__(self):
                    self.note_list = _note_list

                def __iter__(self):
                    return self

                def __next__(self):
                    if _exc_to_raise:
                        if _raise_exc_after is None or self.popped == _raise_exc_after:
                            raise _exc_to_raise

                    if not self.note_list or (_stop_after and self.popped >= _stop_after):
                        raise StopIteration
                    self.popped += 1
                    return self.note_list.pop(0)

                def __exit__(self, exc_type, exc_val, exc_tb):
                    self.close_or_purge_scrl()

                def close_or_purge_scrl(self, close=False):
                    self.note_list = []
                    self.popped = 0

            return X(*args, **kwargs)

        return mock_scroller_obj


