"""
test_data.py

File contains fixed test data structures
"""
import json
from copy import deepcopy


# epmc_has_affiliation = json.dumps({
#     "query": {
#         "bool": {
#             "must": {
#                 "exists": {"field": "authorList.author.affiliation"}
#             }
#         }
#     }
# })

epmc_api_search_2_results_json_dict = {
    "version": "6.4",
    "hitCount": 2,
    "nextCursorMark": "AoIIQAY21Cg0MjAwODc2NA==",
    "request": {
        "queryString": " CREATION_DATE:[\"2020-08-07\" TO 2020-08-07] & OPEN_ACCESS:y & HAS_PDF:y",
        "resultType": "core",
        "cursorMark": "*",
        "pageSize": 5,
        "sort": "",
        "synonym": False
    },
    "resultList": {
        "result": [{
                "id": "PMC7487765",
                "source": "PMC",
                "pmcid": "PMC7487765",
                "fullTextIdList": {
                    "fullTextId": [
                        "PMC7487765"
                    ]
                },
                "title": "<h1>Virological failure</h1>, HIV-1 drug resistance, and early mortality in adults admitted to hospital in Malawi: an observational cohort study",
                "authorString": "Gupta-Wright A, Fielding K, van Oosterhout J, Alufandika M, Grint D, Chimbayo E, Heaney J, Byott M, Nastouli E, Mwandumba H, Corbett E, Gupta R.",
                "authorList": {
                    "author": [
                        {
                            "fullName": "Gupta-Wright A",
                            "firstName": "Ankur",
                            "lastName": "Gupta-Wright",
                            "initials": "A",
                            "authorId": {
                                "type": "ORCID",
                                "value": "0000-0002-5150-2970"
                            },
                            "authorAffiliationDetailsList": {
                                "authorAffiliation": [{
                                    "affiliation": "d Malawi-Liverpool-Wellcome Trust Clinical Research Programme, University of Malawi College of Medicine, Blantyre, Malawi"
                                }]
                            }
                        },
                        {
                            "fullName": "Fielding K",
                            "firstName": "Katherine",
                            "lastName": "Fielding",
                            "initials": "K",
                            "authorAffiliationDetailsList": {
                                "authorAffiliation": [{
                                    "affiliation": "f School of Public Health, University of the Witwatersrand, Johannesburg, South Africa"
                                }]
                            }
                        },
                        {
                            "fullName": "van Oosterhout J",
                            "firstName": "Joep J",
                            "lastName": "van Oosterhout",
                            "initials": "J",
                            "authorAffiliationDetailsList": {
                                "authorAffiliation": [{
                                    "affiliation": "g Dignitas International, Zomba, Malawi"
                                }]
                            }
                        },
                        {
                            "fullName": "Heaney J",
                            "firstName": "Judith",
                            "lastName": "Heaney",
                            "initials": "J",
                            "authorAffiliationDetailsList": {
                                "authorAffiliation": [{
                                    "affiliation": "h Advanced Pathogen Diagnostics Unit, University College London Hospitals NHS Foundation Trust, London, UK"
                                }]
                            }
                        },
                        {
                            "fullName": "Byott M",
                            "firstName": "Matthew",
                            "lastName": "Byott",
                            "initials": "M",
                            "authorAffiliationDetailsList": {
                                "authorAffiliation": [{
                                    "affiliation": "h Advanced Pathogen Diagnostics Unit, University College London Hospitals NHS Foundation Trust, London, UK"
                                }]
                            }
                        }
                    ]
                },
                "authorIdList": {
                    "authorId": [
                        {
                            "type": "ORCID",
                            "value": "0000-0002-5150-2970"
                        }
                    ]
                },
                "dataLinksTagsList": {
                    "dataLinkstag": [
                        "supporting_data"
                    ]
                },
                "journalInfo": {
                    "issue": "9",
                    "volume": "7",
                    "journalIssueId": 3007693,
                    "dateOfPublication": "2020 Sep",
                    "monthOfPublication": 9,
                    "yearOfPublication": 2020,
                    "printPublicationDate": "2020-09-01",
                    "journal": {
                        "title": "The lancet. <h2>HIV</h2>",
                        "medlineAbbreviation": "Lancet HIV",
                        "essn": "2352-3018",
                        "issn": "2405-4704",
                        "isoabbreviation": "Lancet HIV",
                        "nlmid": "101645355"
                    }
                },
                "pubYear": "2020",
                "pageInfo": "e620-e628",
                "abstractText": "<h1>Summary Background</h1> Antiretroviral therapy (ART) scale-up in sub-Saharan Africa combined with weak routine virological monitoring has driven increasing HIV drug resistance. We investigated ART failure, drug resistance, and early mortality among patients with HIV admitted to hospital in Malawi. Methods This observational cohort study was nested within the rapid urine-based screening for tuberculosis to reduce AIDS-related mortality in hospitalised patients in Africa (STAMP) trial, which recruited unselected (ie, irrespective of clinical presentation) adult (aged ≥18 years) patients with HIV-1 at admission to medical wards. Patients were included in our observational cohort study if they were enrolled at the Malawi site (Zomba Central Hospital) and were taking ART for at least 6 months at admission. Patients who met inclusion criteria had frozen plasma samples tested for HIV-1 viral load. Those with HIV-1 RNA of at least 1000 copies per mL had drug resistance testing by ultra-deep sequencing, with drug resistance defined as intermediate or high-level resistance using the Stanford HIVDR program. Mortality risk was calculated 56 days from enrolment. Patients were censored at death, at 56 days, or at last contact if lost to follow-up. The modelling strategy addressed the causal association between HIV multidrug resistance and mortality, excluding factors on the causal pathway (most notably, CD4 cell count, clinical signs of advanced HIV, and poor functional and nutritional status). Findings Of 1316 patients with HIV enrolled in the STAMP trial at the Malawi site between Oct 26, 2015, and Sept 19, 2017, 786 had taken ART for at least 6 months. 252 (32%) of 786 patients had virological failure (viral load ≥1000 copies per mL). Mean age was 41·5 years (SD 11·4) and 528 (67%) of 786 were women. Of 237 patients with HIV drug resistance results available, 195 (82%) had resistance to lamivudine, 128 (54%) to tenofovir, and 219 (92%) to efavirenz. Resistance to at least two drugs was common (196, 83%), and this was associated with increased mortality (adjusted hazard ratio 1·7, 95% CI 1·2–2·4; p=0·0042). Interpretation Interventions are urgently needed and should target ART clinic, hospital, and post-hospital care, including differentiated care focusing on patients with advanced HIV, rapid viral load testing, and routine access to drug resistance testing. Prompt diagnosis and switching to alternative ART could reduce early mortality among inpatients with HIV. Funding Joint Global Health Trials Scheme of the Medical Research Council, UK Department for International Development, and Wellcome Trust.",
                "language": "eng",
                "pubModel": "Undetermined",
                "pubTypeList": {
                    "pubType": [
                        "research-article",
                        "Journal Article"
                    ]
                },
                "grantsList": {
                    "grant": [
                        {
                            "grantId": "WT200901/Z/16/Z",
                            "agency": "Wellcome Trust",
                            "orderIn": 0
                        }
                    ]
                },
                "fullTextUrlList": {
                    "fullTextUrl": [
                        {
                            "availability": "Free",
                            "availabilityCode": "F",
                            "documentStyle": "html",
                            "site": "PubMedCentral",
                            "url": "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC7487765/?tool=EBI"
                        },
                        {
                            "availability": "Free",
                            "availabilityCode": "F",
                            "documentStyle": "pdf",
                            "site": "PubMedCentral",
                            "url": "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC7487765/pdf/?tool=EBI"
                        },
                        {
                            "availability": "Free",
                            "availabilityCode": "F",
                            "documentStyle": "html",
                            "site": "Europe_PMC",
                            "url": "https://europepmc.org/articles/PMC7487765"
                        },
                        {
                            "availability": "Free",
                            "availabilityCode": "F",
                            "documentStyle": "pdf",
                            "site": "Europe_PMC",
                            "url": "https://europepmc.org/articles/PMC7487765?pdf=render"
                        }
                    ]
                },
                "isOpenAccess": "Y",
                "inEPMC": "Y",
                "inPMC": "Y",
                "hasPDF": "Y",
                "hasBook": "N",
                "hasSuppl": "Y",
                "citedByCount": 0,
                "hasData": "Y",
                "hasReferences": "N",
                "hasTextMinedTerms": "Y",
                "hasDbCrossReferences": "N",
                "hasLabsLinks": "N",
                "license": "cc by",
                "authMan": "N",
                "epmcAuthMan": "N",
                "nihAuthMan": "N",
                "hasTMAccessionNumbers": "Y",
                "tmAccessionTypeList": {
                    "accessionType": [
                        "doi"
                    ]
                },
                "dateOfCreation": "2020-09-20",
                "firstIndexDate": "2020-09-23",
                "fullTextReceivedDate": "2020-09-20",
                "dateOfRevision": "2020-09-29",
                "electronicPublicationDate": "2020-09-01",
                "firstPublicationDate": "2020-09-01"
            },
            {
                "id": "32948688",
                "source": "MED",
                "pmid": "32948688",
                "pmcid": "PMC7502863",
                "fullTextIdList": {
                    "fullTextId": [
                        "PMC7502863"
                    ]
                },
                "doi": "10.1128/mbio.02243-20",
                "title": "Impaired Cytotoxic CD8+ T Cell Response in Elderly COVID-19 Patients.",
                "authorString": "Westmeier J, Paniskaki K, Karaköse Z, Werner T, Sutter K, Dolff S, Overbeck M, Limmer A, Liu J, Zheng X, Brenner T, Berger MM, Witzke O, Trilling M, Lu M, Yang D, Babel N, Westhoff T, Dittmer U, Zelinskyy G.",
                "authorList": {
                    "author": [
                        {
                            "fullName": "Westmeier J",
                            "firstName": "Jaana",
                            "lastName": "Westmeier",
                            "initials": "J",
                            "authorAffiliationDetailsList": {
                                "authorAffiliation": [{
                                    "affiliation": "Institute for Virology, University Hospital Essen, University of Duisburg-Essen, Essen, Germany."
                                }]
                            }
                        },
                        {
                            "fullName": "Berger MM",
                            "firstName": "Marc M",
                            "lastName": "Berger",
                            "initials": "MM",
                            "authorId": {
                                "type": "ORCID",
                                "value": "0000-0001-6771-3193"
                            },
                            "authorAffiliationDetailsList": {
                                "authorAffiliation": [{
                                    "affiliation": "Department of Anesthesiology, University Hospital Essen, University Duisburg-Essen, Essen, Germany."
                                }]
                            }
                        },
                        {
                            "fullName": "Witzke O",
                            "firstName": "Oliver",
                            "lastName": "Witzke",
                            "initials": "O",
                            "authorAffiliationDetailsList": {
                                "authorAffiliation": [{
                                    "affiliation": "Department of Infectious Diseases, West German Centre of Infectious Diseases, University Hospital Essen, University Duisburg-Essen, Essen, Germany."
                                }]
                            }
                        },
                        {
                            "fullName": "Trilling M",
                            "firstName": "Mirko",
                            "lastName": "Trilling",
                            "initials": "M",
                            "authorId": {
                                "type": "ORCID",
                                "value": "0000-0003-3659-3541"
                            },
                            "authorAffiliationDetailsList": {
                                "authorAffiliation": [{
                                    "affiliation": "Institute for Virology, University Hospital Essen, University of Duisburg-Essen, Essen, Germany."},{
                                    "affiliation": "Joint International Laboratory of Infection and Immunity, HUST, Wuhan, China."
                                }]
                            }
                        },
                        {
                            "fullName": "Zelinskyy G",
                            "firstName": "Gennadiy",
                            "lastName": "Zelinskyy",
                            "initials": "G",
                            "authorAffiliationDetailsList": {
                                "authorAffiliation": [{
                                    "affiliation": "Institute for Virology, University Hospital Essen, University of Duisburg-Essen, Essen, Germany ulf.dittmer@uni-due.de gennadiy.zelinskyy@uni-due.de."},{
                                    "affiliation": "Joint International Laboratory of Infection and Immunity, HUST, Wuhan, China."
                                }]
                            }
                        }
                    ]
                },
                "authorIdList": {
                    "authorId": [
                        {
                            "type": "ORCID",
                            "value": "0000-0001-6771-3193"
                        },
                        {
                            "type": "ORCID",
                            "value": "0000-0003-3659-3541"
                        }
                    ]
                },
                "journalInfo": {
                    "issue": "5",
                    "volume": "11",
                    "journalIssueId": 3004594,
                    "dateOfPublication": "2020 Sep",
                    "monthOfPublication": 9,
                    "yearOfPublication": 2020,
                    "printPublicationDate": "2020-09-01",
                    "journal": {
                        "title": "mBio",
                        "medlineAbbreviation": "mBio",
                        "essn": "2150-7511",
                        "issn": "2150-7511",
                        "isoabbreviation": "mBio",
                        "nlmid": "101519231"
                    }
                },
                "pubYear": "2020",
                "abstractText": "Severe acute respiratory syndrome coronavirus 2 (SARS-CoV-2) infection induces a T cell response that most likely contributes to virus control in COVID-19 patients but may also induce immunopathology. Until now, the cytotoxic T cell response has not been very well characterized in COVID-19 patients. Here, we analyzed the differentiation and cytotoxic profile of T cells in 30 cases of mild COVID-19 during acute infection. SARS-CoV-2 infection induced a cytotoxic response of CD8+ T cells, but not CD4+ T cells, characterized by the simultaneous production of granzyme A and B as well as perforin within different effector CD8+ T cell subsets. PD-1-expressing CD8+ T cells also produced cytotoxic molecules during acute infection, indicating that they were not functionally exhausted. However, in COVID-19 patients over the age of 80 years, the cytotoxic T cell potential was diminished, especially in effector memory and terminally differentiated effector CD8+ cells, showing that elderly patients have impaired cellular immunity against SARS-CoV-2. Our data provide valuable information about T cell responses in COVID-19 patients that may also have important implications for vaccine development.IMPORTANCE Cytotoxic T cells are responsible for the elimination of infected cells and are key players in the control of viruses. CD8+ T cells with an effector phenotype express cytotoxic molecules and are able to perform target cell killing. COVID-19 patients with a mild disease course were analyzed for the differentiation status and cytotoxic profile of CD8+ T cells. SARS-CoV-2 infection induced a vigorous cytotoxic CD8+ T cell response. However, this cytotoxic profile of T cells was not detected in COVID-19 patients over the age of 80 years. Thus, the absence of a cytotoxic response in elderly patients might be a possible reason for the more frequent severity of COVID-19 in this age group than in younger patients.",
                "affiliation": "Institute for Virology, University Hospital Essen, University of Duisburg-Essen, Essen, Germany.",
                "publicationStatus": "epublish",
                "language": "eng",
                "pubModel": "Electronic",
                "pubTypeList": {
                    "pubType": [
                        "Research Support, Non-U.S. Gov't",
                        "research-article",
                        "Journal Article"
                    ]
                },
                "keywordList": {
                    "keyword": [
                        "Aging",
                        "Perforin",
                        "Cytotoxic T cells",
                        "PD-1",
                        "Cd4+",
                        "Granzyme",
                        "Cd8+",
                        "Covid-19",
                        "Sars-cov-2"
                    ]
                },
                "subsetList": {
                    "subset": [
                        {
                            "code": "IM",
                            "name": "Index Medicus"
                        }
                    ]
                },
                "fullTextUrlList": {
                    "fullTextUrl": [
                        {
                            "availability": "Subscription required",
                            "availabilityCode": "S",
                            "documentStyle": "doi",
                            "site": "DOI",
                            "url": "https://doi.org/10.1128/mBio.02243-20"
                        },
                        {
                            "availability": "Open access",
                            "availabilityCode": "OA",
                            "documentStyle": "html",
                            "site": "Europe_PMC",
                            "url": "https://europepmc.org/articles/PMC7502863"
                        },
                        {
                            "availability": "Open access",
                            "availabilityCode": "OA",
                            "documentStyle": "pdf",
                            "site": "Europe_PMC",
                            "url": "https://europepmc.org/articles/PMC7502863?pdf=render"
                        }
                    ]
                },
                "commentCorrectionList": {
                    "commentCorrection": [
                        {
                            "id": "PPR204727",
                            "source": "PPR",
                            "type": "Preprint in",
                            "note": "Link created based on a title-first author match",
                            "orderIn": 10002
                        }
                    ]
                },
                "isOpenAccess": "Y",
                "inEPMC": "Y",
                "inPMC": "N",
                "hasPDF": "Y",
                "hasBook": "N",
                "hasSuppl": "N",
                "citedByCount": 0,
                "hasData": "N",
                "hasReferences": "N",
                "hasTextMinedTerms": "Y",
                "hasDbCrossReferences": "N",
                "hasLabsLinks": "N",
                "license": "cc by",
                "authMan": "N",
                "epmcAuthMan": "N",
                "nihAuthMan": "N",
                "hasTMAccessionNumbers": "N",
                "dateOfCreation": "2020-09-19",
                "firstIndexDate": "2020-09-23",
                "fullTextReceivedDate": "2020-09-28",
                "dateOfRevision": "2020-09-26",
                "electronicPublicationDate": "2020-09-18",
                "firstPublicationDate": "2020-09-18"
            }
        ]
    }
}

