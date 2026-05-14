
from copy import deepcopy
from flask import current_app
from octopus.modules.testing.compare import compare_dict_ignore_list_order
from router.harvester.app import app_decorator
from router.harvester.engine.QueryEngineEPMC import QueryEngineEPMC
from tests.harvester_tests.test_engine.query_engine_test_base import QueryEngineTest
from tests.harvester_tests.fixtures.test_data import epmc_json_dict, epmc__old_dates_json_dict

docRouterExpected = {
    'has_pdf': True,
    'links': [{
            'url': 'https://www.ncbi.nlm.nih.gov/pmc/articles/PMC7487765/?tool=EBI',
            'type': 'fulltext',
            'format': 'text/html',
            'access': 'public'
        },
        {
            'url': 'https://www.ncbi.nlm.nih.gov/pmc/articles/PMC7487765/pdf/?tool=EBI',
            'type': 'fulltext',
            'format': 'application/pdf',
            'access': 'public'
        },
        {
            'url': 'https://europepmc.org/articles/PMC7487765',
            'type': 'fulltext',
            'format': 'text/html',
            'access': 'public'
        },
        {
            'url': 'https://europepmc.org/articles/PMC7487765?pdf=render',
            'type': 'fulltext',
            'format': 'application/pdf',
            'access': 'public'
        }
    ],
    "provider": {
        'agent': 'EPMC',
        'harv_id': 88,
        'route': 'harv',
        'rank': 2
    },
    'metadata': {
        'journal': {
            'volume': '7',
            'issue': '9',
            'title': 'The lancet. <h2>HIV</h2>',
            'abbrev_title': 'Lancet HIV',
            'identifier': [{
                    'id': '2405-4704',
                    'type': 'issn'
                }, {
                    'id': '2352-3018',
                    'type': 'essn'
                },
                {
                    'id': '101645355',
                    'type': 'nlmid'
                }
            ]
        },
        'history_date': [{
            'date_type': 'epub',
            'date': '2020-09-01'
        }, {
            'date_type': 'ppub',
            'date': '2020-09-01'
        }],
        'publication_date': {
            'year': '2020',
            'month': '09',
            'day': '01',
            'date': '2020-09-01',
            'publication_format': 'electronic'
        },
        'publication_status': 'Published',
        'article': {
            'title': '<h1>Virological failure</h1>, HIV-1 drug resistance, and early mortality in adults admitted to hospital in Malawi: an observational cohort study',
            'type': 'research-article; Journal Article',
            'page_range': 'e620-e628',
            'start_page': 'e620',
            'end_page': 'e628',
            'language': ['eng'],
            'abstract': '<h1>Summary Background</h1> Antiretroviral therapy (ART) scale-up in sub-Saharan Africa combined with weak routine virological monitoring has driven increasing HIV drug resistance. We investigated ART failure, drug resistance, and early mortality among patients with HIV admitted to hospital in Malawi. Methods This observational cohort study was nested within the rapid urine-based screening for tuberculosis to reduce AIDS-related mortality in hospitalised patients in Africa (STAMP) trial, which recruited unselected (ie, irrespective of clinical presentation) adult (aged ≥18 years) patients with HIV-1 at admission to medical wards. Patients were included in our observational cohort study if they were enrolled at the Malawi site (Zomba Central Hospital) and were taking ART for at least 6 months at admission. Patients who met inclusion criteria had frozen plasma samples tested for HIV-1 viral load. Those with HIV-1 RNA of at least 1000 copies per mL had drug resistance testing by ultra-deep sequencing, with drug resistance defined as intermediate or high-level resistance using the Stanford HIVDR program. Mortality risk was calculated 56 days from enrolment. Patients were censored at death, at 56 days, or at last contact if lost to follow-up. The modelling strategy addressed the causal association between HIV multidrug resistance and mortality, excluding factors on the causal pathway (most notably, CD4 cell count, clinical signs of advanced HIV, and poor functional and nutritional status). Findings Of 1316 patients with HIV enrolled in the STAMP trial at the Malawi site between Oct 26, 2015, and Sept 19, 2017, 786 had taken ART for at least 6 months. 252 (32%) of 786 patients had virological failure (viral load ≥1000 copies per mL). Mean age was 41·5 years (SD 11·4) and 528 (67%) of 786 were women. Of 237 patients with HIV drug resistance results available, 195 (82%) had resistance to lamivudine, 128 (54%) to tenofovir, and 219 (92%) to efavirenz. Resistance to at least two drugs was common (196, 83%), and this was associated with increased mortality (adjusted hazard ratio 1·7, 95% CI 1·2–2·4; p=0·0042). Interpretation Interventions are urgently needed and should target ART clinic, hospital, and post-hospital care, including differentiated care focusing on patients with advanced HIV, rapid viral load testing, and routine access to drug resistance testing. Prompt diagnosis and switching to alternative ART could reduce early mortality among inpatients with HIV. Funding Joint Global Health Trials Scheme of the Medical Research Council, UK Department for International Development, and Wellcome Trust.',
            'identifier': [{
                'id': 'PMC7487765',
                'type': 'pmcid'
            }]
        },
        'author': [{
                'name': {
                    'firstname': 'Ankur',
                    'surname': 'Gupta-Wright',
                    'fullname': 'Gupta-Wright A'
                },
                'affiliations': [{'raw': 'd Malawi-Liverpool-Wellcome Trust Clinical Research Programme, University of Malawi College of Medicine, Blantyre, Malawi'}],
                'identifier': [{
                    'type': 'orcid',
                    'id': '0000-0002-5150-2970'
                }]
            },
            {
                'name': {
                    'firstname': 'Katherine',
                    'surname': 'Fielding',
                    'fullname': 'Fielding K'
                },
                'affiliations': [{'raw': 'f School of Public Health, University of the Witwatersrand, Johannesburg, South Africa'}]
            },
            {
                'name': {
                    'firstname': 'Joep J',
                    'surname': 'van Oosterhout',
                    'fullname': 'van Oosterhout J'
                },
                'affiliations': [{'raw': 'g Dignitas International, Zomba, Malawi'}]
            },
            {
                'name': {
                    'firstname': 'Judith',
                    'surname': 'Heaney',
                    'fullname': 'Heaney J'
                },
                'affiliations': [{'raw': 'h Advanced Pathogen Diagnostics Unit, University College London Hospitals NHS Foundation Trust, London, UK'}]
            },
            {
                'name': {
                    'firstname': 'Matthew',
                    'surname': 'Byott',
                    'fullname': 'Byott M'
                },
                'affiliations': [{'raw': 'h Advanced Pathogen Diagnostics Unit, University College London Hospitals NHS Foundation Trust, London, UK'}]
            }
        ],
        'funding': [{
            'name': 'Wellcome Trust',
            'grant_numbers': ['WT200901/Z/16/Z']
        }],
        'license_ref': [{
            'type': 'cc by',
            'title': 'cc by'
        }]
    }
}


