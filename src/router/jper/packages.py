"""
Provides general packaging handling infrastructure and specific implementations of known packaging formats

All packaging format handlers should extend the PackageHandler class defined in this module.

Packages should then be configured through the PACKAGE_HANDLERS configuration option
"""
import os
import shutil
import re
from io import BytesIO
from lxml import etree
from zipfile import ZipFile, BadZipfile, ZIP_STORED

from flask import current_app
from octopus.lib.data import decode_non_xml_html_entities, UTF8_BYTES
from octopus.lib.plugin import load_class
from octopus.modules.store import store
from router.shared.models.note import NotificationMetadata
from router.jper.models.jats import JATS, InvalidJATSError
from router.jper.pub_testing import init_pub_testing, ERROR, WARNING, INFO

# Regex to match 'article' root element, where 'article' is followed by ' ' or '>'
# (?:\xef\xbb\xbf|\xfe\xff|\xff\xfe)? non-capturing group matches UTF-8 or UTF-16 big-endian or UTF-16 little-endian Byte Order Mark that (may) appear at start of the file text stream
# (?:\s*<[?!][^>]+>)* non-capturing group matches repeating elements like '<?……>' or '<!……>' (separated by white-space)
# - e.g. <?xml version="1.0" encoding="utf-8"?>  OR
#        <!-- some comment -->  OR
#        <!DOCTYPE article PUBLIC "-//NLM//DTD Journal Archiving and Interchange DTD v2.3 20070202//EN" "archivearticle.dtd">
regex_root_article = re.compile(rb"^(?:\xef\xbb\xbf|\xfe\xff|\xff\xfe)?(?:\s*<[?!][^>]+>)*\s*<(article)[ >]", re.S)
# Regex to match 'xmlns=' inside current XML element - follows use of `regex_root_article`
regex_xmlns_in_element = re.compile(rb"^[^>]*?(xmlns=[^ >]+)", re.S)


class PackageException(Exception):
    """
    Generic exception to be thrown when there are issues working with packages
    """
    pass


class PackageFactory:
    """
    Factory which provides methods for accessing specific PackageHandler implementations
    """

    @classmethod
    def get_handler_class(cls, pkg_format):
        """
        Obtain a PackageHandler class name for the provided format to be used to work
        with processing an incoming binary object.

        :param pkg_format: Required package format
        :return: Name of class which will handle the pkg_format
        """
        pkg_formats_to_class_dot_name_dict = current_app.config.get("PACKAGE_HANDLERS", {})
        class_dot_path = pkg_formats_to_class_dot_name_dict.get(pkg_format)
        if class_dot_path is None:
            msg = f"No handler for package format '{pkg_format}'"
            current_app.logger.error(f"Package Factory - {msg}")
            raise PackageException(msg)
        return load_class(class_dot_path)


    @classmethod
    def get_pkg_mgr_and_extract_metadata_from_file(cls, pkg_format, zip_path=None, metadata_files=None, pub_test=None):
        """
        Obtain an instance of a PackageHandler for the specified format and instantiate it with data from either
        Zip file or metadata file.

        If the zip path is provided, the handler will be constructed from data in that file

        If only the metadata file handles are provided, the handler will be constructed using data in those

        Metadata file handles should be of the form

        ::

            [("filename", <file handle>)]

        It is recommended that as the metadata files are likely to be highly implementation specific
        that you rely on the handler itself to provide you with the names of the files, which you may
        use to retrieve the streams from store.

        :param pkg_format: format identifier for the package handler.  As seen in the configuration.
        :param zip_path: file path to an accessible on-disk location where the zip file is stored
        :param metadata_files: list of tuples of filename/filehandle pairs for metadata files extracted from a package
        :param pub_test: Publisher testing object
        :return: an instance of a PackageHandler, constructed with the zip_path and/or metadata_files
        """
        pkg_mgr_class = cls.get_handler_class(pkg_format)
        # Instantiate an instance of the package manager (handler) class
        return pkg_mgr_class(zip_path=zip_path, metadata_files=metadata_files, pub_test=pub_test)

    @classmethod
    def get_pkg_mgr(cls, pkg_format):
        """
        Obtain an instance of a PackageHandler which can be used to process a package of format pkg_format.

        :param pkg_format: format identifier for the package handler.
        :return: Instantiated class
        """
        pkg_mgr_class = cls.get_handler_class(pkg_format)
        return pkg_mgr_class()


