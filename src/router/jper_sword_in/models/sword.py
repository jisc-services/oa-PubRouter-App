"""
Models for python-sword2 implementation for Router SWORD-IN 

NOTE: authentication for Router's SWORD server endpoint relies upon Username = Account UUID; and Password = API-Key.

Following successful SWORD authentication the value of `current_user` will be an AccOrg account object (as opposed to
an AccUser object).

These models are used by the SWORD2 server located at /sword2, which provides a means  for depositing articles
into Router using the SWORD2 protocol.

*** IMPORTANT - Router SWORD-IN implementation special characteristics ***
* Handling submitted files:
    (1) Submitting a SINGLE Zip file containing a publisher deposit (just like zip files submitted via FTP) - These
        are stored as-is by the SWORD-IN service and later presented to the Router notification handling process (which
        may flatten the zip file). Only ONE zip file is allowed.
    (2) Submitting separate (non-zip) binary file(s) (JATS XML, PDF etc.) with the In-Progress flag True -
        which the SWORD-IN service will store separately, but later will be bundled as a (derived) Zip file before
        presenting to the Router notification handling process.
    NOTE: Submitting a combination of Zip and non-Zip files is NOT supported.
    (3) Once a submission is complete (In-Progress flag is False) then the submitted files are presented to the Router
        notification handling process as a zip file for ingesting to create an Unrouted-notification.  After this time
        the original SWORD submission file(s) will no longer be accessible via SWORD as they are deleted once the
        notification has been ingested.  Note that if Publisher-Autotesting is in progress, then testing is performed
        and may result in a SWORD error response.
    (4) Atom Entry metadata CANNOT be submitted - Router only accepts JATS XML metadat submitted as a file.

JPERSwordAuth: Basic auth implementation for the SWORD API
JPERContainer: python-sword2 Container implementation. Uses SwordInDepositRecord MySQL db DAO for persisted data
    Also uses the TMP store as we don't want to keep the file data over long periods of time.
JPERCollection: python-sword2 Collection implementation
JPERRepository: python-sword2 Repository implementation
"""

from flask import request, current_app
from flask_login import current_user, login_user
from io import BytesIO
from zipfile import ZipFile
from octopus.modules.store.store import TempStore, os
from router.jper.api import JPER
from router.jper.models.publisher import SwordInDepositRecord
from router.shared.models.account import AccOrg
from router.jper.validate_route import auto_testing_validation_n_routing, ValidationException
from router.jper.pub_testing import init_pub_testing, CRITICAL, ERROR, WARNING, INFO
from router.jper.packages import FTPZipFlattener, PackageException

from sword2.server.auth import SwordAuthenticationBase
from sword2.server.repository import RepoContainer, RepoCollection, Repository
from sword2.server.exceptions import RepositoryError


class JPERSwordAuth(SwordAuthenticationBase):
    """
    Basic Auth login into JPER for SWORD2.
    """

    @classmethod
    def valid_credentials(cls, auth):
        """
        Login with given Basic Auth credentials

        Will only log in the user if they are a superuser or a publisher.

        :param auth: Flask authorization object
        """
        if auth:
            # First retrieve Organisation account
            org_acc = AccOrg.pull(auth.username, pull_name="uuid")
            if org_acc is not None and org_acc.api_key == auth.password:
                if org_acc.is_super or org_acc.is_publisher:
                    login_user(org_acc, remember=False)
                    return True
        return False

    @classmethod
    def authenticate(cls, collection_id=None, container_id=None):
        """
        Validate the authorization credentials of a request.

        Will also check if the account has access to the container.

        This will throw an error if the user is unauthenticated - which will cause a 400 response.

        :param collection_id: ID of collection
        :param container_id: ID of container  -  NOTE: This is a requirement of the abstract class.
        """
        # Validate credentials provided in the request's authorization attribute, this sets the `current_user` object
        valid = cls.valid_credentials(request.authorization)
        if collection_id and valid and current_user.is_publisher:
            valid = current_user.uuid == collection_id
        if not valid:
            cls.unauthenticated()


