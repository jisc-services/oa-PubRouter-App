"""
#    Library:
#
#    Model objects used to represent Notification objects
"""
import re
# from operator import itemgetter
from copy import deepcopy
from datetime import datetime, timezone
from dateutil.relativedelta import relativedelta
from flask import current_app
from octopus.lib import dataobj, dates
from octopus.lib.data import strip_tags_adjust_whitespace
from octopus.modules.identifiers import postcode
from router.shared.mysql_dao import UnroutedNotificationDAO, RoutedNotificationDAO, NotificationAccountDAO,\
    NotificationDAO, HarvestedUnroutedNotificationDAO, CONN_CLOSE, PURGE, DAOException

# Global variables
YYYY_MM_DD = "%Y-%m-%d"  # YYYY-MM-DD
TO_UNICODE = dataobj.to_unicode  # Convert to Unicode coerce function
TO_INT = dataobj.to_int
TO_YYYY_MM_DD = dataobj.date_str(out_format=YYYY_MM_DD)  # Convert to YYYY-MM-DD coerce function
match_emails_regex = re.compile(r"\b[^@\s]+@[-_a-z0-9]+\.[-_a-z0-9.]+\b", re.IGNORECASE)
match_multispace = re.compile(r'\s+')   # Match one or more white space characters
# Match 'Abstract' at start of string followed by optional colon/space(s)
match_abstract_title = re.compile(r"^abstract\b[:.,]? *", re.IGNORECASE)
# Match 'Acknowledg(e)ment(s)' at start of string followed by optional colon/space(s)
match_ack_title = re.compile(r"^acknowledge?ments?\b[:.,]? *", re.IGNORECASE)
# Regex test to check if a url (string) contains a filename suffix '.pdf' or sequence '?pdf'
best_pdf_url = re.compile(r'[.?]pdf\b')

# scroll_num values: help ensure that Scrollers use unique connections (though uniqueness is conferred by scroll_name
# which is a composite of scroll_num, pull_name and other attributes).
# IMPORTANT check entire code base for other similar declarations before adding new ones (or changing these numbers) to
# avoid overlaps - do global search for "_SCROLL_NUM ="
ROUTED_SCROLL_NUM = 1
DEPOSIT_SCROLL_NUM = 2
UNROUTED_SCROLL_NUM = 3
PUB_DOI_SCROLL_NUM = 4
ROUTED_ALL_SCROLL_NUM = 5   # Used in jper.reports
ROUTED_DAY_SCROLL_NUM = 6   # Used in models.reports

class EnhancementException(Exception):
    pass


def coerce_to_ymd(date_string):
    """

    If date_string is not in either %Y, %Y-%m or %Y-%m-%d format, coerce to %Y-%m-%d,
        otherwise keep current date_string.

    :param date_string: date string we will attempt to format

    :return: Date string in %Y-%m-%d format if not adhering to the requirements above,
        otherwise TO_UNICODE of the original date_string

    """
    # Arranged in order most likely to match the passed date string
    good_formats = ["%Y-%m-%d", "%Y-%m", "%Y"]
    for format_ in good_formats:
        try:
            datetime.strptime(date_string, format_)
            return date_string      # Return date string that converted without an exception
        except:
            pass
    return TO_YYYY_MM_DD(date_string)


def normalise_article_version(ver):
    """
    Given an article version, it returns a normalised article version value.
    For use in various crosswalks.

    :param ver: string, the article version we wish to normalise
    :return: string, the normalised version of the input article version, or None if we fail to make a mapping.
    """

    # Article version mappings (keys in uppercase, as we force version to upper before checking dict)
    article_version_mapping = {
        'AO': 'AO',  # Author's Original
        'SMUR': 'SMUR',  # Submitted Manuscript Under Review
        'AM': 'AM',  # Accepted Manuscript
        'AAM': 'AM',  # - ditto -
        'P': 'P',  # Proof
        'VOR': 'VoR',  # Version of Record
        'CVOR': 'CVoR',  # Corrected Version of Record
        'EVOR': 'EVoR',  # Enhanced Version of Record
        'C/EVOR': 'C/EVoR',  # Corrected or Enhanced VoR
        'NA': 'NA'  # Not Applicable
    }
    # Return mapping if valid or default to None, upon unsuccessful mapping or None input
    if ver:
        return article_version_mapping.get(ver.upper())
    return None


def strip_remove_multispace(s):
    """
    Strip white space from either end of passed string, and replace all multi-space by single space
    :param s: String
    :return: Modified string
    """
    if s is None:
        return ""

    # Strip white space from start/end of s, then replace any multiple white-space by a single space
    return match_multispace.sub(" ", s.strip())


def remove_embedded_xml_and_redundant_headings_from_titles_abstract_ack(data, is_harvested=False):
    """
    Remove any XML or HTML tags that may be present in the following fields in HARVESTED notifications:
        article title, article_abstract, journal title, acknowledgement

    Remove redundant headings:
        - Remove "Acknowledgement" heading from acknowledgement element text
        - Remove "Abstract" heading from abstract element text

    :return: Notification data dict
    """
    def remove_tags_n_heading(base_dict, key, strip_tags=True, remove_heading=None):
        v = base_dict.get(key)
        if v:
            if strip_tags and "<" in v:
                v = strip_tags_adjust_whitespace(v, complex=True)
            if remove_heading:
                v = remove_heading.sub("", v)
            base_dict[key] = v

    # NB. We always expect to have "metadata", "metadata.article" and "metadata.journal" data entries
    meta = data["metadata"]
    article = meta["article"]

    if is_harvested:
        remove_tags_n_heading(meta["journal"], "title")   # Process "metadata.journal.title"
        remove_tags_n_heading(article, "title")           # Process "metadata.article.title"
    # Process "metadata.article.abstract"
    remove_tags_n_heading(article, "abstract", strip_tags=is_harvested, remove_heading=match_abstract_title)
    # Process "metadata.ack"
    remove_tags_n_heading(meta, "ack", strip_tags=is_harvested, remove_heading=match_ack_title)

    return data