class PackageManager:
    """
    Class which provides an API onto the package management system

    If you need to work with packages, the operation you want to do should be covered by one of the
    methods on this class.
    """

    @classmethod
    def ingest(cls, store_id, zip_path, pkg_format, storage_manager=None):
        """
        Ingest into the storage system the supplied package, of the specified format, with the specified store_id.

        This will attempt to load a PackageHandler for the format around the zip_file.  Then the original
        zip file and the metadata files extracted from the package by the PackageHandler will be written
        to the storage system with the specified id.

        If a storage_manager is provided, that will be used as the interface to the storage system,
        otherwise a storage manager will be constructed from the StoreFactory.

        A copy of the package manager will be returned, for use in enhancing the UnroutedNotification
        associated with this submission.

        The original Zip file is NOT deleted

        :param store_id: the id to use when storing the package
        :param zip_path: locally accessible path to the source package on disk
        :param pkg_format: format identifier for the package handler.  As seen in the configuration.
        :param storage_manager: an instance of Store to use as the storage API

        :return: the package manager class used in creating the submission
        """
        # load the package manager corresponding to package format,
        # extract metadata from the zip package and add it to the package manager object
        pkg_manager = PackageFactory.get_pkg_mgr_and_extract_metadata_from_file(pkg_format, zip_path)
        if storage_manager is None:
            storage_manager = store.StoreFactory.get()

        pkg_manager.store_package_files(storage_manager=storage_manager, store_id=store_id)

        return pkg_manager

    @classmethod
    def extract(cls, store_id, format, storage_manager=None):
        """
        Extract notification metadata from the package in the store which has the specified format

        This will look in the store for the store_id, and look for files which match the known metadata file
        names from the PackageHandler which is referenced by the format.  Once those files are found, they are loaded
        into the PackageHandler and the metadata is extracted and returned.

        If a storage_manager is provided, that will be used as the interface to the storage system,
        otherwise a storage manager will be constructed from the StoreFactory.

        :param store_id: the storage id where this object can be found
        :param format: format identifier for the package handler.  As seen in the configuration.
        :param storage_manager: an instance of Store to use as the storage API
        :return: NotificationMetadata representing the metadata stored in the package
        """
        if current_app.config.get("LOG_DEBUG"):
            current_app.logger.debug(f"Package Extract - StoreID: {store_id}; Format: {format}")

        # load the storage manager
        if storage_manager is None:
            storage_manager = store.StoreFactory.get()

        # list the stored files
        file_names = storage_manager.list(store_id)

        # store_id was not a directory location
        if file_names is None:
            return None, None

        # get an instance of the package manager that can answer naming convention questions
        pkg_handler_class = PackageFactory.get_handler_class(format)

        #  Determine which of the stored files are the metadata files
        metadata_file_names = pkg_handler_class.metadata_names()
        handles = []
        for file_name in file_names:
            if file_name in metadata_file_names:
                file_handle = storage_manager.get(store_id, file_name)
                handles.append((file_name, file_handle))

        # create the specific package manager
        package_handler = pkg_handler_class(metadata_files=handles)

        # now return the metadata
        return package_handler.notification_metadata()

    @classmethod
    def convert(cls, store_id, source_format, target_formats, storage_manager=None):
        """
        For the package held in the store at the specified store_id, convert the package from
        the source_format to the target_format.

        NOTE that some package definitions (notably FileAndJats and SimpleZip) actually have IDENTICAL structures;
        in this case real conversion is not necessary as both package types can share the same zip file.

        This will make a local copy of the source package from the storage system, make all
        the relevant conversions (also locally), and then synchronise back to the store.

        If a storage_manager is provided, that will be used as the interface to the storage system,
        otherwise a storage manager will be constructed from the StoreFactory.

        :param store_id: the storage id where this object can be found
        :param source_format: format identifier for the input package handler.  As seen in the configuration.
        :param target_formats: list of required package fornats.
        :param storage_manager: an instance of Store to use as the storage API
        :return: a list of tuples of the conversions carried out of the form [(format, filename)]
        """
        msg_snippet = f"StoreID: {store_id}; SourceFormat: {source_format}; TargetFormats: {target_formats}"
        if current_app.config.get("LOG_DEBUG"):
            current_app.logger.debug("Package Convert - " + msg_snippet)

        # load the storage manager
        if storage_manager is None:
            storage_manager = store.StoreFactory.get()

        # check that there is a source package file to convert
        store_listing = storage_manager.list(store_id)
        # if current_app.config.get("LOG_DEBUG"):
        #     current_app.logger.debug(f"Storage-mgr: {storage_manager.__class__.__name__}, Store-dir: {storage_manager.dir}, Listing: {store_listing}.")

        # Either store_id doesn't exist or it has no contents
        if not store_listing:
            return []

        # get an instance of the local temp store
        temp_store = store.TempStore()

        # get the packager that will do the conversions
        source_pkg_mgr_class = PackageFactory.get_handler_class(source_format)

        # Set src_stream at an earlier time to avoid issues with the 'finally' block below
        # This is needed to fix packages.py for windows
        src_stream = None
        try:
            # first check the file we want exists
            src_zip_name = source_pkg_mgr_class.zip_name()
            if src_zip_name not in store_listing:
                return []

            # a record of all the conversions which took place, with all the relevant extra info
            conversions = []
            # a record of all the identical files, with relevant extra info
            identical = []

            src_path = None      # path to source package file that will be converted

            # for each target format, load it's equivalent packager to get the storage name,
            # then run the conversion
            for target_format in target_formats:
                target_packager_obj = PackageFactory.get_pkg_mgr(target_format)

                # If target package file format is IDENTICAL to current file format, then no need to create a new file
                if source_pkg_mgr_class.convertible(target_format) == PackageHandler.IDENTICAL:
                    # append the target format name, and the source zip file name
                    identical.append((target_format, src_zip_name))

                # target package format is different, we need to do a real conversion
                else:
                    # This is done ONCE for the first real conversion
                    if not src_stream:
                        # Make a local temporary copy of the package manager's primary file zip file (needed as it may
                        # reside on a different server).
                        # This is done at this point, rather than before the loop as it may never be needed.
                        src_stream = storage_manager.get(store_id, src_zip_name)
                        src_path = temp_store.store(store_id, src_zip_name, source_stream=src_stream)

                    target_zip_name = target_packager_obj.zip_name()
                    # The converted files will be saved initially in the temp local store
                    out_path = temp_store.path(store_id, target_zip_name, must_exist=False)
                    converted = source_pkg_mgr_class.convert(src_path, target_format, out_path)
                    if converted:
                        conversions.append((target_format, target_zip_name))

            # with the conversions completed, copy them to the main storage system from temp local store
            for target_format, target_zip_name in conversions:
                src_stream = temp_store.get(store_id, target_zip_name)
                storage_manager.store(store_id, target_zip_name, source_stream=src_stream)

        except Exception as e:
            current_app.logger.critical(f"Package conversion failed for {msg_snippet}. Error: {str(e)}",
                                        extra={"subject": "Deposited zip package conversion"})
            raise e
        finally:
            try:
                # finally, burn the local copy, ensuring stream is closed before attempting to burn
                if src_stream:
                    src_stream.close()
                    temp_store.delete(store_id)
            except:
                msg = f"Unable to delete '{store_id}' from temporary storage."
                current_app.logger.critical(msg, extra={"subject": "File deletion failed"})
                raise store.StoreException(msg)

        # return details of the conversions and "fake" conversions (target package files same as source package file)
        return conversions + identical


