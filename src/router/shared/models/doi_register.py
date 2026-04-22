"""
    Model for DOI Register index and associated code for calculating metadata metrics used for deduplication.

    The DOI Register table has a record for each DOI that has been processed by Router.

Author: Jisc
"""
import re
from copy import deepcopy
from operator import itemgetter
from flask import current_app
from octopus.lib import dataobj
from octopus.lib.data import select_tuple_arr_formatter
from octopus.lib.dates import now_str
from router.shared.mysql_dao import DoiRegisterDAO

# Regex checking string for creative commons URLs
# CC_URL_CHECKER_REGEX = r'^https?:\/\/creativecommons\.org\/licenses\/by(?:-nc)?(?:-nd|-sa)?\/[1-4]\.[0]\/$'
# regex_cc_url = re.compile(CC_URL_CHECKER_REGEX)

# Regex to check for Creative Commons strings like: "cc0" | "ccby" | "cc by" | "cc-by" | "ccbync" | "cc by nc" etc. etc.
CC_NAME_CHECKER_REGEX = r'^cc(?:0|[ -]?by)(?:[ -]?nc)?(?:[ -]?(?:nd|sa))?$'
regex_cc_name = re.compile(CC_NAME_CHECKER_REGEX)

PUBLISHER_RANK = 1

# Metadata rating
ULTRA = 0
HIGH = 1
MED = 2
LOW = 3
NONE = 4
# Dict that describes the ratings
_rating_desc = {
    ULTRA: "Very high",
    HIGH: "High",
    MED: "Medium",
    LOW: "Low",
    NONE: "None"
}

# Duplicate levels - IMPORTANT: duplicate levels are DIFFERENT from Metadata rating levels (see above)
DUP_NONE = 0
DUP_ULTRA_DIFF = 1
DUP_ANY_DIFF = 5
DUP_WITH_PDF = 6
DUP_ALL = 9
# Defines/describes "duplicate levels" - this is used to populate GUI Select and provide display information.
_duplicate_levels = [
    (DUP_NONE, "No duplicates", "No duplicates"),
    (DUP_ULTRA_DIFF, "Duplicates with Enhanced/Corrected VoR or first with PDF",
     "Duplicate notifications with article-version 'Enhanced/Corrected VoR', or the FIRST with a full-text PDF (no PDF received previously)"),
    ## THE FOLLOWING OPTIONS MAY BE INTRODUCED IN SUBSEQUENT RELEASE when comprehensive functionality is provided
    # (2, "With changed counts (plus the above)",
    #  "Duplicates with increased counts (e.g. number of authors, funders etc.), or article-version of 'Enhanced/Corrected VoR', or first with a PDF"),
    # (3, "With new high ranked metadata (plus the above)",
    #  "Duplicates with additional high ranked metadata, or changed counts (number of authors, funders etc.), or with article-version of 'Enhanced/Corrected VoR', or first with a PDF"),
    # (4, "With new medium ranked metadata (plus the above)",
    #  "Duplicates with additional medium or high ranked metadata, or changed counts (number of authors, funders etc.), or with article-version of 'Enhanced/Corrected VoR', or first with a PDF"),
    # (5, "With new low ranked metadata (plus the above)",
    #  "Duplicates with additional low, medium or high ranked metadata, or changed counts (number of authors, funders etc.), or with article-version of 'Enhanced/Corrected VoR', or first with a PDF"),
    (DUP_ANY_DIFF, "Duplicates with additional metadata or first with PDF",
     "Duplicate notifications with version 'Enhanced/Corrected VoR', or containing additional metadata, or the FIRST with a full-text PDF (no PDF received previously)"),
    (DUP_WITH_PDF, "Duplicates with additional metadata or with a full-text PDF",
     "Duplicate notifications with version 'Enhanced/Corrected VoR', or containing additional metadata, or with a full-text PDF (even if a PDF was previously received)"),
    (DUP_ALL, "All duplicates", "All duplicate notifications whether or not they have additional metadata fields or files")
]

##############
# The following set of functions (which return Boolean or None) are used in the analysis of a notification
# to calculate the duplication metrics - specifically to decide which bits in a bit-field are to be set On/Off.
##############


def _is_pub_date_full(date_str):
    """
    Check if we have a full publication date: "YYYY-MM-DD"
    :param date_str: Date string
    :return: None - no date string; True - Full date; False - partial date
    """
    if date_str:
        return len(date_str) >= 10
    return None


def _lic_is_open(lic_dict):
    """
    Check if licence dict is Open licence or Not
    :param lic_dict:
    :return: None - if problem with the dict; True - Licence is Open; False - licence NOT open
    """
    if lic_dict:
        url = lic_dict.get("url")
        if url:
            # Iterate through all strings that identify an open license
            for keyword in current_app.config.get("OPEN_LICENCE_KEYWORD_LIST", []):
                if keyword in url:
                    return True
            return False
        else:
            lic_type = lic_dict.get("type")
            if lic_type:
                return regex_cc_name.match(lic_type) is not None  # Return True or False
    return None


def _id_is_doi(id_dict):
    """
    Check if id dict is a DOI
    :param id_dict: dict - Identifier { "id": "id-value", "type": "type-of-id"}
    :return:  None - if problem with the dict; True - ID is a DOI; False - ID is NOT a DOI
    """
    if id_dict and id_dict.get("id"):
        id_type = id_dict.get("type")
        if id_type:
            return id_type == "doi"  # Return True or False
    return None


# def _link_is_fulltext(link_dict):
#     """
#     Check if link is to full-text
#     :param link_dict:
#     :return: True - If link is to full text; None - problem with dict or NOT full text
#     """
#     if link_dict and link_dict.get("cloc"):
#         link_type = link_dict.get("type")
#         link_format = link_dict.get("format")
#         if link_type == "fulltext" and link_format == "application/pdf":
#             return True
#         if link_type == "package" and link_format == "application/zip":     # QQQ - erroneous if zip has no PDF
#             return True
#     return None


def _has_funding(fund_dict):
    """
    Determine if a funder is present
    :param fund_dict:
    :return: Boolean - True: Funding dict is populated; False: No funder
    """
    return True if fund_dict else False


def _has_funder_identifier(fund_dict):
    """
    Determine if there are any Funder identifiers
    :param fund_dict: Funder dict
    :return: Integer - Number of funder identifiers
    """
    return len(fund_dict.get("identifier", []))


def _has_funder_grants(fund_dict):
    """
    Determine if there are any Funder Grants
    :param fund_dict: Funder dict
    :return: Integer - Number of funder grants
    """
    return len(fund_dict.get("grant_numbers", []))