class NotificationMetadata(dataobj.DataObj):
    """
    {
        "vers: <Metadata structure version string e.g. "4">,
        "category": <Char - Up to 3 character code (may be single char) that defines Type of resource.>,
        "has_pdf": <Boolean - indicates if notification has a PDF file associated with it>,
        "metadata" : {
            "journal" : {
                "title" : "<Journal title or book title in series title>",
                "abbrev_title" : "<Abbreviated version of journal  title>",
                "volume" : "<Number of a journal (or other document) within a series>",
                "issue" : "<Issue number of a journal, or in rare instances, a book.>",
                "publisher" : ["<Name of the publisher of the content>"], /* can have > 1 */
                "identifier" : [{
                        "type" : "issn",
                        "id" : "<issn of the journal (could be print or electronic)>"
                    }, {
                        "type" : "eissn",
                        "id" : "<electronic issn of the journal>"
                    }, {
                        "type" : "pissn",
                        "id" : "<print issn of the journal>"
                    }, {
                        "type" : "doi",
                        "id" : "<doi for the journal or series>"
                    }
                ]

            },
            "article" : {
                "doi": "<Article DOI - ONLY for RoutedNotification >",
                "title" : "<Article title or book chapter title>",
                "subtitle" : ["<Article title or book chapter Subtitle>"],  /* >1 */
                "type" : "<Type or kind of article 'research', 'commentary', 'review', 'case', or 'calendar')>",
                "version" : "<version of the record, e.g. AAM>",
                "start_page" : "<Page number on which a document starts>",
                "end_page" : "<Page number on which a document ends>",
                "page_range" : "<Text describing discontinuous pagination.>",
                "num_pages" : "<Total number of pages>",
                "e_num": "<Article number (JATS e-location number)>"
                "language" : ["<languages >"],
                "abstract" : "<Abstract of the work >",
                "identifier" : [{
                        /* NB. for RoutedNotification DOI will ALSO be stored in article.doi field - see above*/
                        "type" : "doi", /*  may be others, such as "pmcid" */
                        "id" : "<doi for the record>" /*  */
                    }],
                "subject" : ["<subject keywords/classifications>"]
            },

            "author" : [ {
                    "type" : "<Type of contribution author>",
                    "name" : {
                        "firstname" : "<author first name>",
                        "surname" : "<author surname>",
                        "fullname" : "<author name>",
                        "suffix" : "<Qualifiers that follow a persons name Sr. Jr. III, 3rd>"
                    },
                    "organisation_name" : "<Name of organisation if author is an organisation >",
                    "identifier" : [{
                            "type" : "orcid",
                            "id" : "<author's orcid>"
                        }, {
                            "type" : "email",
                            "id" : "<author's email address>"
                        }],
                    "affiliation" : "<author affiliation - ORIGINAL simple string>",    # ZZZ - API v3 REMOVE in due course
                    "affiliations": [ {
                        "identifier" : [{
                            "type" : "ISNI",
                            "id" : "<institution ISNI Id>"
                        }, {
                            "type" : "ROR",
                            "id" : "<institution ROR Id>"
                        }],
                        "org": "<Organisation name> or field absent (*)",
                        "dept": "<Org division/dept> or field absent (*)",
                        "street": "<Street> or field absent",
                        "city": "<City> or field absent",
                        "state": "<State> or field absent",
                        "postcode": "<Post code> or field absent",
                        "country": "<Country> or field absent",
                        "country_code": "<Country code> or field absent",
                        "raw": "<Unstructured affilation> or absent",
                    ] }
            } ],
            "contributor" : [{
                    "type" : "<Type of contribution like editor..>",
                    "name" : {
                        "firstname" : "<editor first name>",
                        "surname" : "<editor surname>",
                        "fullname" : "<editor name>",
                        "suffix" : "<Qualifiers that follow a persons name Sr. Jr. III, 3rd>"
                    },
                    "organisation_name" : "<Name of organisation if editor is an organisation >",
                    "identifier" : [{
                            "type" : "orcid",
                            "id" : "<editor's orcid>"
                        }, {
                            "type" : "email",
                            "id" : "<editor's email address>"
                        }],
                    "affiliation" : "<author affiliation - ORIGINAL simple string>",    # ZZZ - API v3 REMOVE in due course
                    "affiliations": [ {
                        "identifier" : [{
                            "type" : "ISNI",
                            "id" : "<institution ISNI Id>"
                        }, {
                            "type" : "ROR",
                            "id" : "<institution ROR Id>"
                        }],
                        "org": "<Organisation name> or field absent (*)",
                        "dept": "<Org division/dept> or field absent (*)",
                        "street": "<Street> or field absent",
                        "city": "<City> or field absent",
                        "state": "<State> or field absent",
                        "postcode": "<Post code> or field absent",
                        "country": "<Country> or field absent",
                        "country_code": "<Country code> or field absent",
                        "raw": "<Unstructured affilation> or absent"
                    ] }
            } ],
            "accepted_date" : "<date>" /* yyyy-mm-dd format*/,
            "publication_date" : {
                "publication_format" : "<Format of publication (print, electronic)>",
                "date" : "<date>", /* yyyy-mm-dd format*/
                "year" : "year":"<year>" /* yyyy format */
                "month" : "month":"<month>" /* mm format */
                "day" : "day":"<day>" /* dd format */
                "season" : "<Season of publication (for example, Spring, Third Quarter).>"
            },
            "history_date" : [{
                "date_type" : "<Type of date: received, accepted...>", /* NEED TO DEFINE POSSIBILIES */
                "date" : "<date>"
            }],
            "publication_status" : "<Published, accepted, submitted or blank>",
            "funding" : [{
                    "name" : "<name of funder>",
                    "identifier" : [{
                            "type" : "<identifier type>",
                            "id" : "<funder identifier>"
                        }
                    ],
                    "grant_numbers" : ["<list of funder's grant numbers>"]
                }
            ],
            "embargo" : {
                "start" : "<embargo start date>",
                "end" : "<embargo end date>",
                "duration" : "<embargo duration in days>"
            },
           "license_ref" : [{
                "title" : "<name of licence>",
                "type" : "<type>", /* For example would be used to indicate <ali:free_to_read> or other eg. cc-by */
                "url" : "<url>",
                "version" : "<version>",
                "start" : "<Date licence starts>",
                "best" : "<Boolean indicates if best licence>"
            }],
            "peer_reviewed" : "<Boolean indicates if article is peer reviewed>",
            "ack": "<Acknowledgement(s)>"
        }
    }
    """
    # Category values
    ARTICLE = "JA"

    def __init__(self, raw=None, **kwargs):
        """
        Create a new instance of the NotificationMetadata object, optionally around the raw python dictionary.

        In reality, this class provides a base-class for all other notification-like objects
        (in this module and in others) so you will never instantiate it directly.

        If supplied, the raw dictionary will be validated against the allowed structure of this
        object, and an exception will be raised if it does not validate

        :param raw: python dict object containing the metadata
        """
        identifier_struct = {
            "fields": {
                "type": {"coerce": "unicode"},
                "id": {"coerce": "unicode"}
            }
        }
        auth_contrib_struct = {
            "fields": {
                "type": {"coerce": "unicode"},
                "organisation_name": {"coerce": "unicode"},
                "affiliation": {"coerce": "unicode"}    # Original affiliation - ZZZ - API v3 REMOVE in due course
            },
            "objects": ["name"],
            "lists": {
                "identifier": {"contains": "object"},
                "affiliations": {"contains": "object"}
            },
            "structs": {
                "name": {
                    "fields": {
                        "firstname": {"coerce": "unicode"},
                        "surname": {"coerce": "unicode"},
                        "fullname": {"coerce": "unicode"},
                        "suffix": {"coerce": "unicode"}
                    }
                },
                "identifier": identifier_struct,
                "affiliations": {
                    "fields": {
                        "org": {"coerce": "unicode"},
                        "dept": {"coerce": "unicode"},
                        "street": {"coerce": "unicode"},
                        "city": {"coerce": "unicode"},
                        "state": {"coerce": "unicode"},
                        "postcode": {"coerce": "unicode"},
                        "country": {"coerce": "unicode"},
                        "country_code": {"coerce": "unicode"},
                        "raw": {"coerce": "unicode"}
                    },
                    "lists": {
                        "identifier": {"contains": "object"}
                    },
                    "structs": {
                        "identifier": {
                            "fields": {
                                "type": {"coerce": "uc_upper"},     # Force to Upper Case
                                "id": {"coerce": "unicode"}
                            }
                        }
                    }
                }
            }
        }
        struct = {
            "fields": {
                "vers": {},
                "category": {},
                "has_pdf": {}
            },
            "objects": [
                "metadata"
            ],
            "structs": {
                "metadata": {
                    "fields": {
                        "publication_status": {"coerce": "unicode"},
                        "accepted_date": {"coerce": "y_m_d_date"},
                        "peer_reviewed": {"coerce": "bool"},
                        "ack": {}
                    },
                    "objects": [
                        "journal", "article", "publication_date", "embargo"
                    ],
                    "lists": {
                        "author": {"contains": "object"},
                        "contributor": {"contains": "object"},
                        "history_date": {"contains": "object"},
                        "funding": {"contains": "object"},
                        "license_ref": {"contains": "object"}
                    },
                    "required": [],

                    "structs": {
                        "journal": {
                            "fields": {
                                "title": {"coerce": "unicode"},
                                "abbrev_title": {"coerce": "unicode"},
                                "volume": {"coerce": "unicode"},
                                "issue": {"coerce": "unicode"}
                            },
                            "lists": {
                                "publisher": {"contains": "field", "coerce": "unicode"},
                                "identifier": {"contains": "object"}
                            },
                            "structs": {
                                "identifier": identifier_struct
                            }
                        },
                        "article": {
                            "fields": {
                                "doi": {},
                                "title": {"coerce": "unicode"},
                                "type": {"coerce": "unicode"},
                                "version": {"coerce": "uc_upper"},
                                "start_page": {"coerce": "unicode"},
                                "end_page": {"coerce": "unicode"},
                                "page_range": {"coerce": "unicode"},
                                "num_pages": {"coerce": "unicode"},
                                "e_num": {"coerce": "unicode"},
                                "abstract": {"coerce": "unicode"}
                            },
                            "lists": {
                                "subtitle": {"contains": "field", "coerce": "unicode"},
                                "language": {"contains": "field", "coerce": "unicode"},
                                "subject": {"contains": "field", "coerce": "unicode"},
                                "identifier": {"contains": "object"}
                            },
                            "structs": {
                                "identifier": identifier_struct
                            }
                        },
                        "author": auth_contrib_struct,
                        "contributor": auth_contrib_struct,
                        "publication_date": {
                            "fields": {
                                "publication_format": {"coerce": "unicode"},
                                "date": {"coerce": "y_m_d_date"},
                                "year": {"coerce": "unicode"},
                                "month": {"coerce": "unicode"},
                                "day": {"coerce": "unicode"},
                                "season": {"coerce": "unicode"}
                            }
                        },
                        "history_date": {
                            "fields": {
                                "date_type": {"coerce": "unicode"},
                                "date": {"coerce": "y_m_d_date"}
                            }
                        },
                        "funding": {
                            "fields": {
                                "name": {"coerce": "unicode"}
                            },
                            "lists": {
                                "identifier": {"contains": "object"},
                                "grant_numbers": {"contains": "field", "coerce": "unicode"}
                            },
                            "structs": {
                                "identifier": identifier_struct
                            }
                        },
                        "embargo": {
                            "fields": {
                                "start": {"coerce": "y_m_d_date"},
                                "end": {"coerce": "y_m_d_date"},
                                "duration": {"coerce": "unicode"}
                            }
                        },
                        "license_ref": {
                            "fields": {
                                "title": {"coerce": "unicode"},
                                "type": {"coerce": "unicode"},
                                "url": {"coerce": "unicode"},
                                "version": {"coerce": "unicode"},
                                "start": {"coerce": "y_m_d_date"},
                                "best": {"coerce": "bool"}      # Only used for OutgoingNotification
                            }
                        }
                    }
                }
            }
        }

        self._add_struct(struct)
        super(NotificationMetadata, self).__init__(raw, **kwargs)

    def _validate_coerce(self, val_dict, valid_keys, coerce_fn, obj_name):
        for key in val_dict:
            # Validate
            if key not in valid_keys:
                raise dataobj.DataSchemaException(f"'{obj_name}' object cannot contain key: {key}")
            # Coerce
            if coerce_fn:
                val_dict[key] = self._coerce(val_dict[key], coerce_fn, key)

        return val_dict

    def _validate_coerce_dates_unicode(self, obj, valid_date_keys, valid_unicode_keys, coerce_func, ob_name):

        for key in obj:
            # Validate & Coerce
            if key in valid_date_keys:
                obj[key] = self._coerce(obj[key], coerce_func, key)
            elif key in valid_unicode_keys:
                obj[key] = str(obj[key])
            else:
                raise dataobj.DataSchemaException(f"'{ob_name}' object cannot contain key: {key}")

        return obj

    def _validate_coerce_funding_object(self, obj):
        """
        validate and coerce a funding object into format 
        {
            "identifier": [{"type": UNICODE, "id": UNICODE}], 
            "grant_numbers": [UNICODE],
            "name": UNICODE
        }
        """
        for key in obj:
            # validate and coerce all identifier objects
            if key == "identifier":
                # Loop for each ID-object in Identifier array	
                for id_obj in obj["identifier"]:
                    # id_obj should be {"type":"<id-type>", "id":"<id-value>"}	
                    self._validate_coerce(id_obj, ["type", "id"], None, "Funding identifier")
            # validate grant numbers and coerce to unicode
            elif key == "grant_numbers":
                grants = obj["grant_numbers"]
                if not isinstance(grants, list):
                    raise dataobj.DataSchemaException("Funding grant_numbers must be a list")

                for ix, grant in enumerate(grants):
                    grants[ix] = str(grant)     # str() in unlikely event a number value was passed in
            # validate name and coerce to unicode
            elif key != "name":
                raise dataobj.DataSchemaException(f"Funding cannot contain key: {key}")

    ##
    # JOURNAL PROPERTIES
    ##

    @property
    def journal_title(self):
        """
        The journal title.

        :return: The journal title
        """
        return self._get_single("metadata.journal.title")

    @staticmethod
    def calc_cat_from_single_article_type(article_type, default="O"):
        """
        Calculate Category (resource type) code (1 to 3 chars) by analysing a single article_type value
        :param article_type: String
        :param default: String - Default category code
        :return: String - Category code (1 to 3 chars)
        """
        single_art_type_to_cat = {
            "monograph": "B",  # book
            "book-chapter": "BC",  # book part
            "proceedings": "CP",  # conference proceedings
            "correction": "JAC",  # corrigendum
            "erratum": "JAC",  # corrigendum
            "retraction": "JAC",  # corrigendum
            "published-erratum": "JAC",  # corrigendum
            "retraction-of-publication": "JAC",  # corrigendum
            "corrected-and-republished-article": "JAC",  # corrigendum
            "data-paper": "JAD",  # data paper
            "abstract": "JAR",  # research article
            "methods-article": "JAR",  # research article
            "research-article": "JAR",  # research article
            "article": "JAR",  # research article
            "journal-article": "JAR",  # research article
            "rapid-communication": "JAR",  # Research article
            "discussion": "JAV",  # review article
            "product-review": "JAV",  # review article
            "review-article": "JAV",  # review article
            "systematic-review": "JAV",  # review article
            "editorial": "JE",  # editorial
            "letter": "JL",  # letter to the editor
            "reply": "JL",  # letter to the editor
            "lecture": "U",     # Lecture
            "article-preprint": "P",  # preprint
            "preprint": "P",  # preprint
            "report": "R",  # Report
            "meeting-report": "RM",  # memorandum
            "practice-and-policy": "RO",  # policy report
            "practice-guideline": "RO",  # policy report
            "brief-report": "RR",  # research report
            "case-report": "RR",  # research report
            "case-study": "RR",  # research report
            "case-reports": "RR",  # research report
            "technical-note": "RT",  # technical report
            "book-review": "VB",  # book review
            "article-commentary": "VC",  # commentary
            "clinical-conference": "C",  # Conference output
            "short-communication": "RR",  # Research report
            "perspective": "RR",  # Research report
        }
        # Convert article-type to lower case; & replace any spaces by '-'
        return single_art_type_to_cat.get(article_type.strip().lower().replace(" ", "-"), default) if article_type \
            else default

    @staticmethod
    def calc_cat_from_compound_article_type(article_type, default="O"):
        """
        Calculate Category (resource type) code (1 to 3 chars) by analysing an article_type string containing
        multiple values separated by '; ' (semicolon).
        :param article_type: String of article types, separated by semicolon
        :param default: String - Default category code
        :return: String - Category code (1 to 3 chars)
        """
        # The ordering of this list is important...
        first_pass = [
            (["research-article", "abstract", "clinical trial", "methods-article", "journal-article"], "JAR"),
            # Journal research article
            (["review", "review-article", "systematic-review", "systematic review", "product-review"], "JAV"),
            # Journal review article
            (["data-paper"], "JAD"),  # Journal data paper
            (["correction", "erratum", "retraction", "published erratum", "retraction of publication",
              "corrected and republished article"], "JAC"),  # Journal article corrigendum
            (["article-commentary"], "VC"),  # Review commentary
            (["brief-report", "case reports", "case-study"], "RR"),  # Research report
            (["letter", "Letter", "reply"], "JL"),  # Journal letter
            (["editorial", "Editorial"], "JE"),  # Journal editorial
            (["meeting-report"], "RM"),  # Report memorandum
            (["clinical trial protocol"], "RL"),  # Research Protocol report
            (["practice-and-policy", "practice guideline"], "RO"),  # Policy report
            (["preprint", "article-preprint"], "P"),  # Preprint
            (["monograph"], "B"),  # Book
            (["book-chapter"], "BC"),  # Book chapter
            (["book-review"], "VB"),  # Book review
            (["report"], "R"),  # Report
            (["technical-note"], "RT"),  # Technical report
            (["proceedings"], "CP"),  # Conference proceedings
            (["clinical conference"], "C"),  # Conference output
        ]
        # After forcing to lower case
        second_pass = [
            (["case-report"], "RR"),  # Research report
            (["journal article", "article", ], "JAR"),  # Journal research article
        ]

        if article_type:
            # Some article types are concatenated strings, joined by "; "
            type_list = [s.strip() for s in article_type.split("; ")]

            for compare_list, cat_code in first_pass:
                for art_type in type_list:
                    if art_type in compare_list:
                        return cat_code

            for compare_list, cat_code in second_pass:
                for art_type in type_list:
                    if art_type.lower() in compare_list:
                        return cat_code
        return default

    @classmethod
    def calc_category_from_article_type(cls, article_type, default="O"):
        """
        Compares article_type value with keywords and returns Category (resource type) code (1 to 3 chars).
        USE THIS METHOD IF YOU AREN'T SURE IF article_type IS SIMPLE (SINGLE) OR COMPOUND STRING.

        :param article_type: - Article type string, possibly separate values concatenated with '; '
        :param default: String - default category code if match not found
        :return: Category code of 1 to 3 chars.
        """
        # Below we use (article_type or "") in case article_type is None. Both of the called functions will return
        # default if article_type is None.
        # This slightly more efficient than always testing for `if article_type is None` beforehand.
        if ";" in (article_type or ""):
            return cls.calc_cat_from_compound_article_type(article_type, default)
        else:
            return cls.calc_cat_from_single_article_type(article_type, default)

    @staticmethod
    def decode_category(cat_code, raise_on_error=True):
        """
        Convert 1 to 3 character Category code into resource type description using COAR Controlled Vocabulary
        See: https://vocabularies.coar-repositories.org/resource_types/

        :param cat_code: String - 1 to 3 character UPPERCASE category code
        :param raise_on_error: Boolean - True: Raise an EncodingWarning exception if category code doesn't exactly match;
                                         False: Return Error string in place of decoded category
        :return: Category description string
        """
        cat_map = {
            "J": ("journal",
                  {
                    "E": ("editorial", None),
                    "A": ("journal article",
                          {
                              "C": ("corrigendum", None),
                              "D": ("data paper", None),
                              "R": ("research article", None),
                              "V": ("review article", None),
                              "S": ("software paper", None)
                          }),
                    "L": ("letter to the editor", None)
                  }),
            "B": ("book",   # Aka Monograph
                  {
                      "C": ("book part", None)  # Aka Book chapter
                  }),
            "C": ("conference output",
                  {
                      "E": ("conference presentation", None),
                      "P": ("conference proceedings",
                            {
                                "A": ("conference paper", None),
                                "O": ("conference poster", None)
                            }),
                      "A": ("conference paper not in proceedings", None),
                      "O": ("conference poster not in proceedings", None)
                  }),
            "R": ("Report",
                  {
                      "C": ("clinical study", None),
                      "D": ("data management plan", None),
                      "M": ("memorandum", None),
                      "O": ("policy report", None),
                      "P": ("project deliverable", None),
                      "R": ("research report", None),
                      "T": ("technical report", None),
                      "L": ("research protocol", None)
                  }),
            "P": ("preprint", None),
            "V": ("review",
                  {
                      "B": ("book review", None),
                      "C": ("commentary", None),
                      "P": ("peer review", None)
                  }),
            "L": ("letter", None),
            "U": ("lecture", None),
            "O": ("other", None)
        }
        desc = None
        mapped_code = ""
        ok = False
        if cat_code:
            map_dict = cat_map
            # Iterate over list of characters in category-code string
            for code_char in list(cat_code):
                desc, map_dict = map_dict.get(code_char, (None, None))
                if desc:
                    mapped_code += code_char
                if not map_dict:
                    break
        if not desc:
            desc = f"Unrecognised category code: '{cat_code}'"
        elif cat_code != mapped_code:
            desc += f" - partially matched '{mapped_code}' of code: '{cat_code}'"
        else:
            ok = True
        if not ok and raise_on_error:
            raise EncodingWarning(desc)

        return desc

    @property
    def category(self):
        return self._get_single("category")

    @category.setter
    def category(self, val):
        self._set_single("category", val)

    @property
    def has_pdf(self):
        return self._get_single("has_pdf")

    @has_pdf.setter
    def has_pdf(self, val):
        self._set_single("has_pdf", val)

    @journal_title.setter
    def journal_title(self, val):
        """
        Set the journal title.

        :param val: the journal title
        """
        self._set_single("metadata.journal.title", val, ignore_none=True)

    @property
    def journal_abbrev_title(self):
        """
        The journal abbrev_title.

        :return: The journal abbrev_title
        """
        return self._get_single("metadata.journal.abbrev_title")

    @journal_abbrev_title.setter
    def journal_abbrev_title(self, val):
        """
        Set the journal abbrev_title.

        :param val: the journal abbrev_title
        """
        self._set_single("metadata.journal.abbrev_title", val, ignore_none=True)

    @property
    def journal_volume(self):
        """
        The journal volume.

        :return: The journal volume
        """
        return self._get_single("metadata.journal.volume")

    @journal_volume.setter
    def journal_volume(self, val):
        """
        Set the journal volume.

        :param val: the journal volume
        """
        self._set_single("metadata.journal.volume", val, coerce=TO_UNICODE, ignore_none=True)

    @property
    def journal_issue(self):
        """
        The journal issue.

        :return: The journal issue
        """
        return self._get_single("metadata.journal.issue")

    @journal_issue.setter
    def journal_issue(self, val):
        """
        Set the journal issue.

        :param val: the journal issue
        """
        self._set_single("metadata.journal.issue", val, coerce=TO_UNICODE, ignore_none=True)

    @property
    def journal_publishers(self):
        """
        The list of journal_publishers strings.

        :return: list of journal_publishers
        """
        return self._get_list("metadata.journal.publisher")

    @journal_publishers.setter
    def journal_publishers(self, objlist):
        """
        Add a journal_publisher list

        :param objlist: list of journal_publishers
        :return:
        """
        self._set_list("metadata.journal.publisher", objlist)

    def add_journal_publisher(self, value):
        """
        Add a journal_publisher keyword to the list

        :param value: new journal_publisher
        :return:
        """
        self._add_to_list("metadata.journal.publisher", value, unique=True)

    @property
    def journal_identifiers(self):
        """
        The list of identifier objects for the journal (e.g. journal) work represented by this metadata.
        The returned objects look like:

        ::

            {"type" : "<identifier type>", "id" : "<actual identifier>" }

        :return: List of python dict objects containing the identifier information for the journal
        """
        return self._get_list("metadata.journal.identifier")

    @journal_identifiers.setter
    def journal_identifiers(self, objlist):
        """
        Set journal_identifiers list

        :param objlist: list of identifier objects
        :return: nothin
        """
        self._set_list("metadata.journal.identifier", objlist)

    def add_journal_identifier(self, type, id):
        """
        Add an identifier for the journal (e.g. an ISSN for a journal)

        :param type: the type of identifier
        :param id: the identifier itself
        """
        if id is None or type is None:
            return
        # str() id in unlikely event a number is passed
        obj = {"id": str(id), "type": type}
        # self._delete_from_list("metadata.journal.identifier", matchsub=obj, prune=False)
        self._add_to_list("metadata.journal.identifier", obj, unique=True)

    def get_journal_identifiers(self, type):
        """
        Get list of journal identifiers of a particular type.

        Note that this returns a simple list of Ids, not a dict.

        :return: List of identifiers of the requested type
        """
        return [i.get("id") for i in self._get_list("metadata.journal.identifier") if i.get("type") == type]

    ##
    # ARTICLE PROPERTIES
    ##

    def calculate_embargo_and_best_license(self, licenses_and_article_versions):
        """
        Take a list of licenses and respective article versions and attempt to use this information to calculate the
        'best license'. All calculations made using following algorithm: 
        
        Ignore any licences with content-version not in (EVoR, CVoR, VoR, P, AM) 
        If there any article versions have open licence(s): 
            If there are any whose start dates are in the past or which have no start-date:
                Prioritise the article version in this order: EVoR, CVoR, VoR, P, AM. 
            Else, if all open licences have start dates that are in the future:
                Take the article version whose open licence has the earliest start date  
        Else, if there are multiple article versions whose earliest open licences have the SAME start dates:
            Prioritise in this order: EVoR, CVoR, VoR, P, AM 
        Else, if there is at least one licence, but none of these are open licences 
            Prioritise the article version in this order: AM, P, VoR, CVoR, EVoR. 
        Else, if there are no licences for any of the versions in the list (AM, P, VoR, CVoR, EVoR):
            do not populate the article version field and do not harvest any licence metadata.

        :param licenses_and_article_versions: A list of tuples (license, article_version)
            license: a license is an IncomingNotification license object. Minimally containing the
            following key:value pairs -
            license = {
                "url": "",   # the URL of the given license
                "start": "YYYY-MM-DD" (optional)   # the start date of the given license in "YYYY-MM-DD" form,
                # if start empty, assume license already started
                ...
            }
            article_version: the version of the article this license pertains to

        :return: tuple (Dict-best_license, String-best_article_version, Boolean-calculate_embargo)
                * best_license: contains the licensing information for the calculated 'best license'
                * best_article_version: the respective article version for our 'best license'
                * calculate_embargo: indicates if this record requires an embargo calculation.

            returns (None, None, False) if we failed to successfully calculate a best license from given information
        """
        # list of current valid content versions in uppercase, in PRIORITY ORDER (highest first)
        prioritised_valid_article_versions = ["EVOR", "CVOR", "VOR", "P", "AM"]

        def _is_better_article_version(article_version, second_article_version):
            """
            Function is defined as a sub function to access prioritised_valid_article_versions without passing as an
            argument. Returns Boolean indicating if a license's article version appears earlier within the list
            prioritised_valid_article_versions, for example an application of this to two article versions,
            article_version of "vor" and second_article_version of "p", would return True.

            :param article_version: article version to compare against second_article_version.
            :param second_article_version: article_version to be compared against.

            :return: True: if first article_version appears earlier in the list ["evor", "cvor", ... ]
            than second_article_version; otherwise returns False
            """
            article_index = prioritised_valid_article_versions.index(article_version)
            second_article_index = prioritised_valid_article_versions.index(second_article_version)
            return article_index < second_article_index

        # refine list of licenses into list containing only licenses with article_version in
        # prioritised_valid_article_versions
        valid_licenses_and_article_versions = [
            # _tuple[1] is the article version
            _tuple for _tuple in licenses_and_article_versions if _tuple[1] in prioritised_valid_article_versions
        ]

        # set up variables used in algorithm
        best_open_license = None
        best_open_article_version = None
        best_closed_license = None
        best_closed_article_version = None
        # today's date in "YYYY-MM-DD" form (same format as start's)
        today = datetime.today().strftime("%Y-%m-%d")

        # Loop over all licenses (they are in random order)
        for license, article_version in valid_licenses_and_article_versions:
            if self.is_open_license(license):
                # if we currently have no best_open_license, this open license is our best by default
                if best_open_license is None:
                    best_open_license = license
                    best_open_article_version = article_version
                else:  # We already have an open license - need to see if the current license is a better option
                    license_start_date = license.get("start", "")
                    best_open_license_start_date = best_open_license.get("start", "")

                    # If best open license is already active (started in the past)
                    if best_open_license_start_date < today:

                        # we only consider open licenses which also start in the past (i.e. already active)
                        if license_start_date < today:

                            # As best license and current license are both active, then we compare the article versions
                            # and choose the one appearing EARLIER in the list prioritised_valid_article_versions
                            if _is_better_article_version(article_version, best_open_article_version):
                                best_open_license = license
                                best_open_article_version = article_version
                    # if our best license is in the future, simply choose the license which starts EARLIER
                    elif license_start_date < best_open_license_start_date:
                        best_open_license = license
                        best_open_article_version = article_version
                    # if our best license is in the future, but the start dates are equal, prioritise licenses which
                    # appear EARLIER in the list prioritised_valid_article_versions
                    elif license_start_date == best_open_license_start_date:
                        if _is_better_article_version(article_version, best_open_article_version):
                            best_open_license = license
                            best_open_article_version = article_version

            # we aren't working with an open license
            else:
                # if we have no best_closed_license, this closed license is our best by default
                if best_closed_license is None:
                    best_closed_license = license
                    best_closed_article_version = article_version
                # if we already have a closed license, simply prioritise licenses which appear LATER in the list
                # prioritised_valid_article_versions, (hence using not _is_better_article_version)
                elif not _is_better_article_version(article_version, best_closed_article_version):
                    best_closed_license = license
                    best_closed_article_version = article_version

        # default return values
        calculate_embargo = False

        # if we found an open_license, return this
        if best_open_license:
            # if our best_open_license starts in the future, we need to calculate embargo
            if best_open_license.get("start", "") > today:
                calculate_embargo = True
            return best_open_license, best_open_article_version, calculate_embargo
        # else if we found a closed_license, return this
        elif best_closed_license:
            return best_closed_license, best_closed_article_version, calculate_embargo
        # we failed to find any valid open license in our list
        return None, None, calculate_embargo

    @staticmethod
    def is_open_license(license=None, lic_url=None):
        """
        Method which calculates whether a license is an open license, by looking at the URL and comparing this
        to a list of open license URLs.

        :param license: License object we are checking.
        :param lic_url: OPTIONAL license URL

        :return: Boolean - True: the license is an open license; False: license is NOT open
        """
        # list of currently considered open licenses
        if lic_url is None:
            lic_url = license.get("url")
        if lic_url:
            # Iterate through all strings that identify an open license
            for keyword in current_app.config.get("OPEN_LICENCE_KEYWORD_LIST", []):
                if keyword in lic_url:
                    return True
        return False

    @property
    def article_title(self):
        """
        The article title.

        :return: The article title
        """
        return self._get_single("metadata.article.title")

    @article_title.setter
    def article_title(self, val):
        """
        Set the article title.

        :param val: the article title
        """
        self._set_single("metadata.article.title", val, ignore_none=True)

    @property
    def article_type(self):
        """
        The article type.

        :return: The article type
        """
        return self._get_single("metadata.article.type")

    @article_type.setter
    def article_type(self, val):
        """
        Set the article type.

        :param val: the article type
        """
        self._set_single("metadata.article.type", val, ignore_none=True)

    @property
    def article_version(self):
        """
        The article version.

        :return: The article version
        """
        return self._get_single("metadata.article.version")

    @article_version.setter
    def article_version(self, val):
        """
        Set the article version.

        :param val: the article version
        """
        self._set_single("metadata.article.version", val, coerce=TO_UNICODE, ignore_none=True)

    @property
    def article_start_page(self):
        """
        The article start_page.

        :return: The article start page
        """
        return self._get_single("metadata.article.start_page")

    @article_start_page.setter
    def article_start_page(self, val):
        """
        Set the article start_page.

        :param val: the article start_page
        """
        self._set_single("metadata.article.start_page", val, coerce=TO_UNICODE, ignore_none=True)

    @property
    def article_end_page(self):
        """
        The article end_page.

        :return: The article end page
        """
        return self._get_single("metadata.article.end_page")

    @article_end_page.setter
    def article_end_page(self, val):
        """
        Set the article end_page.

        :param val: the article end_page
        """
        self._set_single("metadata.article.end_page", val, coerce=TO_UNICODE, ignore_none=True)

    @property
    def article_page_range(self):
        """
        The article page_range.

        :return: The article page range
        """
        return self._get_single("metadata.article.page_range")

    @article_page_range.setter
    def article_page_range(self, val):
        """
        Set the article page_range.

        :param val: the article page_range
        """
        self._set_single("metadata.article.page_range", val, coerce=TO_UNICODE, ignore_none=True)

    @property
    def article_e_num(self):
        """
        The article e_num (JATS <elocation-id>)

        :return: The article e-number / elocation-id
        """
        return self._get_single("metadata.article.e_num")

    @article_e_num.setter
    def article_e_num(self, val):
        """
        Set the e_num (JATS <elocation-id>)

        :param val: the article e_num (JATS <elocation-id>)
        """
        self._set_single("metadata.article.e_num", val, coerce=TO_UNICODE, ignore_none=True)

    @property
    def article_num_pages(self):
        """
        The article num_pages.

        :return: The article number of pages
        """
        return self._get_single("metadata.article.num_pages")

    @article_num_pages.setter
    def article_num_pages(self, val):
        """
        Set the article num_pages.

        :param val: the article num_pages
        """
        self._set_single("metadata.article.num_pages", val, coerce=TO_UNICODE, ignore_none=True)

    @property
    def article_abstract(self):
        """
        The article abstract.

        :return: The article abstract
        """
        return self._get_single("metadata.article.abstract")

    @article_abstract.setter
    def article_abstract(self, val):
        """
        Set the article abstract

        :param val: the article abstract
        """
        self._set_single("metadata.article.abstract", val, ignore_none=True)

    @property
    def article_subtitle(self):
        """
        The list of article_subtitle strings.

        :return: list of article_subtitle
        """
        return self._get_list("metadata.article.subtitle")

    def add_article_subtitle(self, value):
        """
        Add an article_subtitle keyword to the list

        :param value: new article_subtitle
        :return:
        """
        self._add_to_list("metadata.article.subtitle", value, unique=True)

    @property
    def article_language(self):
        """
        The list of article_language strings.

        :return: list of article_language
        """
        return self._get_list("metadata.article.language")

    @article_language.setter
    def article_language(self, values):
        """
        Add list of article languages

        :param values: List of language codes
        :return:
        """
        self._set_list("metadata.article.language", values)

    def add_article_language(self, value):
        """
        Add an article_language keyword to the list

        :param value:  language code
        :return:
        """
        self._add_to_list("metadata.article.language", value, unique=True)

    @property
    def article_subject(self):
        """
        The list of article_subject strings.

        :return: list of article_subject
        """
        return self._get_list("metadata.article.subject")

    @article_subject.setter
    def article_subject(self, objlist):
        """
        Add a list of article_subject strings.

        :param objlist: article_subject list
        """
        self._set_list("metadata.article.subject", objlist)

    def add_article_subject(self, value):
        """
        Add an article_subject keyword to the list

        :param value: new article_subject
        :return:
        """
        self._add_to_list("metadata.article.subject", value, unique=True)

    @property
    def article_doi(self):
        """
        Gets Article DOI value (lower-case) from list of article identifiers (NOTE different from RoutedNotification).

        :return: String - Article DOI; or None
        """
        # returns the doi of this article if it has one, else returns None
        for id_dict in self.article_identifiers:
            if id_dict.get("type") == "doi":
                return id_dict.get("id").lower()
        return None

    @property
    def article_identifiers(self):
        """
        The list of identifier objects for the article (e.g. journal) work represented by this metadata.
        The returned objects look like:

        ::

            {"type" : "<identifier type>", "id" : "<actual identifier>" }

        :return: List of python dict objects containing the identifier information for the article
        """
        return self._get_list("metadata.article.identifier")

    @article_identifiers.setter
    def article_identifiers(self, objlist):
        """
        Set article_identifiers list

        :param objlist: list of identifier objects
        :return: nothing
        """
        self._set_list("metadata.article.identifier", objlist)

    def add_article_identifier(self, type, id):
        """
        Add an identifier for the article (e.g. an ISSN for a journal)

        :param type: the type of identifier
        :param id: the identifier itself
        """
        if id is None or type is None:
            return
        obj = {"id": str(id), "type": type}
        # self._delete_from_list("metadata.article.identifier", matchsub=obj, prune=False)
        self._add_to_list("metadata.article.identifier", obj, unique=True)

    def get_article_identifiers(self, type):
        """
        The list of identifiers for the work represented by this metadata, as filtered by type.

        Unlike .identifiers, this returns a list of strings of the actual identifiers,
        rather than the dict representation.

        :return: List of identifiers of the requested type
        """
        return [i.get("id") for i in self._get_list("metadata.article.identifier") if i.get("type") == type]

    ##
    # AUTHOR
    ##

    def _validate_coerce_auth_contrib(self, obj):
        # validate the object structure quickly
        validation = {"type": (None, None),
                      "name": (["firstname", "surname", "fullname", "suffix"], "Author name"),
                      "organisation_name": (None, None),
                      "identifier": (["type", "id"], "Author identifier"),
                      "affiliations": (["raw", "identifier", "org", "dept", "street", "city", "state", "postcode", "country", "country_code"], "Author affiliations"),
                      }
        for k in obj:
            if k not in validation:
                raise dataobj.DataSchemaException(
                    f"Author object list must only contain the following keys: {list(validation.keys())}")
            expected_keys, desc = validation[k]
            if expected_keys:
                value = obj[k]
                if isinstance(value, list):
                    for val in value:
                        # validator[0] is list of valid keys; validator[1] is Description of thing being validated
                        self._validate_coerce(val, expected_keys, None, desc)
                else:
                    self._validate_coerce(value, expected_keys, None, desc)
        return obj

    @staticmethod
    def make_name_dict(firstname, surname, fullname=None, suffix=None):
        """
        Create the dict used to store name parts in an Author or Contributor structure.
        "name":  { "firstname" : "...",
                   "surname" : "...",
                   "fullname" : "...",
                   "suffix" : "..." }
        NOTE: Keys will NOT be present if there is no corresponding value
        :param firstname:
        :param surname:
        :param fullname:
        :param suffix:
        :return: Dict or None
        """
        # Construct fullname if it doesn't exist
        if not fullname:
            if surname:
                fullname = surname
                if firstname:
                    fullname += ", " + firstname

        if fullname:
            name = {"fullname": fullname}
            if surname:
                name["surname"] = surname
            if firstname:
                name["firstname"] = firstname
            if suffix:
                name["suffix"] = suffix
        else:
            name = None
        return name

    @staticmethod
    def extract_name_surname_suffix(name_obj):
        """
        helper function to extract first_name and surname from name_obj
        :param name_obj: contributor json structure. e.g.:
                "name": {
                    "firstname": "Aran",
                    "surname": "Kathrani",
                    "fullname": "Kathrani, Aran",
                    "suffix": "Snr."
                }
        :return: first_name, surname, suffix
        """
        surname = name_obj.get('surname', '')
        first_name = name_obj.get('firstname', '')
        suffix = name_obj.get('suffix', '')
        full_name_parts = None

        # If surname is None or empty string
        if not surname:
            # No surname, so get fullname (assume format: "Surname, Firstnames"
            full_name_parts = name_obj.get('fullname', '').partition(',')
            # 1st element will contain stuff before the separator
            if full_name_parts[0]:
                # Get surname from first element
                surname = full_name_parts[0].strip()

        # if firstname None or empty
        if not first_name:
            # Not yet retrieved this
            if full_name_parts is None:
                # No surname, so get fullname (assume format: "Surname, Firstnames"
                full_name_parts = name_obj.get('fullname', '').partition(',')
            # 3rd element will contain stuff after the separator
            if full_name_parts[2]:
                first_name = full_name_parts[2].strip()

        return first_name, surname, suffix

    @staticmethod
    def format_contrib_name(contrib, add_type=False):
        """
        Convert a contributor object to a standardised string representation of the name or organisation name,
        optionally prefixing with the contributor type. The returned string will have one of following formats -
        where [optional elements] are surround by square brackets
            "[Type: ]Surname[, Firstname][, Suffix][; Organisation-name]"
            "[Type: ]Organisation-name"

        :param contrib: author/contrib object
        :param add_type: Boolean - whether to add the Type of contributor as prefix
        :return: String - formatted name or None if there is no name
        """
        # If concatenating type of contributor, then this is set as the prefix, e.g. "editor: "
        c_type = contrib.get("type") if add_type else None
        contrib_text = f"{c_type}: " if c_type else ""

        name_obj = contrib.get("name")
        org_name = contrib.get("organisation_name")
        if name_obj:
            first_name, surname, suffix = NotificationMetadata.extract_name_surname_suffix(name_obj)
            contrib_text += surname
            if first_name:
                contrib_text += ", " + first_name
            if suffix:
                contrib_text += ", " + suffix
            if org_name:
                contrib_text += "; " + org_name
        elif org_name:
            contrib_text += org_name
        else:  # Should never happen, if it does it means no name or org_name
            return None

        return contrib_text

    def _set_auths_contribs(self, path, objlist):
        """
        Add the supplied list of author or contributor objects.
        The structure of each author/contributor object is validated, and the values coerced to unicode where necessary.

        ** See authors property below for description of Author/Contributor object.

        :param path: dot notation path
        :param objlist: list of author objects
        :return:
        """
        for obj in objlist:
            self._validate_coerce_auth_contrib(obj)

        # finally write it
        self._set_list(path, objlist)

    def _add_auth_contrib(self, path, auth_obj):
        """
        Add a single author object to the existing list of author objects.

        ** See authors property below for description of Author/Contributor object.

        :param path: dot notation path
        :param auth_obj: author object to add
        :return:
        """
        self._add_to_list(path, self._validate_coerce_auth_contrib(auth_obj), unique=True)

    @property
    def authors(self):
        """
        The list of author objects for the work represented by this metadata.  The returned objects look like:
        ::
            {
                "type" : "<Type of contribution author>",
                "name" : {
                    "firstname" : "<author first name>",
                    "surname" : "<author surname>",
                    "fullname" : "<author name>",
                    "suffix" : "<Qualifiers that follow a persons name Sr. Jr. III, 3rd>"
                },
                "organisation_name" : "<Name of organisation if author is an organisation >",
                "identifier" : [{
                        "type" : "orcid",
                        "id" : "<author's orcid>"
                    }, {
                        "type" : "email",
                        "id" : "<author's email address>"
                    }],
                "affiliations": [ {
                        "identifier" : [{
                            "type" : "ISNI",
                            "id" : "<institution ISNI Id>"
                        }, {
                            "type" : "ROR",
                            "id" : "<institution ROR Id>"
                        }],
                        "org": "<Organisation name> or field absent (*)",
                        "dept": "<Org division/dept> or field absent (*)",
                        "street": "<Street> or field absent",
                        "city": "<City> or field absent",
                        "state": "<State> or field absent",
                        "postcode": "<Post code> or field absent",
                        "country": "<Country> or field absent",
                        "country_code": "<Country code> or field absent",
                        "raw": "<Unstructured affilation> or absent"
                    ] }
            }

        :return: List of python dict objects containing the author information
        """
        return self._get_list("metadata.author")

    @authors.setter
    def authors(self, objlist):
        """
        Set the supplied list of author objects as the authors for this work.
        The structure of each author object will be validated, and the values coerced to unicode where necessary.

        ** See authors property above for description of Author/Contributor object.

        :param objlist: list of author objects
        :return:
        """
        self._set_auths_contribs("metadata.author", objlist)

    def add_author(self, auth_dict):
        """
        Add a single author object to the existing list of author objects.

        ** See authors property above for description of Author/Contributor object.

        :param auth_dict: author object to add
        :return:
        """
        self._add_auth_contrib("metadata.author", auth_dict)

    ##
    # CONTRIBUTOR
    ##

    @property
    def contributors(self):
        """
        The list of contributor objects for the work represented by this metadata.  The returned objects look like:
        ::
            {
                "type" : "<Type of contribution author>",
                "name" : {
                    "firstname" : "<contributor first name>",
                    "surname" : "<contributor surname>",
                    "fullname" : "<contributor name>",
                    "suffix" : "<Qualifiers that follow a persons name Sr. Jr. III, 3rd>"
                },
                "organisation_name" : "<Name of organisation if contributor is an organisation >",
                "identifier" : [{
                        "type" : "orcid",
                        "id" : "<contributor's orcid>"
                    }, {
                        "type" : "email",
                        "id" : "<contributor's email address>"
                    }],
                "affiliations": [ {
                        "identifier" : [{
                            "type" : "ISNI",
                            "id" : "<institution ISNI Id>"
                        }, {
                            "type" : "ROR",
                            "id" : "<institution ROR Id>"
                        }],
                        "org": "<Organisation name> or field absent (*)",
                        "dept": "<Org division/dept> or field absent (*)",
                        "street": "<Street> or field absent",
                        "city": "<City> or field absent",
                        "state": "<State> or field absent",
                        "postcode": "<Post code> or field absent",
                        "country": "<Country> or field absent",
                        "country_code": "<Country code> or field absent",
                        "raw": "<Unstructured affilation> or absent"
                    ] }
            }

        :return: List of python dict objects containing the contributor information
        """
        return self._get_list("metadata.contributor")

    @contributors.setter
    def contributors(self, objlist):
        """
        Set the supplied list of contributor objects as the contributors for this work.

        The structure of each contributor object will be validated, and the values coerced to unicode where necessary.

        ** See contributors property above for description of Author/Contributor object.

        :param objlist: list of contributor objects
        :return:
        """
        self._set_auths_contribs("metadata.contributor", objlist)

    def add_contributor(self, contributor_object):
        """
        Add a single contributor object to the existing list of contributor objects.

        ** See contributors property above for description of Author/Contributor object.

        :param contributor_object: contributor object to add
        :return:
        """
        self._add_auth_contrib("metadata.contributor", contributor_object)

    def add_affiliation_email_identifiers(self):
        """
        For all authors and contributors, if an individual doesn't yet have any email identifier, then extract any
        emails that may exist in their affiliation string.

        However, there is additional complexity, because sometimes the same email address appears erroneously in
        multiple affiliation strings (for different authors). Accordingly, an email extracted from an affiliation is
        only added to an individual (author/contributor) if it is unique across all affiliations.  An email address
        appearing in multiple affiliations will be ignored.

        Hence two processing loops are needed: the first loop finds which individuals potentially have
        affiliation email(s) to add as their email identifier(s). However, until all individuals have been processed
        it can't be confirmed whether the potential email is unique or not, hence the second loop at which time
        the duplicates ("bad_email_set") are known and are removed.
        """

        # List of contributors to update after first pass
        contributors_to_update = []

        # Set of only unique emails
        unique_email_set = set()

        # Set of emails that appear more than once
        bad_email_set = set()

        # get a list of both author and contributors
        for contrib in self.authors + self.contributors:

            # Check to see if an existing email identifier exists
            no_email_id = True
            for ident in contrib.get("identifier", []):
                if ident.get("type") == "email":
                    no_email_id = False
                    break

            # Search the contributor's affiliation for email(s)
            emails_to_add_for_contrib = set()
            for aff_dict in contrib.get("affiliations", []):
                # Search the contributor's affiliation for email(s)
                aff = aff_dict.get("raw", "")
                # only run a regex query if there is an @ symbol in the affiliation text (more efficient)
                if "@" in aff:
                    # find all emails within the affiliation field of the contributor's data
                    emails = match_emails_regex.findall(aff)
                    if emails:
                        # Convert all found emails to lower-case and remove duplicates by creating a set
                        for email in set([email.lower() for email in emails]):
                            if email not in unique_email_set:
                                # If contrib doesn't already have an email ID, then add this potentially unique email
                                # to the set for processing in the second pass
                                if no_email_id:
                                    emails_to_add_for_contrib.add(email)
                                # Add this email to unique set so we can tell if it occurs again
                                unique_email_set.add(email)
                            else:
                                # Email was previously seen, so is not unique - add to the set to be excluded in 2nd pass
                                bad_email_set.add(email)

            # If this contrib doesn't already have an email ID, create tuple of contrib and the emails to add
            if emails_to_add_for_contrib:
                contributors_to_update.append((contrib, emails_to_add_for_contrib))

        # Second loop: for all contributors_to_update, add email identifiers as long as the emails are unique
        for contrib, emails_to_add_for_contrib in contributors_to_update:
            identifiers = contrib.get("identifier", [])
            # Subtract all bad emails from list of potential emails, leaving a set of unique emails to add
            for email in emails_to_add_for_contrib - bad_email_set:
                identifiers.append({"type": "email", "id": email})

            contrib["identifier"] = identifiers

    ##
    # PUB STATUS
    ##

    @property
    def publication_status(self):
        """
        The publication_status ., as a string

        :return: The publication_status string
        """
        return self._get_single("metadata.publication_status")

    @publication_status.setter
    def publication_status(self, val):
        """
        Set the publication status.
        :param val: <publication status value>
        """
        self._set_single("metadata.publication_status", val)

    ##
    # DATES
    ##

    @property
    def publication_date(self):
        """
        The publication date dictionary object.

        :return: The publication dictionary object:
                        {
                        "publication_format" : "<Format of publication (print, electronic)>",
                        "date" : "<date>", /* yyyy-mm-dd format*/
                        "year" : "year":"<year>", /* yyyy format */
                        "month" : "month":"<month>", /* mm format */
                        "day" : "day":"<day>", /* dd format */
                        "season" : "<Season of publication (for example, Spring, Third Quarter).>"
                        }
        """
        return self._get_single("metadata.publication_date")

    @publication_date.setter
    def publication_date(self, date_dict):
        """
        Add a single Publication date object.

        Publication date dict should be of the form:
        ::
        "publication_date" : {
            "publication_format" : "<Format of publication (print, electronic)>",
            "date" : "<date>", /* yyyy-mm-dd format*/
            "year" : "year":"<year>", /* yyyy format */
            "month" : "month":"<month>", /* mm format */
            "day" : "day":"<day>", /* dd format */
            "season" : "<Season of publication (for example, Spring, Third Quarter).>"
        }

        :param date_dict: Publication date dict to add
        :return:
        """
        self._set_single("metadata.publication_date", date_dict)

    def get_publication_date_string(self, return_season=False):
        """
        The publication date., as a string

        May be any of these forms:
            YYYY
            YYYY-MM
            YYYY-MM-DD

        :return: The publication date string
        """

        pub_date_obj = self._get_single("metadata.publication_date")
        if not pub_date_obj:
            return None

        date = pub_date_obj.get("date", "")
        if date:
            return TO_YYYY_MM_DD(date)

        # If got this far then haven't got a whole date
        year = pub_date_obj.get("year")
        if not year:
            return None

        full_date = year

        month = pub_date_obj.get("month")
        if month:
            full_date += "-" + month

        if return_season:
            season = pub_date_obj.get("season")
            if season:
                full_date = season + " " + full_date

        return full_date

    def set_publication_date_format(self, date=None, pub_format=None, year=None, month=None, day=None, season=None):
        """
        Create a publication date., as a string.
        Then, create publication_date object with this date.
        Also, set publication_status to 'Published'.
        It will attempt to coerce to the correct ISO form
            (YYYY-MM-DD) but will accept the value even if the coerce fails.

        :param date: the publication date, ideally in the form YYYY-MM-DD, or a similar form
        :param pub_format: <Format of publication (print, electronic)>
        :param year: Year value
        :param month: Month value
        :param day: Day value
        :param season: <Season of publication (for example, Spring, Third Quarter).>
        """

        if not year and not date:
            return

        obj = {}
        if year:
            obj["year"] = str(year)
        if month:
            if not month.isdigit():
                month = dates.month_string_to_number(month)
            obj["month"] = str(month)
        if day:
            obj["day"] = str(day)

        # Build the date if date is empty but year, month and day are received
        # We know we have a year, because of first test above `if not year and not date: return`
        if not date and month and day:
            date = f"{year}-{month}-{day}"
        if date:
            obj["date"] = self._coerce(date, TO_YYYY_MM_DD, "publication_date")

        if pub_format:
            obj["publication_format"] = pub_format
        if season:
            obj["season"] = season

        self._set_single("metadata.publication_date", obj)
        self._set_single("metadata.publication_status", "Published")

    @property
    def accepted_date(self):
        """
        The accepted-for-publication dateof the work represented by this metadata,
        as a string, of the form YYYY-MM-DD

        :return: The accepted date
        """
        return self._get_single("metadata.accepted_date")   # , coerce=TO_YYYY_MM_DD)

    @accepted_date.setter
    def accepted_date(self, val):
        """
        Set the accepted-for-publication date., as a string.
        It will attempt to coerce to the correct ISO form (YYYY-MM-DD).

        :param val: the accepted date, ideally in the form YYYY-MM-DD, or a similar form that can be read
        """
        self._set_single("metadata.accepted_date", val, coerce=TO_YYYY_MM_DD, allow_none=True, ignore_none=False)
        if self.publication_status is None:
            self._set_single("metadata.publication_status", "Accepted")

    @property
    def peer_reviewed(self):
        """
        Article has been peer-reviewed.

        :return: Boolean - peer reviewed
        """
        return self._get_single("metadata.peer_reviewed", coerce=dataobj.to_bool)

    @peer_reviewed.setter
    def peer_reviewed(self, val):
        """
        Article has been peer-reviewed

        :param val: Boolean - peer reviewed
        """
        self._set_single("metadata.peer_reviewed", val, coerce=dataobj.to_bool, ignore_none=True)

    @property
    def ack(self):
        """
        Acknowledgements.

        :return: String
        """
        return self._get_single("metadata.ack")

    @ack.setter
    def ack(self, val):
        """
        Acknowledgements.

        :param val: String - acknowledgements
        """
        self._set_single("metadata.ack", val, ignore_none=True)

    @property
    def history_date(self):
        """
        The list of dates objects for the work represented by this metadata.  The returned objects look like:
        ::
             {
                "date_type": <description of date type>,
                "date": any of "YYYY-MM-DD", "YYYY-MM" or "YYYY"
            }
        :return: List of python dict objects containing the dates information SORTED by date
        """
        return sorted(self._get_list("metadata.history_date"), key=lambda x: x['date'])

    def _validate_coerce_history_date(self, date_dict):
        """
        :param date_dict: structure like:
                {
                "date_type": <description of date type>,
                "date": any of "YYYY-MM-DD", "YYYY-MM" or "YYYY"
                }
        :return: Object {"date": ..., "date_type": ...}
        """
        return self._validate_coerce_dates_unicode(date_dict, ['date'], ['date_type'], coerce_to_ymd, 'History date')

    def set_history_date_list(self, objlist):
        """
        Set the supplied list of dates objects as the contributors for this work.
        The structure of each date object will be validated, and the values coerced to unicode where necessary.
        Date objects should be of the form:
        ::
            {
                "date_type": <description of date type>,
                "date": any of "YYYY-MM-DD", "YYYY-MM" or "YYYY"
            }
        :param objlist: list of dates objects
        :return:
        """
        for obj in objlist:
            self._validate_coerce_history_date(obj)

        self._set_list("metadata.history_date", objlist)

    def add_history_date_obj(self, date_object):
        """
        Add a single date object to the existing list of history_dates.
        date objects should be of the form:
        ::
            {
                "date_type": <description of date type>,
                "date": any of "YYYY-MM-DD", "YYYY-MM" or "YYYY"
            }
        :param date_object: date object to add
        :return:
        """
        # self._delete_from_list("metadata.history_date", matchsub=date_object)
        self._add_to_list("metadata.history_date", self._validate_coerce_history_date(date_object), unique=True)


    def add_history_date(self, date_type, full_date):
        """
        Add a single history date to the existing list of history_dates. (No validation is done on params).
        :param date_type: string - type of date
        :param full_date: string - Date with format "YYYY-MM-DD"
        :return:
        """

        self.add_history_date_obj({"date_type": date_type, "date": full_date})


    ##
    # FUNDING
    ##

    @property
    def funding(self):
        """
        The list of project/funder objects for the work represented by this metadata of format
            "funding" : [{
                    "name" : "<name of funder>",
                    "identifier" : [{
                            "type" : "<identifier type>",
                            "id" : "<funder identifier>"
                        }
                    ],
                    "grant_numbers" : ["<list of funder's grant numbers>"]
                }
            ],
        """
        return self._get_list("metadata.funding")

    @funding.setter
    def funding(self, objlist):

        # validate all objects first
        for obj in objlist:
            self._validate_coerce_funding_object(obj)
        # now set the list
        self._set_list("metadata.funding", objlist)

    ##
    # LICENSES
    ##

    @property
    def licenses(self):
        """
        Get sorted list of licenses.
        [{
            "title" : "<name of licence><string>",
            "type" : "<type of license, example cc-by><string>",
            "url" : "<url of license><string>",
            "version" : "<version of license; for example: 4.0><string>",
            "start" : "<Date licence starts><date>"    
        }]
        """
        # Return list sorted by start date. Dicts without a 'start' are returned at beginning of list
        return sorted(self._get_list("metadata.license_ref"), key=lambda k: k.get("start", ""))

    @licenses.setter
    def licenses(self, objlist):
        # validates and sets a license list
        self._set_list("metadata.license_ref", objlist)

    def add_license(self, obj):
        """
        Add the supplied licence object to the license list.

        The object will be validated and types coerced as needed.

        The supplied object should be structured as follows:

        ::
            {
                "title" : {"coerce" : "unicode"},
                "type" : {"coerce" : "unicode"},
                "url" : {"coerce" : "unicode"},
                "version" : {"coerce" : "unicode"},
                "start" : {"coerce" : "unicode"}
            }

        :param obj: the licence object as a dict
        """
        self._validate_coerce_dates_unicode(obj, ["start"], ["title", "type", "url", "version"], TO_YYYY_MM_DD, 'License')
        self._add_to_list("metadata.license_ref", obj, unique=True)

    def set_license(self, url="", type="", title="", version="", start=""):
        """
        Construct a license object using supplied details and ADD to license list.

        :param url: the url where more information about the licence can be found
        :param type: the name/type of the licence (e.g. CC-BY)
        :param title: title of the licence
        :param version: version of the licence
        :param start: the start of the licence
        """
        obj = {}
        if url:
            obj["url"] = url
        if type:
            obj["type"] = type
        if title:
            obj["title"] = title
        if version:
            obj["version"] = str(version)
        if start:
            obj["start"] = self._coerce(start, TO_YYYY_MM_DD, "licence-start")

        if obj:
            self._add_to_list("metadata.license_ref", obj, unique=True)

    ##
    # EMBARGO
    ##

    @property
    def embargo(self):
        """
        The embargo information for the work represented by this metadata

        The returned object is as follows:

        ::
            {
                "start": {"coerce": "unicode"},
                "end": {"coerce": "unicode"},
                "duration": {"coerce": "unicode"}
            }

        :return: The embargo information as a python dict object
        """
        return self._get_single("metadata.embargo")

    @embargo.setter
    def embargo(self, obj):
        """
        Set the embargo object

        The object will be validated and types coerced as needed.

        The supplied object should be structured as follows:

        ::
            {
                "start": {"coerce": "unicode"},
                "end": {"coerce": "unicode"},
                "duration": {"coerce": "unicode"}
            }

        :param obj: the embargo object as a dict
        :return:
        """

        self._validate_coerce_dates_unicode(obj, ["start", "end"], ["duration"], TO_YYYY_MM_DD, 'Embargo')
        self._set_single("metadata.embargo", obj)

    def set_embargo(self, start=None, end=None, duration=None):
        """
        Set the embargo with the supplied params.

        :param start: date start embargo
        :param end: date end embargo
        :param duration: embargo duration in days
        :return:
        """
        obj = {}
        if start:
            obj["start"] = self._coerce(start, TO_YYYY_MM_DD, "embargo-start")
        if end:
            obj["end"] = self._coerce(end, TO_YYYY_MM_DD, "embargo-end")
        if duration:
            obj["duration"] = str(duration)

        if obj:
            self._set_single("metadata.embargo", obj)

    @property
    def embargo_start(self):
        return self._get_single("metadata.embargo.start")  # , TO_YYYY_MM_DD)

    @property
    def embargo_end(self):
        return self._get_single("metadata.embargo.end")  # , TO_YYYY_MM_DD)

    @property
    def embargo_duration(self):
        return self._get_single("metadata.embargo.duration", TO_UNICODE)