class PackageHandler:
    """
    Interface/Parent class for all objects wishing to provide package handling
    """

    # Convertible types
    CONVERT = 1  # A real conversion from current package file format to target package format is needed
    IDENTICAL = 2  # Current package file format is identical to the target package format (no conversion needed)

    def __init__(self, zip_path=None, metadata_files=None, pub_test=None):
        """
        Construct a new PackageHandler around the zip file and/or the metadata files.

        Metadata file handles should be of the form
        ::
            [("filename", <file handle>)]

        :param zip_path:
        :param metadata_files:
        :param pub_test: Publisher testing object
        :return:
        """
        self.zip_path = zip_path
        self.zip_filename = os.path.basename(zip_path) if zip_path else None
        self.metadata_files = metadata_files
        self.zip = None
        self.pub_test = pub_test or init_pub_testing()    # If pub_test is None then initialise a PubTesting() object

    @classmethod
    def zip_name(cls):
        """
        Get the name of the package zip file to be used in the storage layer

        :return: the name of the zip file
        """
        raise NotImplementedError()

    @classmethod
    def metadata_names(cls):
        """
        Get a list of the names of metadata files extracted and stored by this packager

        :return: the names of the metadata files
        """
        raise NotImplementedError()

    # Methods for retriving data from the actual package

    def metadata_streams(self):
        """
        A generator which yields tuples of metadata file names and data streams

        :return: generator for file names/data streams
        """
        for x in []:
            yield None, None

    def store_package_files(self, storage_manager, store_id):
        """
        Store the package file and separate extracted file streams using supplied storage_manager
        :param storage_manager: Storage manager object
        :param store_id: String or Int - Directory name (aka Storage container identifier)
        :return:
        """
        # store the zip file as-is (with the name specified by the packager)
        storage_manager.store(store_id, self.zip_name(), source_path=self.zip_path)

        # now extract the metadata streams from the package and store them
        for name, stream in self.metadata_streams():
            storage_manager.store(store_id, name, source_stream=stream)

    def notification_metadata(self):
        """
        Get the notification metadata as extracted from the package

        :return: NotificationMetadata populated
        """
        return NotificationMetadata()

    ### NOT USED - as match_data always comes from unrouted.match_data()
    # def match_data(self):
    #     """
    #     Extracts data from the package that is used by the matching (routing) algorithm.
    #
    #     :return: RoutingMetadata object.
    #     """
    #     return RoutingMetadata()

    @classmethod
    def convertible(cls, target_format):
        """
        Can this handler convert to the specified format

        :param target_format: format we may want to convert to
        :return: None or PackageHandler.IDENTICAL or PackageHandler.CONVERT
        """
        return None

    @classmethod
    def convert(cls, in_path, target_format, out_path):
        """
        Convert the file at the specified in_path to a package file of the
        specified target_format at the out_path.

        You should check first that this target_format is supported via convertible()

        :param in_path: locally accessible file path to the source package
        :param target_format: the format identifier for the format we want to convert to
        :param out_path: locally accessible file path for the output to be written
        :return: True/False on success/fail
        """
        return False

    @classmethod
    def format_uri(cls):
        """
        Return the Package format URI (like "https://pubrouter.jisc.ac.uk/FilesAndJATS")
        :return:
        """
        raise NotImplementedError()

    def package_contains_file_type(self, type_suffix):
        """
        Check if package contains a file with particular suffix, return True/False. (E.g. check if PDF is present).
        :param type_suffix: String file suffix (e.g. ".pdf")
        :return: Boolean True/False
        """
        if self.zip_path:
            with ZipFile(self.zip_path) as zip_file:
                for filename in zip_file.namelist():
                    if filename.lower().endswith(type_suffix):
                        return True
        return False

    def package_has_pdf(self):
        return False


class SimpleZip(PackageHandler):
    """
    Very basic class for representing the SimpleZip package format

    SimpeZip is identified by the format identifier http://purl.org/net/sword/package/SimpleZip
    """

    # methods for exposing naming information

    @classmethod
    def format_uri(cls):
        """
        Return the Package format URI
        """
        return "http://purl.org/net/sword/package/SimpleZip"

    @classmethod
    def zip_name(cls):
        """
        Get the name of the package zip file to be used in the storage layer

        In this case it is FileAndJats.zip as it has identical format

        :return: filename
        """
        return "ArticleFiles.zip"

    @classmethod
    def metadata_names(cls):
        """
        Get a list of the names of metadata files extracted and stored by this packager

        In this case there are none

        :return: list of names
        """
        return []

    def package_has_pdf(self):
        return self.package_contains_file_type(".pdf")


