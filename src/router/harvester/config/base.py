"""
Main configuration file for Harvester

On deployment, desired configuration can be overridden by content of production.py|staging.py|test.py|development.py
or from local ~/.pubrouter/harvester.cfg files that they specify
"""
import os
import json

TEST_DB_NAME = "test_jper"  # Name of test database

ELASTIC_SEARCH_HOST = "http://gateway:9200"

# PUBLIC VERSION: obfuscate details
ELSEVIER_API_KEY = "XXXXYYYYXXXXYYYY"

# Crossref Authorization key
CROSSREF_API_KEY = None

##########   BELOW HERE SHOULD BE FIXED ACROSS ENVIRONMENTS ############

LOGFILE = "/var/log/pubrouter/harvester.log"


# Harvested sources
CROSSREF = 'Crossref'
ELSEVIER = 'Elsevier'
EPMC = 'EPMC'
PUBMED = 'PubMed'

# Relative ranking of harvester data sources (used by de-duplication).  Highest = 1 (direct from publisher), lowest = 3.
HARVESTER_RANKING = {
    CROSSREF: 3,
    ELSEVIER: 1,
    EPMC: 2,
    PUBMED: 3,
}

# See here for PUBMED REST API info:
#   https://www.ncbi.nlm.nih.gov/books/NBK25499/
#   https://www.nlm.nih.gov/bsd/licensee/data_elements_doc.html
#   https://www.nlm.nih.gov/databases/dtd/index.html

# Maximum number of IDs to get with eSearch - REDUCE to 200 if PubMed reports problems
PUBMED_ESEARCH_MAX = 500
# PubMed API Key - can be refreshed (if needed) at: https://www.ncbi.nlm.nih.gov/
# Login with these credentials: XXXX / YYYY (then click on username & scroll down to 'API Key Management').
PUBMED_API_KEY = "XXXXYYYYXXXXYYYY"

# URL for fetching a single article PubMed XML package.
# This should be https to avoid 301 (redirect) response which is received for http (and which results in 2 GET requests instead of 1)
PUBMED_EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

# Number of days to keep history in the DB
HISTORY_FILE_LIMIT = 90

MATCH_ALL = {
    "match_all": {}
}

# Query to retrieve IncomingNotifications that have at least the minimum information needed for matching
# (It excludes records that can't be matched because they lack any potential match data).
INCOMING_NOTIFICATION_QUERY =  json.dumps({
    "bool": {
        "should": [
            {"exists": {"field": "metadata.author.identifier"}},
            {"exists": {"field": "metadata.author.affiliations"}},
            {"exists": {"field": "metadata.funding"}}
        ],
        "minimum_should_match": 1
    }
})

# Initial WebService data if it does't exist
WEBSERVICES_DATA_EPMC = {
    'name': "EPMC",
    'url': "https://www.ebi.ac.uk/europepmc/webservices/rest/search/resulttype=core&format=json&query=%20CREATION_DATE%3A%5B{start_date}%20TO%20{end_date}%5D%20&%20OPEN_ACCESS:y%20&%20HAS_PDF:y",
    'query': json.dumps({
        "bool": {
            "should": [
                {"exists": {"field": "authorList.author.authorId"}},
                {"exists": {"field": "authorList.author.authorAffiliationDetailsList.authorAffiliation"}},
                {"exists": {"field": "authorIdList.authorId"}},
                {"exists": {"field": "grantList.grant"}}
            ],
            "minimum_should_match": 1
        }
    }),
    'frequency': "daily",
    'active': True,
    'email': "YYYY@YYYY.ac.uk",
    'engine': EPMC,
    'wait_window': 30,
    'publisher': False
}
DAYS_TO_START_FROM_EPMC = 35

WEBSERVICES_DATA_PUBMED = {
    'name': "PubMed",
    'url': "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&mindate={start_date}&maxdate={end_date}",
    'query': INCOMING_NOTIFICATION_QUERY,
    'frequency': "daily",
    'active': True,
    'email': "YYYY@YYYY.ac.uk",
    'engine': PUBMED,
    'wait_window': 8,
    'publisher': False
}
DAYS_TO_START_FROM_PUBMED = 5

WEBSERVICES_DATA_CROSSREF = {
    'name': "Crossref",
    'url': "https://api.crossref.org/types/journal-article/works?filter=from-update-date:{start_date},until-update-date:{end_date},from-pub-date:{pub_year}&rows=1000",
    'query': json.dumps({
        "bool": {
            "should": [
                {"exists": {"field": "funder"}},
                {"exists": {"field": "author.affiliation"}},
                {"exists": {"field": "author.ORCID"}}
            ],
            "minimum_should_match": 1
        }
    }),
    'frequency': "daily",
    'active': True,
    'email': "YYYY@YYYY.ac.uk",
    'engine': CROSSREF,
    'wait_window': 3,
    'publisher': False
}

