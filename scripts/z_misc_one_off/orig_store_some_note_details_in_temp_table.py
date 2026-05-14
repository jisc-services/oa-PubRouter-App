#!/usr/bin/env python
"""
Scans current notifications and stores some details in temporary table: `z_cum_notifications`.

Create table script:

CREATE TABLE `jper`.`z_cum_notifications` (
  `id` INT UNSIGNED NOT NULL,
  `doi` VARCHAR(100) NULL,
  `prov_id` INT UNSIGNED NULL,
  `prov_harv_id` INT UNSIGNED NULL,
  `prov_route` VARCHAR(5) NULL,
  `art_type` VARCHAR(200) NULL,
  `category` CHAR(3) NULL,
  PRIMARY KEY (`id`),
  INDEX `doi` (`doi` ASC) VISIBLE)
COMMENT = 'Temporary table holds info about past notifications';

"""
import os
from octopus.core import initialise
from octopus.lib.dates import now_str
# import octopus.modules.mysql.dao as db
from octopus.modules.mysql.dao import DAO, TableDAO, RAW, DICT, WRAP, CONN_CLOSE, PURGE, DAOException

from router.jper.app import app     # need to import app_decorator as other modules import it from here.
from router.shared.models.note import RoutedNotification


def calc_cat_from_single_article_type(article_type, default="O"):
    """
    Calculate Category (resource type) code (1 to 3 chars) by analysing a single article_type value
    :param article_type: String
    :param default: String - Default category code
    :return: String - Category code (1 to 3 chars)
    """
    single_art_type_to_cat = {
        "monograph": "B",  # book
        "book-chapter": "BC",  # book part
        "proceedings": "CP",  # conference proceedings
        "correction": "JAC",  # corrigendum
        "erratum": "JAC",  # corrigendum
        "retraction": "JAC",  # corrigendum
        "published-erratum": "JAC",  # corrigendum
        "retraction-of-publication": "JAC",  # corrigendum
        "corrected-and-republished-article": "JAC",  # corrigendum
        "data-paper": "JAD",  # data paper
        "abstract": "JAR",  # research article
        "methods-article": "JAR",  # research article
        "research-article": "JAR",  # research article
        "article": "JAR",  # research article
        "journal-article": "JAR",  # research article
        "rapid-communication": "JAR",  # Research article
        "discussion": "JAV",  # review article
        "product-review": "JAV",  # review article
        "review-article": "JAV",  # review article
        "systematic-review": "JAV",  # review article
        "editorial": "JE",  # editorial
        "letter": "JL",  # letter to the editor
        "reply": "JL",  # letter to the editor
        "lecture": "U",  # Lecture
        "article-preprint": "P",  # preprint
        "preprint": "P",  # preprint
        "report": "R",  # Report
        "meeting-report": "RM",  # memorandum
        "practice-and-policy": "RO",  # policy report
        "practice-guideline": "RO",  # policy report
        "brief-report": "RR",  # research report
        "case-report": "RR",  # research report
        "case-study": "RR",  # research report
        "case-reports": "RR",  # research report
        "technical-note": "RT",  # technical report
        "book-review": "VB",  # book review
        "article-commentary": "VC",  # commentary
        "clinical-conference": "C",  # Conference output
        "short-communication": "RR",  # Research report
        "perspective": "RR",  # Research report
    }


    # Convert article-type to lower case; & replace any spaces by '-'
    return single_art_type_to_cat.get(article_type.strip().lower().replace(" ", "-"), default)