class FilesAndJATS(PackageHandler):
    """
    Class for representing the FilesAndJATS format

    You should use the format identifier: https://pubrouter.jisc.ac.uk/FilesAndJATS

    This is the default format that we currently prefer to get from
    providers.  It consists of a zip of a single XML file which is the JATS fulltext,
    a single PDF which is the fulltext, and an arbitrary number of other
    files which are supporting information.

    To be valid, the zip must contain the JATS file.
    All other files are optional
    """

    def __init__(self, zip_path=None, metadata_files=None, pub_test=None):
        """
        Construct a new PackageHandler around the zip file and/or the metadata files.

        Metadata file handles should be of the form

        ::

            [("filename", <file handle>)]

        :param zip_path: locally accessible path to zip file
        :param metadata_files: metadata file handles tuple
        :param pub_test: Publisher testing object
        :return:
        """
        super(FilesAndJATS, self).__init__(zip_path=zip_path, metadata_files=metadata_files, pub_test=pub_test)

        self.format = "https://pubrouter.jisc.ac.uk/FilesAndJATS"
        self.jats = None    # will store JATS metadata loaded from file

        if self.zip_path is not None:
            self._process_zip_load_jats_xml()
        elif self.metadata_files is not None:
            self._load_jats_xml_from_metadata_file()

    # Overrides of methods for exposing naming information

    def package_has_pdf(self):
        # If Zipfile has already been processed, we can avoid reopening it
        if self.zip:
            return self._filenames_of_type(".pdf") != []
        else:
            return self.package_contains_file_type(".pdf")

    @classmethod
    def format_uri(cls):
        """
        Return the Package format URI
        """
        return "https://pubrouter.jisc.ac.uk/FilesAndJATS"

    @classmethod
    def zip_name(cls):
        """
        Get the name of the package zip file to be used in the storage layer

        In this case FilesAndJATS.zip

        :return: filname
        """
        return "ArticleFilesJATS.zip"

    @classmethod
    def metadata_names(cls):
        """
        Get a list of the names of metadata files extracted and stored by this packager

        In this case ["filesandjats_jats.xml"]

        :return: list of metadata files
        """
        return ["filesandjats_jats.xml"]


    # Over-rides of methods for retriving data from the actual package

    def metadata_streams(self):
        """
        A generator which yields tuples of metadata file names and data streams

        In this handler, this will yield up to 1 metadata streams; for "filesandjats_jats.xml",
        in that order, where there is a stream present for that file.

        :return: generator for file names/data streams
        """
        sources = [("filesandjats_jats.xml", self.jats)]
        for name, jats_data in sources:
            if name is not None:
                yield name, BytesIO(jats_data.to_byte_str())

    def notification_metadata(self):
        """
        Get the notification metadata as extracted from the package

        This will extract metadata from the JATS XML.

        :return: NotificationMetadata populated
        """

        # extract all the relevant data from jats
        if self.jats is not None:
            return self._jats_metadata()

        return None

    @classmethod
    def convertible(cls, target_format):
        """
        Checks whether this handler can do the conversion to the target format.

        This handler currently supports the following conversion formats:

        * http://purl.org/net/sword/package/SimpleZip

        :param target_format: target format
        :return: Type of conversion: None or PackageHandler.IDENTICAL or PackageHandler.CONVERT
        """
        convertible_formats = {
            # SimpleZip package file format is identical to FileAndJATS file format
            "http://purl.org/net/sword/package/SimpleZip": PackageHandler.IDENTICAL
        }
        return convertible_formats.get(target_format)

    @classmethod
    def convert(cls, in_path, target_format, out_path):
        """
        Convert the file at the specified in_path to a package file of the
        specified target_format at the out_path.

        You should check first that this target_format is supported via convertible()

        This handler currently supports the following conversion formats:

        * http://purl.org/net/sword/package/SimpleZip

        :param in_path: locally accessible file path to the source package
        :param target_format: the format identifier for the format we want to convert to
        :param out_path: locally accessible file path for the output to be written
        :return: True/False on success/fail
        """
        if target_format == "http://purl.org/net/sword/package/SimpleZip":
            cls._simple_zip(in_path, out_path)
            return True
        return False

    # Internal methods

    @classmethod
    def _simple_zip(cls, in_path, out_path):
        """
        convert to simple zip

        :param in_path:
        :param out_path:
        :return:
        """
        # files and jats are already basically a simple zip, so a straight copy
        shutil.copyfile(in_path, out_path)

    def _jats_metadata(self):
        """
        Extract metadata from the JATS file

        :return: NotificationMetadata object
        """
        try:
            md = NotificationMetadata()

            # Journal Title, Publiser, Issue, Volume, Identifiers
            md.journal_title = self.jats.journal_title
            md.journal_abbrev_title = self.jats.abbrev_journal_title
            md.add_journal_publisher(self.jats.journal_publisher)
            tmp = self.jats.journal_issue
            if tmp:
                md.journal_issue = tmp

            tmp = self.jats.journal_volume
            if tmp:
                md.journal_volume = tmp

            for issn in self.jats.issn_tuples:
                md.add_journal_identifier(issn[0], issn[1])

            # Article Type, Title, Identifiers
            md.article_type = self.jats.article_type

            # Article language or default to english
            md.article_language = self.jats.article_language.lower() or "en"

            md.article_title = self.jats.article_title
            for txt in self.jats.article_subtitles:
                md.add_article_subtitle(txt)

            # Identifiers
            for art_id in self.jats.article_id_tuples:
                # art_id is tuple of form: (type, id)
                md.add_article_identifier(art_id[0], art_id[1])

            # Article Abstract
            tmp = self.jats.article_abstract
            if tmp:
                md.article_abstract = tmp

            # Page information
            (first_page, last_page, page_range, e_num) = self.jats.page_info_tuple
            if first_page:
                md.article_start_page = first_page

            if last_page:
                md.article_end_page = last_page
                if first_page:
                    try:
                        md.article_num_pages = int(last_page) - int(first_page) + 1
                    except:
                        # Sometimes page numbers include alphabetic chars, so ignore int conversion exception
                        pass
                    
            if page_range:
                md.article_page_range = page_range

            if e_num:
                md.article_e_num = e_num

            # Subject values
            kw_list = self.jats.keywords
            if kw_list:
                # Remove duplicates
                md.article_subject = list(set(kw_list))

            # Authors
            self._add_authors_contribs(md, self.jats.authors, is_author=True)
            # Contributors
            self._add_authors_contribs(md, self.jats.contributors, is_author=False)

            # List of history dates and best publication date we can find.
            history_dates, pub_date = self.jats.get_history_and_pub_dates()

            if pub_date is not None:
                # Set Publication date (metadata.publication_date) and Publication status (metadata.publication_status)
                md.set_publication_date_format(pub_date['date'],
                                               pub_date['publication_format'],
                                               pub_date['year'],
                                               pub_date['month'],
                                               pub_date['day'])

            # Various dates
            for history_date in history_dates:
                md.add_history_date_obj(history_date)

                # If this is the "Accepted" date
                if history_date.get("date_type").lower() in ('accepted', 'am', 'aam'):
                    md.accepted_date = history_date.get("date")

            # Grant Funding
            md.funding = self.jats.grant_funding

            article_version, licenses = self.jats.get_licence_and_article_version_details()
            if article_version is not None:
                md.article_version = article_version
            #  Licensing
            for lic in licenses:
                md.set_license(url=lic['url'], type=lic['type'], title=lic['title'], start=lic['start'])

            # Acknowledgements
            tmp = self.jats.ack
            if tmp:
                md.ack = tmp

        except InvalidJATSError as e:
            raise PackageException(f"Problem processing JATS metadata: {str(e)}") from e

        return md

    @staticmethod
    def _add_authors_contribs(md, contrib_list, is_author=True):
        """
        Add authors or contributors to Notification metadata object
        :param md: Notification metadata object (will be UPDATED by this function)
        :param contrib_list: list of contributors (authors or collaborators) to extract data
        :param is_author: Boolean True if adding Authors, False if adding Contributors
        :return: Nothing - but new authors or contributors are added to the Notification metadata object
        """
        for contrib in contrib_list:
            md_contrib = {"type": contrib["type"]}   # contrib ALWAYS has a "type" key

            # Should be either a surname or an org_name
            surname = contrib.get("surname")
            if surname:
                md_contrib["name"] = NotificationMetadata.make_name_dict(contrib.get("firstname"),
                                                                         surname,
                                                                         suffix=contrib.get("suffix"))
            else:
                org_name = contrib.get("org_name")
                if org_name:
                    md_contrib["organisation_name"] = org_name
                else:   # Should never happen - as would have an author without a name of any kind
                    continue

            id_tuples = contrib.get("id_tuples", [])
            emails = contrib.get("emails", [])
            if id_tuples or emails:
                md_contrib["identifier"] = []

                # author/contributor id_tuples = [ (id-type, id), (...),... ]
                for id_tuple in id_tuples:
                    md_contrib["identifier"].append({"type": id_tuple[0], "id": id_tuple[1]})

                # Now add any emails as identifiers
                for e in emails:
                    md_contrib["identifier"].append({"type": "email", "id": e})

            affs = contrib.get("affiliations")
            if affs:
                md_contrib["affiliations"] = affs

            if is_author:
                # If corresponding author (NB "corresp" key is always present), reset type from "author" to "corresp"
                if contrib["corresp"]:
                    md_contrib["type"] = "corresp"
                md.add_author(md_contrib)
            else:
                md.add_contributor(md_contrib)

    def _load_jats_xml_from_metadata_file(self):
        """
        Load JATS XML from a metadata file, setting self.jats to an etree representation of the XML

        :return: Nothing, but sets self.jats
        """
        for name, stream in self.metadata_files:
            if name == "filesandjats_jats.xml":
                try:
                    xml_etree = etree.fromstring(stream.read())
                    self._set_jats(xml_etree)
                except Exception:
                    msg = "Unable to parse 'filesandjats_jats.xml' file from store"
                    self.pub_test.log(ERROR, msg, save=False)
                    raise PackageException(msg)
            elif name == "filesandjats_epmc.xml":
                # This option has been removed
                msg = "File format of 'filesandjats_epmc.xml' is not supported"
                self.pub_test.log(ERROR, msg, save=False)
                raise PackageException(msg)

        if self.jats is None:
            msg = f"No JATS metadata found in metadata files: {[fname for fname, s in self.metadata_files]}"
            self.pub_test.log(ERROR, msg, save=False)
            raise PackageException(msg)


    def _raise_pkg_exception(self, xml_file, err_type, err, e):
        msg = f"Unable to parse XML file '{xml_file}'. {err_type}: {err}"
        self.pub_test.log(ERROR, f"{msg}. From zip: {str(self.zip_path)}.", save=False)
        raise PackageException(msg) from e


    def _process_zip_load_jats_xml(self):
        """
        Load JATS XML from a zip file, setting self.jats to an etree representation of the XML

        :return: Nothing, but sets self.jats
        """
        try:
            self.zip = ZipFile(self.zip_path, "r", allowZip64=True)
        except BadZipfile as e:
            err = str(e)
            self.pub_test.log(ERROR, f"Cannot read zip file: {str(self.zip_path)} ({err})", save=False)
            raise PackageException(f"Cannot read zip file - {err}") from e

        for xml_file in self._filenames_of_type(".xml"):
            try:
                xml_binary_str = self.zip.open(xml_file).read()
            except Exception as e:
                self._raise_pkg_exception(xml_file, "Read Error", repr(e), e)

            # Test if XML file has root element of <article>
            has_article_root = regex_root_article.match(xml_binary_str)
            if not has_article_root:
                continue    # Not a JATS file, so CONTINUE with next XML file (if there is one)

            # Some publishers (wrongly) include a namespace definition for root JATS  <article>
            # element (i.e. <article xmlns="something" …>).  We need to remove that in order for our logic to work.

            # Search for 'xmlns=' in xml_binary_str starting at the character after '<article'
            article_end_offset = has_article_root.end(1)
            has_xmlns = regex_xmlns_in_element.match(xml_binary_str[article_end_offset:])
            if has_xmlns:
                # Adjust xml_binary_str to exclude the matched 'xmlns=....' string by combinging 2 slices
                xml_binary_str = xml_binary_str[:article_end_offset + has_xmlns.start(1)] + xml_binary_str[article_end_offset + has_xmlns.end(1):]

            etree_root = None
            try:
                etree_root = etree.fromstring(xml_binary_str)
            except etree.XMLSyntaxError as e:
                # There were problems with parsing the XML - use the recover parser and unescape html entities
                # returning value as byte-string to see if we can now parse it
                try:
                    etree_root = etree.XML(
                        decode_non_xml_html_entities(xml_binary_str, return_as=UTF8_BYTES),
                        etree.XMLParser(recover=True, encoding="utf-8")
                    )
                except Exception as ee:
                    e = ee  # Overwrite original exception value

                err = str(e)
                if etree_root is None:
                    self._raise_pkg_exception(xml_file, "Syntax Error", err, e)
                else:
                    self.pub_test.log(WARNING,
                                      f"Unable to parse XML file '{xml_file}' on 1st attempt, succeeded after 2nd. Syntax Error: {err}.")

            except Exception as e:
                self._raise_pkg_exception(xml_file, "UNEXPECTED Error", repr(e), e)

            # If we get this far then we have parsed valid XML
            # JATS files have <article> as the root element
            if etree_root.tag == "article":
                self._set_jats(etree_root)
                break   # We have found JATS XML, so no need to look at other XML files

        if self.jats is None:
            msg = "No JATS metadata found in package"
            self.pub_test.log(ERROR,  f"{msg}: {str(self.zip_path)}", save=False)
            raise PackageException(msg)

        self.zip.close()

    def _filenames_of_type(self, type_suffix):
        """
        List the XML files in the zip file
        :param type_suffix: String - File suffix like ".xml" or ".pdf"
        :return: List of XML filenames
        """
        return [name for name in self.zip.namelist() if name.lower().endswith(type_suffix)] if self.zip else []

    def _set_jats(self, xml_etree):
        """
        Set the local JATS property on this object based on the xml document passed in
        :param xml_etree: XML in etree object form
        :return:
        """
        self.jats = JATS(xml=xml_etree)