class JPERContainer(RepoContainer):
    """
    RepoContainer implementation for JPER

    This stores all the files and data related to a SWORD deposit. It also is used to create, update and delete
    files inside of a SWORD deposit.

    Uses database for the persistent store (for storing in_progress etc).

    The ".entry.atom" file stored is a special file for storing specifically the Entry metadata itself.
    """
    INIT_FILENAME = "SWORD_Container"
    METADATA_FILENAME = ".entry.atom"

    def __init__(self, record, collection_id, org_acc, save_metadata=False):
        """
        Initialize a JPERContainer with a SwordInDepositRecord instance

        :param record: SwordInDepositRecord instance
        :param collection_id: Id (UUID) of parent collection
        :param org_acc: SwordInDepositRecord instance
        :param save_metadata: Boolean - True: Save Container metadata to file; False: Don't save metadata to file

        This uses the db container to get the store ID for the deposit, as the store ID is where the
        files will be stored.
        """
        super().__init__(None, str(record.id))
        self._app_config = current_app.config
        current_app.logger.debug(f"SWORD-IN: Container with id '{record.id}' for account '{org_acc.id}' accessed")
        self.org_acc = org_acc
        self.record = record
        self.updated = record.updated
        self.temp_store = TempStore()               # Temp store is ALWAYS on Local server
        self._path = os.path.join(collection_id, self.id)
        self._files_path = os.path.join(self._path, "files")    # Location within container where binary files are placed
        self._files_full_path = self.temp_store.full_path(self._path, "files")    # Location within container where binary files are placed
        metadata_synched = self._load_metadata_from_file_or_create_file(save_metadata)
        if not metadata_synched and record.name != self.INIT_FILENAME:
            # This is the case where a container is being instantiated AFTER the disk directory (temporarily) storing
            # the deposit has been deleted (including the ENTRY metadata file)
            self.add_part(record.name)
        self.in_progress = record.in_progress

    def _load_metadata_from_file_or_create_file(self, save_metadata):
        """
        Load the metadata from the store, using the id of this container and the collection id.

        If there is no metadata file & `save_metadata` is true then store whatever metadata is currently in this container.
        :param save_metadata: Boolean - True: Save Container metadata to file; False: Don't save metadata to file

        :return: Boolean - True: metadata matches that on disk False: metadata does not match that on disk
        """
        metadata_synched = False
        metadata_file_ptr = self.temp_store.get(self._path, self.METADATA_FILENAME)
        if metadata_file_ptr:
            super()._load_metadata(metadata_file_ptr.read())
            metadata_file_ptr.close()
            metadata_synched = True
        elif save_metadata:
            self._store_metadata()
            metadata_synched = True
        return metadata_synched

    def _store_metadata(self):
        """
        IMPLEMENTS RepoContainer._store_metadata

        Store the metadata in this container.

        Cast to a string representation of the XML stored in this container, then encode to bytes.
        After that, store the file in .entry.atom.
        """
        # self.temp_store.store(self._path, self.METADATA_FILENAME, source_data=self.string_metadata().encode("utf-8"))
        self.temp_store.store(self._path, self.METADATA_FILENAME, source_data=bytes(self))

    def _store_binary_file(self, stream, filename, is_derived=False):
        """
        IMPLEMENTS RepoContainer._store_binary_file

        Store a file in this container.

        Needs the is_derived param as it will be passed by the superclass, but we do not need to use it.

        :param stream: File stream
        :param filename: Name of flie
        :param is_derived: Whether or not this file was derived from a zip file
        """
        self.temp_store.store(self._files_path, filename, source_stream=stream)

    def _find_any_existing_zipfile_name(self):
        """
        If a zipfile exists in the container, then return its name. Also return indicator if non-zip files exist.
        :return: Tuple - (Zip filename, has_non_zip)
        """
        zip_name = None
        has_non_zip = False
        # Check if a zip file with different name (i.e. not being replaced) already exists
        for f_name in self.contents:
            if f_name.endswith(".zip"):
                zip_name = f_name
            else:
                has_non_zip = True
        return zip_name, has_non_zip

    def add_or_replace_binary_file(self, stream, filename, is_derived=False):
        """
        Method for adding or replacing binary data.

        OVERRIDES RepoContainer.add_or_replace_binary_file

        This does the following DIFFERENTLY:
        * Zip files are stored 'as-is', NOT unpacked
        * Cannot store >1 zip file

        :param stream: Some sort of file stream
        :param filename: Filename for this stream
        :param is_derived: Boolean - whether the file is derived from another (e.g. by unpacknig a zip file)

        :return: No return value
        """
        existing_zip_name, has_non_zip = self._find_any_existing_zipfile_name()
        if filename.endswith(".zip"):
            if existing_zip_name:
                # Check if a zip file with different name (i.e. not being replaced) already exists
                if filename != existing_zip_name:
                    # 422: Unprocessable Content
                    raise RepositoryError(
                        "Prohibited file combination",
                        f"Only one Zip file allowed; you attempted to store '{filename}', but '{existing_zip_name}' was previously stored.",
                        status_code=422)
            elif has_non_zip:
                raise RepositoryError(
                    "Prohibited file combination",
                    f"Cannot mix Zip and non-Zip files; you attempted to store '{filename}', but non-zip files were previously stored.",
                    status_code=422)
        elif existing_zip_name:
            # 422: Unprocessable Content
            raise RepositoryError(
                "Prohibited file combination",
                f"Cannot mix non-Zip and Zip files; you attempted to store '{filename}', but '{existing_zip_name}' was previously stored.",
                status_code=422)

        self._add_file_to_current_request_contents(filename, is_derived)
        self._store_binary_file(stream, filename, is_derived)
        self.add_part(filename, allow_duplicates=False)
        if not is_derived:
            self._set_updated_and_store_metadata()
            if self.record.name == self.INIT_FILENAME:
                self.record.name = filename
                self.record.update()

    def update_metadata(self, entry_data):
        """
        Merge the new data with our current metadata. Will keep the ID of the current container.

        :param entry_data: Some kind of entry data (binary, string, other Entries)
        """
        # 422: Unprocessable Content
        raise RepositoryError(
            "Atom Entry submission prohibited",
            f"Publications Router ONLY accepts Metadata deposited as a JATS XML file (which may be within a Zip package).",
            status_code=422)

    def add_or_replace_metadata(self, entry_data):
        """
        Load new metadata and then store the metadata in the container.

        :param entry_data: Some kind of entry data (binary, string, other Entries)
        """
        # 422: Unprocessable Content
        raise RepositoryError(
            "Atom Entry submission prohibited",
            f"Publications Router ONLY accepts Metadata deposited as a JATS XML file (which may be within a Zip package).",
            status_code=422)

    @property
    def contents(self):
        """
        IMPLEMENTS RepoContainer.contents

        Return a list of filenames in this container.

        :return: List of files inside the files directory of this container.
        """
        return self.temp_store.list(self._files_path) or []

    def contents_with_path(self):
        """
        :return: List of Tuples [(file-full-path, filename), ...]
        """
        return [(self.temp_store.full_path(self._files_path, fname), fname) for fname in self.contents]

    def get_file_content(self, filename):
        """
        IMPLEMENTS RepoContainer.get_file_content

        Get the binary content of a file

        :param filename: Filename to get

        :return: Binary content of the file if it existed in the store, otherwise None
        """
        # TempStore GET returns a file-stream
        return self.temp_store.get(self._files_path, filename)

    def get_all_file_content_as_zip(self):
        """
        OVERRIDES RepoContainer.get_all_file_content_as_zip

        Get all file content in this container as a Zip file - either returns the (single) existing Zip or it
        creates a derived Zip file.

        :return: File stream of the zipped content or None
        """
        zip_stream = None
        existing_zip_name, has_non_zip = self._find_any_existing_zipfile_name()
        if existing_zip_name:
            zip_stream = self.get_file_content(existing_zip_name)
        elif has_non_zip:
            # Bundle the non-zip files into a zipfile stream
            zip_stream = BytesIO()
            with ZipFile(zip_stream, "w", compression=self.compression, compresslevel=self.compress_level) as zip_file:
                for filepath, filename in self.contents_with_path():
                    zip_file.write(filepath, filename)
            zip_stream.seek(0)

        return zip_stream

    @property
    def in_progress(self):
        """
        IMPLEMENTS RepoContainer.in_progress

        Simple property to return the in_progress value of the db container

        :return: in_progress property of db container
        """
        return self.record.in_progress

    @in_progress.setter
    def in_progress(self, value):
        """
        IMPLEMENTS RepoContainer.in_progress

        Simple setter to set the container's value for in_progress.

        Value will be always cast to a bool - so if it's a truthy, the value will be True, if it's falsy,
        the value is False. This should only ever be given booleans anyway, however.

        :param value: Boolean value
        """
        # Save the current in-progress statement in XML
        self.set_element_with_value("sword:verboseDescription",
                                    self._app_config.get("IN_PROGRESS_DESCRIPTIONS", {}).get(value)
                                    )
        self.record.in_progress = value
        # self.record.update()
        # Don't update, because the only place this is called is immediately before ._proces() which calls update

    def delete(self):
        """
        IMPLEMENTS RepoContainer.delete

        Delete this container and files associated with it

        This will delete the Sword-deposit-record first, then the folder that stores the files related to this container.
        """
        self.record.delete()
        self._delete_temp_store_container()

    def _delete_temp_store_container(self):
        """
        Deletes just the store container.
        """
        return self.temp_store.delete(self._path, raise_exceptions=False)

    def delete_content(self, filename=None):
        """
        IMPLEMENTS RepoContainer.delete_content to delete file content.

        If filename is None then should delete ALL the file content.

        :param filename: Filename to delete or None to delete all content

        :return: whether the file was successfully deleted
        """
        successful = self._delete_content(filename)
        if successful:
            self.remove_parts(filename)
            self._set_updated_and_store_metadata()
            if filename:
                if self.record.name == filename:
                    other_parts = self.has_part
                    self.record.name = other_parts[0] if other_parts else self.INIT_FILENAME
                    self.record.update()
            else:
                self.record.name = self.INIT_FILENAME
                self.record.update()

        return successful

    def _delete_content(self, filename):
        """
        IMPLEMENTS RepoContainer._delete_content

        Delete a specific file or all files.

        :param filename: Filename to delete content of

        filename can be None, as the file that passes arguments to this may pass None.

        :return: True - at least one attempted deletion succeeded or False - all attempted deletions failed
        """
        if not filename:
            contents = self.contents
            # deleted_ok is initially set to False if there are files to delete, otherwise set to True
            deleted_ok = len(contents) == 0
            # Delete files in the container (but not the container itself)
            for filename in contents:
                # By ORing the result of delete with current value of deleted_ok we ensure that False is returned ONLY
                # if all attempted deletions fail. If any deletion succeeds then True is returned
                deleted_ok = self.temp_store.delete(self._files_path, filename, raise_exceptions=False) or deleted_ok
        else:
            deleted_ok = self.temp_store.delete(self._files_path, filename, raise_exceptions=False)

        return deleted_ok

    def get_all_file_content_as_flattened_zip(self, pub_test):
        """
        Get all file content in this container as a Zip file - either returns the (single) existing Zipfile pathname
        or it creates a derived Zip file which is returned as a stream.

        :return: Tuple - (ZipFilename, ZipFile stream of the zipped content) NB. one or both values will be None
        """
        zip_stream = None
        zip_pathname = None
        existing_zip_name, has_non_zip = self._find_any_existing_zipfile_name()
        if existing_zip_name:
            zip_pathname = self.temp_store.full_path(self._files_path, existing_zip_name)
            try:
                flattener = FTPZipFlattener(
                    self._files_full_path,
                    pub_test,
                    max_zip_size=self._app_config.get("MAX_ZIP_SIZE"),
                    large_zip_size=self._app_config.get("LARGE_ZIP_SIZE")
                )
                flattener.process_and_zip(zip_pathname)
            except Exception:
                raise
        elif has_non_zip:
            # Bundle the non-zip files into a zipfile stream
            zip_stream = BytesIO()
            with ZipFile(zip_stream, "w", compression=self.compression, compresslevel=self.compress_level) as zip_file:
                for filepath, filename in self.contents_with_path():
                    zip_file.write(filepath, filename)
            zip_stream.seek(0)

        return zip_pathname, zip_stream

    def _process_completed_deposit(self):
        """
        IMPLEMENTS RepoContainer._process_completed_deposit

        When the deposit is complete, get all the file content as a zip, then send it off to JPER.
        """
        notification = {
            "vers": self._app_config.get("API_VERSION"),
            "provider": {"route": "sword"},
            "content": {"packaging_format": "https://pubrouter.jisc.ac.uk/FilesAndJATS"}
        }

        pub_test = init_pub_testing(self.org_acc, "sword", init_mail=True)
        pub_test.set_filename(self.record.name)
        try:
            zip_path, zip_stream = self.get_all_file_content_as_flattened_zip(pub_test)
        except Exception as e:
            flatten_exception = e
        else:
            flatten_exception = None

        # Publisher is in automated-testing mode
        if self.org_acc.publisher_data.in_test:
            try:
                if flatten_exception:
                    raise flatten_exception
                auto_testing_validation_n_routing(pub_test, notification, note_zip_file=zip_path, note_zip_stream=zip_stream)
            except (ValidationException, PackageException) as e:
                errors = "\nERRORS:\n  " + '\n  '.join(pub_test.errors).replace('&', 'and') + "\n" if pub_test.errors else ""
                issues = "\nISSUES:\n  " + '\n  '.join(pub_test.issues).replace('&', 'and') + "\n" if pub_test.issues else ""
                raise RepositoryError(f"Failed Deposit {str(e).replace('&', 'and')}", f"{errors}{issues}", status_code=400)
            except Exception as e:
                raise RepositoryError(f"SWORD deposit could not be processed - {repr(e)}", status_code=400)
            finally:
                self.delete()   # Remove temporary files and self.record
        # Normal live running mode
        else:
            try:
                if flatten_exception:
                    raise flatten_exception
                unrouted = JPER.create_unrouted_note(self.org_acc, notification, file_handle=zip_stream, file_path=zip_path, orig_fname=self.record.name)
                self.record.notification_id = unrouted.id
                self.record.successful = True
                # Finally, delete the store content
                if self._app_config.get("DELETE_AFTER_INGEST", True):
                    self._delete_temp_store_container()
                else:
                    self._set_updated_and_store_metadata()
            except Exception as e:
                # Raise a repository error to tell the user something went wrong with the submission
                error_message = str(e)
                self.record.error = error_message
                # Deposit will remain in TempStore (until separate Scheduler job deletes it in X days)
                raise RepositoryError(
                    f"SWORD deposit failed", verbose_msg=f"{error_message}", status_code=400,
                    log_level=CRITICAL,
                    log_msg = f"Org: {self.org_acc.org_name} ({self.org_acc.id}); Container: {self.id}; Filename: {self.record.name}; Path: {self._files_full_path}."
)
            finally:
                self.record.update()


