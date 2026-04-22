"""
Test that Octopus's StoreRemote class works with Jper's store. 
"""

import os
import shutil
from unittest import TestCase
import requests_mock
from flask import current_app
from octopus.lib.files import AlwaysBytesIO
from octopus.modules.store.store import StoreRemote, StoreException
from router.jper.app import app_decorator


class TestStore(TestCase):

    @classmethod
    @app_decorator
    def setUpClass(cls):
        shutil.rmtree("/tmp/storetests", ignore_errors=True)
        current_app.config['REMOTE_STORE_URL'] = 'http://localhost'

    @app_decorator
    def setUp(self):
        os.makedirs('/tmp/storetests')
        self.store_jper = StoreRemote()

    def tearDown(self):
        shutil.rmtree("/tmp/storetests")

    @app_decorator
    def test_0_url_path_join(self):
        # check various cases with helper function url_path_join, make sure function behaves as we'd like it to
        result = self.store_jper._url_path_join("http://testurl", "container123", "item1.pdf")
        assert result == "http://testurl/container123/item1.pdf"
        result = self.store_jper._url_path_join("http://testurl", "container123/", "item1.pdf")
        assert result == "http://testurl/container123/item1.pdf"
        result = self.store_jper._url_path_join("http://testurl", "container123", "item1.pdf/")
        assert result == "http://testurl/container123/item1.pdf/"

    @app_decorator
    def test_list(self):
        # check that behaviour of JperStore.list function is as expected
        with requests_mock.Mocker() as m:
            # upon a successful get request, list behaviour is as expected
            m.get('http://localhost/', text='["container"]')
            result = self.store_jper.list()
            assert result == ["container"]
            # if 404 encountered, we expect None as result
            m.get("http://localhost/notacontainer", status_code=404)
            result = self.store_jper.list("notacontainer")
            assert result is None
            # if we get an empty set, we expect an empty list returned, not None
            m.get('http://localhost/', text='')
            result = self.store_jper.list()
            assert result == []
            assert result is not None

    @app_decorator
    def test_get(self):
        # check that behaviour of JperStore.get is as expected
        with requests_mock.Mocker() as m:
            # if a successful get request is made, we expect our get to return a raw datafile with the get text inside
            m.get('http://localhost/container/file.pdf', text='teststring')
            result = self.store_jper.get('container', 'file.pdf')
            assert result.read() == b'teststring'
            # if we encounter a 404, we expect False to be returned
            m.get('http://localhost/container/filenotthere.pdf', status_code=404)
            result = self.store_jper.get('container', 'filenotthere.pdf')
            assert result is None

    @app_decorator
    def test_stream(self):
        with requests_mock.Mocker() as m:
            m.get('http://localhost/container/file.pdf', text='teststring')
            result = self.store_jper.stream('container', 'file.pdf')
            assert result is not False
            # The stream object should be a generator of some kind, so just finish the generator and see the outcome
            assert b''.join(list(result)) == b'teststring'
            # if we encounter a 404, we expect False to be returned
            m.get('http://localhost/container/filenotthere.pdf', status_code=404)
            result = self.store_jper.stream('container', 'filenotthere.pdf')
            assert result is None

    @app_decorator
    def test_exists(self):
        # check that behaviour of the JperStore.exists function is as expected
        with requests_mock.Mocker() as m:
            # returns True when a successful get request containing a JSON file is made
            m.get('http://localhost/container', text='["text"]')
            result = self.store_jper.container_exists('container')
            assert result is True
            # returns False when a successful get request not containing a JSON file is made
            m.get('http://localhost/container', text='')
            result = self.store_jper.container_exists('container')
            assert result is False
            # returns False when a 404 get request is made
            m.get('http://localhost/container', status_code=404)
            result = self.store_jper.container_exists('container')
            assert result is False

    @app_decorator
    def test_delete(self):
        # test that behaviour of JperStore.delete is as expected
        with requests_mock.Mocker() as m:
            m.delete('http://localhost/container/file.pdf')
            # shouldn't raise any exceptions as file successfully deletion occurred
            self.store_jper.delete('container', 'file.pdf')
            # we expect mocker raises exception as file to delete does not exist
            self.assertRaises(
                requests_mock.NoMockAddress,
                self.store_jper.delete,
                'container',
                'failfile.pdf'
            )

    # @app_decorator
    # def test_store_failed_container(self):
    #     # function checks that behaviour of JperStore.store is as expected
    #     # specifically when our initial get requests fail in store function
    #     with requests_mock.Mocker() as m:
    #         m.get('http://localhost/container', status_code=404)
    #         # upon an unsuccessful get request, (as request doesn't exist) we expect a Mocker exception raised
    #         self.assertRaisesRegex(
    #             requests_mock.NoMockAddress,
    #             "No mock address: GET http://localhost/containerfail",
    #             self.store_jper.store,
    #             'containerfail',
    #             'file.pdf'
    #         )
    #         # upon a
    #         self.assertRaisesRegex(
    #             requests_mock.NoMockAddress,
    #             "No mock address: PUT http://localhost/container",
    #             self.store_jper.store,
    #             'container',
    #             'file.pdf'
    #         )
    #         m.put('http://localhost/container')
    #         # we fail our get request, then successfully make a put(http://localhost/container)
    #         # as we have no source_path or source_stream specified, we terminate the function here with no exceptions.
    #         self.store_jper.store('container', 'file.pdf')

    @app_decorator
    def test_store_no_file_data(self):
        # we check that behaviour is as expected when no file data is present
        with self.assertRaises(StoreException):
            # if we pass our initial get request but have no source_path or source_stream specified,
            # we expect an exception to be raised
            self.store_jper.store('container', 'file.pdf')


    @app_decorator
    def test_store_source_path(self):
        # we check that behaviour is as expected when we have a source path specified
        with requests_mock.Mocker() as m:
            # assume get request passes, we covered situations in which it didn't in previous tests
            m.get('http://localhost/container')
            # in store, we make a successful get request, then as there is no data_source specified,
            # we attempt a post request in /container/file.pdf, which doesn't exist
            with open('/tmp/storetests/here.pdf', 'w') as file_stream:
                file_stream.write("Test")

            self.assertRaisesRegex(
                requests_mock.NoMockAddress,
                "No mock address: POST http://localhost/container/file.pdf",
                self.store_jper.store,
                'container',
                'file.pdf',
                source_path='/tmp/storetests/here.pdf'
            )
            # if our post succeeds, the function will successfully terminate
            m.post('http://localhost/container/file.pdf')
            self.store_jper.store('container', 'file.pdf', source_path='/tmp/storetests/here.pdf')

    @app_decorator
    def test_store_source_stream(self):
        # we check that behaviour is as expected when source_path unspecified, but source_stream specified
        with requests_mock.Mocker() as m:
            m.get('http://localhost/container')
            stream = AlwaysBytesIO("Test")
            # we attempt a post but fail as it hasn't happened
            self.assertRaisesRegex(
                requests_mock.NoMockAddress,
                "No mock address: POST http://localhost/container/file.pdf",
                self.store_jper.store,
                'container',
                'file.pdf',
                source_stream=stream
            )
            m.post('http://localhost/container/file.pdf')
            self.store_jper.store(
                'container',
                'file.pdf',
                source_stream=stream
            )