class FTPZipFlattener:
    """
    Class for flattening FTP deposits in an input ZIP file into a particular directory/file structure:

        ./*.xml - XML files that were found in the same directory as the first xml file found in zip file.
        ./*.pdf - PDF files that were found in same directory as the first xml file found in zip file.
        ./additional-files.zip - All files other than the XML and PDF files that exist at the first level
                    this will have same directory hierarchy as the input zip file.

    An FTP deposited notification must be in a zip file which has contents conforming to certain rules -
    notably it must have JATS XML file (and any article PDFs) at the top or first level -
    see WORD doc "FTP Deposit Protocol for New Publishers" for more details.

    If a zip file is NOT found in the directory (passed as param to FTPZipFlattener) then any files in that directory are
    simply zipped up without any analysis - in that case the ZIP file will not necessarily have the above structure.

    PackageException will be raised if a Zip file is found that is empty, contains no XML file or more than one XML file
    in the first directory encountered that contains any XML file.

    Calling convention:
        flattener = FTPZipFlattener( directory_containing_zipfile_to_flatten, pub_test)

    Methods available:
        * process_and_zip(...) - the main function, it walks a directory looking for a zip file containing an XML file;
                                if found then creates a zip file with the above structure; if no XML file found in zip,
                                or more than 1 XML file found at same level then Exception is raised; if no Zip found
                                it just creates a zip of directory contents as found.
        * extract_xml_pdf_rebundle_zip_or_do_nothing(...) - used by above method: walks the directory, looking for zip file
                                with an XML file (may raise exceptions described above); if found it extracts XML and PDF
                                files, zipping up the remaining files in 'additional-files.zip'; if no zip is found it
                                leaves files as they were.
        * zip_directory(...) - creates a new zip file, optionally deleting source files afterwards.
    """

    ADDITIONAL_FILES_ZIP = "additional-files.zip"

    def __init__(self, dir_, pub_test, max_zip_size=None, large_zip_size=None):
        """
        Simply set the directory we want to flatten.

        :param dir_: Directory containing zip file to flatten
        :param pub_test: Publisher testing object
        :param max_zip_size: Int - Maximum size (BYTES) of zipfile that will be accepted for processing or None
        :param large_zip_size: Int - Size (BYTES) of zipfile that is considered worthy of maximum compression or None
        """
        self.dir = dir_
        self._config = current_app.config
        self.compression = self._config.get('ZIP_COMPRESSION', ZIP_STORED)
        self.reqd_compression_level = self._config.get('ZIP_STD_COMPRESS_LEVEL')    # None --> Default compression level
        self.pub_test = pub_test
        self.max_zip_size = max_zip_size
        self.large_zip_size = large_zip_size

    def _full_path(self, *args):
        """
        Wrapper for os.path.join with self.dir as the first argument

        :param *args: List of paths to join with self.dir

        :return: arguments path joined with self.dir
        """
        return os.path.join(self.dir, *args)

    def _write_file_from_zip_to_top_level(self, filename, zip_file, zip_info):
        """
        Extract a file with a given filename from input zip file and write to self.dir directory.

        :param filename: Name of file (not a path)
        :param zip_file: ZipFile instance - from where the required file will be extracted
        :param zip_info: ZipInfo instance - describing the required file (used for reading data from the zip_file).
        """
        # Replace space characters in filename by underscore (to fix problem with  SWORD deposits in DSpace)
        if " " in filename:
            self.pub_test.log(INFO,
                f"Spaces replaced by underscores in filename: '{filename}' while processing FTP zip directory: {self.dir}")
            filename = filename.replace(" ", "_")

        with open(self._full_path(filename), "wb") as new_file:
            new_file.write(zip_file.read(zip_info))

    def _extract_rebundle_then_delete_zip(self, input_zip_path):
        """
        Walk the input zip file to extract JATS XML and article PDF files, and to write remaining content to an
        'additional-files.zip' file.

        Starting at the top level, the directories in the Zip file are successively processed,
        looking for PDF or XML files which are extracted and written to the top level directory.
        Once an XML file has been found, then the extraction of PDF and XML files ceases for all lower directories.
        All other files encountered (including any PDF and XML in lower directories)
        are written to an 'additional-files.zip' file.

        Finally, the input zip file is deleted.


        PROCESSING RULES for each directory level in the zip file

        If an XML file was not found in any previous directory level:
            1. Extract and write all XML or PDF files in the current directory to self.dir (top level)
            2. Extract and write all other files to the `additional-files.zip` with their original paths and filenames.
        If an XML file has been found in a previous directory:
            1. Extract and write all files to the `additional-files.zip` with their original paths and filenames.

        :param input_zip_path: Path to the input zip file we want to process
        """
        additional_files_zip_path = self._full_path(self.ADDITIONAL_FILES_ZIP)
        # If we don't actually have any files in the zip, we'll want to delete it at the end of the loop.
        has_additional_files = False
        # Create `additional-files.zip` file
        in_zip_fname = os.path.basename(input_zip_path)
        with ZipFile(
                additional_files_zip_path,
                "w",
                compression=self.compression,
                compresslevel=self.reqd_compression_level
        ) as additional_files_zip:

            # Open the input zip file
            with ZipFile(input_zip_path) as input_zip_file:

                collect_xml_and_pdf = True  # While True, XML and PDF files will be extracted to top level directory
                xml_found_at_depth = None   # Stores the directory level at which first XML is found
                pdf_found = False
                xml_at_same_depth = 0       # Count of xml files at same depth, which gives rise to Warning
                # We must sort the infolist in hierarchy order, as zip files data does not have to be in directory
                # order as you would expect in a folder.
                for zip_info in sorted(input_zip_file.infolist(), key=lambda zip_info: zip_info.filename.count("/")):
                    full_path = zip_info.filename
                    if full_path.endswith("/"):
                        # This is a directory - don't write to a zip
                        continue

                    filename = os.path.basename(full_path)
                    lower_filename = filename.lower()

                    if not pdf_found and lower_filename.endswith(".pdf"):
                        pdf_found = True

                    if collect_xml_and_pdf:
                        if xml_found_at_depth is not None:
                            # If there are more "/" in the full_path, we're now in a directory below that where
                            # the XML was found.
                            if full_path.count("/") > xml_found_at_depth:
                                # All XML and PDF files found in the first directory that contained an XML file
                                # have been copied to the top level
                                # Any further XML or PDF files found in lower-level directories are to be copied
                                # into the additional_files_zip file.
                                collect_xml_and_pdf = False

                    # If collecting XML or PDF, and XML file
                    if collect_xml_and_pdf and lower_filename.endswith(".xml"):
                        self._write_file_from_zip_to_top_level(filename, input_zip_file, zip_info)
                        xml_directory = os.path.dirname(full_path)
                        # if we've already found an XML file at this depth then log a warning or raise exception
                        if xml_found_at_depth is not None:
                            # This XML file found in same directory as last XML file
                            if xml_directory == last_xml_directory:
                                xml_at_same_depth += 1
                            else:
                                if xml_at_same_depth:
                                    msg = f"{xml_at_same_depth + 1} XML files were found at same depth of directory structure in '{in_zip_fname}'"
                                    self.pub_test.log(WARNING, msg, suffix=f" Zip path: {input_zip_path}")
                                # Need to raise exception, because if it is an Atypon file the result of repackaging
                                # would be to coalesce all article PDFs and JATS XMLs into a single directory
                                msg = f"Possible Atypon file: More than 1 XML file at same depth, but in different directories in '{in_zip_fname}'."
                                raise PackageException(msg)

                        # Set the depth so we can stop collecting files in future iterations
                        xml_found_at_depth = full_path.count("/")
                        last_xml_directory = xml_directory

                    # If collecting XML or PDF, and is a PDF file
                    elif collect_xml_and_pdf and lower_filename.endswith(".pdf"):
                        self._write_file_from_zip_to_top_level(filename, input_zip_file, zip_info)

                    # Otherwise, write file to `additional-files.zip` file
                    else:
                        # Note that we actually have files in the additional-files.zip
                        has_additional_files = True
                        additional_files_zip.writestr(full_path, input_zip_file.read(zip_info))

            if xml_at_same_depth:
                ## No need to raise exception, as a later process will check all XML files for JATS file
                msg = f"{xml_at_same_depth + 1} XML files were found at same depth of directory structure in '{in_zip_fname}'"
                self.pub_test.log(WARNING, msg, suffix=f" Zip path: {input_zip_path}")

            # If no XML files were found raise an exception
            pkg_error = []
            if xml_found_at_depth is None:
                pkg_error = ["no XML file"]
            # Check for missing PDF is now done elsewhere
            # if not pdf_found:
            #     pkg_error.append("no PDF file")
            if pkg_error:
                err = ' and '.join(pkg_error)
                err = err[0].capitalize() + err[1:]     # Capitalise first letter
                raise PackageException(f"{err} in zip file '{in_zip_fname}'.")

            # Lastly, delete the input zip file
            os.remove(input_zip_path)

        # If there are no files in the additional-files.zip, remove the zip.
        if not has_additional_files:
            os.remove(additional_files_zip_path)

        if not os.listdir(self.dir):
            raise PackageException(f"The zip file '{in_zip_fname}' was empty")

    def extract_xml_pdf_rebundle_zip_or_do_nothing(self):
        """
        Process the current directory, which involves walking the directory structure until a zip file is found.

        IMPORTANT: It is assumed that the first zip file contains the notification, comprising at least a JATS XML file.

        That zip file is processed to extract XML and any article PDF file(s).  Any other files are bundled into
        'additional-files.zip' file.

        The logic is intended to extract XML and PDF found at the first level where an XML file occurs. Any XML or PDF
        files appearing at lower directory levels are not extracted, but are bundled into 'additional-files.zip' file.

        RETURN:

        If a Zip file was found then the self.dir directory will contain ONLY:
            * 1 or more XML file,
            * zero or more PDF files,
            * zero or one 'additional-files.zip' file.

        If no zip file was found, then self.dir remains unchanged.

        PackageException - will be raised if found Zip file is empty, or contains no XML file or more than one XML file
        in the first directory found that contains any XML file.
        """
        def _get_first_zipfile():
            """
            Return pathname of first Zip file found in directory
            @return: None or Zip path name
            """
            # Recurse over the directory until we find a zip
            for path, dirs, filenames in os.walk(self.dir):
                for filename in filenames:
                    if filename.lower().endswith(".zip"):
                        return os.path.join(path, filename)
            return None

        zip_path = _get_first_zipfile()
        if zip_path:
            file_size = os.path.getsize(zip_path)
            # Test if maximum permitted file size exceeded (this necessary because processing oversized zip files
            # can result in Out of Memory server failure.
            if self.max_zip_size and file_size > self.max_zip_size:
                raise PackageException(
                    f"Zip file too large ({file_size} bytes); maximum allowed is {self.max_zip_size} bytes")

            # For large files we use maximum compression to avoid risk of creating a bigger zip file than we started with that may then exceed the system limits
            if self.large_zip_size and file_size > self.large_zip_size:
                self.reqd_compression_level = self._config.get('ZIP_XTRA_COMPRESS_LEVEL', 9)

            # Do the PDF & XML filextraction, and save remainder of input zip file in an 'additional-files.zip' file
            self._extract_rebundle_then_delete_zip(zip_path)

            # Delete leftover directories afterwards
            for path in os.listdir(self.dir):
                full_path = self._full_path(path)
                if os.path.isdir(full_path):
                    shutil.rmtree(full_path)
        # At this point = if a zip file was found & successfully processed, self.dir will contain ONLY:
        #    1 or more XML files, 0 or more PDF files, 0 or 1 Zip file

    def zip_directory(self, save_path, delete_files_on_zip):
        """
        Zip just self.dir - can be used directly if things go wrong to zip the directory when partially flattened.
        So, if an exception is raised by flatten, it can be caught by the calling code then the partially flattened
        directory can be zipped by this function.

        :param save_path: full path to where the new zip should be saved - like /path/to/dir/filename
        :param delete_files_on_zip: Boolean - Whether to delete the files when they have been zipped.
        """
        paths_to_zip = os.listdir(self.dir)
        with ZipFile(save_path, "w", compression=self.compression, compresslevel=self.reqd_compression_level) as zip_file:
            for path in paths_to_zip:
                full_path = self._full_path(path)
                # Write the file at location full_path to location path in the zip file.
                zip_file.write(full_path, path)

                if delete_files_on_zip:
                    os.remove(full_path)

    def process_and_zip(self, save_path=None, delete_files_on_zip=None):
        """
        Process the directory and then create a zip file of the processed directory.

        Processing the directory will convert the first found zip file in the directory to the format described
        in the class description.

        :param save_path: Full path to where the new zip should be saved - like /path/to/dir/filename
        :param delete_files_on_zip: Boolean - Whether to delete the files when they have been zipped.
        """
        # Look for a zip file, and if found extract XML, PDFs and create an 'additional-files.zip' file, then remove
        # original zip; if no zip then leave directory alone.
        self.extract_xml_pdf_rebundle_zip_or_do_nothing()
        if not save_path:
            save_path = "ArticleFilesJATS.zip"

        # If self.dir is not empty (listdir returns a non-empty list)
        if os.listdir(self.dir):
            # zip it up, and delete all but the new zip file.
            self.zip_directory(save_path, delete_files_on_zip)
