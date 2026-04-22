from router.harvester.engine.QueryEngine import QueryEngine

class TestQueryEngine:

    def test_auth_ids(self):
        orcid = ("ORCID", "1234")
        orcid_url = ("ORCID", "http://orcid.org/1234")
        not_orcid = ("NOTORCID", "http://orcid.org/1234")

        assert QueryEngine._process_author_id(*orcid) == {"type": "orcid", "id": "1234"}
        assert QueryEngine._process_author_id(*orcid_url) == {"type": "orcid", "id": "1234"}
        assert QueryEngine._process_author_id(*not_orcid) == {"type": "notorcid", "id": "http://orcid.org/1234"}
        assert QueryEngine._process_author_id(None, None) is None
