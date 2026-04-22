"""
This engine is used to retrieve Publication meta-data information from PubMed

References:
     PUBMED XML: https://www.nlm.nih.gov/bsd/licensee/data_elements_doc.html
     PUBMED XML DTD: http://dtd.nlm.nih.gov/ncbi/pubmed/out/pubmed_170101.dtd
     Blog - Info on planned changes to APIs: https://ncbiinsights.ncbi.nlm.nih.gov/tag/api/

Retrieving Meta-data from PubMed via REST APIs is a 2 step process:
    (1) Query PubMed 'esearch' REST API to retrieve list of IDs of articles matching the query parameters
        e.g. https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&mindate=2017/01/01&maxdate=2017/02/02

    (2) Loop for each Article ID, use PubMed 'eFetch' REST API to retrieve the Article Meta-data XML
        e.g. https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&retmode=xml&id=28088845

"""
from datetime import date
from time import sleep
from lxml import etree
from octopus.lib.exceptions import InputError, HarvestError
from octopus.lib.http_plus import http_get_xml_etree, http_post_xml_etree, RESTError
from router.shared.models.note import IncomingNotification
from router.harvester.engine.QueryEngine import QueryEngine, current_app

class PubMedQueryEngine(QueryEngine):

    empty_el = etree.fromstring('<NONE></NONE>')

    def __init__(self, es_db, url, harvester_id, start_date, end_date, name_ws):
        """
        Query engine token constructor.

        :param es_db: elasticsearch database connector
        :param url: valid web service provider URL.
        :param harvester_id: string Unique ID of the harvester
        :param start_date : start date to retrieve data from the ws provider
        :param end_date : end date to retrieve data from the ws provider
        :param name_ws: name of webservice as shown to user
        """
        super(PubMedQueryEngine, self).__init__(es_db,
                                                "PubMed",
                                                harvester_id,
                                                name_ws,
                                                self._add_url_params_for_execution(
                                                    url.format(start_date=start_date.strftime("%Y/%m/%d"),
                                                               end_date=end_date.strftime("%Y/%m/%d"))))
        self.max_esearch = self.config.get("PUBMED_ESEARCH_MAX", 200)
        self.fetch_url = self.config["PUBMED_EFETCH_URL"]
        self.api_key = self.config["PUBMED_API_KEY"]

    @staticmethod
    def _add_url_params_for_execution(url):
        """
        Add query params to the URL.

        Currently, retmax and retstart are added. 'retmax' defines how many items there are per page, and retstart
        defines what position to return data from.

        ex:
            retmax=1000, restart=0 (return the first 1000 items)
            retmax=1000, retstart=1000 (return items 1000-1999)
            etc.

        :param url: URL to add the parameters to
        :return: URL with added query parameters
        """
        return url + "&api_key=" + current_app.config["PUBMED_API_KEY"] + "&retmax={max}&retstart={start}"

    @staticmethod
    def is_valid(url):
        """
        Check if the url provided is valid

        :param url: url to validate
        """
        is_valid = False
        url = PubMedQueryEngine._add_url_params_for_execution(url)

        try:
            data = http_get_xml_etree(url.format(start_date=date.today().strftime("%Y/%m/%d"),
                                                 end_date=date.today().strftime("%Y/%m/%d"),
                                                 max=1,
                                                 start=0))
            if not data.get('error'):
                is_valid = True
        except Exception:
            pass

        return is_valid

    def execute(self):
        """
        Executes the query against PubMed URL and stores retrieved date
        into the ES DB.

        For PubMed retrieval of article meta-data is a 2 step process.
        The initial GET query returns list of articles,
        successive calls must be made to retrieve each Article's meta data.

        Initial call returns XML like this:
            <eSearchResult>
             <Count>7717</Count>
             <RetMax>20</RetMax>
             <RetStart>0</RetStart>
             <IdList>
              <Id>26930722</Id>
              <Id>26930721</Id>
              <Id>26930720</Id>
              ...
              <Id>26930703</Id>
             </IdList>
             ... some other stuff ...
            </eSearchResult>

        :return: number of records retrieved
        """
        # Maximum number of articles to return from single request to eSearch API
        max_ret = self.max_esearch
        start = 0
        total = 0
        while True:
            tmp_url = self.url.format(max=max_ret, start=start)
            self.logger.info(f"Executing PubMed URL: {tmp_url}")
            # Get list of articles from PubMed using eSearch API
            etree_data = http_get_xml_etree(tmp_url)

            num_article_ids = int(etree_data.findtext("RetMax", 0))  # Number of articles IDs returned by query
            if num_article_ids:
                try:
                    # Now fetch the Article Metadata for each Article ID in the "IdList" array using eFetch API
                    json_notification_arr = self.get_listed_articles_meta_data(etree_data.find("IdList"))
                except Exception as err:
                    self.logger.error(f"Exception retrieving article meta data: {str(err)}")
                    raise err
                total += len(json_notification_arr)
                self.insert_into_harvester_index(json_notification_arr)

            # If num articles returned is less than max number, we must have now received ALL of them
            if num_article_ids < max_ret:
                break

            # Get next page of etree_data
            start += max_ret

        return total

    @classmethod
    def __pubmed_date_to_ymd(cls, pub_date_el):
        """

        :param pub_date_el:  PubMed date XML elment DTD: PubMedPubDate (Year, Month, Day, (Hour, (Minute, Second?)?)?)
        :return: Date string in format 'YYYY-MM-DD' or None
        """
        year = pub_date_el.findtext("Year")
        month = pub_date_el.findtext("Month")
        day = pub_date_el.findtext("Day")
        # Apply leading 0 to month & day to 2 chars width
        return f"{year}-{month:>02}-{day:>02}" if year and month and day else None

    @classmethod
    def __add_contrib(cls, notification, contrib_list, type):
        """
        Adds authors content into the notification

        :param notification: metadata structure to add the authors info
        :param contrib_list: list of contributors information
        """
        for author in contrib_list:
            obj = {}

            # DTD: Author (((LastName, ForeName?, Initials?, Suffix?) | CollectiveName), Identifier*, AffiliationInfo*)

            # In some cases there may not be a LastName, in which case see if there is a CollectiveName
            last_name = author.findtext("LastName")
            if last_name:
                obj["name"] = IncomingNotification.make_name_dict(author.findtext("ForeName"),
                                                                  last_name,
                                                                  suffix=author.findtext("Suffix")
                                                                  )
            else:   # No LastName, so should be a CollectiveName
                temp = author.findtext("CollectiveName")
                if temp:
                    obj["organisation_name"] = temp
                else: # This should never occur
                    continue    # Next author in contrib_list

            # Look for Identifiers
            id_list = []
            for ident in author.findall("Identifier"):
                id_dict = cls._process_author_id(ident.get("Source"), ident.text)
                if id_dict:
                    id_list.append(id_dict)
            if id_list:
                obj['identifier'] = id_list

            # Process author affiliations
            aff_list = []
            for aff_info in author.iterfind("AffiliationInfo"):
                aff_dict = {}
                raw_aff = aff_info.findtext("Affiliation")
                if raw_aff:
                    aff_dict["raw"] = raw_aff
                ids = []
                for aff_id in aff_info.iterfind("Identifier"):
                    id_txt = aff_id.text
                    id_type = aff_id.get("Source")
                    if id_txt and id_type:
                        ids.append({"type": id_type.upper(), "id": id_txt})
                if ids:
                    aff_dict["identifier"] = ids
                if aff_dict:
                    aff_list.append(aff_dict)

            if aff_list:
                obj['affiliations'] = aff_list

            # If obj is not longer empty
            if obj:
                if type == cls.TYPE_AUTHOR:
                    notification.add_author(obj)
                else:
                    notification.add_contributor(obj)
        return

    @classmethod
    def __add_funding(cls, notification, grant_list):
        """
        Adds funding content into the notification

        :param notification: metadata structure to add the grants info
        :param grant_list: list of grants information
        """
        funding_map = {}
        # for each grant, add the grant number to the funding_map with key of the grant's funder name
        for grant in grant_list:
            funder = grant.findtext("Agency")
            if funder:
                grant_number = grant.findtext("GrantID")
                if funder not in funding_map:
                    funding_map[funder] = []
                if grant_number:
                    funding_map[funder].append(grant_number)

        # for each funder, create a funder object of format {"name": name, "grant_numbers": [list of grant numbers]}
        funding_objs = [{"name": funder, "grant_numbers": grants} for funder, grants in funding_map.items()]

        if funding_objs:
            notification.funding = funding_objs

    @classmethod
    def xml2json(cls, article_xml):
        '''
        Converts PubMed XML format to JSON metadata

        :param article_xml : PubmedArticle xml notification from PubMed - see FILE HEADER for reference URLs
        '''

        if article_xml is None:
            raise Exception('Invalid XML (None) passed to xml2json method.')

        in_note = IncomingNotification()
        # in_note.category = ???    # Allow this to be set after Routing

        medline_citation = article_xml.find('./MedlineCitation')
        if medline_citation is None:
            medline_citation = cls.empty_el

        # PubMed DTD says always 1 MedlineCitation and 1 Article
        medline_article = medline_citation.find('./Article')

        if medline_article is None:
            raise Exception('XML does not contain <MedlineCitation><Article> element.')

        # If Not present, set to essentially an empty XML doc to avoid having to test
        art_journal = medline_article.find('./Journal')
        if art_journal is None:
            art_journal = cls.empty_el

        # Add article title (DTD says 1 ArticleTitle)
        _txt = medline_article.findtext("./ArticleTitle")
        if _txt:
            in_note.article_title = _txt

        # Add Abstract (DTD says 0 or 1 Abstract, and 1 or more AbstractText and possible CopyrightInformation msg
        _abs = medline_article.find("./Abstract")
        if _abs is not None:
            # Add Abstract (DTD says 0 or 1 Abstract, and 1 or more AbstractText
            _list = _abs.xpath("./AbstractText/text()")
            if _list:
                # See if there is a copyright msg for the Abstract
                _cpy = _abs.findtext("./CopyrightInformation")
                if _cpy:
                    _list.append(f" [Abstract copyright: {_cpy}]")
                in_note.article_abstract = " ".join(_list)

        # Add article language (DTD: Language+) - using xpath because extracting text via ".../text()"
        for lang in medline_article.xpath("./Language/text()"):
            in_note.add_article_language(lang.lower())

        # Add JOURNAL title (DTD: Title?)
        _txt = art_journal.findtext("./Title")
        if _txt:
            in_note.journal_title = _txt

        # Add JOURNAL ISSN (DTD: ISSN?)
        _val = art_journal.find("./ISSN")
        if _val is not None:
            # IssnType  (Electronic | Print) #REQUIRED
            # Convert ISSN type to one of our standard values (eissn|pissn|issn)
            issn_type = {'Electronic': 'eissn', 'Print': 'pissn'}.get(_val.get("IssnType"), 'issn')
            in_note.add_journal_identifier(issn_type, _val.text)
        else:
            # See: https://www.nlm.nih.gov/bsd/licensee/elements_descriptions.html#issnlinking
            _txt = medline_citation.findtext("./MedlineJournalInfo/ISSNLinking")
            if _txt:
                in_note.add_journal_identifier("issn", _txt)

        # Take ArticleDate first as it's always an electronic publication date
        pub_date = medline_article.find("./ArticleDate")
        pub_format = "electronic"

        #
        # Extract data from <JournalIssue> group
        #
        # Must always be one of these <JournalIssue>
        _journal_issue_el = art_journal.find("./JournalIssue")
        if _journal_issue_el is not None:

            # If the ArticleDate wasn't populated or has garbage, take the PubDate from the journal issue
            if pub_date is None or not pub_date.findtext("Year"):
                pub_date = _journal_issue_el.find("./PubDate")
                pub_format = "print"

            _txt = _journal_issue_el.findtext("./Volume")
            if _txt:
                in_note.journal_volume = _txt

            _txt = _journal_issue_el.findtext("./Issue")
            if _txt:
                in_note.journal_issue = _txt

        if pub_date is not None:
            in_note.set_publication_date_format(None,
                                                pub_format,
                                                pub_date.findtext("Year"),
                                                pub_date.findtext("Month"),
                                                pub_date.findtext("Day")
                                                )

        # Add article publication/content type  (PubMed DTD: PublicationType+
        # using xpath because extracting text via ".../text()"
        _list = medline_article.xpath("./PublicationTypeList/PublicationType/text()")
        if _list:
            # Convert all members of _list to lower case, then concatenate with "; " separator
            in_note.article_type = "; ".join([x.lower() for x in _list])

        # Add article authors information (Pubmed DTD: AuthorList?  (Author+)
        cls.__add_contrib(in_note, medline_article.findall("./AuthorList/Author"), cls.TYPE_AUTHOR)

        # Add article grants (Pubmed DTD: GrantList?  (Grant+)
        cls.__add_funding(in_note, medline_article.findall("./GrantList/Grant"))

        subject_set = set()
        # Add Mesh headings
        for mesh_el in medline_citation.findall("./MeshHeadingList/MeshHeading"):
            # MeshHeading may look like this - we want to find text from all elements, joining with a hyphen
            # <MeshHeading>
            #     <DescriptorName UI="D016032" MajorTopicYN="N">Randomized Controlled Trials as Topic</DescriptorName>
            #     <QualifierName UI="Q000592" MajorTopicYN="Y">standards</QualifierName>
            # </MeshHeading>
            # itertext() retrieves all text from the child elements
            temp_list = []
            for txt in mesh_el.itertext():
                txt = txt.strip()
                if txt:
                    temp_list.append(txt)
            subject_set.add(" - ".join(temp_list))
        # Add article keywords
        for keyword in medline_citation.findall("./KeywordList/Keyword"):
            subject_set.add(keyword.text)
        if subject_set:
            in_note.article_subject = list(subject_set)

        #
        # Pagination
        #
        _start_page = None
        pagination_el = medline_article.find("./Pagination")
        if pagination_el is not None:
            _start_page = pagination_el.findtext("./StartPage")
            if _start_page:
                in_note.article_start_page = _start_page

            _end_page = pagination_el.findtext("./EndPage")
            if _end_page:
                in_note.article_end_page = _end_page

                # Calculate number of pages (if both start & end are numeric)
                if _start_page and _start_page.isdigit() and _end_page.isdigit():
                    in_note.article_num_pages = int(_end_page) - int(_start_page) + 1

            _txt = pagination_el.findtext("./MedlinePgn")
            if _txt:
                in_note.article_page_range = _txt


        # Get Elocation-ID - note that multiple values may be provided, we ignore DOI which is captured elsewhere, and
        # only save the elocation-ID if different from start-page
        # See https://www.nlm.nih.gov/bsd/licensee/elements_descriptions.html
        for eloc_id in medline_article.findall("./ELocationID"):
            if eloc_id.get("EIdType") == "pii":
                eloc_val = eloc_id.text
                if eloc_val != _start_page:
                    in_note.article_e_num = eloc_id.text
                break

        # PubMed DTD: PubmedData? (i.e. occurs zero or one time)
        pubmed_data = article_xml.find('./PubmedData')
        if pubmed_data is not None:
            # DTD: PubmedData (History?, PublicationStatus, ArticleIdList, ObjectList?)

            # Add article identifiers (DOI,...) (Pubmed DTD: PubmedData? ArticleIdList (ArticleId+)
            for ident in pubmed_data.findall("./ArticleIdList/ArticleId"):
                in_note.add_article_identifier(ident.get("IdType"), ident.text)

            # Process any History dates
            valid_pub_date_types = ['epublish', 'ppublish']
            valid_other_date_types = ['received', 'accepted', 'revised', 'retracted', 'aheadofprint']
            for date_element in pubmed_data.findall("./History/PubMedPubDate"):
                date_type = date_element.get("PubStatus")

                # Convert "epublish" -> "epub" and "ppublish" -> "ppub"
                if date_type in valid_pub_date_types:
                    date_type = date_type[:4]
                # Not a published or other date type, so continue
                elif date_type not in valid_other_date_types:
                    continue

                ymd_date = cls.__pubmed_date_to_ymd(date_element)
                if not ymd_date:
                    continue

                # Add history date
                in_note.add_history_date(date_type, ymd_date)

                # If accepted also set the accepted date
                if date_type == 'accepted':
                    in_note.accepted_date = ymd_date

            # Get Publication status.
            # IMPORTANT - this is done last so can overwrite the Publication status set automatically
            # via notification.set_publication_date_format OR notification.accepted_date
            _txt = pubmed_data.findtext('./PublicationStatus')
            if _txt:
                in_note.publication_status = _txt

        return in_note.json()

    def get_listed_articles_meta_data(self, id_list):
        """
        Retrieves xml format notifications from PubMed provider and convert them
        into JSON format

        :param id_list: list of etree Element IDs to retrieve XML from

        :return: array with JSON to be inserted into ES DB
        """
        json_output = []
        id_vals = [id_.text for id_ in id_list]
        ids = ",".join(id_vals)

        # There have been intermittent problems getting data from pubmed...
        max_tries = 3
        tries = 0
        while True:
            try:
                # Large requests need to be POSTED
                # NB. there have been problems with this, so can use GET where number of ids <= 200
                if len(id_vals) > 200:
                    # POST the payload to PubMed URL, receive the results in etree object form
                    payload = {
                        "api_key": self.api_key,
                        "db": "pubmed",
                        "rettype": "xml",
                        "retmode": "xml",
                        "id": ids
                    }
                    # POST as a multipart form request
                    etree_data = http_post_xml_etree(self.fetch_url, data=payload, multipart=True)
                else:
                    # GET request available for smaller max_search values
                    url = f"{self.fetch_url}?api_key={self.api_key}&db=pubmed&retmode=xml&rettype=xml&id={ids}"
                    etree_data = http_get_xml_etree(url)
            except RESTError as e:
                tries += 1
                if tries < max_tries:
                    self.logger.warning(f"PubMed article XML request failed, sleeping {tries}s, then retrying - {repr(e)}")
                    sleep(tries)    # Sleep for increasing seconds each attempt
                else:
                    raise HarvestError(f"Failed to retrieve article XML after {max_tries} attempts - {repr(e)}") from e
            else:
                # No exception, so exit the while loop
                break

        for entry in etree_data.getchildren():
            # We only process <PubmedArticle> entries, NOT things like <PubmedBookArticle>
            if entry.tag == "PubmedArticle":
                try:
                    article_json = self.xml2json(entry)
                    json_output.append(article_json)
                except Exception as err:
                    self.logger.warning(f"Problem parsing PubMed notification - {repr(err)}. Ignoring & continuing.")
        return json_output


    def convert_to_notification(self, document, service_id=None):
        """
        Function which adds data to IncomingNotification retrieved from temporary Harvester database table (ES index)

        :param document: the IncomingNotification JSON document .
        :param service_id: webservice identifier.
        :return dict of IncomingNotification
        """
        try:
            notification = IncomingNotification(document)
            # Add provider information to the Router incoming notification model
            notification.provider_agent = self.harv_name
            notification.provider_harv_id = service_id
            notification.provider_route = "harv"
            notification.provider_rank = self.rank
        except Exception as err:
            raise InputError(f'Creating PubMed IncomingNotification - {repr(err)}') from err
        return notification.data
