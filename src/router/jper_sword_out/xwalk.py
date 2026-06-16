"""
Module that handles the conversion of JPER json formatted notifications to XML suitable for delivery via SWORDv2
Xwalks:
  - to Eprints RIOXX XML
  - to Eprints XML
  - to DSpace RIOXX XML
  - to DSpace XML
"""
import re
from datetime import datetime
from octopus.lib import isolang
from octopus.lib.dates import now_str, ymd_to_dmy
from octopus.lib.dicttoxml import DictToXml
from router.jper_sword_out.dublincore_xml import extract_license_details, format_license_text, \
    format_provider_text, format_article_version_text, format_funding_text
from router.shared.models.note import NotificationMetadata, normalise_article_version
from router.jper_sword_out.models.dspace.dspace import DspaceVanilla, DspaceRioxx
from router.jper_sword_out.models.eprints.eprints import EprintsVanilla, EprintsRioxxPlus
from router.jper_sword_out.models.native.native import Native

# Regex test to check if a string ends with a filename suffix of at least 2 alphabetic chars like ".xxx"
name_has_suffix_regex = re.compile('\.[a-z]{2,}$')

# Value to use if no grants are specified for a funder (for RIOXX project)
DEFAULT_GRANT = ["unspecified"]


def _best_email_list(emails):
    """
    For a list of emails, returns the list of emails, ordered such that the email deemed to be the "best" is in the 0th
    position. We select the best email based on domain name, prioritising those with domain ac.uk, then with domain
    name edu, then gov.uk and finally any other.

    :param emails: emails to be sorted

    :return: list of emails with the "best" in the 0th position (returns original list if no best found)
    """

    # list of domains in order of preference
    ordered_domains = [".ac.uk", ".edu", ".gov.uk"]
    for domain in ordered_domains:
        for index, email in enumerate(emails):
            # if we make a match, reorder the list
            if email.endswith(domain):
                if index != 0:
                    best_email = emails.pop(index)
                    emails.insert(0, best_email)
                return emails
    return emails

def _normalise_type_from_tuple_list(type_, tuple_list, default):
    """
    Given an original 'type' return a normalised type from a list of tuples containing types and
    their respective values.

    :param type_: string
    :param tuple_list: List of tuples of possible type strings with their required values in the
                       XML.
    :param default: Default value if nothing matches
    :return: Matched value if type found in one of the dict's keys, otherwise default value.
    """
    # Everything is compared as UPPER case
    type_ = type_.upper()

    for key, value in tuple_list:
        if key in type_:
            return value

    return default

# rioxxterms:typeList Item Types
#   See: http://www.rioxx.net/schema/v2.0/rioxxterms/ (search for rioxxterms:typeList)
def _normalise_rioxxterms_type(type_):
    """
    Given a type, it returns a normalised rioxxterms type value.

    :param type_: string
    :return: string corresponding rioxxterms-type value (will default to "Other")
    """

    # Map of notification article type keywords to normalised Rioxxterms item type values.
    rioxxterms_types = [
        ('ARTICLE', 'Journal Article/Review'),
        ('REVIEW', 'Journal Article/Review'),
        ('MONOGRAPH', 'Monograph'),
        ('CHAPTER', 'Book chapter'),
        ('SECTION', 'Book chapter'),
        ('BOOK', 'Book'),
        ('PROCEEDING', 'Conference Paper/Proceeding/Abstract'),
        ('CONFERENCE', 'Conference Paper/Proceeding/Abstract'),
        ('ABSTRACT',  'Conference Paper/Proceeding/Abstract'),
        ('REPORT', 'Technical Report'),
        ('THESIS', 'Thesis')
    ]

    # Return matching type or default to 'other'
    return _normalise_type_from_tuple_list(type_, rioxxterms_types, "Other")


def _best_license_with_url(licenses):
    """
    Uses the "best" license flag to select the best license from the list of licenses.
    This license must also have a URL.

    :param licenses: list of licenses
    :return: the best license from the list or None
    """
    for license in licenses:
        if license.get("best") and license.get("url"):
            return license

    return None


def _format_embargo_end_text(end_date, prefix=''):
    """
    Construct string describing Embargo (converts YYYY-MM-DD to DD-MM-YYYY)

    :param end_date: date string in YYYY-MM-DD format
    :param prefix: String to prefix the returned text with

    :return: Formatted embargo string or empty string (if date string doesn't exist or can't be converted)
    """
    if end_date:
        try:
            return f"{prefix}Embargo end date: {ymd_to_dmy(end_date)}"
        except Exception:
            pass  # Ignore any issue with date conversion
    return ''


def _normalise_article_type(type_):
    """
    Given an article type, it returns a normalised Eprints type value

    :param type_: string
    :return: string - corresponding Eprints type value
    """

    # Mapping of Eprints item types
    eprints_types = [
        ('ARTICLE', 'article'),
        ('REVIEW', 'article'),
        ('SECTION', 'book_section'),
        ('CHAPTER', 'book_section'),
        ('BOOK', 'book'),
        ('MONOGRAPH', 'monograph'),
        ('PROCEEDING', 'conference_item'),
        ('CONFERENCE', 'conference_item'),
        ('ABSTRACT', 'conference_item'),
        ('OTHER', 'other'),
        ('THESIS', 'thesis'),
        ('PATENT', 'patent'),
        ('ARTIFACT', 'artifact'),
        ('EXHIBITION', 'exhibition'),
        ('COMPOSITION', 'composition'),
        ('PERFORMANCE', 'performance'),
        ('IMAGE', 'image'),
        ('VIDEO', 'video'),
        ('AUDIO', 'audio'),
        ('DATASET', 'dataset'),
        ('EXPERIMENT', 'experiment'),
        ('TEACHING_RESOURCE', 'teaching_resource'),
    ]
    # Return matching type or default to 'other'
    return _normalise_type_from_tuple_list(type_, eprints_types, "other")


def _normalise_eprints_contributor_type(type_):
    """
    EPRINTS Contributor Types

    Given a contributor type, it returns a normalise value
    http://www.loc.gov/loc.terms/relators/


    :param type_: string
    :return: Eprints contributor type
    """

    # Mapping of Eprints contributor types
    eprints_types = [
        ('AUTHOR', 'AUT'),
        ('CORRESP', 'AUT'),   # Corresponding author
        ('CREATOR', 'CRE'),
        ('CONTRIBUTOR', 'CTB'),
        ('EDITOR', 'EDT'),
        ('COLLABORATOR', 'CLB'),
    ]
    # Return normalised Eprint type, default to other type
    type_normalised = _normalise_type_from_tuple_list(type_, eprints_types, "OTH")
    return 'http://www.loc.gov/loc.terms/relators/' + type_normalised


