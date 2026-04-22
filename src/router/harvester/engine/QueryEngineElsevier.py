"""
Elsevier query engine code.

Uses Elsevier search API with JSON format, which returns a list of URL pointers to metadata. Requests are made 
to these URLs, and the data returned is received in XML format. 

Documentation/specification here:
https://jisc365.sharepoint.com/:w:/r/sites/dcrd/OAdev/_layouts/15/Doc.aspx?sourcedoc={8017DFAF-674E-4DD8-8029-FEB23A94BC2E}&file=Elsevier_JISC_API_Design_v1_7.docx&action=default&mobileredirect=true
"""
from datetime import date, timedelta
from functools import partial
from octopus.lib.http_plus import http_get_json, http_get_xml_etree
from octopus.lib.exceptions import IncorrectFormatError, RESTError, HarvestError, InputError
from octopus.lib.data import strip_bad_text
from octopus.lib.dates import zfilled_date
from router.shared.models.note import IncomingNotification

from router.harvester.engine.QueryEngine import QueryEngine, current_app


class ElsevierIterator:
    """
    Class that will create an iterator for all metadata entries in a given elsevier API search request.

    It uses JSON for the search requests as they are simple and easy to navigate using JSON, but XML for article
    metadata as the complexity of the metadata can create very unhelpful JSON structures.
    """
    api_key = None

    def __init__(self, search_url, count=100):
        """
        Set the amount of entries we should retrieve per request, and the search URL for this iterator.

        :param search_url: Elsevier search URL for this iterator
        :param count: Total number of items we should expect per search request (100 is recommended maximum)
        """
        self.logger = current_app.logger
        self.logger.info(f"ELSEVIER - Query url: {search_url}")
        self._set_initial_search_url_and_reset(search_url, count)
        ElsevierIterator._api_key()     # Init API Key value

    @classmethod
    def _api_key(cls):
        if cls.api_key is None:
            cls.api_key = current_app.config["ELSEVIER_API_KEY"]
        return cls.api_key

    @classmethod
    def request_json(cls, url):
        """
        Make a JSON request.

        :param url: Elsevier API url to request.
        :return: Dictionary of the returned JSON object.
        """
        headers = {
            "Accept": "application/json",  # Only accept responses in JSON format
            "X-ELS-APIKey": cls._api_key()  # Elsevier API key
        }
        return http_get_json(url, headers)

    @classmethod
    def request_xml(cls, url):
        """
        Make an XML request to the API.

        :param url: Elesvier API url to request.
        :return: LXML Etree object of the returned request content.
        """
        headers = {
            "Accept": "application/xml",  # Only accept responses in XML format
            "X-ELS-APIKey": cls._api_key()  # Elsevier API key
        }
        return http_get_xml_etree(url, headers)

    def empty_iterator(self):
        """
        If our URL isn't set because there was no next url, and we have emptied the items from the previous search
        request, we have finished scraping and the iterator is empty.

        :return: Whether we are done scraping through the given initial url
        """
        return not self.search_url and not self.article_urls

    def _reset(self):
        """
        Reset all properties in case we want to reuse the iterator
        """
        # Reset the URL
        self.search_url = self.initial_search_url
        # Total number of items for the given URL
        self.total = None
        # Number of entries which had missing "prism:url"
        self.missing_prism = 0
        # List of dictionaries with include links to article metadata
        self.article_urls = None

    def _set_initial_search_url_and_reset(self, url, count):
        """
        Set the intial seach URL and (re) initialise all of the other properties
        """
        self.initial_search_url = f"{url}&count={count}&start=0"
        self._reset()

    def _get_next_search_url_if_available(self, links):
        """
        In a list of links retrieved from a search URL response, retrieve the next avaliable URL
        in this page if available.

        :param links: List of JSON links in the following format:
        [
            {
                "@ref": "next,
                "@href": "http://some.url"
                ..
            },
            ...
        ]

        :return: If one of the following links has the ref 'next', the href of that link. Otherwise, None,
        implying that this is the last page of the initial search url.
        """
        for link in links:
            if link.get("@ref") == "next":
                return link.get("@href")
        return None

    def _get_page_of_search_results(self):
        """
        Retrieve the next list of search results from the Elsevier API.

        This returns up to a given amount of results per request (The default is 500.)

        :return: List of entries from the search request. (looks like:
            [
                {
                    "prism:url": "url/for/some/article/metadata"
                    ..
                },
                ...
            ]
        )
        """
        self.logger.debug("ELSEVIER - Making new Search Request")
        data = self.request_json(self.search_url).get("search-results")
        # If we don't have a total yet, set it so we can access it later
        if self.total is None:
            results = data.get("opensearch:totalResults")
            self.logger.info(f"ELSEVIER - Search Request has a total of {results} results")
            self.total = int(results)
            if self.total == 0:
                # Stop the iteration as the total is 0.
                raise StopIteration
        self.search_url = self._get_next_search_url_if_available(data.get("link", []))
        return data.get("entry", [])

    def __next__(self):
        """
        Get the next article metadata.

        This will be called as part of the __iter__ magic method - once StopIteration is raised, the iteration stops
        and it will proceed out of the loop.

        NOTE: We have encountered instances where in the 'entry' results list, we have encountered objects WITHOUT a
        "prism:url" e.g. an object like this:  { "@_fa": "true"} - this function is design to skip these.


        :return: Article XML metadata for the next item if we have any items remaining or None if "prism:url" absent.
        """
        # Infinite loop allows missing "prism:url" to be skipped
        while True:
            # If we don't have a URL because there is no next URL, and there are no items left, stop.
            if self.empty_iterator():
                raise StopIteration
            # If we do have a next URL but we have exhausted the list of article metadata from the previous request,
            # get a new list from the next request.
            elif not self.article_urls:
                self.article_urls = self._get_page_of_search_results()

            try:
                # Remove the next document in list order
                item = self.article_urls.pop(0)
                prism_url = item["prism:url"]
                # Retrieve article metadata using the prism:url.
                return self.request_xml(prism_url)
            except KeyError:
                self.missing_prism += 1
                self.total -= 1
                # Continue to next
            except IndexError:
                self.logger.info("ELSEVIER - Unexpected end of search results")
                raise StopIteration
            except (IncorrectFormatError, RESTError) as e:
                raise HarvestError("Search phase - Could not retrieve article XML.", repr(e)) from e

    def __iter__(self):
        return self


