"""
Engine for Crossref's JSON API

References
    API Doc: https://github.com/CrossRef/rest-api-doc/  (specifically look at api_format.md and rest_api.md)
    Blog - Info on planned changes to APIs: https://www.crossref.org/categories/apis

Sharepoint IncomingNotification mappings:
https://jisc365.sharepoint.com/sites/dcrd/OAdev/_layouts/15/WopiFrame.aspx?sourcedoc=%7B48A20651-2B6B-4A8F-8EFF-58CD12C955B7%7D&file=PubRouterMappingCrossref.xlsx&action=default&DefaultItemOpen=1
"""
from datetime import datetime, date
import re
from urllib.parse import quote
from time import sleep
from dateutil.relativedelta import relativedelta
from octopus.lib.data import dictionary_get, strip_bad_text
from octopus.lib.http_plus import http_get_json, http_get
from octopus.lib.exceptions import InputError, RESTError
from router.shared.models.note import IncomingNotification
from router.harvester.engine.QueryEngine import QueryEngine, current_app

# pre compile this regex expression for repetitive use in removing xml tags from a string
rows_in_url_regex = re.compile(r"&rows=\d+")    # Match rows parameter in Crossref URL


class _CrossrefCursor:
    """
    Provides an iterator for pagination with Crossref's API

    example usage:
        # Construct
        crossref_cursor = _CrossrefCursor(CROSSREF_API_LINK)
        # Get next item
        next_item = crossref_cursor.next()
        # Iterate through data
        for list_of_items in crossref_cursor:
            # Do something with items
        # reset cursor if wanted
        crossref_cursor.reset_cursor()
        # Change url for new data
        crossref_cursor.set_url_and_reset_cursor(CROSSREF_OTHER_API_LINK)
        # Make a request with the current cursor value if you just want to see the full request
        request = crossref_cursor.request()
        # Get the current URL with cursor
        url = crossref_cursor.url
    """
    SLEEP = 5           # Initial num of Seconds to sleep if failure retrieving a cursor (increases exponentially)
    TRIES = 4           # Number of times to try a cursor before giving up
    INIT_CURSOR = "*"   # Initial cursor value

    def __init__(self, url, headers=None):
        """
        Initialises a _CrossrefCursor.

        Will set variables ready for iteration/use of next

        :param url: URl to request from
        :param headers: Custom http headers to add to the request
        """
        # Set None as a wait time, as if it's None we won't wait.
        self.wait_timestamp = None
        self.headers = headers
        self.set_url_and_reset_cursor(url)
        self.logger = current_app.logger

    @property
    def url_with_cursor(self):
        """
        Format the URL with the URI encoded cursor so we can make requests.

        Also good for seeing exactly what URL was used when requesting.

        :return: URL formatted with a URI encoded cursor.
        """
        return self._url.format(quote(self._cursor))

    def _wait_if_necessary(self):
        """
        Waiting function - will cause waiting if we attempt to request too early from crossref.

        Will compare a given wait_timestamp with now - if the difference is positive, it will wait
            for the allotted time.
        """
        if self.wait_timestamp:
            now = datetime.now()
            # total_seconds() returns a fractional number of seconds
            wait_time = (self.wait_timestamp - now).total_seconds()
            if wait_time > 0:
                self.logger.info(f"Crossref needs us to sleep: Sleeping for {wait_time:.2f} seconds")
                sleep(wait_time)
            self.wait_timestamp = None

    def reset_cursor(self):
        """
        Function to simply reset the cursor if we want to access the data again.
        """
        self._cursor = _CrossrefCursor.INIT_CURSOR
        self.expected_total = None  # Expected number of records to be returned by by query through successive API calls
        self.running_total = 0           # Running Total of records returned by query (usually via successive calls to API)

    def set_url_and_reset_cursor(self, val):
        """
        When setting the URL, we should reset the cursor,total and items values to show we have changed the URL.

        wait_time will not be repopulated however as that would still be in effect.

        :param val: URL value to set
        """
        self._url = val + "&cursor={}"
        self.reset_cursor()

    def get_crossref_data_dict(self):
        """
        Make a request to Crossref.

        Will sleep if we found that there was X-Rate-Limit-Interval and X-Rate-Limit-Limit headers set
            on the previous request.

        :return: Request object of current constructed URL
        """
        self._wait_if_necessary()

        url_with_cursor = self.url_with_cursor
        self.logger.info(f"Crossref - GET {url_with_cursor}")

        tries = 0
        while True:
            try:
                response = http_get(url_with_cursor, self.headers)
                break   # No error, so exit while loop
            except RESTError as e:
                # If failure occurs for the first request (cursor still has initial value)
                if self._cursor == _CrossrefCursor.INIT_CURSOR:
                    raise e     # Exit with exception

                tries += 1
                # Exceeded allowed attempts
                if tries >= _CrossrefCursor.TRIES:
                    self.logger.warning(f"Crossref - GET failed after {tries} attempts (reached limit) - {repr(e)}")
                    raise e     # Exit with exception

                sleep_secs = _CrossrefCursor.SLEEP * tries**2    # sleep time increases exponentially with each attempt
                self.logger.warning(f"Crossref - GET failed, sleeping for {sleep_secs} secs before retrying - {repr(e)}")
                sleep(sleep_secs)



        # X-Rate-Limit-Interval defines a time period in seconds in which a number of retries
        #   defined by X-Rate-Limit-Limit can be attempted.
        interval = response.headers.get("X-Rate-Limit-Interval")
        limit = response.headers.get("X-Rate-Limit-Limit")

        if interval and limit:
            # Remove trailing 's'
            interval = interval.rstrip('s')

            # Set wait_time so on next request we will sleep if we need to.
            # This is the minimum amount of time needed to sleep to make sure that we never get throttled.
            # If the interval is 1 second, and the limit is 10 - we sleep for 0.1 seconds.
            # This makes sure we do not do more than 10 requests in a 1 second period.
            wait_microseconds = int((int(interval) / int(limit)) * 1000000) + 10000   # Add 1/100th second for safety
            self.wait_timestamp = datetime.now() + relativedelta(microseconds=wait_microseconds)

        # Convert returned request JSON into a dict
        return response.json()

    def _get_data_from_crossref(self):
        """
        Takes crossref JSON data and sets properties dependent on the data.

        :return: List of crossref metadata in dictionary form.
        """
        # if last API request didn't set cursor, or
        # if there was a previous request and total recs received so far equals (or exceeds) expected number
        if self._cursor is None or self.expected_total is not None and self.running_total >= self.expected_total:
            raise StopIteration

        data = self.get_crossref_data_dict()
        msg = data.get("message")
        self.expected_total = msg.get("total-results")     # Total recs expected from query (thru successive API calls)
        self._cursor = msg.get("next-cursor")
        items = msg.get("items")
        if not items:
            raise StopIteration

        self.running_total += len(items)                        # Total recs received so far
        return items

    def __next__(self):
        """
        Request next cursor data from Crossref.

        Once data is retrieved, set the following properties:
            self._cursor
            self.running_total
        and then return the list of metadata received from crossref.

        :return: list of metadata from self._get_data_from_crossref
        """

        return self._get_data_from_crossref()     # raises StopIteration if no more data

    def __iter__(self):
        """
        Simple iterator for crossref

        Will iterate through the cursor until we get a response with no items
        """
        return self