def _is_author(auth_dict):
    """
    Determine if this is an author - assume that all members of author list are indeed authors
    :param auth_dict:   author dict
    :return: True (if auth_dict not empty) otherwise False
    """
    return auth_dict != {} 


def _is_corresp_author(auth_dict):
    """
    Determine if this is a Corresponding author
    :param auth_dict:   author dict
    :return: True: Corresponding author; False: other author
    """
    return auth_dict.get("type") == "corresp"


def _auth_has_orcid(auth_dict):
    """
    Determine if author has an ORCID 
    :param auth_dict:    author dict
    :return: True if there is an ORCID Id.
    """
    for id_dict in auth_dict.get("identifier", []):
        if id_dict.get("type") == "orcid" and id_dict.get("id"):
            return True
    return False


def _auth_has_struct_affs(auth_dict):
    """
    Determine if author has structured affiliations
    :param auth_dict:    author dict
    :return: Number of structured affiliations
    """
    num_affs = 0
    for aff_dict in auth_dict.get("affiliations", []):
        _aff_dict = aff_dict.copy()     # take copy so we don't alter the original list in following code
        _aff_dict.pop("raw", None)      # Remove any "raw" element
        # If affiliation dict NOT empty after removing "raw" value
        if _aff_dict:
            num_affs += 1
    return num_affs


def _auth_has_aff_ids(auth_dict):
    """
    Count the number of author structured affiliations that include at least one Org Id
    :param auth_dict:    author dict
    :return: Number of affiliations that contain at least 1 org Identifier
    """
    num_ids = 0
    for aff_dict in auth_dict.get("affiliations", []):
        # If aff dict contains a non-empty "identifier" list, then we have Org Ids
        if aff_dict.get("identifier"):
            num_ids += 1
    return num_ids


def _is_evor_or_cvor(v):
    """
    Article version is CVoR or EVor or C/EVoR
    :param v:
    :return: True if value is one of CVOR, EVOR or C/EVOR, otherwise False
    """
    return v in ("EVOR", "CVOR", "C/EVOR")


### Metadata Rating Defintions ###
# This dict defines all aspects of rating for individual metadata fields.
# The dict keys correspond to metadata fields. The dict values have one of two forms: simple-tuple and complex-list.
# Each of these make use of a standard tuple:
# * Standard-tuple: (Bit-number, "supplementary-description", "Full-description", Rating-value, "count-key" or None)
#   - this determines which bit is set, & provides additional text to append to field name (when outputting commentary),
#     the rating value to apply, and whether a count of field entries is required.
# _base_eval_dict: Dict values:
# * Simple form - (standard-tuple)
# * Complex form - [(func-name OR "specific-value", (standard-tuple-True), (standard-tuple-False) or None), ...]
# For the Complex form, the field value is either passed to the function or compared with the specific-value, if the
# result is True then the first standard-tuple is applied, if False then the second tuple, if present, is applied
# If a "count-key" is specified then the number of occurrences of a bit being set ON are counted and stored in the
# counts dict.

### IMPORTANT: NEVER CHANGE BIT NUMBERS, otherwise historical comparisons will be incorrect, however you can add
# NEW bit-numbers.  You can also change existing Rating-value (ULTRA, HIGH... etc). If you specify additional
# "count-key"s then You will need to change _counts_desc dict, and more importantly, change various index mappings and
# object definitions.
_base_eval_dict = {
    # Simple form
    # "field": (Bit-number, "field-supplementary-description", "Full-description", Rating-value, "Count-key" or None)
    # Complex form
    # "field": [(function-name OR "specific-value", (standard-tuple-True), None OR (standard-tuple-False)]
    "event": (1, "", "Publishing event", LOW, None),
    # Full-text (PDF) BIT number is particularly important for deciding whether to send duplicate (see _fulltext_mask)
    "has_pdf": (2, "Fulltext", "Article PDF", ULTRA, None),
    "metadata": {
        "journal": {
            "title": (3, "", "Journal title",  HIGH, None),
            "abbrev_title": (4, "", "Journal abbreviated title", LOW, None),
            "volume": (5, "", "Journal volume", MED, None),
            "issue": (6, "", "Journal issue", MED, None),
            "publisher": (7, "", "Publisher name", HIGH, None),
            "identifier": {
                "id": (8, "", "Publisher identifier", MED, None),
            }
        },
        "article": {
            "title": (9, "", "Article title", HIGH, None),
            "subtitle": (10, "", "Article subtitle", LOW, None),
            "type": (11, "", "Article type", LOW, None),  # Kind of article (e.g. 'research', 'commentary', 'review'...,
            # article-version: Set Bit 12 if AM, Bit 13 if VoR, or Bit 14 if EVoR or CVoR
            "version": [("AM", (12, "AM", "Article version - AM", HIGH, None), None),
                        ("VOR", (13, "VoR", "Article version - VoR", HIGH, None), None),
                        # ULTRA because possibly important changes, likely in duplicate rather than first notification
                        # This BIT is particularly important for deciding whether to send duplicate (see _evor_or_cvor_mask)
                        (_is_evor_or_cvor, (14, "EVoR or CVoR", "Article version - EVoR or CVoR", ULTRA, None), None),
                        ],
            "start_page": (15, "", "Article page start", MED, None),
            "end_page": (16, "", "Article page end", MED, None),
            "page_range": (17, "", "Article page range", MED, None),
            "num_pages": (18, "", "Article number of pages", MED, None),
            "e_num": (41, "", "Electronic article number", MED, None),
            "language": (19, "", "Article language", LOW, None),
            "abstract": (20, "", "Article abstract", HIGH, None),
            # Set bit 21 if DOI present, 22 if non-DOI present
            "identifier": [(_id_is_doi,
                            (21, "DOI", "Article DOI", MED, None),
                            (22, "Other", "Non-DOI article identifier", LOW, None))],
            "subject": (23, "", "Subject keywords", LOW, None),
        },
        # If author set bit 24, if corresponding author set bit 25, if ORCID set bit 26; count authors and orcids
        "author": [(_is_author, (24, "Author", "Authors", HIGH, "n_auth"), None),
                   (_is_corresp_author, (25, "Corresp", "Corresponding author(s)", LOW, None), None),
                   (_auth_has_orcid, (26, "", "Author ORCIDs", HIGH, "n_orcid"), None),
                   (_auth_has_struct_affs, (42, "", "Author with structured affiliations", HIGH, "n_struct_aff"), None),
                   (_auth_has_aff_ids, (43, "", "Author with affiliation Org Ids", HIGH, "n_aff_ids"), None)
                   ],
        # Any contributor: set bit 27
        "contributor": (27, "", "Contributors", LOW, "n_cont"),
        "accepted_date": (28, "", "Accepted date", HIGH, None),  # "<date YYYY-MM-DD format>",
        # Set bit 29 if full Publication date, otherwise bit 30
        "publication_date": {
            "date": [(_is_pub_date_full,
                      (29, "Full", "Publication date (full)", HIGH, None),
                      (30, "Partial", "Publication date (partial)", HIGH, None))],
        },
        "publication_status": (31, "", "Publication status", HIGH, None),
        "history_date": (32, "", "History dates", LOW, "n_hist"),
        "funding": [(_has_funding, (33, "", "Funding information", HIGH, "n_fund"), None),
                    (_has_funder_identifier, (34, "Identifier", "Funder identifiers", HIGH, "n_fund_id"), None),
                    (_has_funder_grants, (35, "Grants", "Grant numbers", HIGH, "n_grant"), None)],
        "embargo": (36, "", "Embargo date", HIGH, None),
        # Set bit 37 if we have open licence and/or bit 38 if other licence
        "license_ref": [(_lic_is_open,
                         (37, "Open", "Open licence", HIGH, "n_lic"),
                         (38, "Other", "Other licence", HIGH, "n_lic"))],
        "peer_reviewed": (39, "", "Peer reviewed", LOW, None),
        "ack": (40, "", "Acknowledgements", LOW, None)
        # NOTE: 41 has been used above for "article.e_num" above; 42 for author._has_structured_aff, 43
        # for author._auth_has_aff_ids. So use 44 for next field that is added here
    }
}
_fulltext_mask = 1 << 2             # Convert Bit number 2 (fulltext) into bit value
_evor_or_cvor_mask = 1 << 14        # Convert Bit number 14 (article version is EVoR or CVoR) into bit value