def pub_date_mock(date):
    return {
        "electronicPublicationDate": date,
        "firstPublicationDate": date,
        "journalInfo": {
            "printPublicationDate": date
        }
    }

def print_pub_date_mock(date):
    return {
        "journalInfo": {
            "printPublicationDate": date
        }
    }

EPMC_URL = 'https://www.ebi.ac.uk/europepmc/webservices/rest/search/resulttype=core&format=json&query=malaria%20CREATION_DATE%3A%5B{start_date}%20TO%20{end_date}%5D'

HARVESTER_ID = 'test_epmc'

class TestQueryEngineEPMC(QueryEngineTest):

    @app_decorator
    def test_simple_import(self):
        end_date = self.date_today.replace(month=11,day=20)
        start_date = self.date_today.replace(month=11,day=20)
        epmc_engine = QueryEngineEPMC(self.es_db, EPMC_URL, HARVESTER_ID, start_date, end_date, name_ws="EPMC")
        epmc_engine.create_harvester_ix()
        number_of_result = epmc_engine.execute()
        self.assertTrue(number_of_result >= 0)
        epmc_engine.delete_harvester_ix()

    @app_decorator
    def test_default_value(self):
        epmc_engine = QueryEngineEPMC(self.es_db, EPMC_URL, HARVESTER_ID, name_ws="EPMC")
        epmc_engine.create_harvester_ix()
        number_of_result = epmc_engine.execute()
        self.assertTrue(number_of_result >= 0)
        epmc_engine.delete_harvester_ix()

    @app_decorator
    def test_publication_dates(self):
        engine = QueryEngineEPMC(self.es_db, EPMC_URL, HARVESTER_ID, name_ws="EPMC")

        july_sixteen = ["2016-07", "electronic", "2016", "07"]
        seven_july_sixteen = ["2016-07-07", "electronic", "2016", "07", "07"]
        old_date =  ["1887-10-07", "print", "1887", "10", "07"]

        assert ["2015", "electronic", "2015"] == engine._get_publication_date(pub_date_mock("2015"), "2015", "2015")
        assert july_sixteen == engine._get_publication_date(pub_date_mock("2016-07"), "2016-07", "2016-07")
        assert july_sixteen == engine._get_publication_date(pub_date_mock("2016-7"), "2016-7", "2016-7")
        assert seven_july_sixteen == engine._get_publication_date(pub_date_mock("2016-07-07"), "2016-07-07", "2016-07-07")
        assert seven_july_sixteen == engine._get_publication_date(pub_date_mock("2016-7-7"), "2016-7-7", "2016-7-7")
        assert ["2015", "print", "2015"] == engine._get_publication_date(print_pub_date_mock("2015"), None, "2015")
        assert old_date == engine._get_publication_date(print_pub_date_mock("1887-10-07"), None, "1887-10-07")
        pass

    @app_decorator
    def test_full_notification(self):
        current_app.logger.info("Test full document")
        notification_dict = QueryEngineEPMC(self.es_db, EPMC_URL, HARVESTER_ID, name_ws="EPMC").convert_to_notification(epmc_json_dict, 88)
        self.maxDiff = None
        # print(sorted(notification_dict.items()))
        # print(sorted(docRouterExpected.items()))
        assert compare_dict_ignore_list_order(notification_dict, docRouterExpected)

    @app_decorator
    def test_full_notification_old_dates(self):
        """
        Test with an EPMC record containing publication dates of 1873

        :return:
        """
        current_app.logger.info("Test full EPMC document with publication dates in 1873")
        oldDocRouterExpected = deepcopy(docRouterExpected)
        oldDocRouterExpected["metadata"]["publication_date"]["year"] = "1873"
        oldDocRouterExpected["metadata"]["publication_date"]["month"] = "07"
        oldDocRouterExpected["metadata"]["publication_date"]["day"] = "10"
        oldDocRouterExpected["metadata"]["publication_date"]["date"] = "1873-07-10"
        oldDocRouterExpected["metadata"]["history_date"][0]["date"] = "1873-07-10"
        oldDocRouterExpected["metadata"]["history_date"][1]["date"] = "1873-01-01"

        notification_dict = QueryEngineEPMC(self.es_db, EPMC_URL, HARVESTER_ID, name_ws="EPMC").convert_to_notification(epmc__old_dates_json_dict, 88)
        self.maxDiff = None
        # print(sorted(notification_dict.items()))
        # print(sorted(oldDocRouterExpected.items()))
        assert compare_dict_ignore_list_order(notification_dict, oldDocRouterExpected)

