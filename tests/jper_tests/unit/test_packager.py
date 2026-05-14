# coding=utf-8
"""
Unit tests for the packaging system
"""
from zipfile import ZipFile, ZIP_STORED, ZIP_DEFLATED
import os
import shutil
from lxml import etree
from unittest import TestCase
from flask import current_app
from octopus.lib.paths import get_real_path
from octopus.modules.store import store
from router.jper.app import app_decorator
from router.jper.unpacked import UnpackEprintsRioxx
from tests.jper_tests.fixtures.packages import PackageFactory, PackageHandlerForTesting, FTPSubmissionFactory

from router.jper import packages
from router.jper.pub_testing import init_pub_testing


FILE_JATS_PACKAGE = "https://pubrouter.jisc.ac.uk/FilesAndJATS"
TEST_FORMAT = "http://router.jisc.ac.uk/packages/OtherTestFormat"
SIMPLE_ZIP = "http://purl.org/net/sword/package/SimpleZip"
TEST_HANDLER = "tests.jper_tests.fixtures.packages.PackageHandlerForTesting"
STORE_ID = "12345"

def safe_makedirs(path):
    os.makedirs(path, exist_ok=True)

class TestPackager(TestCase):
    """
    Test retrieving JATS from zip file or metadata file.
    """
    # EXPECTED metadata from JATS package
    metadata = {
        'publication_status': 'Published',
        'funding': [{
            'grant_numbers': ['NIH GM61374'],
            'name': 'NIH'
        }, {
            'grant_numbers': ['NSF DBI-0317510'],
            'name': 'NSF'
        }, {
            'grant_numbers': ['GM18458'],
            'name': 'National Institutes of Health'
        }, {
            'grant_numbers': ['DMS-0204674', 'DMS-0244638'],
            'name': 'National Science Foundation'
        }
        ],
        'author': [{
            'affiliations': [{'raw': 'An affiliation without ID.'},
                             {'raw': 'Another affiliation without ID.'},
                             {'raw': 'Local affiliation WITH ID'}],
            'identifier': [{
                'type': 'email',
                'id': 'e.asoli@frontiersin.org'
            }
            ],
            'type': 'corresp',
            'name': {
                'fullname': 'Asoli, Eleonora',
                'surname': 'Asoli',
                'firstname': 'Eleonora'
            }
        }, {
            'affiliations': [{'raw': "An affiliation without ID."},
                             {'raw': "Another affiliation without ID."},
                             {'org': "Basic Medical Sciences, St. George's University of London", 'city': "London", 'country': "UK", 'postcode': "EH10 6KL"}],
            'identifier': [{
                'type': 'email',
                'id': 'b.ceecee@frontiersin.org'
            }
            ],
            'type': 'author',
            'name': {
                'fullname': 'Ceecee, Bob with global xref',
                'surname': 'Ceecee',
                'firstname': 'Bob with global xref'
            }
        }, {
            'affiliations': [{'org': 'Biotechnology Department, National Physical Laboratory', 'city': "Teddington", 'country': 'UK', 'postcode': "SW1 5EY"}],
            'identifier': [{
                'type': 'email',
                'id': 'e.cerasoli@frontiersin.org'
            }
            ],
            'type': 'author',
            'name': {
                'fullname': 'Cerasoli, Eleonora',
                'surname': 'Cerasoli',
                'firstname': 'Eleonora'
            }
        }, {
            'affiliations': [{'org': 'Biotechnology Department, National Physical Laboratory', 'city': "Teddington", 'country': 'UK', 'postcode': "SW1 5EY"}],
            'identifier': [],
            'type': 'an author',
            'name': {
                'fullname': 'Ryadnov, Maxim G.',
                'surname': 'Ryadnov',
                'firstname': 'Maxim G.'
            }
        }, {
            'affiliations': [{'org': "Basic Medical Sciences, St. George's University of London", 'city': "London", 'country': "UK", 'postcode': "EH10 6KL"}],
            'identifier': [
                {
                    'type': 'orcid',
                    'id': '0000-0002-1825-0097'
                }, {
                    'type': 'scopus',
                    'id': '7007156898'
                }
            ],
            'type': 'assisting author',
            'name': {
                'fullname': 'Austen, Brian M.',
                'surname': 'Austen',
                'firstname': 'Brian M.'
            }
        }
        ],
        'contributor': [{
            'affiliations': [{'raw': 'An affiliation without ID.'},
                             {'raw': 'Another affiliation without ID.'},
                             {'raw': 'Beebee\'s very own Affiliation'}
                             ],
            'identifier': [{'type': 'orcid', 'id': '0000-0002-1825-8888'},
                           {'type': 'scopus', 'id': '123456'},
                           {'type': 'email', 'id': 'j.beebee@frontiersin.org'}
                           ],
            'type': 'editor',
            'name': {
                'fullname': 'Beebee, Jane with local xref',
                'surname': 'Beebee',
                'firstname': 'Jane with local xref'
            }
        }
        ],
        'license_ref': [{
            'title': 'This is an open-access article distributed under the terms of the Creative Commons Attribution License (CC BY). SOME SUP The use, distribution or reproduction in other forums is permitted, provided the original author(s) or licensor are credited and that the original publication in this journal is cited, in accordance with accepted academic practice. No use, distribution or reproduction is permitted which does not comply with these terms.',
            'url': 'http://creativecommons.org/licenses/by/4.0/',
            'start': '',
            'version': '',
            'type': 'open-access'
        }, {
            'title': 'http://some-url/ok',
            'url': 'http://some-url/ok',
            'start': '2017-05-02',
            'version': '',
            'type': ''
        }
        ],
        'journal': {
            'publisher': ['Frontiers Media S.A.'],
            'identifier': [{
                'type': 'eissn',
                'id': '2296-2646'
            }
            ],
            'title': 'Frontiers in Chemistry'
        },
        'publication_date': {
            'date': '2015-03-19',
            # 'season': '',
            'publication_format': 'electronic'
        },
        'article': {
            'subtitle': [],
            'language': [],
            'title': "The elusive nature and diagnostics of misfolded Aβ oligomers",
            'identifier': [{
                'type': 'pmcid',
                'id': 'PMC4365737'
            }, {
                'type': 'doi',
                'id': '10.3389/fchem.2015.00017'
            }
            ],
            'type': 'review-article',
            'subject': [u'Aβ oligomers', 'neurodegeneration', 'protein misfolding', 'fibrillogenesis',
                        "Alzheimer's disease"],
            'abstract': "Abstract: Test abstract. Amyloid-beta (Aβ) peptide oligomers are believed to be the causative agents of Alzheimer's disease (AD). Though post-mortem examination shows that insoluble fibrils are deposited in the brains of AD patients in the form of intracellular (tangles) and extracellular (plaques) deposits, it has been observed that cognitive impairment is linked to synaptic dysfunction in the stages of the illness well before the appearance of these mature deposits. Increasing evidence suggests that the most toxic forms of Aβ are soluble low-oligomer ligands whose amounts better correlate with the extent of cognitive loss in patients than the amounts of fibrillar insoluble forms. Therefore, these ligands hold the key to a better understanding of AD prompting the search for clearer correlations between their structure and toxicity. The importance of such correlations and their diagnostic value for the early diagnosis of AD is discussed here with a particular emphasis on the transient nature and structural plasticity of misfolded Aβ oligomers."
        },
        'ack': 'Acknowledgements: This is a test acknowledgement. Test ack 2nd para.',
        'history_date': [],
        'accepted_date': '2015-02-24'
    }

    routing_metadata = {
        'orcids' : ['0000-0002-1825-0097'],
        'postcodes' : ['EH10 6KL', 'SW1 5EY'],
        'affiliations' : ['An affiliation without ID.', 'Another affiliation without ID.', 'Local affiliation WITH ID', "Basic Medical Sciences, St. George's University of London, London, UK, EH10 6KL", 'Biotechnology Department, National Physical Laboratory, Teddington, UK, SW1 5EY'],
        'grants' : ['NIH GM61374', 'NSF DBI-0317510', 'GM18458', 'DMS-0204674', 'DMS-0244638'],
        'emails' : ['e.asoli@frontiersin.org', 'b.ceecee@frontiersin.org', 'e.cerasoli@frontiersin.org']
    }
    store = os.path.join("/tmp", "store")

    @classmethod
    @app_decorator
    def setUpClass(cls):
        # # List the tables (by table name) needed for testing
        # cls.tables_for_testing = ['account', 'acc_user', 'notification', 'notification_account']
        # cls.tables_for_testing = []
        super().setUpClass()
        cls.curr_app_config = current_app.config  # Do this to avoid repeatedly calling current_app local-proxy

        cls.curr_app_config["TESTING"] = True
        # Set up store
        cls.curr_app_config["STORE_TMP_DIR"] = cls.store_path("tmp")
        cls.curr_app_config["STORE_MAIN_DIR"] = cls.store_path("live")
        cls.curr_app_config["STORE_TYPE"] = None  # Force StoreFactory to use STORE_IMPL
        cls.curr_app_config["STORE_IMPL"] = "octopus.modules.store.store.StoreLocal"

        # Disable FTP accounts on UNIX
        cls.curr_app_config["UNIX_FTP_ACCOUNT_ENABLE"] = False

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        # Clear all folders
        shutil.rmtree(cls.store, ignore_errors=True)

    @classmethod
    def store_path(cls, endpoint):
        return os.path.join(cls.store, endpoint)

    @classmethod
    def setup_store(cls):
        # Set up store directories
        shutil.rmtree(cls.store, ignore_errors=True)
        safe_makedirs(cls.curr_app_config["STORE_TMP_DIR"])
        safe_makedirs(cls.curr_app_config["STORE_MAIN_DIR"])

    @app_decorator
    def setUp(self):
        self.curr_app_config["PACKAGE_HANDLERS"].update({TEST_FORMAT : TEST_HANDLER})
        self.curr_app_config["STORE_IMPL"] = "octopus.modules.store.store.StoreLocal"
        super(TestPackager, self).setUp()

        self.setup_store()

        self.custom_zip_path = get_real_path(__file__, "..", "resources", "custom.zip")
        self.pub_test = init_pub_testing()

    def tearDown(self):
        super(TestPackager, self).tearDown()
        if os.path.exists(self.custom_zip_path):
            os.remove(self.custom_zip_path)

    def _compare_authors_contributors(self, derived_people, expected_people):
        assert len(derived_people) == len(expected_people)

        derived= sorted(derived_people, key=lambda x: x['name']['fullname'])
        expected = sorted(expected_people, key=lambda x: x['name']['fullname'])
        for d, e in zip(derived, expected):
            assert d["name"]["fullname"] == e["name"]['fullname']
            assert d["type"] == e["type"]
            assert d["affiliations"] == e["affiliations"]
            derived_identifiers = (sorted(d.get("identifier", []), key=lambda identifier: identifier.get("id")))
            expected_identifiers = (sorted(e["identifier"], key=lambda identifier: identifier.get("id")))
            assert derived_identifiers == expected_identifiers

    @app_decorator
    def test_01_factory(self):
        # try loading incoming packages
        pkg_handler = packages.PackageFactory.get_pkg_mgr_and_extract_metadata_from_file(FILE_JATS_PACKAGE)
        assert isinstance(pkg_handler, packages.FilesAndJATS)

        pkg_handler = packages.PackageFactory.get_pkg_mgr_and_extract_metadata_from_file(TEST_FORMAT)
        assert isinstance(pkg_handler, PackageHandlerForTesting)

        # try loading converter packages
        pkg_handler = packages.PackageFactory.get_pkg_mgr(FILE_JATS_PACKAGE)
        assert isinstance(pkg_handler, packages.FilesAndJATS)

        pkg_handler = packages.PackageFactory.get_pkg_mgr(TEST_FORMAT)
        assert isinstance(pkg_handler, PackageHandlerForTesting)

    @app_decorator
    def test_02_valid_zip(self):
        # first construct the packager around the zip
        zip_path = PackageFactory.example_package_path()
        pkg_handler = packages.PackageFactory.get_pkg_mgr_and_extract_metadata_from_file(FILE_JATS_PACKAGE, zip_path=zip_path)

        # now check the properties are initialised as we would expect
        assert pkg_handler.zip_path == zip_path
        assert pkg_handler.zip is not None
        assert pkg_handler.jats is not None
        ##REMOVED-epmc-XML## assert pkg_handler.epmc is not None

        # now see if we can extract the metadata streams
        names = []
        for name, stream in pkg_handler.metadata_streams():
            names.append(name)
            xml = etree.fromstring(stream.read())
            if name == "filesandjats_jats.xml":
                assert xml.tag == "article"
            elif name == "filesandjats_epmc.xml":
                assert xml.tag == "result"

        assert "filesandjats_jats.xml" in names
        ##REMOVED-epmc-XML## assert "filesandjats_epmc.xml" in names

        # now try doing the same but with zips that only contain one of the relevant
        # metadata files (which would still be valid)

        # first a zip that just contains the jats (no epmc)
        PackageFactory.make_custom_zip(self.custom_zip_path)
        pkg_handler = packages.PackageFactory.get_pkg_mgr_and_extract_metadata_from_file(FILE_JATS_PACKAGE, zip_path=self.custom_zip_path)

        assert pkg_handler.zip_path == self.custom_zip_path
        assert pkg_handler.zip is not None
        assert pkg_handler.jats is not None
        ##REMOVED-epmc-XML## assert pkg_handler.epmc is None

        # now see if we can extract the metadata streams
        names = []
        for name, stream in pkg_handler.metadata_streams():
            names.append(name)
        assert len(names) == 1
        assert "filesandjats_jats.xml" in names

    @app_decorator
    def test_03_invalid_zip(self):
        PackageFactory.make_custom_zip(self.custom_zip_path, corrupt_zip=True)
        with self.assertRaises(packages.PackageException) as exc:
            packages.PackageFactory.get_pkg_mgr_and_extract_metadata_from_file(FILE_JATS_PACKAGE,
                                                                               zip_path=self.custom_zip_path)
        self.assertIn("Cannot read zip file", str(exc.exception))

        PackageFactory.make_custom_zip(self.custom_zip_path, no_jats=True)
        with self.assertRaises(packages.PackageException) as exc:
            packages.PackageFactory.get_pkg_mgr_and_extract_metadata_from_file(FILE_JATS_PACKAGE,
                                                                               zip_path=self.custom_zip_path)
        self.assertEqual("No JATS metadata found in package", str(exc.exception))

        PackageFactory.make_custom_zip(self.custom_zip_path, invalid_jats=True)
        with self.assertRaises(packages.PackageException) as exc:
            packages.PackageFactory.get_pkg_mgr_and_extract_metadata_from_file(FILE_JATS_PACKAGE,
                                                                               zip_path=self.custom_zip_path)
        self.assertTrue(str(exc.exception).startswith("No JATS metadata found in package"))


    @app_decorator
    def test_04_valid_file_handles(self):
        handles = PackageFactory.custom_file_handles()
        pkg_handler = packages.PackageFactory.get_pkg_mgr_and_extract_metadata_from_file(FILE_JATS_PACKAGE, metadata_files=handles)

        # now check the properties are initialised as we would expect
        assert pkg_handler.zip_path is None
        assert pkg_handler.zip is None
        assert pkg_handler.jats is not None

        # now see if we can extract the metadata streams
        names = []
        for name, stream in pkg_handler.metadata_streams():
            names.append(name)
            xml = etree.fromstring(stream.read())
            if name == "filesandjats_jats.xml":
                assert xml.tag == "article"

        assert "filesandjats_jats.xml" in names

        # now do the same but with handles containing only one of epmc and jats

        # first for files containing only jats (no epmc)
        handles = PackageFactory.custom_file_handles(elife_jats=True)
        pkg_handler = packages.PackageFactory.get_pkg_mgr_and_extract_metadata_from_file(FILE_JATS_PACKAGE, metadata_files=handles)

        assert pkg_handler.zip_path is None
        assert pkg_handler.zip is None
        assert pkg_handler.jats is not None
        ##REMOVED-epmc-XML## assert pkg_handler.epmc is None

        names = []
        for name, stream in pkg_handler.metadata_streams():
            names.append(name)
        assert len(names) == 1
        assert "filesandjats_jats.xml" in names

        ##REMOVED-epmc-XML## NEVER EXECUTE FOLLOWING BLOCK
        # # then for files containing only epmc (no jats)
        # handles = PackageFactory.custom_file_handles(epmc_native=True)
        # pkg_handler = packages.PackageFactory.get_pkg_mgr_and_extract_metadata_from_file(FILE_JATS_PACKAGE, metadata_files=handles)
        #
        # assert pkg_handler.zip_path is None
        # assert pkg_handler.zip is None
        # assert pkg_handler.jats is None
        # ##REMOVED-epmc-XML## assert pkg_handler.epmc is not None
        #
        # names = []
        # for name, stream in pkg_handler.metadata_streams():
        #     names.append(name)
        # assert len(names) == 1
        # assert "filesandjats_epmc.xml" in names

    @app_decorator
    def test_05_invalid_file_handles(self):
        handles = PackageFactory.custom_file_handles(elife_jats=False)
        with self.assertRaises(packages.PackageException) as exc:
            packages.PackageFactory.get_pkg_mgr_and_extract_metadata_from_file(FILE_JATS_PACKAGE,
                                                                               metadata_files=handles)
        self.assertTrue(str(exc.exception).startswith("No JATS metadata found in metadata files"))

        ## REMOVED - as epmc XML not currently supported
        # handles = PackageFactory.custom_file_handles(invalid_epmc=True)
        # with self.assertRaises(packages.PackageException) as exc:
        #     packages.PackageFactory.get_pkg_mgr_and_extract_metadata_from_file(FILE_JATS_PACKAGE,
        #                                                                        metadata_files=handles)
        # self.assertEqual("Unable to parse 'filesandjats_epmc.xml' file from store", str(exc.exception))

        handles = PackageFactory.custom_file_handles(invalid_jats=True)
        with self.assertRaises(packages.PackageException) as exc:
            packages.PackageFactory.get_pkg_mgr_and_extract_metadata_from_file(FILE_JATS_PACKAGE,
                                                                               metadata_files=handles)
        self.assertEqual("Unable to parse 'filesandjats_jats.xml' file from store", str(exc.exception))

    @app_decorator
    def test_06_package_manager_ingest(self):
        # create a custom zip
        PackageFactory.make_custom_zip(self.custom_zip_path)

        # get the package manager to ingest
        packages.PackageManager.ingest(STORE_ID, self.custom_zip_path, FILE_JATS_PACKAGE)

        # now check that the consequences of the above have worked out

        # create our own instance of the storage manager, and query the store directly
        sm = store.StoreFactory.get()

        # check that all the files have been stored
        stored = sm.list(STORE_ID)
        assert len(stored) == 2
        assert "ArticleFilesJATS.zip" in stored
        assert "filesandjats_jats.xml" in stored

        # check that we can retrieve the metadata files and read them
        jats = sm.get(STORE_ID, "filesandjats_jats.xml")

        # should be able to initialIse the package handler around them without error
        pkg_handler = packages.PackageFactory.get_pkg_mgr_and_extract_metadata_from_file(
            FILE_JATS_PACKAGE, metadata_files=[("filesandjats_jats.xml", jats)])

    @app_decorator
    def test_07_package_manager_ingest_fail(self):
        # create a package that has an error in it
        PackageFactory.make_custom_zip(self.custom_zip_path, corrupt_zip=True)

        # try to import it, and expect a PackageException to be raised
        with self.assertRaises(packages.PackageException):
            packages.PackageManager.ingest(STORE_ID, self.custom_zip_path, FILE_JATS_PACKAGE)

        # now switch the current store for one which will fail to save
        self.curr_app_config["STORE_IMPL"] = "tests.jper_tests.fixtures.packages.StoreFailStore"

        # now do a correctly structured package, but make sure a store exception
        # is handled
        PackageFactory.make_custom_zip(self.custom_zip_path)
        with self.assertRaises(store.StoreException):
            packages.PackageManager.ingest(STORE_ID, self.custom_zip_path, FILE_JATS_PACKAGE)

    @app_decorator
    def test_10_jats_metadata(self):
        """
        Ok, so technically this is testing a private method on a specific instance of the
        packager, but that method does some quite difficult work, so needs to be tested in isolation
        We will also test it further down as part of the broader function it is part of
        :return:
        """
        fhs = PackageFactory.custom_file_handles(elife_jats=False, epmc_jats=True)
        pkg_handler = packages.PackageFactory.get_pkg_mgr_and_extract_metadata_from_file(FILE_JATS_PACKAGE, metadata_files=fhs)
        md = pkg_handler._jats_metadata()

        assert md.article_title == self.metadata['article']['title']
        assert md.journal_publishers[0] == self.metadata['journal']['publisher'][0]
        assert md.accepted_date == self.metadata['accepted_date']

        lic = md.licenses
        assert lic[0]['title'] == self.metadata['license_ref'][0]['title']
        assert lic[0]['type'] == self.metadata['license_ref'][0]['type']
        assert lic[0]['url'] == self.metadata['license_ref'][0]['url']

        assert md.get_article_identifiers("pmcid")[0] == self.metadata['article']['identifier'][0]['id']
        assert md.get_article_identifiers("doi")[0] == self.metadata['article']['identifier'][1]['id']

        assert md.get_journal_identifiers("eissn")[0] == self.metadata['journal']['identifier'][0]['id']

        self._compare_authors_contributors(md.authors, self.metadata.get('author'))
        self._compare_authors_contributors(md.contributors, self.metadata.get('contributor'))

        for s in md.article_subject:
            assert s in self.metadata.get('article').get('subject')
        assert len(md.article_subject) == len(self.metadata.get('article').get('subject'))

        assert md.article_abstract ==  self.metadata['article']['abstract']
        assert md.ack == self.metadata['ack']

    @app_decorator
    def test_11_notification_metadata(self):
        fhs = PackageFactory.custom_file_handles(elife_jats=False, epmc_jats=True)
        pkg_handler = packages.PackageFactory.get_pkg_mgr_and_extract_metadata_from_file(FILE_JATS_PACKAGE, metadata_files=fhs)
        md = pkg_handler.notification_metadata()

        assert md.article_title == self.metadata['article']['title']
        assert md.journal_publishers[0] == self.metadata['journal']['publisher'][0]
        assert md.article_type == self.metadata['article']['type']
        ## JATS does not provide a language ## assert md.article_language[0] == lang
        assert md.get_publication_date_string() == self.metadata['publication_date']['date']
        assert md.accepted_date == self.metadata['accepted_date']

        lic = md.licenses
        assert lic[0]['title'] == self.metadata['license_ref'][0]['title']
        assert lic[0]['type'] == self.metadata['license_ref'][0]['type']
        assert lic[0]['url'] == self.metadata['license_ref'][0]['url']

        assert md.get_article_identifiers("pmcid")[0] == self.metadata['article']['identifier'][0]['id']
        assert md.get_article_identifiers("doi")[0] == self.metadata['article']['identifier'][1]['id']

        self._compare_authors_contributors(md.authors, self.metadata.get('author'))

        count = 0
        for p in md.funding:
            for funder in self.metadata.get('funding'):
                if p.get("grant_numbers") == funder["grant_numbers"]:
                    assert p.get("name") == funder["name"]
                    count += 1
        assert count == 4

        for s in md.article_subject:
            assert s in self.metadata.get('article').get('subject')
        assert len(md.article_subject) == len(self.metadata.get('article').get('subject'))
        
        assert md.article_abstract ==  self.metadata['article']['abstract']
        assert md.ack == self.metadata['ack']

    @app_decorator
    def test_12_package_manager_extract(self):
        # create a custom zip
        PackageFactory.make_custom_zip(self.custom_zip_path)

        # get the package manager to ingest
        packages.PackageManager.ingest(STORE_ID, self.custom_zip_path, FILE_JATS_PACKAGE)

        # now the item is in the store, get the package manager to extract from store
        md = packages.PackageManager.extract(STORE_ID, FILE_JATS_PACKAGE)

        assert md.article_title == self.metadata['article']['title']
        assert md.journal_publishers[0] == self.metadata['journal']['publisher'][0]
        assert md.article_type == self.metadata['article']['type']
        assert md.get_publication_date_string() == self.metadata['publication_date']['date']
        assert md.accepted_date == self.metadata['accepted_date']

        lic = md.licenses
        assert lic[0]['title'] == self.metadata['license_ref'][0]['title']
        assert lic[0]['type'] == self.metadata['license_ref'][0]['type']
        assert lic[0]['url'] == self.metadata['license_ref'][0]['url']

        assert md.get_article_identifiers("pmcid")[0] == self.metadata['article']['identifier'][0]['id']
        assert md.get_article_identifiers("doi")[0] == self.metadata['article']['identifier'][1]['id']

        self._compare_authors_contributors(md.authors, self.metadata.get('author'))

        count = 0
        for p in md.funding:
            for funder in self.metadata.get('funding'):
                if p.get("grant_numbers") == funder["grant_numbers"]:
                    assert p.get("name") == funder["name"]
                    count += 1
        assert count == 4

        for s in md.article_subject:
            assert s in self.metadata.get('article').get('subject')
        assert len(md.article_subject) == len(self.metadata.get('article').get('subject'))

    @app_decorator
    def test_13_filesandjats_names(self):
        pm = packages.PackageFactory.get_pkg_mgr_and_extract_metadata_from_file(FILE_JATS_PACKAGE)
        assert pm.zip_name() == "ArticleFilesJATS.zip"
        assert "filesandjats_jats.xml" in pm.metadata_names()
        # !!REMOVED-epmc-XML!! assert "filesandjats_epmc.xml" in pm.metadata_names()

    @app_decorator
    def test_14_convert_file_and_jats_to_simplezip(self):
        # get a package manager and the path to our test package
        pkg_mgr_class = packages.PackageFactory.get_handler_class(FILE_JATS_PACKAGE)
        in_path = PackageFactory.example_package_path()

        # run the coversion to the custom zip path
        converted = pkg_mgr_class.convert(in_path, SIMPLE_ZIP, self.custom_zip_path)

        assert converted is True
        assert os.path.exists(self.custom_zip_path)
        assert os.path.isfile(self.custom_zip_path)

        # now try a conversion to an unsupported format
        os.remove(self.custom_zip_path)
        converted = pkg_mgr_class.convert(in_path, "random string", self.custom_zip_path)

        assert converted is False
        assert not os.path.exists(self.custom_zip_path)

    @app_decorator
    def test_15_package_manager_convert(self):
        # first put a package into the store
        # create a custom zip
        PackageFactory.make_custom_zip(self.custom_zip_path)

        # get the package manager to ingest
        packages.PackageManager.ingest(STORE_ID, self.custom_zip_path, FILE_JATS_PACKAGE)

        # now run the conversion to 2 formats, one of which cannot be converted to and the other of which can
        conversions = packages.PackageManager.convert(STORE_ID, FILE_JATS_PACKAGE, [TEST_FORMAT, SIMPLE_ZIP])

        # check that the result looks right (as SimpleZip has same format as FilesAndJATS a new file is not actually created)
        assert len(conversions) == 1    # not 2!
        assert len(conversions[0]) == 2     # it's a tuple
        assert conversions[0][0] == SIMPLE_ZIP
        assert conversions[0][1] == "ArticleFilesJATS.zip"

        # now check that under the hood the right things happened
        tmp = store.TempStore()
        assert not tmp.container_exists(STORE_ID)

        # check that the remote store still exists
        s = store.StoreFactory.get()
        assert s.container_exists(STORE_ID)

        ### No longer needed since real conversion does not occur
        # # check that the new file is there along with the others
        # l = s.list(STORE_ID)
        # assert "ArticleFiles.zip" in l
        # assert len(l) == 3          # the files and jats zip, the 2 extracted metadata files, and the simple zip
        #
        # # ensure that the new file has content
        # f = s.get(STORE_ID, "ArticleFiles.zip")
        # c = f.read()        # file is only small and this is a test, so read it all into memory
        # assert len(c) > 0

    @app_decorator
    def test_16_convert_no_source(self):
        # try to run the conversion without creating the stored object in the first place
        conversions = packages.PackageManager.convert(STORE_ID, FILE_JATS_PACKAGE, [TEST_FORMAT, SIMPLE_ZIP])
        assert len(conversions) == 0

        # now create the container, but remove the file, to see if we can trip up the converter

        # create a custom zip
        PackageFactory.make_custom_zip(self.custom_zip_path)

        # get the package manager to ingest
        packages.PackageManager.ingest(STORE_ID, self.custom_zip_path, FILE_JATS_PACKAGE)

        # interfere with the store, and delete the file we want to convert from, leaving behind the
        # store directory itself
        s = store.StoreFactory.get()
        s.delete(STORE_ID, "ArticleFilesJATS.zip", raise_exceptions=False)

        conversions = packages.PackageManager.convert(STORE_ID, FILE_JATS_PACKAGE, [TEST_FORMAT, SIMPLE_ZIP])
        assert len(conversions) == 0

    @app_decorator
    def test_17_unpacker(self):
        PackageFactory.make_custom_zip(self.custom_zip_path, inc_pdf=True)
        pkg_mgr = packages.PackageManager.ingest(STORE_ID, self.custom_zip_path, SIMPLE_ZIP)
        assert pkg_mgr.package_contains_file_type(".pdf") is True

        unpacked = UnpackEprintsRioxx(STORE_ID, "ArticleFiles.zip")
        links = unpacked.construct_link_metadata_list()
        assert len(links) == 2

        fileinfo = links[0]
        assert fileinfo.get("type") == "unpackaged"
        assert fileinfo.get("format") == "application/zip"
        assert fileinfo.get("cloc") == os.path.join("eprints-rioxx", "non-pdf-files.zip")

        fileinfo = links[1]
        assert fileinfo.get("type") == "unpackaged"
        assert fileinfo.get("format") == "application/pdf"


    @app_decorator
    def test_18_html_entities_in_zipped_xml(self):
        PackageFactory.zip_with_xml_file(
            self.custom_zip_path,
            "<article>&lt; pubrouter&commat;jisc.ac.uk &gt;</article>"
        )
        # Should not throw an error if passing
        pkg_handler = packages.FilesAndJATS(self.custom_zip_path)
        jats_xml = pkg_handler.jats
        assert jats_xml.to_unicode_str() == '<article>&lt; YYYY@YYYY.ac.uk &gt;</article>'

    @app_decorator
    def test_19_bad_namespacing_in_xml(self):
        PackageFactory.zip_with_xml_file(
            self.custom_zip_path,
            "<article><namespaced:element>Some data</namespaced:element></article>"
        )
        # Should not throw an error (but the bad namespaced element should be excluded)
        pkg_handler = packages.FilesAndJATS(self.custom_zip_path)
        jats_xml = pkg_handler.jats
        xml_str = jats_xml.to_unicode_str()
        assert xml_str == '<article/>'

    @app_decorator
    def test_20_poor_xml_file_with_metadata(self):
        PackageFactory.zip_with_poorly_formed_xml_file(self.custom_zip_path)
        jats = packages.FilesAndJATS(self.custom_zip_path)
        md = jats._jats_metadata()

        assert md.article_title == self.metadata['article']['title']
        assert md.journal_publishers[0] == self.metadata['journal']['publisher'][0]
        assert md.accepted_date == self.metadata['accepted_date']

        lic = md.licenses
        assert lic[0]['title'] == self.metadata['license_ref'][0]['title']
        assert lic[0]['type'] == self.metadata['license_ref'][0]['type']
        assert lic[0]['url'] == self.metadata['license_ref'][0]['url']

        assert md.get_article_identifiers("pmcid")[0] == self.metadata['article']['identifier'][0]['id']
        assert md.get_article_identifiers("doi")[0] == self.metadata['article']['identifier'][1]['id']

        assert md.get_journal_identifiers("eissn")[0] == self.metadata['journal']['identifier'][0]['id']

        self._compare_authors_contributors(md.authors, self.metadata.get('author'))

        for s in md.article_subject:
            assert s in self.metadata.get('article').get('subject')
        assert len(md.article_subject) == len(self.metadata.get('article').get('subject'))


    @app_decorator
    def test_21_non_jats_xml(self):
        PackageFactory.zip_with_xml_file(
            self.custom_zip_path,
            '<bad><front><journal-meta><journal-id journal-id-type="hwp">archdischild</journal-id></journal-meta></front></bad>'
        )
        with self.assertRaises(packages.PackageException) as exc:
            packages.FilesAndJATS(self.custom_zip_path)
        self.assertEqual("No JATS metadata found in package", str(exc.exception))


    @app_decorator
    def test_22_jats_with_xmlns(self):
        """
        Confirm that JATS XML file containing 'xmlns="..."' within <article ...> element can be read & recognised
        as JATS.  (The unexpected 'xmlns="..."' is removed).
        """
        PackageFactory.make_custom_zip(self.custom_zip_path, jats_with_xmlns=True)
        pkg_handler = packages.PackageFactory.get_pkg_mgr_and_extract_metadata_from_file(FILE_JATS_PACKAGE, zip_path=self.custom_zip_path)
        assert pkg_handler.jats is not None
        assert pkg_handler.jats.journal_title == "Article with xmlns"