_counts_desc = {
    "n_auth": "Author{}",
    "n_orcid": "Author ORCID{}",
    "n_fund": "Funder{}",
    "n_fund_id": "Funder Identifier{}",
    "n_grant": "Grant number{}",
    "n_lic": "Licence{}",
    "n_struct_aff": "Author{} with structured affiliation(s)",
    "n_aff_ids": "Author{} with affiliation Org Id(s)",
    "n_cont": "Contributor{}",
    "n_hist": "History date{}"
}
### The following dicts that are created from _base_eval_dict for performance reasons
# evaluation_dict (which controls processing) has the same hierarchical structure as _base_eval_dict, but the
# standard-tuple -> (Bit-number, "supplementary-description", "Full description", Rating-value, count-key) is replaced by
# (Bit-value calculated from Bit-number, count-key); the other 3 elements end up in _bit_field_info dict, keyed by Bit-value
evaluation_dict = {}    # This dict is accessed outside of this file, hence no underscore prefix
_bit_field_info = {
    # bit-value: [bit-number, "dot.path description", "Full-description", rating]
}
# Dict for storing initial counts of particular fields
_counts = {
    # count-key: 0
}
# Dict for storing bit-field-value associated with thing being counted
_counts_bit_field = {
    # count-key: Bit-field-value
}
# Bit masks for particular ratings - THIS DICT IS UPDATED BY THE INITIALISATION FUNCTION
_rating_mask_dict = {
    ULTRA: 0,
    HIGH: 0,
    MED: 0,
    LOW: 0,
    NONE: 0
}
# Bit masks for particular ratings, which have bits set for current level PLUS all higher levels. For example, the
# MED mask will be a combination of MED, HIGH and ULTRA masks in _rating_mask_dict - UPDATED BY INITIALISATION FUNCTION
_rating_or_better_mask_dict = {
    ULTRA: 0,
    HIGH: 0,
    MED: 0,
    LOW: 0,
    NONE: 0
}


def init_dicts(base_ctl_dic, path, new_ctl_dic):
    """
    Function that creates the following structures using the base control dict:
    * evaluation_dict
    * _bit_field_info dict
    * _rating_mask_dict
    * _counts dict - with an initial zero entry for each count required
    * _counts_bit_field dict - containing bit-field
    :param base_ctl_dic: Source control dict
    :param path: String - Dot.path for dict element (field)
    :param new_ctl_dic: New control dict that is being created
    :return: Nothing, but initialises the 3 dicts: evaluation_dict, _bit_field_info, _counts, _counts_bit_field
    """
    def _process_bit_tuple(bit_tuple, path):
        """
        Process the Tuple that contains
        (Bit-number, "supplementary-description", "Full-description", rating-value, count_key), converting it
        into a Bit field value (e.g. Bit 3 has bit field value of 8) which is returned.

        ALSO, populate the _bit_field_info, _rating_mask_dict dicts, initialises _counts & _counts_bit_field dicts:
        * _bit_field_info is keyed by bit-field-value and stores:
            [bit number, dot.path description, full-description, rating]
        * _rating_mask_dict is keyed by rating and stores bit mask of all fields with a particular rating
        :param bit_tuple: Tuple - (Bit-number, "supplementary-description", "Full-description", rating-value, count_key)
        :param path: String - Metadata field dot.path
        :return: Tuple: (Int - Bit field value, String - count_key or None).
                    (Also updates 3 dicts: _bit_field_info, _rating_mask_dict, _counts & _counts_bit_field).
        """
        bit, desc, full_desc, rating, count_key = bit_tuple
        desc = f"{path} {desc}" if desc else path
        bit_value = 1 << bit    # Convert bit number into its bit-field value (e.g. bit number 3 --> value 8)
        # { bit_value: [ Bit-number, Field-dot.path-desc, Full-description, Rating-value ] }
        _bit_field_info[bit_value] = [bit, desc, full_desc, rating]
        # Add bit_value to bit-mask for particular rating
        _rating_mask_dict[rating] |= bit_value
        if count_key:
            _counts[count_key] = 0
            _counts_bit_field[count_key] = bit_value
        return bit_value, count_key

    for key, val in base_ctl_dic.items():
        _path = path + "." + key if path else key       # Dot-path for field
        # If value is a sub-structure to process
        if isinstance(val, dict):
            new_ctl_dic[key] = {}
            init_dicts(val, _path, new_ctl_dic[key])
        # Else value is a processing specification tuple: either Simple or Complex form
        else:
            if isinstance(val, list):
                new_list = []
                for (func_or_value, true_tuple, false_tuple) in val:
                    # complex_tuple structure: (function-name-or-comparison-value, (True-tuple), (False-tuple)) where
                    # True-tuple & False-tuple are used depending on Boolean value returned by function or comparison
                    new_tuple = (func_or_value,  # Function-name or specific-value
                                 _process_bit_tuple(true_tuple, _path),
                                 _process_bit_tuple(false_tuple, _path) if false_tuple is not None else None
                                 )
                    new_list.append(new_tuple)
                new_ctl_dic[key] = new_list
            else:
                new_ctl_dic[key] = _process_bit_tuple(val, _path)

    # Lastly set _rating_or_better_mask_dict
    mask_value = 0
    for key in [ULTRA, HIGH, MED, LOW, NONE]:
        mask_value |= _rating_mask_dict[key]
        _rating_or_better_mask_dict[key] = mask_value


