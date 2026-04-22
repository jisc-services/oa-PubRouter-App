"""
Functionality to format a Notification for display as an HTML Table.

Author: Jisc
"""
from router.jper_sword_out.dublincore_xml import format_funding_text
from router.shared.models.doi_register import evaluation_dict as doi_register_eval_dict
from router.shared.models.note import BaseNotification

UPPER = 1
TITLE = 2

def _format_dict_key_val(val_dict, label_key, data_key, label_format=None):
    """
    Format a dict with 2 keys, where value of key_1 is the label, and value of of data_key is the data - Output is:
        "label: data".  The label can be forced to UPPER or Title case.
    @param val_dict: Dict with at least 2 keys.
    @param label_key: String - Key of the label
    @param data_key: String - Key of the data
    @param label_format: Int - UPPER: force label to UPPER case; TITLE: force label to Title case.
    @return: String - "label: data"
    """
    label = val_dict.get(label_key)
    if label_format == UPPER:
        label = label.upper()
    elif label_format == TITLE:
        label = label.title()
    return label + ": " + val_dict.get(data_key, "")


def _format_dict(val_dict, key_list, join_with=", "):
    """
    Format contents of a dictionary, to produce string: "Key1: text..."
    @param val_dict: Dict whose contents are to be formatted
    @param key_list: List of keys 
    @param join_with: String - with which to join the "Key: value" snippets
    @return: String
    """
    parts = []
    for k in key_list:
        v = val_dict.get(k)
        if v:
            parts.append(f"{k.title()}: {str(v)}")
    return join_with.join(parts)


def _format_list(data, sep):
    """
    Convert a list of data to a comma separated string
    @param data: List of data
    @param sep: String - for separating phrases - NOT USED in this func
    @return: List of String - comma separated data.
    """
    return [", ".join(data)]


def _format_bool(data, sep):
    """
    Convert a bool value to "True" or "False" or ""
    @param data: Boolean value
    @param sep: String - for separating phrases - NOT USED in this func
    @return: List of String - boolean value
    """

    return [{None: "", True: "True", False: "False"}.get(data, "")]


def _format_ids(ids_list, sep):
    """
    Format a List of Identifiers like [{"type": type-of-id, "id": id-value}, ...] to produce a
    list of "id-type: id-value"
    strings. 
    @param ids_list: List of id dicts
    @param sep: String - for separating phrases - NOT USED in this func
    @return: List of strings ["id-type: id-value", ...]
    """
    return [_format_dict_key_val(id, "type", "id", UPPER) for id in ids_list]


def _format_auth(auth_list, sep=", "):
    """
    Format list of author or contributor dicts.
    @param auth_list: List of dicts
    @param sep: String - for separating phrases - separator for text elements
    @return: List of formatted author details
    """
    ret = []
    for auth in auth_list:
        contrib_text = BaseNotification.format_contrib_name(auth, True)
        if not contrib_text:
            continue
        # extract email and orcid
        for id in auth.get("identifier", []):
            contrib_text += sep + _format_dict_key_val(id, "type", "id", UPPER)
        # Affiliations
        for aff in auth.get("affiliations", []):
            raw = aff.get("raw")
            if raw:
                contrib_text += f"{sep}AFF: {raw}"
        ret.append(contrib_text)
    return ret


def _format_history_date(hist_list, sep):
    """
    Format list of history date dicts.
    @param hist_list: List of history date dicts
    @param sep: String - for separating phrases - NOT USED in this func
    @return: List  ["Date-type: date-value", ...]
    """
    return [_format_dict_key_val(hist, "date_type", "date", TITLE) for hist in hist_list]


def _format_funding(fund_list, sep="; "):
    """
    Format list of funding dicts.
    @param fund_list: List of dicts
    @param sep: String - for separating phrases - separator for text elements
    @return: List of funding text
    """
    ret = []
    for fund in fund_list:
        fund_string = format_funding_text(fund)
        if sep != "; ":
            fund_string = fund_string.replace("; ", sep)
        ret.append(fund_string)
    return ret


def _format_embargo(emb, sep="; "):
    """
    Format embargo dict.
    @param emb: embargo dict
    @param sep: String - for separating phrases - with which to join the "Key: value" snippets
    @return: List containing single embargo.
    """
    return [ _format_dict(emb, ["start", "end", "duration"], sep) ]


