"""
Mapper class that creates a xml structure mapping an outgoing notification into dublin core schema

2017-10 This is used by Dspace and OAI-PMH xwalks

"""
from octopus.lib.dates import ymd_to_dmy
from router.shared.models.note import NotificationMetadata, normalise_article_version


def extract_license_details(lic, always_text=False, max_text_len=None):
    """
    Takes a license and returns key license information: URL, start-date, description

    The license description is set according to this algorithm:
        if there is no license.url or if always_text flag is True:
            Use license.title where it is set and shorter than a max_text_len (if one is specified); Otherwise use
            license.type if one is present; Otherwise use truncated title (where a max_text_len is at least 80
            and a license.title exists); Otherwise return None.

    :param lic: License dict
    :param always_text: Boolean - True: always return license-text string; False: only return license-text if no url
    :param max_text_len: Maximum length of license description text

    :return: licence-url, license-start-date, license-textual description
             NOTE any of these can be None
    """

    lic_txt = None

    url=lic.get("url")

    # Only try to set license text if always_text is specified or there is no Url
    if always_text or not url:
        truncate_title_len = 0

        # Try to set License text from License title, failing that from License type, failing that set according type
        lic_title = lic.get('title')

        if lic_title:
            # If license title is longer than permitted then we may want to use truncated title if there is no license.type
            if max_text_len and len(lic_title) > max_text_len:
                # Truncate only if we can grab at least first 80 characters
                if max_text_len >= 80:
                    truncate_title_len = max_text_len - 1 # allow for an Ellipsis to be added
            # No problem with title length
            else:
                lic_txt = lic_title

        if not lic_txt:
            lic_txt = lic.get('type')

        if not lic_txt and truncate_title_len:
            # Set text to truncated title text with an Ellipsis added
            lic_txt = lic_title[:truncate_title_len] + "\u2026"

    return url, lic.get("start"), lic_txt


def format_license_text(lic_url, lic_start, lic_text, article_vers=None, prefix='', dmy_format=False):
    """
    Constructs a license description based on this template:
        "** Licence for [article-version version of] this article [starting on lic-start-date]: [lic_url or lic_text]"
    For example one of these:
        ** Licence for VoR version of this article starting on 02-09-2019: https://creativecommons.org/licenses/by-nc-sa/4.0/
        ** License for this article: CC BY-ND

    IMPORTANT - Either lic_url or lic_text is expected to be non-empty

    :param lic_url: License URL
    :param lic_start: License start date YYYY-MM-DD format
    :param lic_text: License description
    :param article_vers: Article version
    :param prefix: String to prefix the returned text with
    :param dmy_format: Boolean (True|False): True -> Format date as DD-MM-YYYY; False -> date formatted as YYYY-MM-DD

    :return: Formatted string describing license
    """

    # Start date provided, and DD-MM-YYYY format required
    if lic_start and dmy_format:
        try:
            # Need to convert a YYYY-MM-DD date to DD-MM-YYYY format
            lic_start = ymd_to_dmy(lic_start)
        except:
            lic_start = None

    return "{}Licence for{} this article{}: {}".format(
        prefix,
        " {} version of".format(article_vers) if article_vers else "",
        " starting on {}".format(lic_start) if lic_start else "",
        lic_url or lic_text  # Use url if present otherwise license-text
    )


def format_provider_text(provider, prefix=''):
    """
    Constructs string describing notification source

    :param provider: Agent string (known not to be empty)
    :param prefix: String to prefix the returned text with
    :return: Formatted provider description
    """
    # provider = {'EPMC': 'Europe PMC'}.get(provider, provider)

    if provider == 'EPMC':
        provider = 'Europe PMC'
    return f"{prefix}From {provider} via Jisc Publications Router"

def format_article_version_text(vers, prefix=''):
    return f"{prefix}Article version: {vers}"

def format_funding_text(funding_dict, prefix=''):
    """
    Construct funding text string with general format:
        '{prefix}Funder: {funder-name}; {id-type: id}, {id-type: id}; Grant(s): {grant-num}, {grant-num}'

    Example:
    'Funder: Rotary Club of Eureka; ringgold: rot-club-eurek, doi: http://dx.doi.org/10.13039/100008650; Grant(s): BB/34/juwef'

    :param funding_dict: Notification funding dictionary
    :param prefix:     :param prefix: String to prefix the returned text with
    :return: Formatted string
    """

    funding_text = ""
    # Get funder name & process
    temp = funding_dict.get('name')
    if temp:
        funding_text = f"Funder: {temp}"

    # Get funder identifiers, like ['doi: http://dx.doi.org/10.13039/100008650']
    funder_ids = [f"{id_.get('type')}: {id_.get('id')}" for id_ in funding_dict.get("identifier", [])]
    if funder_ids:
        if funding_text:
            funding_text += "; "
        funding_text += ", ".join(funder_ids)

    # Get grant-number & process
    temp = funding_dict.get('grant_numbers')
    if temp:
        if funding_text:
            funding_text += "; "
        funding_text += "Grant(s): " + ", ".join(temp)

    if funding_text:
        return prefix + funding_text
    return None