####################################
#   Initialisation - Create `evaluation_dict` and `_bit_field_info` from _base_eval_dict
####################################
if not evaluation_dict:
    init_dicts(_base_eval_dict, "", evaluation_dict)


####################################
#   Operational Functions
####################################

def duplicate_level_description(level, lowercase=False):
    """
    Return long-description of duplicate level.
    :param level: Int - Level for which description required.
    :param lowercase: Boolean - True: Convert 1st char to lowercase, False: no change
    :return: String
    """
    for lev, short_desc, long_desc in _duplicate_levels:
        if level == lev:
            if lowercase:
                long_desc = long_desc[0].lower() + long_desc[1:]
            return long_desc
    return None


def bit_field_info(reqd_format="raw"):
    """
    Return _bit_field_info (control dict) with optional formatting for printing or other purposes (e.g. documentation).

    For example, to run this in Python console:
        from src.router.shared.models.doi_register import bit_field_info
        result = bit_field_info("dict_list")
        print(result)

    :param reqd_format: String - specifying format to return information in:
                "raw" - simply return _bit_field_info dict (which is keyed on bit-mask-value
                "dict_full" - return Dictionary of dicts, keyed by bit number
                "dict_list" - return Dictionary of lists, keyed by bit number. Each list has these contents:
                                [integer-mask-value, string-field-dot.specification, Full-description, String-rating, integer-weight]
                "rating_dict" - return dict keyed by Rating (ULTRA, HIGH, ...) containing array of dicts:
                                {"bit": ..., "mask_value": ..., "field": ..., "desc": ..., "weight": ...}
                "rating_dict_desc" = return dict keyed by Rating, each value being an array of Bit descriptions
    :return: dict - structure will depend on reqd_format
    """
    ret = "BAD PARAMETER"
    if reqd_format == "raw":
        ret = _bit_field_info
    elif reqd_format == "dict_full":
        ret = {array[0]: {"mask_value": key, "field": array[1], "desc": array[2], "rating": _rating_desc[array[3]]}
               for key, array in _bit_field_info.items()}
    elif reqd_format == "dict_list":
        ret = {array[0]: [key, array[1], array[2], _rating_desc[array[3]]] for key, array in _bit_field_info.items()}
    elif "rating_dict" in reqd_format:
        ret = {}
        full_output = reqd_format == "rating_dict"
        for key, array in _bit_field_info.items():
            rating = _rating_desc[array[3]]
            if full_output:
                stuff = {"bit": array[0], "mask_value": key, "field": array[1], "desc": array[2]}
            else:
                stuff = array[2]   # Long description
            if rating in ret:
                ret[rating].append(stuff)
            else:
                ret[rating] = [stuff]

    return ret


def _process_complex(bit_field, complex_list, data_val, counts):
    """
    Process complex evaluation control list.  Sample scenarios for evaluation control list:
        [("some-value", True-Bit-value, None)] - if metadata field equals "some-value" then a particular bit is set
        [("some-value", True-Bit-value, False-Bit-value)] - if the metadata field equals "some-value" then
                the True bit value is set, otherwise the False bit value is set
        [("value-1", True-Bit-value-1, None), ("value-2", True-Bit-value-2, None), ("value=3", True-Bit-value-3, None)] -
                If metadata field equals one of the "value-?" strings then the corresponding bit is set.
        [("func-name", True-Bit-value, False-Bit-value)] - If func-name(metadata-value) evaluates to True then
                True bit value is set, otherwise if False then False bit value is set
        [("func-name-1", True-Bit-value-1, False-Bit-value-1), ("func-name-2", True-Bit-value-2, False-Bit-value-2), ...] -
                In this case, multiple functions will be called for the same metadata-value (which could be a dict)
                & different bits will be set accordingly.
    :param bit_field: Integer - current bit-field value
    :param complex_list: List of tuples [(func-name or value, true-Bit-value, false-Bit-value), (...), ...]
    :param data_val: Metadata value
    :param counts: Dict of counts
    :return:
    """
    for v, bit_true_tuple, bit_false_tuple in complex_list:
        v_is_func = callable(v)
        bool_num_none = v(data_val) if v_is_func else data_val == v
        # bool_num_none can be None, True or False or a number
        if bool_num_none:
            bit_value, count_key = bit_true_tuple
        elif bit_false_tuple is not None:
            bit_value, count_key = bit_false_tuple
            if bool_num_none is not None:
                bool_num_none = 1   # Where bool_num_none was False or 0 we need it to be 1 below
        else:
            bit_value, count_key = None, None
        if bit_value is not None:
            bit_field |= bit_value  # Set the bit
            if count_key and bool_num_none:
                counts[count_key] += 1 if bool_num_none is True else bool_num_none
            if not v_is_func:  # for simple text comparisons, exit loop as soon as we have set a bit
                break
    return bit_field


def _set_bits(bit_field, counts, eval_dict, data_dict):
    """
    Evaluate metadata and set bits as appropriate in the bit_field. Function is called recursively, as needed.

    :param bit_field: Integer - current bit-field value
    :param counts: Dict - storing counters
    :param eval_dict: Dict - controls how data_dict is evaluated
    :param data_dict: Dict - Notification data dict
    :return: Integer - bit field (modified)
    """
    for key, eval_val in eval_dict.items():
        data_val = data_dict.get(key)  # metadata value
        if not data_val:
            # data_val is None or empty or False, so no bits to set
            continue
        # If eval_val is a dict, then recursion required
        if isinstance(eval_val, dict):
            # If data_val is a list, need to perform bit setting evaluation for each member of the list
            if isinstance(data_val, list):
                for dv in data_val:
                    bit_field = _set_bits(bit_field, counts, eval_val, dv)
            # Else data_val is scalar, so just evaluate
            else:
                bit_field = _set_bits(bit_field, counts, eval_val, data_val)
        # Else we are at a "leaf-node" for which we need to calculate bit setting(s)
        else:
            # eval_val is either a tuple (Simple) OR list (Complex)
            if isinstance(eval_val, tuple):
                bit_value, count_key = eval_val     # Simple case
            else:
                # Complex case - setting bit_value to None means _process_complex(...) is called below
                bit_value, count_key = None, None

            # List of data values, each of which must be processed
            if isinstance(data_val, list):
                for x in data_val:
                    if x:
                        if bit_value is None:
                            bit_field = _process_complex(bit_field, eval_val, x, counts)
                        else:
                            # Set the particular Bit in bit_field from the Bit-value
                            bit_field |= bit_value
                            break  # Can exit now that bit has been set
                if count_key:
                    counts[count_key] = len(data_val)
            else:  # Process single data value
                if bit_value is None:
                    bit_field = _process_complex(bit_field, eval_val, data_val, counts)
                else:
                    bit_field |= bit_value
                    if count_key:
                        counts[count_key] += 1
    return bit_field