class ProviderMetadata(dataobj.DataObj):
    """
    Class to provide basic provider information.
    """
    def __init__(self, raw=None, **kwargs):
        """
        Create a new instance of the ProviderMetadata:

        "provider":{
            "id":"<The Publisher account Id associated with source of Notification>",
            "agent":"<Was originally meant to store API client used to create notification, but now stores either the
                        harvester name or the publisher org name>",
            "harv_id":"<Used for HARVESTER clients only - records the Webservice ID",
            "route":"<Method by which notification was received: native 'api', 'sword', 'ftp', 'harv'>",
            "rank": "<The provider's level of importance: 1, 2, 3 - High (from Publisher), Medium, Low>"
        }

        In reality, this class provides a base-class for other notification-like objects
        in this module, so you will never instantiate it directly.

        If supplied, the raw dictionary will be validated against the allowed structure of this
        object, and an exception will be raised if it does not validate

        :param raw: python dict object containing the base notification data
        """

        struct = {
            "objects": [
                "provider"
            ],
            "structs": {
                "provider": {
                    "fields": {
                        "id": {"coerce": "integer"},
                        "agent": {"coerce": "unicode"},
                        "harv_id": {"coerce": "integer"},
                        "ref": {"coerce": "unicode"},   # ZZZ Remove in future (v5) release of API
                        "route": {"coerce": "unicode"},
                        "rank": {"coerce": "integer"}
                    },
                    "required": []
                }
            }
        }

        self._add_struct(struct)
        super(ProviderMetadata, self).__init__(raw, **kwargs)

    @property
    def provider_id(self):
        """
        The id of the provider of this notification, which is the account ID value
        (e.g. 1cba2051d45a4e17bd0884cf78eeb513)

        :return: the provider id/account name
        """
        return self._get_single("provider.id")

    @provider_id.setter
    def provider_id(self, val):
        """
        Set the id of the provider of this notification, which is the account ID value

        :param val: the provider id/account name
        """
        self._set_single("provider.id", val, coerce=TO_INT)

    @property
    def provider_agent(self):
        """
        Originally intended to be the API client used to create the notification, but now used to store Harvester
        name or publisher org name

        :return: the provider agent
        """
        return self._get_single("provider.agent")

    @provider_agent.setter
    def provider_agent(self, val):
        """
        Originally intended to be the API client used to create the notification, but now used to store Harvester
        name or publisher org name

        :param val: the provider agent
        """
        self._set_single("provider.agent", val)

    @property
    def provider_harv_id(self):
        """
        The Webservice record Id for Harvester clients only

        :return: the harvester webservice id
        """
        return self._get_single("provider.harv_id")

    @provider_harv_id.setter
    def provider_harv_id(self, val):
        """
        Set the Webservice Id for Harvester clients only

        :param val: Int - harvester webservice id
        """
        self._set_single("provider.harv_id", val, coerce=TO_INT)

    @property
    def provider_route(self):
        """
        The provider route is the Method by which notification was received: native api, sword, ftp

        :return: the provider route value
        """
        return self._get_single("provider.route")

    @provider_route.setter
    def provider_route(self, val):
        """
        Set the provider route is the Method by which notification was received: native api, sword, ftp

        :param val: the provider route
        """
        self._set_single("provider.route", val)

    @property
    def provider_rank(self):
        """
        The provider rank is the relative importance of the provider - Values: 1, 2, 3. Rank 1 (highest) indicates
        provider is the Publisher.

        :return: the provider rank value
        """
        return self._get_single("provider.rank", coerce=TO_INT)

    @provider_rank.setter
    def provider_rank(self, val):
        """
        The provider rank is the relative importance of the provider - Values: 1, 2, 3. Rank 1 (highest) indicates
        provider is the Publisher.

        :param val: Integer (or string) - the provider rank
        """
        self._set_single("provider.rank", val, coerce=TO_INT)
