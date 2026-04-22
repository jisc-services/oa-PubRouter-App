"""
jats.py specifies the JATS data model

We currently support both the current 
JATS standard: https://jats.nlm.nih.gov/publishing/tag-library/1.1/ as well as the 
NLM standard: http://dtd.nlm.nih.gov/publishing/tag-library/

This file is derived from original Octopus/modules/epmc/models.py file by stripping out all the EPMC crap which
is no longer required by PubRouter since packages.py was changed to strip out the notional "EPMC" XML format which
CottageLabs had coded for.  However, no DTD or XML Schema corresponding to this EPMC XML format could be identified.
Possible CottageLabs had worked from some archaic XML structure?
(EPMC REST APIs all provide XML in JATS format).

Author: Jisc
"""
from lxml import etree
import re
from copy import deepcopy
from datetime import date
from octopus.lib.data import get_orcid_from_url


class InvalidJATSError(Exception):
    # an exception class used whenever we determine that the JATS provided by a publisher "doesn't make sense" or
    # disobeys our FTP protocol
    pass


class XMLException(Exception):

    def __init__(self, message, rawstring):
        super(XMLException, self).__init__(message)
        self.raw = rawstring


# XML base class
class XMLbase:

    # Regex to match a space followed by punctuation character, using lookahead assertion
    space_punctuation = re.compile(r" (?=[.,;:?!])")

    def __init__(self, raw=None, xml=None):
        """
        :param raw: Byte-string XML
        :param xml: ElementTree Object
        """
        self.raw = None
        self.xml = None
        if raw is not None:
            self.raw = raw
            try:
                self.xml = etree.fromstring(self.raw)
            except Exception:
                raise XMLException("Unable to parse XML", self.raw)
        elif xml is not None:
            self.xml = xml

    def to_byte_str(self):
        if self.raw is not None:
            return self.raw
        elif self.xml is not None:
            return etree.tostring(self.xml)
        else:
            return ""

    def to_unicode_str(self):
        if self.raw is not None:
            return self.raw.decode("utf-8")
        elif self.xml is not None:
            return etree.tostring(self.xml, encoding="unicode")
        else:
            return ""

    @staticmethod
    def extract_text_formatted_no_texmath(element):
        """
        Extract all text within an element except for any <tex-math> contents, special treatment of title and paragraph,
        by insertion of ": " and " " after each respectively
        :param element: Element whose text is required
        :return: text string
        """

        def concat(base, xtra):
            """
            Concatenates base and new strings. If `xtra` is 1 char long and a ',' or ';' then it appends a space after.
            :param base: base string
            :param xtra: string to append to base
            :return:
            """
            base += xtra
            if len(xtra) == 1 and xtra in ",;":
                base += " "
            return base

        s = ''  # String we are building
        # tree walk over the element hierarchy, return events at start and end of an element
        for event, el in etree.iterwalk(element, ("start", "end",)):
            if event == "start":
                if el.tag != "tex-math" and el.text:
                    s = concat(s, el.text)

            else:  # End of an element
                if el.tag == 'title':
                    # Title text is followed by colon space
                    s += ' ' if s.endswith(':') else ': '
                elif el.tag == 'p':
                    s += ' '  # Paragraph text is followed by space
                if el.tail:
                    s = concat(s, el.tail)

        # Remove leading/trailing and multiple white space and replace by space
        return " ".join(s.split())

    @classmethod
    def extract_text_no_texmath(cls, element):
        """
        Extract all text within an element except for any <tex-math> contents
        :param element: Element whose text is required
        :return: text string
        """
        # First join array of elements returned by xpath concatenating with space;
        # then split and rejoin to remove multiple spaces
        s = " ".join(" ".join(element.xpath(".//*[not(self::tex-math)]/text()|./text()")).split())
        # Finally remove spaces before punctuation
        return cls.space_punctuation.sub('', s)

    @staticmethod
    def xp_first_text(element, xpath, no_texmath=False, default=None):
        """
            Returns text associated with first element matching supplied xpath selector.

        :param element: XML element "root"
        :param xpath: XPATH selector
        :param no_texmath: Flag determines whether to exclude tex_match element text
        (True = exclude, False = return ALL text)
        :param default: Default value if no element matching xpath selector
        :return:    Text string or None
        """
        els = element.xpath(xpath)
        if els:
            # using the first element matching the xpath expression
            if no_texmath:
                return XMLbase.extract_text_no_texmath(els[0])
            else:
                # expect a simple string returned - remove multiple consecutive spaces, by splitting and rejoining
                return " ".join(els[0].xpath("string()").split())

        return default

    @staticmethod
    def strip_text(txt):
        if txt is None:
            return ''
        return txt.strip()

    @staticmethod
    def find_simple_first_text(element, match, default=None):
        el = element.find(match)
        if el is not None:
            return XMLbase.strip_text(el.text)
        return default

    @staticmethod
    def xp_texts(element, xpath):
        """
        :param element: XML element "root"
        :param xpath: XPATH selector
        :return: Array of strings
        """
        # extract all strings (including those from sub-elements) from each element returned by the xpath expression
        return [" ".join(el.xpath("string()").split()) for el in element.xpath(xpath)]

    @staticmethod
    def xp_texts_no_texmath(element, xpath):
        """
        Retrieve all text except <tex-math> content for all elements returned by the xpath selector
        :param element: XML element "root"
        :param xpath: XPATH selector
        (True = exclude, False = return ALL text)
        :return: Array of strings
        """
        # extract all strings (including those from sub-elements) from each element returned by the xpath expression
        return [XMLbase.extract_text_no_texmath(el) for el in element.xpath(xpath)]

    @staticmethod
    def etree_to_dict(element, children=None):
        """
        Convert an xml element tree to a (nested) dictionary, keyed by tag names
        """
        if children is None:
            children = element.getchildren()
        obj = {}
        for c in children:
            # FIXME: does not currently handle attributes
            # for attr in c.keys():
            #    obj["@" + attr] = c.get(attr)
            kids = c.getchildren()
            if len(kids) > 0:
                obj[c.tag] = XMLbase.etree_to_dict(c, kids)
            else:
                obj[c.tag] = XMLbase.strip_text(c.text)
        return obj