def calc_bitfield_and_counts_from_note_dict(note_dict):
    """
    Calculate bitfield integer (where individual bits indicate presence/absence of particular metadata fields or
    field values) and tally counts for particular metadata fields.

    :param note_dict: Dict = Notification data dict
    :return: Tuple (Int, Dict) - (Bit-field-value, counts-dict)
    """
    bit_field = 0
    counts = _counts.copy()  # Initial dict - all values are zero
    bit_field = _set_bits(bit_field, counts, evaluation_dict, note_dict)
    return bit_field, counts


def describe_bit_settings(bit_field, off_bits=False, sort_by=None):
    """
    Using the passed bit_field (bit-mask) create 2 lists which describe the Bits that are set and those that are not.
    By default ONLY the 'bits-on' list is created, the 2nd is empty.
    The returned lists themselves contain lists (one for each bit) of the form:
        [Bit-number, Description, Rating]
    :param bit_field: Int - bit field (aka bit-mask)
    :param off_bits: Boolean - False: only create List for bits set On; True - Create both Lists
    :param sort_by: Integer or List of Integers, Whether results are sorted, and on which elements:
                        None - no sorting
                        0 - Sort on bit number
                        1 - Sort on Full description
                        2 - Sort on Rating
    :return: Tuple (List, List) - (List-for-bits-set-On, List-for-bits-set-Off)
    """
    bits_on = []
    bits_off = []
    for bit_val, val_list in _bit_field_info.items():
        if bit_field & bit_val:
            # append array [Bit-number, Expanded-description, Rating-value
            bits_on.append([val_list[0], val_list[2], val_list[3]])
        elif off_bits:
            bits_off.append([val_list[0], val_list[2], val_list[3]])
    if sort_by is not None:
        if not isinstance(sort_by, list):
            sort_by = [sort_by]
        bits_on.sort(key=itemgetter(*sort_by))
        if off_bits:
            bits_off.sort(key=itemgetter(*sort_by))
    return bits_on, bits_off


def bit_field_diff(bit_field_new, bit_field_old):
    """
    Compares 2 bit-field values (e.g. bit-field for newest notification compared with bit-field for older
    notification) and identifies Bits which are now On which were previously Off, and
    Bits Off which were previously On.  Returning results as 2 bit-field integers
    :param bit_field_new: Int - new bit-field value
    :param bit_field_old: Int - old bit-field value
    :return: Tuple (Int, Int) - (Bits-now-On, Bits-now-Off)
    """
    plus = (~ bit_field_old) & bit_field_new  # Bits previously Off but now set On (1)
    minus = (~ bit_field_new) & bit_field_old  # Bits previously On but now unset (0)
    return plus, minus  # These are both bit-fields (bit-masks)


def count_bits(value):
    """
    Count the number of bits that are set On.
    :param value: Int - Number (i.e. a bit-field) for which number of On-bits is required
    :return: Int - Count of number of bits set On
    """
    bits_to_count = value
    bits_set = 0
    while bits_to_count:
        bits_set += 1
        bits_to_count &= (bits_to_count - 1)
    return bits_set


def fields_with_rating(bit_field, rating):
    """
    Return a bit-field, where bits set ON have the specified rating
    :param bit_field: Int - Bit-field
    :param rating: Int - Required rating value (ULTRA, HIGH, MED, LOW, NONE)
    :return: Int - bit-field
    """
    return bit_field & _rating_mask_dict[rating]


def fields_with_rating_or_better(bit_field, rating):
    """
    Return a bit-field, where bits set ON have the specified rating or better rating . E.g. if MED rating is
    specified, the returned bit-field will have bits set ON for all entries with rating of MED, HIGH or ULTRA
    :param bit_field: Int - Bit-field
    :param rating: Int - Required rating value (ULTRA, HIGH, MED, LOW, NONE)
    :return: Int - bit-field
    """
    return bit_field & _rating_or_better_mask_dict[rating]


def compare_metrics(older, newer):
    """
    Compare 2 metrics dicts, with contents:
    {
        "m_date": ...,
        "bit_field": ...,
        "n_auth": ...,
        "n_orcid": ...,
        "n_fund": ...,
        "n_fund_id": ...,
        "n_grant": ...,
        "n_lic": ...,
        "n_struct_aff": ...,
        "n_aff_ids": ...,
        "n_cont": ...,
        "n_hist": ...
    }
    :param older: Older metric (from previous notification)
    :param newer: The most recent metric
    :return: Tuple: (Dict of DIFFERENCES, Int: Bits-newly-set-on, Int: counts-changed indicator = (see below)
    Differences dict: {
        "old_date": String - Timestamp of older notification,
        "old_bits": Bitfield - Older bitfield
        "curr_bits": Bitfield - Newer bitfield
        "n_auth": Positive or negative number - change in number of authors,
        "n_orcid": Positive or negative number - change in number of authors with Orcids,
        "n_fund": Positive or negative number - change in number of fundings,
        "n_fund_id": Positive or negative number - change in number of Funder Identifiers,
        "n_grant": Positive or negative number - change in number of Grant numbers,
        "n_lic": Positive or negative number - change in number of licences,
        "n_struct_aff": Positive or negative number - change in number of authors with at least one structured affiliation,
        "n_aff_ids": Positive or negative number - change in number of authors with structured affiliations containing any Org Ids,
        "n_cont": Positive or negative number - change in number of non-author contributors,
        "n_hist": Positive or negative number - change in number of history dates,
    }

    Counts-changed int indicator, has possible values:
        None - No counts have changed
        +1 - One or more counts has increased, none has decreased
        0 - Some counts have increased, others decreased
        -1 - One or more counts has decreased, none has increased
    """
    older_bit_field = older["bit_field"]
    newer_bit_field = newer["bit_field"]
    diff_dict = {
        "old_date": older["m_date"],
        "old_bits": older_bit_field,
        "curr_bits": newer_bit_field
    }
    new_bits = (~ older_bit_field) & newer_bit_field  # Bits previously Off but now set On (1)

    counts_increased = 0
    counts_decreased = 0
    # Calculate differences in `count` fields
    for key in _counts.keys():
        # Use get() for older in case a new metric counter has been added since original was calculated
        diff = newer[key] - older.get(key, 0)
        diff_dict[key] = diff
        if diff > 0:
            counts_increased = 1
        elif diff < 0:
            counts_decreased = -1
    counts_changed = counts_increased + counts_decreased if counts_increased or counts_decreased else None
    return diff_dict, new_bits, counts_changed