# Number subtracted from the current year, used to establish the oldest publication date harvested from Crossref
# E.g. if current year is 2019, crossref query will only retrieve records with a publication date in 2017 or later)
CROSSREF_PUB_YEARS = 2

WEBSERVICES_DATA_ELSEVIER = {
    'name': "Elsevier",
    'url': 'https://staging.elsapi-np.elsst.com/content/metadata/article?query=((available-online-date+AFT+{start_date})+(available-online-date+BEF+{end_date}))+OR+((vor-available-online-date+AFT+{start_date})+(vor-available-online-date+BEF+{end_date}))+affil("U.K."+OR+"United+Kingdom"+OR+"UNITED+KINGDOM")&view=JISC',
    # LIVE 'url': 'https://api.elsevier.com/content/metadata/article?query=((available-online-date+AFT+{start_date})+(available-online-date+BEF+{end_date}))+OR+((vor-available-online-date+AFT+{start_date})+(vor-available-online-date+BEF+{end_date}))+affil("U.K."+OR+"United+Kingdom"+OR+"UNITED+KINGDOM")+content-type(JL)&view=JISC',
    'query': INCOMING_NOTIFICATION_QUERY,
    'frequency': 'daily',
    'active': True,
    'email': "YYYY@YYYY.ac.uk",
    'engine': ELSEVIER,
    'wait_window': 8,
    'publisher': True
}


# Dicts for converting particular Crossref "type" or "subtype" values into more useful article-type values
CROSSREF_TYPE_MAP = {
    "proceedings-article": "proceedings"
}
CROSSREF_SUBTYPE_MAP = {
    "preprint": "article-preprint"
}
# Dict converts Crossref "type" & any "subtype" to notification category
# - see `note.py` NotificationMetadata class for possible categories
CROSSREF_CATEGORY_MAP = {
    "journal-article": {None: "JA"},
    "monograph": {None: "B"},
    "book-chapter": {None: "BC"},
    "report": {None: "R"},
    "posted-content": {"preprint": "P", "other": "O", None: "O"},
    "proceedings-article": {None: "CP"},
}

### ELasticsearch Mapping Types - for use in Mapping definition dicts (see MAPPINGS below) ###
TEXT_FIELD_WITH_KEYWORD = {
    "type": "text",
    "fields": {
        "keyword": {
            "type": "keyword"
        }
    }
}
TEXT_FIELD = {"type": "text"}
KEYWORD_FIELD = {"type": "keyword"}
KEYWORD_NOT_INDEXED_FIELD = {"type": "keyword", "index": False}
IGNORE_FIELD = {"type": "keyword", "index": False}
DATE_FIELD = {"type": "date"}
INTEGER_FIELD = {"type": "integer"}
BOOL_FIELD = {"type": "boolean"}
IGNORE_OBJECT = {"enabled": False}

#
### ELASTICSEARCH (Version 8) MAPPINGS FOR HARVESTER INDEXES ###
#
# One Elasticsearch mapping per engine == harvester index