def _format_licence(lic_list, sep="; "):
    """
    Format list of licence dicts like:
    [
        {
            "start": "2015-07-05",
            "url": "https://creativecommons.org/licenses/by/4.0/",
            "title": "This is an open access article distributed in accordance with the Creative Commons Attribution 4.0 Unported (CC BY 4.0) license, which permits others to copy, redistribute, remix, transform and build upon this work for any purpose, provided the original work is properly cited, a link to the licence is given, and indication of whether changes were made. See: https://creativecommons.org/licenses/by/4.0/.",
            "type": "open-access",
            "version": "4.0"
        },
        {...}
    ]
    @param lic_list: - List of licence dicts
    @param sep: String - for separating phrases - with which to join the "Key: value" snippets
    @return: list of formatted license strings
    """
    return [_format_dict(lic, ["type", "start", "url", "title", "version", "best"], sep) for lic in lic_list]


processing_dict = {
    # The leaf elements of this dict have structure:
    #   "field": [Sort-order, "Metadata label", None or formatting-function]
    # IMPORTANT - Each 3 element list has an Integer Bit-mask appended to it (to make a 4 element list) by the
    # _init_processing_dict() function, so IT WILL END UP AS:
    #   "field": [Sort-order, "Metadata label", None or formatting-function, Bit-field-mask-value]
    # HOW IT IS USED:
    # This dict has a structure corresponding to that of a Notification. It is "walked" to extract corresponding 
    # entries from a notification. Each leaf node in this dict represents a metadata element that will be output
    # as a 2 column row in a table of metadata: with the "metadata-label" appearing in the 1st column, and the metadata 
    # extracted from the notification appearing in the 2nd column after appropriate formatting (determined by the 
    # presence or absence of a formatting-function).  The bit-field-mask-value is used in conjunction with the 
    # notification's duplicate-add-bit-mask (that identifies NEW metadata) to highlight those rows of metadata that
    # are new information compared to previous versions of the notification.
    #
    # The formatting-functions, are typically used to consolidate a list or dict into a sensible presentation. 
    # For example a list of values may be converted into a comma-separated string, or a list of dicts will
    # be converted into an appropriate string representation.
    "metadata": {
        "journal": {
            "title": [1, "Journal title",  None],
            "abbrev_title": [2, "Journal abbreviated title", None],
            "volume": [3, "Journal volume", None],
            "issue": [4, "Journal issue", None],
            "publisher": [5, "Publisher name", _format_list],
            "identifier": [6, "Publisher identifiers", _format_ids],
        },
        "article": {
            "title": [7, "Article title", None],
            "subtitle": [8, "Article subtitle", _format_list],
            "type": [9, "Article type", None],  # Kind of article (e.g. 'research', 'commentary', 'review'...,
            "abstract": [10, "Article abstract", None],
            "identifier": [11, "Article identifiers", _format_ids],
            "version": [12, "Article version", None ],
            "start_page": [13, "Article page start", None],
            "end_page": [14, "Article page end", None],
            "page_range": [15, "Article page range", None],
            "num_pages": [16, "Article number of pages", None],
            "e_num": [17, "Article e-location", None],
            "language": [18, "Article language", _format_list],
            "subject": [19, "Subject keywords", _format_list],
        },
        "author": [20, "Authors", _format_auth],
        "contributor": [21, "Contributors",  _format_auth],
        "accepted_date": [22, "Accepted date", None],
        "publication_date": {
            "date": [23, "Publication date", None],
            "publication_format": [24, "Publication format", None]
        },
        "publication_status": [25, "Publication status", None],
        "history_date": [26, "History dates", _format_history_date],
        "funding": [27, "Funding", _format_funding],
        "embargo": [28, "Embargo", _format_embargo],
        "license_ref": [29, "Licences", _format_licence],
        "peer_reviewed": [30, "Peer reviewed", _format_bool],
        "ack": [31, "Acknowledgements", None],
    }
}