def calc_notification_metrics(note_dict):
    """
    Calculate metrics for notification data dict.  The resulting metrics dict has these keys:
    {
        "m_date": String, Timestamp of notification creation
        "bit_field": Integer, whose individual bits indicate presence/absence of particular metadata fields or values
        "n_auth": Int, number of Authors
        "n_orcid": Int, number of Authors with ORCIDS
        "n_fund": Int, number of Funders
        "n_fund_id": Int, number of Funder Identifiers
        "n_grant": Int, number of Grant numbers
        "n_lic": Int, number of licences
        "n_struct_aff": Int, number of authors with at least one structured affiliation (if one author has multiple
                        structured affiliations, then n_struct_aff will still be incremented by just 1  - i.e. it is
                        NOT counting total number of structured affs that an author has, but rather whether an author
                        has at least 1 structured aff)
        "n_aff_ids": Int, number of authors with structured affiliations containing any Org Ids (if one author has
                        multiple structured affs, and each of these has multiple Org Ids, then n_aff_ids will still be
                        incremented by just 1 - i.e. it is NOT counting total number of aff-Org-ids that an author has,
                        but rather whether an author has at least 1 aff-Org-id)
        "n_cont": Int, number of non-author contributors,
        "n_hist": Int, number of history dates
    }
    :param note_dict: Dict - notification
    :return: Dict
    """
    bit_field, counts = calc_bitfield_and_counts_from_note_dict(note_dict)
    ret = {
        "m_date": note_dict.get("created"),
        "bit_field": bit_field
    }
    ret.update(counts)  # merge counts into return dict
    return ret


def update_cumulative_metrics(cum_metrics, curr_metrics):
    """
    Update cumulative metrics dict from current metrics
    :param cum_metrics: Dict - cumulative metrics
    :param curr_metrics: Dict - current metrics
    :return: Updated cum_metrics dict
    """
    cum_metrics["m_date"] = curr_metrics["m_date"]
    # Turn on any bits in cum_metrics that were not already on
    cum_metrics["bit_field"] |= curr_metrics["bit_field"]
    # Update those count fields that have increased (we never decrease)
    for key in _counts.keys():
        # Use get() for cum_metrics in case a new metric counter has been added since original cum_metrics were calculated
        if curr_metrics[key] > cum_metrics.get(key, 0):
            cum_metrics[key] = curr_metrics[key]
    return cum_metrics


def duplicate_doi_check(unrouted):
    """
    This function determines whether a notification is a duplicate or not.

    It calculates various metrics for the unrouted notification, and will generate a new doi_record object (if not a
    duplicate) or may amend existing record. (NOTE that the doi_record is NOT saved here - that only occurs if
    the unrouted notification is actually routed).

    If it is a duplicate, it compares it with prior versions: the original and, possibly a later cumulative version,
    producing a list of metrics differences dicts (diff-dicts). The comparison-list will have either 1 or 2 elements:
        [dict-comparison-with-original, dict-comparison-with-later-cumulative**].
    See function `compare_metrics()` for description of the diff-dicts

    :param unrouted: Object - unrouted notification

    :return: Tuple (Doi-record Object or None, Note-metrics, Boolean: Note-from-publisher, Int: Duplicate-level, Comparison-list or None)

        Note-metrics includes DOI repetition counts (number of times DOI seen from Publisher & Harvester sources) as
        well as values calculated from the notification itself, but excludes the "m_date".

        Duplicate-level: 0 - NOT a duplicate
                         1 - Duplicate with first PDF (none previously received_ or is CVoR or EVoR
                         2 - Duplicate has changes in Numbers of things or #1
                         3 - Duplicate has additional HIGH value metadata or #2
                         4 - Duplicate has additional MED value metadata or #3
                         5 - Duplicate has additional LOW value metadata or #4
                         6 - Duplicate has a full-text PDF (not the first)
                         9 - Duplicate has no discernible difference (but existing content could have changed)

        Comparison-list: will be:
            * None if the DOI being processed has NOT been seen before;
            * A single element list if the DOI has been seen ONCE before, containing the difference between
              current metrics and original metrics
            * A two element list if the DOI has been seen TWO or more times (with different metrics), 1st element
              recording the difference between the current & original metrics, 2nd element recording the difference
              between the current metrics and the cumulative metrics (which records a consolidated view of metrics
              across all metadata previously received for this DOI)
    """
    note_metrics = None
    duplicate_level = 0  # Not a duplicate
    comparison_list = None
    note_from_pub = None
    doi = unrouted.article_doi  # Extract DOI value from unrouted notification
    if doi:
        unrouted_rank = unrouted.provider_rank  # Extract provider-rank from notification
        note_from_pub = unrouted_rank == PUBLISHER_RANK
        # Calculate current notification's metrics
        curr_metrics = calc_notification_metrics(unrouted.data)
        curr_bit_field = curr_metrics["bit_field"]
        # Attempt to retrieve DOI record
        doi_rec = DoiRegister.pull(doi, for_update=True)
        # DOI record NOT found, so this first time this DOI seen
        if doi_rec is None:
            # Create DOI-rec object
            doi_rec = DoiRegister({
                "id": doi,
                "best_rank": unrouted_rank,
                "p_count": 1 if note_from_pub else 0,
                "h_count": 0 if note_from_pub else 1,
                "orig": curr_metrics
            })
        else:  # DOI has been seen before: IS A DUPLICATE
            doi_rec.baseline()  # used to control later saving

            orig_metrics = doi_rec.get_metrics("orig")
            diff_dict, new_bits, counts_changed = compare_metrics(orig_metrics, curr_metrics)
            comparison_list = [diff_dict]
            # Get cumulative metrics - these will exist only for 2nd duplicate onwards
            cumulative_metrics = doi_rec.get_metrics("cum")
            if cumulative_metrics:
                # We want comparison with cumulative to override prior setting of new_bits and counts_changed
                diff_dict, new_bits, counts_changed = compare_metrics(cumulative_metrics, curr_metrics)
                comparison_list.append(diff_dict)

            counts_increased = counts_changed is not None and counts_changed >= 0

            # If is a publisher notification
            if note_from_pub:
                doi_rec.pub_count += 1
            else:   # Is a harvested notification
                doi_rec.harv_count += 1

            ## Duplicate_level indicates the importance of a duplicate: 1 - Most important to 9 - Least important ##

            # If first notification (`new_bits`) with a PDF OR current notification (`curr_bit_field`) is EVoR or CVoR
            if _fulltext_mask & new_bits or _evor_or_cvor_mask & curr_bit_field :
                duplicate_level = 1
            elif counts_increased:  # If some counts have increased
                duplicate_level = 2
            else:
                # Set the level according to whether any HIGH, MED or LOW status fields have been added
                for rating, level in [(HIGH, 3), (MED, 4), (LOW, 5)]:
                    if fields_with_rating(new_bits, rating):
                        duplicate_level = level
                        break
                # If duplicate level not set
                if not duplicate_level:
                    duplicate_level = DUP_WITH_PDF if curr_bit_field & _fulltext_mask else DUP_ALL

            # If we have a better rank
            if unrouted_rank < doi_rec.best_rank:
                doi_rec.best_rank = unrouted_rank

            # Update cumulative metrics if appropriate (new bits set or some counts have increased)
            if new_bits or counts_increased:
                # If cumulative metrics don't yet exist, use original
                doi_rec.set_metrics("cum", update_cumulative_metrics(cumulative_metrics or orig_metrics.copy(),
                                                                     curr_metrics))
        if curr_bit_field & _fulltext_mask:
            doi_rec.has_pdf = True

        # Finally, convert curr_metrics into Full-metrics; need to copy as don't want to modify curr_metrics
        tmp_metrics = curr_metrics.copy()
        del tmp_metrics["m_date"]
        note_metrics = {
            "p_count": doi_rec.pub_count,
            "h_count": doi_rec.harv_count,
            "val": tmp_metrics
        }
        # else Notification has no DOI
    else:
        doi_rec = None

    return doi_rec, note_metrics, note_from_pub, duplicate_level, comparison_list