def _create_history_date_string(history_date_dicts, prefix, separator='; ', sub_sep=' ', terminator="."):
    """
    From a list of history_date note objects, create a string representation of the history dates.
    Format is like so:
        {prefix}[{date_type} {date} {separator},]{terminator}

    :param history_date_dicts: List of history_date objects from a note
    :param prefix: Prefix, such as 'History:', to go before the string of history dates.
    :param separator: Separator to use between the history date strings
    :param sub_sep: Separator to use within sub-strings e.g. between type and date (typically ': ' or ' ')
    :param terminator: Terminator to end the string. Default is "."

    :return: Returns history date string (maybe be empty if not valid history dates)
    """
    date_string = ''
    history_strings = []
    for history in history_date_dicts:
        date = history.get("date")
        if date:
            try:
                history_strings.append(history.get("date_type", "") + sub_sep + ymd_to_dmy(date))
            except:
                pass  # ignore failed date conversion
    if history_strings:
        date_string = prefix + separator.join(history_strings) + terminator
    return date_string

def set_filename_extension_from_format(format):
        """
        given a format, it returns a normalised extension value

        :param format: string
        :return: string - corresponding extension value
        """

        # Dictionary for Formats ItemTypes
        formats_types = {'application/pdf': '.pdf',
                         'application/zip': '.zip',
                         'text/html': '.html',
                         'text/plain': '.txt'
                         }

        # Return matching extension value
        return formats_types.get(format, '')


def _add_common_dspace_dcterms_elements(dspace_xml, note):
    """
    Add dcterms:xxxx elements that are common to BOTH DSpace Vanilla and DSpace RIOXX XML.
    :param dspace_xml:  XML etree object
    :param note: Notification

    :return: art_vers.  NOTE: Also UPDATES the dspace_xml structure
    """
    def add_identifiers(dspace_xml, qual_tagname, identifiers_list):
        """
        Add identifier elements to the XML.

        :param dspace_xml: the etree XML structure being created
        :param qual_tagname: Qualified tagname e.g. "dcterms:identifier"
        :param identifiers_list: List of identifer objects {type: "id-type", id: "id-value"}

        :return: Nothing, but updates dspace_xml
        """
        for ident in identifiers_list:
            id = ident.get('id')
            if id:
                dspace_xml.add_element_with_value(qual_tagname, ident.get('type') + ': ' + id)

    # Create dcterms elements

    # metadata.language -> dcterms:language
    if note.article_language:
        dspace_xml.add_elements_with_values_list("dcterms:language", note.article_language)

    # metadata.journal.identifier -> <dcterms:source>
    add_identifiers(dspace_xml, "dcterms:source", note.journal_identifiers)

    # metadata.journal.publishers -> <dcterms:publisher>
    if note.journal_publishers:
        dspace_xml.add_elements_with_values_list("dcterms:publisher", note.journal_publishers)

    # metadata.provider.agent -> <dcterms:description>
    _temp = note.provider_agent
    if _temp:
        dspace_xml.add_element_with_value("dcterms:description", format_provider_text(_temp))

    # metadata.article.title -> dcterms:title
    _temp = note.article_title
    if _temp:
        dspace_xml.add_element_with_value("dcterms:title", _temp)

    # metadata.article.identifier -> <dcterms:identifier>
    add_identifiers(dspace_xml, "dcterms:identifier", note.article_identifiers)

    # article_subject -> <dcterms:subject>
    if note.article_subject:
        dspace_xml.add_elements_with_values_list("dcterms:subject", note.article_subject)

    # history_dates -> <dcterms:description>
    _history_info = []
    for hist_date in note.history_date:
        date = hist_date.get('date')
        if date:
            date_type = hist_date.get('date_type', "")
            _history_info.append(date_type + ' ' + date)
    if _history_info:
        dspace_xml.add_element_with_value("dcterms:description", 'History: ' + ", ".join(_history_info))

    # Licenses -> <dcterms:rights>
    art_vers = normalise_article_version(note.article_version)
    for lic in note.licenses:
        (lic_url, lic_start, lic_text) = extract_license_details(lic)
        if lic_url or lic_text:
            dspace_xml.add_element_with_value("dcterms:rights",
                                              format_license_text(lic_url, lic_start, lic_text, art_vers))

    # article_abstract -> <dcterms:abstract>
    _temp = note.article_abstract
    if _temp:
        dspace_xml.add_element_with_value("dcterms:abstract", _temp)

    # metadata.date_accepted -> <dc:dateAccepted>
    _temp = note.accepted_date
    if _temp is not None:
        dspace_xml.add_element_with_value("dcterms:dateAccepted", _temp)

    # metadata.journal.title or journal_abbrev_title -> <dc:bibliographicCitation>
    _citation = []
    _temp = note.journal_title or note.journal_abbrev_title
    if _temp:
        _citation.append(_temp)

    # metadata.journal_volume + journal_issue + article_page_range -> <dcterms:bibliographicCitation>
    _temp = note.journal_volume
    if _temp:
        _citation.append('volume ' + _temp)

    _temp = note.journal_issue
    if _temp:
        _citation.append('issue ' + _temp)

    _temp = note.article_page_range
    if _temp:
        _citation.append('page ' + _temp)
    else:
        _page = []
        _temp = note.article_start_page
        if _temp:
            _page.append(_temp)

        _temp = note.article_end_page
        if _temp:
            _page.append(_temp)

        # Either a start or and end page has been found
        if _page:
            _citation.append('page ' + ' - '.join(_page))

    _temp = note.article_e_num
    if _temp:
        _citation.append('article-number ' + _temp)

    if _citation:
        dspace_xml.add_element_with_value("dcterms:bibliographicCitation", ", ".join(_citation))

    # metadata.publication_date -> <dcterms:issued>
    _temp = note.get_publication_date_string()
    if _temp:
        dspace_xml.add_element_with_value("dcterms:issued", _temp)

    # metadata.peer_reviewed --> <pr:note>
    _temp = note.peer_reviewed
    if _temp is not None:
        dspace_xml.add_element_with_value("dcterms:description", f"Peer reviewed: {'True' if _temp else 'False'}")

    # metadata.ack -> <pr:note>
    _temp = note.ack
    if _temp:
        dspace_xml.add_element_with_value("dcterms:description", f"Acknowledgements: {_temp}")

    return art_vers

