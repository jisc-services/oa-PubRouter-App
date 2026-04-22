"""
Main workflow engine which carries out the mediation between JPER and the SWORD-enabled repositories
"""
import re
from sword2.client import SwordClient
from sword2.client.util import SwordException
from hashlib import md5
from flask import current_app
from logging import CRITICAL, ERROR, WARNING, INFO, DEBUG
from octopus.modules.logger.logger import ERROR_X
from octopus.lib.killer import GracefulKiller
from octopus.modules.store import store
from octopus.lib.mail import MailMsg, MailAccount

from router.shared.client import JPER
from router.shared.models.note import RoutedNotification, DEPOSIT_SCROLL_NUM, PURGE, DAOException
from router.shared.models.doi_register import describe_differences, dup_short_dict
from router.shared.models.account import AccOrg, OFF, OKAY, FAILING, PROBLEM
from router.shared.models.sword_out import SwordDepositRecord, DEPOSITED, FAILED

from router.jper.packages import PackageFactory

from router.jper_sword_out import xwalk
from router.jper_sword_out.format_note import format_note_as_html

# Set here to avoid overhead of setting it everytime it is needed
match_http = re.compile(r'https?://')

repo_xml_map = {
    # xml-format: (XWALK function that constructs the required XML, OPTIONAL XML content-type value, Description)
    "dspace": (xwalk.dspace_xml_entry, None, "Dspace"),
    "dspace-rioxx": (xwalk.dspace_rioxx_entry, None, "Dspace RIOXX"),
    "eprints": (xwalk.eprints_xml_entry, "application/vnd.eprints.data+xml; charset=utf-8", "Eprints"),
    "eprints-rioxx": (xwalk.eprints_rioxx_entry,
                      "application/vnd.rioxx2.data+xml;type=entry;charset=utf-8",
                      "Eprints RIOXX"),
    "eprints-rioxx-2": (xwalk.eprints_rioxx_entry,
                        "application/vnd.rioxx2.data+xml;type=entry;charset=utf-8",
                        "Eprints RIOXX v2"),
    "native": (xwalk.native_xml_entry, None, "Native")
}


class SwordOutGracefulKiller(GracefulKiller):
    """
    Implementation of GracefulKiller which ensures Sword-out closes properly on SIGTERM signals.
    """
    def __init__(self, logger, **kwargs):
        super().__init__(logger, "SWORD-Out", **kwargs)

    def _protected_exit(self):
        pass

    def _standard_exit(self):
        pass


class DepositBaseException(Exception):
    def __init__(self, msg="", base_msg=None, orig_exception=None):
        """
        Base exception message.

        :param msg: Full error message
        :param base_msg: Minimum error message (typically used to populate deposit record)
        :param orig_exception: Any precursor exception which was caught and gave rise to this exception
        """
        super(DepositBaseException, self).__init__(msg)
        self.message = msg
        self.base_msg = base_msg if base_msg else msg
        self.orig_exception = orig_exception

    def _return_msg(self, msg, prefix=""):
        _msg = prefix + msg
        if self.orig_exception:
            _msg += " - \n" + repr(self.orig_exception)
        return _msg

    def detailed_msg(self, prefix=""):
        return self._return_msg(self.message, prefix)

    def detailed_base_msg(self):
        return self._return_msg(self.base_msg)


class DepositException(DepositBaseException):
    def __init__(self, org_name, ac_id, note_id, stage, msg, orig_exception=None):
        """
        Generic exception to be thrown in the case of deposit error.

        :param org_name: String - organisation name
        :param ac_id: String - account id
        :param note_id: String - notication id
        :param stage: String - processing stage, one of: Metadata | Package | Complete (corresponding to
                                metadata-deposit, package-deposit, complete-deposit)
        :param msg: String - error message
        :param orig_exception: Object - precursor exception (if any)
        """
        self.abbrev_msg = f"{org_name} ({ac_id}): {stage} deposit failed for Notification: {note_id}"
        super(DepositException, self).__init__(f"{self.abbrev_msg} - {msg}",
                                               f"{stage} deposit failed - {msg}",
                                               orig_exception)
        self.stage = stage


class MetadataException(DepositBaseException):
    def __init__(self, msg="", orig_exception=None, xml_format=None, xml=None):
        """
        Exception to be thrown when completing a deposit.

        :param msg: String - Error message
        :param orig_exception: Object - precursor exception
        :param xml: Object or String - XML that was being deposited
        """
        super(MetadataException, self).__init__(f"Metadata deposit failed - {msg}", msg, orig_exception)
        self.xml_format = xml_format
        # saved xml_doc will be either None or a string
        self.xml_doc = xml if xml is None or isinstance(xml, str) else str(xml)

    def formatted_xml_msg(self, ac_id, note_id):
        """
        Return formatted error message that includes the XML document
        :param ac_id: String - Organisation Account ID
        :param note_id: String - Notification ID
        :return: error string, including XML document
        """
        if self.xml_doc:
            return f"Acc-ID: {ac_id}, Notification: {note_id}, {self.base_msg}\n\n--- {self.xml_format.upper()} XML sent to repository ---\n{self.xml_doc}\n------\n"
        else:
            return ""


