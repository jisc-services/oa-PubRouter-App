"""
Fixtures for testing packages
"""
import uuid
import os, codecs
from io import StringIO
from shutil import copy as file_copy
from zipfile import ZipFile, ZIP_STORED
from octopus.lib.paths import rel2abs
from octopus.modules.store import store
from tests.jper_tests.fixtures.models import JATSFactory
from router.jper.packages import PackageHandler, FilesAndJATS

RESOURCES = rel2abs(__file__, "..", "resources")
"""Path to the test resources directory, calculated relative to this file"""

def _resource_path(fname):
    return os.path.join(RESOURCES, fname)

class PackageHandlerForTesting(PackageHandler):
    """
    Class which implements the PackageHandler interface for the purposes of mocks

    See the PackageHandler documentation for more information about the methods here
    """

    def zip_name(self):
        return "ForTesting.zip"

    def metadata_names(self):
        return []


class StoreFailStore(store.StoreLocal):
    """
    Class which extends the local store implementation in order to raise errors under
    useful testing conditions
    """

    def store(self, container_id, filename, source_path=None, source_stream=None, source_data=None):
        """
        Raise an exception when attempting to store
        """
        raise store.StoreException("Nope")


class StoreFailRetrieve(store.StoreLocal):
    """
    Class which extends the local store implementation in order to raise errors under useful
    testing conditions
    """

    def get(self, container_id, target_name):
        """
        Raise an exception on retrieve

        :param container_id:
        :param target_name:
        :return:
        """
        raise store.StoreException("Shant")


class PackageFactory:
    """
    Class which provides access to fixtures for testing packaging
    """

    @classmethod
    def example_package_path(cls):
        """
        Get the path to the example package in the resources directory

        :return: path
        """
        return _resource_path("example.zip")

    @classmethod
    def make_custom_zip(cls,
                        path,
                        no_jats=False,
                        invalid_jats=False,
                        jats_errors=False,
                        jats_no_match_data=False,
                        corrupt_zip=False,
                        target_size=None,
                        inc_pdf=False,
                        example_zip=False,
                        space_in_fname=False,
                        jats_with_xmlns=False,
                        compression=ZIP_STORED
                        ):
        """
        Construct a custom zip file for testing packaging, which has the following features

        :param path: where to store it
        :param no_jats: whether to omit the JATS XML
        :param invalid_jats: Boolean - whether the included JATS is invalid
        :param jats_errors: Boolean - True: include invalid_jats_with_errors.xml file in Zip
        :param jats_no_match_data: Valid JATS, but without any actionable matching metadata
        :param corrupt_zip: should the zip file be corrupt
        :param target_size: how large should the file be (output is approximate, not exact)
        :param inc_pdf: Whether to include a PDF file
        :param example_zip: Whether to create new zip by copying the example zip
        :param space_in_fname: Whether to include a space in the PDF or MXL filename
        :param jats_with_xmlns: JATS file that contains (unexpected) xmlns="..." within the <article ...> element
        :param compression: Whether to create a compressed ZipFile (default is no compression). Permitted values:
                        zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED, zipfile.ZIP_LZMA, zipfile.ZIP_BZIP2.
        :return:
        """
        # if we want a corrupt zip, no need to pay attention to any of the other options
        if corrupt_zip:
            with open(path, "wb") as f:
                f.write(b"alkdsjfasdfwqefnjwqeoijqwefoqwefoihwqef")
            return

        if example_zip:
            file_copy(cls.example_package_path(), path)
            return

        # create the zip we're going to populate
        zip = ZipFile(path, "w", compression=compression)

        insert_space = " " if space_in_fname else ""

        # determine if we need to write a jats file
        if not no_jats:
            if invalid_jats:
                filename = f"invalid{insert_space}_jats.xml"
                zip.writestr(filename, "akdsjiwqefiw2fuwefoiwqejhqfwe")
            elif jats_no_match_data:
                filename = f"valid{insert_space}_jats_no_match_data.xml"
                zip.write(_resource_path("valid_jats_no_match_data.xml"), filename)
            elif jats_errors:
                filename = f"invalid{insert_space}_jats_with_errors.xml"
                zip.write(_resource_path("invalid_jats_with_errors.xml"), filename)
            elif jats_with_xmlns:
                filename = f"valid{insert_space}_jats_unexpected_xmlns.xml"
                zip.write(_resource_path("valid_jats_unexpected_xmlns.xml"), filename)
            else:
                filename = f"valid{insert_space}_jats.xml"
                zip.write(_resource_path("valid_jats_epmc.xml"), filename)

        if inc_pdf:
            filename = f"the{insert_space}_article.pdf"
            zip.write(_resource_path("download.pdf"), filename)

        # now pad the file out with pdf files until it reaches the target size (or slightly over)
        if target_size is not None:
            while os.path.getsize(path) < target_size:
                zip.write(_resource_path("download.pdf"), uuid.uuid4().hex + ".pdf")

        zip.close()

    @classmethod
    def zip_with_poorly_formed_xml_file(cls, path, compression=ZIP_STORED):
        """
        Create a zip with a poorly formed XML file for the purposes of checking whether we can deal with such a file

        The file has the following problems:
            HTML entities included (&commat;)
            A namespaced element without a namespace definition (namespaced:element)

        :param path: Path where the zip will be saved
        :param compression: Whether to create a compressed ZipFile (default is no compression). Permitted values:
                        zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED, zipfile.ZIP_LZMA, zipfile.ZIP_BZIP2.
        """
        zip = ZipFile(path, "w", compression=compression)

        zip.write(_resource_path("valid_jats_epmc_poor.xml"), "validjats.xml")

        zip.close()

    @classmethod
    def zip_with_xml_file(cls, path, xml_string, compression=ZIP_STORED):
        """
        Simple method that just adds an xml file with a given value into a zip that can be used with packages.

        :param path: Path where the zip file will be located
        :param xml_string: XML string to be used in the XML file located in the zip
        :param compression: Whether to create a compressed ZipFile (default is no compression). Permitted values:
                        zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED, zipfile.ZIP_LZMA, zipfile.ZIP_BZIP2.
        """
        zip = ZipFile(path, "w", compression=compression)

        zip.writestr("jats.xml", xml_string)

        zip.close()

    @classmethod
    def get_metadata_from_jats(cls, method=''):
        factory = JATSFactory
        map = {
            "multi_license": factory.multi_license_xml,
            "multi_license_p": factory.multi_license_xml_multiple_license_p,
            "start_date": factory.license_with_start_date
        }
        jats = map.get(method, factory.multi_license_xml)()
        package = FilesAndJATS()
        package.jats = jats
        return package._jats_metadata()

    @classmethod
    def custom_file_handles(cls,
                            elife_jats=True,
                            epmc_jats=False,
                            epmc_native=False,
                            invalid_jats=False,
                            invalid_epmc=False):
        """
        Custom metadata file handles suitable for passing to a package handler

        :param elife_jats: Boolean - require elife JATS
        :param epmc_jats: Boolean - require EPMC JATS
        :param epmc_native: Boolean - require EPMC native XML
        :param invalid_jats: should the included JATS be invalid
        :param invalid_epmc: should the included EPMC be invalid
        :return:
        """
        handles = []

        if invalid_jats or invalid_epmc:
            file_handle = StringIO("akdsjiwqefiw2fuwefoiwqejhqfwe")

        if elife_jats:
            handles.append(("filesandjats_jats.xml",
                            file_handle if invalid_jats
                            else codecs.open(_resource_path("valid_jats_elife.xml"), "rb")))

        if epmc_jats:
            handles.append(("filesandjats_jats.xml",
                            file_handle if invalid_jats
                            else codecs.open(_resource_path("valid_jats_epmc.xml"), "rb")))

        if epmc_native:
            handles.append(("filesandjats_epmc.xml",
                            file_handle if invalid_epmc
                            else codecs.open(_resource_path("valid_epmc.xml"), "rb")))

        return handles