# EPMC Mapping - only the fields of actual (or potential) interest are indexed - all others are ignored
# dynamic field mapping is disabled as is creation of _all index.
EPMC_MAPPING = {
    "dynamic": False,
    "properties": {
        # "publicationStatus": IGNORE_FIELD,
        # "fullTextUrlList": IGNORE_OBJECT,
        # "meshHeadingList": IGNORE_OBJECT,
        # "fullTextIdList": IGNORE_OBJECT,
        # "language": IGNORE_FIELD,
        # "source": IGNORE_FIELD,
        # "nihAuthMan": IGNORE_FIELD,
        "authorIdList": {
            "properties": {
                "authorId": {
                    "properties": {
                        "type": KEYWORD_FIELD,
                        "value": KEYWORD_FIELD
                    }
                }
            }
        },
        # "epmcAuthMan": IGNORE_FIELD,
        # "affiliation": IGNORE_FIELD,
        # "journalInfo": IGNORE_OBJECT,
        # "id": IGNORE_FIELD,
        "isOpenAccess": KEYWORD_FIELD,
        # "dateOfRevision": IGNORE_FIELD,
        # "hasBook": IGNORE_FIELD,
        # "subsetList": IGNORE_OBJECT,
        "grantsList": {
            "properties": {
                "grant": {
                    "properties": {
                        "grantId": KEYWORD_FIELD,
                        "agency": KEYWORD_FIELD,
                        # "acronym": IGNORE_FIELD,
                        # "orderIn": IGNORE_FIELD
                    }
                }
            }
        },
        # "hasDbCrossReferences": IGNORE_FIELD,
        # "dateOfCompletion": IGNORE_FIELD,
        # "authorString": IGNORE_FIELD,
        # "tmAccessionTypeList": IGNORE_OBJECT,
        # "keywordList": IGNORE_OBJECT,
        "license": TEXT_FIELD,
        # "hasTextMinedTerms": IGNORE_FIELD,
        # "pubYear": IGNORE_FIELD,
        "authorList": {
            "properties": {
                "author": {
                    "properties": {
                        # "collectiveName": IGNORE_FIELD,
                        # "firstName": IGNORE_FIELD,
                        # "lastName": IGNORE_FIELD,
                        "authorAffiliationDetailsList": {
                            "properties": {
                                "authorAffiliation": {
                                    "properties": {
                                        "affiliation": KEYWORD_FIELD
                                    }
                                }
                            }
                        },
                        # "initials": IGNORE_FIELD,
                        # "fullName": IGNORE_FIELD,
                        "authorId": {
                            "properties": {
                                "type": KEYWORD_FIELD,
                                "value": KEYWORD_FIELD
                            }
                        }
                    }
                }
            }
        },
        # "abstractText": IGNORE_FIELD,
        # "commentCorrectionList": IGNORE_OBJECT,
        # "bookOrReportDetails": IGNORE_OBJECT,
        # "citedByCount": IGNORE_FIELD,
        # "doi": IGNORE_FIELD,
        # "pubModel": IGNORE_FIELD,
        # "title": IGNORE_FIELD,
        # "pubTypeList": IGNORE_OBJECT,
        # "dataLinksTagsList": IGNORE_OBJECT,
        # "bookid": IGNORE_FIELD,
        # "firstIndexDate": IGNORE_FIELD,
        # "hasTMAccessionNumbers": IGNORE_FIELD,
        # "inPMC": IGNORE_FIELD,
        "firstPublicationDate": DATE_FIELD,
        "electronicPublicationDate": DATE_FIELD,
        # "authMan": IGNORE_FIELD,
        # "hasData": IGNORE_FIELD,
        # "hasReferences": IGNORE_FIELD,
        # "chemicalList": IGNORE_OBJECT,
        # "pageInfo": IGNORE_FIELD,
        # "embargoDate": IGNORE_FIELD,
        # "hasSuppl": IGNORE_FIELD,
        # "pmid": IGNORE_FIELD,
        # "hasLabsLinks": IGNORE_FIELD,
        # "dateOfCreation": IGNORE_FIELD,
        # "investigatorList": IGNORE_OBJECT,
        # "manuscriptId": IGNORE_FIELD,
        # "dbCrossReferenceList": IGNORE_OBJECT,
        # "fullTextReceivedDate": IGNORE_FIELD,
        # "pmcid": IGNORE_FIELD,
        # "inEPMC": IGNORE_FIELD,
        "hasPDF": KEYWORD_FIELD
    }
}