# END ProviderMetadata class


class BaseNotification(NotificationMetadata, ProviderMetadata):
    """
    Class to provide a baseline for all stored notifications (both routed and unrouted) in the core of the system

    In addition to the properties that it gets from the NotificationMetadata and ProviderMetadata it adds the following:
    {
        "id" : <notification ID>,
        "created": <>,
        "event": <event causing the notification to be generated>,
        "type": <notification type: [routed | unrouted] ,
        "content":
        {
            packaging_format: "<identifier for packaging format used>"
        },
        "links" : [
            {
                "type" : "<link type: splash|fulltext>",
                "format" : "<text/html|application/pdf|application/xml|application/zip|...>",
                "url" : "<provider's splash, fulltext or machine readable page>",
                "access": "<one of ["router"|"public"|"special"]",
                "packaging": "<type of package - if relevant>",
                "proxy": "<the ID of the proxy link - INTERNAL use only>",
                "cloc": "<Content location - used to construct URL to Router stored files - INTERNAL use only>"
            }
        ]
    }


    See the system model documentation for details on the JSON structure used by this model.
    https://github.com/jisc-services/Public-Documentation/blob/master/PublicationsRouter/api/v3/IncomingNotification.md
    It provides the basis for all Notification objects that extend from this one.
    """

    def __init__(self, raw=None, **kwargs):
        """
        Create a new instance of the BaseNotification object, optionally around the raw python dictionary.

        This class provides a base-class for all other notification-like objects in this module, so you
        will never instantiate it directly.  See UnroutedNotification or RoutedNotification instead.

        If supplied, the raw dictionary will be validated against the allowed structure of this
        object, and an exception will be raised if it does not validate

        :param raw: python dict object containing the base notification data
        """
        struct = {
            "fields": {
                "id": {"coerce": "integer"},
                "created": {"coerce": "utcdatetime"},
                "event": {},
                "type": {}       # notification type - e.g. routed "R" or unrouted "U"
            },
            "objects": [
                "content"
            ],
            "lists": {
                "links": {"contains": "object"}
            },
            "required": [],

            "structs": {
                "content": {
                    "fields": {
                        "packaging_format": {}
                    },
                    "required": []
                },
                "links": {
                    "fields": {
                        "type": {},
                        "format": {},
                        "url": {"coerce": "url"},
                        "access": {},
                        "packaging": {},
                        "proxy": {},
                        "cloc": {}
                    }
                }
            }
        }

        self._add_struct(struct)
        super(BaseNotification, self).__init__(raw, **kwargs)
        self.api_note_url_template = current_app.config.get("API_NOTE_URL_TEMPLATE")

    @property
    def id(self):
        return self._get_single("id")

    @id.setter
    def id(self, val):
        self._set_single("id", val, coerce=TO_INT)

    @property
    def type(self):
        return self._get_single("type")

    @type.setter
    def type(self, val):
        self._set_single("type", val)

    @property
    def packaging_format(self):
        """
        Get the packaging format identifier of the associated binary content

        :return: the packaging format identifier
        """
        return self._get_single("content.packaging_format")

    @property
    def links(self):
        """
        Get the list of link objects associated with this notification

        Link objects are of the form
        ::
            {
                "type" : "<link type: splash|fulltext>",
                "format" : "<text/html|application/pdf|application/xml|application/zip|...>",
                "access" : "<type of access control on the resource: 'router' (requires router auth) or 'public' (no auth)>",
                "url" : "<provider's splash, fulltext or machine-readable page>",
                "packaging" : "<packaging format identifier>",
                "proxy": "<the ID of the proxy link>",
                "cloc": "<Content location - used to construct URL to Router stored files - INTERNAL use only>"
            }
        For more information about links, see the overall system documentation

        :return: list of link objects
        """
        return self._get_list("links")

    @links.setter
    def links(self, link_obj_list):
        """
        Add a link object to the current list of links

        :param link_obj_list: link Object
        """
        self._set_list("links", link_obj_list)

    def add_link_dict(self, link_dict):
        """
        Add link dict, which should conform to this structure:
        {
        "format": "",
        "access": "",
        "type": "",
        "packaging": "" [OPTIONAL element, may be absent],

        "cloc": "",
      OR
        "url": "",
        }

        :param link_dict: Dict - see above for structure
        :return:
        """
        ## Comment out the following code, because this function only (indirectly) used under program control, so values
        ## guaranteed to be OK
        # allowed = ["router", "public", "special"]
        # access = link_dict.get("access")
        # if access not in allowed:
        #     raise dataobj.DataSchemaException(f"link access must be one of {allowed}; not '{access}'.")
        self._add_to_list("links", link_dict, unique=True)

    def add_link(self, type, format, access, cloc=None, url=None, packaging=None):
        """
        Add a link object to the current list of links

        :param type: String - The type of resource that link points to (e.g. fulltext or splash etc.)
        :param format: String - The format/mimetype of the resource (e.g. 'text/html' or 'application/pdf' etc.)
        :param access: String - The access level of this link: router or public
        :param cloc: String - Content location (may be empty string: "")
        :param url: String - URL (should NOT be empty)
        :param packaging: String - The packaging format identifier for this resource if required
        """
        obj = {
            "type": type,
            "format": format,
            "access": access
        }
        if cloc is not None:
            obj["cloc"] = cloc
        elif url is not None:
            obj["url"] = url
        else:
            raise ValueError("add_link function requires either `cloc` or `url` parameter to be provided")
        if packaging:
            obj["packaging"] = packaging
        self.add_link_dict(obj)

    def get_package_link(self, packaging):
        if packaging:
            for l in self.links:
                if l.get("type") == "package" and l.get("packaging") == packaging:
                    return l
        return None

    def link_cloc_to_url(self, api_vers, cloc):
        """
        Convert a content location to a URL, based on API version. EXAMPLES:
        * http://pubrouter.jisc.ac.uk/api/v4/notification/14859/content
        * http://pubrouter.jisc.ac.uk/api/v3/notification/123/content/FilesAndJATS.zip

        :param api_vers: String - API version number (e.g. "3" or "4")
        :param cloc: String - Content location string (may be empty: "")
        :return: URL
        """
        base_url = self.api_note_url_template.format(api_vers, self.id) + "/content"
        return f"{base_url}/{cloc}" if cloc else base_url

    @staticmethod
    def _select_best_external_pdf_link(links):
        """
        Find likely best link to an external downloadable PDF file and return link object,
        :param links: List of notification link objects
        :return: a link object pointing to external PDF file or None
        """
        link_pdf = None
        possible_pdf_links = [link for link in links
                              if "application/pdf" == link.get("format") and link.get("access") == "public"]
        # If at least one Public PDF URL is present
        if possible_pdf_links:
            # If more than one, then select link that contains text ".pdf" or "?pdf"
            if len(possible_pdf_links) > 1:
                for link in possible_pdf_links:
                    # Use regex to search for best URL
                    if best_pdf_url.search(link.get("url")):
                        link_pdf = link

            # If link not yet set, then use first in list
            if link_pdf is None:
                link_pdf = possible_pdf_links[0]
        return link_pdf

    def select_best_external_pdf_link(self):
        """
        Find likely best link to an external downloadable PDF file and return link object,
        :return: a link object pointing to external PDF file or None
        """
        return self._select_best_external_pdf_link(self.links)

    @staticmethod
    def aff_dict_to_string(aff_dict):
        """
        Convert v4 affiliation dict to a string.

        :param aff_dict: Affiliation dictionary
        :return: String - Affiliation
        """
        aff_els = []
        for key in ("org", "dept", "street", "city", "state", "postcode", "country"):
            aff_el = aff_dict.get(key)
            if aff_el:
                aff_els.append(aff_el)
        for id_dict in aff_dict.get("identifier", []):
            aff_els.append("{type}: {id}".format(**id_dict))
        return ", ".join(aff_els)

    @staticmethod
    def aff_dict_to_string_for_matching(aff_dict):
        """
        Convert v4 affiliation dict to a string suitable for use by matching algorithm.  (Exclude PostCode &
        Organisation Identifiers).

        :param aff_dict: Affiliation dictionary
        :return: String - Affiliation
        """
        aff_els = []
        for key in ("org", "dept", "street", "city", "state", "country"):
            aff_el = aff_dict.get(key)
            if aff_el:
                aff_els.append(aff_el)
        return ", ".join(aff_els)

    def match_data(self):
        """
        Extract data required for matching algorithm from the notification, and return as a RoutingMetadata object.

        The following data is selected:
            * publication_date
            * author emails
            * author affiliations
            * author orcids
            * postcodes
            * grants
            * organization ids (from structured affiliations)

        RoutingMetadata does NOT include data from contributors.

        :return: a RoutingMetadata object containing data for matching
        """
        def _set_auth_matching_meta(md, authors):
            affiliations = set()
            postcodes = set()
            emails = set()
            orcids = set()
            org_ids = set()

            for author in authors:
                # Extract affiliations from V4 Affiliations
                affs = author.get("affiliations")
                if affs is not None:
                    for aff_dict in affs:
                    # for aff_dict in author.get("affiliations", []):   # ZZZ - KEEP & use this line instead of 3 preceding lines (& left indent entire block)
                        raw_aff = aff_dict.get("raw")
                        if raw_aff:
                            # We have a raw affiliation, so search it for any post-codes
                            postcodes |= set(postcode.extract_all(raw_aff))
                        else:   # We DON'T have a raw affiliation, so create one from dict
                            raw_aff = self.aff_dict_to_string_for_matching(aff_dict)
                            post_code = aff_dict.get("postcode")
                            if post_code:
                                postcodes.add(post_code)
                        affiliations.add(strip_remove_multispace(raw_aff))
                        try:
                            # Convert list of org-identifier dicts to Set of Org-id strings "TYPE:id-value, with spaces removed"
                            org_ids |= {f"{id_dict['type']}:{id_dict['id'].lower().replace(' ', '')}"
                                        for id_dict in aff_dict.get("identifier", [])}
                        except KeyError as e:
                            # An affiliation organisation identifier is missing either 'type' or 'id' attribute
                            # but is ignored as not worth raising an exception that would cause notification to fail
                            pass
                # ZZZ - original V3 code TO BE REMOVED  (Remove all code in Else block)
                else: # Look for V3 affiliation
                    aff = author.get("affiliation")  # Get v3 Affiliation,
                    if aff:
                        affiliations.add(strip_remove_multispace(aff))
                        postcodes |= set(postcode.extract_all(aff))

                # other author ids
                for id in author.get("identifier", []):
                    _type = id.get("type")
                    if _type == "email":
                        emails.add(id.get("id").strip().lower())
                    elif _type == "orcid":
                        orcids.add(id.get("id").strip())
                        
            md.affiliations = affiliations
            md.postcodes = postcodes
            md.emails = emails
            md.orcids = orcids
            md.org_ids = org_ids
            return

        md = RoutingMetadata()

        # Set publication date so it can be used in routing metadata
        pub_date = self.get_publication_date_string()
        if pub_date:
            md.publication_date = pub_date

        # authors, and all their various properties
        _set_auth_matching_meta(md, self.authors)

        # grants
        grant_nums = set()
        for funding in self.funding:
            grant_nums |= {strip_remove_multispace(grant) for grant in funding.get("grant_numbers", [])}
        md.grants = grant_nums

        return md

    def _set_best_license_flag(self, note_dict):
        """
        Sets the 'best' license boolean flag on the list of licenses in the notification metadata.

            For a list of licenses ordered by start date (no start date comes first) - identifies the "best" license.
            Priority is as follows:
            OPEN licence with the latest (most recent) start_date in the past (or today)
            ELSE
            OPEN licence with NO start_date (the first one found, if more than one)
            ELSE
            OPEN licence with the earliest start_date in the future
            ELSE
            Other licence with the latest (most recent) start_date in the past (or today)
            ELSE
            Other licence with NO start_date (the first one found, if more than one)
            ELSE
            Other licence with the earliest start_date in the future

        Just one license will have "best" flag set to True, except where there is more than one license and
        none has a URL in which case all of the "best" flags will be False.

        :param note_dict: Notification dict (which is MODIFIED by this function)
        :return: Nothing
        """

        today = datetime.today().strftime("%Y-%m-%d")

        best_license_ix = None
        is_best_license_open = False
        # Sort licenses by start date
        licenses = sorted(note_dict["metadata"].get("license_ref", []), key=lambda k: k.get("start", ""))
        for (index, license) in enumerate(licenses):
            # All licenses are initialised with best flag set False
            license["best"] = False

            url = license.get("url")
            # if the license has no URL then ignore it
            if not url:
                continue
            is_license_open = self.is_open_license(lic_url=url)
            # if our best license is open
            if is_best_license_open:
                # but this license is not
                if not is_license_open:
                    continue
            # if our current best license is not open and this license is open, then take this license and
            # continue the loop
            elif is_license_open:
                best_license_ix = index
                is_best_license_open = True
                continue

            # if we haven't already found a license, then this is currently our best
            if best_license_ix is None:
                best_license_ix = index
                is_best_license_open = is_license_open
            else:
                license_start = license.get("start")
                # if this license is in the past, then so is the current best_license (as the licenses are ordered by
                # start date). This license has a later start date than current best_license using same argument,
                # so take this license as the best license.
                if license_start and license_start <= today:
                    best_license_ix = index
                    is_best_license_open = is_license_open

        # If we have just one licence without a URL, that one is best
        if best_license_ix is None and len(licenses) == 1:
            best_license_ix = 0

        # If we have identified a best license, so set it's indicator
        if best_license_ix is not None:
            licenses[best_license_ix]["best"] = True

    def make_outgoing(self, api_vers=None):
        """
        Create an instance of an OutgoingNotification from this object.

        :param api_vers: String - API version

        :return: OutgoingNotification
        """
        def delete_dict_fields(_dict, fields):
            """
            Attempt to delete elements from dict, ignore KeyError (field not in dict)
            """
            for _field in fields:
                try:
                    del _dict[_field]
                except KeyError:
                    pass

        app_config = current_app.config     # We use for efficiency this because current_app is a proxy
        note_dict = deepcopy(self.data)
        # Obtain & remove the vers field (may be absent for old versions of notification)
        note_vers = note_dict.pop("vers", None)
        note_is_latest_vers = note_vers == app_config["API_VERSION"]

        # Remove 'type', 'repositories', 'metrics', 'category' & 'has_pdf' attributes
        delete_dict_fields(note_dict, ("type", "repositories", "metrics", "category", "has_pdf"))

        metadata = note_dict.get("metadata", {})
        article = metadata.get("article", {})
        delete_dict_fields(article, ("doi"))    # remove metadata.article.doi field (the doi is also in identifier list)

        # ZZZ - REMOVE entire if ... else ... block When API v3 is no longer supported then UNCOMMENT the block below it
        if api_vers == app_config["OLD_API_VERSION"]:
            # Change created to created_date    # ZZZ - API v3
            note_dict["created_date"] = note_dict.pop("created", None)  # ZZZ - API v3

            # Need to convert v4 note to v3 note
            if note_is_latest_vers:
                # Delete v4 fields: 'peer_reviewed', 'ack', 'article.e_num'
                delete_dict_fields(metadata, ("peer_reviewed", "ack"))
                e_num = article.pop("e_num", None)

                # If e_num is present & no page_range then assign that to page_range
                if e_num and not article.get("page_range"):
                    article["page_range"] = e_num

                # For each author & contributor convert `affiliations` list of dicts into `affiliation` string.
                for field in ("author", "contributor"):
                    for auth_cont in metadata.get(field, []):
                        affs = auth_cont.pop("affiliations", None)
                        if affs:
                            v3_aff_list = [aff.get("raw") or self.aff_dict_to_string(aff) for aff in affs]
                            auth_cont["affiliation"] = "; ".join(v3_aff_list)

        else:   # Latest API version
            if api_vers is None:
                # Set for later use in setting link urls
                api_vers = app_config["API_VERSION"]
            if note_is_latest_vers:
                # For all author and contributor affiliation dicts, set the "raw" value to be concatenated String
                for field in ("author", "contributor"):
                    for auth_cont in metadata.get(field, []):
                        for aff in auth_cont.get("affiliations", []):
                            if not aff.get("raw"):
                                aff["raw"] = self.aff_dict_to_string(aff)
            else:   # We are processing old version of notification
                # Convert `affiliation` string to `affiliations` list of dict
                for field in ("author", "contributor"):
                    for auth_cont in metadata.get(field, []):
                        aff = auth_cont.pop("affiliation", None)
                        if aff:
                            # Save old-style affiliation as the "raw" field
                            auth_cont["affiliations"] = [{"raw": aff}]

        # ZZZ - UNCOMMENT following code when API v3 is no longer supported (after removing preceding if/else block).
        # # For all author and contributor affiliation dicts, set the "raw" value to be concatenated String
        # for field in ("author", "contributor"):
        #     auth_cont_list = metadata.get(field, [])
        #     for auth_cont in auth_cont_list:
        #         for aff in auth_cont.get("affiliations", []):
        #             if not aff.get("raw"):
        #                 aff["raw"] = self.aff_dict_to_string(aff)


        # Determine which (if any) of attached licenses is best, set boolean flag for each license in the notification.
        self._set_best_license_flag(note_dict)

        # Remove information that is restricted to the Provider of the original notification
        provider = note_dict.get("provider")
        if provider:
            keys_to_delete = list(provider.keys())
            try:
                keys_to_delete.remove("agent")   # Remove "agent", which we DON'T want to delete
            except ValueError:
                pass
            delete_dict_fields(provider, keys_to_delete)

        # Adjust links
        for link in note_dict.get("links", []):
            # Remove any proxy link (these are URLs to content on a provider's system which are to be kept hidden
            proxy = link.pop("proxy", None)
            if proxy is None:   # Not a proxy: will be a Router stored content link or public file link
                # Convert content location, if there is one, to URL.  if there isn't one then URL will already exist
                # As "cloc" is more likely than "url", it is done this way rather than first testing for "url"
                try:
                    cloc = link.pop("cloc")     # Never return "cloc" in outgoing notification
                    link["url"] = self.link_cloc_to_url(api_vers, cloc)
                except KeyError:
                    pass

        # Adjust Funding identifiers - if ID is not a URI, then convert to one if possible
        id_type_to_uri_dict = None
        for proj in metadata.get("funding", []):
            for id_dict in proj.get('identifier', []):
                id = id_dict.get("id")
                # ID is not a URI
                if id and not id.startswith("http"):
                    # For efficiency, only initialise `id_type_to_uri_dict` the first time it is needed
                    if id_type_to_uri_dict is None:
                        id_type_to_uri_dict = app_config["ID_TYPE_TO_URI"]
                    # Retrieve prefix URI corresponding to the id-type from ID_TYPE_TO_URI dict
                    try:
                        http_domain, starts_with = id_type_to_uri_dict[id_dict.get("type").lower()]
                    except KeyError:
                        pass
                    else:
                        if starts_with and not id.startswith(starts_with):
                            id_dict["id"] = http_domain + starts_with + id
                        else:
                            id_dict["id"] = http_domain + id


        return OutgoingNotification(note_dict, api_vers=api_vers)