class QueryEngineElsevier(QueryEngine):

    ITEM_STAGE_PUB_STATUS_MAP = {
        "S5": "Accepted",
        "S100": "Accepted",
        "S200": "Accepted",
        "S250": "Published",
        "S300": "Published",
        "S350": "Published"
    }

    def __init__(self, es_db, url, harvester_id, start_date=None, end_date=None, name_ws=''):
        """
        Initialise the query engine with a formatted Elsevier API url.

        :param es_db: elasticsearch database connector
        :param url: valid web service provider URL. It will need the following format string variables:
            {start_date}.
        :param harvester_id: string Unique ID of the harvester
        :param start_date: Start date to retreive data from Elsevier
        :param end_date: Not needed for Elsevier but is a member of the parent class, so it is needed.
        :param name_ws: name of webservice as shown to user
        """
        super(QueryEngineElsevier, self).__init__(es_db,
                                                  "Elsevier",
                                                  harvester_id,
                                                  name_ws,
                                                  self.format_url(url, start_date, end_date))

    @staticmethod
    def format_url(url, start_date=None, end_date=None):
        """
        Format a url with a given start date or if start_date is not provided, default to today's date.

        :param url: URL that should have a {start_date} format variable
        :param start_date: Datetime object of the date to start processing from
        :param end_date: Datetime object of the last date to process

        :return: Formatted URL with a set start_date
        """
        # In order to harvest articles received on or after our target date using the Elsevier AFT operator,
        # we need to set the start_date to the day before our target date.
        start_date = (start_date or date.today()) - timedelta(days=1)
        # In order to harvest articles received on or before the end date using the Elsevier BEF operator,
        # we need to set the end_date to the day after the end date.
        end_date = (end_date or date.today()) + timedelta(days=1)

        # YYYYMMDD is the format required for Elsevier's API.
        return url.format(start_date=start_date.strftime("%Y%m%d"), end_date=end_date.strftime("%Y%m%d"))

    @classmethod
    def _create_aff_text_lookup_dict(cls, affiliation_elements, namespaces):
        """
        Create a lookup dict for affiliations and their IDs.

        A <ce:author> element may have multiple <ce:cross-ref> elements that include a 'refid' - these refids
        will refer to an affiliation with the corresponding id attribute. An affilation may be needed multiple times,
        so it makes sense to have a lookup dict to easily grab the text content of a given affilation.

        :param affiliation_elements: List of <ce:affiliation> elements (etree objects)
        :return: A dictionary that maps the ID of a <ce:affiliation> element to the text content of the element.
        """
        lookup_dict = {}
        for affiliation_element in affiliation_elements:
            aff_dict = {}
            textfn = affiliation_element.find("ce:textfn", namespaces=namespaces)
            if textfn is not None:
                # Get text from all elements inside the textfn element, then remove all useless text (like \n)
                aff_dict["raw"] = strip_bad_text(textfn.xpath("string()"))
            structured_aff = affiliation_element.find("sa:affiliation", namespaces=namespaces)
            if structured_aff is not None:
                org = ", ".join(o.text for o in structured_aff.iterfind("sa:organization", namespaces=namespaces))
                if org:
                    aff_dict["org"] = org
                for xml_el, aff_key in (
                    ("sa:address-line", "street"),
                    ("sa:city", "city"),
                    ("sa:state", "state"),
                    ("sa:country", "country"),
                    ("sa:postal-code", "postcode")
                ):
                    _txt = structured_aff.findtext(xml_el, namespaces=namespaces)
                    if _txt:
                        aff_dict[aff_key] = _txt

            if aff_dict:
                aff_id = affiliation_element.get("id")
                if aff_id:
                    lookup_dict[aff_id] = aff_dict

        return lookup_dict

    @classmethod
    def _process_author_group(cls, author_group, namespaces):
        """
        Process an author group.

        Each author group will have possibly many affiliations (<ce:affiliation>) and many authors (<ce:author>).

        This will firstly collect all of the affiliations and join the affilation strings with a semicolon.

        After this, it will iterate over all the <ce:author> elements inside this author group, collecting name
        and identifier data. If there was any affiliations in the group, the affiliation data will also be added
        and then yielded as a generator for use in adding a new author to an IncomingNotification.

        :param author_group: <ce:author-group> element
        :param namespaces: Namespaces to use when finding other elements inside the author_group

        :yield: IncomingNotification formatted author dictionary (like:
            {
                "name": {
                    "fullname": "Name Some"
                },
                "identifier": [
                    {"type": "email", "id": "someemail@email.email"}
                ],
                "affiliations": [{"raw": "University of Jisc, Mars"}]
            }
        )
        """
        aff_lookup_dict = cls._create_aff_text_lookup_dict(
            author_group.findall("ce:affiliation", namespaces=namespaces),
            namespaces
        )
        for author in author_group.findall("ce:author", namespaces=namespaces):
            author_findall = partial(author.findall, namespaces=namespaces)
            author_findtext = partial(author.findtext, namespaces=namespaces)

            name_dict = IncomingNotification.make_name_dict(author_findtext("ce:given-name"),
                                                            author_findtext("ce:surname"))
            if not name_dict:
                continue
            author_dict = {"name": name_dict}

            identifiers = []

            orcid = author.get("orcid")
            if orcid:
                identifiers.append({"type": "orcid", "id": orcid})

            for email in author_findall("ce:e-address"):
                if email.get("type", "") == "email":
                    identifiers.append({"type": "email", "id": email.text})

            if identifiers:
                author_dict["identifier"] = identifiers

            aff_list = []
            for cross_reference in author_findall("ce:cross-ref"):
                ref_id = cross_reference.get("refid")
                # If cross-reference is an affiliation
                if ref_id.startswith("aff"):
                    aff_dict = aff_lookup_dict.get(ref_id)
                    if aff_dict:
                        aff_list.append(aff_dict)
                # If cross-ref is a corresponding author
                elif ref_id.startswith("cor"):
                    author_dict["type"] = "corresp"
            if aff_list:
                author_dict["affiliations"] = aff_list

            yield author_dict

    @classmethod
    def _process_grants(cls, sponsors, grant_numbers):
        """
        Process grant numbers and their relative sponsors.

        This will firstly iterate over grant numbers and create a map of these which will be used to map sponsors
        to their grant numbers.

        Sample of actual XML data:
            <ce:grant-sponsor id="gs1" sponsor-id="https://doi.org/10.13039/501100000867">Commonwealth Scholarship Commission</ce:grant-sponsor>
            <ce:grant-number refid="gs1">NGCN-2018-237</ce:grant-number>

        :param sponsors: <ce:grant-sponsor> etree elements, example raw data:
        :param grant_numbers: <ce:grant-number> etree elements, example raw data:
        :return: List of funder dictionary objects for an IncomingNotification (like:
            {
                "name": "My Funder",
                "identifier": [
                    {"type": "FundRef", "id": "doi.org..."}
                ],
                "grant_numbers": ["12412422", ...]
            }
        )
        """
        # Create map of funder refids --> list of grant-numbers
        grant_num_map = {}
        for grant_number in grant_numbers:
            funder_xml_ref_id = grant_number.get("refid")
            if funder_xml_ref_id:
                # If we haven't seen this refid before, create new entry in the map
                if grant_num_map.get(funder_xml_ref_id) is None:
                    grant_num_map[funder_xml_ref_id] = []
                # Add the grant-num to the list
                grant_num_map[funder_xml_ref_id].append(grant_number.text)

        # At this point grant_num_map is a dict of grant-num lists keyed by refid

        funder_dicts = []
        for sponsor in sponsors:
            funder_dict = {"name": sponsor.text}
            # Sponsor ID will be a DOI or other sort of FundRef
            sponsor_id = sponsor.get("sponsor-id")
            if sponsor_id:
                funder_dict["identifier"] = [{"type": "FundRef", "id": sponsor_id}]

            funder_xml_id = sponsor.get("id")
            # Get the list of grant numbers for this funder
            grant_number_list = grant_num_map.get(funder_xml_id, [])
            if grant_number_list:
                funder_dict["grant_numbers"] = grant_number_list

            funder_dicts.append(funder_dict)

        return funder_dicts

    @classmethod
    def _calculate_license_and_embargo(cls, license_url_obj, start_date_obj, is_oa, pub_status):
        """
        Calculate licenses and embargo to be used based on license text, start date & if the licence is open access.
        Based on algorithm found here: https://goo.gl/bVTRL6

        :param license_url_obj: etree object - license_url object
        :param start_date_obj: etree object - start date of license
        :param is_oa: Boolean - whether the article is open access
        :param pub_status: String - publication status: Published or Accepted
        :return: license_dicts, embargo_end
        """
        license_dicts = []
        license_dict = {}
        embargo_end = None
        license_url = None
        start_date = None
        

        # if we have a license url and start date, use them as a template license
        if license_url_obj is not None and license_url_obj.text:
            license_url = license_url_obj.text
            license_dict["url"] = license_url
        if start_date_obj is not None and start_date_obj.text:
            # Start date comes in %Y-%m-%dT... format, will strip away everything after the T
            start_date = start_date_obj.text[:10]
            license_dict["start"] = start_date

        # if the article is a subscription article, we have special processing (if it's an oa article then just
        # use the license info provided and set NO embargo (hence set no embargo_end)
        if not is_oa:
            # if we have existing licensing info
            if license_dict:
                # NOTE: this is a temporary solution requested by Elsevier 15-05-2019. This should be removed when
                # they amend the inconsistent metadata
                # when start-date is present but the licence_url is missing, then
                #   if published then a CC BY-NC-ND license will be assumed;
                #   if not yet published then a text message advising article under embargo will be provided
                if not license_url and start_date:
                    if pub_status == "Published":
                        license_dict["url"] = "http://creativecommons.org/licenses/by-nc-nd/4.0/"
                        embargo_end = start_date
                    else:
                        embargo_end = "9999-12-31"
                        license_dict["title"] = "This article is under embargo with an end date yet to be finalised."
                        del license_dict["start"]
                        
                # if it's an open access license, use the start_date as the embargo end date when start-date is present
                # otherwise text message advising article under embargo will be provided
                elif IncomingNotification.is_open_license(lic_url=license_url):
                    if start_date:
                        embargo_end = start_date
                    else:
                        del license_dict["url"]
                        embargo_end = "9999-12-31"
                        license_dict["title"] = "This article is under embargo with an end date yet to be finalised."
                    
                # if it's NOT an open access license, then set the embargo end date to as late as possible
                else:
                    embargo_end = "9999-12-31"
                    # if we have a start_date, then generate an additional licence with just a title explaining the
                    # likely scenario
                    if start_date:
                        license_dicts.append({"title": "This article is under embargo with an end date yet to be finalised."})
                    # else just add a warning in the title to the existing licence
                    else:
                        license_dict["title"] = "Probably under embargo with an end date yet to be finalised. Please refer to licence."
            # if we have no existing licensing info, then just make up a default licence with embargo end date as
            # late as possible and warning in licence
            else:
                embargo_end = "9999-12-31"
                license_dict["title"] = "This article is under embargo with an end date yet to be finalised."
                
        license_dicts.append(license_dict)
        return license_dicts, embargo_end

    @classmethod
    def convert_etree_to_incoming_notification(cls, etree):
        """
        Convert Elsevier XML article metadata to IncomingNotification metadata.

        :param etree: Elsevier article metadata returned by Elsevier API, converted into Etree object

        :return: IncomingNotification of the metadata retrieved from the etree element, or None if this is an article
            we're uninterested in retrieving
        """
        in_note = IncomingNotification()
        in_note.category = IncomingNotification.ARTICLE

        # Store namespaces
        namespaces = etree.nsmap

        # Because Xpath cannot use a default namespaces with key value of None (i.e. { None: "/namespaceURI" }
        # the default is assigned to a key value of "els", and the original default is deleted
        namespaces["els"] = namespaces.pop(None)

        # Initialize this now as you can find publication statuses in multiple places
        pub_status = None

        # !! xocs:doc section - includes author groups, funding information and license information !! #
        xocs_doc = etree.find("xocs:doc", namespaces)
        if xocs_doc is not None:
            # Partials - just wrappers to make it so we don't have to repeatedly set namespaces=namespaces
            xocs_doc_find = partial(xocs_doc.find, namespaces=namespaces)
            xocs_doc_findall = partial(xocs_doc.findall, namespaces=namespaces)

            xocs_meta = xocs_doc_find("xocs:meta")
            if xocs_meta is not None:
                xocs_meta_find = partial(xocs_meta.find, namespaces=namespaces)

                # The item stage relates to the publication status, as mapped in cls.ITEM_STAGE_PUB_STATUS_MAP
                item_stage = xocs_meta_find("xocs:item-stage")
                if item_stage is not None:
                    pub_status = cls.ITEM_STAGE_PUB_STATUS_MAP.get(item_stage.text)

            if pub_status:
                # This is the date the final article was published online
                pub_date = xocs_meta_find("xocs:vor-available-online-date")
                if pub_date is not None:
                    pub_date = pub_date.text
                    in_note.set_publication_date_format(pub_date, "electronic")
                    # Add publication date to history as epub
                    in_note.add_history_date("epub", pub_date)

                # Check the open-access element -
                # if there is one" we can get the open access license and calculate embargo
                open_access = xocs_meta_find("xocs:open-access")
                start_date = None
                license_url = None
                is_oa = False
                if open_access is not None:
                    # Try the open access element first - the dates are earlier and imply it's an OA article.
                    oa_find = partial(open_access.find, namespaces=namespaces)
                    start_date = oa_find("xocs:oa-access-effective-date")
                    license_url = oa_find("xocs:oa-user-license")
                    # consider this an open access article if is-open-access attribute == "1"
                    is_oa = oa_find("xocs:oa-article-status").get("is-open-access") == "1"

                if start_date is None or license_url is None:
                    # Otherwise find the embargo via the self-archiving element.
                    self_archive = xocs_meta_find("xocs:self-archiving")
                    if self_archive is not None:
                        self_archive_find = partial(self_archive.find, namespaces=namespaces)
                        start_date = self_archive_find("xocs:sa-start-date")
                        license_url = self_archive_find("xocs:sa-user-license")

                license_dicts, embargo_end = cls._calculate_license_and_embargo(license_url, start_date, is_oa, pub_status)

                if embargo_end:
                    in_note.set_embargo(end=embargo_end)
                for license_dict in license_dicts:
                    in_note.add_license(license_dict)

                date_accepted = xocs_doc_find("ce:date-accepted")
                if date_accepted is not None:
                    year = date_accepted.get("year")
                    month = date_accepted.get("month")
                    day = date_accepted.get("day")
                    if year and month:
                        # only set accepted date if we have a full date YYYY-MM-DD
                        if day:
                            accepted_date = zfilled_date(year, month, day)
                            in_note.accepted_date = accepted_date
                        # if we don't have a day, use YYYY-MM date to only be used in history dates
                        else:
                            accepted_date = zfilled_date(year, month)
                        in_note.add_history_date("accepted", accepted_date)

                # we consider this an AM article by default, and a VoR article if it is fully open access and has
                # a pub_status of published
                in_note.article_version = "VOR" if is_oa and pub_status == "Published" else "AM"

                # For each author in all author groups, process that author into a notification author dictionary
                for author_group in xocs_doc_findall("ce:author-group"):
                    for author in cls._process_author_group(author_group, namespaces):
                        in_note.add_author(author)

                sponsors = xocs_doc_findall("ce:grant-sponsor")
                # Can only make a funder dictionary if we have sponsors.
                if sponsors:
                    grant_numbers = xocs_doc_findall("ce:grant-number")
                    in_note.funding = cls._process_grants(sponsors, grant_numbers)

        # if we were unable to derive publication status from the item stage, this implies that this is a
        # version of the article we're uninterested in retrieving, so exit without creating a note
        if not pub_status:
            current_app.logger.info(f"Ignoring notification as does not have notification status of interest")
            return None

        # !! coredata section - includes journal information and article information like publication name, titles. !! #
        # the els namespace refers to the namespace we set as 'els' at the start of the function
        coredata = etree.find("els:coredata", namespaces)
        if coredata is not None:
            coredata_findtext = partial(coredata.findtext, namespaces=namespaces)

            pub_name = coredata_findtext("prism:publicationName")
            if pub_name:
                in_note.journal_title = pub_name

            issn = coredata_findtext("prism:issn")
            if issn:
                in_note.add_journal_identifier("issn", issn)

            title = coredata_findtext("dc:title")
            if title:
                in_note.article_title = strip_bad_text(title)

            doi = coredata_findtext("prism:doi")
            if doi:
                in_note.add_article_identifier("doi", doi)

            description = coredata_findtext("dc:description")
            if description:
                in_note.article_abstract = description

            start_page = coredata_findtext("prism:startingPage")
            if start_page:
                in_note.article_start_page = start_page

            end_page = coredata_findtext("prism:endingPage")
            if end_page:
                in_note.article_end_page = end_page

            page_range = coredata_findtext("prism:pageRange")
            if page_range:
                in_note.article_page_range = page_range

            e_num = coredata_findtext("prism:articleNumber")
            if e_num:
                in_note.article_e_num = e_num

            issue = coredata_findtext("prism:issueIdentifier")
            if issue:
                in_note.journal_issue = issue

            volume = coredata_findtext("prism:volume")
            if volume:
                in_note.journal_volume = volume

            issue_date = coredata_findtext("prism:coverDate")
            if issue_date:
                in_note.add_history_date("issued", issue_date)

        # Set pub_status last to overwrite the value which may have been set automatically when
        # acceptance and/or publication date was set
        in_note.pub_status = pub_status

        # We are sure all notifications are Articles because the Elsevier search query restricts results
        # using ContentType = Journals
        in_note.article_type = "Article"

        return in_note.data

    def execute(self):
        """
        Using the ElsevierIterator class, iterate over the url given to this class and convert each piece of article
        metadata received into an IncomingNotification. After the iterator is empty, send the notifications
        to elasticsearch.

        :return: Total pieces of metadata processed.
        """
        article_iterator = ElsevierIterator(self.url)
        batched_items = []
        for elsevier_article_metadata_etree in article_iterator:
            item = self.convert_etree_to_incoming_notification(elsevier_article_metadata_etree)
            if item:
                batched_items.append(item)
        if batched_items:
            # Attempt to insert items into elasticsearch
            self.insert_into_harvester_index(batched_items)

        num_missing = article_iterator.missing_prism
        if num_missing:
            if article_iterator.total == 0:
                raise HarvestError(f"All {num_missing} search results were missing 'prism:url' elements")
            self.logger.info("ELSEVIER - {} search {} missing a 'prism:url' element".format(
                num_missing, "result was" if num_missing == 1 else "results were"))

        return article_iterator.total

    def convert_to_notification(self, document, service_id=None):
        """
        Function which adds data to IncomingNotification retrieved from temporary Harvester database table (ES index)
        As this document will already be in IncomingNotification format, simply add the Elsevier provider agent
        and the given service_id.

        :param document: The IncomingNotification JSON document .
        :param service_id: webservice identifier.

        :return: dict of IncomingNotification
        """
        try:
            in_note = IncomingNotification(document)
            # Add provider information to the Router incoming notification model
            in_note.provider_agent = self.harv_name
            in_note.provider_harv_id = service_id
            in_note.provider_route = "harv"
            in_note.provider_rank = self.rank
            # As it must be Elsevier, simply add the journal publisher here
            in_note.add_journal_publisher("Elsevier")

        except Exception as err:
            raise InputError(f"Creating Elsevier IncomingNotification - {repr(err)}") from err
        return in_note.data


    @staticmethod
    def is_valid(url):
        """
        Format the URL with a start date and test if it returns a service error.
        If it doesn't return a service error, the request is valid.

        :param url: URL with {start_date} somewhere in the url string

        :return: Boolean: True if the URL is a valid Elsevier API url, False if not.
        """
        url = QueryEngineElsevier.format_url(url)
        # If there's an error, the key "service-error" will be in the top level object
        try:
            return "search-results" in ElsevierIterator.request_json(url)
        # If this isn't actually JSON, (500 server error does this) return False.
        except Exception:
            return False