class JPERCollection(RepoCollection):
    """
    Implementation of a RepoCollection for JPER.

    Each Publisher account will have a JPERCollection, which are retrieved by using the list and get_collection
    methods of JPERRepository.
    """
    allow_generate_id = False     # _generate_container_id() is NEVER called

    def __init__(self, org_acc):
        """
        We don't need to save Collection data, so don't add any in the __init__.
        :param org_acc: Publisher Org Account
        """
        super().__init__(None, org_acc.uuid)
        self.org_acc = org_acc
        self.org_id = org_acc.id
        self.feed_max_containers = current_app.config.get("FEED_MAX_CONTAINERS", 10)

    def _generate_container_id(self):
        """
        OVERRIDES RepoCollection._generate_container_id

        Unique UUID generator for collections without slugs. (requests without the SWORD2 Slug header.)

        This overrides the default version of _gen_id because our db objects have a different way of
        generating IDs. this changes the function to have parity with the octopus DAO models.

        :return: Unique ID for a container for this collection
        """
        raise RepositoryError("ID is provided by database insert; it cannot be generated.", status_code=500, log_level=CRITICAL)

    def _get_last_updated_from_list_of_containers(self, containers):
        # Containers are sorted in descending ID order which corresponds to updated date
        return containers[0].updated

    @property
    def containers(self):
        """
        IMPLEMENTS RepoCollection.containers

        Get all database Containers for this collection.

        Will query database for all containers for this collection, then create JPERContainers from them.
        """
        return [JPERContainer(record, self.id, self.org_acc) for record in
                SwordInDepositRecord.get_all_from_publisher(self.org_id, limit_offset=self.feed_max_containers)]

    def _valid_sword_in_deposit_record(self, record):
        """
        Check if a SwordInDepositRecord is associated with current organisation.

        :param record: SwordInDepositRecord instance or None

        :return: Boolean - True: record is associated with organisation; False: no record or not associated with org.
        """
        return record and self.org_id == record.publisher_id

    def _create_container_with_id(self, id=None):
        """
        IMPLEMENTS RepoCollection._create_container_with_id

        Create a container with a given ID.

        The record file-name will be set the name to initial value "SWORD_Container" which will be overwritten when first
        file is loaded.

        Then, create a JPERContainer out of the SwordInDepositRecord.

        :param id: ID to give to the new container - VALUE IS ALWAYS IGNORED

        :return: JPERContainer created with the given ID
        """
        record = SwordInDepositRecord()
        record.in_progress = True
        record.publisher_id = self.org_id
        record.name = JPERContainer.INIT_FILENAME
        record.error = ""
        record.successful = False
        record.matched = False
        record.insert()
        current_app.logger.debug(f"SWORD-IN: Container created for account '{self.org_id}' with id '{record.id}'")
        return JPERContainer(record, self.id, self.org_acc, save_metadata=True)

    def container_exists(self, id):
        """
        IMPLEMENTS RepoCollection.container_exists

        Test if the container exists by pulling the ID, if there is no result, there is no container.

        :param id: ID of container to check

        :return: Container is found, otherwise None.
        """
        return self._valid_sword_in_deposit_record(SwordInDepositRecord.pull(id))

    def get_container(self, id):
        """
        IMPLEMENTS RepoCollection.get_container

        Get a container with a given ID.

        :param id: ID of container to check

        :return: JPERContainer if Container with id existed, otherwise None.
        """
        record = SwordInDepositRecord.pull(id)
        return JPERContainer(record, self.id, self.org_acc) if self._valid_sword_in_deposit_record(record) else None

    def delete(self):
        """
        IMPLEMENTS RepoCollection.delete

        Do not allow deletion of collections.
        """
        return False