def describe_differences(diff_dict):
    """
    Produce text description of differences between a duplicate and its earlier version.
    :param diff_dict: dup_diff dict of structure:
            {
                "old_date": String - Timestamp of older notification,
                "old_bits": Bitfield - Older bitfield
                "curr_bits": Bitfield - Newer bitfield
                "n_auth": Positive or negative number - change in number of authors,
                "n_orcid": Positive or negative number - change in number of authors with Orcids,
                "n_fund": Positive or negative number - change in number of fundings,
                "n_fund_id": Positive or negative number - change in number of funding IDs,
                "n_grant": Positive or negative number - change in number of grants,
                "n_lic": Positive or negative number - change in number of licences,
                "n_struct_aff": Positive or negative number - change in number of authors with at least one structured affiliation,
                "n_aff_ids": Positive or negative number - change in number of authors with structured affiliations containing any Org Ids,
                "n_cont": Positive or negative number - change in number of non-author contributors,
                "n_hist": Positive or negative number - change in number of history dates,
            }
    :return: Dict of lists: {
                "old_date": Date of first notification
                "new": [List of field descriptions present in new notification but not in old],
                "lost": [List of field descriptions that were present in old, but are not in new],
                "increased": [List describing increases in counts],
                "decreased": [List describing decreases in counts],
                "add_bits": Int: bit-field with bits set on for new fields or where counts have increased
                }
             or None if there are no differences
    """
    plus_bits, minus_bits = bit_field_diff(diff_dict["curr_bits"], diff_dict["old_bits"])
    # Sort by rating, then description
    new_fields, ignore = describe_bit_settings(plus_bits, False, sort_by=[2, 1])
    new_field_descs = [x[1] for x in new_fields]  # x[1] is the Description
    lost_fields, ignore = describe_bit_settings(minus_bits, False, sort_by=[2, 1])
    lost_field_descs = [x[1] for x in lost_fields]  # x[1] is the Description
    increased_counts = []
    decreased_counts = []
    for key in _counts.keys():
        # Use get() for diff_dict in case a new metric counter has been added since original diff_dict was calculated
        val = diff_dict.get(key)
        if val:
            abs_val = abs(val)
            msg = "{} {{}} {}".format(abs_val, _counts_desc[key].format("s" if abs_val > 1 else ""))
            if val < 0:
                decreased_counts.append(msg.format("less"))
            elif val > 0:
                increased_counts.append(msg.format("more"))
                # Update plus-bits with any fields that have additional counts
                plus_bits |= _counts_bit_field[key]

    if new_field_descs or lost_field_descs or increased_counts or decreased_counts:
        return {"old_date": diff_dict["old_date"],
                "new": new_field_descs,
                "lost": lost_field_descs,
                "increased": increased_counts,
                "decreased": decreased_counts,
                "add_bits": plus_bits}
    else:
        return None


