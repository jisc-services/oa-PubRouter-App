"""
Created on 21 Oct 2015

Engine for EPMC multipage query.

References:

    Information about fields: http://europepmc.org/Help#searchbyID
    Info on planned changes to APIs: https://groups.google.com/a/ebi.ac.uk/g/epmc-webservices

@author: Mateusz.Kasiuba
"""
from datetime import date, timedelta
from urllib.parse import quote

from octopus.lib.exceptions import InputError
from octopus.lib.data import dictionary_get
from octopus.lib.dates import ymd_to_datetime
from octopus.lib.http_plus import http_get_json
from router.shared.models.note import IncomingNotification
from router.harvester.engine.QueryEngine import QueryEngine


class QueryEngineEPMC(QueryEngine):

    def __init__(self, es_db, url, harvester_id, date_start=None, date_end=None, name_ws=''):
        """
        By default, start date is 01-Last Month-Current Year end date is 01-Current Month-Current Year,
        should be date object

        :param es_db: ESConnection DB
        :param url: correctly formated url to access the webservice with
        :param harvester_id: string Unique ID of the harvester
        :param date_start: Date obj - start date to retrieve data form the ws provider
        :param date_end: Date obj - end date to retrieve data from the ws provider
        :param name_ws: name of webservice as shown to user
       """
        if not date_start:
            prevdate = date.today() - timedelta(days=2)
            date_start = prevdate.replace(day=1)
        if not date_end:
            date_end = date.today().replace(day=1)

        super(QueryEngineEPMC, self).__init__(es_db,
                                              "EPMC",
                                              harvester_id,
                                              name_ws,
                                              url.format(start_date=date_start.isoformat(),
                                                         end_date=date_end.isoformat()))
        self.next_cursor_mark = '*'
        self.page_size = 1000

    def _handle_metadata_from_request(self, data):
        """
        According to documentation @ https://cwiki.apache.org/confluence/display/solr/Pagination+of+Results if all
        results have been retrieved then the returned nextCursorMark will be unchanged from previous value; however
        as of August 2021 we have found that nextCursorMark may be absent if all results are retrieved.
        Hence self.next_cursor_mark is now set to None in either case.

        :param data: JSON data from EPMC

        :return: None if we have no results, list of JSON results in dictionary format otherwise.
        """
        self.logger.info("EPMC query: %s" % self.query_url)
        next_cursor_mark = data.get("nextCursorMark")
        # If next-cursor-mark is set and is different from previous value then save it as next value
        if next_cursor_mark and next_cursor_mark != self.next_cursor_mark:
            self.next_cursor_mark = next_cursor_mark
        else:
            self.next_cursor_mark = None
        return dictionary_get(data, "resultList", "result")

    def execute(self):
        """
        Import all data from EPMC using setted variables

        Params:
            DB - Object of H_DBConnection

        Returns:
            Boolean
        """
        full_data = http_get_json(self.query_url)
        hit_count = full_data.get("hitCount", 0)
        hits_retrieved = 0
        result_list = self._handle_metadata_from_request(full_data)
        while result_list:
            hits_retrieved += len(result_list)
            self.insert_into_harvester_index(result_list)
            # Not yet retrieved all records matching the query, and previous request set a next-cursor-mark
            if hits_retrieved < hit_count and self.next_cursor_mark:
                # Get next "page" of results
                result_list = self._handle_metadata_from_request(http_get_json(self.query_url))
            else:
                break
        return hits_retrieved

    @staticmethod
    def str_and_zfill(a_number):
        return str(a_number).zfill(2)

    @classmethod
    def _get_publication_date(cls, json_doc, e_pub_date_ymd_str, p_pub_date_ymd_str):
        """
        Gets the best publication date possible from the JSON structure.

        Note that EPMC documentation (https://europepmc.org/docs/EBI_Europe_PMC_Web_Service_Reference.pdf (pg 46)
        E_PDATE entry indicates that although date may be in a variety of forms, it always begins with YYYY.  Our
        experience leads to an implementation that assumes the date is received in hyphen separated form: YYYY-MM-DD
        (or shorter derivative of this, e.g. YYYY-MM).

        :param json_doc: JSON json_doc (EPMC)
        :param e_pub_date_ymd_str: String - Electronic publication date in format "YYYY-MM-DD"
        :param p_pub_date_ymd_str: String - Print publication date in format "YYYY-MM-DD"
        :return: list of arguments to be applied to UnroutedNotification.set_publication_date_format
            Will be like any of these:
                []
                [pub_date, pub_format]
                [pub_date, pub_format, year]
                [pub_date, pub_format, year, month]
                [pub_date, pub_format, year, month, day]
        """
        # Add publication date
        pub_date = json_doc.get("firstPublicationDate", e_pub_date_ymd_str)
        pub_format = ''
        if pub_date:
            if pub_date == e_pub_date_ymd_str:
                pub_format = 'electronic'
            elif pub_date == p_pub_date_ymd_str:
                pub_format = 'print'
        elif p_pub_date_ymd_str is not None:
            pub_date = p_pub_date_ymd_str
            pub_format = 'print'

        if pub_date:
            try:
                # Convert string YYYY-MM-DD to date object (raises exception if fails,
                # but will accept YYYY-MM-D, YYYY-M-D etc.)
                date_obj = ymd_to_datetime(pub_date)

                # At this point we know we have a valid date
                formats = {
                    1: "%Y",
                    2: "%Y-%m",
                    3: "%Y-%m-%d"
                }
                num_parts = len(pub_date.split("-"))
                # Create string date using appropriate format
                date_str = date_obj.strftime(formats[num_parts])
                args = [date_str, pub_format] + date_str.split("-")
            except:
                args = [pub_date, pub_format]
        else:
            args = []
        return args

    def convert_to_notification(self, json_doc, service_id=None):
        """
        Convert EPMC API result JSON json_doc into Router Incoming notification structure.

        :param json_doc: the json json_doc to be converted.
        :param service_id: webservice identifier.

        :return dict of IncomingNotification Router
        """

        _type = {'pdf': 'fulltext',
                 'html': 'fulltext',
                 'abs': 'fulltext',
                 'doi': 'fulltext'}

        _format = {'pdf': 'application/pdf',
                   'html': 'text/html',
                   'abs': 'text/html',
                   'doi': 'text/html'}

        try:
            in_note = IncomingNotification()
            # in_note.category = ???    # Allow this to be set after Routing
            in_note.has_pdf = False
            # Add links to the Router incoming notification model
            for link in dictionary_get(json_doc, "fullTextUrlList", "fullTextUrl", default=[]):
                # If NOT a subscription link
                if link.get("availabilityCode", "S") != "S":
                    _link_doc_style = link['documentStyle']
                    if _link_doc_style == "pdf":
                        in_note.has_pdf = True
                    in_note.add_url_link(link['url'].strip(),
                                         _type.get(_link_doc_style, 'fulltext'),
                                         _format.get(_link_doc_style, 'text/html')
                                         )

            # Add provider information to the Router incoming notification model
            in_note.provider_agent = self.harv_name
            in_note.provider_harv_id = service_id
            in_note.provider_route = "harv"
            in_note.provider_rank = self.rank

            # Add journal information
            journal_info = json_doc.get("journalInfo")
            if journal_info:
                if "volume" in journal_info:
                    in_note.journal_volume = journal_info["volume"]

                if "issue" in journal_info:
                    in_note.journal_issue = journal_info["issue"]

                journal = journal_info.get("journal")
                if journal:
                    if "title" in journal:
                        in_note.journal_title = journal["title"]
                    abbrev_title = journal.get("isoabbreviation", journal.get("medlineAbbreviation"))
                    if abbrev_title:
                        in_note.journal_abbrev_title = abbrev_title

                    # Add all journal identifiers that match the list of options: issn, essn, nlmid
                    for ident in {"issn", "essn", "nlmid"} & journal.keys():
                        in_note.add_journal_identifier(ident, journal[ident])

            # Add publication dates to History
            epub_date = json_doc.get("electronicPublicationDate")
            if epub_date:
                in_note.add_history_date("epub", epub_date)

            ppub_date = dictionary_get(json_doc, "journalInfo", "printPublicationDate")
            if ppub_date:
                in_note.add_history_date("ppub", ppub_date)

            # === ARTICLE info ===
            pub_date_info = self._get_publication_date(json_doc, epub_date, ppub_date)
            if pub_date_info:
                # pub_date_info applies arguments to the function in this order:
                # notification.set_publication_date_format(pub_date, pub_format, year, month, day)
                in_note.set_publication_date_format(*pub_date_info)

            # Add article title
            in_note.article_title = json_doc.get("title")
            # Add type(s) of publication as a string  (json_doc['pubTypeList']['pubType'] is a list)
            try:
                in_note.article_type = "; ".join(json_doc['pubTypeList'].get("pubType", []))
            except KeyError:
                pass

            # The page range: start page-end page, e.g. 145-178 or 559 or E141 or e01234
            try:
                page_info = json_doc['pageInfo']
                in_note.article_page_range = page_info
                # If page range separator present
                if '-' in page_info:
                    pages = page_info.split('-')
                    in_note.article_start_page = pages[0]
                    in_note.article_end_page = pages[1]
                    if in_note.article_start_page.isdigit() and in_note.article_end_page.isdigit():
                        in_note.article_num_pages = int(pages[1]) - int(pages[0]) + 1
                elif page_info.isdigit():   # Single number present (assume article on 1 page only
                    in_note.article_start_page = page_info
                    in_note.article_end_page = page_info
                    in_note.article_num_pages = 1
            except KeyError:
                pass

            # Add language
            in_note.article_language = json_doc.get("language")

            abstract = json_doc.get("abstractText")
            if abstract:
                in_note.article_abstract = abstract

            # Add all article identifiers from the set "doi", "pmid", "pmcid" that exist in the json_doc
            for ident in ("doi", "pmid", "pmcid"):
                try:
                    in_note.add_article_identifier(ident, json_doc[ident])
                except KeyError:
                    pass

            # Add subject keywords
            for keyword in dictionary_get(json_doc, "keywordList", "keyword", default=[]):
                in_note.add_article_subject(keyword)
            for keyword in dictionary_get(json_doc, "meshHeadingList", "meshHeading", default=[]):
                descriptor = keyword.get("descriptorName")
                if descriptor:
                    in_note.add_article_subject(descriptor)

            all_auth_ids = []  # Array holds Ids of all authors found
            # Add authors list
            for author in dictionary_get(json_doc, "authorList", "author", default=[]):
                name_dict = IncomingNotification.make_name_dict(author.get("firstName"),
                                                                author.get("lastName"),
                                                                author.get("fullName"))
                if not name_dict:
                    continue
                auth = {"name": name_dict}
                auth_ids = []
                author_id = author.get("authorId")
                if author_id:
                    id_value = author_id.get("value")
                    auth_id_dict = self._process_author_id(author_id.get("type"), id_value)
                    # If we have a valid auth id dict
                    if auth_id_dict:
                        auth_ids = [auth_id_dict]
                        all_auth_ids.append(id_value)

                # affiliations is list of dicts, like [{"affiliation": "...", "affiliationOrgId": "..."}, {"affiliation": "..."} ...]
                affs = []
                for aff in dictionary_get(author, "authorAffiliationDetailsList", "authorAffiliation", default=[]):
                    aff_txt = aff.get("affiliation")
                    aff_id = aff.get("affiliationOrgId")
                    raw = []
                    if aff_txt:
                        raw.append(aff_txt)
                    if aff_id:
                        raw.append(aff_id)
                    if raw:
                        affs.append({"raw": "; ".join(raw)})
                if affs:
                    auth['affiliations'] = affs

                # auth_ids array is NOT empty
                if auth_ids:
                    auth['identifier'] = auth_ids

                if auth:
                    in_note.add_author(auth)

            # Add author identifiers (if not previously set)
            for author_id in dictionary_get(json_doc, "authorIdList", "authorId", default=[]):
                # Author Id from the authorIdList does NOT already exist
                id_value = author_id.get("value")
                if id_value not in all_auth_ids:
                    author_id_dict = self._process_author_id(author_id.get("type"), id_value)
                    if author_id_dict:
                        in_note.add_author({"identifier": [author_id_dict]})
                        # Add this Id to list, just in case duplicates exist in this authorIdList
                        all_auth_ids.append(id_value)

            # Add funding information
            funding_map = {}
            # for each grant, add the grant number to the funding_map with key of the grant's funder name
            for grant in dictionary_get(json_doc, "grantsList", "grant", default=[]):
                funder = grant.get("agency")
                if funder:
                    if funder not in funding_map:
                        funding_map[funder] = []
                    grant_number = grant.get("grantId")
                    if grant_number:
                        funding_map[funder].append(grant_number)
            # for each funder, create a funder object of format {"name": name, "grant_numbers": [list of grant numbers]}
            funding_objs = [{"name": funder, "grant_numbers": grants} for funder, grants in funding_map.items()]

            if funding_objs:
                in_note.funding = funding_objs

            # Add embargo end date to the Router incoming notification model
            try:
                in_note.set_embargo(end=json_doc['embargoDate'])
            except KeyError:
                pass

            # Add license
            try:
                doc_license = json_doc['license']
                in_note.set_license("", doc_license, doc_license)
            except KeyError:
                pass

        except Exception as err:
            raise InputError(f"Creating EPMC IncomingNotification - {repr(err)}") from err

        return in_note.data

    @staticmethod
    def create_query_url(url, page_size, cursor_mark):
        """
        Constructs query url
        :param url: Base URL (without page params)
        :param page_size: Number of items per page
        :param cursor_mark: Cursor mark
        :return: formatted URL with query params added
        """
        return f"{url}&pageSize={page_size}&cursorMark={quote(cursor_mark)}"

    @staticmethod
    def is_valid(url):
        """
        Check is the url is valid
        """
        # Append query params - we just want to get one result to confirm the URL is OK
        url = QueryEngineEPMC.create_query_url(url, 1, '*')
        try:
            data = http_get_json(url)
        except Exception:
            return False

        keys = data.keys()
        # Valid if errCode does not appear in data dict, but resultLists does
        return 'errCode' not in keys and 'resultList' in keys

#
# === DEFINE VARIABLES ===
#
    @property
    def query_url(self):
        return self.create_query_url(self.url, self.page_size, self.next_cursor_mark)