# END BaseNotification class


class RoutingInformation(dataobj.DataObj):
    """
    Class which provides some additional data to any notification regarding the routing status

    Any class which extends from this will get the following information added to its datastructure:

        {
            "analysis_date" : "<date the routing analysis was carried out>",
            "repositories" : ["<ids of repository user accounts which match this notification>"]
            # dup_diffs is a list with between 0 and 2 elements.  If the notification is the 1st duplicate there will
            # be 1 element (difference between current an original notification); for 2nd duplicate onwards, there will
            # be 2 elements [0] will be diff between current and original; [1] will be diff between current and last
            "dup_diffs" : [{
                "old_date": String - Timestamp of older notification,
                "curr_bits": Bitfield - Newer bitfield
                "old_bits": Bitfield - Older bitfield
                "n_auth": Positive or negative number - change in number of authors,
                "n_orcid": Positive or negative number - change in number of authors with ORCIDs,
                "n_fund": Positive or negative number - change in number of fundings,
                "n_fund_id": Positive or negative number - change in number of funding IDs,
                "n_grant": Positive or negative number - change in number of grants,
                "n_lic": Positive or negative number - change in number of licences,
                "n_struct_aff": Positive or negative number - change in number of structured author affiliations,
                "n_aff_ids": Positive or negative number - change in number of structured author affiliations with Org Ids,
                "n_cont": Positive or negative number - change in number of non-author contributors,
                "n_hist": Positive or negative number - change in number of history dates,
            }],
            "metrics": {
                "p_count": Integer - number of times notification with this DOI has been sent by Publisher to date
                "h_count": Integer - number of times notification with this DOI has been harvested to date
                "val": {
                    "bit_field": Bitfield - Indicating presence of particular Metadata fields/values.
                    "n_auth": Number of authors,
                    "n_orcid": Number of authors with ORCIDs,
                    "n_fund": Number of funders,
                    "n_fund_id": Number of funder IDs,
                    "n_grant": Number of grants,
                    "n_lic": Number of licences,
                    "n_struct_aff": Number of structured author affiliations,
                    "n_aff_ids": Number of structured author affiliations with Org Ids,
                    "n_cont": Number of non-author contributors,
                    "n_hist": Number of history dates
                }
            }
        }
    """
    def __init__(self, raw=None, **kwargs):
        """
        Create a new instance of the RoutingInformation object, optionally around the raw python dictionary.

        In reality, this class provides a data extension for other notification-like objects
        in this module, so you will never instantiate it directly.  See RoutedNotification instead.

        If supplied, the raw dictionary will be validated against the allowed structure of this
        object, and an exception will be raised if it does not validate

        :param raw: python dict object containing the notification data
        """
        struct = {
            "fields": {
                "analysis_date": {"coerce": "utcdatetime"}
            },
            "lists": {
                "repositories": {"contains": "field", "coerce": "integer"},
                "dup_diffs": {"contains": "object"}
            },
            "objects": [
                "metrics"
            ],
            "structs": {
                "dup_diffs": {
                    "fields": {
                        "old_date": {"coerce": "utcdatetime"},
                        "old_bits": {"coerce": "integer"},
                        "curr_bits": {"coerce": "integer"},
                        "n_auth": {"coerce": "integer"},
                        "n_orcid": {"coerce": "integer"},
                        "n_fund": {"coerce": "integer"},
                        "n_fund_id": {"coerce": "integer"},
                        "n_grant": {"coerce": "integer"},
                        "n_lic": {"coerce": "integer"},
                        "n_struct_aff": {"coerce": "integer"},
                        "n_aff_ids": {"coerce": "integer"},
                        "n_cont": {"coerce": "integer"},
                        "n_hist": {"coerce": "integer"}
                    }
                },
                "metrics": {
                    "fields": {
                        "p_count": {"coerce": "integer"},
                        "h_count": {"coerce": "integer"},
                    },
                    "objects": [
                        "val"
                    ],
                    "structs": {
                        "val": {
                            "fields": {
                                "bit_field": {"coerce": "integer"},
                                "n_auth": {"coerce": "integer"},
                                "n_orcid": {"coerce": "integer"},
                                "n_fund": {"coerce": "integer"},
                                "n_fund_id": {"coerce": "integer"},
                                "n_grant": {"coerce": "integer"},
                                "n_lic": {"coerce": "integer"},
                                "n_struct_aff": {"coerce": "integer"},
                                "n_aff_ids": {"coerce": "integer"},
                                "n_cont": {"coerce": "integer"},
                                "n_hist": {"coerce": "integer"}
                            }
                        }
                    }
                }
            }
        }

        self._add_struct(struct)
        super(RoutingInformation, self).__init__(raw, **kwargs)

    @property
    def analysis_date(self):
        """
        The date this notification was analysed for routing, as a string of the form YYYY-MM-DDTHH:MM:SSZ

        :return: the analysis date
        """
        return self._get_single("analysis_date")

    @analysis_date.setter
    def analysis_date(self, val):
        """
        Set the date this notification was analysed for routing, as a string of the form YYYY-MM-DDTHH:MM:SSZ

        :param val: the analysis date
        """
        self._set_single("analysis_date", val, coerce=dataobj.date_str())

    @property
    def analysis_datestamp(self):
        """
        The date this notification was analysed for routing, as a datetime object

        :return: the analysis date
        """
        return self._get_single("analysis_date", coerce=dataobj.to_datetime_obj())

    @property
    def repositories(self):
        """
        List of repository ids to which this notification was routed

        :return: the list of repository ids
        """
        return self._get_list("repositories")

    @repositories.setter
    def repositories(self, val):
        """
        Set the list of repository ids to which this notification was routed

        :param val: the list of repository ids
        """
        self._set_list("repositories", val)


    @property
    def dup_diffs(self):
        """
        List of Dict of duplicate difference information
        [{
            "old_date": String - Timestamp of older notification,
            "curr_bits": Bitfield - Newer bitfield
            "old_bits": Bitfield - Older bitfield
            "n_auth": Positive or negative number - change in number of authors,
            "n_orcid": Positive or negative number - change in number of authors with Orcids,
            "n_fund": Positive or negative number - change in number of fundings,
            "n_fund_id": Positive or negative number - change in number of funding IDs,
            "n_grant": Positive or negative number - change in number of grants,
            "n_lic": Positive or negative number - change in number of licences,
            "n_struct_aff": Positive or negative number - change in number of structured author affiliations,
            "n_aff_ids": Positive or negative number - change in number of structured author affiliations with Org Ids,
            "n_cont": Positive or negative number - change in number of non-author contributors,
            "n_hist": Positive or negative number - change in number of history dates,
        }]

        :return: Dict
        """
        return self._get_list("dup_diffs")


    @dup_diffs.setter
    def dup_diffs(self, objlist):
        """
        Set dict of duplicate difference information

        :param objlist: List of Dict -
        [{
            "old_date": String - Timestamp of older notification,
            "curr_bits": Bitfield - Newer bitfield
            "old_bits": Bitfield - Older bitfield
            "n_auth": Positive or negative number - change in number of authors,
            "n_orcid": Positive or negative number - change in number of authors with Orcids,
            "n_fund": Positive or negative number - change in number of fundings,
            "n_fund_id": Positive or negative number - change in number of funding IDs,
            "n_grant": Positive or negative number - change in number of grants,
            "n_lic": Positive or negative number - change in number of licences,
            "n_struct_aff": Positive or negative number - change in number of structured author affiliations,
            "n_aff_ids": Positive or negative number - change in number of structured author affiliations with Org Ids,
            "n_cont": Positive or negative number - change in number of non-author contributors,
            "n_hist": Positive or negative number - change in number of history dates,
        }]
        """
        self._set_list("dup_diffs", objlist)


    def is_duplicate(self):
        """
        Determine if this notification is a duplicate
        :return:
        """
        return len(self.dup_diffs) > 0


    @property
    def metrics(self):
        """
        Metrics dict
        {
            "p_count": Integer - number of times notification with this DOI has been sent by Publisher to date
            "h_count": Integer - number of times notification with this DOI has been harvested to date
            "val": {
                "bit_field": Bitfield - Indicating presence of particular Metadata fields/values.
                "n_auth": Number of authors,
                "n_orcid": Number of authors with Orcids,
                "n_fund": Number of funders,
                "n_fund_id": PNumber of funder IDs,
                "n_grant": Number of grants,
                "n_lic": Number of licences,
                "n_struct_aff": Number of structured author affiliations,
                "n_aff_ids": Number of structured author affiliations with Org Ids,
                "n_cont": Number of non-author contributors,
                "n_hist": Number of history dates
            }
    }
        :return: Dict
        """
        return self._get_single("metrics")


    @metrics.setter
    def metrics(self, metrics_dict):
        """
        Set dict containing notification metrics (assuming metrics_dict not None or empty).

        :param metrics_dict:
        {
            "p_count": Integer - number of times notification with this DOI has been sent by Publisher to date
            "h_count": Integer - number of times notification with this DOI has been harvested to date
            "val": {
                "bit_field": Bitfield - Indicating presence of particular Metadata fields/values.
                "n_auth": Number of authors,
                "n_orcid": Number of authors with Orcids,
                "n_fund": Number of funders,
                "n_fund_id": PNumber of funder IDs,
                "n_grant": Number of grants,
                "n_lic": Number of licences,
                "n_struct_aff": Number of structured author affiliations,
                "n_aff_ids": Number of structured author affiliations with Org Ids,
                "n_cont": Number of non-author contributors,
                "n_hist": Number of history dates
            }
        }
        """
        if metrics_dict:
            self._set_single("metrics", metrics_dict)

