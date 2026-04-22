"""
Unpacked.py

Contains 3 classes:
- UnpackUtil : a factory class for repackaging a set of packaged files
- UnpackZipHandler : class for repackaging a standard zip file
- UnpackEprintsRioxx : specific implementation that separates PDF files from a zip package, with non-PDF files left
    in the zip file

Purpose of these classes is to dis-aggregate the contents of a zip file, for example: converting a single zip file
containing PDF, meta-data, image files into a set of separate PDF files and a "left-overs" zip file containing the rest.
The new set of files will be saved in a new folder.

General functionality: filters zips, unpacks some files and repacks others.

(In hindsight may be better to think of this as repackaging rather than unpacking).
"""

from contextlib import contextmanager
from flask import current_app
from io import BytesIO
from zipfile import ZipFile, ZIP_STORED
from octopus.lib.files import guess_mimetype
from octopus.lib.plugin import load_class
from octopus.modules.store import store

import os

# Map used for deciding which unpackaging handler to use for particular format
UNPACKING_HANDLERS = {
    "https://pubrouter.jisc.ac.uk/PDFUnpacked": "router.jper.unpacked.UnpackEprintsRioxx"
}



class UnpackUtil:
    unpacked_handler_dict = UNPACKING_HANDLERS

    @classmethod
    def unpacker(cls, note_id, source_zip_name, unpacked_formats):
        """
        Very similar to packages.PackageManager.converter.

        Takes a list of formats, and unpacks using the classes that correspond to the unpacked_formats.

        Unpacking is removing some files from a zip and storing them so they can be accessed directly.

        :param note_id: Notification id
        :param source_zip_name: Name of source Zipfile (that will be retrieved from store for processing)
        :param unpacked_formats: list of unpack URIs similar to the package URIs.

        Example: https://pubrouter.jisc.ac.uk/PDFUnpacked
        :return: List of link metadata dicts from all the converted formats we find.
        """
        config_formats = cls.unpacked_handler_dict
        link_dict_list = []
        for format in unpacked_formats:
            class_path = config_formats.get(format)
            if class_path is None:
                current_app.logger.error(f"Unpack format {format} does not exist.")
                raise ImportError(f"No class path for unpack format {format}")
            # unpacker_class = load_class_raw(class_path)
            unpacker_class = load_class(class_path)
            if unpacker_class:
                # unpacked_pkg - an initialised child class of UnpackZipHandler.
                # IMPORTANT: initialisation of unpacker_class actually performs the Unpacking
                unpacked_pkg = unpacker_class(note_id, source_zip_name)
                # At this point the unpacking will have occurred
                link_dict_list += unpacked_pkg.construct_link_metadata_list()
            else:
                current_app.logger.error(f"Unpack class path {class_path} for format {format} is not a class")
                raise ImportError(f"No class for class path {class_path} with format {format}")
        return link_dict_list