def _init_processing_dict(proc_dict, duplicates_eval_dict):
    """
    Update the processing_dict (which controls formatting) by appending an Integer bit-mask to each list in the dict.
    The bit-mask value is obtained from the duplicates evaluation dict imported from doi_register.py
    
    @param proc_dict: Processing dict defined ablve
    @param duplicates_eval_dict: Evaluation dict from doi_register.py
    @return: Nothing (but proc_dict is updated)
    """
    def _get_bit_mask_value(eval_dict_entry):
        """
        Obtain a bit-mask value from duplicates evaluation dict entry.
        @param eval_dict_entry: an entry in duplicates evaluation dict, which may be a dict, tuple or list of tuples
        @return: Int - bit mask value
        """
        bit_mask_value = 0
        if eval_dict_entry:
            if isinstance(eval_dict_entry, dict):
                # We need to walk through the duplicates evaluation dictionary, extracting and consolidating
                # all bit-mask values by making a recursive function call
                for ved_keys, ved_vals in eval_dict_entry.items():
                    bit_mask_value |= _get_bit_mask_value(ved_vals)
            # We have a simple 2 element tuple: (bit-field-value, ...) from which we take the bit-field-value
            elif isinstance(eval_dict_entry, tuple):
                bit_mask_value = eval_dict_entry[0]
            else:
                # We have a list of tuples, each like:
                #   (func-or-str, (bit-field, ...), None) 
                # OR (func-or-str, (bit-field-a, ...), (bit-field-b, ...))
                # We build our bit-mask-value by combining all bit-field-values we can find
                for ignore, tuple_1, tuple_2 in eval_dict_entry:
                    bit_mask_value |= tuple_1[0]
                    if tuple_2:
                        bit_mask_value |= tuple_2[0]
        return bit_mask_value

    for field_name, list_or_dict in proc_dict.items():
        if isinstance(list_or_dict, dict):
            # Recursive call
            _init_processing_dict(list_or_dict, duplicates_eval_dict[field_name])
        else:
            # Must be a list - append bit-mask returned by _get_bit_mask_value
            list_or_dict.append(_get_bit_mask_value(duplicates_eval_dict.get(field_name)))

####################################
#   Initialisation - Update the processing_dict
####################################
_init_processing_dict(processing_dict, doi_register_eval_dict)


def _produce_list_of_formatted_metadata(process_ctl_dict, note_dict, out_list, sep):
    """
    Walks the process_ctl_dict (processing control dict) and extracts information from note_dict (notification),
    which is formatted and added to the out_list (along with other information).
    Format notification dict (or sub-structure dict). May be called recursively.
    @param process_ctl_dict: Processing control dict
    @param note_dict: Notification dict (or a sub-structure of it)
    @param out_list: List - Output information (list of lists)
    @param sep: String - for separating phrases - phrase separator (e.g. "; " or "<br>"
    @return: List of lists [[int-sort-order-value, int-bit-mask, string-label-text, [list-string-data-values]], ...]
    """
    # iterate of processing dict
    for k, dict_or_list in process_ctl_dict.items():
        # Get Notification data
        note_val = note_dict.get(k)
        if note_val is not None:
            # If we have a sub-structure processing dict
            if isinstance(dict_or_list, dict):
                # recursive call
                out_list = _produce_list_of_formatted_metadata(dict_or_list, note_val, out_list, sep)
            else:
                # We have processing-list: [ sort-order, label, format-function or None, Integer-bit-mask ]
                sort_order, label, func, bit_mask = dict_or_list
                # We append a list: [sort-order-value, bit-mask, label-text, [list-of-formatted-metadata-strings] ]
                out_list.append([sort_order, bit_mask, label, [note_val] if func is None else func(note_val, sep)])
    return out_list


def format_note(note, new_bits, as_html=True):
    """
    Format a notification, outputting a sorted list of lists.
    @param note: Notification object
    @param new_bits: Int-bit-field (see doi_register) - where bits set-On are fields new in this notification.
    @param as_html: Boolean - whether to format output as HTML or not
    @return: list of tuples [(Boolean: New-field-indicator, String: label, [List-of-formatted-metadata-string-values])]
    """
    out_list_of_lists = []        # Dict of output HTML blocks keyed by integer - sort order
    sep = "<br>" if as_html else "; "
    out_list_of_lists = _produce_list_of_formatted_metadata(processing_dict, note.data, out_list_of_lists, sep)
    out_list_of_lists.sort(key=lambda x: x[0])    # Sort on first element of each sub-list
    return [(True if new_bits & bit_mask else False, label, formatted_metadata_list)
            for ignore, bit_mask, label, formatted_metadata_list in out_list_of_lists]


def format_note_as_html(note, add_bits):
    """
    Format a notification as an HTML table
    @param note: Notification object
    @param add_bits: Int-bit-field (see doi_register) - where bits set-On are fields new or with additional counts
                     in this notification.
    @return: String - HTML table code
    """
    out_str = ["<table><tbody>"]
    for highlight, label, data_list in format_note(note, add_bits, as_html=True):
        out_str.append("<tr{}><th>{}</th><td>{}</td></tr>".format(' class="hi"' if highlight else '',
                                                                  label,
                                                                  '<hr>'.join(data_list)))
    out_str.append("</tbody></table>")
    return "\n".join(out_str)
