"""
This is the main Python API for interacting with the JPER system.

If you are building a web API, or consuming information from the system as an external data consumer (i.e. you're not
writing a core module that sits underneath this interface) then you should use this class to validate, create and
consume notifications.

Go around it at your own risk!
"""
import uuid
from os.path import basename
from flask import current_app
from flask_login import current_user
from logging import ERROR, WARNING, INFO, DEBUG
from octopus.lib.files import guess_mimetype
from octopus.lib import dates, dataobj, http
# from octopus.modules.mysql.dao import DAOException
from octopus.modules.store import store
from router.shared.models.note import EnhancementException, IncomingNotification, UnroutedNotification, \
    RoutedNotification, pull_routed_or_unrouted_notification
from router.jper.packages import PackageFactory, PackageException
from router.jper.routing import apply_licence_defaults, get_routing_default_description, MAJOR


class ValidationException(Exception):
    """
    Exception which gets raised if an attempt to validate in incoming notifications fails.
    """
    pass


class ValidationMetaException(ValidationException):
    """
    Exception which gets raised if the only problems are with metadata unrelated to any supplied package
    """
    pass


class ParameterException(Exception):
    """
    Exception which gets raised if there is a problem with the parameters passed to a method.

    This would be, for example, if you don't clean up user input via the web API properly before passing it
    here
    """
    pass


class ForbiddenException(Exception):
    """
    Exception which gets raised where an authenticated user is denied access to the resource.

    For example, during content retrieve, if there is no content, nothing is returned, but if there is content
    but the user is unauthorised, this exception can be raised.
    """
    pass


class ContentException(Exception):
    """
    Exception raised where expected content cannot be found.
    """
    pass