# END RoutingInformation class


class UnroutedMixin:
    """
    Class that provides unrouted_scroller_obj(...), count(...) methods
    that are used by both UnroutedNotification and HarvestedNotification classes.

    ** MUST BE USED in conjunction with ...DAO class. **
    """
    @classmethod
    def unrouted_scroller_obj(cls, order="asc"):
        """
        Return a basic Scroller object for scrolling through ALL unrouted notifications.  The connection is
        automatically closed when all records have been scrolled through.

        Note: We use a basic scroller here, unlike the Reusable-scroller used for routed_scroller_obj, because the
        unrouted scroller is used relatively infrequently and it scrolls through ALL unrouted notifications in a
        single pass. This contrasts with routed-scroller, which is called in a loop for different accounts, retrieving
        sub-sets of routed notifications each time - for which reusable-scroller is more appropriate.

        We use fetchmany_size of 20.

        :param order: "asc" (Ascending) or "desc" (Descending) - sort order for results
        :return: Scroller object
        """
        return cls.scroller_obj(pull_name="all", order_by=order, end_action=CONN_CLOSE,
                                scroll_num=UNROUTED_SCROLL_NUM, fetchmany_size=20)

    @classmethod
    def count(cls):
        """
        Count Unrouted notifications.
        :return: Integer - number of Unrouted notifications
        """
        return super().count(pull_name="all")


class UnroutedNotification(BaseNotification, UnroutedNotificationDAO, UnroutedMixin):
    """
    Class which represents a notification that has been received into the system successfully
    but has not yet been routed to any repository accounts.

    It extends the BaseNotification and does not add any additional information, so see that class's
    documentation for details of the data model.

    This class also extends a DAO, which means it can be persisted.
    """
    def __init__(self, raw=None, **kwargs):
        """
        Create a new instance of the UnroutedNotification object, optionally around the raw python dictionary.

        If supplied, the raw dictionary will be validated against the allowed structure of this
        object, and an exception will be raised if it does not validate

        :param raw: python dict object containing the notification data
        """
        super(UnroutedNotification, self).__init__(raw=raw, **kwargs)
        self.type = UnroutedNotificationDAO.__type__

    def set_link_default_access_and_has_pdf_flag(self):
        """
        If a link has missing access, then set as "public".
        Set the `has_pdf` flag (will override setting supplied in original incoming JSON).
        :return:
        """
        _has_pdf = False
        for link in self.links:
            # treat a missing access annotation as a "public" link
            if "access" not in link:
                link["access"] = "public"
            if link["format"].endswith("pdf"):
                _has_pdf = True
        self.has_pdf = _has_pdf


    @staticmethod
    def compare_enhance_flat_dict(curr_dict, new_dict, keys, desc, errors):
        """
        Compare 2 dicts (flat structure i.e. not nested) & enhance elements of the current dict if they don't exist
        using the corresponding element in new.  IMPORTANT: Relies on dicts being passed by reference
        :param curr_dict: Current (existing) dict
        :param new_dict:  New dict
        :param keys:      List of keys to check (this may be a subset of all the possible keys in the dicts)
        :param desc:      Description in case error.
        :param errors:    List of errors - may be updated
        :return: curr_dict
        """
        if not curr_dict:
            return new_dict

        for key in keys:
            curr_value = curr_dict.get(key)
            new_value = new_dict.get(key)
            if curr_value:
                if new_value and curr_value != new_value:
                    errors.append(f"In {desc}, the «{key}» values differ: base ({curr_value}), new ({new_value})")
            elif new_value:
                curr_dict[key] = new_value
        return curr_dict

    @staticmethod
    def add_unique_to_list_or_enhance(curr_list, new_list, unique_keys, other_keys, desc, errors):
        """
        Enhance a current list with entries or content from a new_list. NOTE relies upon lists being passed by
        reference.

        Loop for each item in new_list
            If NOT item already exists in curr_list (checked by comparing unique_keys)
                add new item to curr_list
        :param curr_list:   Existing list of dicts, which may be updated
        :param new_list:    New list of dicts
        :param unique_keys: Keys to use to decide if and entry in new list is already in current list
        :param other_keys:  Keys expected in the dict, other than those already included in unique_keys
        :param desc:        Description of list being processed
        :param errors:      List of errors - may be updated
        :return: curr_list
        """
        if not curr_list:
            return new_list

        add_list = []
        for new in new_list:
            match_found = False
            for curr in curr_list:
                same = True
                for key in unique_keys:
                    if curr.get(key) != new.get(key):
                        same = False
                        break
                if same:
                    match_found = True
                    break
            if match_found:
                if other_keys:
                    UnroutedNotification.compare_enhance_flat_dict(curr, new, other_keys, desc, errors)
            else:
                add_list.append(new)
        if add_list:
            curr_list.extend(add_list)
        return curr_list

    def enhance(self, metadata):
        """
        Enhance the notification with additional metadata extracted from another source, in NotificationMetadata format

        :param metadata: a NotificationMetadata object
        """
        # for those methods that are unicode (simple setters and getters)
        # we just want to accept the existing value if it is set, otherwise take the value from the other metadata
        errors = []
        # Loop through all metadata class attributes, which includes and getters/setters
        for attrib in dir(metadata):
            if not attrib.startswith('_'):
                metadata_value = getattr(metadata, attrib)
                if isinstance(metadata_value, str) and getattr(self, attrib) is None:
                    try:
                        setattr(self, attrib, metadata_value)
                    except AttributeError:
                        # This will arise if a getter has been defined, but there is no corresponding setter, as
                        # for example with `@property def embargo_start()`
                        pass

        meta_pub_date = metadata.publication_date
        if meta_pub_date:
            self.publication_date = self.compare_enhance_flat_dict(
                self.publication_date,
                meta_pub_date,
                ["publication_format", "date", "year", "month", "day", "season"],
                "publication_date",
                errors)
        meta_status = metadata.publication_status
        if meta_status:
            self.publication_status = meta_status

        meta_embargo = metadata.embargo
        if meta_embargo:
            self.embargo = self.compare_enhance_flat_dict(
                self.embargo, meta_embargo, ["start", "end", "duration"], "embargo", errors)

        # add history dates
        for date in metadata.history_date:
            self.add_history_date_obj(date)

        # add article_language
        for lang in metadata.article_language:
            self.add_article_language(lang)

        # add article_subtitle
        for subtitle in metadata.article_subtitle:
            self.add_article_subtitle(subtitle)

        # add any license
        meta_lic = metadata.licenses
        if meta_lic:
            self.licenses = self.add_unique_to_list_or_enhance(
                self.licenses, meta_lic, ["url", "start"], ["title", "type", "version"], "license_ref", errors)

        # add any journal_publishers
        for jp in metadata.journal_publishers:
            self.add_journal_publisher(jp)

        # add any new journal identifiers
        meta_idents = metadata.journal_identifiers
        if meta_idents:
            self.journal_identifiers = self.add_unique_to_list_or_enhance(
                self.journal_identifiers, meta_idents, ["type"], ["id"], "journal identifier", errors)

        # add any new article identifiers
        meta_idents = metadata.article_identifiers
        if meta_idents:
            self.article_identifiers = self.add_unique_to_list_or_enhance(
                self.article_identifiers, meta_idents, ["type"], ["id"], "article identifier", errors)

        # add any new subjects
        for s in metadata.article_subject:
            self.add_article_subject(s)

        # deal with object based metadata

        # add and merge new authors
        self._merge_contribs(self.authors, metadata.authors, errors)

        # add and merge new contributors
        self._merge_contribs(self.contributors, metadata.contributors, errors)

        # add unique funder objects to list
        self._add_unique_funding(metadata)

        if errors:
            raise EnhancementException("; ".join(errors))

    def _merge_contribs(self, self_contribs, meta_contribs, errors):
        """
        For each contributor in the provided metadata (meta_contribs), checks whether it is a new cocntributor to be
        added to original list (self_contribs) or an identical contributor (same surname & ORCID) in which case the
        original record may be enhanced by additional information from the matching meta_contrib.

        IMPORTANT: function may UPDATE the self_contribs list (adding info to exisiting elements or
        appending new elements)

        :param self_contribs: List of original contributors or authors
        :param meta_contribs: List of additional contributors or authors
        :param errors: List of errors - may be updated
        """

        # For efficiency, store new contributors for subsequent processing to avoid increasing
        # size of original contributor array during the first for loop
        contribs_to_add = []

        # for each contributor in meta_contribs, we either wish to merge it with an existing contributor in
        # self_contribs or add the new contributor to our contributors
        for meta_contrib in meta_contribs:

            # See if meta_contrib matches an existing contributor, if so enhance by merging the records
            if not self._try_merge(self_contribs, meta_contrib, errors):
                # No merge occurred, must be a new contributor to add to list for later processing
                contribs_to_add.append(meta_contrib)

        # Finally add any new contributors to the original list
        for new_contribs in contribs_to_add:
            self_contribs.append(new_contribs)

    def _try_merge(self, self_contribs, meta_contrib, errors):
        """
        Attempts to match a single metadata contributor against list of original contributors.  A match requires
        surnames and ORCID IDs to be identical.

        If matched, the original contributor is enhanced with additional info from the meta_contrib (i.e. merging them)

        This function returns True if a match was found, and False otherwise

        IMPORTANT: function may UPDATE the self_contribs list (adding info to an exisiting element)

        :param self_contribs: List of existing contributors
        :param meta_contrib: single contributor to compare against the existing contributors
        :param errors: List of errors - may be updated

        :return: boolean - True = matched (& merged) | False = not matched (i.e. meta_contrib is a NEW contributor)
        """
        meta_surname = meta_contrib.get("name", {}).get("surname")
        if not meta_surname:
            return False
        # Extract all ORCIDs from meta_contrib
        meta_orcids = [meta_ident["id"] for meta_ident in meta_contrib.get("identifier", []) if meta_ident.get("type") == "orcid"]
        if not meta_orcids:
            return False
        # loop through all current contributors in self_contribs, keeping track of index additionally
        for self_contrib in self_contribs:
            # if surnames are equal and not None
            if self_contrib.get("name", {}).get("surname") == meta_surname:
                for self_ident in self_contrib.get("identifier", []):
                    if self_ident.get("type") == "orcid":
                        self_orcid = self_ident.get("id")
                        for meta_orcid in meta_orcids:
                            if self_orcid == meta_orcid:
                                # perform the merge
                                self._merge_contrib(self_contrib, meta_contrib, errors)
                                return True  # We have successfully merged, so return
        # If we got this far the meta_contributor was not matched (& so is a new contributor)
        return False

    def _merge_contrib(self, orig_contrib, merge_contrib, errors):
        """
        Merges two contributor objects and returns the result. A merge combines *unique* identifiers into a longer
        list, combines *unique* affiliations by concatenating affiliations with comma separation, likewise
        merges name objects based on their availability. Chooses a not None organisation name if one exists.

        IMPORTANT: function may UPDATE the orig_contrib (adding info to it)

        :param orig_contrib: The original contributor object, being merged
        :param merge_contrib: The new contributor object, to be merged into orig_contrib
        :param errors: List of errors - may be updated

        :return:
        """
        def update_fields(orig, extra, keys):
            """
            Helper, updates original dictionary fields if needed

            IMPORTANT: function may UPDATE the orig dict (adding info to it)

            :param orig: original dict
            :param extra: possible additional info dict
            :param keys: keys
            :return:
            """
            for key in keys:
                # Original value does exist or is empty
                if not orig.get(key):
                    value = extra.get(key)
                    # If extra info dict has a value, then update the original dict
                    if value:
                        orig[key] = value


        # deal with merging author/contributor identifiers (e.g. ORCID, emails)
        orig_idents = list(orig_contrib.get("identifier", []))
        for merge_ident in merge_contrib.get("identifier", []):
            # if this identifier isn't already in original metadata list of identifiers
            if merge_ident not in orig_idents:
                # Add to original identifiers list
                orig_contrib["identifier"].append(merge_ident)

        # Merge affiliations (v4 structure)
        merge_affiliation_list = merge_contrib.get("affiliations")
        if merge_affiliation_list:
            orig_affiliation_list = orig_contrib.get("affiliations")
            if not orig_affiliation_list:
                orig_contrib["affiliations"] = merge_affiliation_list
            else:
                # We have both original and new (merge) affiliations...
                try:
                    # Sort original and new affiliations by lower-case organisation name, Ascending
                    merge_affiliation_list.sort(key=lambda x: x["org"].lower())
                    orig_affiliation_list.sort(key=lambda x: x["org"].lower())
                except (KeyError, AttributeError) as e:
                    # Missing organisation name - cannot do a comparative merge
                    # - so just append all merge affiliations to original list - we may end up with duplicates which will
                    # be inefficient, but not otherwise cause a problem
                    orig_affiliation_list.extend(merge_affiliation_list)
                else:
                    num_orig = len(orig_affiliation_list)
                    orig_ix =  0
                    last_orig_ix = None
                    num_merge = len(merge_affiliation_list)
                    merge_ix = 0
                    last_merge_ix = None
                    while orig_ix < num_orig:
                        if merge_ix == num_merge:
                            # All merge affiliations have been processed
                            break
                        if merge_ix != last_merge_ix:   # First time around loop or merge_ix has changed
                            merge_aff_dict = merge_affiliation_list[merge_ix]
                            merge_org = merge_aff_dict["org"].lower()
                            last_merge_ix = merge_ix
                        if orig_ix != last_orig_ix:     # First time around loop or orig_ix has changed
                            orig_aff_dict = orig_affiliation_list[orig_ix]
                            orig_org = orig_aff_dict["org"].lower()
                            last_orig_ix = orig_ix
                        # same organisation name
                        if merge_org == orig_org:
                            # Merge identifiers
                            merge_ids_list = merge_aff_dict.get("identifier")
                            orig_ids_list = orig_aff_dict.get("identifier")
                            if merge_ids_list and orig_ids_list:
                                # Note that at affiliation may, for example have more than 1 ISNI - e.g. a primary ISNI
                                # for organisation overall and subsidiary ISNIs for departments/schools.
                                self.add_unique_to_list_or_enhance(
                                    orig_ids_list, merge_ids_list, ["type", "id"], [], "affiliation organisation identifier", errors)
                            # Merge other fields (except "org" which we know are the same)
                            self.compare_enhance_flat_dict(
                                orig_aff_dict,
                                merge_aff_dict,
                                ["dept", "street", "city", "state", "postcode", "country", "country_code", "raw"],
                                f"affiliation for '{merge_org}'",
                                errors)
                            orig_ix += 1  # Move to next orig aff
                            merge_ix += 1  # Move to next merge aff
                        elif merge_org < orig_org:
                            # Merge org does not appear in original org list, so add it to the end
                            orig_affiliation_list.append(merge_aff_dict)
                            merge_ix += 1 # Move to next merge aff
                        else:
                            # Orig org NOT in merge list
                            orig_ix += 1

                    # If after cycling through all original affs, there are still merge affs left, then append them all
                    if merge_ix < num_merge:
                        orig_affiliation_list.extend(merge_affiliation_list[merge_ix:])

        # update name dict with info from firstname and suffix fields (as needed)
        update_fields(orig_contrib['name'], merge_contrib['name'], ['firstname', 'suffix'])

        # update organisation name (as needed)
        update_fields(orig_contrib, merge_contrib, ['organisation_name'])

    def _add_unique_funding(self, metadata):
        """
        Method runs through new funding objects in metadata, and simply adds any object which is considered to be
        unique. We consider two funding objects equal if their identifier AND grant numbers are both equal.

        :param metadata: The new set of metadata we are adding
        """

        # if we don't perform a hard copy of self.funding, then the loop gets larger as we add more funding objects
        self_funding = list(self.funding)
        funding_to_add = []
        for meta_fund in metadata.funding:
            meta_grant_nos_set = set(meta_fund.get("grant_numbers", []))
            meta_idents = meta_fund.get("identifier", [])
            try:
                for self_fund in self_funding:
                    # if grant numbers are equal and not empty
                    if meta_grant_nos_set and meta_grant_nos_set == set(self_fund.get("grant_numbers", [])):
                        self_idents = self_fund.get("identifier", [])
                        for meta_ident in meta_idents:
                            for self_ident in self_idents:
                                if meta_ident == self_ident:
                                    # this metadata object is equivalent to one already in the self_funding so we don't want to add it
                                    raise StopIteration
            except StopIteration:
                # We found that current meta_fund dict matches an existing self_fund dict
                pass
            else:
                funding_to_add.append(meta_fund)

        if funding_to_add:
            self.funding = self_funding + funding_to_add

    def make_routed(self):
        """
        Create an instance of a RoutedNotification from this object.

        Note that once this is done you'll still need to populate the RoutedNotification with all the appropriate
        routing information.

        :return: RoutedNotification
        """
        cpy_data = deepcopy(self.data)
        # Remove redundant headings from Ack & Abstract fields
        remove_embedded_xml_and_redundant_headings_from_titles_abstract_ack(cpy_data, is_harvested=False)
        return RoutedNotification(cpy_data)

    @classmethod
    def bulk_delete_by_id(cls, ids):
        """
        Bulk delete all of the notifications specified by the ID

        :param ids: ids of notifications to be deleted
        :return: Int =  Number deleted
        """
        num_deleted = 0
        if ids:
            try:
                cls.start_transaction()
                for i in ids:
                    num_deleted += cls.delete_by_query(i, commit=False)
                cls.commit()
            except Exception as e:
                current_app.logger.critical(
                    f"Bulk delete of notifications failed for Ids: {ids} - consider deleting manually. {repr(e)}")
        return num_deleted

    @classmethod
    def bulk_delete_less_than_equal_id(cls, max_id):
        """
        Bulk delete all of Unrouted notifications with an ID less than or equal to max_id

        :param max_id: Int - ID of last notification to delete
        :return: Int =  Number deleted
        """
        num_deleted = 0
        try:
            num_deleted = cls.delete_by_query(max_id, del_name="del_upto_id")
        except Exception as e:
            current_app.logger.critical(
                f"Bulk delete of notifications failed for all Ids up to: {max_id} - consider deleting manually. {repr(e)}")
        return num_deleted