def _add_common_rioxxterms_elements(rioxx_xml, note):
    """
    Add rioxxterms:xxxx elements that are common to BOTH Eprints RIOXX and DSpace RIOXX XML.
    :param rioxx_xml:  XML etree object
    :param note: Notification

    :return: tuple (article_vers, pub_date, best_lic).
            ALSO NOTE the function UPDATES the dspace_xml structure by adding elements to it.
    """

    # <rioxxterms:version>	{0..1}
    article_vers = normalise_article_version(note.article_version)
    if article_vers:
        rioxx_xml.add_element_with_value("rioxxterms:version", article_vers)

    # <rioxxterms:version_of_record>	{0..1}
    for ident in note.article_identifiers:
        id_type = ident.get('type', '').lower()
        if id_type == "doi":
            doi = ident.get("id")
            if doi:
                rioxx_xml.add_element_with_value("rioxxterms:version_of_record", doi)
                break

    # <rioxxterms:type>  {0..1}
    art_type = note.article_type
    if art_type:
        rioxx_xml.add_element_with_value("rioxxterms:type", _normalise_rioxxterms_type(art_type))

    # <rioxxterms:publication_date>	{0..1}
    pub_date = note.get_publication_date_string()
    if pub_date:
        rioxx_xml.add_element_with_value("rioxxterms:publication_date", pub_date)

    # <ali:license_ref> {0..1}
    best_lic = _best_license_with_url(note.licenses)
    if best_lic:
        license_start = best_lic.get("start")
        rioxx_xml.add_element_with_value("ali:license_ref",
                                         best_lic["url"],
                                         {"start_date": license_start} if license_start else {})

    return article_vers, pub_date, best_lic