class TestFtpPackages(TestCase):
    """
    Test that various permutations of Zip file (e.g. different depths of directory structure in zip, different types
    of content etc.) can be successfully processed.

    Mainly calls function: extract_xml_pdf_rebundle_zip_or_do_nothing() and also process_and_zip()
    """

    FTP_PATH = "{0}tmp{0}ftp-tests".format(os.sep)
    ADDITIONAL_ZIP_PATH = os.path.join(FTP_PATH, "additional-files.zip")

    @app_decorator
    def setUp(self):
        shutil.rmtree(self.FTP_PATH, ignore_errors=True)
        os.makedirs(self.FTP_PATH)
        self.pub_test = init_pub_testing()

    def tearDown(self):
        shutil.rmtree(self.FTP_PATH)

    @classmethod
    def create_notification_zip_path(cls, in_folder):
        path = cls.FTP_PATH
        if in_folder:
            path = os.path.join(path, "folder")
        if not os.path.exists(path):
            os.makedirs(path)
        path = os.path.join(path, "notification.zip")
        return path

    def create_empty_zip(self):
        path = self.create_notification_zip_path(False)
        FTPSubmissionFactory.empty_zip(path)

    def create_flat_zip(self, in_folder=False, space_in_filename=False, large=False, compress=False, extra_xml=False):
        path = self.create_notification_zip_path(in_folder)
        compression = ZIP_DEFLATED if compress else ZIP_STORED
        FTPSubmissionFactory.zip_with_directories(
            path, space_in_filename=space_in_filename, compression=compression, large=large, extra_xml=extra_xml)

    def create_zip_only_pdf_n_jats_xml(self, in_folder=False, space_in_filename=False, large=False, compress=False):
        path = self.create_notification_zip_path(in_folder)
        compression = ZIP_DEFLATED if compress else ZIP_STORED
        FTPSubmissionFactory.zip_with_directories(path, space_in_filename=space_in_filename, compression=compression, large=large, with_other=False)

    def create_deep_zip(self, in_folder=False, space_in_filename=False, large=False, compress=False):
        path = self.create_notification_zip_path(in_folder)
        compression = ZIP_DEFLATED if compress else ZIP_STORED
        FTPSubmissionFactory.zip_with_directories(path, ["first", "second"], space_in_filename, compression, large)

    @app_decorator
    def test_empty_zip(self):
        self.create_empty_zip()
        processor = packages.FTPZipFlattener(self.FTP_PATH, self.pub_test)
        with self.assertRaises(packages.PackageException) as exc:
            processor.extract_xml_pdf_rebundle_zip_or_do_nothing()
        assert str(exc.exception).startswith("No XML file in zip file")

    @app_decorator
    def test_flat_zip_no_folder(self):
        """
        Test processing of zip file created within self.FTP_PATH directory:
            {self.FPT_PATH}/notification.zip
        """
        self.create_flat_zip()
        processor = packages.FTPZipFlattener(self.FTP_PATH, self.pub_test)
        processor.extract_xml_pdf_rebundle_zip_or_do_nothing()

        filenames = set(os.listdir(self.FTP_PATH))
        assert filenames == {
            "additional-files.zip",
            "jats.xml",
            "file.pdf"
        }

        with ZipFile(self.ADDITIONAL_ZIP_PATH) as zip_file:
            assert set(zip_file.namelist()) == {"other.txt"}

    @app_decorator
    def test_flat_zip_extra_xml_no_folder(self):
        """
        Test processing of zip file that contains 3 XML files in the same directory - all should be retained.
        The additional-files.zip should contain only 'other.txt' file
        """
        self.create_flat_zip(extra_xml=True)
        processor = packages.FTPZipFlattener(self.FTP_PATH, self.pub_test)
        processor.extract_xml_pdf_rebundle_zip_or_do_nothing()

        filenames = set(os.listdir(self.FTP_PATH))
        assert filenames == {"additional-files.zip",
                             "jats.xml",
                             "extra_1.xml",
                             "extra_2.xml",
                             "file.pdf"}

        with ZipFile(self.ADDITIONAL_ZIP_PATH) as zip_file:
            assert set(zip_file.namelist()) == {"other.txt"}

    @app_decorator
    def test_flat_zip_no_folder_space_in_filename(self):
        """
        Test processing of zip file created within self.FTP_PATH directory:
            {self.FPT_PATH}/notification.zip
        The PDF and JATS file names have a space in them - which get replaced by underscores by the process
        """
        self.create_flat_zip(False, True)
        processor = packages.FTPZipFlattener(self.FTP_PATH, self.pub_test)
        processor.extract_xml_pdf_rebundle_zip_or_do_nothing()

        filenames = set(os.listdir(self.FTP_PATH))
        assert filenames == {
            "additional-files.zip",
            "jats_.xml",
            "file_.pdf"
        }

        with ZipFile(self.ADDITIONAL_ZIP_PATH) as zip_file:
            assert set(zip_file.namelist()) == {"other.txt"}

    @app_decorator
    def test_deep_zip_no_folder(self):
        self.create_deep_zip()
        processor = packages.FTPZipFlattener(self.FTP_PATH, self.pub_test)
        processor.extract_xml_pdf_rebundle_zip_or_do_nothing()

        filenames = set(os.listdir(self.FTP_PATH))
        assert filenames == {
            "additional-files.zip",
            "jats.xml",
            "file.pdf"
        }

        with ZipFile(self.ADDITIONAL_ZIP_PATH) as zip_file:
            assert set(zip_file.namelist()) == {
                "first/other.txt",
                "first/second/jats.xml",
                "first/second/file.pdf",
                "first/second/other.txt"
            }

    @app_decorator
    def test_deep_zip_no_folder_space_in_filename(self):
        self.create_deep_zip(False, True)
        processor = packages.FTPZipFlattener(self.FTP_PATH, self.pub_test)
        processor.extract_xml_pdf_rebundle_zip_or_do_nothing()

        filenames = set(os.listdir(self.FTP_PATH))
        assert filenames == {
            "additional-files.zip",
            "jats_.xml",
            "file_.pdf"
        }

        with ZipFile(self.ADDITIONAL_ZIP_PATH) as zip_file:
            assert set(zip_file.namelist()) == {
                "first/other.txt",
                "first/second/jats .xml",
                "first/second/file .pdf",
                "first/second/other.txt"
            }

    @app_decorator
    def test_zip_no_extra_files(self):
        self.create_zip_only_pdf_n_jats_xml()
        processor = packages.FTPZipFlattener(self.FTP_PATH, self.pub_test)
        processor.extract_xml_pdf_rebundle_zip_or_do_nothing()

        filenames = set(os.listdir(self.FTP_PATH))
        assert filenames == {"jats.xml", "file.pdf"}

    @app_decorator
    def test_zip_no_extra_files_space_in_filenames(self):
        """
        Only JATS XML & PDF are expected
        Spaces in filenames should be replaced by underscore '_'.
        """
        self.create_zip_only_pdf_n_jats_xml(False, True)
        processor = packages.FTPZipFlattener(self.FTP_PATH, self.pub_test)
        processor.extract_xml_pdf_rebundle_zip_or_do_nothing()

        filenames = set(os.listdir(self.FTP_PATH))
        assert filenames == {"jats_.xml", "file_.pdf"}

    @app_decorator
    def test_flat_zip_in_folder(self):
        """
        The notification.zip file is created in a directory named "folder" within self.FTP_PATH:
            {self.FPT_PATH}/folder/notification.zip
        """
        self.create_flat_zip(True)
        processor = packages.FTPZipFlattener(self.FTP_PATH, self.pub_test)
        processor.extract_xml_pdf_rebundle_zip_or_do_nothing()

        filenames = set(os.listdir(self.FTP_PATH))
        assert filenames == {
            "additional-files.zip",
            "jats.xml",
            "file.pdf"
        }

        with ZipFile(self.ADDITIONAL_ZIP_PATH) as zip_file:
            assert set(zip_file.namelist()) == {"other.txt"}

    @app_decorator
    def test_flat_zip_in_folder_space_in_filename(self):
        """
        The notification.zip file is created in a directory named "folder" within self.FTP_PATH:
            {self.FPT_PATH}/folder/notification.zip
        The PDF and JATS file names have a space in them - which get replaced by underscores by the process
        """
        self.create_flat_zip(True, True)
        processor = packages.FTPZipFlattener(self.FTP_PATH, self.pub_test)
        processor.extract_xml_pdf_rebundle_zip_or_do_nothing()

        filenames = set(os.listdir(self.FTP_PATH))
        assert filenames == {
            "additional-files.zip",
            "jats_.xml",
            "file_.pdf"
        }

        with ZipFile(self.ADDITIONAL_ZIP_PATH) as zip_file:
            assert set(zip_file.namelist()) == {"other.txt"}

    @app_decorator
    def test_zip_with_directories(self):
        path = self.create_notification_zip_path(False)
        FTPSubmissionFactory.zip_with_directories(path, dir_list=["first"], with_other=False)

        processor = packages.FTPZipFlattener(self.FTP_PATH, self.pub_test)
        processor.extract_xml_pdf_rebundle_zip_or_do_nothing()

        filenames = set(os.listdir(self.FTP_PATH))
        assert filenames == {
            "jats.xml",
            "file.pdf"
        }

    @app_decorator
    def test_deep_zip_in_folder(self):
        self.create_deep_zip(True)
        processor = packages.FTPZipFlattener(self.FTP_PATH, self.pub_test)
        processor.extract_xml_pdf_rebundle_zip_or_do_nothing()

        filenames = set(os.listdir(self.FTP_PATH))
        assert filenames == {
            "additional-files.zip",
            "jats.xml",
            "file.pdf"
        }

        with ZipFile(self.ADDITIONAL_ZIP_PATH) as zip_file:
            assert set(zip_file.namelist()) == {
                "first/other.txt",
                "first/second/jats.xml",
                "first/second/file.pdf",
                "first/second/other.txt"
            }

    @app_decorator
    def test_deep_zip_large_compressed_in_folder(self):
        self.create_deep_zip(True, large=True, compress=True)
        processor = packages.FTPZipFlattener(self.FTP_PATH, self.pub_test)
        processor.extract_xml_pdf_rebundle_zip_or_do_nothing()

        filenames = set(os.listdir(self.FTP_PATH))
        assert filenames == {
            "additional-files.zip",
            "jats.xml",
            "file.pdf"
        }

        with ZipFile(self.ADDITIONAL_ZIP_PATH) as zip_file:
            assert set(zip_file.namelist()) == {
                "first/other.txt",
                "first/second/jats.xml",
                "first/second/file.pdf",
                "first/second/other.txt"
            }

    @app_decorator
    def test_atypon_zip(self):
        """
        Test that if an Atypon format file is processed an exception is raised for having >1 XML file at same depth,
        but different directories.
        :return:
        """
        path = self.create_notification_zip_path(False)
        FTPSubmissionFactory.atypon_zip(path)

        processor = packages.FTPZipFlattener(self.FTP_PATH, self.pub_test)
        with self.assertRaises(packages.PackageException) as exc:
            processor.extract_xml_pdf_rebundle_zip_or_do_nothing()
        self.assertIn("Possible Atypon file: More than 1 XML file at same depth", str(exc.exception))

        filenames = set(os.listdir(self.FTP_PATH))
        self.assertEqual({'additional-files.zip', 'article_A0.pdf', 'jats_A0.xml', 'extra_A0.xml', 'jats_B0.xml',
                          'notification.zip'}, filenames)

    @app_decorator
    def test_process_and_zip(self):
        flattened_zip_loc = os.path.join(self.FTP_PATH, "flattened.zip")
        self.create_flat_zip()
        processor = packages.FTPZipFlattener(self.FTP_PATH, self.pub_test)
        processor.process_and_zip(flattened_zip_loc, True)

        assert set(os.listdir(self.FTP_PATH)) == {"flattened.zip"}

        with ZipFile(flattened_zip_loc) as zip_file:
            assert set(zip_file.namelist()) == {
                "additional-files.zip",
                "jats.xml",
                "file.pdf"
            }

    @app_decorator
    def test_process_and_zip_large_compressed(self):
        flattened_zip_loc = os.path.join(self.FTP_PATH, "flattened.zip")
        self.create_flat_zip(large=True, compress=True)


        ## 1 ## Test Zip file too large
        processor = packages.FTPZipFlattener(self.FTP_PATH, self.pub_test, max_zip_size=1000)
        with self.assertRaises(packages.PackageException) as exc:
            processor.process_and_zip(flattened_zip_loc, True)
        assert "Zip file too large" in str(exc.exception)

        ## 2 ## Test large file can be processed
        processor = packages.FTPZipFlattener(self.FTP_PATH, self.pub_test)
        processor.process_and_zip(flattened_zip_loc, True)

        assert set(os.listdir(self.FTP_PATH)) == {"flattened.zip"}

        with ZipFile(flattened_zip_loc) as zip_file:
            assert set(zip_file.namelist()) == {
                "additional-files.zip",
                "jats.xml",
                "file.pdf"
            }