def calc_cat_from_compound_article_type(article_type, default="O"):
    """
    Calculate Category (resource type) code (1 to 3 chars) by analysing an article_type string containing
    multiple values separated by '; ' (semicolon).
    :param article_type: String of article types, separated by semicolon
    :param default: String - Default category code
    :return: String - Category code (1 to 3 chars)
    """
    # The ordering of this list is important...
    first_pass = [
        (["research-article", "abstract", "clinical trial", "methods-article", "journal-article"], "JAR"),
        # Journal research article
        (["review", "review-article", "systematic-review", "systematic review", "product-review"], "JAV"),
        # Journal review article
        (["data-paper"], "JAD"),  # Journal data paper
        (["correction", "erratum", "retraction", "published erratum", "retraction of publication",
          "corrected and republished article"], "JAC"),  # Journal article corrigendum
        (["article-commentary"], "VC"),  # Review commentary
        (["brief-report", "case reports", "case-study"], "RR"),  # Research report
        (["letter", "Letter", "reply"], "JL"),  # Journal letter
        (["editorial", "Editorial"], "JE"),  # Journal editorial
        (["meeting-report"], "RM"),  # Report memorandum
        (["clinical trial protocol"], "RL"),  # Research Protocol report
        (["practice-and-policy", "practice guideline"], "RO"),  # Policy report
        (["preprint", "article-preprint"], "P"),  # Preprint
        (["monograph"], "B"),  # Book
        (["book-chapter"], "BC"),  # Book chapter
        (["book-review"], "VB"),  # Book review
        (["report"], "R"),  # Report
        (["technical-note"], "RT"),  # Technical report
        (["proceedings"], "CP"),  # Conference proceedings
        (["clinical conference"], "C"),  # Conference output
    ]
    # After forcing to lower case
    second_pass = [
        (["case-report"], "RR"),  # Research report
        (["journal article", "article", ], "JAR"),  # Journal research article
    ]

    # Some article types are concatenated strings, joined by "; "
    type_list = [s.strip() for s in article_type.split("; ")]

    for compare_list, cat_code in first_pass:
        for art_type in type_list:
            if art_type in compare_list:
                return cat_code

    for compare_list, cat_code in second_pass:
        for art_type in type_list:
            if art_type.lower() in compare_list:
                return cat_code
    return default


def calc_category_from_article_type(article_type, default="O"):
    """
    Compares article_type value with keywords and returns Category (resource type) code (1 to 3 chars).
    USE THIS METHOD IF YOU AREN'T SURE IF article_type IS SIMPLE (SINGLE) OR COMPOUND STRING.

    :param article_type: - Article type string, possibly separate values concatenated with '; '
    :param default: String - default category code if match not found
    :return: Category code of 1 to 3 chars.
    """
    if ";" in article_type:
        return calc_cat_from_compound_article_type(article_type, default)
    else:
        return calc_cat_from_single_article_type(article_type, default)


def decode_category(cat_code, raise_on_error=True):
    """
    Convert 1 to 3 character Category code into resource type description using COAR Controlled Vocabulary
    See: https://vocabularies.coar-repositories.org/resource_types/

    :param cat_code: String - 1 to 3 character UPPERCASE category code
    :param raise_on_error: Boolean - True: Raise an EncodingWarning exception if category code doesn't exactly match;
                                     False: Return Error string in place of decoded category
    :return: Category description string
    """
    cat_map = {
        "J": ("journal",
              {
                  "E": ("editorial", None),
                  "A": ("journal article",
                        {
                            "C": ("corrigendum", None),
                            "D": ("data paper", None),
                            "R": ("research article", None),
                            "V": ("review article", None),
                            "S": ("software paper", None)
                        }),
                  "L": ("letter to the editor", None)
              }),
        "B": ("book",  # Aka Monograph
              {
                  "C": ("book part", None)  # Aka Book chapter
              }),
        "C": ("conference output",
              {
                  "E": ("conference presentation", None),
                  "P": ("conference proceedings",
                        {
                            "A": ("conference paper", None),
                            "O": ("conference poster", None)
                        }),
                  "A": ("conference paper not in proceedings", None),
                  "O": ("conference poster not in proceedings", None)
              }),
        "R": ("Report",
              {
                  "C": ("clinical study", None),
                  "D": ("data management plan", None),
                  "M": ("memorandum", None),
                  "O": ("policy report", None),
                  "P": ("project deliverable", None),
                  "R": ("research report", None),
                  "T": ("technical report", None),
                  "L": ("research protocol", None)
              }),
        "P": ("preprint", None),
        "V": ("review",
              {
                  "B": ("book review", None),
                  "C": ("commentary", None),
                  "P": ("peer review", None)
              }),
        "L": ("letter", None),
        "O": ("other", None)
    }
    desc = None
    mapped_code = ""
    ok = False
    if cat_code:
        map_dict = cat_map
        # Iterate over list of characters in category-code string
        for code_char in list(cat_code):
            desc, map_dict = map_dict.get(code_char, (None, None))
            if desc:
                mapped_code += code_char
            if not map_dict:
                break
    if not desc:
        desc = f"Unrecognised category code: '{cat_code}'"
    elif cat_code != mapped_code:
        desc += f" - partially matched '{mapped_code}' of code: '{cat_code}'"
    else:
        ok = True
    if not ok and raise_on_error:
        raise EncodingWarning(desc)

    return desc