# END UnroutedNotification class


class HarvestedNotification(BaseNotification, HarvestedUnroutedNotificationDAO, UnroutedMixin):
    """
    Class which represents a notification that has been Harvested but has not yet been routed to any repository accounts.
    ** These notifications are stored in 'harvested_unrouted' table, separately from routed notifications & publisher
    unrouted notifications - which are both stored in 'notification' table. **

    It extends the BaseNotification and does not add any additional information, so see that class's
    documentation for details of the data model.

    This class also extends a DAO, which means it can be persisted.
    """
    def __init__(self, raw=None, **kwargs):
        """
        Create a new instance of the HarvestedNotification object, optionally around the raw python dictionary.

        If supplied, the raw dictionary will be validated against the allowed structure of this
        object, and an exception will be raised if it does not validate

        :param raw: python dict object containing the notification data
        """
        super(HarvestedNotification, self).__init__(raw=raw, **kwargs)

    def make_routed(self):
        """
        Create an instance of a RoutedNotification from this HarvestedNotification object.

        Note that once this is done you'll still need to populate the RoutedNotification with all the appropriate
        routing information.

        :return: RoutedNotification
        """
        cpy_data = deepcopy(self.data)
        # The Id is removed, because the RoutedNotification will be stored in the 'notification' table (DIFFERENT from
        # the table storing the HarvestedUnrouted notification) so it needs to be inserted, which will give it a NEW Id.
        # If Id wasn't deleted, then when the data is added to 'notification' table it would cause a pre-existing (wrong)
        # record to be updated.
        del(cpy_data["id"])

        # Remove any embedded XML from certain fields, also redundant headings
        remove_embedded_xml_and_redundant_headings_from_titles_abstract_ack(cpy_data, is_harvested=True)

        return RoutedNotification(cpy_data)

    @classmethod
    def max_id(cls):
        """
        :return: Integer - Largest ID of record in table (i.e. Id of last record created)
        """
        rec_tuple_list = cls.bespoke_pull(pull_name="bspk_max_id")
        if rec_tuple_list:
            return int(rec_tuple_list[0][0])    # Expect single array of results, with that array having 1 entry
        return 0

    @classmethod
    def bulk_delete_less_than_equal_id(cls, max_id):
        """
        Bulk delete all of Harvested Unrouted notifications with an ID less than or equal to max_id

        :param max_id: Int - ID of last notification to delete
        :return: Int =  Number deleted
        """
        return cls.delete_by_query(max_id, del_name="del_upto_id")

# END HarvestedUnroutedNotificationDAO class


class RoutedNotification(BaseNotification, RoutingInformation, RoutedNotificationDAO):
    """
    Class which represents a notification that has been received into the system and successfully
    routed to one or more repository accounts

    It extends the BaseNotification and mixes that with the RoutingInformation, so see both of
    those class definitions for the data that is held.

    This class also extends a DAO, which means it can be persisted.
    """
    def __init__(self, raw=None, **kwargs):
        """
        Create a new instance of the RoutedNotification object, optionally around the raw python dictionary.

        If supplied, the raw dictionary will be validated against the allowed structure of this
        object, and an exception will be raised if it does not validate

        :param raw: python dict object containing the notification data
        """
        if raw:
            # Copy DOI from metadata.article.identifiers list to metadata.article.doi element
            try:
                for id_dict in raw["metadata"]["article"]["identifier"]:
                    if id_dict["type"] == "doi":
                        # Set NEW doi attribute on article metadata
                        raw["metadata"]["article"]["doi"] = id_dict["id"].lower()
                        break
            except KeyError:
                pass

        super(RoutedNotification, self).__init__(raw=raw, **kwargs)
        self.type = RoutedNotificationDAO.__type__

    @property
    def article_doi(self):
        """
        The article doi

        :return: The article doi
        """
        return self._get_single("metadata.article.doi")

    @article_doi.setter
    def article_doi(self, val):
        """
        Set the article doi
        """
        self._set_single("metadata.article.doi", val)

    def set_category_if_empty(self):
        """
        Set the notification category (IF NOT ALREADY SET) by analysing the article type value
        :return:
        """
        # Already set, so do nothing
        if not self.category:
            self.category = self.calc_category_from_article_type(self.article_type)

    def save_newly_routed(self):
        """
        Save newly created Routed notification record AND creates entries in notification_account table.
        Updates the relevant record in `notification` table AND, for each repository to which the notification is matched
        it inserts a record into the `notification_account` table.
        :return:
        """
        self.start_transaction()
        if self.id:
            # Update the current Routed notification
            self.update(commit=False)
        else:
            # Harvested unrouted notifications come from different table, so must be inserted into notification table
            self.insert(commit=False)

        # Create notification_account records for each repository.
        note_acc_dict = {"id_note": self.id, "id_acc": None}
        for repo_id in self.repositories:
            note_acc_dict["id_acc"] = repo_id
            # Create notification_account record and insert it into database
            NotificationAccountDAO(note_acc_dict).insert(commit=False)
        self.commit()

    @classmethod
    def _get_pull_name_and_params_list(cls, repo_id, pub_id, since_id, since_date, search_doi=None):
        """
        Establishes the pull_name to use for the query based on supplied parameter values.  Also constructs the
        parameters list needed for that pull_name.
        :param repo_id: Int - Repository ID
        :param pub_id: Int - Publisher ID
        :param since_id: Int - Get all records with an Id greater than this value
        :param since_date: Datetime obj - Get all records with Date later than this OR
                          String - with one of these formats: "YYYY-MM-DD", "YYYY-MM-DD HH:MM:SS", "YYYY-MM-DDTHH:MM:SSZ"
        :param search_doi: String - (partial) DOI value to match
        :return: Tuple: (String - pull_name, List - [parameters for pull request])
        """
        if repo_id:
            pull_name_prefix = "all_4rac_"  # All for Repository Ac
            params = [repo_id]
        elif pub_id:
            pull_name_prefix = "all_4pac_"  # All for Publisher Ac
            params = [pub_id]
        else:
            pull_name_prefix = "all_"
            params = []

        if search_doi is not None:
            # Set pull_name depending on whether search_doi contains wild-card or not
            pull_name = pull_name_prefix + ("like_doi" if "%" in search_doi else "equal_doi")
            params.append(search_doi)
        elif since_id is not None:
            pull_name = pull_name_prefix + "since_id"
            params.append(since_id)
        elif since_date is not None:
            # Convert date string to datetime object
            if isinstance(since_date, str):
                # obtain date/time format that corresponds to length of since_date string
                fmt = {10: "%Y-%m-%d", 19: "%Y-%m-%d %H:%M:%S", 20: "%Y-%m-%dT%H:%M:%SZ"}.get(len(since_date))
                if fmt:
                    since_date = datetime.strptime(since_date, fmt).replace(tzinfo=timezone.utc)
                else:
                    raise Exception("In _get_pull_name_and_params_list since_date string NOT in one of 3 accepted formats")

            pull_name = pull_name_prefix + "since_date"
            params.append(since_date)
        else:
            pull_name = pull_name_prefix[:-1]   # pull_name_prefix with last char '_' removed

        return pull_name, params

    @classmethod
    def list_routed(cls, since_id=None, since_date=None, repo_id=None, page=1, page_size=None, order="asc"):
        """
        List Routed notifications.  If page_size is provided then returns just that many notifications, starting
        from offset determined by page number.

        By default (called without ANY params) lists ALL notifications of the particular type.
        :param since_id: Int - Get all records with an Id greater than this value
        :param since_date: Datetime obj - Get all records with Date later than this
        :param repo_id: Int - Repository ID
        :param page: Int - page number
        :param page_size: Int - Number of entries per page
        :param order: String - "asc" or "desc" (Ascenging/Descending)
        :return: List of notification Class objects
        """
        pull_name, params = cls._get_pull_name_and_params_list(repo_id, None, since_id, since_date)
        return cls.pull_all(
            *params,
            pull_name=pull_name,
            limit_offset=cls.calc_limit_offset_param(page, page_size),
            order_by=order
        )

    @classmethod
    def routed_scroller_obj(cls, since_id=None, since_date=None, repo_id=None, limit_offset=None, order="asc", scroll_num=None, **kwargs):
        """
        Return a Reusable-scroller object for scrolling through routed notifications.  (A reusable scroller is used
        for processing efficiency - avoids opening/closing database connections & cursors for each use of scroller which
        is called repeatedly for different accounts (& other params) in processing loop).

        :param since_id: Int - Get all records with an Id greater than this value
        :param since_date: Datetime obj - Get all records with Date later than this
        :param repo_id: Int - Repository ID
        :param limit_offset: Either None OR 2 element List: [Int: num-rows, Int: offset)] OR single Int: num-rows
        :param order: "asc" (Ascending) or "desc" (Descending) - sort order for results
        :param scroll_num: None or Integer - unique connection number
        :return: Scroller object
        """
        pull_name, params = cls._get_pull_name_and_params_list(repo_id, None, since_id, since_date)
        return cls.reusable_scroller_obj(
            *params, pull_name=pull_name, limit_offset=limit_offset, order_by=order, scroll_num=scroll_num, **kwargs)

    @classmethod
    def count(cls, repo_id=None, pub_id=None, since_id=None, since_date=None, search_doi=None):
        """
        Count ALL notifications matching supplied parameters.
        :param repo_id: Int - Repository ID
        :param pub_id: Int - Publisher ID
        :param since_id: Int - Get all records with an Id greater than this value
        :param since_date: Datetime obj - Get all records with Date later than this
        :param search_doi: String - Get all records matching DOI - may or may not contain '%' wild cards
        :return: Integer - number of Routed notifications matching the criteria (as per supplied parameters)
        """
        pull_name, params = cls._get_pull_name_and_params_list(repo_id, pub_id, since_id, since_date, search_doi)
        return super().count(*params, pull_name=pull_name)

    @classmethod
    def outgoing_list_obj(cls, api_vers, since_id=None, since_datetime=None, repo_id=None, page=1, page_size=100, order="asc"):
        """
        Create a NotificationList object, populated with Outgoing notifications.
        List notifications of the following types: Unrouted or Routed.
        :param api_vers: String - API version
        :param since_id: Int - Get all records with an Id greater than this value
        :param since_datetime: Datetime obj - Get all records with Date later than this
        :param repo_id: Int - Repository ID
        :param page: Int - page number
        :param page_size: Int - Number of entries per page
        :param order: String - sort order, one of: "asc" or "desc"
        :return: NotificationList object
        """
        note_list_dict = {
            "since" : dates.format(since_datetime) if since_datetime else "",
            # "since_id": since_id,     # ZZZ - UNCOMMENT line when API v3 is no longer supported
            "page" : page,
            "pageSize" : page_size,
            "timestamp" : dates.now_str(),
            "total" : cls.count(repo_id=repo_id, since_id=since_id, since_date=since_datetime),
        }
        # If latest version (v4) of API then add since_id
        if api_vers == current_app.config["API_VERSION"]:   # ZZZ - DELETE line when API v3 no longer supported & line above is uncommented
            note_list_dict["since_id"] = since_id           # ZZZ - DELETE line when API v3 no longer supported

        routed_scroller = cls.routed_scroller_obj(
            since_id=since_id,
            since_date=since_datetime,
            repo_id=repo_id,
            limit_offset=cls.calc_limit_offset_param(page, page_size),
            order=order,
            scroll_num=ROUTED_SCROLL_NUM
        )
        with routed_scroller:
            # notifications is a list of data Dicts (NOT class objects)
            note_list_dict["notifications"] = [note.make_outgoing(api_vers).data for note in routed_scroller]

        return NotificationList(note_list_dict)

    @classmethod
    def pull_data_tuple_for_content_retrieval(cls, note_id):
        """
        Retrieve data required for API call to retrieve Content.
        Columns: id, prov_id, repositories, pkg_format
        Avoids unnecessarily retrieving ALL notification data (which involves unpacking MEDIUMTEXT json column)

        :param note_id: Int - Notification ID
        :return: Tuple of record data or all None if no record found: (note_id, prov_id, repositories, pkg_format)
        """
        # Retrieve list of tuples (we expect either an empty list or 1 element list)
        list_of_tuples = cls.bespoke_pull(note_id, pull_name="bspk_4content")
        if list_of_tuples:
            note_id, prov_id, repositories, pkg_format = list_of_tuples[0]
            # Convert repositories list packaged as a '|' separated string back into the original list
            return note_id, prov_id, cls.convert_int_list(repositories), pkg_format
        else:
            return None, None, None, None


    @classmethod
    def pull_data_tuple_for_proxy_url(cls, note_id):
        """
        Retrieve data required for API to get proxy links.
        Columns: id, links
        Avoids unnecessarily retrieving ALL notification data (which involves unpacking MEDIUMTEXT json column)

        :param note_id: Int - Notification ID
        :return: Tuple of record data (id, links-list) or (None, []) if no record found
        """
        # Retrieve list of tuples (we expect either an empty list or 1 element list)
        list_of_tuples = cls.bespoke_pull(note_id, pull_name="bspk_links_4proxycontent")
        if list_of_tuples:
            note_id, links_json = list_of_tuples[0]
            # Convert json-String (list of objects) to python list
            return note_id, cls.list_to_from_json_str(links_json)
        else:
            return None, []

    @classmethod
    def get_pub_doi_repo_data_between_2_dates_scroller(cls, pub_id, from_date, to_date):
        """
        Reusable scroller for obtaining DOI information
        :param pub_id: Publisher ID
        :param from_date: Date object - first date
        :param to_date: Date object - last date
        """
        def format_rec(rec_tuple):
            """
            rec_tuple is (created-date-obj, doi, repo_ids_string)
            :return: Tuple: (Y-M-D string, DOI, [array of repo-IDs])
            """
            date_obj, doi, repo_ids_str = rec_tuple
            return date_obj.strftime("%Y-%m-%d"), doi, [int(id) for id in repo_ids_str.split("|")]

        return cls.reusable_scroller_obj(
            pub_id, from_date, to_date, pull_name="bspk_pub_doi_repo_data_in_range", scroll_num=PUB_DOI_SCROLL_NUM,
            rec_format=format_rec)


    @classmethod
    def get_pub_doi_repo_csv_data(cls, pub_id, from_date, to_date, format_flag, live_repo_id_to_orgname_dict):
        """
        Get data list, including header row and final totals row, for use in csv file production, for publisher report
        showing which DOIs have been matched to which repositories.

        :param pub_id: Publisher ID
        :param from_date: Date object - Jan 1st YYYY
        :param to_date: Date object - Dec 1st YYYY
        :param format_flag: String - "": Don't produce report
                                     "C": Concatenate repo names comma separated,
                                     "N": Concatenate repo names comma, newline separated,
                                     "S": Separate lines for each repo,
                                     "B": Separate lines for each repo, but blank (don't repeat) other values
        :param live_repo_id_to_orgname_dict: Dict maps repo-id to repo-org-name (Live repo accounts only)

        :return: List of data lists for specified period:
            [[Date-processed, DOI, Number-of-matches, Institution-name(s)], ...]
        """
        if not format_flag:
            return []

        # Map format flag to concatenation string
        concat_str = {'C': "; ", 'N': "; \n"}.get(format_flag)

        all_live_repo_ids_set = set()  # Used to establish Total number of institutions articles have been sent to
        total_articles = 0
        total_matches = 0
        # Create header row
        all_csv_rows = [["Date processed", "DOI", "Number of matches", "Matched to institution(s)"]]
        scroller = cls.get_pub_doi_repo_data_between_2_dates_scroller(pub_id, from_date, to_date)
        with scroller:
            for proc_date, doi, repo_ids_list in scroller:
                live_repo_ids = []
                live_repo_names = []
                # Get Live Repo org names, sorted
                for repo_id in repo_ids_list:
                    # Ids of Test repositories  will give repo_name of None
                    repo_name = live_repo_id_to_orgname_dict.get(repo_id)
                    if repo_name:
                        live_repo_names.append(repo_name)
                        live_repo_ids.append(repo_id)
                if not live_repo_ids:
                    continue    # Skip to next record if notification was NOT matched to any Live repositories
                total_articles += 1
                repo_count = len(live_repo_ids)
                total_matches += repo_count
                all_live_repo_ids_set.update(live_repo_ids)  # Add repo ids to set of repo ids
                live_repo_names.sort()

                if concat_str:  # Concatenate repo names (format_flag is "C" or "N"
                    all_csv_rows.append([proc_date, doi, repo_count, concat_str.join(live_repo_names)])
                else:
                    # Separate rows for each repo name (format_flag is "B" or "S")
                    if format_flag == "S":  # All columns populated
                        repo_count = 1
                        blanking = False
                    else:   # "B" - Date, DOI, repo-count shown once for each DOI, not repeated for multiple repos
                        blanking = repo_count > 1   # Only need to blank subsequent lines if more than 1 repo
                    for repo_name in live_repo_names:
                        all_csv_rows.append([proc_date, doi, repo_count, repo_name])
                        # If blanking out proc_date, DOI & repo_count for 2nd repo-name onwards
                        if blanking:
                            proc_date = doi = repo_count = ""
                            blanking = False
        # Append 3 totals row
        all_csv_rows.extend([
            ["Total articles:", total_articles, "", ""],
            ["Total institutions:", len(all_live_repo_ids_set), "", ""],
            ["Total matches:", total_matches, "", ""]
        ])
        return all_csv_rows