#
### EPRINTS RIOXX XWALK ###
#
def eprints_rioxx_entry(note, new_vers=True):
    """
    Convert the supplied JPER notification to RIOXXplus XML

    TRANSITIONAL arrangement: will output new or original format XML, depending on value of flag.

    See "New PubRouter RIOXXplus Schema Specification v1_10.docx" for details of the field-to-field mappings used.

    :param note: the notification
    :param new_vers: Boolean True=New version (default); False=Original version of XML
    :return: XML document
    """

    def _auth_contrib(contrib_type, auth):
        """
        Method creates an author element, and returns a formatted string to be used in the <comment> field.

        :param contrib_type: string - name of element. Either "author" or "contributor"
        :param auth: Author or Contributor dictionary object

        :return: The created author element, and if there are any emails associated with the author, it returns a string
                    like "Firstname Lastname: Email1, Email2, ...". If there are no emails, the second value returns None.
        """
        # contib_el has root element of either pr:author or pr:contributor
        ## TRANSITIONAL code: passing new_ver, when removed the EprintsRioxxPlus class must be modified accordingly
        contrib_el = EprintsRioxxPlus(f"pr:{contrib_type}", new_ver=new_vers)

        type_ = auth.get('type')
        if type_:
            contrib_el.add_element_with_value("pr:type", _normalise_eprints_contributor_type(type_))

        name_dict = auth.get('name')
        if name_dict is not None:
            # <pr:surname>
            surname = name_dict.get('surname', "")
            if surname:
                contrib_el.add_element_with_value("pr:surname", surname)

            # <pr:firstnames>
            firstname = name_dict.get('firstname', "")
            if firstname:
                contrib_el.add_element_with_value("pr:firstnames", firstname)

            # <pr:suffix>
            temp = name_dict.get('suffix')
            if temp:
                contrib_el.add_element_with_value("pr:suffix", temp)
        else:
            # If no name, there should be an organisation name
            # <pr:org_name>
            surname = auth.get('organisation_name', "")
            if surname:
                contrib_el.add_element_with_value("pr:org_name", surname)
            firstname = ""

        # Process identifiers (Emails have to be treated as special case)
        emails = []
        for ident in auth.get('identifier', []):
            type_ = ident.get('type').lower()
            if type_ == 'email':
                emails.append(ident.get('id'))
            else:
                contrib_el.add_element_with_value("pr:id", ident.get("id"), {"type": type_})

        # if we have multiple emails, set multi_email_string to "[firstname] [surname]: [email1], [email2], ..."
        if len(emails) > 1:
            # make sure that the email in the 0th position is the best possible email
            emails = _best_email_list(emails)
            # format the string
            multi_email_string = f"{firstname} {surname}: {', '.join(emails)}"
        else:
            multi_email_string = None

        # <pr:email>
        if emails:
            contrib_el.add_elements_with_values_list("pr:email", emails)

        return contrib_el, multi_email_string


    def _normalise_history_date_type(date_type):
        """
        Where necessary, convert PubRouter date type to one of corresponding Eprints standard types:
            - published
            - published_online
            - accepted
            - submitted
            - deposited
            - completed

        Known cases for conversion (but other variants, such as "publication" will also be converted):
            epub -> published_online
            ppub -> published
            pub -> published
            received -> submitted

        :param date_type: history date type
        :return: normalised article type
        """
        eprints_date_type_set = {'published', 'published_online', 'accepted', 'submitted', 'deposited', 'completed'}

        if date_type not in eprints_date_type_set:
            if date_type == 'received':
                date_type = 'submitted'
            elif date_type == 'epub':
                date_type = 'published_online'
            elif 'pub' in date_type:
                date_type = 'published'

        return date_type

    ## TRANSITIONAL code: passing new_ver, when this is removed the EprintsRioxxPlus class must be modified accordingly
    eprints_rioxx = EprintsRioxxPlus(new_ver=new_vers)

    note_txt_list = []      # For storing text to send in <pr:note> element

    # Add RIOXX elements

    # <rioxxterms:version>	{0..1}
    article_vers, pub_date, best_lic = _add_common_rioxxterms_elements(eprints_rioxx, note)
    if article_vers:
        note_txt_list.append(format_article_version_text(article_vers, "** "))

    # <pr:embargo start_date="..." end_date="...">	{0..1}
    emb = note.embargo
    if emb:
        attr = {}
        start = emb.get('start')
        if start:
            attr['start_date'] = start

        end = emb.get('end')
        if end:
            attr['end_date'] = end
            note_txt_list.append(_format_embargo_end_text(end, '** '))

        if attr:
            eprints_rioxx.add_element_with_value("pr:embargo", "", attr)

    # metadata.provider.agent added to Note
    provider = note.provider_agent
    if provider:
        note_txt_list.append(format_provider_text(provider, '** '))

    # <rioxxterms:project rioxxterms:funder_id="..." rioxxterms:funder_name="...">	{0..n}
    for proj in note.funding:
        attr = {}  # Empty attributes dict
        # Process any funder identifiers
        funder_id_list = proj.get('identifier', [])
        if funder_id_list:
            # As there can be multiple IDs, for now we will process all to produce a concatenated string like:
            # "id1-type:id1-value, id2-type:id2-value,  ..."
            #   but if this proves problematic for receiving system we can
            #   fall-back to arbitrarily using the first element
            ids = [f"{id_.get('type')}:{id_.get('id')}"for id_ in funder_id_list]
            attr['funder_id'] = "; ".join(ids)

        # get and process funder name
        funder_name = proj.get('name')
        if funder_name:
            attr['funder_name'] = funder_name

        # If at least one attribute is set (funder id(s) or funder name),
        # add the rioxxterms:project element for each grant
        if attr:
            grants = proj.get('grant_numbers') or DEFAULT_GRANT
            for grant in grants:
                eprints_rioxx.add_element_with_value("rioxxterms:project", grant, attr)


    formats_to_download = ['application/pdf']   # File formats to download when processing public links
    # Process all links to files - only interested in public or special links
    format_set = set()
    for link in note.links:
        url = link.get('url')
        access = link.get("access")
        # Special links will be linking to unpacked files in PubRouter's internal store.
        # These will be provided to repositories in special cases - but should not be able to be accessed publicly.
        if url and access in ("public", "special"):
            fmt = link.get('format', 'text/plain')
            attr = {'url': url, 'format': fmt}
            pkg = link.get('packaging')
            if pkg is not None:
                attr['packaging'] = pkg

            # filename is last segment of URL
            filename = url.split("/")[-1]

            # Public links are always provided as <pr:relation> elements which are visible in the Eprint
            if access == "public":
                # <pr:relation url="..." format="..." packaging="..."> {0..n}
                # Empty element so eprints displays URL
                eprints_rioxx.add_element_with_value("pr:relation", "", attr)

                # This public link is NOT pointing to a file that repository should attempt to download
                if fmt not in formats_to_download:
                    # ## SKIP rest of loop - Process next link in note.links
                    continue

                # If we've got this far then this is a public URL we want repository to download
                attr["public"] = "true"    # Optional public attribute added to the <pr:download_link element

                # The last segment of a public URL could have a query appended to it such as for EPMC:
                #       http://europepmc.org/articles/PMC5605758?pdf=render
                # So split filename into tuple of 3: (text-before-the-?, the-?-if-present, stuff-after-the-?)
                filename_parts = filename.partition('?')
                filename = filename_parts[0]
                # Check if filename ends with a suffix like ".xxx", if NOT then append suffix
                if name_has_suffix_regex.search(filename) is None:
                    # Add filename suffix based on format (mime-type)
                    filename += set_filename_extension_from_format(fmt)

            # If we've got this far then the link is either 'special' or
            # a 'public' link with format we want repository to download

            attr["filename"] = filename

            # TRANSITIONAL code (KEEP this line post-transition)
            if new_vers:
                attr["set_details"] = "true"    # License, embargo etc are to be added to document in Eprints

            attr["primary"] = "true" if fmt == "application/pdf" else "false"

            # <pr:download_link="..." format="..." packaging="..." [ public=Bool ] primary=Bool filename="..."> {0..n}
            eprints_rioxx.add_element_with_value("pr:download_link", "", attr)

            # If a downloadable format then add to set (using a set avoids duplicates)
            if fmt in formats_to_download:
                format_set.add(fmt)

    # <dcterms:format> {0..n}
    if format_set:
        # Must convert set to list since add_elements_with_values_list() expects param to be a scalar or a list
        eprints_rioxx.add_elements_with_values_list("dcterms:format", list(format_set))

    # <pr:source volume="..." issue="..."> {1..1}
    # metadata.journal.title -> <eprint><publication>
    temp = note.journal_title
    if temp:
        attr = {}

        # metadata.journal.volume -> <eprint><volume>
        temp2 = note.journal_volume
        if temp2:
            attr['volume'] = temp2

        # metadata.journal.issue -> <eprint><number>
        temp2 = note.journal_issue
        if temp2:
            attr['issue'] = temp2

        eprints_rioxx.add_element_with_value("pr:source", temp, attr)

    # <pr:source_id type="...">  {1..n} issn or isbn
    for iden in note.journal_identifiers:
        eprints_rioxx.add_element_with_value("pr:source_id", iden.get("id"), {"type": iden.get("type")})


    # <dcterms:publisher> {0..n}
    temp = note.journal_publishers
    if temp:
        eprints_rioxx.add_elements_with_values_list("dcterms:publisher", temp)

    # <dcterms:title>	{1..1}
    eprints_rioxx.add_element_with_value("dcterms:title", note.article_title)

    # <dcterms:type>	{0..1}
    temp = note.article_type
    if temp:
        eprints_rioxx.add_element_with_value("dcterms:type", temp)

    # <pr:start_page>	{0..1}  use article.e_num if article.start_page not available
    start_pg = note.article_start_page or note.article_e_num
    if start_pg:
        eprints_rioxx.add_element_with_value("pr:start_page", start_pg)

    # <pr:end_page>	{0..1}
    end_pg = note.article_end_page
    if end_pg:
        eprints_rioxx.add_element_with_value("pr:end_page", end_pg)

    # <pr:page_range>	{0..1}
    pg_range = note.article_page_range
    # If no explicit page_range, but start or end page is set, then construct the page-range
    if not pg_range:
        if end_pg:
            # Note that `en-dash` (rather than hyphen or dash) is used in pg_range below
            pg_range = f"{start_pg}–{end_pg}" if start_pg else end_pg
        elif start_pg:
            pg_range = start_pg
    if pg_range:
        eprints_rioxx.add_element_with_value("pr:page_range", pg_range)

    # <pr:num_pages>	{0..1}
    temp = note.article_num_pages
    if temp:
        eprints_rioxx.add_element_with_value("pr:num_pages", temp)

    # <dcterms:language>	{0..n}
    # This first converts list of article_languages into corresponding list of isolang values, some of which may be ""
    # The filter then removes the empty strings, and the result is forced back to a list
    temp = list(filter(None, [isolang.map_lang_to_2char_iso(lang) for lang in note.article_language]))
    if temp:
        eprints_rioxx.add_elements_with_values_list("dcterms:language", temp)

    # <dcterms:abstract>	{0..1}
    temp = note.article_abstract
    if temp:
        eprints_rioxx.add_element_with_value("dcterms:abstract", temp)

    # <pr:identifier type="...">	{1..n}
    for ident in note.article_identifiers:
        eprints_rioxx.add_element_with_value("pr:identifier", ident.get('id'), {'type': ident.get('type', '').lower()})


    # <dcterms:subject>	{0..n}
    temp = note.article_subject
    if temp:
        eprints_rioxx.add_elements_with_values_list("dcterms:subject", temp)

    # <dcterms:dateAccepted>	{0..1}
    accepted_date = note.accepted_date
    if accepted_date:
        eprints_rioxx.add_element_with_value("dcterms:dateAccepted", accepted_date)

    # <dcterms:medium>	{0..1}
    pub_date_dict = note.publication_date
    if pub_date_dict is not None:
        format = pub_date_dict.get('publication_format')
        if format:
            eprints_rioxx.add_element_with_value("dcterms:medium", format)

    # <pr:history_date type="...">	{0..n}
    # Need to send history dates to Eprints-RIOXX in date descending order (most recent first)
    history_dates = note.history_date
    if history_dates:
        # Loop over reversed dates (most recent first)
        for date_dict in reversed(history_dates):
            eprints_rioxx.add_element_with_value("pr:history_date",
                                             date_dict.get('date'),
                                             {"type": _normalise_history_date_type(date_dict.get('date_type'))})

        # TRANSITIONAL code (KEEP this line post-transition)
        if new_vers:
            note_txt_list.append(_create_history_date_string(history_dates, "** History: ", ";\n"))

    # If there were no history dates, then we need to "spoof" them
    else:
        if pub_date:
            eprints_rioxx.add_element_with_value("pr:history_date", pub_date, {"type": "published"})

        # If there is an accepted date
        if accepted_date:
            eprints_rioxx.add_element_with_value("pr:history_date", accepted_date, {"type": "accepted"})

    # TRANSITIONAL CODE (KEEP this line post-transition)
    if new_vers:
        # Create License descriptions to add to pr:note (will appear in Eprints Additional information field)
        for lic in note.licenses:
            (lic_url, lic_start, lic_text) = extract_license_details(lic)
            if lic_url or lic_text:
                # Add formatted license description string to list (date in DMY format)
                note_txt_list.append(format_license_text(lic_url, lic_start, lic_text, article_vers, '** ', True))

    # TRANSITIONAL CODE (REMOVE post-transition)
    else:
        # Eprints-RIOXX WORKAROUND: due to problematic handling of license information in RIOXXplus plugin the following
        # is implemented:
        #   1. At most, only a single <pr:license> element is sent (regardless of the number of licenses). It is set to the
        #      rioxx ali@license_ref value
        #   2. Information about licenses is also sent in a <pr:note> field (which populates Eprints Additional Information)
        #      - but with special selection criteria because the RIOXXplus plugin will also populate Additional Information
        #        with details of non-OA licenses sent in <pr:license ...> element
        ali_is_not_cc = None
        ali_url = None

        if best_lic:
            # Create single <pr:license> element (correspdonding to ali:license_ref value) from best_lic
            # best_lic ALWAYS has a url
            (ali_url, lic_start, lic_text) = extract_license_details(best_lic, always_text=True, max_text_len=40)
            ali_is_not_cc = "creativecommons" not in ali_url

            attr = {'url': ali_url}
            if lic_start:
                attr['start_date'] = lic_start
            # Add <pr:license ...> element
            eprints_rioxx.add_element_with_value("pr:license", lic_text or "", attr)

            # Create License descriptions to add to pr:note (will appear in Eprints Additional information field)
        for lic in note.licenses:
            (lic_url, lic_start, lic_text) = extract_license_details(lic)
            # Eprints RIOXXplus plugin when processing <pr:license> elements will automatically add a NON-CreativeCommons
            # license to 'Additional information' field.  So if this is the <pr:license> created above and it is NOT CC
            # then we DON'T want to add it to the <pr:note> element
            if lic_url == ali_url and ali_is_not_cc:
                continue  # Don't process this license

            if lic_url or lic_text:
                # Add formatted license description string to list (date in DMY format)
                note_txt_list.append(format_license_text(lic_url, lic_start, lic_text, article_vers, '** ', True))

    # metadata.peer_reviewed --> <pr:note>
    temp = note.peer_reviewed
    if temp is not None:
        note_txt_list.append(f"** Peer reviewed: {'TRUE' if temp else 'FALSE'}")

    # metadata.ack -> <pr:note>
    temp = note.ack
    if temp:
        note_txt_list.append("** Acknowledgements: " + temp)

    # Add <pr:note> element
    if note_txt_list:
        eprints_rioxx.add_element_with_value("pr:note", "\n".join(note_txt_list))

    # list of comments for use in <pr:comment>
    comments = []

    # <pr:author> {0..n}
    # for each author, add an entry and collect a comment for submission in the comment field
    author_els = []
    for a in note.authors:
        author, comment = _auth_contrib("author", a)
        author_els.append(author)
        if comment:
            comments.append(comment)
    if author_els:
        eprints_rioxx.create_elements_with_xml_instance_list(author_els)

    # <pr:contributor> {0..n}
    # for each contributor, add an entry and collect a comment for submission in the comment field
    contrib_els = []
    for c in note.contributors:
        contributor, comment = _auth_contrib("contributor", c)
        contrib_els.append(contributor)
        if comment:
            comments.append(comment)
    if contrib_els:
        eprints_rioxx.create_elements_with_xml_instance_list(contrib_els)


    # <pr:comment> {0..1}
    # if we have any comments after adding authors and contributors, then add string of the format
    # "The following authors/contributors have multiple emails: [author1]: [author1.email1], [author1.email2],...;
    # [author2]: [author2.email1] [author2.email2],..." to the <pr:comment> tag
    if comments:
        comment = f"The following authors/contributors have multiple emails: {'; '.join(comments)}"
        eprints_rioxx.add_element_with_value("pr:comment", comment)

    return eprints_rioxx
