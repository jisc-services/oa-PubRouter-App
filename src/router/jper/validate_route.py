"""
Function to perform validation of notification, and if no or only non-critical errors then
optionally have it routed to a YOUR-ORG test repository.

Author: Jisc
"""
from logging import INFO, CRITICAL
from router.jper.api import JPER, ValidationException, ValidationMetaException
from router.jper.routing import get_repo_ids_n_pkg_types_matching_org_name, route_to_specified_test_repos

# Text that should appear at beginning of test repository Org name for it to be used for auto-routing
JISC_ORG_NAME_BEGINS = "YOUR-ORG-auto%"


def auto_testing_validation_n_routing(pub_test, basic_note_dict, note_zip_file=None, note_zip_stream=None):
    """
    Perform auto-testing validation on the supplied notification, AND possibly also routes a successfully tested
    notification to active YOUR-ORG test repositories (those with "YOUR-ORG" in org-name).
    :param pub_test: publisher testing object
    :param basic_note_dict: Basic notification dict
    :param note_zip_file: Zip file path (or None)
    :param note_zip_stream: Zip file stream (or None)
    :return: Created notification ID or None - but may raise exceptions
    """

    note_id = None
    try:
        step = "validating"
        exception_to_raise = None
        try:
            JPER.validate(
                pub_test.acc,
                basic_note_dict,
                file_handle=note_zip_stream,
                file_path=note_zip_file,
                pub_test=pub_test
            )
        # If we have non-critical metadata only exception, then save for raising later and allow for possible routing
        except ValidationMetaException as e:
            exception_to_raise = e
        # Any other exception (including ValidationException) raise immediately
        except Exception as e:
            raise e

        # If we've got this far then either there are No critical validation errors
        # If creating notifications during testing...
        if pub_test.test_active and pub_test.pub_data.route_note:
            step = "creating"
            # First we check that there are some active test repositories with "YOUR-ORG-auto" in org-name  to route the
            # notification to.  If not, there is no point continuing
            jisc_repo_ids, reqd_pkg_types = get_repo_ids_n_pkg_types_matching_org_name(False, JISC_ORG_NAME_BEGINS)
            if jisc_repo_ids:
                if note_zip_stream is not None:
                    # Need to reset the stream, because JPER.create_unrouted_note(...) ONCE AGAIN saves the stream
                    # to temporary local file, which will be empty unless this is done
                    note_zip_stream.seek(0)
                note = JPER.create_unrouted_note(
                    pub_test.acc,
                    basic_note_dict,
                    file_handle=note_zip_stream,
                    file_path=note_zip_file,
                    orig_fname=pub_test.filename
                )
                note_id = note.id
                pub_test.log(INFO, "Created notification ID: {}{}{}, for account {} ({}).".format(
                    note_id,
                    f", with DOI: {pub_test.doi}" if pub_test.doi else "",
                    f", from file: {pub_test.filename}" if pub_test.filename else "",
                    pub_test.acc.id,
                    pub_test.acc.org_name))

                step = "routing"
                routed_note = route_to_specified_test_repos(note, jisc_repo_ids, reqd_pkg_types,
                                                            "Publisher auto-testing")
                if routed_note:
                    pub_test.log(INFO,
                                 f"Routed notification ID: {routed_note.id} to YOUR-ORG test repos {routed_note.repositories}.")
                else:  # This should never occur!
                    # Set the step to deleting so that the notification that failed to route is deleted
                    step = "deleting"
                    pub_test.log(INFO,
                                 f"Routing failed for notification ID: {routed_note.id} - No repositories to route to.")
            else:
                pub_test.log(INFO,
                             f"No active test repo account for routing the notification to (Org name must begin with '{JISC_ORG_NAME_BEGINS[:-1]}').",
                             extra={"mail_it": True, "subject": "No active test repo account"}
                             )

        # We got a ValidationMetaException above
        if exception_to_raise:
            raise exception_to_raise

    except ValidationException as e:    # This also catches ValidationMetaException
        pub_test.log(INFO, f"{str(e)} for Account {pub_test.acc.id} ({pub_test.acc.org_name}).")
        raise e
    except Exception as e:
        pub_test.log(CRITICAL, repr(e), prefix=f"Unexpected error while {step} {pub_test.route.upper()} submission - ",
                     suffix=f". For account {pub_test.acc.id}.", exc_info=True)
        # If exception got raised during routing, then we want to delete the notification that was created
        if step == "routing":
            step = "deleting"
        raise e
    finally:  # This code always runs
        pub_test.create_test_record_and_finalise_autotest()
        if step == "deleting":
            if note.packaging_format is None:
                unrouted_ids_no_pkgs = [note_id]
                unrouted_ids_with_pkgs = []
            else:
                unrouted_ids_no_pkgs = []
                unrouted_ids_with_pkgs = [note_id]
            JPER.delete_unrouted_notifications_and_files(unrouted_ids_no_pkgs, unrouted_ids_with_pkgs)
            pub_test.log(INFO, f"Deleted unrouted notification ID: {note_id}.")
            note_id = None

    return note_id