class JPERRepository(Repository):
    """
    We have a collection for each publisher, so check to make sure that an account exists for the collection
    and that account is a publisher. Publishers upload content via SWORD to their own repository collection.
    """

    @property
    def collections(self):
        """
        IMPLEMENTS Repository.collections

        If the user is a publisher, return that publisher's collection.
        If the user is a superuser, return all collections.
        otherwise, return no collections.

        :return: A list of JPERCollection which refer to each publisher.
        """
        # Collection ids will be the same as the current user's account UUID, unless it's a superuser.
        return [JPERCollection(account) for account in AccOrg.get_publishers()] if current_user.is_super \
            else [JPERCollection(current_user.copy())]      # Copy for efficiency as current_user is LocalProxy

    def collection_exists(self, id):
        """
        IMPLEMENTS Repository.collection_exists

        Check whether the ID is an ID for an Organisation Account that is a publisher.

        :param id: ID to check

        :return: OrgAcc object if passed ID relates to publisher account, otherwise None
        """
        org_acc = None
        if current_user.is_super:
            org_acc = AccOrg.pull(id, pull_name="uuid")
            # In case the super user has put in an ID that does not exist
            if org_acc and not org_acc.is_publisher:
                org_acc = None  # Not a publisher account
        elif current_user.uuid == id and current_user.is_publisher:
            org_acc = current_user.copy()   # Copy because current_user is LocalProxy
        return org_acc

    def get_collection(self, id):
        """
        IMPLEMENTS Repository.get_collection

        Get a collection if the ID exists.  The ID corresponds to the Publisher account UUID.

        :param id: ID (Publisher UUID) of collection

        :return: JPERCollection if the collection with ID exists, otherwise None.
        """
        org_acc = self.collection_exists(id)
        return JPERCollection(org_acc) if org_acc else None

    def create_collection(self, *args, **kwargs):
        """
        Do not allow creation of collections, as they are implicitly created when a publisher account is created.
        """
        return False
