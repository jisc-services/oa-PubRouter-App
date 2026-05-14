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
from octopus.modules.mysql.dao import TableDAO, DAO

from router.jper.app import app     # need to import app_decorator as other modules import it from here.
from router.shared.models.note import RoutedNotification


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

    last_id = ZNoteDAO.max_id()
    print(f"\nLast notification ID processed: {last_id}")

    count = 0
    scroller = RoutedNotification.routed_scroller_obj(since_id=last_id, scroll_num=97)
    with scroller:
        for note in scroller:
            count += 1
            if (count % 1000) == 0:
                print(f"Processed {count}")
                ZNoteDAO.commit()
            raw_art_type = note.article_type
            art_type = raw_art_type or NONE
            cat = RoutedNotification.calc_category_from_article_type(art_type)
            z_data = {
                "id": note.id,
                "doi": note.article_doi,  # Article DOI
                "prov_id": note.provider_id,  # Id of Publisher provider (NOT harvester provider)
                "prov_harv_id": note.provider_harv_id,  # Id of Harvester provider
                "prov_route": note.provider_route,
                "art_type": raw_art_type,  # Article_type
                "category": cat
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
        code = RoutedNotification.calc_category_from_article_type(art_type)
        desc = RoutedNotification.decode_category(code)
        write_log(f" {code}: {desc} -- {art_type}\n")

write_log(f"\n**** {count} Notifications processed ****\n")
log_file.close()