class CompletionException(DepositBaseException):
    def __init__(self, msg="", orig_exception=None):
        """
        Exception to be thrown when completing a deposit.

        :param msg: String error message
        :param orig_exception: Object - precursor exception
        """
        super(CompletionException, self).__init__(f"Complete deposit failed - {msg}", msg, orig_exception)


class FileDepositException(DepositBaseException):
    def __init__(self, source, filename, packaging, msg="", orig_exception=None):
        """
        Exception to be thrown in the case of File deposit error.

        :param source: String - Path or URL to file
        :param filename: String - Name of file
        :param packaging: String - Packaging format
        :param msg: String - Error message
        :param orig_exception: Object - precursor exception
        """
        pkg_snippet = f", with Packaging: {packaging}" if packaging else ""
        msg = f"Problem depositing file: '{filename}'{pkg_snippet}, From: {source} - {msg}"
        super(FileDepositException, self).__init__(msg, msg, orig_exception)


class GetFileException(DepositBaseException):
    def __init__(self, msg, orig_exception=None):
        """
        Exception to be thrown in the case of error while retrieving a file for processing.

        :param msg: String - Error msg
        :param orig_exception: Object - precursor exception
        """
        super(GetFileException, self).__init__(msg, msg, orig_exception)


class Deposit:
    """
    Class that wraps all deposit functions.
    """
    graceful_killer = None
    temp_store = None
    mail_account = None
    total_deposits = 0
    store_is_local = True   # Assume Sword-Out deposit process is running on same server as main notification Store
                            # File not found Exceptions will be raised if this turns out to be wrong!
    
    @classmethod
    def init_cls(cls):
        cls.graceful_killer = SwordOutGracefulKiller(current_app.logger)
        cls.temp_store = store.TempStore()
        cls.mail_account = MailAccount()
        cls._app_config = current_app.config
        cls.store_is_local = cls._app_config.get("STORE_TYPE", "local") == "local"
        return cls

    @staticmethod
    def receipt_has_metadata(receipt):
        """
        Test whether a receipt has metadata (like dc:title) or not.

        :param receipt:DepositReceipt instance from sword2.SwordClient

        :return: Boolean - True: DepositReceipt has metadata; False: No receipt or no metadata.
        """
        return receipt is not None and receipt.atom_title is not None

    @staticmethod
    def create_sword_client(repo_data):
        """
        Create a SwordClient for the given repo.

        :param repo_data: RepositoryData object for a Repository
        :return: SwordClient using the given sword credentials.
        """
        return SwordClient(
            repo_data.sword_collection,
            {"username": repo_data.sword_username, "password": repo_data.sword_password},
            timeout=current_app.config.get("SWORD_TIMEOUT_IN_SECONDS")
        )

    @classmethod
    def send_notes_to_sword_acs(cls):
        """
        Execute a single pass on all the accounts that have sword activated and process all of their
        notifications since the last time their account was synchronised, until now

        :return: Integer - number of deposits across all sword accounts
        """
        current_app.logger.debug("Entering send_notes_to_sword_acs")
        cls.total_deposits = 0
        # process all the accounts that have sword activated
        for acc in AccOrg.with_sword_activated():
            if cls.graceful_killer.killed:
                break
            try:
                cls.process_account(acc)
            except Exception as e:
                current_app.logger.error("Problem while processing deposits - skipping remaining accounts")
                raise e
        current_app.logger.debug("Leaving send_notes_to_sword_acs run")
        return cls.total_deposits

    @classmethod
    def process_account(cls, acc):
        """
        Retrieve the notifications in JPER associated with this account and relay them on to their sword-enabled repository.

        If the account is in status FAILING, it will be skipped.

        If the account is in status PROBLEM, and the retry delay has elapsed,
            it will be re-tried, otherwise it will be skipped

        Notifications are retrieved & sent in Ascending ID order (which corresponds to date order - oldest to newest).
        Processing ceases EITHER after All notifications have been sent OR if a notification's metadata fails to deposit.
        (If content, which is sent after metadata, fails then processing of notifications continues).

        :param acc: the account whose notifications to process
        :return: Number of notifications deposited
        """
        repo_data = acc.repository_data
        save_acc = False
        num_deposits = 0
        # if no status record is found, this means the repository is new to sword deposit
        if repo_data.status is None:
            current_app.logger.debug("Acc: '%s' (%d) has no prior SWORD deposit - creating status record", acc.org_name, acc.id)
            repo_data.status = OKAY
            save_acc = True

        # check to see if we should be continuing with this account (may be failing or off)
        if repo_data.status in (FAILING, OFF):
            current_app.logger.debug("Skipping Acc: '%s' (%d) Status: %d. You may need to manually reactivate this account.",
                                     acc.org_name, acc.id, repo_data.status)
            return

        # check to see if enough time has passed to warrant a re-try (if relevant)
        if repo_data.status == PROBLEM and not repo_data.can_retry(cls._app_config.get("DEPOSIT_RETRY_DELAY")):
            current_app.logger.debug(
                "Acc: '%s' (%d) is experiencing problems & retry delay has not yet elapsed - skipping", acc.org_name, acc.id
            )
            return

        current_app.logger.debug("Processing Acc: '%s' (%d) Status: %d", acc.org_name, acc.id, repo_data.status)

        # tell the killer we're currently in a part of the code we wish to protect
        cls.graceful_killer.allow_protected_exit("process_account")
        try:
            # Loop until all notifications for account are processed OR fatal (abend) DAOException OR another Exception raised
            while True:
                try:
                    # For new repositories, last_deposited_note_id will be None, so set since_id to 0
                    routed_scroller = RoutedNotification.routed_scroller_obj(
                        since_id=repo_data.last_deposited_note_id or 0,
                        repo_id=acc.id,
                        scroll_num=DEPOSIT_SCROLL_NUM)
                    with routed_scroller:
                        # Iterate over ROUTED notifications for this repository, in ascending analysis_date order (i.e. oldest first)
                        for note in routed_scroller:
                            # If interrupt raised during processing then exit loop
                            if cls.graceful_killer.killed:
                                break
                            if cls.process_notification(acc, note):
                                # if notification is successfully processed, record the new last_deposit_date, and notification ID
                                repo_data.last_deposit_date = note.analysis_date
                                repo_data.last_deposited_note_id = note.id
                                save_acc = True
                                num_deposits += 1

                    break   # Exit `while True` loop after successfully processing all notifications

                except DAOException as e:
                    # Raise ERROR_X (which emits an email) error only if grave & NOT abend; otherwise ERROR - note
                    # that if abend is set, then a CRITICAL error is raised for that downstream, so no need for it here
                    current_app.logger.log(
                        ERROR_X if e.grave and not e.abend else ERROR,
                        f"Problem while processing '{acc.org_name}' ({acc.id}) after {num_deposits} deposits - {'' if e.abend else 'Processing will continue - '}" + e.detailed_msg_history(prefix="\n")
                    )
                    if e.abend:
                        raise e     # Exit the `while True` loop with Exception - will be caught again by outer try:

                # Any other exception is NOT caught and is therefore caught by the outer `try` clause

            # if we get to here, all notifications for this account have been deposited, and we can update the status
            # and finish up
            repo_data.status = OKAY

        except DepositException as e:
            save_acc = True
            # Set status field to either PROBLEM or FAILING
            failure = repo_data.record_failure(cls._app_config.get("DEPOSIT_RETRY_LIMIT"))
            # if a failure was recorded, raise a critical error
            if failure:
                # If a Package error occurred in process_notification then the full error details will already have been
                # logged by the critical error that was raised there, so only need short version of message here
                err_msg = e.abbrev_msg if e.stage == "Package" else e.detailed_msg()
                current_app.logger.critical(f"Deactivated account {err_msg}",
                                            extra={"subject": "Repo account deactivated"})
            elif e.stage != "Package":
                # Only log error if Not Package exception as a critical error will have already been raised in that case
                current_app.logger.error(e.detailed_msg("Account "))

        except DAOException as e:
            # Any DAOException that gets this far will have the `abend` flag set, so need to raise it.
            raise e

        except Exception as e:
            save_acc = True
            # Force status to FAILING
            repo_data.record_failure(0)
            current_app.logger.critical(f"Deactivated account {acc.org_name} ({acc.id}): UNEXPECTED error: {repr(e)}",
                                        extra={"subject": "Repo account deactivated"})
            raise e

        finally:
            cls.total_deposits += num_deposits
            if repo_data.status != OKAY:
                current_app.logger.info(
                    f"Account status set to '{repo_data.status}' for {acc.org_name} ({acc.id}), ceased processing its notifications.")
            # We don't want to update account unnecessarily
            if save_acc or cls.graceful_killer.killed:
                # Retrieve account record (for update) in case it's been updated via GUI since all accounts were read
                acc_4_update = AccOrg.pull(acc.id, for_update=True)
                # We only want to update particular values
                acc_4_update.status = acc.status
                acc_4_update.repository_data.sword_data = repo_data.sword_data
                acc_4_update.update()
                current_app.logger.info(f"Made {num_deposits} SWORD deposits to Repo Acc: '{acc.org_name}' ({acc.id}).")

            # we no longer need the killer to protect our exit
            cls.graceful_killer.cancel_protected_exit()

        current_app.logger.debug("Leaving processing account")

    @classmethod
    def send_note_by_email(cls, note, acc, repo_data, deposit_record):
        """
        Notification is marked as a duplicate. So send by email UNLESS this particular repository has NOT received previous
        notification (which could be the case if their account was activated after previous notification).

        @param note: Routed notification
        @param acc: Repository account
        @param repo_data: Repo-account's repository_data (passed to avoid having to get it again)
        @param deposit_record: partially initialised Deposit record for current deposit
        @return: Boolean - True: Email was sent, False: Email not sent because not a duplicate for this repo.
                   alternatively a DepositException may be raised
        """
        def set_deposit_rec_status_and_save(deposit_record, link_dict, status):
            deposit_record.metadata_status = status
            deposit_record.content_status = status if link_dict else None
            deposit_record.completed_status = status
            if status == DEPOSITED:
                deposit_record.edit_iri = "email"
            deposit_record.insert()

        try:
            doi = note.article_doi
            outgoing_note = note.make_outgoing()
            prev_deposit_records = SwordDepositRecord.retrieve_deposited_by_acc_and_doi(acc.id, doi, latest_first=True)
            # No previous deposits with this DOI to this repository, so don't send email (normal SWORD deposit will be made).
            if not prev_deposit_records:
                return False
            num_found = len(prev_deposit_records)
            orig_deposit = prev_deposit_records[-1]
            last_deposit = prev_deposit_records[0] if num_found > 1 else None

            # We expect to have 1 or 2 duplicate differences.
            dup_diffs = outgoing_note.dup_diffs
            orig_deposit_diffs = describe_differences(dup_diffs[0])
            cum_deposit_diffs = describe_differences(dup_diffs[1]) if len(dup_diffs) > 1 else None

            # Get best link for downloading Article zip package or PDF
            download_link, is_package = outgoing_note.get_download_link(repo_data.packaging, acc.api_key)

            metadata_representation = repo_data.dups_meta_format
            if metadata_representation == "xml":
                xml_format = repo_data.repository_xml_format
                xwalk_func, content_type, meta_format = repo_xml_map.get(xml_format, (None, None, None))
                if xwalk_func is None:
                    raise MetadataException(f"XML_FORMAT '{xml_format}' not recognised")
                # xwalk_func outputs a SwordModel instance
                if xml_format.startswith("eprints-rioxx"):  # Special case while 2 versions are supported
                    metadata_xml = xwalk_func(note, xml_format == "eprints-rioxx-2")
                else:
                    metadata_xml = xwalk_func(note)
                meta_format += " XML"
                metadata_str_or_list = metadata_xml.to_str(pretty=True)
            elif metadata_representation == "json":   # JSON required
                meta_format = "JSON"
                metadata_str_or_list = outgoing_note.json(indent=2)
            else:
                meta_format = "Text"
                metadata_str_or_list = format_note_as_html(outgoing_note,
                                                           cum_deposit_diffs["add_bits"] if cum_deposit_diffs
                                                           else orig_deposit_diffs["add_bits"])
            title = outgoing_note.article_title
            subject = "PubRouter - Duplicate article - DOI: {}{}".format(
                doi, " - (90 day file download limit)" if is_package else "")
            email = MailMsg(subject,
                         "mail/duplicate.html",
                         source={"route": outgoing_note.provider_route, "name": outgoing_note.provider_agent},
                         doi=doi,
                         title=title,
                         meta_format=meta_format,
                         metadata=metadata_str_or_list,
                         download_link=download_link,
                         is_package=is_package,
                         num_prev_notes=num_found,
                         orig_deposit_date=orig_deposit.deposit_date,
                         orig_deposit_edit_iri=orig_deposit.edit_iri,
                         orig_deposit_content=orig_deposit.content_status,
                         orig_deposit_diffs=orig_deposit_diffs,
                         cum_deposit_diffs=cum_deposit_diffs,
                         last_deposit_date=last_deposit.deposit_date if last_deposit else None,
                         last_deposit_edit_iri=last_deposit.edit_iri if last_deposit else None,
                         last_deposit_content=last_deposit.content_status if last_deposit else None,
                         dup_level_info=f"{dup_short_dict[repo_data.dups_level_pub]} from publishers & {dup_short_dict[repo_data.dups_level_harv]} from secondary sources"
                         )
            cls.mail_account.send_mail(repo_data.dups_emails, msg_obj=email)

            set_deposit_rec_status_and_save(deposit_record, download_link, DEPOSITED)
        except Exception as e:
            deposit_record.error_message = str(e)
            set_deposit_rec_status_and_save(deposit_record, None, FAILED)
            # kick the exception upstairs for continued handling, pass any MetadataException original exception
            raise DepositException(acc.org_name, acc.id, note.id, "Emailing", "Failed to send duplicate notification email", e)

        return True

    @staticmethod
    def _get_store_path(link, note_id):
        """
        This will get the path of the file in Router's store

        :param link: Dict - content details - is expected to have a "cloc"
        :param note_id: ID of notification we are working on
        :return: path
        """
        try:
            filename = link["cloc"]
            if not filename:
                # get filename of default content (that which was originally provided by depositor)
                filename = PackageFactory.get_handler_class(link["packaging"]).zip_name()

            out_path = f"{current_app.config['STORE_MAIN_DIR']}/{note_id}/{filename}"
            current_app.logger.debug(f"---_get_store_path--- PATH: {out_path}")
        except Exception as e:
            raise GetFileException(f"Couldn't construct store path from link: {link} - {repr(e)}", e)

        return out_path

    @staticmethod
    def _url_to_pathname(url, prefix=""):
        """
        Takes a URL, and converts it to a unique pathname using a hash function.
        removes beginning "http(s)://" segment, removes any URL query params to give a path, then extracts
        last segment as the filename, and in the entire path (inc filename segment) replaces all slashes with underscores

        :param url: URL to convert into a pathname & filename
        :param prefix: Optional string to prefix the MD5 hash with
        :return: string pathname - hex-string with optional prefix
        """
        # Remove leading http(s)://
        _url = match_http.sub("",url)
        _hash = md5(_url.encode())  # Need to convert String to Bytes using encode()
        return prefix + _hash.hexdigest()

    @classmethod
    def _cache_content(cls, link, note_id, acc, reqd_content_type):
        """
        Make a local copy of the content referenced by the link

        This will copy the content retrieved via the link into the temp store for use in the onward relay

        :param link: url to content
        :param note_id: ID of notification we are working on
        :param acc: user account we are working as
        :param reqd_content_type: Required mimetype of download (may be None or empty string when it's not relevant)

        :return: path-to-file
        """
        # convert URL to path name and filename
        url = link.get("url")
        path = cls._url_to_pathname(url, "c_")
        filename = "article." + (reqd_content_type.partition("/")[2] if reqd_content_type else "any")
        # See if file was previously cached to disk
        file_exists, out_path = cls.temp_store.file_exists(path, filename)

        if file_exists:
            current_app.logger.debug("---_cache_content--- File exists: " + out_path)
        else:
            # File not already in the cache, so retrieve and save it
            jper_obj = JPER(api_key=acc.api_key)
            try:
                # Get a file download iterator to retrieve the file from remote store via URL
                auth_reqd = 'router' == link.get("access")
                http_req_iter_content_obj, headers = jper_obj.get_content(url, auth=auth_reqd)
            except Exception as e:
                raise GetFileException(f"Couldn't retrieve file from: {url}", e)
            else:
                c_type = headers.get("Content-Type", "").strip()
                # Raise exception if returned content isn't of expected type.  Note that occasionally Content-Type may be
                # of form: 'application/pdf; charset=UTF-8', hence compare c_type and reqd_content_type using startswith()
                if reqd_content_type and not c_type.startswith(reqd_content_type):
                    raise GetFileException(f"Problem getting file from: {url} - Unexpected mimetype: '{c_type}', Expected: '{reqd_content_type}'.")

            try:
                current_app.logger.info(f"Caching file from URL '{url}' to path: {out_path}")
                # Save text file containing source URL
                cls.temp_store.store(path, f"NOTE_{note_id}.txt", source_data=f"{url}\n")

                # Save downloaded file to the temp store
                # Note that file is closed automatically by the 'with' stmt
                with open(out_path, "wb") as f:
                    for chunk in http_req_iter_content_obj:
                        if chunk:
                            f.write(chunk)

            except Exception as e:
                raise GetFileException(f"Couldn't save file from: {url} to: {path}", e)

        return out_path

    @classmethod
    def _process_link_package_deposit(cls, link_file_dict, note, acc, repo_data, receipt, deposit_record, in_disk_store,
                                          reqd_content_type=None):
            """
            download link_file_dict file and package_deposit into the repository

            :param link_file_dict: dict describing file to deposit
            :param note: Routed notification we are working on
            :param acc: user account we are working as
            :param repo_data: Organisation Account repository data
            :param receipt: deposit receipt from the metadata deposit
            :param deposit_record: provenance object for recording actions during this deposit process
            :param in_disk_store: True if files are stored in Router's Store instead of an external link
            :param reqd_content_type: Required mimetype of file if needed
            """
            current_app.logger.debug(
                f"Entering _process_link_package_deposit, link_file_dict: {str(link_file_dict)}, from store: {str(in_disk_store)}")

            note_id = note.id
            try:
                deposit_record.content_status = FAILED  # Default is that deposit failed
                # first, get a copy of the file from the API into the local tmp store
                if in_disk_store:
                    path = cls._get_store_path(link_file_dict, note_id)
                else:
                    path = cls._cache_content(link_file_dict, note_id, acc, reqd_content_type)

                current_app.logger.debug("---_process_link_package_deposit Stored file path: " + path)

                # now we can do the deposit from the locally stored file (which we need because we're going to use seek() on it
                # which we can't do with the http stream)
                with open(path, "rb") as f:
                    cls.package_deposit_file(link_file_dict, receipt, f, repo_data, deposit_record)

            except (FileDepositException, GetFileException) as e:
                raise DepositException(acc.org_name, acc.id, note_id, "Package", e.base_msg, e.orig_exception)

            except Exception as e:
                raise DepositException(acc.org_name, acc.id, note_id, "Package", str(e), e)

    @classmethod
    def process_notification(cls, acc, note):
        """
        For the given account and notification, deliver the notification to the sword-enabled repository.

        notifications all with the same timestamp

        :param acc: user account of repository
        :param note: Routed notification to be deposited
        :return Boolean: True - notification processed; False - processing skipped as record previously processed
        """
        current_app.logger.debug("Processing Notification: %d, Acc: '%s' (%d)", note.id, acc.org_name, acc.id)

        # make a deposit record object to record the events
        deposit_record = SwordDepositRecord({
            "repo_id": acc.id,
            "note_id": note.id,
            "doi": note.article_doi
        })
        repo_data = acc.repository_data

        # If this is a duplicate notification and repo account wants duplicates emailed
        if note.is_duplicate() and repo_data.dups_emails:
            if cls.send_note_by_email(note, acc, repo_data, deposit_record):
                return True
            # else (False returned by send_note_by_email) send the notification by SWORD

        # work out if there is a content object (Package file or PDF file) to be deposited
        link_pkg_file = None
        link_pdf = None
        # For Eprints-rioxx SWORD submission we NEVER send any files (PDF or zip) because
        # Eprints "pulls" these files using supplied special URL (to "unpacked" files in Store)
        if not repo_data.repository_xml_format.startswith("eprints-rioxx"):
            # See if content exists with a packaging format supported by the repository (ONLY 1 pkg file per notification!)
            link_pkg_file = note.get_package_link(repo_data.packaging)
            link_pdf = note.select_best_external_pdf_link()

        completed = (link_pkg_file is None and link_pdf is None)

        current_app.logger.debug("\n---- link_file: %s\n---- link_pdf: %s", str(link_pkg_file), str(link_pdf))

        ##  make the metadata deposit  ##
        try:
            receipt = cls.metadata_deposit(note, repo_data, deposit_record, completed)
        except MetadataException as e:
            # save the  deposit record (the status will have been changed within metadata_deposit func)
            deposit_record.error_message = e.detailed_msg()
            deposit_record.insert()
            # If XML doc was saved in exception
            if e.xml_doc:
                current_app.logger.error(e.formatted_xml_msg(acc.id, note.id))
            # kick the exception upstairs for continued handling, pass any MetadataException original exception
            raise DepositException(acc.org_name, acc.id, note.id, "Metadata", e.base_msg, e.orig_exception)

        last_exception = None
        if completed:
            current_app.logger.debug(
                "No content files to deposit for Notification: %d, Acc: '%s' (%d)", note.id, acc.org_name, acc.id)
            # pre-populate the content_status & completed status of the deposit record, if there is no package to be deposited
            deposit_record.content_status = None
            deposit_record.completed_status = None
        else:
            ## Send file attachments ##
            try:
                if link_pkg_file:
                    if not cls.store_is_local:
                        # Need to convert link "cloc" value to URL if we are retrieving package via API
                        link_pkg_file["url"] = note.link_cloc_to_url(cls._app_config["API_VERSION"], link_pkg_file["cloc"])
                    # link_pkg_file, if set, will always point to PubRouter store
                    cls._process_link_package_deposit(link_pkg_file, note, acc, repo_data, receipt, deposit_record,
                                                      cls.store_is_local)

                if link_pdf:
                    # Note that if link_pdf is set it will point to an external (non-PubRouter) location
                    cls._process_link_package_deposit(link_pdf, note, acc, repo_data, receipt, deposit_record,
                                                      False, "application/pdf")
            except DepositException as e:
                last_exception = e
                # Always raise CRITICAL error for package deposit fail
                current_app.logger.critical(e.detailed_msg("Account "), extra={"subject": "SWORD deposit exception"})
                deposit_record.error_message = e.detailed_base_msg()
                # Processing continues below, despite exception

            ## Complete the SWORD deposit if necessary ##
            try:
                cls.complete_deposit(receipt, repo_data, deposit_record)
            except CompletionException as e:
                deposit_exception = DepositException(acc.org_name, acc.id, note.id, "Complete", e.base_msg, e.orig_exception)
                if last_exception is not None:
                    # Combine prev and current error message
                    deposit_record.error_message += "\n******\n" + deposit_exception.detailed_base_msg()
                else:
                    deposit_record.error_message = deposit_exception.detailed_base_msg()
                last_exception = deposit_exception
                # Processing continues below, despite exception

        # Do this whether exceptions occur above or not
        deposit_record.insert()

        if last_exception:
            # Need to set this here as Metadata deposit was successful, but due to raising an exception the
            # last_deposit_date & last note id won't be set in process_account
            repo_data.last_deposit_date = note.analysis_date
            repo_data.last_deposited_note_id = note.id
            raise last_exception

        current_app.logger.debug("Leaving process notification")
        return True

    @classmethod
    def metadata_deposit(cls, note, repo_data, deposit_record, complete=False):
        """
        Deposit the metadata from the notification in the target repository

        :param note: the notification to be deposited
        :param repo_data: Organisation Account repository data
        :param deposit_record: provenance object for recording actions during this deposit process
        :param complete: True/False; should we tell the repository that the deposit process is complete
                        (do this if there is no binary deposit to follow)
        :return: the deposit metadata_receipt from the sword client
        """
        current_app.logger.debug("Depositing metadata for Notification: %d, Account: %d", note.id, repo_data.id)
        try:
            metadata_xml = None
            metadata_receipt = None
            sword = cls.create_sword_client(repo_data)
            try:
                # For eprints, in_progress doesn't do anything other than on the first deposit.
                # If it's the first deposit, when in_progress is True, it sends the deposit to 'Manage Deposits'.
                # If it's False, it sends the deposit to the 'Review Queue'.
                in_prog = repo_data.in_progress_eprints() if repo_data.is_eprints() else not complete
                repo_xml_format = repo_data.repository_xml_format
                xwalk_func, content_type, desc = repo_xml_map.get(repo_xml_format, (None,None,None))
                if xwalk_func is None:
                    raise MetadataException(f"XML_FORMAT '{repo_xml_format}' not recognised")

                outgoing_note = note.make_outgoing()    # Convert to outgoing (does some particular processing)
                if repo_xml_format.startswith("eprints-rioxx"):  # Special case while 2 versions are supported
                    metadata_xml = xwalk_func(outgoing_note, repo_xml_format == "eprints-rioxx-2")
                else:
                    metadata_xml = xwalk_func(outgoing_note)
                current_app.logger.debug("---metadata_deposit--- %s XML TO SEND:\n%s\n", desc, str(metadata_xml))
                kwargs = {"in_progress": in_prog}
                if content_type:
                    kwargs["content_type"] = content_type
                # Create the meta-data deposit (sends XML to target repository & obtains metadata_receipt)
                metadata_receipt = sword.metadata_deposit(metadata_xml, **kwargs)
                current_app.logger.debug("---metadata_deposit--- METADATA-RECEIPT:\n%s\n", str(metadata_receipt))

            except SwordException as e:
                err_msg = "SWORD EXCEPTION:"
                error_request = e.request
                if error_request:
                    err_msg += f"\nREQUEST HEADERS: {error_request.headers}"
                err_response = e.response
                if err_response is not None:
                    err_msg += f"\nSTATUS CODE: {err_response.status_code}\nRESPONSE:\n{str(err_response.content)}"
                raise MetadataException(err_msg, e, xml_format=repo_xml_format, xml=metadata_xml)

            except Exception as e:
                raise MetadataException("EXCEPTION:\n" + str(e), e, xml_format=repo_xml_format, xml=metadata_xml)

            # find out if this was an error document, and throw an error if so
            # (recording deposited/failed on the deposit_record along the way)
            if metadata_receipt.is_error():
                raise MetadataException(f"Metadata receipt error. ERROR:\n{str(metadata_receipt)}",
                                        xml_format=repo_xml_format, xml=metadata_xml)
            else:
                deposit_record.metadata_status = DEPOSITED
                deposit_record.edit_iri = metadata_receipt.edit_iri
                current_app.logger.debug(
                    "Metadata deposit successful for Notification: %d, Account: %d", note.id, repo_data.id)

            # Make sure we actually have metadata in this receipt, if not explicitly get the full receipt with metadata
            if not cls.receipt_has_metadata(metadata_receipt):
                try:
                    metadata_receipt = sword.get_deposit_receipt_with_metadata(deposit_receipt=metadata_receipt)
                except Exception as e:
                    raise MetadataException("Couldn't retrieve metadata receipt. EXCEPTION:\n" + str(e), e)

        except Exception as e:
            deposit_record.metadata_status = FAILED  # Default is to assume failure
            raise e  # Re-raise the exception

        current_app.logger.debug("Leaving metadata deposit")
        return metadata_receipt

    @classmethod
    def package_deposit_file(cls, link, receipt, file_handle, repo_data, deposit_record):
        """
        Deposit the binary package content to the target repository

        :param link: url to content
        :param receipt: deposit receipt from the metadata deposit
        :param file_handle: the file_handle handle of the binary content to deliver
        :param repo_data: Organisation Account repository data
        :param deposit_record: provenance object for recording actions during this deposit process
        """
        def specify_source(link, file_handle):
            """
            Either return a PUBLIC URL or Path to file on disk
            :param link: Link dict
            :param file_handle: Filehandle object
            :return: String - URL or File path
            """
            return link.get("access") == "public" and link.get("url") or file_handle.name


        current_app.logger.debug("Package deposit file %s; Account: %d", file_handle.name, repo_data.id)
        # create a SWORD connection object
        sword = cls.create_sword_client(repo_data)
        content_type = link.get("format")
        fname = 'article' + xwalk.set_filename_extension_from_format(content_type)

        try:
            deposit_receipt = sword.add_file(
                fname,
                file_handle,
                deposit_receipt=receipt,
                packaging=link.get("packaging"),
                content_type=content_type,
                in_progress=True
            )
        except SwordException as e:
            sword_response = e.response.content if e.response else "** NO RESPONSE **"
            raise FileDepositException(specify_source(link, file_handle), fname, link.get("packaging"), f"SWORD Response:\n{sword_response}",
                                       e)

        except Exception as e:
            raise FileDepositException(specify_source(link, file_handle), fname, link.get("packaging"), f"ERROR:\n{str(e)}", e)

            # This would append the package's files to the resource
            # deposit_receipt = sword.append(
            #   payload=file_handle,
            #   filename="deposit.zip",
            #   mimetype="application/zip",
            #   packaging=packaging,
            #   dr=receipt
            # )

        # find out if this was an error document, and throw an error if so
        # DSpace does NOT return a receipt when deposit file succeed
        if deposit_receipt and deposit_receipt.is_error():
            raise FileDepositException(specify_source(link, file_handle), fname, link.get("packaging"), f"SWORD Error Doc:\n{str(deposit_receipt)}")
        else:
            deposit_record.content_status = DEPOSITED

        current_app.logger.debug("Leaving package deposit - Success - Packaging: %s", link.get('packaging'))
        return

    @classmethod
    def complete_deposit(cls, receipt, repo_data, deposit_record):
        """
        Issue a "complete" request against the repository, to indicate that no further files are coming

        :param receipt: deposit receipt from previous metadata deposit
        :param repo_data: Organisation Account repository data
        :param deposit_record: provenance object for recording actions during this deposit process
        """
        current_app.logger.debug("Sending complete request for Account: %d", repo_data.id)

        # EPrints repositories can't handle the "complete" request
        if not repo_data.is_eprints():
            deposit_record.completed_status = FAILED
            # send the complete request to the repository
            try:
                sword = cls.create_sword_client(repo_data)  # create a connection object
                complete_receipt = sword.complete_deposit(deposit_receipt=receipt)

            except SwordException as e:
                sword_response = e.response.content if e.response else "** NO RESPONSE **"
                raise CompletionException(f"SWORD Response:\n{sword_response}", e)

            except Exception as e:
                raise CompletionException(f"ERROR\n{str(e)}", e)

            else:   # NO errors so far
                if complete_receipt and complete_receipt.is_error():
                    raise CompletionException(f"SWORD error doc:\n{str(complete_receipt)}")

        # We only get this far if no errors
        deposit_record.completed_status = DEPOSITED
        current_app.logger.debug("Leaving complete deposit - Successfully sent complete request")

    @staticmethod
    def classes_for_cursor_close():
        """
        Return list of classes for which cursors are to be closed (if action_after_run is set to "close_class_curs")
        """
        return [RoutedNotification, SwordDepositRecord]