class JATS(XMLbase):

    # Regex to capture any base URL string that begins http(s):// and is followed by at least one character that is not
    # whitespace or comma or semicolon or bracket or question mark
    # (note optional s after the http)
    http_regex = re.compile(r"https?://[^\s,;)\]?]+")
    # Regex to identify a Department from the content-type in element like: <institution content-type="...">
    aff_dept_regex = re.compile(r"(?:dep(?:t|artment)|office|division)", re.IGNORECASE)

    # AM: Accepted manuscript, P: Proof, VOR: Version of record, EVOR: Enhanced VOR, CVOR: Corrected VOR
    allowed_licence_specific_uses = {"AM", "P", "VOR", "EVOR", "CVOR", "C/EVOR"}
    allowed_article_versions = {"AM", "P", "VOR", "EVOR", "CVOR", "C/EVOR"}
    jav_set = {"AO", "SMUR", "AM", "P", "VOR", "EVOR", "CVOR", "C/EVOR"}
    acronym_max_len = 6
    niso_rp8_2008_dict = {
        "AUTHORS-ORIGINAL": "AO",
        "SUBMITTED-MANUSCRIPT-UNDER-REVIEW": "SMUR",
        "ACCEPTED-MANUSCRIPT": "AM",
        "PROOF": "P",
        "VERSION-OF-RECORD": "VOR",
        "CORRECTED-VERSION-OF-RECORD": "CVOR",
        "ENHANCED-VERSION-OF-RECORD": "EVOR",
        "CORRECTED-OR-ENHANCED-VERSION-OF-RECORD": "C/EVOR",
    }

    def __init__(self, raw=None, xml=None):
        super(JATS, self).__init__(raw, xml)

        # We are only interested in JATS meta-data contained within the <article><front> and <back> element
        # (<article> is the root element) so we delete anything else (such as <body>, <sub-article> etc.) to
        # (potentially) substantially reduce the size of the JATS xml that we process and store
        elements_to_keep = ['front', 'back']
        # loop for all immediate child elements (under root element <article>)
        for child_element in self.xml:
            # if child element is not one we want to keep, then delete it from the etree XML structure
            if child_element.tag not in elements_to_keep:
                self.xml.remove(child_element)

        # If journal-meta NOT found, then create empty xml tree
        # (to avoid having to check for None wherever self.xml_journal_meta is used)
        self.xml_journal_meta = self.find_etree_el_or_empty_el("./front/journal-meta")

        # If article-meta NOT found, then create empty xml tree
        # (to avoid having to check for None wherever self.xml_article_meta is used)
        self.xml_article_meta = self.find_etree_el_or_empty_el("./front/article-meta")

        # If back NOT found, then create empty xml tree
        # (to avoid having to check for None wherever self.xml_article_back is used)
        self.xml_article_back = self.find_etree_el_or_empty_el("./back")

    def find_etree_el_or_empty_el(self, xpath_str):
        """
        Return Element matching the xpath_str if one is found, otherwise return an empty element (this means that
        code does not have to test for None wherever the returned element is used.

        :param xpath_str: String - XPATH query
        :return: etree XML element
        """
        el = self.xml.find(xpath_str)
        if el is None:
            el = etree.XML('<none></none>')
        return el

    @property
    def abbrev_journal_title(self):
        return self.xp_first_text(self.xml_journal_meta, ".//abbrev-journal-title")

    @property
    def journal_title(self):
        """
        Return the journal title with the following priorty order:
            Journal title in a journal title group (JATS >1.0)
            Journal title anywhere (all versions)
            Abbrev journal title (NLM versions)
                (abbrev journal title will be captured by .//journal-title in JATS > 1.0)
        """
        journal_title = self.xp_first_text(self.xml_journal_meta, "./journal-title-group/journal-title")
        if not journal_title:
            journal_title = self.xp_first_text(self.xml_journal_meta, ".//journal-title")
            if not journal_title:
                journal_title = self.abbrev_journal_title
        return journal_title

    @property
    def journal_publisher(self):
        return self.xp_first_text(self.xml_journal_meta, "./publisher/publisher-name")

    @property
    def journal_volume(self):
        # In JATS the volume is found in article-meta
        return self.find_simple_first_text(self.xml_article_meta, "./volume")

    @property
    def journal_issue(self):
        # In JATS the issue is found in article-meta
        return self.find_simple_first_text(self.xml_article_meta, "./issue")

    @property
    def article_type(self):
        # For JATS we expect the Root node to be <Article> which has attribute 'article-type'
        return self.xml.get('article-type', '')

    @property
    def article_language(self):
        # For JATS we expect the Root node to be <Article> which has attribute 'xml:lang'
        return self.xml.get('{http://www.w3.org/XML/1998/namespace}lang', '')

    @property
    def article_title(self):
        return self.xp_first_text(self.xml_article_meta, "./title-group/article-title", no_texmath=True)

    @property
    def article_subtitles(self):
        return self.xp_texts_no_texmath(self.xml_article_meta, "./title-group/subtitle")

    @property
    def article_abstract(self):
        # Attempts first to find an article abstract without any abstract-type attribute; failing that it looks for
        # an abstract with an abstract-type, and if found, selects one matching these values (priority order):
        # 'summary', 'web-summary', 'executive-summary'; or if none match then the first abstract found
        abs_ix = None   # Index of element to use from el_list

        # Get abstract elements without an abstract-type attribute
        el_list = self.xml_article_meta.xpath("./abstract[not(@abstract-type)]")
        if el_list:
            abs_ix = 0  # We want the first result (it would be unusual if there was more than one)
        else:
            # See if there are abstracts with abstract-type attribute
            el_list = self.xml_article_meta.xpath("./abstract[@abstract-type]")
            if el_list:
                # Create a map of abstract-type values mapped to list index
                abs_type_to_ix = {}     # dict mapping abstract-type to list index
                for ix, el in enumerate(el_list):
                    abs_type_to_ix[el.get("abstract-type")] = ix

                # Look for particular abstract-type, in priority order
                for abs_type in ('summary', 'web-summary', 'executive-summary'):
                    abs_ix = abs_type_to_ix.get(abs_type)
                    if abs_ix is not None:
                        break
                # particular abstract-type not found, so just use first in list
                if abs_ix is None:
                    abs_ix = 0

        # Return selected abstract text or None
        return self.extract_text_formatted_no_texmath(el_list[abs_ix]) if abs_ix is not None else None

    @property
    def is_aam(self):
        manuscripts = self.xml_article_meta.xpath("./article-id[@pub-id-type='manuscript']")
        return len(manuscripts) > 0

    @classmethod
    def _get_license_url_from_text(cls, license_text, require_end_slash=True):
        """
        Regex search for and return a url from some license text. NOTE that this will NOT
        capture any URL query parameters (it stops capturing if it encounters a '?')

        :param license_text: Text from a license
        :param require_end_slash: Boolean flag indicates if URL should have a terminating slash or not

        :return: Matched URL or ''
        """
        # Search for a URL (any string that begins http:// or https:// followed by at least one non-blank character
        # that is not a comma, semicolon or bracket or question mark)
        match = cls.http_regex.search(license_text)
        if match:
            url = match.group(0)
            # Set flag depending on whether last char is a slash or not
            end_slash_found = url[-1] == '/'
            # what is required ISN'T what is found
            if require_end_slash != end_slash_found:
                if require_end_slash:
                    # Add end slash
                    url += '/'
                else:
                    # Remove end slash
                    url = url[:-1]
        else:  # No match
            url = ''

        return url

    @classmethod
    def _get_url_from_licence_para_or_text(cls, license_para_element, license_text):
        """
        Get a href from an ext_link element, or regex search the license_text for one.

        Examples with and without <ext-link>:
            <license-p>
                Some text with URL within ext_link <ext-link xlink:href=http://someurl.url></ext-link> element
            </license-p>
            <license-p>
                Some text with a license https://creativecommons.org/licenses/by-nd/4.0/ URL within the text
            </license-p>

        :param license_para_element: <p> or <license-p> element
        :param license_text: Text from a license

        :return: href retrieved from an <ext-link> element, or a url found in regex.
        """
        ext_link = license_para_element.find("ext-link")
        if ext_link is not None:
            # Get url from the xlink:href attribute
            url = ext_link.get("{http://www.w3.org/1999/xlink}href", cls._get_license_url_from_text(license_text))
        else:
            url = cls._get_license_url_from_text(license_text)
        return url

    def normalise_article_vers(self, article_version):
        """
        Returns a normalised UPPER CASE article version.
        :param article_version: String - article version
        :return: normalised version of the article version
        """
        article_version = article_version.upper()
        if article_version == "AAM":        # Historically, people used Authors Accepted Manuscript (AAM)
            article_version = "AM"
        return article_version

    def get_ali_license_ref(self, lic):
        """
        Searches for <ali:license_ref> elements within a <license> element and returns the url, start_date and
        specific-use within it if present. 
        
        :param lic: <license> element
        :return: tuple lic_url, lic_start, lic_specific_use which represents the url found within a <ali:license_ref>,
            the start date and the specific-use found in  the attributes respectively. If url or start_date are not
            present, then "" will be returned instead. If specific-use is not present, None will be returned instead. 
        """
        ali_lic = lic.find("{http://www.niso.org/schemas/ali/1.0/}license_ref")
        # if there is indeed an <ali:license_ref> element inside the <license> element
        if ali_lic is not None:
            # get url from text of the element
            lic_url = self.strip_text(ali_lic.text)
            lic_start = ali_lic.get("start_date", "")
            lic_specific_use = ali_lic.get("specific-use")
        else:
            lic_url = ""
            lic_start = ""
            lic_specific_use = None

        return lic_url, lic_start, lic_specific_use

    def get_paragraph_license_info(self, lic, lic_url):
        """
        Runs through all <license-p> and <p> elements in a <license> element. Concatenates all contents into a title
        if present. If cur_url is not set, then will try to find a url from text and <ext-link> elements inside
        <license-p> and <p> elements.
        
        :param lic: <license> element
        :param lic_url: current license url, can be None or a value
        :return: a tuple: lic_title, lic_url  
            lic_title: a string containing space separated contents of all elements inside all <license-p> and <p>
            elements inside the <license> element
            lic_url: if the passed lic_url is set, then will simply return this value. If it is not set, will return
            either "" or a url which has been parsed out of the text contents and the <ext-link> sub elements
            inside the <license-p> and <p> elements
        """
        lic_title = ""
        # check both <license-p> and <p> elements
        for lic_para in lic.xpath(".//license-p|.//p"):
            # join all the text within this element, then split/join to remove any surplus white space
            para_text = " ".join("".join(lic_para.xpath("string()")).split())
            lic_title += para_text
            # if we don't currently have a url, and haven't already found one from <license-p> or <p>s
            # in this license, then try to find a license from current paragraph
            if not lic_url:
                lic_url = self._get_url_from_licence_para_or_text(lic_para, para_text)
        return lic_title, lic_url

    def get_licence_and_article_version_details(self):
        """
        Extracts license and article version details from JATS
        JATS spec page: https://jats.nlm.nih.gov/publishing/tag-library/1.1/element/license.html
        
        Follows this algorithm:
        When retrieving licenses, do not capture any with a "tdm" specific use

        valid_article_version_specific-use = (AM, VoR, CVoR, EVoR)
        allowed_licence_specific-use = (P, AM, VoR, CVoR, EVoR, TDM)
        
        if <article> element contains a valid_article_version_specific-use_:
           capture _article-specific-use_ as article-version 
        
        if NONE of the licences has specific-use tagged:
                Capture ALL
        if SOME of the licences has specific-use tagged
           OR any licence specific-use value is NOT in allowed_licence_specific-use_:
                ERROR 
        if ALL of the licences has specific-use tagged:
                 if article-version has value:
                        Capture all the licences with specific-use same as article-version.
                        if no licence captured:
                                ERROR
                 if article-version has NO value:
                        if all licences have the same valid specific-use value
                            AND licence specific-use contains a valid_article_version_specific-use:
                               Capture ALL licences
                               Capture the specific-use value as the article-version
                        else ERROR
                        
        :return: article_version, licenses 
            article version will either be one of the values ["VoR", "CVoR", "EVoR", "AM"] or None
            licenses will be a list of objects of the format
            {"type": type, "url": url, "title": lic_title, "start": start_date, "specific-use": specific-use}
        """
        licenses = []
        # number of licenses which have a specific-use value set
        specific_use_license_count = 0
        # for each <license> element, create and append a single license dictionary to our list of licenses
        for lic in self.xml_article_meta.iterfind("./permissions/license"):
            # first try to get a license url out of any <ali:license_ref> elements within this <license>
            # (also get a start date if present)
            lic_url, lic_start, lic_specific_use = self.get_ali_license_ref(lic)
            # If there was no <ali:license_ref> element, or there was one without a specific-use attribute,
            # then attempt to get specific-use from <license> element.
            if lic_specific_use is None:
                lic_specific_use = lic.get("specific-use")
            if lic_specific_use:
                orig_lic_specific_use = lic_specific_use
                lic_specific_use = self.normalise_article_vers(lic_specific_use)
                # Don't capture any "text & data mining" licences
                if "TDM" in lic_specific_use:
                    continue  # Skip to next license (don't capture this one)

                # If we (possibly) have long form of specific use, try to convert to acronym (short) form
                # (We ignore possible value of "Proof" (length 5) because no licence should exist at Proof stage
                if len(lic_specific_use) > self.acronym_max_len:
                    # Convert long form like "version-of-record" or "version of record" to short form (like VOR)
                    lic_specific_use = self.niso_rp8_2008_dict.get(lic_specific_use.replace(" ", "-"))
                # if this is a license with specific-use value we will not allow, then see if further conversion req'd
                if lic_specific_use not in self.allowed_licence_specific_uses:
                     raise InvalidJATSError(
                        f"Found a licence with invalid specific-use value: '{orig_lic_specific_use}'. "
                        f"We expect one of: {self.allowed_licence_specific_uses} (case-insensitive)."
                    )

                specific_use_license_count += 1
            # if we couldn't get a license url out of an <ali:license_ref> element, then look for it in the xref:href
            # attribute of our <license>
            if not lic_url:
                lic_url = lic.get("{http://www.w3.org/1999/xlink}href", "")
            # license type
            lic_type = lic.get("license-type", "")
            # get the title of the license out of the <p> and <license-p> elements. Try to create a license url out
            # of this information if we haven't already found one
            lic_title, lic_url = self.get_paragraph_license_info(lic, lic_url)
            # if we've managed to get a url by this point, then create a new license object and append it to the list
            if lic_url:
                licenses.append(
                    {
                        "start": lic_start,
                        "url": lic_url,
                        "title": lic_title,
                        "type": lic_type,
                        "specific-use": lic_specific_use
                    }
                )
        return self.article_version_calculator(licenses, specific_use_license_count)

    def jats_article_version(self):
        """
        Get the article version from JATS 1.2 onwards <article-version>
        :return: article-version or None or exception InvalidJATSError where vocab is specified, but value isn't in
                 allowed set of values
        """
        invalid_version_type_msg = "Invalid {} article-version-type: '{}' in <article-version> element, expected one of: {} (case insensitive)."

        def _version_text_to_version_acronym(version_text):
            if version_text:
                # Convert to upper case and replace spaces by hyphens
                version_text = self.normalise_article_vers(version_text)
                # if length of text suggests it is an article-version acronym, check if it is
                if len(version_text) <= self.acronym_max_len and version_text in self.jav_set:
                    return version_text
                # Otherwise check if text is long-form article-version
                return self.niso_rp8_2008_dict.get(version_text.replace(" ", "-"))
            return None

        def _get_article_version(el):
            orig_version_type = el.get("article-version-type")
            if orig_version_type is not None:
                vocab = el.get("vocab")
                if vocab is None or vocab == "JAV":
                    version_type = orig_version_type.upper()
                    if version_type in self.jav_set:
                        return version_type
                    elif vocab:
                        raise InvalidJATSError(invalid_version_type_msg.format(vocab, orig_version_type, self.jav_set))
                elif vocab == "NISO-RP-8-2008":
                    # Convert to upper case and replace spaces by hyphens
                    version_type = orig_version_type.upper().replace(" ", "-")
                    art_vers = self.niso_rp8_2008_dict.get(version_type)
                    if art_vers:
                        return art_vers
                    else:
                        raise InvalidJATSError(
                            invalid_version_type_msg.format(vocab, orig_version_type, list(self.niso_rp8_2008_dict.keys())))
            else:
                # Try to obtain the article version from the element text value (rather than its attributes)
                return _version_text_to_version_acronym(el.text)
            return None

        article_version = None

        # JATS 1.2 onwards - see https://jats.nlm.nih.gov/publishing/tag-library/1.2/element/article-version.html
        article_version_el = self.xml_article_meta.find("./article-version")
        if article_version_el is not None:
            article_version = _get_article_version(article_version_el)
        else:
            # Possibly there will be more than one <article-version> within <article-version-alternatives>
            for article_version_el in self.xml_article_meta.iterfind("./article-version-alternatives/article-version"):
                article_version = _get_article_version(article_version_el)
                if article_version:
                    break

        # Before JATS 1.2, the <article> element MAY have had the article-version encoded in specific-use attrib
        if article_version is None:
            article_version = _version_text_to_version_acronym(self.xml.get("specific-use"))

        return article_version if article_version and article_version in self.allowed_article_versions else None

    def article_version_calculator(self, licenses, specific_use_license_count):
        """
        Calculates the article version of the article and which licenses are valid, based on specific-use attribute 
        value in the <article> element at base of XML, and specific-use values of licenses. 
        
        A specific-use value is considered "valid" if it is one of the following ["VoR", "CVoR", "EVoR", "AM]
        
        :param licenses: licenses to be checked
        :param specific_use_license_count: number of licenses which have a specific_use value set
        :return: article_version, licenses 
            article version will either be one of the values ["VoR", "CVoR", "EVoR", "AM"] or None
            licenses will be a list of objects of the format
            {"type": type, "url": url, "title": lic_title, "start": start_date, "specific-use": specific-use}
        """

        # specific use value in article element (will be one of "VOR", "CVOR", "EVOR", "AM" or None)
        article_version = self.jats_article_version()

        # if we have any licenses
        if licenses:
            # if we have any licenses with a specific-use value set
            if specific_use_license_count > 0:
                # if we have some licenses with specific-use and some without, raise an error
                if specific_use_license_count != len(licenses):
                    raise InvalidJATSError("Some licenses have specific-use (article version) values but others do not.")

                # if we have an article_version value then we are only interested in licenses
                # with a specific-use matching that; except if article_version is one of CVOR, EVOR, C/EVOR then
                # any licences with specific-use VOR will be used
                if article_version:
                    licenses_matching_article_version = []
                    vor_licences = []
                    for licence in licenses:
                        lic_specific_use = licence["specific-use"]
                        if lic_specific_use == article_version:
                            licenses_matching_article_version.append(licence)
                        elif lic_specific_use == "VOR" and "VOR" in article_version:
                            vor_licences.append(licence)
                    # if any licenses with specific-use values matching article-version are returned
                    if licenses_matching_article_version:
                        licenses = licenses_matching_article_version
                    # otherwise if we have 'VOR' licences & article-version is 'CVOR', 'EVOR' or 'C/EVOR'
                    elif vor_licences:
                        licenses = vor_licences
                    # else, if we have a valid article specific-use, but none of our licenses have the same specific-use
                    # value, then raise an error
                    else:
                        raise InvalidJATSError(
                            f"Valid article version value '{article_version}', but no licences share this in their specific-use attribute."
                        )

                # if we don't have an article_version value we try to set it from Licence specific-use value(s)
                else:
                    set_of_specific_use_values = set([licence["specific-use"] for licence in licenses])
                    # if all of our licenses have the same specific-use value then we use that for the article_version
                    if len(set_of_specific_use_values) == 1:
                        article_version = set_of_specific_use_values.pop()
                        # if invalid article_version then raise an error
                        if article_version not in self.allowed_article_versions:
                            raise InvalidJATSError(
                                f"No valid article version value and license specific-use '{article_version}' is unacceptable."
                            )
                    # else the licenses have different specific-use values, so raise an error
                    else:
                        raise InvalidJATSError(
                            f"No valid article version value and licenses have contrasting specific-use values: {set_of_specific_use_values}."
                        )

        return article_version, licenses

    @property
    def copyright_statement(self):
        return self.xp_first_text(self.xml_article_meta, "./permissions/copyright-statement")

    @property
    def authors(self):
        # NOTE - The passed XPATH strings are relative for a reason!
        return self._make_contribs(self.xml_article_meta, "./contrib[contains(@contrib-type, 'author')]")

    @property
    def contributors(self):
        # NOTE - The passed XPATH strings are relative for a reason!
        return self._make_contribs(self.xml_article_meta, "./contrib[not(contains(@contrib-type, 'author'))]")

    @property
    def categories(self):
        # NOTE - these were previously captured as notification.article_subject values, but this was changed in Release 12.10.0
        return self.xp_texts(self.xml_article_meta, "./article-categories/subj-group/subject")

    @property
    def keywords(self):
        """
        Get all TEXT within <kwd> elements or
        <compound-kwd-part content-type="te..."> (i.e. where content-type is e.g. 'text' or 'term')
        """
        return self.xp_texts(self.xml_article_meta, ".//kwd-group/kwd|.//kwd-group/compound-kwd/compound-kwd-part[starts-with(@content-type, 'te')]")

    def _get_ymd_date_parts(self, element):
        # :return: list of numeric strings: 'YYYY', 'MM', 'DD'; any of these can also be None.
        #          Possible return combinations:
        #               'YYYY', 'MM', 'DD'
        #               'YYYY', 'MM', None
        #               'YYYY', None, None
        #               None, None, None
        date_dict = self.etree_to_dict(element)
        year = date_dict.get('year')
        if year is None or len(year) != 4:
            return None, None, None

        # Get month & day, left pad with zero to width of 2 chars
        month = date_dict.get('month')
        if month is None:
            return year, None, None

        # If Month is not numeric value, attempt to convert from text value
        if not month.isdigit():
            from octopus.lib import dates
            # Note that '' will be returned if month is invalid month-name
            month = dates.month_string_to_number(month)

        # left pad with zero as needed
        month = month.zfill(2)

        # Invalid month, so RETURN just the year
        if len(month) > 2 or month < '01' or month > '12':
            return year, None, None

        # If we've got this far then we have a valid month

        day = date_dict.get('day')
        if day:
            day = day.zfill(2)
            # Invalid day number, so reset to None
            if len(day) > 2 or day < '01' or day > '31':
                day = None

        return year, month, day

    @classmethod
    def _get_type_from_date_element(cls, date):
        """
        Simple method to get a date type from a date element

        :param date: Date element (<pub-date> or <date>)

        :return: Tuple ( date-type or pub-type attribute value or None, attribute-name.
        """
        date_type = date.get("date-type")
        if date_type:
            return date_type, "date-type"
        return date.get("pub-type"), "pub-type"

    @staticmethod
    def create_pub_date_from_element(date_el, date_type, text_date, year, month, day):
        """
        Create a pub date dictionary from a date element
        Will be skipped if it does not have a type that is to do with publication dates

        :param date_el: Date element (<pub-date> or <date>)
        :param date_type: Type of date like "pub", "epub", "ppub" etc.
        :param text_date: String date ("YYYY-MM-DD" or "YYYY-MM" or "YYYY")
        :param year: string year "YYYY" format or None
        :param month: string month "MM" format or None; if month is not None, then year must be present
        :param day: string day "DD" format or None; day is not None, then year and month must both be present

        :return: None if the date is not a publication date, otherwise a publication date dict.
             {
                    "date": formatted date ("YYYY-MM-DD" or None),
                    "year": year,
                    "month": month,
                    "day": day,
                    "publication_format": format,

                    # The following elements must be DELETED before adding to a Notification
                    "text_date": date string,
                    "date_len": len(text_date),
                    "date_type": a compbination of date_type and, where date_type is "pub", the date_format,
                    "type_rating": integer rating, used to prioritise date date_type
             }
        """

        type_precedence = {
            "epub": 3,
            "epub-ppub": 2,
            "ppub": 1
        }

        pub_date = None
        date_type = date_type.lower()
        # Convert long form to short
        if date_type in {"published", "publication"}:
            date_type = "pub"

        if date_type in {"pub", "epub", "ppub", "epub-ppub"}:
            pub_format = None
            if date_type == "pub":
                pub_format = date_el.get("publication-format")
            if pub_format not in {"electronic", "print"}:
                # if date_type is "epub" or "epub-ppub", then "electronic" otherwise "print"
                pub_format = "electronic" if date_type[:4] == "epub" else "print"
                
            # Convert "pub" into "epub" or "ppub"
            if date_type == "pub":
                date_type = f"{pub_format[0]}pub"
                
            pub_date = {
                "date": text_date if day else None,   # Either a full YYYY-MM-DD or None
                "year": year,
                "month": month,
                "day": day,
                "publication_format": pub_format,

                # Helper attributes - used when choosing from a set of publication dates
                "text_date": text_date,
                "date_len": len(text_date),
                "date_type": date_type,
                "type_rating": type_precedence[date_type]
            }
        return pub_date

    def get_history_and_pub_dates(self):
        """
        Get a list of all history dates as dicts and the best publication date we can find in Notification form.

        :return: List of history dates (like {"date": "<date>", "type": "accepted"}) and the best publication date.
        """
        pub_dates = []
        # Dict to avoid duplicates
        history_date_dict = {}

        def _process_date_el(date_el, set_pub):
            """
            Process an XML <date> or <pub-date> element. Add valid date to History dict; possibly add a publication
            date to `pub_dates` list (depending on set_pub value).
            :param date_el: Etree date or pub-date element
            :param set_pub: Boolean - True: add a publication date to `pub_dates` list;
                                      False: don't add a publication date to `pub_dates` list
            :return: nothing
            """
            # Get history info for this date element
            date_type, date_attr = self._get_type_from_date_element(date_el)
            # If we have a blank date type, don't process further, but continue with next element in the loop
            if not date_type:
                return

            year, month, day = self._get_ymd_date_parts(date_el)
            # We must have at least a YYYY value in order to proceed
            if not year:
                return

            try:
                text_date = self._make_date_in_ymd_order(year, month, day)
            except ValueError as e:
                raise InvalidJATSError(f'{e} for element: ❮{date_el.tag} {date_attr}="{date_type}"❯')

            # This can return None (if the date-type does not relate to publication, so if it does don't append.
            pub_date = self.create_pub_date_from_element(date_el, date_type, text_date, year, month, day)
            if pub_date:
                # The date-type may have been modified e.g. published -> "pub-print"
                date_type = pub_date["date_type"]
                if set_pub:
                    pub_dates.append(pub_date)

            # Get the current history date for this type or empty string
            hist_date_of_type = history_date_dict.get(date_type, "")
            # If the string date of element is longer than existing history date of same type, add it to the dict
            if len(text_date) > len(hist_date_of_type):
                history_date_dict[date_type] = text_date


        #
        # Extract all publication dates & history dates from the XML
        #
        capture_pub_date = True
        # Iterate over ALL pub-dates - add any found to: `pub_dates` & `history_date_dict`
        for date_el in self.xml_article_meta.iterfind("./pub-date"):
            _process_date_el(date_el, capture_pub_date)

        # If <pub-date> elements were found, we won't try to capture any publication dates from history dates
        capture_pub_date = len(pub_dates) == 0
        # Iterate over ALL history dates, only capture pub dates into `pub_dates` if none yet found
        for date_el in self.xml_article_meta.iterfind("./history/date"):
            _process_date_el(date_el, capture_pub_date)

        pub_hist_el = self.xml_article_meta.find("./pub-history")
        if pub_hist_el is not None:
            # Iterate over ALL date AND pub-date elements (they will be nested within <event> and/or <event-desc> elements)
            for date_el in pub_hist_el.xpath(".//date|.//pub-date"):
                _process_date_el(date_el, capture_pub_date)

        #
        # Select best publication date (if any)
        # See here for specification of publication-date selection:
        # https://jisc365.sharepoint.com/sites/dcrd/OAdev/_layouts/15/WopiFrame.aspx?sourcedoc={7cb989fa-26e5-43f3-a054-b3aac413bfa2}&action=edit&wd=target%28Functional%20Doc.one%7C9f59ce50-43bd-4e3e-8049-9025f6e66e7c%2FPublication%20Date%7Cd8fd8942-8592-4dc0-b66f-c3df95bb583d%2F%29&wdorigin=703
        #
        chosen_pub_date = None
        if pub_dates:
            # Sort on date length (longest first) and date-type-rating (most desirable first)
            pub_dates = sorted(pub_dates, key=lambda x: (x["date_len"], x["type_rating"]), reverse=True)

            # If there are 2 pub-dates of same date-type, same date-length, but different dates then raise Exception
            if len(pub_dates) > 1 and pub_dates[0]["type_rating"] == pub_dates[1]["type_rating"] \
                    and pub_dates[0]["date_len"] == pub_dates[1]["date_len"] \
                    and pub_dates[0]["text_date"] != pub_dates[1]["text_date"]:
                raise InvalidJATSError(f"More that one publication date found for {pub_dates[0]['date_type']} type.")
            else:
                chosen_pub_date = pub_dates[0]

            # Delete the "helper" dict elements that aren't wanted for notification
            for k in ("text_date", "date_len", "date_type", "type_rating"):
                del chosen_pub_date[k]

        #
        # Create history date list
        #
        history_dates = [{"date_type": date_type, "date": date_} for date_type, date_ in history_date_dict.items()]
        return history_dates, chosen_pub_date

    @property
    def issn_tuples(self):
        # Returns array of tuples: (type, id) where type is one of issn,
        # eissn (for electronic version),
        # pissn (for print version)
        issns = []
        for issn in self.xml_journal_meta.iterfind("./issn"):
            itype = 'issn'  # Default value
            # attribute publication-format used in preference as pub-type is deprecated
            temp = issn.get('publication-format')
            if temp:
                # Convert publication-format into one of: eissn|pissn|issn (default)
                itype = {'electronic': 'eissn', 'online-only': 'eissn', 'print': 'pissn'}.get(temp.lower(), 'issn')
            else:
                temp = issn.get('pub-type')
                if temp:
                    # Convert pub-type into one of: eissn|pissn|issn (default)
                    itype = {'epub': 'eissn', 'ppub': 'pissn'}.get(temp.lower(), 'issn')

            issns.append((itype, self.strip_text(issn.text)))

        return issns

    # @property
    # def pmcid(self):
    #     id = self.xp_first_text(self.xml_article_meta, "./article-id[@pub-id-type='pmcid']")
    #     if id is not None and not id.startswith("PMC"):
    #         id = "PMC" + id
    #     return id
    #
    # @property
    # def doi(self):
    #     return self.xp_first_text(self.xml_article_meta, "./article-id[@pub-id-type='doi']")

    @property
    def article_id_tuples(self):
        # Returns array of tuples: (type, id) where type is the type of identifier and id is the identifier value
        ids = []
        for id_el in self.xml_article_meta.iterfind("./article-id"):
            itype = id_el.get('pub-id-type', 'unknown')
            id_ = self.strip_text(id_el.text).lower()
            # Force PMC identifiers to start witt PMC
            if itype == 'pmcid' and not id_.startswith("PMC"):
                id_ = f"PMC{id_}"
            ids.append((itype, id_))
        return ids

    @property
    def page_info_tuple(self):
        """
        Returns a Tuple of page information

        :return: tuple: first-page, last-page, page-range, elocation-num
        """

        # Electronic publications may return page-range data in <elocation-id>
        e_num = self.find_simple_first_text(self.xml_article_meta, './elocation-id')
        first_pg = self.find_simple_first_text(self.xml_article_meta, './fpage')
        last_pg = self.find_simple_first_text(self.xml_article_meta, './lpage')
        pg_range = self.find_simple_first_text(self.xml_article_meta, './page-range')
        if not pg_range:
            pg_range_list = []
            if first_pg:
                pg_range_list.append(first_pg)
            if last_pg:
                pg_range_list.append(last_pg)
            if pg_range_list:
                pg_range = "-".join(pg_range_list)

        return first_pg, last_pg, pg_range, e_num

    @property
    def grant_funding(self):
        """
            Looks for <funding-group><award-group> elements and
                extracts Funder name(s) from <funding-source> elements if present
                extracts Grant number(s) from <award-id> elements if present

            JATS info: https://jats.nlm.nih.gov/publishing/tag-library/1.1/element/award-group.html

            Returns array of funding dictionary object:
            {
                "name" : "<name of funder>",
                "grant_numbers" : ["<list of funder's grant numbers>"]
                --- NOTE that the following identifier element MAY be absent
                "identifier" : [
                    {"type" : "<identifier type>", "id" : "<funder identifier>"}
                ],
            }

        :return: Array of funding elements
        """

        def _add_funder_id_to_dict(dic, funder_id, id_type=None):
            """
            Adds newly found ID to dictionary.  If ID already present in dictionary, but with default ID-type value
            then update with new ID-type if that is different.

            Note may UPDATE funder_id_dict.

            :param dic: Dictionary keyed on Identifier
            :param funder_id: String - funder Id
            :param id_type: String - Type of Id (e.g. doi)
            :return: nothing - but may UPDATE funder_id_dict
            """
            if not id_type:
                # Set the Id type to 'doi' if URL contains doi.org otherwise to 'Id'
                id_type = 'doi' if 'doi.org' in funder_id else 'Id'
            elif id_type == "DOI":
                id_type = "doi"

            found_id_type = dic.get(funder_id)
            # If new Id
            if found_id_type is None:
                # store ID details in dict
                dic[funder_id] = id_type
            # else previously seen id is default and new id is not default
            elif found_id_type == 'Id' and id_type != 'Id':
                # Use new type
                dic[funder_id] = id_type
            # otherwise do nothing as the ID and Type is a duplicate of one already seen

        funding = []
        # Search for all <funding-group><award-group> elements under <article-meta>
        for award_group in self.xml_article_meta.iterfind("./funding-group/award-group"):
            # See if there is a <funding-source>
            # Note that while JATS allows for multiple <funding-source> elements within an <award-group>, this is not
            # known to occur as would suggest multiple funders contribute to the same grant.
            # Hence find rather than findall
            funding_source = award_group.find('funding-source')
            # Need at least one funder name
            if funding_source is None:
                continue

            funder_name = []
            # Capture funder ids using a dict to avoid duplicate ids in case JATS encodes the same information more
            # than onece, for example both as an xlink:href and in an <institution-id> element
            # keyed on funder id, with id-type being the value
            funder_id_dict = {}

            # See if there is a funder id present in xlink:href attribute of <funding-source xlink:href="...">
            funder_id = funding_source.get("{http://www.w3.org/1999/xlink}href")
            if funder_id:
                _add_funder_id_to_dict(funder_id_dict, funder_id)

            # Iterate over all the elements within <funding-source>
            for el in funding_source.iter():
                fun_name = None
                # If <institution-id> need to extract type and id
                if el.tag == 'institution-id':
                    funder_id = self.strip_text(el.text)
                    if funder_id:
                        # Extract type of institution from attribute, will default to 'Id' if none
                        _add_funder_id_to_dict(funder_id_dict, funder_id, el.get('institution-id-type'))
                    # Cater for special case:
                    # <institution-id>Some-Id</institution-id>FUNDER NAME (not in an enclosing tag)
                    fun_name = el.tail
                # if we have a <named-content> element
                elif el.tag == "named-content":
                    content_type = el.attrib.get("content-type")
                    # specifically in the case that the <named-content> has content-type of "funder-id", save the id
                    if content_type == "funder-id":
                        funder_id = self.strip_text(el.text)
                        if funder_id:
                            _add_funder_id_to_dict(funder_id_dict, funder_id)
                    # or if the value "name" is in the content-type, save the name
                    elif "name" in content_type:
                        fun_name = el.text
                    # if neither of these values, then don't take anything from the named-content element
                else:
                    fun_name = el.text

                # If non-empty funder name is found, add to the funder_name list
                fun_name = self.strip_text(fun_name)    # This does a safe strip: handles fun_name with value of None
                if fun_name:
                    funder_name.append(fun_name)

            # Create funder Id array from dictionary
            funder_id_array = [{"type": id_type, "id": id} for id, id_type in funder_id_dict.items()]

            obj = {}
            # Look for any (possibly multiple) <award-id> elements (which contain the Grant Number)
            grant_numbers = [self.strip_text(award.text) for award in award_group.iterfind('award-id')]
            obj["name"] = " ".join(funder_name)
            if funder_id_array:
                obj["identifier"] = funder_id_array
            if grant_numbers:
                obj["grant_numbers"] = grant_numbers
            funding.append(obj)

        return funding

    @property
    def ack(self):
        ack_el = self.xml_article_back.find("ack")
        return None if ack_el is None else self.extract_text_formatted_no_texmath(ack_el)

    @staticmethod
    def _make_date_in_ymd_order(year, month, day):
        """

        :param year: string - year "YYYY" format or None
        :param month: string - month "MM" format or None; if month is not None, then year must be present
        :param day: string - day "DD" format or None; day is not None, then year and month must both be present
        NOTE: These values are expected to be those returned by a call to _get_ymd_date_parts().

        :return: Numeric string date 'YYYY', 'YYYY-MM', 'YYYY-MM-DD' or None
        """

        if day:
            # Note that if day is set then year and month will also be set
            date_str = year + "-" + month + "-" + day
            # Validate the date
            try:
                date(int(year), int(month), int(day))
            except ValueError as e:
                raise ValueError(f"Invalid date '{date_str}' ({e})")
            return date_str

        if month:
            # Note that if month is set then year will be too
            return year + "-" + month

        # year will be a 'YYYY' or None
        return year

    def _make_contribs(self, contrib_root, contrib_xp, default_type="", org_suffix=None):
        """
        Create list of Author or Contributor dicts.

        :param contrib_root: Root for finding <contrib> elements
        :param contrib_xp: XPATH expression for finding <contrib> elements
        :param default_type: String - default contributor type (used for nested contributors within a <collab-wrap>)
        :param org_suffix: String - Organisation name, for adding to suffix (used for nested contributors within a <collab-wrap>)
        :return: List of author/contributor dicts, each containing names, ids, emails, affiliations etc.
        """
        # An organisation name is added/appended to suffix for any contributors within a <collab-wrap> of an organisation group
        if org_suffix:
            org_suffix = f"[{org_suffix}]"

        contributors_list = []

        # List of tuples [(affiliation-path, boolean-indicator-english-lang-required), ...]
        # For aff-alternatives, we only capture affiliations with an `xml:lang` attribute of "en")
        aff_el_lang_attr_tuples_list = [("./aff", False), ("./aff-alternatives", True)]

        def _get_corresp_emails_set(correspid):
            return {self.strip_text(e.text).lower()
                    for e in self.xml_article_meta.xpath(f"//corresp[@id='{correspid}']/email")}

        def _get_collab_group_name(root_el, name_path_tuple):
            """
            Get name of collaboration group
            :param root_el: Etree element from where to start find
            :param name_path_tuple: Tuple of simple xpath selectors
            :return: String - Collaboration-group-name; otherwise None
            """
            for collab_el in name_path_tuple:
                collab = root_el.findtext(collab_el)
                if collab:
                    return collab
            return None

        def _process_contrib(c, grp_affs_list, grp_xref_aff_dict, can_assign_grp_xref_aff_dict):
            """
            Collect details, including affiliations for each collaborator (author or other contributor)

            :param c: Contributor element <contrib>
                (retrieved from an xpath like ./contrib[@contrib-type='author'][not(./collab)])
            :param grp_affs_list: Initial setting of affs, only affs that are inside the contrib-group element without ids
            :param grp_xref_aff_dict: Affs inside collaborator elements with IDs
            :param can_assign_grp_xref_aff_dict: Boolean - True: Can use the grp_xref_aff_dict as final fall-back if no
                                                other affiliations found;
                                                False: CANNOT use grp_xref_aff_dict as final fall-back

            If there are no grp_affs_list or applicable ids for grp_xref_aff_dict or global_aff_dict,
                will use the global_aff_no_ids list as the list of affiliations for the collaborator

            :return: Contributor dict with keys: 'type', 'corresp' (as a minimum) & optionally 'surname', 'firstname',
                'id_tuples', 'emails', 'affiliations' - all string values except 'corresp' which has Boolean value.
            """
            contrib = {
                "type": c.get("contrib-type", default_type),
                "corresp": c.get("corresp") == "yes"
            }

            # Look for <name> or <string-name> element - first directly within <contrib>, then within
            # <contrib><name-alternatives>
            for name_path in ("name", "string-name", "name-alternatives/name", "name-alternatives/string-name"):
                name_el = c.find(name_path)
                if name_el is not None:
                    break

            if name_el is not None:
                surname = self.strip_text(name_el.findtext("surname"))  # NB. strip_text converts None to ''
                contrib["surname"] = surname
                contrib["firstname"] = self.strip_text(name_el.findtext("given-names"))   # strip_text handles None
                suffix = self.strip_text(name_el.findtext("suffix"))
                # An organisation name is added/appended to suffix for any contributors within a <collab-wrap> of an organisation group
                if org_suffix:
                    suffix = (suffix + " " + org_suffix) if suffix else org_suffix
                contrib["suffix"] = suffix
            else:
                # May be a collaboration group
                surname = None
                grp_name = _get_collab_group_name(c, ("collab", "collab-name", "collab-name-alternatives/collab-name[@{http://www.w3.org/XML/1998/namespace}lang='en']"))

                # See if we have a <collab-wrap> element
                collab_wrap = c.find("collab-wrap")
                if collab_wrap is not None:
                    # If <collab-name> was NOT outside the <collab-wrap>, then it should be within it
                    if grp_name is None:
                        grp_name = _get_collab_group_name(collab_wrap, ("collab-name", "collab-name-alternatives/collab-name[@{http://www.w3.org/XML/1998/namespace}lang='en']"))
                    # Now capture any nested authors
                    contributors_list.extend(self._make_contribs(collab_wrap, "./contrib", contrib["type"], grp_name))

                if grp_name:
                    # save collaborator string as the surname
                    contrib["org_name"] = grp_name


            # see if there are IDs (note there may be different type of id like orcid / scopus etc.
            ids = set()
            for cid in c.iterfind("contrib-id"):
                idtype = cid.get("contrib-id-type", '').strip().lower()
                if idtype:
                    id = self.strip_text(cid.text)
                    if idtype == "orcid":
                        # Normalizes IDs with a URL prefix to extract just the last part
                        # E.g. Cater 'http://orcid.org/0000-0003-3523-4408' or '0000-0003-3523-4408'
                        id = get_orcid_from_url(id)
                    # (id-type, id)
                    ids.add((idtype, id))

            emails = set()

            # see if we have any IDs in ext-link elements (valid for NLM)
            for extlink in c.iterfind("ext-link"):
                try:
                    linktype = extlink.attrib["ext-link-type"].strip().lower()
                except KeyError:
                    contrib_type = contrib["type"].capitalize()
                    name = f"{contrib['firstname']} {surname}" if surname else contrib.get("org_name", "")
                    raise InvalidJATSError(f"{contrib_type} ({name}) <contrib> element has an <ext-link> without an 'ext-link-type' attribute.")

                if linktype:
                    id = self.strip_text(extlink.text)
                    # we only want to capture the id if it's an ORCID or an email, else disregard it
                    if linktype == "orcid":
                        # Normalizes IDs with a URL prefix to extract just the last part
                        # E.g. Cater 'http://orcid.org/0000-0003-3523-4408' or '0000-0003-3523-4408'
                        id = get_orcid_from_url(id)
                        ids.add((linktype, id))
                    elif linktype == "email":
                        emails.add(id.lower())

            if len(ids) > 0:
                contrib["id_tuples"] = ids

            # Extract email addresses from children <email> elements
            for e in c.iterfind("email"):
                emails.add(self.strip_text(e.text).lower())

            # Initialise with any affs apply to all collaborators in this collab-group
            affs = grp_affs_list.copy()
            # Affiliations within the contrib element
            aff_ids = []
            # Get affiliations from <aff> and <aff-alternatives> elements within this <contrib> element
            for el_name, aff_alt in aff_el_lang_attr_tuples_list:
                for aff in c.iterfind(el_name):
                    aff_dict = _process_aff_or_aff_alternatives(aff, aff_alt)
                    if aff_dict:
                        id = aff.get('id')  # Wouldn't normally expect affiliations within a collab to have ids
                        if id:
                            aff_ids.append(id)
                        affs.append(aff_dict)

            # Extract ALL Affiliations and email addresses via Xrefs
            for x in c.iterfind("xref"):
                ref_type = x.get("ref-type")

                # Affiliation XREF
                if ref_type == "aff":
                    affid = x.get("rid")
                    # Not already got this one
                    if affid is not None and affid not in aff_ids:
                        aff_ids.append(affid)
                        # First try getting xref affiliation from local dict
                        aff = grp_xref_aff_dict.get(affid)
                        if not aff:
                            # If not in local, look in global aff dict
                            aff = self.global_aff_xref_dict.get(affid)

                        # Xref affiliation found
                        if aff:
                            # We store a COPY of dict (not just a reference to it) because we pop the email later
                            affs.append(aff.copy())

                # Corresponding auth XREF - Extract email addresses ONLY if contain surname within them or if the
                # corresp is associated only with this contributor
                elif ref_type == "corresp":
                    contrib["corresp"] = True
                    # Extract the cross-reference ID
                    correspid = x.get("rid")
                    # it can be None
                    if correspid:
                        # if list not already created
                        if not hasattr(self, 'global_xref_corresp_rids'):
                            # Set list of cross-reference IDs found in <xref ref-type="corresp"> elements which is used to
                            # test whether a particular <corresp> is shared
                            self.global_xref_corresp_rids = [
                                xref.get("rid") for xref in self.xml_article_meta.iterfind(".//contrib/xref[@ref-type='corresp']")
                            ]
                            # dict of emails keyed by shared rid
                            self.global_shared_corresp_rid_emails = {}

                        # If the <corresp> is shared (it's ID appears in more than one <xref> )
                        # then extract only emails containing the contributor's surname
                        if self.global_xref_corresp_rids.count(correspid) > 1:
                            # See if we have previously obtained the emails for this correspid
                            corresp_emails = self.global_shared_corresp_rid_emails.get(correspid)
                            if corresp_emails is None:
                                corresp_emails = _get_corresp_emails_set(correspid)
                                self.global_shared_corresp_rid_emails[correspid] = corresp_emails
                            for email in corresp_emails:
                                # grab the text before the @ symbol in the email addr
                                email_prefix = email.split('@')[0]
                                # Only capture email if it contains the author surname
                                if surname and surname.lower() in email_prefix:
                                    emails.add(email)
                        else:  # <corresp> is associated with only 1 contributor
                            #  so capture ALL email addressses regardless of whether they contain surnames
                            emails |= _get_corresp_emails_set(correspid)


            # If we don't have any affs, assume the global affs without ids relate to this collaborator
            if not affs:
                affs = deepcopy(self.global_aff_no_ids)

            # American Chemical Society "fix"
            # If still no affiliations and NONE of the other contribs has an XREF to an aff,
            # then take all XREF affiliations within the group
            if not affs and can_assign_grp_xref_aff_dict:
                affs = deepcopy(list(grp_xref_aff_dict.values()))

            # Extract and remove any emails from affs
            for aff in affs:
                try:
                    # Combine 2 sets using Union
                    emails |= aff.pop("email")    # Will result in KeyError if "email" not in aff dict
                except KeyError:
                    pass

            # Convert set of emails to list
            if emails:
                contrib["emails"] = list(emails)

            if affs:
                contrib["affiliations"] = affs

            return contrib

        def _set_dict(dic, key, val, strip_tn=False):
            """
            Set dic[key] = val, where val is NOT None or empty.  May strip whitespace or tabs/newlines first. Replaces
            any embedded '\t' or '\n' by ' ' (space).
            :param dic: Dict to populate
            :param key: Dict key
            :param val: Value
            :param strip_tn: Boolean - True: remove leading/trailing "/t" & "/n", but preserve leading/trailing space
                                     - False: Strip everything

            :return: Nothing
            """
            if val:
                stripped = " ".join(val.split())
                # If preserving leading/trailing space, but removing other whitespace
                if strip_tn:
                    # if `val` wasn't all white-space and first char is whitespace
                    if stripped and val[0] in " \n\t":
                        stripped = " " + stripped
                    # if last char is whitespace
                    if val[-1] in " \n\t":
                        stripped += " "
                if stripped:
                    dic[key] = stripped

        def _update_dict(dic, key, val):
            """
            Append to dic[key], where val is NOT None or empty.
            """
            if val:
                try:
                    dic[key] += val
                except KeyError:
                    dic[key] = val

        def _strip_tn(val):
            """
            Strip leading/trailing white-space or \n or \t (newline, tab), replacing with a single white-space character
            (if the `val` string is not empty).
            """
            if val:
                stripped = " ".join(val.split())
                # if `val` wasn't all white-space and first char is whitespace
                if stripped and val[0] in " \n\t":
                    stripped = " " + stripped
                # if last char is whitespace
                if val[-1] in " \n\t":
                    stripped += " "
                return stripped
            return ""

        def _el_institution(aff_dict, raw_dict, el, content):
            """
            Process <institution> element -> by default populates aff_dict["org"], but may populate aff_dict["dept"]
            if content_type attribute is set with particular values.
            """
            content_type = self.strip_text(el.get("content-type"))
            key_val = "dept" if JATS.aff_dept_regex.search(content_type) else "org"
            if content:
                try:
                    # Append to previous value if exists, with comma separator
                    aff_dict[key_val] += f", {content}"
                except KeyError:
                    aff_dict[key_val] = content
            # Capture any text appearing after the <institution> element
            _set_dict(raw_dict, key_val, el.tail, True)
            return key_val

        def _el_id(aff_dict, raw_dict, el, id_val):
            """
            Process <institution-id> element -> add identifier dict {'type': '...', 'id': '...'} to
            aff_dict["identifier"] list.
            """
            id_type = self.strip_text(el.get("institution-id-type"))
            if id_type and id_val:
                id_dict = {"type": id_type.upper(), "id": id_val}
                try:
                    # Append to existing list
                    aff_dict["identifier"].append(id_dict)
                except KeyError:
                    # initialise new list
                    aff_dict["identifier"] = [id_dict]
            # Return None because the order in which they are encountered is not recorded as they are always appended as
            # the last value(s) in the `raw` string.
            return None

        def _el_addr(aff_dict, raw_dict, el, content):
            """
            Process <addr-line> element -> by default, append to aff_dict["street"] string.
            However, if content-type is supplied then element value may append to other aff_dict keys:
            "city", "state", "country", "postcode"
            """
            key_val = "street"  # Default setting
            content_type = el.get("content-type")
            if content_type:
                if "code" in content_type:
                    key_val = "postcode"
                elif content_type in ("city", "state", "country"):
                    key_val = content_type

            if content:
                try:
                    # Append to existing value with a comma separator
                    aff_dict[key_val] += f", {content}"
                except KeyError:
                    aff_dict[key_val] = content
            # Capture any text appearing after the <addr-line> element
            _set_dict(raw_dict, key_val, el.tail, True)
            return key_val

        def _el_country(aff_dict, raw_dict, el, content):
            """
            Process <country> element -> Create aff_dict["country"] string. Also, if there is a country attribute (which
            contains country-code) then create an aff_dict["country_code"] string
            """
            key_val = "country"
            _set_dict(aff_dict, key_val, content, False)
            country_code_attr = self.strip_text(el.get("country"))
            if country_code_attr:
                aff_dict["country_code"] = country_code_attr
            # Capture any text appearing after the <country> element
            _set_dict(raw_dict, key_val, el.tail, True)
            return key_val

        def _el_email(aff_dict, raw_dict, el, content):
            """
            Process <email> element -> Create or Add to aff_dict["email"] Set (NB. Emails are stored in a set).
            """
            key_val = "email"
            if content:
                content = content.lower()
                try:
                    # Append to existing Set
                    aff_dict[key_val].add(content)
                except KeyError:
                    # initialise new Set
                    aff_dict[key_val] = {content}
            # NB. In the (unlikely) event that there are multiple emails, only the tail of the last email will be captured
            # (earlier tails will be overwritten by subsequent ones)
            _set_dict(raw_dict, key_val, el.tail, True)
            return key_val

        def _walk_aff(aff_dict, raw_dict, el_order, el):
            """
            Recursively "walk" XML tree extracting affiliation information:
            * structured affiliation text is assigned to aff_dict
            * unstructured affiliation text (i.e. text outside of a recognised XML element) is assigned to raw_dict
            :param aff_dict: Dict to be populated with structure affiliation values
            :param raw_dict: Dict to be populated with affiliation content NOT captured within aff_dict
            :param el_order: List storing Aff-key value in the  order in which affiliation elements are encountered
            :param el: The affiliation element being parsed
            :return: Tuple 2 strings- (Text or None, Aff-key value)
            """
            # processing control dict - maps XML element to a key for aff_dict / raw_dict, and a processing indicator or
            # function.
            lookup = {
                # "XML element": ( "Aff-key" or None, Boolean-or-Function-or-None, Boolean-capture-content )
                #                3 tuple elements:
                #                   1) Aff-key is used for aff_dict and raw_dict (but is None where 2nd tuple
                #                      element is a function or where element content is NOT being stored);
                #                   2) Boolean-or-Function-or-None:
                #                        - Boolean value -  False: Don't populate aff_dict (only raw_dict);
                #                                           True: populate aff_dict & raw_dict
                #                        - Function used for special processing of corresponding XML elements;
                #                        - None - Don't store anything, simply return element content + tail value
                #                   3) Boolean-capture-content determines whether Element content is captured.
                "aff": ("aff", False, True),    # special element, aff.content stored only in raw
                "sup": (None, None, False),     # Don't capture content, otherwise treat as non-core element
                "label": (None, None, False),   # Don't capture content, otherwise treat as non-core element
                "phone": (None, None, False),   # Don't capture content, otherwise treat as non-core element
                "institution": (None, _el_institution, True),   # core element
                "institution-id": (None, _el_id, True),     # core element
                "addr-line": (None, _el_addr, True),    # core element
                "city": ("city", True, True),       # core element
                "state": ("state", True, True),     # core element
                "country": ("country", _el_country, True),  # core element
                "postal-code": ("postcode", True, True),    # core element
                "email": (None, _el_email, True)    # core element (but eventually popped from aff for use elsewhere)
            }
            try:
                # See if we have encountered a recognised XML element (i.e. one associated with structured affiliation
                # info, such as <institution> or <city>
                aff_key, aff_proc, aff_content = lookup[el.tag]
                if aff_key and aff_key not in el_order:
                    # el_order records the order in which key elements are encountered
                    el_order.append(aff_key)
            except KeyError:
                # We have encountered an XML element that is most likely a formatting tag (e.g. <bold>
                # Don't directly store content, return content + tail,
                aff_key, aff_proc, aff_content = None, None, True

            content = _strip_tn(el.text) if aff_content else ""

            last_core_key = None    # last_core_key is the last Aff-key processed
            # Capture all text from inner elements (if there are any) - recursively call *this* function (_walk_aff)
            for element in el:
                # For each element, execute _extract_aff on that element and add the content
                _content, _key = _walk_aff(aff_dict, raw_dict, el_order, element)
                # if _key is present then _content will always be None
                if _key:
                    last_core_key = _key
                elif _content:
                    if last_core_key:
                        _update_dict(raw_dict, last_core_key, _content)
                    else:
                        content += _content

            # Non-core element - contents NOT immediately stored in aff_dict, but are returned
            if aff_proc is None:
                if last_core_key:
                    # E.g. if we are  processing: `<bold>Some text</bold> <city>A City</city> or other`
                    # --> "Some text " is returned & "or other" is appended to raw_dict for the last_core_key ('city')
                    _update_dict(raw_dict, last_core_key, _strip_tn(el.tail))
                else:
                    # Add any "tail" text i.e. text appearing after the inner element to the content
                    # E.g. if we are  processing: `<bold>Some text</bold> or other` --> we return "Some text or other"
                    content += _strip_tn(el.tail)
                return content, None        ## RETURN ##


            if aff_proc is False:
                # Store content in raw_dict
                _set_dict(raw_dict, aff_key, content)
            elif aff_proc is True:
                # Store content in aff_dict & tail text (i.e. what immediately follows the XML element) in raw_dict
                _set_dict(aff_dict, aff_key, content, False)
                _set_dict(raw_dict, aff_key, el.tail, True)
            else:
                # Use function to process the element - function will update aff_dict & may also update raw_dict
                # it will return an aff_key value (may be None)
                aff_key = aff_proc(aff_dict, raw_dict, el, content.strip())
                if aff_key and aff_key not in el_order:
                    # el_order list records the order in which key elements are encountered
                    el_order.append(aff_key)

            # If we have got this far, then content will have been stored in aff_dict (or raw_dict) so return empty string
            return None, aff_key

        def _dict_has_non_blank_values(d):
            """
            Determine whether dictionary values are ALL whitespace
            @param d: Dictionary to assess
            @return: Boolean - True: At least one of dictionary values contains Non-whitespace
                               False: All dictionary values are whitespace ONLY
            """
            for v in d.values():
                # Convert string to list by splitting - will return non-empty list if string NOT all whitespace
                if v.split():
                    return True
            return False

        def _extract_aff(aff_el):
            """
            Extracts text from an affiliation <aff> element with the following rules:
                - IGNORE text within <sup> or <label> elements, but capture any following (tail) text
                - Text within particular target XML elements, such as <institution> or <addr-line> or <city>, is captured
                   and stored in aff_dict structure (see below for example)
                - Text outside of target XML elements is captured and stored in raw_dict structure which is later used
                   (in conjunction with aff_dict contents) to generate an aff_dict["raw"] string.

            EXAMPLE AFFILIATION fully structured (i.e. no text outside of the core elements):
                <aff id="aff1">
                    <sup>1</sup>
                    <institution-wrap>
                        <institution content-type="dept">Biotechnology Department</institution>
                        <institution>National Physical Laboratory</institution>
                        <institution-id institution-id-type="grid">grid.410351.2</institution-id>
                        <institution-id institution-id-type="ror">https://ror.org/015w2mp89</institution-id>
                    </institution-wrap>
                    <addr-line>Hampton Road</addr-line>
                    <city>Teddington</city>
                    <state>Greater London</state>
                    <country country="GB">United Kingdom</country>
                    <postal-code>TW11 0LW</postal-code>
                </aff>

                When an affiliation like this is processed, the raw_dict will NOT be used and NO aff_dict["raw"]
                element will be created.

            EXAMPLE AFFILIATION partially structured (i.e. Some text outside of the core elements):
                <aff>
                    <institution>Chemistry Department, Bristol University</institution>, Cantocks Close, <City>Bristol</City>, BS2 9HA
                </aff>

                When an affilation like this is processed, text from the core elements will be captured in
                aff_dict["org"]="Chemistry Department, Bristol University" and aff_dict["city"]="Bristol".
                Other text will be captured in raw_dict (in this case: raw_dict["org"]=", Cantocks Close, " and
                raw_dict["city"]=", BS2 9HA".  Because raw_dict is populated, a "raw" string will ultimately be generated
                and added to aff_dict["raw"].

            :param aff_el: <aff> element
            :return: Dict - Structured affiliation dict
                EXAMPLE - showing ALL possible keys (in practice fewer keys will be returned where data doesn't exist)
                    {
                        "identifier": [{"type": "ISNI", "id": "isni-1234"}, {"type": "ROR", "id": "ror-123"}],
                        "org": "Cottage Labs org",
                        "dept": "Moonshine dept",
                        "street": "Lame street",
                        "city": "Cardiff",
                        "state": "Gwent",
                        "postcode": "HP3 9AA",
                        "country": "England",
                        "country_code": "GB",
                        "email": {"name@something.com"}  # SET of emails
                        "raw": "Cottage Labs org, Moonshine dept, Lame street, Cardiff, Gwent, HP3 9AA, England, ISNI: isni-1234, ROR: ror-123"
                    }
            """
            aff_dict = {}   # Stores structured affilation data (& possibly unstructured in "aff" element)
            raw_dict = {}   # Stores text NOT found within particular structured elements
            el_order = []   # Records the order in which particular elements are encountered - used to create "raw" string.

            # Walk over the <aff> to extract all information - updating aff_dict, raw_dict and el_order list
            _walk_aff(aff_dict, raw_dict, el_order, aff_el)

            # If we found some non-whitespace raw text (not contained within other elements), then create a raw string
            if raw_dict and _dict_has_non_blank_values(raw_dict):
                raw = ""
                # The raw string is created by recombining information from aff_dict and raw_dict in the same order
                # in which the XML elements were encountered.
                for key in el_order:
                    # For these specified keys, we do NOT look in aff_dict for content to add to raw string.
                    a_txt = None if key in ("aff", "email") else aff_dict.get(key)
                    b_txt = raw_dict.get(key)
                    if a_txt:
                        raw += a_txt
                        if not b_txt:
                            raw += " "
                    if b_txt:
                        raw += f"{b_txt} "
                # Finally add any identifiers as formatted strings within parentheses
                ids = ["{type}: {id}".format(**id_dic) for id_dic in aff_dict.get("identifier", [])]
                if ids:
                    raw += f"({', '.join(ids)})"
                # Add raw string to aff_dict
                aff_dict["raw"] = " ".join(raw.split())     # Remove multiple spaces, new-lines etc.

            return aff_dict

        def _process_aff_or_aff_alternatives(el, aff_alt=False):
            """
            Extract affiliation from either an <aff> element or an English language <aff> within an <aff-alternatives>
            element.
            :param el: <aff> element
            :param aff_alt: Boolean - True: el is <aff-alternatives> - extract only English language <aff> element
                                      False: el is <aff> - extract info regardless of attribute
            :return: Dict - Structured affiliation or None
            """
            # Within an <aff-alternatives> we are looking only for English language affiliations
            if aff_alt:
                # Look for aff with xml:lang="en" attribute or containing an <institution xml:lang="en"> element
                for _aff_el in el.iterfind("aff"):
                    aff_lang = _aff_el.get("{http://www.w3.org/XML/1998/namespace}lang")
                    english_found = None
                    if aff_lang:
                        if aff_lang.lower() == "en":
                            english_found = True
                    else:
                        # Look for <institution xml:lang="en"> (may be contained within an <institution-wrap> element)
                        english_found = _aff_el.find(".//institution[@{http://www.w3.org/XML/1998/namespace}lang='en']")
                    if english_found is not None:
                        return _extract_aff(_aff_el)
                return None     # No english language aff found
            else:   # we are processing an <aff>
                return _extract_aff(el)


        # if we haven't already cached global XML affiliations then cache them
        if not hasattr(self, "global_aff_xref_dict"):
            self.global_aff_xref_dict = {}
            self.global_aff_no_ids = []
            for el_name, aff_alt in aff_el_lang_attr_tuples_list:
                # Get global affiliations - that are outside of <contrib-group>'s
                for aff_el in self.xml_article_meta.iterfind(el_name):
                    aff_dict = _process_aff_or_aff_alternatives(aff_el, aff_alt)
                    if aff_dict:
                        aff_id = aff_el.get('id')
                        if aff_id:
                            self.global_aff_xref_dict[aff_id] = aff_dict
                        else:
                            self.global_aff_no_ids.append(aff_dict)

        # Iterate all contrib-groups that are children of <article-meta> or a particular <contrib> containing a <collab-wrap>
        for c_grp in contrib_root.iterfind("./contrib-group"):
            # Capture affiliation elements within the <contrib-group> but outside of any <contrib>
            c_grp_aff_strings = []
            c_grp_aff_xref_dict = {}

            # Get affiliations from <aff> & <aff-alternatives> elements which are immediate children of <contrib-group>
            # i.e. NOT within any <contrib> element
            for el_name, aff_alt in aff_el_lang_attr_tuples_list:
                for c_grp_aff in c_grp.iterfind(el_name):
                    aff_dict = _process_aff_or_aff_alternatives(c_grp_aff, aff_alt)
                    if aff_dict:
                        id_ = c_grp_aff.get('id')
                        if id_:
                            # contrib-group affiliation WITH id values (hence assume Xrefs)
                            c_grp_aff_xref_dict[id_] = aff_dict
                        else:
                            # contrib-group affiliations WITHOUT id values
                            c_grp_aff_strings.append(aff_dict)

            # Determine whether the <contrib-group> contains ANY <contrib> that contains an XREF to an affiliation
            no_contrib_has_xref_aff = None == c_grp.find("./contrib/xref[@ref-type='aff']")

            # for each author or non-author contributor (depending on value of contrib_xp) WITHIN a contrib-group
            # use xpath here because contrib_xp is complicated & iterfind may not cope!
            for contrib in c_grp.xpath(contrib_xp):
                contrib_dict = _process_contrib(contrib, c_grp_aff_strings, c_grp_aff_xref_dict, no_contrib_has_xref_aff)
                if contrib_dict:
                    contributors_list.append(contrib_dict)

        return contributors_list