# ## END eprints_rioxx_entry() ##


#
### EPRINTS VANILLA XWALK ###
#
def eprints_xml_entry(note):
    """
    Convert the supplied JPER notification to Eprints XML, embedded in the sword client's EntryDocument

    See the overview system documentation for details of the field-to-field mappings used

    :param note: the notification
    :return: Vanilla eprints XML object, like <eprints><eprint>...</eprint><eprints>
    """

    # !! IMPORTANT NOTE: Eprints XML doesn't use namespace prefixes in constructing the XML

    def _contributor_list(contributors, contrib_type):
        """
        Given a list of contributors or creators creates <contributors> or <creators> element, containing an <item>
        structure for each person AND/OR a <corp_creators> element containing <items> for each corporate creator.
        Eprints corporate creator structure does not allow for identifiers.

        NOTE that there is no such concept as a corporate contributor, in unlikely event that a contributor is just
        an organisation name, then this is treated as a surname.

        Example (but note that <creators><item> never contain a <type> element):
            <contributors>
                <item>
                    <type>http://www.loc.gov/loc.terms/relators/EDT</type>
    				<orcid>1111-2222-3333-0000</orcid>
                    <id>manoltwo@belford.ac.uk</id>
                    <name>
                        <family>Williams</family>
                        <given>Manolo</given>
                    </name>
                </item>
                <item>
                    ...
                </item>
            </contributors>

            <corp_creators>
                <item>Corporation name</item>
            </corp_creators>
        Also returns a list of formatted "multiple email" strings for use in the suggestions field of an eprint
        (list may be empty).

        :param contributors: list of contributors to add
        :param contrib_type: creator, contributor or author values

        :return: 3 element tuple: <contributors> or <creators> XML, <corp_creators> XML, List of "multiple emails"
                    (which are generated when where an author has >1 email address) like:
                    ["Firstname Lastname: Email1, Email2, ..", "Firstname2 Lastname2: Email1, Email2, ...", ...]
        """

        contrib_el = None   # This will be either <creators> or <contributors>
        corp_creator_el = None

        # Only contributors have a type added to the <item> XML
        is_contributor = contrib_type == "contributors"
        # list of suggestion strings for each author with > 1 email identifier
        multi_email_strings = []
        item_els = []
        corp_item_els = []
        for contrib in contributors:
            surname = None
            org_name = None
            name_obj = contrib.get('name')
            if name_obj is not None:
                first_name, surname, suffix = NotificationMetadata.extract_name_surname_suffix(name_obj)
            else:
                org_name = contrib.get("organisation_name")
                # Organisation name for contributors are treated as "normal" names
                if org_name and is_contributor:
                    surname = org_name
                    first_name = ""
                    suffix = ""

            if surname:
                # Create <item>
                item = EprintsVanilla("item")

                # Add contributor type (if required)
                if is_contributor:
                    type_ = contrib.get('type', '')
                    if type_:
                        item.add_element_with_value("type", _normalise_eprints_contributor_type(type_))

                # Process identifiers (Emails have to be treated as special case)
                emails = []
                for ident in contrib.get('identifier', []):
                    type_ = ident.get('type').lower()
                    if type_ == "email":
                        emails.append(ident.get('id'))
                    else:
                        item.add_element_with_value(type_, ident.get("id"))

                multiple_emails = len(emails) > 1
                if emails:
                    if multiple_emails:
                        # re-order email list
                        emails = _best_email_list(emails)

                    # add first (the "best") email as an 'id' element
                    item.add_element_with_value("id", emails[0])

                # Create <name> element
                name = EprintsVanilla("name")
                name.add_element_with_value("family", surname)
                name.add_element_with_value("given", first_name)
                if suffix:
                    name.add_element_with_value("lineage", suffix)
                # Add the <name> element to <item>
                item.create_element_with_xml_instance(name)

                # if we have more than one email
                if multiple_emails:
                    # Append to array a string like "Firstname Lastname: email_1, email_2, ..."
                    multi_email_strings.append(f"{first_name} {surname}: {', '.join(emails)}")

                item_els.append(item)
            elif org_name:
                # Create an <item>Corporate name</item> element
                corp_item_els.append(EprintsVanilla.create_unattached_element("item", org_name))

        if item_els:
            # <contributors> or <creators>
            contrib_el = EprintsVanilla(contrib_type)
            # Add <item> elements
            contrib_el.create_elements_with_xml_instance_list(item_els)

        if corp_item_els:
            # <corp_creators>
            corp_creator_el = EprintsVanilla("corp_creators")
            # Add <item> elements
            corp_creator_el.create_elements_with_xml_instance_list(corp_item_els)

        # return <contributors> or <creators>, <corp_creators> or None
        return contrib_el, corp_creator_el, multi_email_strings

    note_text_list = []

    # <eprint>
    ep = EprintsVanilla("eprint")

    # Obtain article version, and if not None, then reformat as " XXX version of" otherwise set to empty string
    art_vers = normalise_article_version(note.article_version)
    if art_vers:
        note_text_list.append(format_article_version_text(art_vers, '** '))

    # metadata.identifier -> <eprint><id_number>
    # use DOI if present, otherwise last ID listed
    art_id = None
    for ident in note.article_identifiers:
        art_id = ident.get('id')
        if art_id and ident.get('type').lower() == "doi":
            break
    if art_id:
        ep.add_element_with_value("id_number", art_id)

    # metadata.title -> <title> and <eprint><title>...
    # Title is set and NOT ""
    temp = note.article_title
    if temp:
        for subtitle in note.article_subtitle:
            if subtitle:
                temp += " - " + subtitle
        ep.add_element_with_value("title", temp)

    # metadata.article.abstract -> <eprint><abstract>
    temp = note.article_abstract
    if temp:
        ep.add_element_with_value("abstract", temp)

    # metadata.type -> <eprint><type>...
    # ArticleType is set and NOT ""
    temp = note.article_type
    if temp:
        ep.add_element_with_value("type", _normalise_article_type(temp))

    # metadata.peer_reviewed --> <eprint><refereed>
    temp = note.peer_reviewed
    if temp is not None:
        ep.add_element_with_value("refereed", "TRUE" if temp else "FALSE")

    # ------------------------------------------------------
    # metadata.author -> <eprint><creators>... and possibly <eprint><corp_creators>
    # ------------------------------------------------------

    suggestions = []
    # get authors suggestions for use in <eprint><suggestions>
    creators_el, corp_creators_el, new_suggestions = _contributor_list(note.authors, 'creators')
    if creators_el:
        # Append <creators> element to <eprint>
        ep.create_element_with_xml_instance(creators_el)
    if corp_creators_el:
        # Append <corp_creators> element to <eprint>
        ep.create_element_with_xml_instance(corp_creators_el)
    suggestions += new_suggestions

    # ------------------------------------------------------
    # metadata.contributor -> <eprint><contributors>...
    # ------------------------------------------------------

    # add contributors suggestions for use in <eprint><suggestions>
    contributors_element, null, new_suggestions = _contributor_list(note.contributors, 'contributors')
    if contributors_element:
        # Append <contributors> element to <eprint>
        ep.create_element_with_xml_instance(contributors_element)

    suggestions += new_suggestions

    # metadata.publisher -> <eprint><publisher>
    _list = note.journal_publishers
    if _list:
        ep.add_element_with_value("publisher", ", ".join(_list))

    # metadata.journal.title -> <eprint><publication>
    temp = note.journal_title
    if temp:
        ep.add_element_with_value("publication", temp)

    # metadata.journal.volume -> <eprint><volume>
    temp = note.journal_volume
    if temp:
        ep.add_element_with_value("volume", temp)

    # metadata.journal.issue -> <eprint><number>
    temp = note.journal_issue
    if temp:
        ep.add_element_with_value("number", temp)

    # metadata.article.e_num -> <eprint><article_number>
    art_num = note.article_e_num
    if art_num:
        ep.add_element_with_value("article_number", art_num)

    # metadata.article.page_range or, if absent, metadata.article.e_num -> <eprint><pagerange>
    temp = note.article_page_range or art_num
    if temp:
        ep.add_element_with_value("pagerange", temp)

    # metadata.journal.identifier -> <eprint><??ident??>id
    # if there are many issn, the priority is:
    # 1. eissn/essn
    # 2. issn
    # 3. any ssn (pissn, pssn...)
    ssn_value = ''
    for ident in note.journal_identifiers:
        type_ = ident.get('type')
        if type_ in ('eissn', 'essn'):
            ssn_value = ident.get('id')
            break  # We've got what we most want, so exit loop

        elif type_ == 'issn':
            # a type of "issn" trumps a "pissn" or "pssn"
            ssn_value = ident.get('id')

            # Only interested in pissn or pssn if no other type of ssn has been yet found
        elif 'ssn' in type_ and not ssn_value:
            ssn_value = ident.get('id')

    if ssn_value:
        ep.add_element_with_value("issn", ssn_value)

    # metadata.embargo.end -> <eprint><note>
    temp = note.embargo_end
    if temp:
        note_text_list.append(_format_embargo_end_text(temp, '** '))

    # metadata.provider.agent -> <eprint><note>
    temp = note.provider_agent
    if temp:
        note_text_list.append(format_provider_text(temp, '** '))

    temp = note.history_date
    if temp:
        note_text_list.append(_create_history_date_string(temp, "** History: ", ";\n"))

    # metadata.publication_date -> <eprint><date> AND <eprint><date_type> AND <eprint><ispublished>
    temp = note.get_publication_date_string()
    if temp:
        ep.add_element_with_value("date", temp)
        ep.add_element_with_value("date_type", "published")
        ep.add_element_with_value("ispublished", "pub")

    # metadata.date_accepted -> <eprint><date> AND <eprint><date_type>
    else:
        temp = note.accepted_date
        if temp:
            ep.add_element_with_value("date", temp)
            ep.add_element_with_value("date_type", "accepted")
            ep.add_element_with_value("ispublished", "inpress")

    # metadata.subject -> <eprint><keywords>...

    _list = note.article_subject
    if _list:
        ep.add_element_with_value("keywords", ", ".join(_list))

    # links.url -> <eprint><related_url><item>...
    links = note.links
    licenses = note.licenses

    if links or licenses:
        item_elements = []
        for link in links:
            url = link.get('url')
            if url and 'public' == link.get('access'):
                # create <item> element
                item = EprintsVanilla("item")
                # Add <url> element to <item> --> <item><url>
                item.add_element_with_value("url", url)
                item_elements.append(item)

        # Set flag to True if only one license
        add_lic_url_to_related_urls = (len(licenses) == 1)
        for lic in licenses:
            (lic_url, lic_start, lic_text) = extract_license_details(lic)

            if lic_start:
                # if Start date is NOT in the past (i.e. is same as today or in the future)
                if add_lic_url_to_related_urls and lic_start >= now_str():
                    # Must not add license URL to related-urls
                    add_lic_url_to_related_urls = False

            # Use URL if present
            if lic_url:
                # URL obtained, see if needs to be added to related-urls
                if add_lic_url_to_related_urls:
                    # create <item> element
                    item = EprintsVanilla("item")
                    # Add <url> element to <item> --> <item><url>
                    item.add_element_with_value("url", lic_url)
                    item_elements.append(item)

            if lic_url or lic_text:
                note_text_list.append(format_license_text(lic_url, lic_start, lic_text, art_vers, '** ', True))

        # Create <related_url> element, then add <item> elements to it
        ru = EprintsVanilla("related_url")
        ru.create_elements_with_xml_instance_list(item_elements)
        # Append <related_url> element to <eprint>
        ep.create_element_with_xml_instance(ru)

    # metadata.funding -> <eprint><funders><item>...
    _list = note.funding
    if _list:
        # Create <funders> element, then add <item> elements to it
        fu = EprintsVanilla("funders")
        for proj in _list:
            funding_text = format_funding_text(proj, "** ")
            if funding_text:
                fu.add_element_with_value("item", funding_text)
        # Append <funders> element to <eprint>
        ep.create_element_with_xml_instance(fu)

    # metadata.ack -> <eprint><note>
    temp = note.ack
    if temp:
        note_text_list.append("** Acknowledgements: " + temp)

    # note_text -> <eprint><note>
    if note_text_list:
        ep.add_element_with_value("note", "\n".join(note_text_list))

    # any suggestions -> <eprint><suggestions>
    # format suggestions text in the form:
    # "The following authors/contributors have multiple emails:
    # Author1 Name: Email1, Email2; Author2 Name: Email1, Email2, ...; ..."
    if suggestions:
        txt = f"The following authors/contributors have multiple emails: {'; '.join(suggestions)}"
        ep.add_element_with_value("suggestions", txt)

    # Create <eprints>
    eprints = EprintsVanilla()
    # Add the <eprint> element to <eprints>
    eprints.create_element_with_xml_instance(ep)
    return eprints