class FTPSubmissionFactory:
    SIZE_MULT = 100000

    @classmethod
    def xml_str(cls, large):
        mult = cls.SIZE_MULT if large else 1
        return "<root>" + ("<el>abcdxxxxx</el>" * mult) + "</root>"

    @classmethod
    def a_str(cls, large):
        mult = cls.SIZE_MULT if large else 1
        return "abcdexxxxxxyyzzzzz" * mult

    @classmethod
    def empty_zip(cls, target_path):
        with ZipFile(target_path, "w"):
            pass


    @classmethod
    def zip_with_directories(cls, target_path,
                 dir_list=None,
                 space_in_filename=False,
                 compression=ZIP_STORED,
                 large=False,
                 extra_xml=False,
                 with_pdf=True,
                 with_xml=True,
                 with_other=True
                 ):
        filler = " " if space_in_filename else ""
        test_str = cls.a_str(large)
        test_xml = cls.xml_str(large)
        if dir_list is None:
            dir_list = [""]     # Not creating any sub-directory
        path = ""
        with ZipFile(target_path, "w", compression=compression) as zip_file:
            for dir_name in dir_list:
                if dir_name:
                    path += dir_name + "/"
                    zip_file.writestr(path, "")     # Create directory
                if with_xml:
                    zip_file.writestr(f"{path}jats{filler}.xml", test_xml)
                if extra_xml:
                    zip_file.writestr(f"{path}extra_1{filler}.xml", test_xml)
                    zip_file.writestr(f"{path}extra_2{filler}.xml", test_xml)
                if with_pdf:
                    zip_file.writestr(f"{path}file{filler}.pdf", test_str)
                if with_other:
                    zip_file.writestr(f"{path}other.txt", test_str)

    @classmethod
    def atypon_zip(cls, target_path, space_in_filename=False, compression=ZIP_STORED, large=False):
        """
        Construct an atypon style zip file which contains >1 article sub-directory, each of which contains an article
        PDF and JATS XML and possibly other files or sub-directories):
           zipfile: atypon
                        |-article_A
                                |-jats_A0.xml
                                |-article_A0.pdf
                                |-other_A0.txt
                                |-extra_A0.xml
                                |-extras
                                    |-...
                        |-article_B
                                |-jats_B0.xml
                                |-article_B0.pdf
                                |-other_B0.txt
                                |-extra_B0.xml
                                |-extras
                                    |-...
        """
        filler = " " if space_in_filename else ""
        test_str = cls.a_str(large)
        test_xml = cls.xml_str(large)
        with ZipFile(target_path, "w", compression=compression) as zip_file:
            for suffix in ("_A", "_B"):
                path = f"atypon/article{suffix}"  # First level directory
                for ix, dirname in enumerate(["", "extras"]):
                    path += dirname + "/"
                    zip_file.writestr(f"{path}jats{filler}{suffix}{ix}.xml", test_xml)
                    zip_file.writestr(f"{path}article{filler}{suffix}{ix}.pdf", test_str)
                    zip_file.writestr(f"{path}other{suffix}{ix}.txt", test_str)
                    zip_file.writestr(f"{path}extra{suffix}{ix}.xml", test_xml)