# END RoutedNotification class


class RoutingMetadata(dataobj.DataObj):
    """
    Class to represent the metadata that is extracted from a notification for use by the matching algorithm which
    uses repo account matching params to the notification.

    """

    def __init__(self, raw=None, **kwargs):
        """
        Create a new instance of the RoutingMetadata object, optionally around the raw python dictionary.

        If supplied, the raw dictionary will be validated against the allowed structure of this
        object, and an exception will be raised if it does not validate

        {
            publication_date: "",
            "emails": ["<emails>"],
            "affiliations": ["<affiliation strings>"],
            "orcids": ["<ORCID values>"],
            "postcodes": ["<Postcodes>"],
            "grants": ["<Grants>"]
            "org_ids": ["<Organization ids as 'TYPE: Value' strings>"]
        }
        :param raw: python dict object containing the notification data
        """
        struct = {
            "fields": {
                "publication_date": {}
            },
            "lists": {
                "emails": {"contains": "field"},
                "affiliations": {"contains": "field"},
                "orcids": {"contains": "field"},
                "postcodes": {"contains": "field"},
                "grants": {"contains": "field"},
                "org_ids": {"contains": "field"}
            }
        }

        self._add_struct(struct)
        super(RoutingMetadata, self).__init__(raw=raw, **kwargs)

    def is_too_old(self, max_pub_age_in_years=None):
        """
        Determine whether this notification is too old.

        :param max_pub_age_in_years: The maximum age of the publication in years (in None or zero then it is ignored)

        :return: True if the notification is too old, False otherwise.
                 Will also return False if there is no pub date or if there is no max_pub_age_in_years.
        """
        if max_pub_age_in_years:
            pub_date = self._get_publication_date_as_datetime()
            if pub_date:
                return pub_date < (datetime.today() - relativedelta(years=max_pub_age_in_years))
        return False

    def _get_publication_date_as_datetime(self):
        """
        Simple helper function to get the publication date as a datetime object

        :return: Publication date as a datetime object, or None if there is no pub date.
        """
        pub_date = self.publication_date
        # return dates.parse(pub_date, format=YYYY_MM_DD) if pub_date else None
        return datetime.strptime(pub_date, YYYY_MM_DD) if pub_date else None

    @property
    def publication_date(self):
        return self._get_single("publication_date")  #, coerce=TO_YYYY_MM_DD)

    @publication_date.setter
    def publication_date(self, val):
        self._set_single("publication_date", val, coerce=TO_YYYY_MM_DD)

    def _save_set_as_list(self, key, set_val):
        if set_val:
            # De-duplicate
            self._set_list(key, list(set_val))

    @property
    def affiliations(self):
        """
        :return: list of affiliations
        """
        return self._get_list("affiliations")

    @affiliations.setter
    def affiliations(self, set_val):
        self._save_set_as_list("affiliations", set_val)
    
    @property
    def grants(self):
        """
        :return: list of grants
        """
        return self._get_list("grants")

    @grants.setter
    def grants(self, set_val):
        self._save_set_as_list("grants", set_val)

    @property
    def emails(self):
        """
        :return: list of emails
        """
        return self._get_list("emails")

    @emails.setter
    def emails(self, set_val):
        self._save_set_as_list("emails", set_val)

    @property
    def orcids(self):
        """
        :return: list of orcids
        """
        return self._get_list("orcids")

    @orcids.setter
    def orcids(self, set_val):
        self._save_set_as_list("orcids", set_val)

    @property
    def postcodes(self):
        """
        :return: list of postcodes
        """
        return self._get_list("postcodes")

    @postcodes.setter
    def postcodes(self, set_val):
        self._save_set_as_list("postcodes", set_val)

    @property
    def org_ids(self):
        """
        :return: list of org ids
        """
        return self._get_list("org_ids")

    @org_ids.setter
    def org_ids(self, set_val):
        self._save_set_as_list("org_ids", set_val)

    def is_sufficient(self):
        """
        Does this RoutingMetadata object currently have any metadata elements that can be used for matching?
        NOTE - this consideration EXCLUDES publication date which is not directly used by the matching algorithm; in
        other words, publication date alone is NOT sufficient for matching.

        :return: True/False whether there is effective matching data or not
        """
        if not self.data:
            return False
        for k, v in self.data.items():
            # The publication date is NOT used directly for matching, so we ignore it
            if k != "publication_date":
                if v:
                    return True
        return False
# END class RoutingMetadata


class IncomingNotification(NotificationMetadata, ProviderMetadata):
    """
    Class to represent a notification delivered to the system via the API.

    It combines the structures of  NotificationMetadata and ProviderMetadata and adds the following additional
    structural elements:
    {
        "event" : "<keyword for the kind of notification: acceptance, publication, etc.>",

        "content" : {
            "packaging_format" : "<identifier for packaging format used>"
        },

        "links" : [
            {
                "type" : "<link type: splash|fulltext>",
                "format" : "<text/html|application/pdf|application/xml|application/zip|...>",
                "url" : "<provider's splash, fulltext or machine readable page>",
                "access": "<accessibility of the URL, for incoming notifications this is normally "public">"
            }
        ]
    }
    """
    def __init__(self, raw=None, **kwargs):
        """
        Create a new instance of the IncomingNotification object, optionally around the raw python dictionary.

        You may obtain the raw dictionary from - for example - a POST to the web API.

        If supplied, the raw dictionary will be validated against the allowed structure of this
        object, and an exception will be raised if it does not validate
        """
        struct = {
            "fields": {
                "event": {"coerce": "unicode"},
            },
            "objects": [
                "content"
            ],
            "lists": {
                "links": {"contains": "object"}
            },
            "required": [],

            "structs": {
                "content": {
                    "fields": {
                        "packaging_format": {"coerce": "unicode"}
                    },
                    "required": []
                },
                "links": {
                    "fields": {
                        "type": {"coerce": "unicode"},
                        "format": {"coerce": "unicode"},
                        "url": {"coerce": "url"},
                        "access": {"coerce": "unicode", "allowed_values": ["router", "public", "special"]}
                    }
                }
            }
        }
        self._add_struct(struct)
        super(IncomingNotification, self).__init__(raw=raw, **kwargs)

    @property
    def packaging_format(self):
        return self._get_single("content.packaging_format")

    def add_url_link(self, url, type, format, access="public"):
        """
        Add a link object to the current list of links

        :param url: The URL to the resource
        :param type: The type of resource that link points to (e.g. fulltext or splash etc.)
        :param format: The format/mimetype of the resource (e.g. 'text/html' or 'application/pdf' etc.)
        :param access: The access level of this link: router or public
        """
        obj = {
            "url": url,
            "type": type,
            "format": format,
            "access": access
        }
        self._add_to_list("links", obj, unique=True)

    def make_unrouted(self):
        """
        Convert this object to a note_models.UnroutenNotification object, which is
        suitable for serialisation into the index
        """
        # Because Incoming Notification is always properly structured, we don't need to unnecessarily
        # force restructuring / validation from the raw self.data
        return UnroutedNotification(deepcopy(self.data), construct_raw=False, construct_validate=False)


class OutgoingNotification(BaseNotification, RoutingInformation):
    """
    Class to represent a notification being sent out of the system via the API.

    This is essentially the same as BaseNotification, against which structure any raw data is validated, plus
    data from RoutingInformation,  but with some fields removed.
    """

    def __init__(self, raw=None, api_vers=None):
        """
        Create a new instance of the OutgoingNotification object, optionally around the raw python dictionary.

        You may obtain the raw dictionary from - for example - the Unrouted or Routed notification in the index.

        If supplied, the raw dictionary will be validated against the
        BaseNotification structure, and an exception will be raised if it does not validate.
        """

        # Call __init__ WITHOUT passing `raw` parameter, as we need to first modify self._struct which is created by
        # calling the parent class chain of __init__ functions
        super().__init__()
        # Modify self._struct which was created by __init__()
        if api_vers == "3":
            self._amend_struct(
                change_fields=[("fields.id", {"coerce": "unicode"})],   # Change from "integer"
                change_keys=[("fields.created", "created_date")]
            )
        # else:   # Latest version
        #     self._amend_struct(
        #         change_fields=[("fields.id", {"coerce": "unicode"})]
        #     )

        if raw is not None:
            # Set data using the same function that would have been called by DataObj.__init__
            # We only need to validate in debug mode (i.e. NOT in production) because data comes from previously
            # validated routed/unrouted notifications
            self.data = dataobj.construct(raw, self._struct, self._coerce_map, validate_obj=current_app.debug)

    @property
    def id(self):
        return self._get_single("id")

    @id.setter
    def id(self, val):
        self._set_single("id", val)

    def analysis_date_ymd(self):
        """
        Gets the analysis date in YYYY-MM-DD format

        :return: the analysis date in YYYY-MM-DD format
        """
        # format will always be in %Y-%m-%dT%H:%M:%SZ format, so just take the first 10 elements, %Y-%m-%d
        return self._get_single("analysis_date", default="")[:10]

    def get_download_link(self, packaging, api_key):
        """
        Get a download link for the optimum content file (zip package or PDF)
        :param packaging: Required package format (e.g. SimpleZip)
        :param api_key: Account API-Key
        :return: Tuple (download_link OR None, Boolean-is-package-indicator)
        """
        download_link = None
        # See if there is a link package file (zip from publisher)
        link_dict = self.get_package_link(packaging)
        # If we have a package file (stored in Router) then add the API-Key; otherwise see if there is a
        # publicly accessible link to PDF (e.g. for notification from EPMC)
        if link_dict:
            is_package = True
            download_link = link_dict.get("url") + f"?api_key={api_key}"
        else:
            is_package = False
            link_dict = self.select_best_external_pdf_link()
            if link_dict:
                download_link = link_dict.get("url")

        return download_link, is_package


class NotificationList(dataobj.DataObj):
    """
    Class to represent a list of notifications, as a response to an API request for notifications
    matching a specified set of criteria.

    It reflects back the original parameters of the request, and includes a list of serialised (to dict objects)
    OutgoingNotification objects
    ::

        {
            "since" : "<date from which results start in the form YYYY-MM-DDThh:mm:ssZ>",
            "since_id": "<Integer ID value, query will return records with IDs greater than since_id IF SUPPLIED>",
            "page" : "<page number of results>,
            "pageSize" : "<number of results per page>,
            "timestamp" : "<timestamp of this request in the form YYYY-MM-DDThh:mm:ssZ>",
            "total" : "<total number of results at this time>",
            "notifications" : [
                "<ordered list of Outgoing Data Model (OutgoingNotification) JSON objects>"
            ]
        }
    """

    @property
    def since(self):
        """
        The requested "since" date of the request

        :return: The requested "since" date of the request
        """
        return self._get_single("since")

    @property
    def since_id(self):
        """
        The "since ID" value for the request

        :return: The Integer Id
        """
        return self._get_single("since_id")

    @property
    def page(self):
        """
        The requested page of the response

        :return: The requested page of the response
        """
        return self._get_single("page")

    @property
    def page_size(self):
        """
        The requested page size

        :return: the requested page size
        """
        return self._get_single("pageSize")

    @property
    def timestamp(self):
        """
        The timestamp of the request

        :return: the timestamp of the request in the form YYYY-MM-DDTHH:MM:SSZ
        """
        return self._get_single("timestamp")

    @property
    def total(self):
        """
        The total number of notifications in the full list (not necessarily included here) at the time of request

        :return: number of available notifications
        """
        return self._get_single("total")

    @property
    def outgoing_notes(self):
        return [OutgoingNotification(n) for n in self._get_list("notifications")]


def pull_routed_or_unrouted_notification(note_id):

    ## This commented code will always return a Routed or Unrouted notification - but may require 2 database accesses
    # A notification is most likely to be Routed
    # note = RoutedNotification.pull(note_id)
    # if note is None:
    #     note = UnroutedNotification.pull(note_id)
    # return note

    ## This version always returns a RoutedNotification or UnroutedNotification, but only ever
    ## requires a SINGLE database access.  Bespoke_pull is used because it returns just basic record data as a list
    ## of tuples.  We expect either an empty list or a list containing 1 record tuple to be returned

    rec_tuple_list = NotificationDAO.bespoke_pull(note_id, pull_name="pk")

    if rec_tuple_list:
        rec_tuple = rec_tuple_list[0]
        # rec_tuple from NotificationDAO always contains: (ID, Created-datetime, **TYPE**, Analysis-date, prov-id, prov-harv-id, prov-agent, prov-rank, repos, pkg-format, links, trans_uuid)

        if rec_tuple[2] == "R":     # Routed notification Type
            # Because RoutedNotificationDAO inherits __extra_cols__ from NotificaitonDAO there is NO NEED to call
            # RoutedNotification.set_all_cols() before calling recreate_json_dict_from_rec as it will have been
            # done by NotificationDAO.bespoke_pull() above.
            note_dict = RoutedNotification.recreate_json_dict_from_rec(rec_tuple)
            return RoutedNotification(note_dict)
        else:   # Unrouted notification
            # For UnroutedNotification.pull() we would normally get only 4 fields returned  -
            # the first 3 fields and last 1 fields that are returned by NotificationDAO.bespoke_pull()
            rec_fields = rec_tuple[:3] + rec_tuple[-1:]

            UnroutedNotification.set_all_cols()         # This is required so recreate_json_dict_from_rec works as expected
            note_dict = UnroutedNotification.recreate_json_dict_from_rec(rec_fields)
            return UnroutedNotification(note_dict)

    return None