#
### DSPACE RIOXX XWALK ###
#
def dspace_rioxx_entry(note):
    def create_dspace_rioxx_contributor(dspace_xml, contributor, is_author=False):
        """
        Create a DSpace-RIOXX <pubr:contributor> element.

        :param dspace_xml:  XML etree object
        :param contributor: Notification model contributor/author dictionary.
        :param is_author:  Boolean: True --> Author; False --> Contributor

        :return: Nothing, but element added to XML
        """

        name_text = NotificationMetadata.format_contrib_name(contributor, not is_author)
        if name_text is None:
            return

        attr = {}
        # Identifiers for pubr:contributor only deal with orcids and emails
        for identifier in contributor.get("identifier", []):
            if identifier.get("type") == "orcid":
                attr["id"] = identifier.get("id", "")
            elif identifier.get("type") == "email":
                attr["email"] = identifier.get("id", "")

        # Create either <pubr:author> or <pubr:contributor> element
        dspace_xml.add_element_with_value("pubr:{}".format("author" if is_author else "contributor"), name_text, attr)


    dspace_xml = DspaceRioxx()
    _add_common_dspace_dcterms_elements(dspace_xml, note)

    # Un-normalised <dcterms:type>	{0..1}
    _temp = note.article_type
    if _temp:
        dspace_xml.add_element_with_value("dcterms:type", _temp)

    ### RIOXXTERMS ###

    _add_common_rioxxterms_elements(dspace_xml, note)

    # <rioxxterms:project rioxxterms:funder_id="..." rioxxterms:funder_name="...">	{0..n}
    # <pubr:sponsorship> {0..n}
    for proj in note.funding:
        # Add <pubr:sponsorship>
        funding_text = format_funding_text(proj)
        if funding_text:
            dspace_xml.add_element_with_value("pubr:sponsorship", funding_text)

        # Process to see if <rioxxterms:project > can be created
        attr = {}  # Empty attributes dict
        # get and process funder name
        funder_name = proj.get('name')
        if funder_name:
            attr['funder_name'] = funder_name

        # We want to retrieve Fundref Id from list of identifiers
        for identifier in proj.get('identifier', []):
            id_value = identifier.get('id')
            if id_value:
                attr['funder_id'] = id_value
                # If this is a FundRef DOI then we use that in preference to any other
                if "doi.org/" in id_value:
                    break

        # If at least one attribute is set (funder id(s) or funder name), add the rioxxterms:project element
        if attr:
            grants = proj.get('grant_numbers') or DEFAULT_GRANT
            for grant in grants:
                dspace_xml.add_element_with_value("rioxxterms:project", grant, attr)

    # note.links -> <pubr:openaccess_uri>
    # In the unlikely event that multiple publicly accessible PDFs are associated
    # with the nootification, then just use the first that we find.
    for link in note.links:
        if link.get("access") == "public" and link.get("format") == "application/pdf":
            dspace_xml.add_element_with_value("pubr:openaccess_uri", link.get("url"))
            break

    # note.authors -> <pubr:author>
    for author in note.authors:
        create_dspace_rioxx_contributor(dspace_xml, author, is_author=True)

    # note.contributors -> <pubr:contributor>
    for contributor in note.contributors:
        create_dspace_rioxx_contributor(dspace_xml, contributor, is_author=False)

    # note.embargo_end -> <pubr:embargo_date>
    # NB. DSpace throws an exception if it receives an embargo date in the past.
    embargo_end = note.embargo_end
    # if embargo date (YYYY-MM-DD format) provided and it NOT earlier than today, then add it to the entry
    if embargo_end and embargo_end >= datetime.today().strftime('%Y-%m-%d'):
        dspace_xml.add_element_with_value("pubr:embargo_date", embargo_end)

    return dspace_xml