class UnpackZipHandler:
    zip_format = "http://purl.org/net/sword/package/SimpleZip"

    def __init__(self, note_id, source_zip_name, zip_compression=ZIP_STORED, folder="Unpacked",
                 new_zip_name="remaining.zip"):
        """
        Init method - Will unpack files in the supplied Zipfile using "filter/rules" in the _unpack method.
        The result of this process will be to produce a set of unpacked files plus a NEW zip-file (self.zip_name) which
        contains the remaining files from the source (input) zip file which do not need unpacking.

        :param note_id: Notification id relevant to the store location.
        :param source_zip_name: Zip name that we are finding inside the store to unpack. (Probably FilesAndJATS.zip)
        :param zip_compression: Level of compression to apply to new Zip files (ZIP_STORED = No compression,
                            ZIP_DEFLATED = Compression)
        :param folder: The folder the new files will be located, in /<note_id/<folder>/remaining.zip etc
        :param new_zip_name: file name that the new zip will be called when it is stored.
        """

        # super(UnpackZipHandler, self).__init__()
        self.app_config = current_app.config
        self.source_zip_name = source_zip_name
        self.zip_name = new_zip_name  # Name of new zip file that will store files from source_zip that are not unpacked
        self.store_id = note_id
        self.folder = folder
        self.storage_manager = store.StoreFactory.get()
        self.temp_store = store.TempStore()
        self.zip_compression = zip_compression
        self.zip_compresslevel = self.app_config.get('ZIP_STD_COMPRESS_LEVEL')  # If None, then ZipFile uses a default

        if not self.storage_manager.container_exists(self.store_id):  # XXXX
            raise ValueError("Store location for UnpackagedFiles not found")

        # Save the source_zip file in temporary storage
        self.source_zip_path = self.temp_store.store(
            self.store_id, self.source_zip_name,
            # Retrieve source Zip file (by name) from the store (defined by store_id)
            source_stream=self.storage_manager.get(self.store_id, self.source_zip_name)
        )
        # Unpack the source zipfile,
        self.file_dicts = self._unpack()

        # Delete the source zip file from temporary storage
        self.temp_store.delete(self.store_id)

    def zip_name(self):
        return self.zip_name

    @contextmanager
    def _get_source_zip(self):
        """
        Simple safe file open for the temporary zip file

        :return: ZipFile object
        """
        try:
            zip_file = ZipFile(self.source_zip_path, 'r')
            yield zip_file
        finally:
            zip_file.close()

    def _create_file_dict(self, file_name, file_mimetype):
        """
        Create file_dict objects like they should be in metadata.

        :param file_name: File name of file that now has a link
        :param file_mimetype: mimetype of file

        :return: Dictionary {'file': <file-name>, 'format': <file mime-type>}
        """
        return {"file": file_name, "format": file_mimetype}

    def _file_dict_to_link_dict(self, file_dict):
        """
        Create a link dict from file_dict.

        :param file_dict: File dict like the one created by _create_file_dict.
        :return: Link dict.
        """
        file = file_dict.get("file")
        link_dict = {
            # 'unpackaged' type is something of a "hack" to stop links to zip files created by the repackaging process
            # being treated as links to "normal" packaged files.
            "type": "unpackaged",
            "format": file_dict.get("format"),
            # 'special' access indicates file is intended to be pulled by receiving repository rather than pushed
            "access": "special",
            "cloc": os.path.join(self.folder, file)
        }
        if file.endswith(".zip"):
            link_dict["packaging"] = self.zip_format
        return link_dict

    def _filter_zip_and_unpack(self, filter_func, new_zip_stream):
        """
        Filter each file within the source (input) zip using the filter function, and either unpack it (by saving as
        a separate file) or copy it into the new "remaining.zip" file which holds those files not unpacked.

        :param filter_func: Filter condition function that works on zip_info data
            If filter_func returns False, the file argument will be added to 'remaining.zip'.
            Otherwise, it will store the file separately.
        :param new_zip_stream: zipFile.ZipFile object to be written to

        :return: List of file dicts as created by _create_file_dict. These will only be files that have been unpacked.
        """
        files = []
        with self._get_source_zip() as package_zip:
            for zip_info in package_zip.infolist():
                file_name = zip_info.filename
                file_as_bytes_string = package_zip.read(file_name)
                # If filter_func(zip_info) returns True, unpack - otherwise add to new zip.
                if filter_func(zip_info):
                    file_path = os.path.join(self.folder, file_name)
                    self.storage_manager.store(self.store_id, file_path, source_data=file_as_bytes_string)
                    files.append(self._create_file_dict(file_name, guess_mimetype(file_name)))
                    if self.app_config.get("LOG_DEBUG"):
                        current_app.logger.debug(f"Special unpacking - Saved unpacked file: {file_path}")
                else:
                    new_zip_stream.writestr(zip_info, file_as_bytes_string)
                    if self.app_config.get("LOG_DEBUG"):
                        current_app.logger.debug(f"Special unpacking - Added file to {self.zip_name}: {file_name}")
        return files

    def _unpack_by_filter(self, zipinfo_filter_func=lambda x: True):
        """
        Unpack zip by a given filter_func - any file that returns True will be stored seperately.
        Any that return False will be stored in a zip file.

        :param zipinfo_filter_func: Any one argument function that returns True or False. Will be passed separate
            ZipInfo objects - https://docs.python.org/2/library/zipfile.html#zipinfo-objects

        :return List of file_dicts {'file': <file-name>, 'format': <file mime-type>}, one for each unpacked file plus
                the new zip file (holding files not unpacked)
        """
        new_zip_bytes_io_buffer = BytesIO()
        new_zip_stream = ZipFile(new_zip_bytes_io_buffer,
                                 "w",
                                 compression=self.zip_compression,
                                 compresslevel=self.zip_compresslevel)
        new_zip_path = os.path.join(self.folder, self.zip_name)
        # The first file returned listed is the zipfile containing those items NOT unpacked from the original zipfile
        files = [self._create_file_dict(self.zip_name, "application/zip")]

        # Filter zip and unpack files we want unpacked
        files = files + self._filter_zip_and_unpack(zipinfo_filter_func, new_zip_stream)

        # Close the new zipfile and return file pointer to start of file buffer
        new_zip_stream.close()
        new_zip_bytes_io_buffer.seek(0)

        # Save the new zip file
        self.storage_manager.store(self.store_id, new_zip_path, source_stream=new_zip_bytes_io_buffer)
        return files

    def _unpack(self):
        """
        This will unpack and should return file_dicts (in the same format as the _create_file_dict below), which
        will then set the 'self.file_dicts' attribute.

        """
        return NotImplementedError

    def construct_link_metadata_list(self):
        """
        Construct list of link metadata for all of the files this class has generated.

        Link metadata is most of a Notification link object, like so:
            {
                "cloc": "partial-path/to/file",
                "format": "",
                "access": "",
                "type": "",
                "packaging": "" [OPTIONAL element, may be absent]
            }
        :return List of link dicts
        """
        return [self._file_dict_to_link_dict(file_dict) for file_dict in self.file_dicts]


class UnpackEprintsRioxx(UnpackZipHandler):

    def __init__(self, note_id, source_zip_name):
        """
        Unpacks all pdf files and creates a new zip without PDF files inside the eprints-rioxx directory for note_id.

        :param note_id: Notification id relevant to the store location.
        :param source_zip_name: Zip name that we are finding inside the store to unpack. (Probably FilesAndJATS.zip)
        """
        super(UnpackEprintsRioxx, self).__init__(note_id,
                                                 source_zip_name,
                                                 current_app.config.get('ZIP_COMPRESSION', ZIP_STORED),
                                                 "eprints-rioxx",
                                                 "non-pdf-files.zip")

    def _unpack(self):
        """
        Simple implementation of _unpack - Will unpack from the source zipfile those files with names ending ".pdf.",
        the remaining files will be zipped into "non-pdf-files.zip".

        :return: List of file_dicts {'file': <file-name>, 'format': <file mime-type>}, one for each unpacked file plus
                the new non-pdf-files.zip file
        """
        # The lambda filter function must operate on zip_info data and return True/False
        return self._unpack_by_filter(lambda zip_info: zip_info.filename.endswith(".pdf"))