class QueryEngineCrossref(QueryEngine):

    def __init__(self, es_db, url, harvester_id, start_date=None, end_date=None, name_ws=''):
        """
        Initialise the query engine with a formatted Crossref API url and our PubRouter user_agent header.

        :param es_db: elasticsearch database connector
        :param url: valid web service provider URL. It will need the following format string variables:
            {pub_year},
            {start_date},
            {end_date}
        :param harvester_id: string Unique ID of the harvester
        :param start_date: Start date to retrieve data from Crossref
        :param end_date: End date to retrieve data from Crossref
        :param name_ws: name of webservice as shown to user
        """
        super(QueryEngineCrossref, self).__init__(
            es_db, "Crossref", harvester_id, name_ws, QueryEngineCrossref.format_url(url, start_date, end_date)
        )

        ## Define headers for Crossref API request ##
        # User-Agent is set so Crossref know who we are (and will be less likely to throttle us!)
        self.headers = {"User-Agent": "PubRouter/1.0; mailto:YYYY@YYYY.ac.uk"}

        # If API key is set, then add Authorization header
        api_key = self.config["CROSSREF_API_KEY"]
        if api_key:
            self.headers["Crossref-Plus-API-Token"] = f"Bearer {api_key}"
        self.logger.info(f"Crossref API headers: {self.headers}")

        self.history_dates = None     # History dates so far recorded

    @staticmethod
    def date_dict_from_ymd_list(ymd_list):
        """
        Constructs an IncomingNotification date object from a list like so:
        ["2015", "07", "08"]

        :param ymd_list: Year, Month, Day -date parts to convert to strings and make sure that
        months/days have at least 2 characters.

        :return: date object for IncomingNotification -
        {
            "year": "",
            "month": "",
            "day": "",
            "date": ""
        }
        """
        dictionary = {}
        string_ymd_list = []
        for ix, key in enumerate(["year", "month", "day"]):
            try:
                val = ymd_list[ix]
            except IndexError:
                break
            if not val:
                break
            str_val = str(val).zfill(2)
            dictionary[key] = str_val
            string_ymd_list.append(str_val)

        # If we have 3 elements [YYYY, MM, DD] then construct YYYY-MM-DD string.
        if len(string_ymd_list) == 3:
            dictionary["date"] = '-'.join(string_ymd_list)
        return dictionary

    def get_date_dict_and_add_history_date(self, doc, note, element, history_date_type):
        """
        Helper function to retrieve a date element, if found it creates a date-dictionary
        AND adds the date as a history date to the note.

        :param doc: json_doc dict
        :param note: notification object
        :param element: string - name of date element in json doc
        :param history_date_type: string
        :return: date dictionary
        """
        date_dict = None
        date_parts = dictionary_get(doc, element, "date-parts")
        if date_parts:
            date_dict = QueryEngineCrossref.date_dict_from_ymd_list(date_parts[0])
            fulldate = date_dict.get("date")
            if fulldate:
                note.add_history_date(history_date_type, fulldate)
                self.history_dates.append(history_date_type)    # Record type of history date added

        return date_dict


    @staticmethod
    def hyphen_split_range(page_range):
        """
        Utility function for construct_page_info
        Given a string such as "102-110", create a dict like so: {
            "start_page": Lowest string value (102),
            "end_page": Highest string value (110),
            "num_pages": Range of these values - as an integer. Will not be set if start_page or end_page are
                non numeric (ex: Roman Numerals) (9)
        }

        :param page_range: String like "102-110" or "102"

        :return: Empty dictionary if the range is not valid, otherwise range of highest and lowest number
            and num_pages.

        """
        range_dict = {}
        page_range = page_range.split("-")
        if len(page_range) == 1:
            range_dict["start_page"] = page_range[0]
            range_dict["end_page"] = page_range[0]
        elif len(page_range) > 1:
            range_dict["start_page"] = page_range[0]
            range_dict["end_page"] = page_range[-1]
        if range_dict:
            try:
                range_dict["num_pages"] = int(range_dict.get("end_page", 0)) - int(range_dict.get("start_page", 0)) + 1
            except ValueError:
                pass
        return range_dict

    @staticmethod
    def comma_split_range(page_range):
        """
        Utility function for page_info
        Takes a comma split range ( ex: "210,217", "210-214,220-222")
        and constructs a page_info dictionary for IncomingNotification.
        For example:
        "196-204, 206-220" -> {
            "start_page": "196",
            "end_page": "220",
            "num_pages": 24
        } (does ignore missing pages - can be incorrect if some of the string is not numeric)

        :param page_range: Page range string (ex: "196-204, 206-220")

        Assumes that the lowest number will be first, and highest will be at the end.

        :return: Empty dictionary if the range is not valid, range of split and number of pages otherwise.

        """
        dictionary = {}
        comma_split_range = page_range.split(",")
        for split_range in comma_split_range:
            range_dict = QueryEngineCrossref.hyphen_split_range(split_range)
            if not dictionary:
                dictionary = range_dict
            else:
                if range_dict:
                    dictionary["end_page"] = range_dict.get("end_page")
                    dictionary["num_pages"] = dictionary.get("num_pages", 0) + range_dict.get("num_pages", 0)
        return dictionary

    @staticmethod
    def construct_page_info(page_range):
        """
        Given a page_range string from Crossref, create a page_info dictionary for IncomingNotification.
        page_range could be something like this:
            102
            102-110
            102,110-112
            XII

        page_range can have a lot of odd formats, so we'll only work with ranges
            that are easy to deal with.
        The "page" description in the API documentation is very lax - I have only seen the following formats:
        [0-9]+ (123)
        [0-9]+-[0-9]+ (123-124)


        :param page_range: Page range given by Crossref's API

        :return: Most amount of information we can safely extract from this page range. - {
            "page_range": "",
            "start_page": "",
            "end_page": "",
            "num_pages": 0
        }

        """
        dictionary = {"page_range": page_range}
        dictionary.update(QueryEngineCrossref.comma_split_range(page_range))
        return dictionary

    def construct_contributors(self, contributor_list, contrib_type=None):
        """
        Constructs author and contributor dictionaries, as they are the same in crossref's api.
        Crossref Doc: https://github.com/CrossRef/rest-api-doc/blob/master/api_format.md#contributor

        :param contributor_list:  List of contributor object given by Crossref's API
        (https://github.com/CrossRef/rest-api-doc/blob/master/api_format.md#contributor)
        :param contrib_type: String Contributor type

        :return: Contributor dict formatted for IncomingNotification - {
            "name": {
                "fullname": "",
                "surname": "",
                "firstname": "",
            },
            "identifier": [
                {"type": "orcid", "id": ""}
            ],
            "affiliations": [{"raw": "abc"}, ...],
            "type": ""
        }

        """
        constructed_list = []
        for contributor_dict in contributor_list:
            name_dict = IncomingNotification.make_name_dict(contributor_dict.get("given"),
                                                            contributor_dict.get("family"))
            if not name_dict:
                continue
            dictionary = {"name": name_dict}

            orcid = contributor_dict.get("ORCID")
            if orcid:
                orcid_dict = self._process_author_id("orcid", orcid)
                if orcid_dict:
                    dictionary["identifier"] = [orcid_dict]
            aff_list = []
            for aff in contributor_dict.get("affiliation", []):
                # Capture any of following fields: 'name', 'id', 'department', 'place' - ignore any KeyError exception
                # raised for any missing fields.
                aff_dict = {}
                # Temporary list to hold department, name, place strings (possibly None or empty)
                _dept_name_place_list = []

                _dept = ", ".join(aff.get("department", []))
                if _dept:
                    aff_dict["dept"] = _dept
                    _dept_name_place_list.append(_dept)

                _dept_name_place_list.append(aff.get("name"))

                try:
                    aff_dict["identifier"] = [{"type": id_dict["id-type"].upper(),
                                               "id": id_dict["id"]} for id_dict in aff["id"]]
                except KeyError:
                    pass

                _dept_name_place_list.append(", ".join(aff.get("place", [])))

                # join any non-empty elements of _dept_name_place_list
                _raw = ", ".join([_str for _str in _dept_name_place_list if _str])
                if _raw:
                    aff_dict["raw"] = _raw

                if aff_dict:
                    aff_list.append(aff_dict)

            if aff_list:
                dictionary["affiliations"] = aff_list

            if contrib_type:
                dictionary["type"] = contrib_type
            constructed_list.append(dictionary)
        return constructed_list

    @staticmethod
    def create_funder(funder_dict):
        """
        Construct funder dictionary using Crossref given funder
        Example funder_dict:
        {
          "name": "Funding body primary name",
          "DOI": "Open Funder Registry DOI uniquely identifying the funding body",
          "award": "Award number(s) given by the funding body,
          "doi-asserted-by": "either crossref or publisher"
        }

        :param funder_dict: Funder object from Crossref's API
        (https://github.com/CrossRef/rest-api-doc/blob/master/api_format.md#funder)

        :return: Funder object - {
            "name": "",
            "identifier": [
                {"type": "FundRef", "id": ""}
            ],
            "grant_numbers": ["", ...]
        }

        """
        dictionary = {"name": funder_dict.get("name")}
        doi = funder_dict.get("DOI")
        if doi:
            dictionary["identifier"] = [{"type": "FundRef", "id": doi}]
        grant_numbers = funder_dict.get("award", [])
        if grant_numbers:
            dictionary["grant_numbers"] = grant_numbers
        return dictionary

    @staticmethod
    def construct_license(license_dict):
        """
        Construct license information for IncomingNotification from license object from Crossref's API.

        :param license_dict: License object from Crossref's API
        (https://github.com/CrossRef/rest-api-doc/blob/master/api_format.md#license)

        :return: license information for IncomingNotification - {
            "url": "",
            "start": ""
        }

        """
        dictionary = {"url": license_dict.get("URL")}
        date_parts = dictionary_get(license_dict, "start", "date-parts")
        if date_parts:
            # Is a list within a list ex: [ [ 2017, 03, 14 ] ]
            date_parts = QueryEngineCrossref.date_dict_from_ymd_list(date_parts[0])
            dictionary["start"] = date_parts.get("date")
        else:
            dictionary["start"] = ""
        return dictionary

    # def construct_embargo(self, best_license, issued_date_dictionary):
    #     """
    #     Derive an embargo from the start date of the earliest open access license available:
    #         Embargo end date is set to the open access license start date
    #         Embargo start date, if set, will be publication date.
    #
    #     :param best_license: best open license we could find in the list of licenses
    #     :param issued_date_dictionary: Constructed from date_dict_from_ymd_list, earliest of electronic and
    #         print publisher date.
    #
    #     :return: embargo object to be added. - {
    #         "end": "",
    #         "duration": "",
    #         "start": ""
    #     }
    #     """
    #     embargo_dict = {}
    #     license_start_date_parts = dictionary_get(best_license, "start", "date-parts", default=[[]])
    #     embargo_end_date = QueryEngineCrossref.date_dict_from_ymd_list(license_start_date_parts[0]).get("date")
    #     if embargo_end_date:
    #         embargo_dict["end"] = embargo_end_date
    #         publication_date = issued_date_dictionary.get("date")
    #         if publication_date:
    #             # If embargo end date is after the publication date,
    #             # then set embargo start date to be the publication date
    #             if embargo_end_date > publication_date:
    #                 embargo_dict["start"] = publication_date
    #     return embargo_dict

    @staticmethod
    def format_url(url, start_date=None, end_date=None, rows=None):
        """
        Format a URL using harvester engine standards by replacing the start_date and end_date format variables
            in the url string.
        Crossref needs an extra pub_year variable added to the format string - this is because
            we would get some metadata from articles from decades ago that won't be very relevant as of now.

        :param url: URL that we will format
        :param start_date: start_date as a datetime object
        :param end_date: end_date as a datetime object
        :param rows: number of rows to get in each request

        :return: Formatted url to use in execute()
        """
        if rows:
            # Remove any existing "&rows=999" type parameter & append a new one
            url = rows_in_url_regex.sub("", url) + f"&rows={rows}"
        elif not rows_in_url_regex.search(url):
            # rows not specified & URL has NOT got a `&rows=...` parameter, so append default of 1000 rows
            url = url + f"&rows=1000"
        start_date = start_date or date.today()
        end_date = end_date or date.today()

        # this pub_year variable is added to the URL to stop crossref from retrieving metadata for publications
        # from decades ago that were updated only recently.
        # using crossref's from-pub-date filter, if we simply set from-pub-date to some year then we will not
        # get any publications from before that year.
        pub_year = (date.today() - relativedelta(years=current_app.config["CROSSREF_PUB_YEARS"])).strftime('%Y')
        return url.format(start_date=start_date.strftime('%Y-%m-%d'),
                          end_date=end_date.strftime('%Y-%m-%d'),
                          pub_year=pub_year)

    @staticmethod
    def is_valid(url):
        """
        Formats URL and tests whether it is valid against crossref's API

        :param url: url to validate

        :return: Boolean - True: Valid URL; False: Invalid URL

        """
        url = QueryEngineCrossref.format_url(url, rows=2)
        try:
            data = http_get_json(url)
        except Exception:
            return False
        return "ok" == data.get("status") and isinstance(dictionary_get(data, "message", "items"), list)

    def execute(self):
        """
        Accesses Crossref's API and places the data in elasticsearch.
        Once this is done, temporary json_docs will be placed in elastic search, ready to be
        converted by the convert_to_notification function.

        Exceptions can be raised in this function by http_get_json. -
        these should be handled by the calling function.

        :return: the total number of results retrieved from this URL

        """
        cursor = _CrossrefCursor(self.url, self.headers)
        for items in cursor:
            if items:
                # Attempt to insert items into elasticsearch
                self.insert_into_harvester_index(items)
        return cursor.running_total

    def convert_to_notification(self, json_doc, service_id=None):
        """
        Map crossref's API json_doc into our own IncomingNotification format.

        :param json_doc: JSON document received from Crossref's API
        :param service_id: webservice identifier.

        :return: dict of processed IncomingNotification

        """
        try:
            self.history_dates = []  # History dates so far recorded

            # Simple map between Crossref's issn types to ours
            issn_type_map = {"print": "pissn", "electronic": "eissn"}

            in_note = IncomingNotification()

            # Crossref specific provider settings
            in_note.provider_route = "harv"
            in_note.provider_agent = self.harv_name
            in_note.provider_harv_id = service_id
            in_note.provider_rank = self.rank

            # Journal data
            journal_titles = json_doc.get("container-title", [])
            if journal_titles:
                in_note.journal_title = journal_titles[0]
            short_titles = json_doc.get("short-container-title", [])
            if short_titles:
                in_note.journal_abbrev_title = short_titles[0]
            in_note.journal_issue = json_doc.get("issue")
            in_note.journal_volume = json_doc.get("volume")
            in_note.add_journal_publisher(json_doc.get("publisher"))
            journal_identifiers = json_doc.get("issn-type", [])
            for issn_dict in journal_identifiers:
                # given a type in the issn_dict ("print" or "electronic")
                # map this to type expected by IncomingNotification ("pissn", "eissn")
                issn_type = issn_type_map.get(issn_dict.get("type"))
                in_note.add_journal_identifier(issn_type, issn_dict.get("value"))

            # Article data
            # If we have no title, simply set to None so we do not set it at a later date.
            # Use strip_bad_text to avoid garbage newline characters/whitespace
            article_title = ','.join([strip_bad_text(title) for title in json_doc.get("title", [])]) or None
            article_subtitles = [strip_bad_text(sub_title) for sub_title in json_doc.get("sub-title", [])]
            in_note.article_title = article_title
            for subtitle in article_subtitles:
                in_note.add_article_subtitle(subtitle)
            # abstract may (or may not) contain xml tags in the string returned from Crossref
            abstract_xml_string = json_doc.get("abstract")
            if abstract_xml_string:
                in_note.article_abstract = abstract_xml_string

            type_ = json_doc.get("type")
            subtype_ = json_doc.get("subtype")      # subtype is usually absent, but if present should be used
            in_note.category = self.config["CROSSREF_CATEGORY_MAP"].get(type_, {}).get(subtype_)
            # For article-type: if 'subtype' is present, then use that otherwise use 'type'. May need to convert to more
            # useful article-type name using MAP dicts
            if subtype_ is None:
                art_type = self.config["CROSSREF_TYPE_MAP"].get(type_, type_)
            else:
                art_type = self.config["CROSSREF_SUBTYPE_MAP"].get(subtype_, subtype_)
            in_note.article_type = art_type

            page = json_doc.get("page")
            if page:
                page_info = QueryEngineCrossref.construct_page_info(page)
                in_note.article_start_page = page_info["start_page"]
                in_note.article_end_page = page_info["end_page"]
                if page_info.get("num_pages"):
                    # Careful in case of roman numerals!
                    in_note.article_num_pages = page_info["num_pages"]
                in_note.article_page_range = page_info["page_range"]
            e_num = json_doc.get("article-number")
            if e_num:
                in_note.article_e_num = e_num
            in_note.add_article_identifier("doi", json_doc.get("DOI"))
            in_note.article_subject = json_doc.get("subject", [])

            # Author data
            in_note.authors = self.construct_contributors(json_doc.get("author", []))
            in_note.contributors = self.construct_contributors(json_doc.get("contributor", []), "editor")

            # Funders
            funders = []
            for funder in json_doc.get("funder", []):
                funders.append(QueryEngineCrossref.create_funder(funder))
            in_note.funding = funders

            pub_date_dictionary = None
            epub_date_dict = self.get_date_dict_and_add_history_date(json_doc, in_note, "published-online", "epub")
            ppub_date_dict = self.get_date_dict_and_add_history_date(json_doc, in_note, "published-print", "ppub")
            issue_date_dict = self.get_date_dict_and_add_history_date(json_doc, in_note, "issued", "issued")

            # Publication date data - publication date is set using online date in precedence to printed date,
            # failing that then issue date is used.
            if epub_date_dict:
                pub_date_dictionary = epub_date_dict
                pub_date_dictionary["publication_format"] = "electronic"
            elif ppub_date_dict:
                pub_date_dictionary = ppub_date_dict
                pub_date_dictionary["publication_format"] = "print"
            elif issue_date_dict:
                pub_date_dictionary = issue_date_dict

            if pub_date_dictionary:
                in_note.publication_date = pub_date_dictionary
                in_note.publication_status = "Published"

            # Add any history dates (which are passed in assertion list)
            for assertion in json_doc.get("assertion", []):
                # If assertion is a history date
                if assertion.get("group", {}).get("name") == "publication_history":
                    date_type = assertion.get("name")
                    # date-type is not empty & If we don't already have this type of date
                    if date_type:
                        date_type = date_type.lower()
                        if date_type not in self.history_dates:
                            date_val = assertion.get("value", "")
                            # If we have a full date of format "yyyy-mm-dd"
                            if len(date_val) == 10:
                                in_note.add_history_date(date_type, date_val)
                                self.history_dates.append(date_type)
                                # If Accepted date
                                if "accept" in date_type:
                                    in_note.accepted_date = date_val


            # License, article version and embargo
            # construct list of tuples (license, article_version) where license is a license in IncomingNotification format
            # and article_version is the article version that license pertains to
            licenses_and_article_versions = [
                (QueryEngineCrossref.construct_license(lic), lic.get("content-version", "").upper()) for lic in json_doc.get("license", [])
            ]
            best_license, best_article_version, calculate_embargo = in_note.calculate_embargo_and_best_license(
                licenses_and_article_versions
            )
            # best_licenses defaults to an empty set, this gets set if we fail to calculate any best_licenses
            best_licenses = []
            # if we were able to calculate best_license_and_article_version
            if best_license:
                in_note.article_version = best_article_version
                if calculate_embargo:
                    # we set embargo's end date to the date on which the open license starts
                    in_note.set_embargo(end=best_license["start"])
                # send ALL licenses with version equal to best_license_and_article_version's version
                best_licenses = [
                    lic for lic, art_vers in licenses_and_article_versions if art_vers == best_article_version
                ]
            in_note.licenses = best_licenses

            ## COMMENT OUT until SB confirms article links should be recorded
            # if best_article_version:
            #     in_note.has_pdf = False
            #     # Type map is a lookup, in which last 3 chars of content-type are used to decide the link type
            #     type_map = {"pdf": "fulltext", "xml": "XML", "tml": "splash"}
            #     # Capture links that correspond to the licence article version
            #     for link in json_doc.get("link", []):
            #         if link.get("content-version") == best_article_version:
            #             content_type = link.get("content-type", "text/html")
            #             # Use last 3 chars of content-type to look up the type of content - default to unspecified
            #             _type = type_map.get(content_type[-3:], "unspecified")
            #             in_note.add_url_link(link.get("URL"), _type, content_type)
            #             if _type == "fulltext":
            #                 in_note.has_pdf = True

            """
            Missing Fields for IncomingNotification
            {
                content.packaging_format,
                metadata.article.language,
                metadata.author.type,
                metadata.author.name.suffix,
                metadata.author.organisation_name,
                metadata.contributor.type,
                metadata.contributor.name.suffix,
                metadata.contributor.organisation_name,
                metadata.accepted_date,
                metadata.publication_date.season,
                metadata.embargo.start,
                metadata.license_ref.title,
                metadata.license_ref.type,
            }
            """
        except Exception as err:
            raise InputError(f"Creating Crossref IncomingNotification - {repr(err)}") from err
        return in_note.data