class ZNoteDAO(TableDAO):
    __table__ = "z_cum_notifications"

    __ignore_null__ = True  # When retrieving recs, don't create data dict entries where record fields (cols) are NULL

    # List of tuples for columns that are created/updated by MySQL
    __auto_sql_cols__ = []
    # List of tuples for columns that are created/updated automatically by this DAO
    __auto_dao_cols__ = []

    __extra_cols__ = [("id", None, None),
                      ("doi", None, None),  # Article DOI
                      ("prov_id", None, None),  # Id of Publisher provider (NOT harvester provider)
                      ("prov_harv_id", None, None),  # Id of Harvester provider
                      ("prov_route", None, None),
                      ("art_type", None, None),  # Article_type
                      ("category", None, None),
                      ("metrics_json", None, DAO.dict_to_from_json_str)  # Metrics structure
                      ]
    __json__ = []
    __pull_cursor_dict__ = {
        "pk": ("", ["id"], None),
        # ORDER BY clause direction (ASC or DESC) will be determined by the pull_all(order_by parameter)
        "all": ("", None, "id {}"),
        # Following queries are for use with bespoke_pull() function
        # Select max ID value (most recent record ID) from table
        "bspk_max_id": ("BSPK", f"SELECT MAX(id) FROM {__table__}", None),
    }

    @classmethod
    def max_id(cls):
        """
        :return: Integer - Largest ID of record in table (i.e. Id of last record created)
        """
        rec_tuple_list = cls.bespoke_pull(pull_name="bspk_max_id")
        if rec_tuple_list:
            # Expect single array of results, with that array having 1 entry
            max_val = rec_tuple_list[0][0]
            return int(max_val) if max_val else None
        return None


log_fname = os.path.join("/tmp", f"notification_analysis_{now_str('%Y-%m-%d')}.txt")
log_file = open(log_fname, "w", encoding="utf-8")


def write_log(s):
    print(s)
    log_file.write(s)


def format_output(_set, sep="\n "):

    return sep + sep.join(sorted(_set)) + "\n"


repos = {"pub": "ALL Publishers", "harv": "ALL Harvesters"}
art_types = {"pub": set(), "harv": set()}

write_log(f"\nResults will be written to file: {log_fname}\n")

NONE = "''"     # …
with app.app_context():

    initialise()

    # res_list_of_field_tuples, status_dict = db.DAO.run_query("SELECT MAX(id) FROM z_cum_notifications", fetch=True)
    # last_id = res_list_of_field_tuples[0][0]
    last_id = ZNoteDAO.max_id()
    print(f"\nLast notification ID processed: {last_id}")

    count = 0
    scroller = RoutedNotification.routed_scroller_obj(since_id=last_id, scroll_num=99)
    with scroller:
        for note in scroller:
            count += 1
            if (count % 1000) == 0:
                print(f"Processed {count}")
                ZNoteDAO.commit()
            raw_art_type = note.article_type
            art_type = raw_art_type or NONE
            # Publisher notification without an article type
            if note.provider_id is not None and not raw_art_type:
                cat = "JA"  # Default to Journal article
            else:
                cat = calc_category_from_article_type(art_type)

            z_data = {
                "id": note.id,
                "doi": note.article_doi,  # Article DOI
                "prov_id": note.provider_id,  # Id of Publisher provider (NOT harvester provider)
                "prov_harv_id": note.provider_harv_id,  # Id of Harvester provider
                "prov_route": note.provider_route,
                "art_type": raw_art_type,  # Article_type
                "category": cat,
                "metrics_json": note.metrics
            }
            ZNoteDAO.insert(z_data, commit=False)

            #  Detailed breakdown of article type by publisher
            pub_id = note.provider_id
            # Add to all publisher or all harvesters
            art_types["pub" if pub_id else "harv"].add(art_type)  # All publishers or harvesters

            pub_type = f"p{pub_id}" if pub_id else f"h{note.provider_harv_id}"
            if pub_type not in repos:
                repos[pub_type] = note.provider_agent
            try:
                art_types[pub_type].add(art_type)
            except KeyError:
                art_types[pub_type] = {art_type}    # Create new set

if count:
    ZNoteDAO.commit()

write_log(f"\n**** Analysis Results of {count} Notifications ****\n")

write_log("\n** Article types by provider **\n")
for k, s in art_types.items():
    write_log(f"Article types - {repos[k]}: {format_output(s)}")

write_log("\n** Resource Type (Category) Analysis **")
for k in ["pub", "harv"]:
    write_log(f"\n* {repos[k]} *")
    for art_type in art_types[k]:
        code = calc_category_from_article_type(art_type)
        desc = decode_category(code)
        write_log(f" {code}: {desc} -- {art_type}\n")

write_log(f"\n**** {count} Notifications processed ****\n")

log_file.close()