# JSON as returned by EPMC API call
epmc_api_search_2_results_json = json.dumps(epmc_api_search_2_results_json_dict)

# JSON as returned by EPMC API call - but with NO affiliations or ORCIDS or funder info
epmc_api_search_2_results_nomatch_json = json.dumps({
    "version": "6.4",
    "hitCount": 2,
    "nextCursorMark": "AoIIQAY21Cg0MjAwODc2NA==",
    "request": {
        "queryString": " CREATION_DATE:[\"2020-08-07\" TO 2020-08-07] & OPEN_ACCESS:y & HAS_PDF:y",
        "resultType": "core",
        "cursorMark": "*",
        "pageSize": 5,
        "sort": "",
        "synonym": False
    },
    "resultList": {
        "result": [{
                "id": "PMC7487765",
                "source": "PMC",
                "pmcid": "PMC7487765",
                "fullTextIdList": {
                    "fullTextId": [
                        "PMC7487765"
                    ]
                },
                "title": "Virological failure, HIV-1 drug resistance, and early mortality in adults admitted to hospital in Malawi: an observational cohort study",
                "authorString": "Gupta-Wright A, Fielding K, van Oosterhout J, Alufandika M, Grint D, Chimbayo E, Heaney J, Byott M, Nastouli E, Mwandumba H, Corbett E, Gupta R.",
                "authorList": {
                    "author": [
                        {
                            "fullName": "Gupta-Wright A",
                            "firstName": "Ankur",
                            "lastName": "Gupta-Wright",
                            "initials": "A",
                            "authorAffiliationDetailsList": {
                                "authorAffiliation": [
                                ]
                            }
                        },
                        {
                            "fullName": "Fielding K",
                            "firstName": "Katherine",
                            "lastName": "Fielding",
                            "initials": "K",
                            "authorAffiliationDetailsList": {
                                "authorAffiliation": [
                                ]
                            }
                        },
                        {
                            "fullName": "van Oosterhout J",
                            "firstName": "Joep J",
                            "lastName": "van Oosterhout",
                            "initials": "J",
                            "authorAffiliationDetailsList": {
                                "authorAffiliation": [
                                ]
                            }
                        }
                    ]
                },
                "authorIdList": {
                    "authorId": [
                    ]
                },
                "dataLinksTagsList": {
                    "dataLinkstag": [
                        "supporting_data"
                    ]
                },
                "journalInfo": {
                    "issue": "9",
                    "volume": "7",
                    "journalIssueId": 3007693,
                    "dateOfPublication": "2020 Sep",
                    "monthOfPublication": 9,
                    "yearOfPublication": 2020,
                    "printPublicationDate": "2020-09-01",
                    "journal": {
                        "title": "The lancet. HIV",
                        "medlineAbbreviation": "Lancet HIV",
                        "essn": "2352-3018",
                        "issn": "2405-4704",
                        "isoabbreviation": "Lancet HIV",
                        "nlmid": "101645355"
                    }
                },
                "pubYear": "2020",
                "pageInfo": "e620-e628",
                "abstractText": "Summary Background Antiretroviral therapy (ART) scale-up in sub-Saharan Africa combined with weak routine virological monitoring has driven increasing HIV drug resistance. We investigated ART failure, drug resistance, and early mortality among patients with HIV admitted to hospital in Malawi. Methods This observational cohort study was nested within the rapid urine-based screening for tuberculosis to reduce AIDS-related mortality in hospitalised patients in Africa (STAMP) trial, which recruited unselected (ie, irrespective of clinical presentation) adult (aged ≥18 years) patients with HIV-1 at admission to medical wards. Patients were included in our observational cohort study if they were enrolled at the Malawi site (Zomba Central Hospital) and were taking ART for at least 6 months at admission. Patients who met inclusion criteria had frozen plasma samples tested for HIV-1 viral load. Those with HIV-1 RNA of at least 1000 copies per mL had drug resistance testing by ultra-deep sequencing, with drug resistance defined as intermediate or high-level resistance using the Stanford HIVDR program. Mortality risk was calculated 56 days from enrolment. Patients were censored at death, at 56 days, or at last contact if lost to follow-up. The modelling strategy addressed the causal association between HIV multidrug resistance and mortality, excluding factors on the causal pathway (most notably, CD4 cell count, clinical signs of advanced HIV, and poor functional and nutritional status). Findings Of 1316 patients with HIV enrolled in the STAMP trial at the Malawi site between Oct 26, 2015, and Sept 19, 2017, 786 had taken ART for at least 6 months. 252 (32%) of 786 patients had virological failure (viral load ≥1000 copies per mL). Mean age was 41·5 years (SD 11·4) and 528 (67%) of 786 were women. Of 237 patients with HIV drug resistance results available, 195 (82%) had resistance to lamivudine, 128 (54%) to tenofovir, and 219 (92%) to efavirenz. Resistance to at least two drugs was common (196, 83%), and this was associated with increased mortality (adjusted hazard ratio 1·7, 95% CI 1·2–2·4; p=0·0042). Interpretation Interventions are urgently needed and should target ART clinic, hospital, and post-hospital care, including differentiated care focusing on patients with advanced HIV, rapid viral load testing, and routine access to drug resistance testing. Prompt diagnosis and switching to alternative ART could reduce early mortality among inpatients with HIV. Funding Joint Global Health Trials Scheme of the Medical Research Council, UK Department for International Development, and Wellcome Trust.",
                "language": "eng",
                "pubModel": "Undetermined",
                "pubTypeList": {
                    "pubType": [
                        "research-article",
                        "Journal Article"
                    ]
                },
                "grantsList": {
                    "grant": [
                    ]
                },
                "fullTextUrlList": {
                    "fullTextUrl": [
                        {
                            "availability": "Free",
                            "availabilityCode": "F",
                            "documentStyle": "html",
                            "site": "PubMedCentral",
                            "url": "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC7487765/?tool=EBI"
                        },
                        {
                            "availability": "Free",
                            "availabilityCode": "F",
                            "documentStyle": "pdf",
                            "site": "PubMedCentral",
                            "url": "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC7487765/pdf/?tool=EBI"
                        },
                        {
                            "availability": "Free",
                            "availabilityCode": "F",
                            "documentStyle": "html",
                            "site": "Europe_PMC",
                            "url": "https://europepmc.org/articles/PMC7487765"
                        },
                        {
                            "availability": "Free",
                            "availabilityCode": "F",
                            "documentStyle": "pdf",
                            "site": "Europe_PMC",
                            "url": "https://europepmc.org/articles/PMC7487765?pdf=render"
                        }
                    ]
                },
                "isOpenAccess": "Y",
                "inEPMC": "Y",
                "inPMC": "Y",
                "hasPDF": "Y",
                "hasBook": "N",
                "hasSuppl": "Y",
                "citedByCount": 0,
                "hasData": "Y",
                "hasReferences": "N",
                "hasTextMinedTerms": "Y",
                "hasDbCrossReferences": "N",
                "hasLabsLinks": "N",
                "license": "cc by",
                "authMan": "N",
                "epmcAuthMan": "N",
                "nihAuthMan": "N",
                "hasTMAccessionNumbers": "Y",
                "tmAccessionTypeList": {
                    "accessionType": [
                        "doi"
                    ]
                },
                "dateOfCreation": "2020-09-20",
                "firstIndexDate": "2020-09-23",
                "fullTextReceivedDate": "2020-09-20",
                "dateOfRevision": "2020-09-29",
                "electronicPublicationDate": "2020-09-01",
                "firstPublicationDate": "2020-09-01"
            },
            {
                "id": "32948688",
                "source": "MED",
                "pmid": "32948688",
                "pmcid": "PMC7502863",
                "fullTextIdList": {
                    "fullTextId": [
                        "PMC7502863"
                    ]
                },
                "doi": "10.1128/mbio.02243-20",
                "title": "Impaired Cytotoxic CD8+ T Cell Response in Elderly COVID-19 Patients.",
                "authorString": "Westmeier J, Paniskaki K, Karaköse Z, Werner T, Sutter K, Dolff S, Overbeck M, Limmer A, Liu J, Zheng X, Brenner T, Berger MM, Witzke O, Trilling M, Lu M, Yang D, Babel N, Westhoff T, Dittmer U, Zelinskyy G.",
                "authorList": {
                    "author": [
                        {
                            "fullName": "Westmeier J",
                            "firstName": "Jaana",
                            "lastName": "Westmeier",
                            "initials": "J",
                            "authorAffiliationDetailsList": {
                            }
                        },
                        {
                            "fullName": "Berger MM",
                            "firstName": "Marc M",
                            "lastName": "Berger",
                            "initials": "MM",
                            "authorId": {
                            },
                            "authorAffiliationDetailsList": {
                            }
                        }
                    ]
                },
                "authorIdList": {
                    "authorId": [
                    ]
                },
                "journalInfo": {
                    "issue": "5",
                    "volume": "11",
                    "journalIssueId": 3004594,
                    "dateOfPublication": "2020 Sep",
                    "monthOfPublication": 9,
                    "yearOfPublication": 2020,
                    "printPublicationDate": "2020-09-01",
                    "journal": {
                        "title": "mBio",
                        "medlineAbbreviation": "mBio",
                        "essn": "2150-7511",
                        "issn": "2150-7511",
                        "isoabbreviation": "mBio",
                        "nlmid": "101519231"
                    }
                },
                "pubYear": "2020",
                "abstractText": "Severe acute respiratory syndrome coronavirus 2 (SARS-CoV-2) infection induces a T cell response that most likely contributes to virus control in COVID-19 patients but may also induce immunopathology. Until now, the cytotoxic T cell response has not been very well characterized in COVID-19 patients. Here, we analyzed the differentiation and cytotoxic profile of T cells in 30 cases of mild COVID-19 during acute infection. SARS-CoV-2 infection induced a cytotoxic response of CD8+ T cells, but not CD4+ T cells, characterized by the simultaneous production of granzyme A and B as well as perforin within different effector CD8+ T cell subsets. PD-1-expressing CD8+ T cells also produced cytotoxic molecules during acute infection, indicating that they were not functionally exhausted. However, in COVID-19 patients over the age of 80 years, the cytotoxic T cell potential was diminished, especially in effector memory and terminally differentiated effector CD8+ cells, showing that elderly patients have impaired cellular immunity against SARS-CoV-2. Our data provide valuable information about T cell responses in COVID-19 patients that may also have important implications for vaccine development.IMPORTANCE Cytotoxic T cells are responsible for the elimination of infected cells and are key players in the control of viruses. CD8+ T cells with an effector phenotype express cytotoxic molecules and are able to perform target cell killing. COVID-19 patients with a mild disease course were analyzed for the differentiation status and cytotoxic profile of CD8+ T cells. SARS-CoV-2 infection induced a vigorous cytotoxic CD8+ T cell response. However, this cytotoxic profile of T cells was not detected in COVID-19 patients over the age of 80 years. Thus, the absence of a cytotoxic response in elderly patients might be a possible reason for the more frequent severity of COVID-19 in this age group than in younger patients.",
                "affiliation": "Institute for Virology, University Hospital Essen, University of Duisburg-Essen, Essen, Germany.",
                "publicationStatus": "epublish",
                "language": "eng",
                "pubModel": "Electronic",
                "pubTypeList": {
                    "pubType": [
                        "Research Support, Non-U.S. Gov't",
                        "research-article",
                        "Journal Article"
                    ]
                },
                "keywordList": {
                    "keyword": [
                        "Aging",
                        "Perforin",
                        "Cytotoxic T cells",
                        "PD-1",
                        "Cd4+",
                        "Granzyme",
                        "Cd8+",
                        "Covid-19",
                        "Sars-cov-2"
                    ]
                },
                "subsetList": {
                    "subset": [
                        {
                            "code": "IM",
                            "name": "Index Medicus"
                        }
                    ]
                },
                "fullTextUrlList": {
                    "fullTextUrl": [
                        {
                            "availability": "Subscription required",
                            "availabilityCode": "S",
                            "documentStyle": "doi",
                            "site": "DOI",
                            "url": "https://doi.org/10.1128/mBio.02243-20"
                        },
                        {
                            "availability": "Open access",
                            "availabilityCode": "OA",
                            "documentStyle": "html",
                            "site": "Europe_PMC",
                            "url": "https://europepmc.org/articles/PMC7502863"
                        },
                        {
                            "availability": "Open access",
                            "availabilityCode": "OA",
                            "documentStyle": "pdf",
                            "site": "Europe_PMC",
                            "url": "https://europepmc.org/articles/PMC7502863?pdf=render"
                        }
                    ]
                },
                "commentCorrectionList": {
                    "commentCorrection": [
                        {
                            "id": "PPR204727",
                            "source": "PPR",
                            "type": "Preprint in",
                            "note": "Link created based on a title-first author match",
                            "orderIn": 10002
                        }
                    ]
                },
                "isOpenAccess": "Y",
                "inEPMC": "Y",
                "inPMC": "N",
                "hasPDF": "Y",
                "hasBook": "N",
                "hasSuppl": "N",
                "citedByCount": 0,
                "hasData": "N",
                "hasReferences": "N",
                "hasTextMinedTerms": "Y",
                "hasDbCrossReferences": "N",
                "hasLabsLinks": "N",
                "license": "cc by",
                "authMan": "N",
                "epmcAuthMan": "N",
                "nihAuthMan": "N",
                "hasTMAccessionNumbers": "N",
                "dateOfCreation": "2020-09-19",
                "firstIndexDate": "2020-09-23",
                "fullTextReceivedDate": "2020-09-28",
                "dateOfRevision": "2020-09-26",
                "electronicPublicationDate": "2020-09-18",
                "firstPublicationDate": "2020-09-18"
            }

        ]
    }
})