class JPER:
    """
    Main Python API for interacting with the JPER system

    Each of the methods here provide you with access to one of the key API routes
    """
    @staticmethod
    def validation_msg(err_count, issue_count, tail):
        return f"Validation: {err_count} error{'' if err_count == 1 else 's'} & {issue_count} issue{'' if issue_count == 1 else 's'} {tail}"

    @classmethod
    def validate(cls, account, notification, file_handle=None, file_path=None, pub_test=None):
        """
        Validate the incoming notification (and optional binary content) on behalf of the Organisation Account holder.

        This method will carry out detailed validation of the notification and binary content in order to provide
        feedback to the user on whether their notifications are suitable to send on to the create() method.

        If the validation fails, an appropriate exception will be raised.  If the validation succeeds, the
        method will finish silently (no return)

        :param account: Organisation Account object for which this action will be carried out
        :param notification: raw notification dict object (e.g. as pulled from a POST to the web API)
        :param file_handle: File handle to binary content associated with the notification
        :param file_path: File path to LOCAL disk-file storing binary content associated with the notification
        :param pub_test: Publisher testing object
        :return: does not return anything.  If there is a problem, though, exceptions are raised
        """
        hex_id = uuid.uuid4().hex
        pub_test.log(INFO, f"Validate request Id: {hex_id} from Acc: '{account.org_name}' ({account.id})", save=False)
        debugging = current_app.config.get("LOG_DEBUG")

        # does the metadata parse as valid
        try:
            if debugging:
                pub_test.log(DEBUG, f"-- Received notification:\n{notification}")
            incoming = IncomingNotification(notification)
        except dataobj.DataStructureException as e:
            err_msg = "Validation error(s) occurred"
            try:
                # Perform detailed "publisher testing" validation of submission on raw notification
                err_count, issue_count, info_count = pub_test.validate_metadata(notification)
                if err_count or issue_count:
                    err_msg = cls.validation_msg(err_count, issue_count, "found in raw notification metadata")
            except Exception as ee:
                pass
            pub_test.log(ERROR, f"Could not create Router record from supplied notification metadata: {str(e)}")
            raise ValidationException(err_msg) from e

        # if so, convert it to an unrouted notification
        unrouted_note = incoming.make_unrouted()
        # provider_route will already have been set unless this is notification received via API
        if not unrouted_note.provider_route:
            unrouted_note.provider_route = "api"

        # get the format of the package
        pkg_format = unrouted_note.packaging_format

        # if zip file is available - either as a stream (via file_handle) or a disk-file (via file_path)
        # then we need to validate it
        filename = None
        pkg_problem = False
        if file_handle or file_path:
            try:
                # generate id for putting it into the store
                local_id = None
                # get the Temporary Store implementation, and serialise the file handle to the local id
                temp_store = store.TempStore()
                if file_handle:
                    try:
                        _path = file_handle.name
                    except AttributeError:
                        _path = None
                    # use str(_path) as have had an integer returned by file_handle.name (in submissions from IOP)
                    filename = basename(str(_path)) if _path else "unspecified"
                    try:
                        local_id = uuid.uuid4().hex
                        file_path = temp_store.store(local_id, "validate.zip", source_stream=file_handle)
                    except Exception as e:
                        # This exception is NOT due to validation failure (but to problems storing file)
                        raise e
                else:
                    filename = basename(file_path)
                pub_test.log(INFO, f"Validating package with filename: '{filename}' (original: {pub_test.filename})")
                if pkg_format is None:
                    raise ValidationException("If zipped content is provided, metadata must specify packaging format")

                # Now extract data from temporarily stored package
                # If this is unsuccessful, we ensure that the local copy is deleted from the store, then we can raise
                # the exception
                try:
                    pkg_exception_snippet = "reading"
                    ## Extract metadata from supplied package ##
                    # Instantiate the package manager - if successful, `pkg_mgr.jats` will have been set to JATS object
                    pkg_mgr = PackageFactory.get_pkg_mgr_and_extract_metadata_from_file(
                        pkg_format, zip_path=file_path, pub_test=pub_test)

                    # Check if a PDF is present
                    if not pkg_mgr.package_has_pdf():
                        # We log error here, rather than raise exception because we want to continue with package
                        # validation. Also, this error isn't severe, so `pkg_problem` isn't set -> so this error won't
                        # prevent ValidationMetaException being raised later
                        pub_test.log(ERROR, f"No article PDF file was found in zip file: {pub_test.filename or filename}")

                    # If successful, we should extract the metadata from the package, using the validated id and the
                    # Temporary Store implementation again
                    pkg_exception_snippet = "extracting data from"

                    # now extract metadata from the package
                    metadata = pkg_mgr.notification_metadata()

                    # enhance our UnroutedNotification with the metadata from the package (if any)
                    if metadata:
                        unrouted_note.enhance(metadata)

                except PackageException as e:
                    raise ValidationException(
                        f"Problem {pkg_exception_snippet} zip file: {pub_test.filename or filename} - {str(e)}") from e
                except EnhancementException as e:
                    # Indicate there is problem with the package, log error, but continue with meta-data validation below
                    pkg_problem = True
                    pub_test.log(ERROR, "While enhancing metadata - " + str(e))
                except Exception as e:
                    raise e
                finally:
                    # This always happens - ensures that we don't keep copies of the files
                    if local_id:
                        temp_store.delete(local_id, raise_exceptions=False)

            except ValidationException as e:
                # Problem with extracting package metadata, so doesn't make sense to do further metadata validation
                pub_test.log(ERROR, str(e))
                raise ValidationException(
                    cls.validation_msg(pub_test.num_errors(), pub_test.num_issues(), "with zip package")) from e
            except Exception as e:
                raise e
        # Else no file (metadata only notification), but a packaging format was specified
        elif pkg_format is not None:
            pub_test.log(
                ERROR,
                f"«content.packaging_format» ({pkg_format}) was specified but no package file was submitted")

        # Need to (potentially) apply publisher defaults before proceeding with validation
        # If either embargo or licenses are missing
        unrouted_embargo = unrouted_note.embargo
        unrouted_licenses = unrouted_note.licenses
        if unrouted_embargo is None or not unrouted_licenses:
            # Need to set provider_id to (publishers) account id as apply_licence_defaults() uses it
            unrouted_note.provider_id = account.id
            level, log_msg = get_routing_default_description(
                apply_licence_defaults(unrouted_embargo, unrouted_licenses, unrouted_note, account.publisher_data))
            if level:
                pub_test.log(ERROR if level == MAJOR else WARNING, log_msg)

        # Perform detailed "publisher testing" validation of submission (on the notification dict)
        pub_test.validate_metadata(unrouted_note.data)

        # extract the match data from the enhanced unrouted notification
        note_match_data = unrouted_note.match_data()

        # now check that we got some kind of actionable match data from the notification or the package
        if not note_match_data.is_sufficient():
            pub_test.log(ERROR, f"Found no actionable routing metadata in notification{' or associated package' if filename else ''}")

        # if we've been given files by reference, check that we can access them
        if debugging:
            pub_test.log(DEBUG, "-- validate LINKS ")
        missing_urls = 0
        for l in unrouted_note.links:
            url = l.get("url", "").strip()
            if not url:
                missing_urls += 1
            else:
                if debugging:
                    pub_test.log(DEBUG, "-- validate URL: " + url)
                try:
                    # just ensure that we can get the first few bytes, and that the response is the right one
                    resp, content, size = http.get_stream(url, cut_off=100, chunk_size=100)
                    if resp is None:
                        pub_test.log(ERROR, f"Unable to connect to server to retrieve «link.url» '{url}'")
                    else:
                        status_code = str(resp.status_code)
                        if debugging:
                            pub_test.log(DEBUG, f"-- downloaded document. Size:{str(size)} HttpStatus: {status_code}")
                        if resp.status_code != 200:
                            pub_test.log(ERROR,
                                         f"Couldn't download content from «link.url» '{url}'; Status: {status_code}")
                        elif not content:
                            pub_test.log(ERROR, f"Received no content when downloading from «link.url» '{url}'")
                except Exception as e:
                    pub_test.log(ERROR, f"Couldn't download content from «link.url» '{url}' - {str(e)}")

        if missing_urls:
            pub_test.log(ERROR, f"{missing_urls} of the {len(unrouted_note.links)} supplied «links» had no URL")
        err_count = pub_test.num_errors()
        if err_count:
            # raise more severe ValidationException if a package problem, otherwise less severe ValidationMetaException
            exception_to_raise = ValidationException if pkg_problem else ValidationMetaException
            raise exception_to_raise(cls.validation_msg(err_count, pub_test.num_issues(), "found"))
        pub_test.log(INFO, f"Request Id: {hex_id} -- Validated OK", save=False)

    @classmethod
    def create_unrouted_note(cls, account, notification, file_handle=None, file_path=None, orig_fname=None):
        """
        Create a new unrouted notification in the system on behalf of the Organisation Account holder, based on the supplied
        notification metadata and optional binary content.

        Any metadata contained within the optional binary content will be used to enhance the notification metadata.

        There will be no significant validation of the notification and file handle, although superficial inspection
        of the notification will be done to ensure it is structurally sound.

        If creation succeeds, a new notification will appear in the "unrouted" notifications list in the system, and a
        copy of the created object will be returned.  If there is a problem, an appropriate Exception will be raised.

        :param account: Organisation Account object for which this action will be carried out
        :param notification: raw notification dict object (e.g. as pulled from a POST to the web API)
        :param file_handle: File handle to binary content associated with the notification
        :param file_path: File path to LOCAL disk-file storing binary content associated with the notification
        :param orig_fname: String - Original filename (before any flattening etc)

        :return: UnroutedNotification object representing the successfully created notification
        """

        if not account.is_publisher and not current_user.is_super:
            return False
        no_content_provided = file_handle is None and file_path is None

        current_app.logger.info(f"Creating {'metadata only ' if no_content_provided else ''}notification via {notification.get('provider', {}).get('route', 'api').upper()} for Acc: '{account.org_name}' ({account.id}){' from File: ' + orig_fname if orig_fname else ''}")

        try:
            incoming = IncomingNotification(notification)
        except Exception as e:
            raise ValidationException(f"Problem with notification metadata: {str(e)}") from e

        # if successfully ingested the incoming notification, convert it to an unrouted notification
        unrouted_note = incoming.make_unrouted()
        unrouted_note.set_link_default_access_and_has_pdf_flag()    # has_pdf set here may be overridden below

        # record the provider's account id against the notification
        unrouted_note.provider_id = account.id

        # if NOT harvested notification set the agent and, possibly, the route
        if unrouted_note.provider_harv_id is None:
            # overwrite any previous provider agents, but don't overwrite provider routes
            unrouted_note.provider_agent = account.org_name
            # provider_route will already have been set unless this is notification received via API
            if not unrouted_note.provider_route:
                unrouted_note.provider_route = "api"
            unrouted_note.provider_rank = 1     # Notification from any Publisher has highest rank

        # get the format of the package
        pkg_format = unrouted_note.packaging_format
        if (pkg_format is None) != no_content_provided:
            raise ContentException(
                f"«content.packaging_format» ({pkg_format}) was specified but no package file was submitted" if no_content_provided else "Article content is provided BUT «content.packaging_format» is not specified"
            )

        if no_content_provided:
            try:
                # Add author/contributor email identifiers from emails appearing in affiliation strings
                unrouted_note.add_affiliation_email_identifiers()

                unrouted_note.category = UnroutedNotification.calc_cat_from_single_article_type(
                    unrouted_note.article_type, default=UnroutedNotification.ARTICLE)
            except Exception as e:
                raise ValidationException(f"Problem with notification metadata: {repr(e)}") from e
            unrouted_note.insert()  # May raise a DAOException
            # After insertion, the ID will have been set by the database (unrouted_note.id)
        else:
            # if zip file is available - either as a stream (via file_handle) or a disk-file (via file_path)
            # then any metadata it contains (in an XML file) will be used to enhance our notification

            # If zipfile is being supplied as a stream (via RESTful endpoint) then need to save it to a local file
            if file_handle:
                # generate ids for putting it into the store
                local_id = uuid.uuid4().hex
                try:
                    # get the Temporary Store implementation, and serialise the file handle to the local id
                    temp_store = store.TempStore()
                    try:
                        _path = file_handle.name
                    except AttributeError:
                        _path = None
                    # use str(_path) as have had an integer returned by file_handle.name (in submissions from IOP)
                    fname = basename(str(_path)) if _path else orig_fname or "incoming.zip"
                    file_path = temp_store.store(local_id, fname, source_stream=file_handle)
                except Exception as e:
                    raise e

            try:
                try:
                    ## Extract metadata from supplied package ##
                    # Instantiate the package manager - if successful, `pkg_mgr.jats` will have been set to JATS object
                    pkg_mgr = PackageFactory.get_pkg_mgr_and_extract_metadata_from_file(pkg_format, zip_path=file_path)
                except Exception as e:
                    raise Exception(f"Problem reading file: {file_path}. Error: {str(e)}") from e

                if pkg_mgr.package_has_pdf():
                    unrouted_note.has_pdf = True

                try:
                    metadata = pkg_mgr.notification_metadata()
                    # enhance our Unrouted Notification with the metadata stored in the associated package
                    if metadata:
                        unrouted_note.enhance(metadata)

                    # Finally, add author/contributor email identifiers from emails appearing in affiliation strings
                    unrouted_note.add_affiliation_email_identifiers()

                    unrouted_note.category = UnroutedNotification.calc_cat_from_single_article_type(
                        unrouted_note.article_type, default=UnroutedNotification.ARTICLE)

                except Exception as e:
                    raise ValidationException(f"Problem with notification metadata: {repr(e)}") from e

                unrouted_note.insert()  # May raise a DAOException
                # After insertion, the ID will have been set by the database (unrouted_note.id)

                ## Now SAVE THE TEMPORARILY STORED PACKAGE in the REMOTE STORE using unrouted_note.id as directory name
                try:
                    remote_store = store.StoreFactory.get()
                    pkg_mgr.store_package_files(storage_manager=remote_store, store_id=unrouted_note.id)
                except Exception as e:
                    # Ingest of file was unsuccessful, so ensure that the remote store is deleted (if it was ever created)
                    remote_store.delete(unrouted_note.id, raise_exceptions=False)
                    raise Exception(f"Problem storing file: {file_path}. Error: {str(e)}") from e
            except Exception as e:
                # If the notification was already saved, need to remove it
                if unrouted_note.id:
                    unrouted_note.delete()
                raise e
            finally:
                # This will occur even if exceptions raised in any of the inner try/except blocks was raised above
                if file_handle:
                    # remove the local copy
                    temp_store.delete(local_id, raise_exceptions=False)
        if current_app.config.get("LOG_DEBUG"):
            current_app.logger.debug(
                f"SUCCESS: Created notification ID:{unrouted_note.id} for Acc: '{account.org_name}' ({account.id})\nNotification:\n{unrouted_note.data}"
            )
        return unrouted_note

    @classmethod
    def get_outgoing_note(cls, api_vers, account, notification_id):
        """
        Retrieve a copy of the notification object as identified by the supplied notification_id, on behalf
        of the supplied Organisation account

        :param api_vers: String - API version number (e.g. "3" or "4")
        :param account: Organisation Account for which this action will be carried out
        :param notification_id: identifier of the notification to be retrieved
        :return: None or Outgoing notification
        """
        note = pull_routed_or_unrouted_notification(notification_id)
        if note is None:
            if current_app.config.get("LOG_DEBUG"):
                try:
                    accid = account.id
                except:  # Anonymous user
                    accid = None
                current_app.logger.debug(f"Notification ID: {notification_id} NOT FOUND (for Acc: {accid})")
            return None

        return note.make_outgoing(api_vers)

    @classmethod
    def get_content(cls, account, notification_id, filename=None):
        """
        Retrieve the content associated with the requested ROUTED notification_id, for specified Organisation account.

        If no filename is provided, the default content (that originally provided by the creator) will be returned,
        otherwise any file with the same name that appears in the notification will be returned.

        :param account: Organisation Account for which to carry out this request
        :param notification_id: id of the notification whose content to retrieve
        :param filename: filename of content to be retrieved
        :return tuple: (stream, file-details dict {"filename": filename, "mimetype": mimetype} )
        """
        debugging = current_app.config.get("LOG_DEBUG")
        def _raise_forbidden_exception(base_msg, msg):
            """
            Write to log and raise ForbiddenException
            :param base_msg: String - basic message
            :param msg: String - additional message
            :return:
            """
            if debugging:
                current_app.logger.debug(f"{base_msg} NOT AUTHORIZED TO RECEIVE CONTENT ({msg})")
            raise ForbiddenException(f"Forbidden: {msg}")

        base_message = f"Content Request for Acc:'{account.org_name}' ({account.id}), Notification:{notification_id}, Filename:{filename} -"

        # Attempt to retrieve specific data from Routed notification
        note_id, provider_id, repositories, pkg_format = \
            RoutedNotification.pull_data_tuple_for_content_retrieval(notification_id)

        # No Notification found
        if note_id is None:
            if debugging:
                current_app.logger.debug(f"{base_message} NOTIFICATION NOT FOUND")
            raise ContentException("Notification not found")

        # !! If we've got this far then we have found a notification & need to confirm account allowed to view it !!

        # if Repository and notification has NOT been routed to it
        if account.is_repository:
            if account.id not in repositories:
                _raise_forbidden_exception(base_message, 'notification not matched to repository')
        # if Publisher and notification is NOT one of their's
        elif account.is_publisher:
            if account.id != provider_id:
                _raise_forbidden_exception(base_message, 'publisher did not submit the requested notification')

        # !! If we've got this far the requester is entitled to see notification content !!

        # Particular file NOT specified
        if not filename:
            if pkg_format is None:
                if debugging:
                    current_app.logger.debug(f"{base_message} NO CONTENT (NO PACKAGING FORMAT)")
                raise ContentException("No content available")

            # get filename of default content (that which was originally provided by depositor)
            pkg_mgr_class = PackageFactory.get_handler_class(pkg_format)
            filename = pkg_mgr_class.zip_name()

        remote_store = store.StoreFactory.get()
        if debugging:
            current_app.logger.debug(f"{base_message} Returning stored file")

        # Attempt to retrieve required file by name, returns None if not found.
        stream = remote_store.stream(note_id, filename)
        if not stream:
            raise ContentException(f"File '{basename(filename)}' not found.")
        # Return as a stream for efficient transfer, together with file-info dict. Note that as filename can be a path
        # we extract the last segment (basename)
        file_info = {"filename": basename(filename), "mimetype": guess_mimetype(filename)}
        return stream, file_info

    @classmethod
    def get_proxy_url(cls, notification_id, pid):
        """
        Retrieve URL corresponding to the Proxy link ID
        :param notification_id:
        :param pid: proxy link ID
        :return: URL or None
        """
        note_id, links = RoutedNotification.pull_data_tuple_for_proxy_url(notification_id)
        if note_id:
            for link in links:
                if link.get("proxy", False) == pid:
                    return link.get("url")
        return None

    @classmethod
    def outgoing_notes_list_obj(cls, api_vers, since=None, since_id=None, page=None, page_size=None, repository_id=None, order="asc"):
        """
        Obtain a list of notifications which meet the criteria specified by the parameters. These
        are returned as a list of OutgoingNotifications

        :param api_vers: String - API version number (e.g. "3" or "4")
        :param since: date string for the earliest notification date requested.
        Should be of the form YYYY-MM-DDTHH:MM:SSZ, though other sensible formats may also work
        :param since_id: Integer - Return notifications with ID greater than this (only if `since` is None)  
        :param page: page number in result set to return
        (which results appear will also depend on the page_size parameter)
        :param page_size: number of results to return in this page of results
        :param repository_id: the id of the repository whose notifications to return.
        If no id is provided, all notifications for all repositories will be queried.
        :param order: The listing order: asc or desc

        :return: List of OutgoingNotifications
        """
        if since:
            try:
                since = dates.parse(since)
            except ValueError:
                raise ParameterException(f"Unable to understand 'since' date '{since}'")

        if page == 0:
            raise ParameterException("Parameter 'page' must be greater than or equal to 1")

        max_list_page_size = current_app.config.get("MAX_LIST_PAGE_SIZE")
        if page_size == 0 or page_size > max_list_page_size:
            raise ParameterException(f"Parameter pageSize must be between 1 and {max_list_page_size}")

        return RoutedNotification.outgoing_list_obj(api_vers, since_id, since, repository_id, page, page_size, order)


    @classmethod
    def delete_unrouted_notifications_and_files(cls, unrouted_ids_no_pkgs, unrouted_ids_with_pkgs, del_upto_max=False):
        """
        Delete unrouted notifications from database AND delete any stored files associated with them.

        :param unrouted_ids_no_pkgs: List of ids of notifications which DON'T have any package file stored
        :param unrouted_ids_with_pkgs: List of ids of notifications which DO have a package file stored
        :param del_upto_max: Boolean - False: Delete notifications individually;
                                       True: Delete all notifications with ID <= maximum ID in list
        :return: Tuple (num notifications deleted, num packages deleted, num packages failed to delete)
        """
        all_notifications = unrouted_ids_no_pkgs + unrouted_ids_with_pkgs
        num_with_pkgs = len(unrouted_ids_with_pkgs)
        current_app.logger.info(
            f"Deleting {len(all_notifications)} unrouted notifications and {num_with_pkgs} stored packages.")
        # First delete all files associated with the unrouted notification ids
        pkg_store = store.StoreFactory.get()
        pkgs_deleted = 0
        if num_with_pkgs:
            for note_id in unrouted_ids_with_pkgs:
                try:
                    pkg_store.delete(note_id)
                    pkgs_deleted += 1
                except store.StoreException as e:
                    current_app.logger.warning("Problem removing unrouted package files: " + str(e))

            current_app.logger.info("Deleted {} packages{}.".format(
                pkgs_deleted,
                "" if pkgs_deleted == num_with_pkgs else f"; failed to delete {num_with_pkgs - pkgs_deleted} packages"))

        # Lastly bulk delete unrouted notification records - could raise an Exception
        if del_upto_max:
            notes_deleted = UnroutedNotification.bulk_delete_less_than_equal_id(max(all_notifications))
        else:
            notes_deleted = UnroutedNotification.bulk_delete_by_id(all_notifications)

        return notes_deleted, pkgs_deleted, num_with_pkgs - pkgs_deleted