# Crossref Mapping - only the fields of actual (or potential) interest are indexed - all others are ignored
# dynamic field mapping is disabled as is creation of _all index.
CROSSREF_MAPPING = {
    "dynamic": False,
    "properties": {
        "funder": {
            "properties": {
                "award": KEYWORD_FIELD,
                # "doi-asserted-by": IGNORE_FIELD,
                "name": KEYWORD_FIELD,
                "DOI": KEYWORD_FIELD
            }
        },
        # "is-referenced-by-count": IGNORE_FIELD,
        # "deposited": IGNORE_OBJECT,
        # "prefix": IGNORE_FIELD,
        # "subject": IGNORE_FIELD,
        # "link": {
        #     "properties": {
        #         "content-version": IGNORE_FIELD,
        #         "content-type": IGNORE_FIELD,
        #         "intended-application": IGNORE_FIELD,
        #         "URL": IGNORE_FIELD
        #     }
        # },
        # "issn-type": {
        #     "properties": {
        #         "type": IGNORE_FIELD,
        #         "value": IGNORE_FIELD
        #     }
        # },
        # "language": IGNORE_FIELD,
        # "source": IGNORE_FIELD,
        # "title": IGNORE_FIELD,
        "type": KEYWORD_FIELD,
        # "URL": IGNORE_FIELD,
        # "relation": IGNORE_OBJECT,
        # "reference": {
        #     "properties": {
        #         "volume": IGNORE_FIELD,
        #         "volume-title": IGNORE_FIELD,
        #         "year": IGNORE_FIELD,
        #         "author": IGNORE_FIELD,
        #         "doi-asserted-by": IGNORE_FIELD,
        #         "journal-title": IGNORE_FIELD,
        #         "article-title": IGNORE_FIELD,
        #         "first-page": IGNORE_FIELD,
        #         "key": IGNORE_FIELD,
        #         "DOI": IGNORE_FIELD
        #     }
        # },
        # "score": IGNORE_FIELD,
        # "member": IGNORE_FIELD,
        # "short-container-title": IGNORE_FIELD,
        # "reference-count": IGNORE_FIELD,
        # "assertion": {
        #     "properties": {
        #         "name": IGNORE_FIELD,
        #         "label": IGNORE_FIELD,
        #         "value": IGNORE_FIELD,
        #         "group": IGNORE_OBJECT,
        #         "order": IGNORE_FIELD
        #     }
        # },
        # "issued": IGNORE_OBJECT,
        "DOI": KEYWORD_FIELD,
        # "alternative-id": IGNORE_FIELD,
        # "journal-issue": IGNORE_OBJECT,
        # "issue": IGNORE_FIELD,
        # "indexed": IGNORE_OBJECT,
        "author": {
            "properties": {
                # "given": IGNORE_FIELD,
                # "sequence": IGNORE_FIELD,
                "ORCID": KEYWORD_FIELD,
                "affiliation": {
                    "properties": {
                        "name": KEYWORD_FIELD
                    }
                },
                # "authenticated-orcid": IGNORE_FIELD,
                # "family": IGNORE_FIELD
            }
        },
        # "created": IGNORE_OBJECT,
        # "ISSN": IGNORE_FIELD,
        # "archive": IGNORE_FIELD,
        # "abstract": IGNORE_FIELD,
        # "references-count": IGNORE_FIELD,
        # "volume": IGNORE_FIELD,
        # "license": {
        #     "properties": {
        #         "content-version": IGNORE_FIELD,
        #         "delay-in-days": IGNORE_FIELD,
        #         "start": IGNORE_OBJECT,
        #         "URL": IGNORE_FIELD
        #     }
        # },
        # "published-print": IGNORE_OBJECT,
        # "update-policy": IGNORE_FIELD,
        # "container-title": IGNORE_FIELD,
        # "content-domain": IGNORE_OBJECT,
        # "publisher": IGNORE_FIELD,
        # "page": IGNORE_FIELD
    }
}

# Incoming Notification Mapping used by both PubMed and Elsevier - only the fields of actual (or potential) interest
# are indexed - all others are ignored. Dynamic field mapping is disabled
NOTE_MAPPING = {
    "dynamic": False,
    "properties": {
        "metadata": {
            "properties": {
                "author": {
                    "properties": {
                        "identifier": {
                            "properties": {
                                "id": KEYWORD_FIELD,
                                "type": KEYWORD_FIELD
                            }
                        },
                        "affiliations": {
                            "properties": {
                                "identifier": {
                                    "properties": {
                                        "id": KEYWORD_FIELD,
                                        "type": KEYWORD_FIELD
                                    }
                                },
                                "org": KEYWORD_FIELD,
                                "dept": IGNORE_FIELD,
                                "street": IGNORE_FIELD,
                                "city": IGNORE_FIELD,
                                "state": IGNORE_FIELD,
                                "postcode": IGNORE_FIELD,
                                "country": IGNORE_FIELD,
                                "country_code": IGNORE_FIELD,
                                "raw": KEYWORD_FIELD
                            }
                        },
                        # "name": {
                        #     "properties": {
                        #         "firstname": IGNORE_FIELD,
                        #         "surname": IGNORE_FIELD,
                        #         "fullname": IGNORE_FIELD
                        #     }
                        # }
                    }
                },
                "funding": {
                    "properties": {
                        "identifier": {
                            "properties": {
                                "id": KEYWORD_FIELD,
                                "type": KEYWORD_FIELD
                            }
                        },
                        "name": KEYWORD_FIELD,
                        "grant_numbers": KEYWORD_FIELD
                    }
                }
            }
        }
    }
}


# Look-up dict of mappings - used to select the appropriate mapping for the particular engine
HARVESTER_MAPPINGS = {
    # Engine: Mapping dict
    "epmc": EPMC_MAPPING,
    "pubmed": NOTE_MAPPING,
    "crossref": CROSSREF_MAPPING,
    "elsevier": NOTE_MAPPING
}

# Standard local config file
LOCAL_CONFIG = os.path.expanduser("~/.pubrouter/harvester.cfg")
