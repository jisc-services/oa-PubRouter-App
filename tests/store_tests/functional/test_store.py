"""
Tests whether the various store methods (namely PUT, POST, GET and DELETE) work as expected
"""

import os
import unittest
import shutil
import json
from io import BytesIO
from router.store.app import app

class TestStore(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        shutil.rmtree("/tmp/storetests", ignore_errors=True)
        app.config['STORE_MAIN_DIR'] = '/tmp/storetests'
        app.config['LOGFILE'] = '/tmp/store.log'

    def setUp(self):
        self.test_client = app.test_client()
        os.makedirs('/tmp/storetests')

    def tearDown(self):
        shutil.rmtree('/tmp/storetests')
        if os.path.exists("/tmp/store.log"):
            os.remove('/tmp/store.log')

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree("/tmp/storetests", ignore_errors=True)

    def test_0_get_from_empty_store(self):
        # check that when getting from an empty store we are returned with an empty JSON object
        response = self.test_client.get("/")
        assert response.data == b'[]'
        assert response.status_code == 200

    def test_1_put_container_empty_store(self):
        # put a container in an empty store, check that behaviour is as expected
        # check an acceptable put succeeds with a 200 status code
        response = self.test_client.put("/container")
        assert response.status_code == 200
        # check that after putting something into our store, a get returns all of the expected items
        response = self.test_client.get("/")
        assert response.data == b'["container"]'
        # check that put will fail with 400 if there already exists a container of that name
        response = self.test_client.put("/container")
        assert response.status_code == 400

    def test_2_post_filestream(self):
        # check post works with a filestream, we expect a 200 status code because of success
        response = self.test_client.post("/file.txt", data={
            'file': (BytesIO(b"text"), "file.txt")
        })
        assert response.status_code == 200
        # check that a get subsequent to our post yields a status_code of 200 and the expected file content
        response = self.test_client.get("/")
        assert response.status_code == 200
        assert response.data == b'["file.txt"]'
        # look inside of the actual file, we find the content is as expected, the string "text"
        response = self.test_client.get("/file.txt")
        assert response.status_code == 200
        assert response.data == b'text'

    def test_3_post_jsondata(self):
        # post will work also with JSON data, we expect a 200 status code from our post request
        response = self.test_client.post(
            "/metadata.json",
            data=json.dumps(["my_json_file"]),
            content_type="application/json"
        )
        assert response.status_code == 200
        # check that our JSON file is stored inside the store after our post
        response = self.test_client.get("/metadata.json")
        assert response.status_code == 200
        assert response.data == b'["my_json_file"]'

    def test_4_delete_non_empty_store(self):
        # post some data for us to delete and check that this has succeeded
        response = self.test_client.post("/file.txt", data={
            'file': (BytesIO(b"text"), "file.txt")
        })
        assert response.status_code == 200
        # check that delete works as expected and returns a 200 status code
        response = self.test_client.delete("/file.txt")
        assert response.status_code == 200
        # now that we've deleted the item, a get request to that address should fail with a 404
        response = self.test_client.get("/file.txt")
        assert response.status_code == 404


if __name__ == '__main__':
    unittest.main()
