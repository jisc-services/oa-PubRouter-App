from router.shared.models.note import OutgoingNotification, NotificationList
from octopus.lib import http, dates
from flask import current_app
import json

class JPERException(Exception):
    pass


class JPERConnectionException(JPERException):
    pass


class JPERAuthException(JPERException):
    pass


class ValidationException(JPERException):
    pass


class JPER:
    FilesAndJATS = "https://pubrouter.jisc.ac.uk/FilesAndJATS"

    def __init__(self, api_key=None, base_url=None):
        self.api_key = api_key if api_key is not None else current_app.config.get("JPER_API_KEY")
        self.base_url = base_url if base_url is not None else current_app.config.get("JPER_BASE_URL")

        if self.base_url.endswith("/"):
            self.base_url = self.base_url[:-1]

    def make_url(self, endpoint=None, id=None, auth=True, params=None, url=None):
        if url is None:
            url = self.base_url

        if url.endswith("/"):
            url = url[:-1]

        if endpoint is not None:
            url += f"/{endpoint}"

        if id is not None:
            url += f"/{http.quote(str(id))}"

        if auth:
            if self.api_key:
                if params is None:
                    params = {}
                params["api_key"] = self.api_key

        if params:
            args = [f"{k}={http.quote(str(v))}" for k, v in params.items()]
            url += ("?" if "?" not in url else "&") + "&".join(args)

        return url

    def validate(self, note_dict, file_handle=None):
        """
        Validate notification dict.
        """
        # turn the note_dict into a json string
        data = json.dumps(note_dict)

        # get the url that we are going to send to
        url = self.make_url("validate")

        if file_handle is None:
            # if there is no file handle supplied, send the metadata-only note_dict
            resp = http.post(url, data=data, headers={"Content-Type" : "application/json"})
        else:
            # otherwise send both parts as a multipart message
            files = [
                ("metadata", ("metadata.json", data, "application/json")),
                ("content", ("content.zip", file_handle, "application/zip"))
            ]
            resp = http.post(url, files=files)

        if resp is None:
            raise JPERConnectionException("Unable to communicate with the JPER API")

        if resp.status_code == 401:
            raise JPERAuthException(f"JPER authentication failed with API key {self.api_key}")

        if resp.status_code == 400:
            raise ValidationException(resp.json().get("error"))

        return True

    def create_unrouted_note(self, note_dict, file_handle=None):
        """
        Create a notification record in database.

        :param note_dict: notification dict
        :param file_handle: file handle to notification article zip file (content)

        :return: tuple - notification ID, URL to notification
        """
        # turn the notification into a json string
        data = json.dumps(note_dict)

        # get the url that we are going to send to
        url = self.make_url("notification")

        if file_handle is None:
            # if there is no file handle supplied, send the metadata-only notification
            resp = http.post(url, data=data, headers={"Content-Type" : "application/json"})
        else:
            # otherwise send both parts as a multipart message
            files = [
                ("metadata", ("metadata.json", data, "application/json")),
                ("content", ("content.zip", file_handle, "application/zip"))
            ]
            resp = http.post(url, files=files)

        if resp is None:
            raise JPERConnectionException("Unable to communicate with the JPER API")

        if resp.status_code == 401:
            raise JPERAuthException(f"JPER authentication failed with API key {self.api_key}")

        if resp.status_code == 400:
            raise ValidationException(resp.json().get("error"))

        # extract the useful information from the acceptance response
        acc = resp.json()
        id = acc.get("id")
        loc = acc.get("location")

        return id, loc

    def get_outgoing_note(self, notification_id=None):
        """
        Retrieve a notification.

        :param notification_id:

        :return: notification as an OutgoingNotification object
        """
        # get the url that we are going to send to
        if notification_id is not None:
            url = self.make_url("notification", id=notification_id)
        else:
            raise JPERException("You must supply the notification_id")

        # get the response object
        resp = http.get(url)

        if resp is None:
            raise JPERConnectionException("Unable to communicate with the JPER API")

        if resp.status_code == 404:
            return None

        if resp.status_code != 200:
            raise JPERException(f"Unexpected status code [{resp.status_code}] getting notification from {url}.")

        return OutgoingNotification(resp.json())

    def get_content(self, url, auth=True, chunk_size=8096):
        """
        Retrieve file content from a URL, and return an iterator for reading the file plus the  headers.

        :param url: string : endpoint from which content is to be retrieved
        :param auth: boolean : Indicates if account api_key is to be added to URL or not
        :param chunk_size: size (bytes) of file chunks that are returned by each call of the iterator

        :return: tuple - Content stream iterator, headers returned by the GET
        """
    
        # just sort out the api_key
        url = self.make_url(url=url, auth=auth)

        # get the response object
        # NOTE that get_stream calls requests.get(...) with stream=True in all circumstances.  
        # The read_stream=False parameter setting simply stops http.get_stream from reading through the stream & returning content
        # so it returns '' content and zero bytes_read
        resp, ignore_content, bytes_read = http.get_stream(url, read_stream=False)

        # check for errors or problems with the response
        if resp is None:
            raise JPERConnectionException("Unable to communicate with the JPER API")

        if resp.status_code == 401:
            raise JPERAuthException(f"JPER authentication failed with API key {self.api_key}")

        if resp.status_code != 200:
            raise JPERException(f"Unexpected status code [{resp.status_code}] getting content from {url}.")

        # return the response object, in case the caller wants access to headers, etc.
        return resp.iter_content(chunk_size=chunk_size), resp.headers

    def list_routed_outgoing_notes(self, since, page=None, page_size=None, repo_uuid=None):
        '''
        List routed notifications.

        :param since: Date-string or Date-object : date from when to list notifications
        :param page: Page nunber
        :param page_size: Number of results per page
        :param repo_uuid: Repository account UUID

        :return: NotificationList object
        '''
        # check that the since date is valid, and get it into the right format
        if not hasattr(since, "strftime"):
            since = dates.parse(since)
        since = since.strftime("%Y-%m-%dT%H:%M:%SZ")

        # make the url params into an object
        params = {"since": since}
        if page is not None:
            try:
                params["page"] = str(page)
            except:
                raise JPERException("Unable to convert page argument to string")
        if page_size is not None:
            try:
                params["pageSize"] = str(page_size)
            except:
                raise JPERException("Unable to convert page_size argument to string")

        # get the url, which may contain the repository id if it is not None
        url = self.make_url("routed", id=repo_uuid, params=params)

        # get the response object
        resp = http.get(url)

        # check for errors or problems with the response
        if resp is None:
            raise JPERConnectionException("Unable to communicate with the JPER API")

        if resp.status_code == 401:
            raise JPERAuthException(f"JPER authentication failed with API key {self.api_key}")

        if resp.status_code == 400:
            raise JPERException(resp.json().get("error"))

        if resp.status_code != 200:
            raise JPERException(f"Unexpected status code [{resp.status_code}] getting routed notifications from {url}.")

        # create the notification list object
        return NotificationList(resp.json())

    def iterate_routed_outgoing_notes(self, since, repo_uuid=None, page_size=100):
        """
        Iterate over outgoing notifications

        :param since: Date-string or Date-object : date from when to list notifications
        :param repo_uuid: Repository account UUID
        :param page_size: Number of results per page

        :return: Iterable list of outgoing notifications
        """
        page = 1

        while True:
            nl = self.list_routed_outgoing_notes(since, page=page, page_size=page_size, repo_uuid=repo_uuid)
            outgoing_notes = nl.outgoing_notes
            if len(outgoing_notes) == 0:
                break
            for n in outgoing_notes:
                yield n
            if page * page_size >= nl.total:
                break
            page += 1