class DublinCoreMapper:

    def __init__(self, wrap, prefix_or_parent_element, note):
        '''
        Constructor class
        :param wrap: Parent class which contains a method:  add_field(prefix, tag, value)
        :param prefix_or_parent_element: namespace abbreviation or parent element to add a new node
        :param note: Notification instance
        '''
        self.wrapper = wrap
        self.prefix_or_parent_element = prefix_or_parent_element
        self.note = note

    def _add_field(self, tag, value):
        self.wrapper.add_field(self.prefix_or_parent_element, tag, value)

    def _dcterms_contributor_list(self, contributors, contrib_type, concat_type=False):
        '''
         given a list of contributors, extract the fullname, organisation name and identifiers and add to the entry.xml
        :param contributors: list of contributors to add
        :param contrib_type: creator, contributor or author values
        :param concat_type: boolean flag - determines whether the type of contributor is concatentated to the name
        '''
        for contrib in contributors:
            contrib_text = NotificationMetadata.format_contrib_name(contrib, concat_type)
            if not contrib_text:
                continue

            # extract email and orcid
            for ident in contrib.get('identifier', []):
                contrib_text += '; ' + ident.get('type') + ': ' + ident.get('id')

            self._add_field(contrib_type, contrib_text)

    def create_basic_dc_xml_for_oaipmh(self):
        """
        Create a basic xml based on DublinCore schema http://dublincore.org/documents/dcmi-terms/
        limited by the field for oai-pmh protocol  http://www.openarchives.org/OAI/2.0/oai_dc.xsd

        Fields created:
        <title> - article_title
        <language> - article_language
        <subject> - article_subject
        <description> provider_agent | history_date
        <publisher> - journal_publishers
        <identifier> - article_identifiers
        <source> - journal_identifiers
        <rights> - license info
        <creator> - authors
        <description> - article_version | publication_status | funding
        <contributor> - contributors
        <rights> - embargo info

        :return: None
        """
        # metadata.language -> dc:language
        for language in self.note.article_language:
            self._add_field("language", language)

        # metadata.journal.identifier -> <dc:indentifier>
        for ident in self.note.journal_identifiers:
            journal_id = ident.get('id')
            if journal_id:
                self._add_field('source', ident.get('type') + ': ' + journal_id)

        # metadata.journal.publishers -> <dc:publisher>
        for pub in self.note.journal_publishers:
            self._add_field('publisher', pub)

        # metadata.provider.agent -> <dc:description>
        _temp = self.note.provider_agent
        if _temp:
            self._add_field('description', format_provider_text(_temp))

        # metadata.article.title -> dc:title
        _temp = self.note.article_title
        if _temp:
            self._add_field('title', _temp)

        # metadata.article.identifier -> <dc:indentifier>
        for ident in self.note.article_identifiers:
            art_id = ident.get('id', "")
            if art_id:
                self._add_field('identifier', ident.get('type') + ': ' + art_id)

        # article_subject -> <dc:subject>
        for sub in self.note.article_subject:
            self._add_field('subject', sub)

        # history_dates -> <dc:description>
        _history_info = []
        for hist_date in self.note.history_date:
            date = hist_date.get('date', "")
            if date:
                date_type = hist_date.get('date_type', "")
                _history_info.append(date_type + ' ' + date)

        if _history_info:
            self._add_field('description', 'History: ' + ", ".join(_history_info))

        art_vers = normalise_article_version(self.note.article_version)

        # Licenses -> <dc:rights>
        for lic in self.note.licenses:
            (lic_url, lic_start, lic_text) = extract_license_details(lic)
            if lic_url or lic_text:
                self._add_field('rights', format_license_text(lic_url, lic_start, lic_text, art_vers))

        # metadata.author ->  <dcterms:creator> {0..n}
        self._dcterms_contributor_list(self.note.authors, 'creator')

        # metadata.contributor -> <dcterms:contributor> {0..n}
        self._dcterms_contributor_list(self.note.contributors, 'contributor', True)

        # article_version -> <dc:description>
        art_vers = normalise_article_version(self.note.article_version)
        if art_vers:
            self._add_field('description', format_article_version_text(art_vers))

        # publication_status  -> <dc:description>
        _temp = self.note.publication_status
        if _temp is not None:
            self._add_field('description', 'Publication status: ' + _temp)

        # Funding ->  -> <dc:description>
        _list = self.note.funding
        for proj in _list:
            funding_text = format_funding_text(proj)
            if funding_text:
                self._add_field('description', funding_text)

        # metadata.embargo.end -> <dc:rights>
        _embargo_info = []

        _temp = self.note.embargo_start
        if _temp:
            _embargo_info.append('starts ' + _temp)

        _temp = self.note.embargo_end
        if _temp:
            _embargo_info.append('ends ' + _temp)

        _temp = self.note.embargo_duration
        if _temp:
            _embargo_info.append('duration ' + _temp + ' months from publication.')

        if _embargo_info:
            self._add_field('rights', "Embargo: " + ", ".join(_embargo_info))