#
### DSPACE VANILLA XWALK ###
#
def dspace_xml_entry(note):
    """
    Convert the supplied JPER notification to DSPACE XML for SWORD

    :param note: the notification
    :return: XML document
    """
    def add_contributors(dspace_xml, qual_tagname, contributors, concat_type=False):
        """
        Given a list of contributors, extract the fullname, organisation name and identifiers and add to the XML.

        :param dspace_xml: the etree XML structure being created
        :param qual_tagname: Qualified tagname e.g. "dcterms:identifier"
        :param contributors: list of contributor dicts to add
        :param concat_type: boolean flag - determines whether the contributor type is concatenated to the name

        :return: Nothing, but updates dspace_xml
        """
        for contrib in contributors:
            contrib_text = NotificationMetadata.format_contrib_name(contrib, concat_type)
            if not contrib_text:
                continue

            # extract email and orcid
            for ident in contrib.get('identifier', []):
                contrib_text += '; ' + ident.get('type') + ': ' + ident.get('id')

            dspace_xml.add_element_with_value(qual_tagname, contrib_text)


    dspace_xml = DspaceVanilla()

    # Create dcterms elements
    art_vers = _add_common_dspace_dcterms_elements(dspace_xml, note)

    # metadata.author -> <dcterms:creator> {0..n}
    add_contributors(dspace_xml, "dcterms:creator", note.authors)

    # metadata.contributor -> <dcterms:contributor> {0..n}
    add_contributors(dspace_xml, "dcterms:contributor", note.contributors, True)

    # article_version -> <dcterms:description>
    if art_vers:
        dspace_xml.add_element_with_value("dcterms:description", format_article_version_text(art_vers))

    # publication_status  -> <dc:description>
    _temp = note.publication_status
    if _temp:
        dspace_xml.add_element_with_value("dcterms:description", 'Publication status: ' + _temp)

    # Funding ->  <dcterms:description>
    for proj in note.funding:
        funding_text = format_funding_text(proj)
        if funding_text:
            dspace_xml.add_element_with_value("dcterms:description", funding_text)

    # metadata.embargo.end -> <dcterms:rights>
    _embargo_info = []
    _temp = note.embargo_start
    if _temp:
        _embargo_info.append('starts ' + _temp)
    _temp = note.embargo_end
    if _temp:
        _embargo_info.append('ends ' + _temp)
    _temp = note.embargo_duration
    if _temp:
        _embargo_info.append('duration ' + _temp + ' months from publication.')
    if _embargo_info:
        dspace_xml.add_element_with_value("dcterms:rights", "Embargo: " + ", ".join(_embargo_info))

    # Normalised <dcterms:type>	{0..1}
    _temp = note.article_type
    if _temp:
        dspace_xml.add_element_with_value("dcterms:type", _normalise_article_type(_temp))

    # date received -> <dcterms:dateSubmitted>
    for hist_date in note.history_date:
        date = hist_date.get('date')
        if date:
            # Dspace uses date type of "submitted" rather than "received",
            #   hence add additional element with that date type
            # We are keeping the "received" entry (as opposed to substituting it) as it may be useful to other systems
            if hist_date.get('date_type', "") == 'received':
                dspace_xml.add_element_with_value("dcterms:dateSubmitted", date)
                break

    return dspace_xml


def native_xml_entry(note):
    """
    Convert the supplied JPER notification to Native XML for SWORD

    :param note: the notification Object
    :return: XML document (a SwordModel subclass)
    """
    d2x = DictToXml(xml_declaration=False, root_name="entry", bool_as_int=True)
    # note.data returns the Dict of data
    return Native(data=d2x.dict_to_xml(note.data))