class DoiRegister(dataobj.DataObj, DoiRegisterDAO):

    def __init__(self, raw=None, raw_trusted=True):
        """
        Model for a DoiRegisterRecord - stores data each DOI received

        Field definitions:
        {
            "id": "<DOI value>",
            "created": "<Date this record was created>",
            "updated": "<Date this record was last updated>",
            "category": "<String - Type of submission - see `decode_category` function in note.py for values>",
            "has_pdf": <Integer - Value 1 indicates that full-text received; otherwise None indicates metadata-only>,
            "routed_live": <Integer - 1: DOI routed to at least 1 Live repository; 0: routed to only Test repo(s)
            "best_rank": <Integer - best rank so far received>",
            "p_count": <Integer - number of times this DOI received from publisher to date - i.e. repeat submissions>,
            "h_count": <Integer - number of times this DOI received from harvester to date - i.e. repeat harvests>,
            "repos": ["<ID of repos to which article has been sent>"],
            "orig": {
                "m_date": <String timestamp of notification>,
                "bit_field": <Long integer bit field>,
                "n_auth": <Integer - number of authors>,
                "n_orcid": <Integer - num of authors with Orcids>,
                "n_fund": <Integer - number of fundings>,
                "n_fund_id": <Integer - number of funder ids>,
                "n_grant": <Integer - number of grant numbers>,
                "n_lic": <Integer - number of licences>,
                "n_struct_aff": <Integer - number of authors with at least one structured affiliation>
                "n_aff_ids": <Integer - number of authors with structured affiliations containing any Org Ids>
                "n_cont": Int, number of non-author contributors,
                "n_hist": Int, number of history dates,
            },
            "cum": {
                "m_date": <String timestamp of notification>,
                "bit_field": <Long integer bit field>,
                "n_auth": <Integer - number of authors>,
                "n_orcid": <Integer - num of authors with Orcids>,
                "n_fund": <Integer - number of fundings>,
                "n_fund_id": <Integer - number of funder ids>,
                "n_grant": <Integer - number of grant numbers>,
                "n_lic": <Integer - number of licences>,
                "n_struct_aff": <Integer - number of authors with at least one structured affiliation>
                "n_aff_ids": <Integer - number of authors with structured affiliations containing any Org Ids>
                "n_cont": Int, number of non-author contributors,
                "n_hist": Int, number of history dates,
            },
        }
        :param raw: raw data, a dictionary in a format like the one above. MUST have keys valid to the struct
            definition.
        :param raw_trusted: Boolean - True: Raw data comes from trusted source, like database;
                                      False: Raw data may not be OK, needs validating
        """
        struct = {
            "fields": {
                "id": {},
                "created": {"coerce": "utcdatetime"},
                "updated": {"coerce": "utcdatetime"},
                "category": {},
                "has_pdf": {"coerce": "integer"},
                "routed_live": {"coerce": "integer"},
                "best_rank": {"coerce": "integer"},
                "p_count": {"coerce": "integer"},
                "h_count": {"coerce": "integer"},
            },
            "lists": {
                "repos": {"contains": "field", "coerce": "integer"},
            },
            "objects": ["orig", "cum"],
            "structs": {
                "orig": {
                    "fields": {
                        "m_date": {"coerce": "utcdatetime"},
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
                },
                "cum": {
                    "fields": {
                        "m_date": {"coerce": "utcdatetime"},
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
        # self._add_struct(struct)
        super().__init__(raw=raw, struct=struct, construct_raw=(not raw_trusted))
        self._baseline = None

    @property
    def doi(self):
        return self.id

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

    @property
    def routed_live(self):
        return self._get_single("routed_live")

    @routed_live.setter
    def routed_live(self, val):
        self._set_single("routed_live", val)

    @property
    def best_rank(self):
        return self._get_single("best_rank", coerce=dataobj.to_int)

    @best_rank.setter
    def best_rank(self, val):
        self._set_single("best_rank", val, coerce=dataobj.to_int)

    @property
    def pub_count(self):
        return self._get_single("p_count", default=0, coerce=dataobj.to_int)

    @pub_count.setter
    def pub_count(self, val):
        self._set_single("p_count", val, coerce=dataobj.to_int)

    @property
    def harv_count(self):
        return self._get_single("h_count", default=0, coerce=dataobj.to_int)

    @harv_count.setter
    def harv_count(self, val):
        self._set_single("h_count", val, coerce=dataobj.to_int)

    @property
    def repos(self):
        return self._get_list("repos")

    @repos.setter
    def repos(self, val):
        self._set_list("repos", val)

    def add_repo_ids(self, repo_ids):
        """
        Add repo_ids to list of repo-ids, avoiding duplicates
        :param repo_ids: list of repository IDs
        :return: nothing
        """
        if repo_ids:
            # Remove any duplicates by creating a set, then convert back to list.  List is sorted so that function
            # save_if_changed() works as expected - comparing baseline and latest version of data dict
            self.repos = sorted(list(set(self.repos + repo_ids)))

    def get_metrics(self, orig_or_cum):
        """
        Get original or cumulative metrics dict from DoiRegister structure
        :param orig_or_cum: String - "orig" or "cum"
        :return: Dict - required rank dict
        """
        return self._get_single(orig_or_cum)

    def set_metrics(self, orig_or_cum, data):
        """
        Store rank dict, optionally setting the date value.
        :param orig_or_cum: String - "orig" or "cum"
        :param data: Dict - rank data (see _init comment for structure)
        :return: Nothing
        """
        self._set_single(orig_or_cum, data)

    # @classmethod
    # def pull_by_doi(cls, doi):
    #     """
    #     Get DOI record object for specified doi
    #     :param doi: String - DOI value
    #     :return: Record associated with DOI or None
    #     """
    #     # Get DOI record object for specified doi
    #     res = cls.object_query(q={"query": {"term": {"doi": doi}}})
    #     return res[0] if res else None

    def baseline(self):
        """
        Make a copy of current record
        :return: Nothing
        """
        self._baseline = deepcopy(self.data)

    def save_if_changed(self):
        """
        Determine if data has changed
        :return: Boolean - True: object data has changed; False: no change
        """
        if self._baseline != self.data:
            # Explicitly set `updated` rather than have MySQL automatically set it because, due to its use in
            # reports, we don't want it inadvertently modified by adhoc table / data changes in the future.
            self.updated = now_str()
            # If we have a previously created record, then update
            if self.created:
                self.update()
            else:
                self.insert()
        else:
            # Need to cancel the transaction that was started by doing the pull(for_update=True)
            self.cancel_transaction()

    def differences_between_cum_and_orig(self):
        """
        Describe the differences between cumulative & orig metrics (if cum-metrics are set)

        :return: Dict-of-differences OR None (if cum-metrics not set)
        """
        cumulative_metrics = self.get_metrics("cum")
        if cumulative_metrics:
            diff, ignore, ignore = compare_metrics(self.get_metrics("orig"), cumulative_metrics)
            return describe_differences(diff)
        return None

    @classmethod
    def routed_in_period(cls, from_date, to_date):
        """
        Report on unique articles matched to any institution in a specified period
        :param from_date: Date object - first date
        :param to_date: Date object - second date
        :return: List of tuples [(Category, Total routed, total-with-pdf), ...]
            Category is single char frmo this set:
            "J": "Journal article",
            "B": "Book",
            "C": "Conference output",
            "P": "Preprint",
            "R": "Report",
            "V": "Review",
            "L": "Letter",
            "O": "Other",
        """
        # From & To dates are passed TWICE, as are compared against both `created` & `updated` dates
        return cls.bespoke_pull(from_date, to_date, from_date, to_date, pull_name="bspk_simple_report")


# Dict, keyed by level, of duplicate level long descriptions
dup_desc_dict = select_tuple_arr_formatter(_duplicate_levels, "df")
# Dict, keyed by level, of duplicate level short descriptions with lowercase first char
dup_short_dict = select_tuple_arr_formatter(_duplicate_levels, "dsl")
# List of duplicate level long descriptions
dup_desc_list = select_tuple_arr_formatter(_duplicate_levels, "lf")
# Select field duplicate choices list
dup_choices_tuple_list = select_tuple_arr_formatter(_duplicate_levels,"ls")
