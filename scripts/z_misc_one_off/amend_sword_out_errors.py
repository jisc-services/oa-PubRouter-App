#!/usr/bin/env python
"""
Amend some sword-out errors
"""
import os
from octopus.core import initialise
from octopus.lib.dates import now_str
from router.jper.app import app     # need to import app_decorator as other modules import it from here.
from router.shared.models.note import RoutedNotification
from router.shared.models.sword_out import SwordDepositRecord

log_fname = os.path.join("/tmp", f"amend_sword_out_errs_{now_str('%Y-%m-%d')}.txt")
log_file = open(log_fname, "w", encoding="utf-8")


def write_log(s):
    print(s)
    log_file.write(s + "\n")

write_log(f"\nResults will be written to file: {log_fname}\n")

# ✦ Content error: [ article file (3869545) • repo entry (382994) • DOI: 10.1016/j.tipsro.2025.100359 ]. Package deposit failed - ('Connection aborted.', RemoteDisconnected('Remote end closed connection without response')) - ConnectionError(ProtocolError('Connection aborted.', RemoteDisconnected('Remote end closed connection without response')))
# Package deposit failed - Problem depositing file: 'article.zip', with Packaging: http://purl.org/net/sword/package/SimpleZip, From: /Incoming/store/3777114/ArticleFilesJATS.zip - ERROR: ('Connection aborted.', RemoteDisconnected('Remote end closed connection without response')) - ConnectionError(ProtocolError('Connection aborted.', RemoteDisconnected('Remote end closed connection without response')))
SwordDepositRecord.__pull_cursor_dict__["special_1"] = (
    "WHERE", "content_status = 0 AND error_message NOT LIKE '%europepmc%' AND error_message NOT LIKE '%with Packaging%' AND error_message LIKE '%RemoteDisconnected%'", None
)

# ✦ Content error: [ article file (3872968) • repo entry (383080) • DOI: 10.1093/ehjopen/oeag017 ]. Package deposit failed - Problem getting file: 'article.pdf' - Couldn't retrieve file from: https://europepmc.org/articles/PMC12978528?pdf=render - ConnectionError(ProtocolError('Connection aborted.', RemoteDisconnected('Remote end closed connection without response')))
SwordDepositRecord.__pull_cursor_dict__["special_2"] = (
    "WHERE", "content_status = 0 AND error_message LIKE '%europepmc%' AND error_message LIKE '%RemoteDisconnected%'", None
)

# ✦ Content error: [ article file (3874556) • repo entry (383156) • DOI: unknown ]. Package deposit failed - Problem getting file: 'article.pdf' - Unexpected mimetype: 'text/html;charset=UTF-8', Expected: 'application/pdf'; From: https://europepmc.org/articles/PMC12979119?pdf=render
SwordDepositRecord.__pull_cursor_dict__["special_3"] = (
    "WHERE", "content_status = 0 AND error_message LIKE '%europepmc%' AND error_message LIKE '%Unexpected mimetype%'", None
)

with (app.app_context()):

    initialise()

    count = 0
    updated = 0

    dep_recs_1 = SwordDepositRecord.pull_all(pull_name="special_1", for_update=True)
    dep_recs_2 = SwordDepositRecord.pull_all(pull_name="special_2", for_update=True)
    dep_recs_3 = SwordDepositRecord.pull_all(pull_name="special_3", for_update=True)

    for sword_dep_rec in dep_recs_1:
        count += 1
        note = RoutedNotification.pull(sword_dep_rec.data["note_id"])
        pdf_link = note.select_best_external_pdf_link()
        if pdf_link:
            sword_dep_rec.error_message = sword_dep_rec.error_message.replace("Package deposit failed -", f"Package deposit failed - Couldn't retrieve file from: {pdf_link['url']} -")
            sword_dep_rec.update()
            write_log(f"\n** Sword rec updated id: {sword_dep_rec.id}; Error msg: {sword_dep_rec.error_message}\n")
            updated += 1
        if count >= 1:
            break

    for sword_dep_rec in dep_recs_2:
        count += 1
        err_msg = sword_dep_rec.error_message
        upto = err_msg.find("; From:")
        sword_dep_rec.error_message = sword_dep_rec.error_message.replace(" - Problem getting file: 'article.pdf'", "")
        sword_dep_rec.update()
        write_log(f"\n** Sword rec updated id: {sword_dep_rec.id}; Error msg: {sword_dep_rec.error_message}\n")
        updated += 1
        if count > 1:
            break

    for sword_dep_rec in dep_recs_3:
        count += 1
        err_msg = sword_dep_rec.error_message
        upto = err_msg.find("; From:")
        sword_dep_rec.error_message = err_msg[:upto].replace("- Problem getting file: 'article.pdf'", f"- Problem getting file from: {err_msg[upto + 8:]}")
        sword_dep_rec.update()
        write_log(f"\n** Sword rec updated id: {sword_dep_rec.id}; Error msg: {sword_dep_rec.error_message}\n")
        updated += 1
        if count > 1:
            break

    write_log(f"\n**** Num recs processed {count}; recs updated {updated} ****\n")
    write_log(f"\n**** DONE ****\n")