epmc_json_dict = deepcopy(epmc_api_search_2_results_json_dict["resultList"]["result"][0])

# Problems were originally reported with publication dates before 1900, this structure contains 1873 dates
epmc__old_dates_json_dict = deepcopy(epmc_json_dict)
epmc__old_dates_json_dict['firstPublicationDate'] = '1873-07-10'
epmc__old_dates_json_dict['electronicPublicationDate'] = '1873-07-10'
epmc__old_dates_json_dict['journalInfo']['printPublicationDate'] = '1873-01-01'
epmc__old_dates_json_dict['journalInfo']['dateOfPublication'] = '1873 Jan'

# JSON as returned by CROSSREF API call
crossref_api_search_2_results_json = json.dumps({
    "status": "ok",
    "message-type": "work-list",
    "message-version": "1.0.0",
    "message": {
        "facets": {},
        "next-cursor": "AoJ80XmM6vMCPwRodHRwOi8vZHguZG9pLm9yZy8xMC4yMTc0OC9hbTIwLjE2Mw==",
        "total-results": 2,
        "items": [
            {
                "indexed": {
                    "date-parts": [
                        [
                            2020,
                            8,
                            26
                        ]
                    ],
                    "date-time": "2020-08-26T19:03:42Z",
                    "timestamp": 1598468622315
                },
                "reference-count": 48,
                "publisher": "American Physiological Society",
                "issue": "4",
                "funder": [
                    {
                        "DOI": "10.13039/100000072",
                        "name": "National Institute of Dental and Craniofacial Research",
                        "doi-asserted-by": "publisher",
                        "award": [
                            "1R15DE023668-01A1"
                        ]
                    },
                    {
                        "DOI": "10.13039/100000154",
                        "name": "Division of Integrative Organismal Systems",
                        "doi-asserted-by": "publisher",
                        "award": [
                            "IOS-1456810"
                        ]
                    },
                    {
                        "DOI": "10.13039/100000153",
                        "name": "Division of Biological Infrastructure",
                        "doi-asserted-by": "publisher",
                        "award": [
                            "DBI-0922988"
                        ]
                    }
                ],
                "content-domain": {
                    "domain": [],
                    "crossmark-restriction": False
                },
                "short-container-title": [
                    "Journal of Applied Physiology"
                ],
                "published-print": {
                    "date-parts": [
                        [
                            2020,
                            4,
                            1
                        ]
                    ]
                },
                "abstract": "<jats:p> During chewing, movements and deformations of the tongue are coordinated with jaw movements to manage and manipulate the bolus and avoid injury. Individuals with injuries to the lingual nerve report both tongue injuries due to biting and difficulties in chewing, primarily because of impaired bolus management, suggesting that jaw-tongue coordination relies on intact lingual afferents. Here, we investigate how unilateral lingual nerve (LN) transection affects jaw-tongue coordination in an animal model (pig, Sus scrofa). Temporal coordination between jaw pitch (opening-closing) and 1) anteroposterior tongue position (i.e., protraction-retraction), 2) anteroposterior tongue length, and 3) mediolateral tongue width was compared between pre- and post-LN transection using cross-correlation analyses. Overall, following LN transection, the lag between jaw pitch and the majority of tongue kinematics decreased significantly, demonstrating that sensory loss from the tongue alters jaw-tongue coordination. In addition, decrease in jaw-tongue lag suggests that, following LN transection, tongue movements and deformations occur earlier in the gape cycle than when the lingual sensory afferents are intact. If the velocity of tongue movements and deformations remains constant, earlier occurrence can reflect less pronounced movements, possibly to avoid injuries. The results of this study demonstrate that lingual afferents participate in chewing by assisting with coordinating the timing of jaw and tongue movements. The observed changes may affect bolus management performance and/or may represent protective strategies because of altered somatosensory awareness of the tongue. </jats:p><jats:p> NEW &amp; NOTEWORTHY Chewing requires coordination between tongue and jaw movements. We compared the coordination of tongue movements and deformation relative to jaw opening-closing movements pre- and post-lingual nerve transection during chewing in pigs. These experiments reveal that the timing of jaw-tongue coordination is altered following unilateral disruption of sensory information from the tongue. Therefore, maintenance of jaw-tongue coordination requires bilateral sensory information from the tongue. </jats:p>",
                "DOI": "10.1152/japplphysiol.00398.2019",
                "type": "journal-article",
                "created": {
                    "date-parts": [
                        [
                            2020,
                            3,
                            19
                        ]
                    ],
                    "date-time": "2020-03-19T18:00:41Z",
                    "timestamp": 1584640841000
                },
                "page": "941-951",
                "source": "Crossref",
                "is-referenced-by-count": 1,
                "title": [
                    "Unilateral lingual nerve transection alters jaw-tongue coordination during mastication in pigs"
                ],
                "prefix": "10.1152",
                "volume": "128",
                "author": [
                    {
                        "given": "Stéphane J.",
                        "family": "Montuelle",
                        "sequence": "first",
                        "affiliation": [
                            {
                                "name": "Department of Biomedical Sciences, Ohio University Heritage College of Osteopathic Medicine, Warrensville Heights, Ohio"
                            }
                        ]
                    },
                    {
                        "given": "Rachel A.",
                        "family": "Olson",
                        "sequence": "additional",
                        "affiliation": [
                            {
                                "name": "Department of Biological Sciences, Ohio University, Athens, Ohio"
                            }
                        ]
                    },
                    {
                        "given": "Hannah",
                        "family": "Curtis",
                        "sequence": "additional",
                        "affiliation": [
                            {
                                "name": "Department of Biomedical Sciences, Ohio University Heritage College of Osteopathic Medicine, Athens, Ohio"
                            }
                        ]
                    },
                    {
                        "ORCID": "http://orcid.org/0000-0003-4167-678X",
                        "authenticated-orcid": False,
                        "given": "Susan H.",
                        "family": "Williams",
                        "sequence": "additional",
                        "affiliation": [
                            {
                                "name": "Department of Biomedical Sciences, Ohio University Heritage College of Osteopathic Medicine, Athens, Ohio"
                            }
                        ]
                    }
                ],
                "member": "24",
                "reference": [
                    {
                        "key": "B1",
                        "DOI": "10.1080/08990220701470451",
                        "doi-asserted-by": "publisher"
                    },
                    {
                        "key": "B2",
                        "DOI": "10.1002/jez.589",
                        "doi-asserted-by": "publisher"
                    },
                    {
                        "key": "B3",
                        "DOI": "10.1152/ajpregu.2000.279.1.R1",
                        "doi-asserted-by": "publisher"
                    },
                    {
                        "key": "B4",
                        "DOI": "10.1002/jez.1402570105",
                        "doi-asserted-by": "publisher"
                    }
                ],
                "container-title": [
                    "Journal of Applied Physiology"
                ],
                "language": "en",
                "link": [
                    {
                        "URL": "https://journals.physiology.org/doi/pdf/10.1152/japplphysiol.00398.2019",
                        "content-type": "unspecified",
                        "content-version": "vor",
                        "intended-application": "similarity-checking"
                    }
                ],
                "deposited": {
                    "date-parts": [
                        [
                            2020,
                            4,
                            13
                        ]
                    ],
                    "date-time": "2020-04-13T23:56:48Z",
                    "timestamp": 1586822208000
                },
                "score": 1.0,
                "issued": {
                    "date-parts": [
                        [
                            2020,
                            4,
                            1
                        ]
                    ]
                },
                "references-count": 48,
                "journal-issue": {
                    "published-print": {
                        "date-parts": [
                            [
                                2020,
                                4,
                                1
                            ]
                        ]
                    },
                    "issue": "4"
                },
                "alternative-id": [
                    "10.1152/japplphysiol.00398.2019"
                ],
                "URL": "http://dx.doi.org/10.1152/japplphysiol.00398.2019",
                "relation": {
                    "cites": []
                },
                "ISSN": [
                    "8750-7587",
                    "1522-1601"
                ],
                "issn-type": [
                    {
                        "value": "8750-7587",
                        "type": "print"
                    },
                    {
                        "value": "1522-1601",
                        "type": "electronic"
                    }
                ],
                "subject": [
                    "Physiology (medical)",
                    "Physiology"
                ]
            },
            {
                "indexed": {
                    "date-parts": [
                        [
                            2020,
                            8,
                            26
                        ]
                    ],
                    "date-time": "2020-08-26T20:03:36Z",
                    "timestamp": 1598472216551
                },
                "reference-count": 77,
                "publisher": "Wiley",
                "issue": "5",
                "license": [
                    {
                        "URL": "http://creativecommons.org/licenses/by/4.0/",
                        "start": {
                            "date-parts": [
                                [
                                    2020,
                                    1,
                                    26
                                ]
                            ],
                            "date-time": "2020-01-26T00:00:00Z",
                            "timestamp": 1579996800000
                        },
                        "delay-in-days": 0,
                        "content-version": "vor"
                    },
                    {
                        "URL": "http://doi.wiley.com/10.1002/tdm_license_1.1",
                        "start": {
                            "date-parts": [
                                [
                                    2020,
                                    5,
                                    1
                                ]
                            ],
                            "date-time": "2020-05-01T00:00:00Z",
                            "timestamp": 1588291200000
                        },
                        "delay-in-days": 0,
                        "content-version": "tdm"
                    }
                ],
                "funder": [
                    {
                        "DOI": "10.13039/501100003031",
                        "name": "Agence de l'Environnement et de la Maîtrise de l'Energie",
                        "doi-asserted-by": "publisher",
                        "award": [
                            "TUD ‐ P18"
                        ]
                    }
                ],
                "content-domain": {
                    "domain": [
                        "onlinelibrary.wiley.com"
                    ],
                    "crossmark-restriction": True
                },
                "short-container-title": [
                    "Prog Photovolt Res Appl"
                ],
                "published-print": {
                    "date-parts": [
                        [
                            2020,
                            5
                        ]
                    ]
                },
                "DOI": "10.1002/pip.3250",
                "type": "journal-article",
                "created": {
                    "date-parts": [
                        [
                            2020,
                            1,
                            27
                        ]
                    ],
                    "date-time": "2020-01-27T06:45:17Z",
                    "timestamp": 1580107517000
                },
                "page": "403-416",
                "update-policy": "http://dx.doi.org/10.1002/crossmark_policy",
                "source": "Crossref",
                "is-referenced-by-count": 2,
                "title": [
                    "Implantation‐based passivating contacts for crystalline silicon front/rear contacted solar cells"
                ],
                "prefix": "10.1002",
                "volume": "28",
                "author": [
                    {
                        "ORCID": "http://orcid.org/0000-0001-9257-8034",
                        "authenticated-orcid": False,
                        "given": "Gianluca",
                        "family": "Limodio",
                        "sequence": "first",
                        "affiliation": [
                            {
                                "name": "Photovoltaic Material and Devices GroupDelft University of Technology PO Box 5031 2600 GA Delft The Netherlands"
                            }
                        ]
                    },
                    {
                        "ORCID": "http://orcid.org/0000-0003-4997-3551",
                        "authenticated-orcid": False,
                        "given": "Paul",
                        "family": "Procel",
                        "sequence": "additional",
                        "affiliation": [
                            {
                                "name": "Photovoltaic Material and Devices GroupDelft University of Technology PO Box 5031 2600 GA Delft The Netherlands"
                            }
                        ]
                    },
                    {
                        "given": "Arthur W.",
                        "family": "Weber",
                        "sequence": "additional",
                        "affiliation": [
                            {
                                "name": "Photovoltaic Material and Devices GroupDelft University of Technology PO Box 5031 2600 GA Delft The Netherlands"
                            }
                        ]
                    },
                    {
                        "ORCID": "http://orcid.org/0000-0001-7673-0163",
                        "authenticated-orcid": False,
                        "given": "Olindo",
                        "family": "Isabella",
                        "sequence": "additional",
                        "affiliation": [
                            {
                                "name": "Photovoltaic Material and Devices GroupDelft University of Technology PO Box 5031 2600 GA Delft The Netherlands"
                            }
                        ]
                    }
                ],
                "member": "311",
                "reference": [
                    {
                        "key": "e_1_2_6_2_1",
                        "DOI": "10.1039/C5EE03380B",
                        "doi-asserted-by": "publisher"
                    },
                    {
                        "key": "e_1_2_6_3_1",
                        "author": "Hermle M",
                        "first-page": "135",
                        "year": "2016",
                        "volume-title": "Passivated Contacts"
                    },
                    {
                        "key": "e_1_2_6_4_1",
                        "first-page": "1",
                        "article-title": "24.7% record efficiency HIT solar cell on thin silicon wafer",
                        "volume": "4",
                        "author": "Taguchi M",
                        "year": "2014",
                        "journal-title": "IEEE JPV"
                    },
                    {
                        "key": "e_1_2_6_78_1",
                        "DOI": "10.1109/JPHOTOV.2015.2395140",
                        "doi-asserted-by": "publisher"
                    }
                ],
                "container-title": [
                    "Progress in Photovoltaics: Research and Applications"
                ],
                "language": "en",
                "link": [
                    {
                        "URL": "https://onlinelibrary.wiley.com/doi/pdf/10.1002/pip.3250",
                        "content-type": "application/pdf",
                        "content-version": "vor",
                        "intended-application": "text-mining"
                    },
                    {
                        "URL": "https://onlinelibrary.wiley.com/doi/full-xml/10.1002/pip.3250",
                        "content-type": "application/xml",
                        "content-version": "vor",
                        "intended-application": "text-mining"
                    },
                    {
                        "URL": "https://onlinelibrary.wiley.com/doi/pdf/10.1002/pip.3250",
                        "content-type": "unspecified",
                        "content-version": "vor",
                        "intended-application": "similarity-checking"
                    }
                ],
                "deposited": {
                    "date-parts": [
                        [
                            2020,
                            4,
                            13
                        ]
                    ],
                    "date-time": "2020-04-13T06:34:54Z",
                    "timestamp": 1586759694000
                },
                "score": 1.0,
                "issued": {
                    "date-parts": [
                        [
                            2020,
                            5
                        ]
                    ]
                },
                "references-count": 77,
                "journal-issue": {
                    "published-print": {
                        "date-parts": [
                            [
                                2020,
                                5
                            ]
                        ]
                    },
                    "issue": "5"
                },
                "alternative-id": [
                    "10.1002/pip.3250"
                ],
                "URL": "http://dx.doi.org/10.1002/pip.3250",
                "archive": [
                    "Portico"
                ],
                "relation": {
                    "cites": []
                },
                "ISSN": [
                    "1062-7995",
                    "1099-159X"
                ],
                "issn-type": [
                    {
                        "value": "1062-7995",
                        "type": "print"
                    },
                    {
                        "value": "1099-159X",
                        "type": "electronic"
                    }
                ],
                "subject": [
                    "Renewable Energy, Sustainability and the Environment",
                    "Electrical and Electronic Engineering",
                    "Electronic, Optical and Magnetic Materials",
                    "Condensed Matter Physics"
                ],
                "assertion": [
                    {
                        "value": "2019-06-14",
                        "order": 0,
                        "name": "received",
                        "label": "Received",
                        "group": {
                            "name": "publication_history",
                            "label": "Publication History"
                        }
                    },
                    {
                        "value": "2020-01-05",
                        "order": 1,
                        "name": "accepted",
                        "label": "Accepted",
                        "group": {
                            "name": "publication_history",
                            "label": "Publication History"
                        }
                    },
                    {
                        "value": "2020-01-26",
                        "order": 2,
                        "name": "published",
                        "label": "Published",
                        "group": {
                            "name": "publication_history",
                            "label": "Publication History"
                        }
                    }
                ]
            }
		],
        "items-per-page": 2,
        "query": {
            "start-index": 0,
            "search-terms": None
        }
    }
})
