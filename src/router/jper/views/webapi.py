"""
Blueprint which provides the RESTful web API for JPER

IMPORTANT: current_user is an Organisation Account object
"""
import json
import os
from flask import Blueprint, make_response, request, redirect, Response, g, stream_with_context, current_app, \
    jsonify, abort
from flask_login import current_user        # In API context the current_user is an AccOrg object
from octopus.lib import dates
from octopus.modules.mysql.dao import DAOException, DAO
from router.shared.models.account import AccOrg, AccRepoMatchParams
from router.jper.security import publisher_or_admin_org__api, active_publisher_or_admin_org__api, \
                                  authentication_required__api, json_abort
from router.jper.api import JPER, ValidationException, ParameterException, ForbiddenException, ContentException
from router.jper.models.contentlog import ContentLog
from router.jper.models.publisher import APIDepositRecord
from router.jper.validate_route import auto_testing_validation_n_routing
from router.jper.pub_testing import init_pub_testing, CRITICAL, ERROR, WARNING, INFO

blueprint = Blueprint('webapi', __name__)


@blueprint.before_request
def before_req():
    # We create this attribute so that Flask's "user" account retrieval is handled differently for API requests compared
    # to other requests (such as GUI web app usage).
    # IMPORTANTLY, this results in an Organisation Account being retrieved into current_user, rather than a User Account.
    g.api_request = True


class BadRequestException(Exception):
    """
    Generic Exception for a bad request
    """
    pass


def _abort_500(error_msg):
    """
    Send 500 error.
    :param error_msg: Error message to return in response
    :return: n/a
    """
    if current_app.config.get("LOG_DEBUG"):
        current_app.logger.debug(f"Sending 500 Internal Server Error: {error_msg}")
    json_abort(500, error_msg)


def _abort_4xx(http_code, error_msg):
    """
    Send a 4xx response. Currently 400, 403, 404 are accepted codes
    :param http_code:   Integer - 400, 403 or 404
    :param error_msg: Error message to return in response
    :return: n/a
    """
    # Abort with a 400 (Bad Request) message
    msg = {400: "Bad Request", 403: "Forbidden", 404: "Not found"}
    if current_app.config.get("LOG_DEBUG"):
        current_app.logger.debug(f"Sending {http_code} {msg.get(http_code, '')}: {error_msg}")
    json_abort(http_code, error_msg)


def _abort_400_bad_request(error_msg):
    _abort_4xx(400, error_msg)


def _abort_403_forbidden(error_msg):
    _abort_4xx(403, error_msg)


def _abort_404_not_found(error_msg):
    _abort_4xx(404, error_msg)


def _validation_make_response(status_code, message, pub_test):
    return make_response(
        jsonify(status="ok" if status_code < 400 else "error",
                summary=message,
                errors=pub_test.errors,
                issues=pub_test.issues),
        status_code)


def _validation_abort_400(pub_test):
    """
    Abort if issues arise during validation.
    JSON response is sent including lists of errors and issues that occurred during the testing.

    :param pub_test: pub-testing object
    :return: nothing
    """
    # Abort with a response object to represent a 400 (Bad Request) around the supplied message
    # Publisher testing is active
    num_errs = pub_test.num_errors()
    num_issues = pub_test.num_issues()
    msg = f"Validation failed with {num_errs} error{'' if num_errs == 1 else 's'} and {num_issues} issue{'' if num_issues == 1 else 's'}"
    pub_test.log(INFO, f"Sending 400 Bad Request: {msg}")
    abort(_validation_make_response(400, msg, pub_test))


def _abort_403_if_not_latest_api_version(api_vers, endpoint):
    """
    Abort with 403 Forbidden if using an endpoint that is restricted to latest version of API
    
    :param api_vers: String - Version of API
    :param endpoint: String - the endpoint being used 
    """
    latest_api_vers = current_app.config.get("API_VERSION")
    if api_vers != latest_api_vers:
        _abort_403_forbidden(f"The '{endpoint}' endpoint is available ONLY for the latest version (v{latest_api_vers})"
                             f" of Router API - use {current_app.config.get('JPER_BASE_URL')}/{endpoint}.")


# ZZZ - API v3 (consider commenting out/deleting/renaming - when v3 API no longer supported
# ZZZ - (Consider leaving as a template for future API versions)
def _validate_convert_note_to_v4(note_dict, api_vers):
    """
    Need to convert v3 notification dictionary to v4: Restructure affiliations.
    """
    def _validate_v4_aff(auth_cont, auth_or_cont):
        if "affiliation" in auth_cont:
            raise ValidationException(f"Unexpected field 'affiliation' found in {auth_or_cont} object: {auth_cont}.")

    def _validate_convert_v3_aff(auth_cont, auth_or_cont):
        try:
            # Assign old style string affiliation to raw element of new style aff list of dicts
            auth_cont["affiliations"] = [{"raw": auth_cont["affiliation"]}]
            # Remove old style aff
            del auth_cont["affiliation"]
        except KeyError:
            if "affiliations" in auth_cont:
                raise ValidationException(
                    f"Unexpected field 'affiliations' found in {auth_or_cont} object: {auth_cont}.")

    latest_api_version = current_app.config.get("API_VERSION")
    validate_aff_func = _validate_v4_aff if api_vers == latest_api_version else _validate_convert_v3_aff
    note_metadata = note_dict.get("metadata", {})
    for auth_or_cont in ("author", "contributor"):
        for auth_cont in note_metadata.get(auth_or_cont, []):
            if not auth_cont:
                raise ValidationException(f"Empty or null entry found in '{auth_or_cont}' array.")
            validate_aff_func(auth_cont, auth_or_cont)
    note_dict["vers"] = latest_api_version
    return note_dict


def _get_parts():
    """
    Used to extract metadata and content from an incoming request

    :return: Tuple: (metadata parsed from incoming json, the zipped binary content)
    """
    metadata = None
    zip_content = None
    mime_json = "application/json"
    mime_zip = "application/zip"
    content_type_error_template = "Content-Type for {} part of multipart request must be '{}', not '{}'"
    parse_error_template = "Invalid JSON found in {} (it could not be parsed)"

    # Content-type, if present, could be of form: "blah; something=xyz" - we just want the "blah" part
    c_type = request.headers.get("content-type", "MISSING").split(";")[0].strip()

    # We expect either a multipart submission of Metadata & Content (zipfile) as 2 files,
    # or a Metadata only JSON submission
    if len(request.files) > 0:
        if c_type not in ("multipart/related", "multipart/form-data"):
            raise BadRequestException('Files have been submitted, but the request Content-Type is NOT "multipart/related"')
        try:
            # this is a multipart request, so extract the data accordingly
            file_metadata = request.files["metadata"]
            content = request.files["content"]
        except KeyError as e:
            raise BadRequestException(f'The submitted multipart request does NOT have the 2 parts expected, one named "metadata" containing JSON, the other named "content" containing a Zip file')

        # now, do some basic validation on the incoming http request (not validating the content,
        # that's for the underlying validation API to do
        if file_metadata.mimetype != mime_json:
            raise BadRequestException(content_type_error_template.format("metadata", mime_json, file_metadata.mimetype))

        try:
            # Metadata will be in bytes format - we assume it's not binary as it should be metadata
            # will return an error if it's binary.
            rawmd = file_metadata.stream.read().decode("utf-8")
            metadata = json.loads(rawmd)
        except Exception as e:
            raise BadRequestException(parse_error_template.format("metadata part of multipart request"))

        if content.mimetype != mime_zip:
            raise BadRequestException(content_type_error_template.format("content", mime_zip, content.mimetype))

        zip_content = content
    else:
        if c_type != mime_json:
            raise BadRequestException(f"Content-Type must be '{mime_json}', not '{c_type}' as no files submitted")

        try:
            metadata = request.json
        except Exception as e:
            raise BadRequestException(parse_error_template.format("request body"))

    return metadata, zip_content


@blueprint.route("/validate", methods=["POST"])
@publisher_or_admin_org__api
def validate(api_vers, pub_acc=None):
    """
    Receive a POST to the /validate endpoint and process it

    :param api_vers: API version - set automatically as defined in `url_defaults` when webapi blueprint is registered
    :param pub_acc: Publisher account (current_user) - SET BY DECORATOR FUNCTION
    :return: A 400 (Bad Request) if not valid, or a 204 if successful
    """
    _abort_403_if_not_latest_api_version(api_vers, 'validate')  # ZZZ - Can REMOVE in due course if ONLY supporting a single version of API

    pub_test = init_pub_testing(pub_acc, "api", init_mail=True)
    try:
        try:
            note_dict, zip_content = _get_parts()
        except BadRequestException as ee:
            pub_test.log(ERROR, f"BadRequest - {str(ee)}", suffix=f". For account {pub_acc.id}.")
            pub_test.create_test_record_and_finalise_autotest()
            raise ee

        # If we have a zip file but the Content-Type is form-data, just tell the user that they did everything right
        # except the Content-Type header.
        if zip_content is not None and "multipart/form-data" in request.content_type:
            msg = "BadRequest - Content-Type is 'multipart/form-data' not 'multipart/related'."
            suffix = " Despite this, the request would be successfully processed."
            pub_test.log(WARNING, msg, suffix=f"{suffix} For account {pub_acc.id}.")

        if len(request.files) > 2:
            msg = "BadRequest - The request included more than the 2 required files 'metadata' and 'content'."
            suffix = " Despite this, the request would be successfully processed, with additional files ignored."
            pub_test.log(WARNING, msg, suffix=f"{suffix} For account {pub_acc.id}.")

        filename = zip_content.filename if zip_content else None
        pub_test.set_filename(filename)
        note_dict["vers"] = api_vers
        # use getattr in case the zip_content is none
        auto_testing_validation_n_routing(pub_test, note_dict, note_zip_stream=getattr(zip_content, "stream", None))
    except DAOException as e:
        if e.abend:
            DAO.abnormal_exit(e, "Validate ")
    except Exception:
        pass

    err_count = pub_test.num_errors()
    issue_count = pub_test.num_issues()
    if err_count:
        _validation_abort_400(pub_test)

    return _validation_make_response(200,
                                     "Validated OK" if issue_count == 0
                                     else f"{issue_count} issues were found (these would not affect processing)",
                                     pub_test)


@blueprint.route("/validate/list", methods=["POST"])
@publisher_or_admin_org__api
def validate_list(api_vers, pub_acc=None):
    """
    Validate list of metadata only notifications.
    :param api_vers: API version - set automatically as defined in `url_defaults` when webapi blueprint is registered
    :param pub_acc: Publisher account (current_user) - SET BY DECORATOR FUNCTION
    """
    _abort_403_if_not_latest_api_version(api_vers, 'validate/list')  # ZZZ - Can REMOVE in due course if ONLY supporting a single version of API

    pub_test = init_pub_testing(pub_acc, "api", init_mail=True)

    try:
        c_type = request.content_type
        if c_type != 'application/json':
            raise ValidationException(f"Content-Type must be 'application/json', not '{c_type}'")

        try:
            notifications = request.json
        except Exception as e:
            raise ValidationException(f"The request body is not a JSON structure: {repr(e)}")

        if not isinstance(notifications, list):
            raise ValidationException(
                f"Expected a list of JSON objects in the request body, got {type(notifications)}")

        for index, notification in enumerate(notifications):
            if not isinstance(notification, dict):
                raise ValidationException(
                    f"Item at JSON array index [{index}] was not a JSON object, got {type(notification)} instead")

            id = notification.get("id")
            if not id:
                raise ValidationException(f"Notification object at JSON array index [{index}] did not have an 'id' property")

            note_dict = notification.get("notification")
            if not note_dict:
                raise ValidationException(
                    f"Object at JSON array index [{index}], with id '{id}', did not have a 'notification' property")
            try:
                note_dict["vers"] = api_vers
                JPER.validate(pub_acc, note_dict, None, pub_test=pub_test)

            except ValidationException as e:
                raise ValidationException(f"Notification at array index [{index}] with id '{id}' failed validation")
            except Exception as e:
                raise e

    except ValidationException as e:
        pub_test.log(ERROR, str(e), prefix="ValidationException - ", suffix=f". For account {pub_acc.id}.")
        _validation_abort_400(pub_test)

    except Exception as e:
        pub_test.log(CRITICAL, f"Unexpected error while validating API list submission - {repr(e)}",
                     suffix=f". For account {pub_acc.id}.")
        if isinstance(e, DAOException) and e.abend:
            DAO.abnormal_exit(e, "Validate list ")
        _validation_abort_400(pub_test)

    finally:  # This always gets executed, even if _validation_abort_400 occurs above
        try:
            pub_test.create_test_record_and_finalise_autotest()
        except DAOException as e:
            if e.abend:
                DAO.abnormal_exit(e, "Validate list ")
        except Exception as e:
            pass    # Critical error already raised within the function

    issue_count = pub_test.num_issues()
    return _validation_make_response(200,
                                     "Validated OK" if issue_count == 0 else
                                        f"{issue_count} issues were found (these would not affect processing)",
                                     pub_test)


def _store_deposit_in_tmparchive(pub_uuid, api_deposit_rec, json_dict, zip_content=None, ok_note_id=None):
    """
    Stores the JSON submitted metadata (or in case of failure, a JSON representation of the request made including
    basic request info, list of files in request and the headers)
    and zip content of a deposit into tmparchive. 

    :param pub_uuid: the UUID of publisher
    :param api_deposit_rec: the APIDepositRecord object associated with this deposit
    :param json_dict: a dictionary to be converted into JSON and stored in tmparchive
    :param zip_content: a file object representing the zip submitted as part of this deposit, to be stored in tmparchive
    :param ok_note_id: Notification ID - used when zip content has been ingested into main Store & we don't want to
                also save it in temp archive

    :return String target_dir: Temp Archive Location where files are stored
    """
    target_dir = ""
    try:
        tmparchive_dir = current_app.config.get("FTP_SAFETY_DIR")
        # where we want to store the deposit information in tmparchive: tmparchive/publisher_id/api_deposit_record_id
        target_dir = os.path.join(tmparchive_dir, pub_uuid, str(api_deposit_rec.id))
        # make all directories needed, if they already exist that's fine
        os.makedirs(target_dir, exist_ok=True)
        # store the JSON
        with open(os.path.join(target_dir, "deposit.json"), "w", encoding='utf-8') as json_file:
            json.dump(json_dict, json_file)
        # if there's zip content, store that too
        if zip_content:
            with open(os.path.join(target_dir, api_deposit_rec.name), "wb") as zip_file:
                zip_content.seek(0)
                zip_file.write(zip_content.read())
        elif ok_note_id:
            store_location = os.path.join(current_app.config.get('STORE_MAIN_DIR'), str(ok_note_id))
            with open(os.path.join(target_dir, "zip_location.txt"), "w") as f:
                f.write(f"Location of ingested zipfile in Store: {store_location}\n\n(Note that location will be deleted if notification is not routed).")
    except Exception as e:
        current_app.logger.critical(
            f"Couldn't save files to {target_dir} for deposit_record {api_deposit_rec.id}, publisher UUID {pub_uuid}\n{str(e)}",
            exc_info=True, extra={"subject": "API file save failed"}
        )
    return target_dir

def _convert_request_into_json(request):
    # converts a request into a JSON file with header info, files info (if there are files) and basic request info
    json_dict = {"headers": dict(request.headers), "request": str(request)}
    if request.files:
        json_dict["files"] = str(request.files)
    return json_dict


def _notification_exception(pub_acc, prefix, e, api_deposit_rec, json_dict=None, zipfile=None):
    """
    Handles exceptions occurring in the create_unrouted_note method. Logs the error internally, then returns an error 
    message to the API user. If there is an api_deposit_rec, then the api_deposit_rec is saved with error 
    information, then we store the following into tmparchive
    - metadata JSON of the request if we managed to extract it
       - OR a JSON representation of the request if we failed to extract the metadata JSON
    - the zipfile associated with the request, if it exists

    :param pub_acc: Publisher account
    :param prefix: error message prefix of this error
    :param e: the actual exception
    :param api_deposit_rec: the record of this api_deposit
    :param json_dict: json_dict representative of this request (either extracted metadata if we successfully extracted
        this, or a json representation of the request if we failed to extract metadata)
    :param zipfile: zipfile already extracted from this request
    """
    archive_location = ""
    exception_str = str(e) if e else ""
    exception_snippet = " - " + exception_str if exception_str else ""
    if api_deposit_rec:
        api_deposit_rec.error = prefix + exception_snippet
        try:
            api_deposit_rec.insert()
        except Exception as ee:
            current_app.logger.error(
                f"Failed to insert API Deposit record {api_deposit_rec.data} while processing earlier exception.")
            if isinstance(ee, DAOException) and ee.abend:
                ee.update_msg(after=f" Failed after original exception: {exception_str}")
                e = ee
        target_dir = _store_deposit_in_tmparchive(pub_acc.uuid, api_deposit_rec, json_dict, zipfile)
        archive_location = f"\nFiles saved in: {target_dir}"

    current_app.logger.critical(
        f"{prefix} - Acc: '{pub_acc.org_name}' ({pub_acc.id}){exception_snippet}{archive_location}",
        extra={"subject": "API submission error"}
    )

    if exception_str:
        file_name = zipfile.filename if zipfile else None
        subj = "Publications Router submission error"
        if file_name:
            subj += f" - file '{file_name}'"
        pub_acc.send_email(
            subj,
            exception_str,
            to=pub_acc.TECHS,     # Prefer tech contact emails, if absent default to contact_email (as a list)
            email_template="mail/pub_error.html",
            filename=file_name,
            save_acc_email_rec=True
        )

    if isinstance(e, DAOException) and e.abend:
        DAO.abnormal_exit(e)

    _abort_400_bad_request(exception_str or prefix)


def _default_pub_api_deposit_record(account):
    # creates a default api deposit record if the user is a publisher, else returns None
    if account.is_publisher:
        return APIDepositRecord({"pub_id": account.id, "successful": False, "matched": False})
    else:
        return None


@blueprint.route("/notification/list", methods=["POST"])
@active_publisher_or_admin_org__api
def create_notifications_from_list(api_vers, pub_acc=None):
    """
    Create notifications (metadata only, not PDF content) from a list of metadata.
    If current_user is an admin, will not create any deposit records.
    If current_user is a publisher, any notifications in the list are successfully created,
    then for each notification in the list (successful or failed) save a APIDepositRecord object for each
    notification and store the contents of the notification into tmparchive.
    
    @request.body: JSON list of metadata.
    
    :param api_vers: API version - set automatically as defined in `url_defaults` when webapi blueprint is registered
    :param pub_acc: Publisher account (current_user) - SET BY DECORATOR FUNCTION
    :return:
    201 - on successful creation of all request_objects
    202 - if some succeed and some fail 
    400 - if the very first request_object is a failure or if the request is a failure in general
    401 - if unauthenticated user attempts to access endpoint
    """
    # Publisher in auto-test mode isn't allowed to access this endpoint
    if pub_acc.is_publisher and pub_acc.publisher_data.in_test:
        _abort_403_forbidden("A publisher in auto-testing mode is not able to create notifications.")

    api_key = request.values.get('api_key', False)
    error_message = None

    def error_message_formatter(message, request_object_id=None):
        # formats an error message to include an API key and a request object ID (if it is not None)
        request_id_line = f"\nREQUEST_ID: {request_object_id}" if request_object_id else ""
        return f"{message}\nAPI-KEY: {api_key}{request_id_line}"

    def abort_failed_request(message):
        # if the entire request has failed, abort with a 400 and raise a critical error which includes info on the
        # request
        current_app.logger.critical(f"{message}\n{str(request)}\n{str(request.headers)}",
                                    extra={"subject": "API create notifications failure"})
        _abort_400_bad_request(message)

    c_type = request.content_type
    if c_type != 'application/json':
        abort_failed_request(error_message_formatter(f"Content-Type was '{c_type}' not 'application/json'"))
    request_objects = None
    try:
        request_objects = request.json
    except Exception as e:
        abort_failed_request(error_message_formatter(f"The request body is not a JSON structure: {str(e)}"))

    if not isinstance(request_objects, list):
        abort_failed_request(error_message_formatter(
            f"The request body is not a LIST instead it is a: {type(request_objects)}"
        ))

    # list of ids of the metadata which successfully created a notification
    success_ids = []
    # list of notification ids of notifications successfully created
    created_ids = []
    # list of ids of the metadata which failed to create a notification
    fail_ids = []

    status_code = 201

    # each request object should be of the form {"notification": {"metadata": {...}}, "id": "<ID>"}
    for request_object in request_objects:
        # initialise deposit record for this notification, will be None if user is not a publisher
        deposit_record = _default_pub_api_deposit_record(pub_acc)
        # id associated with this request object
        request_object_id = None
        # notification associated with this request object
        note_dict = None
        error_message = None
        try:
            note_dict = request_object.get("notification")
            request_object_id = request_object.get("id")
            # if request_object is a dictionary (a JSON object), but doesn't have a "notification" key, raise an error
            if not note_dict:
                raise ValidationException("JSON object did not contain a notification")
            # if we have a "notification" key, but does not have a "metadata" sub key, raise an error
            if not note_dict.get("metadata"):
                raise ValidationException("JSON notification has no article metadata")
            # if request_object didn't have an accompanying id, raise an error
            if not request_object_id:
                raise ValidationException("JSON did not have an id key")

            # ZZZ - API v3 - Multi-version API code - could modify / comment out if no longer supporting multiple versions of API
            _validate_convert_note_to_v4(note_dict, api_vers)
            unrouted = JPER.create_unrouted_note(pub_acc, note_dict, None)
        except ValidationException as e:
            error_message = error_message_formatter(f"Invalid notification: {str(e)}", request_object_id)
        # an AttributeError will occur if an item in our list is not an object (performing .get() on a non dict object)
        except AttributeError as e:
            error_message = error_message_formatter(
                f"A notification in the list is not a JSON object: {str(e)}", request_object_id)
        except Exception as e:
            error_message = error_message_formatter(
                f"Unexpected error, notification unsuccessful: {str(e)}", request_object_id)
            # this was an unexpected exception, so create an error in our logs as it could indicate an issue with code
            current_app.logger.critical(repr(e), exc_info=True)
            if isinstance(e, DAOException) and e.abend:
                DAO.abnormal_exit(e, "Create from list ")

        # if we had any errors during processing of this notification
        if error_message:
            # if we haven't successfully managed to create any request_objects out of this list yet, then assume
            # all items in this list are garbage and exit with an error immediately
            if len(success_ids) == 0:
                return abort_failed_request(f"Further processing of notifications list abandoned: {error_message}")

            status_code = 202
            current_app.logger.warning(error_message)
            fail_ids.append(request_object_id)
            if deposit_record:
                deposit_record.error = error_message
                if note_dict:
                    _store_deposit_in_tmparchive(pub_acc.uuid, deposit_record, note_dict)

        # if we had no errors during processing of this notification
        else:
            if deposit_record:
                deposit_record.successful = True
                deposit_record.notification_id = unrouted.id
                _store_deposit_in_tmparchive(pub_acc.uuid, deposit_record, note_dict)
            success_ids.append(request_object_id)
            created_ids.append(unrouted.id)

        if deposit_record:
            try:
                deposit_record.insert()
            except DAOException as e:
                if e.abend:
                    DAO.abnormal_exit(e, "Create from list ")

    response_json = {
        "successful": len(success_ids),
        "total": len(request_objects),
        "success_ids": success_ids,
        "fail_ids": fail_ids
    }
    if pub_acc.role == "publisher":
        response_json["created_ids"] = created_ids
        response_json["last_error"] = error_message

    # return make_response(jsonify(response_json), status_code)
    return jsonify(response_json), status_code


@blueprint.route("/notification", methods=["POST"])
@active_publisher_or_admin_org__api
def create_notification(api_vers, pub_acc=None):
    """
    Receive a POST to the /notification endpoint to create a notification, and process it
    If current_user is an admin, will not create any deposit records
    If current_user is a publisher, will create a deposit record for this notification and will store the created
    notification and the contents submitted in tmparchive if successful. If an error occurs, will store the
    JSON submitted with the request, and an overview of the contents of the request inside tmparchive.

    :param api_vers: API version - set automatically as defined in `url_defaults` when webapi blueprint is registered
    :param pub_acc: Publisher account (current_user) - SET BY DECORATOR FUNCTION
    :return: A 400 (Bad Request) if not valid, or a 202 (Accepted) if successful
    """
    # Publisher in auto-test mode isn't allowed to access this endpoint
    if pub_acc.is_publisher and pub_acc.publisher_data.in_test:
        _abort_403_forbidden("A publisher in auto-testing mode is not able to create notifications.")

    api_deposit_rec = _default_pub_api_deposit_record(pub_acc)
    try:
        note_dict, zip_content = _get_parts()
    except BadRequestException as e:
        # we couldn't extract notification metadata, so store the request as JSON in tmparchive instead
        return _notification_exception(
            pub_acc, "BadRequest _get_parts", e, api_deposit_rec, _convert_request_into_json(request))
    except Exception as e:
        # we couldn't extract notification metadata, so store the request as JSON in tmparchive instead
        return _notification_exception(
            pub_acc, "Exception _get_parts", e, api_deposit_rec, _convert_request_into_json(request))

    try:
        if zip_content:
            orig_fname = zip_content.filename or "deposit.zip"
            if api_deposit_rec:
                api_deposit_rec.name = orig_fname
            file_handle = getattr(zip_content, "stream", None)
        else:
            orig_fname = None
            file_handle = None

        # ZZZ - API v3 - Multi-version API code - could modify / comment out if no longer supporting multiple versions of API
        _validate_convert_note_to_v4(note_dict, api_vers)
            
        unrouted = JPER.create_unrouted_note(pub_acc, note_dict, file_handle=file_handle, orig_fname=orig_fname)
        # if we created a notification without useful metadata, raise an error and store a representation of the request
        # as JSON in tmparchive
        if not unrouted.data.get("metadata"):
            return _notification_exception(
                pub_acc, "Notification has no article metadata", None, api_deposit_rec, note_dict, zip_content)
    except Exception as e:
        return _notification_exception(
            pub_acc, "Exception create_notification", e, api_deposit_rec, note_dict, zip_content)

    note_id = unrouted.id
    if api_deposit_rec:
        api_deposit_rec.successful = True
        api_deposit_rec.notification_id = note_id
        api_deposit_rec.insert()
        # Since any zip file has been stored in main Store, we don't need to also save it in the tmp archive
        _store_deposit_in_tmparchive(pub_acc.uuid, api_deposit_rec, note_dict)
    _config = current_app.config
    if _config.get("LOG_DEBUG"):
        current_app.logger.debug(f"Sending 201 Created: {note_id}")
    url = _config.get("API_NOTE_URL_TEMPLATE").format(api_vers, note_id)
    # return make_response(jsonify(id=note_id, location=url), 201)
    return jsonify(id=note_id, location=url), 201


@blueprint.route("/notification/<notification_id>", methods=["GET"])
@authentication_required__api
def retrieve_notification(api_vers, notification_id):
    """
    Receive a GET on a specific notification, as identified by the notification id, and return the body
    of the notification

    :param api_vers: API version - set automatically as defined in `url_defaults` when webapi blueprint is registered
    :param notification_id: the id of the notification to retrieve
    :return: 404 (Not Found) if not found, else 200 (OK) and the outgoing notification as a json body
    """
    notification = JPER.get_outgoing_note(api_vers, current_user, notification_id)
    if notification is None:
        _abort_404_not_found("Not found")
    resp = make_response(notification.json(), 200)
    resp.mimetype = "application/json"
    return resp


@blueprint.route("/notification/<notification_id>/content", methods=["GET"])
@blueprint.route("/notification/<notification_id>/content/<path:filename>", methods=["GET"])
@authentication_required__api
def retrieve_content(api_vers, notification_id, filename=None):
    """
    Receive a GET against the default content or a specific content file in a notification and supply the binary
    in return.

    Saves details of the request in content_log table.

    :param api_vers: API version - set automatically as defined in `url_defaults` when webapi blueprint is registered
    :param notification_id: String - ID of the notification whose content to retrieve
    :param filename: the content file in the notification (either a simple filename or path ending with filename)
    :return: 404 (Not Found) if either the notification or content are not found) or 200 (OK) and the binary content
    """
    if current_app.config.get("LOG_DEBUG"):
        current_app.logger.debug(f"Notification {notification_id} file {filename} content requested")
    org_acc = current_user.copy()     # Assign to local variable for efficiency as current_user is a proxy

    log_dict = {
        "acc_id": org_acc.id,
        "note_id": notification_id,
        "filename": filename or "package-content"
    }
    try:
        filestream, file_info = JPER.get_content(org_acc, notification_id, filename)
        log_dict["source"] = "store"
        # Where filename was not supplied (as param) then overwrite the "package-content" value (set above) with
        # package filename. Note that file_info["filename"] is always a pure filename (no path element).
        if not filename:
            log_dict["filename"] = file_info["filename"]
        return Response(stream_with_context(filestream),
                        mimetype=file_info["mimetype"],
                        headers={"Content-Disposition": f'inline; filename="{file_info["filename"]}"'})
    except ForbiddenException as e:
        log_dict["source"] = "forbidden"
        # return make_response(jsonify(error=str(e)), 403)
        return jsonify(error=str(e)), 403
    except ContentException as e:
        log_dict["source"] = "notfound"
        # return make_response(jsonify(error=str(e)), 404)
        return jsonify(error=str(e)), 404
    except Exception as e:
        log_dict["source"] = "error"
        current_app.logger.critical(f"API error while retrieving content: {str(log_dict)}. Exception: {str(e)}",
                                    extra={"subject": "API retrieve content failure"})
        # return make_response(jsonify(error=str(e)), 500)
        return jsonify(error=str(e)), 500
    finally:
        # This is done in all circumstances before returning: save summary in ContentLog table
        try:
            ContentLog(log_dict).insert()
        except Exception as e:
            current_app.logger.critical(f"Unexpected database error saving ContentLog: {log_dict} - {repr(e)}")



# @blueprint.route("/notification/<notification_id>/proxy/<pid>", methods=["GET"])
# NOTE: this blueprint and API endpoint has been removed as of 26/11/18 - code remains as may have use later
def proxy_content(api_vers, notification_id, pid):
    """

    :param api_vers: API version - set automatically as defined in `url_defaults` when webapi blueprint is registered
    :param notification_id: ID of notification
    :param pid: ID of proxy link
    :return:
    """
    org_acc = current_user.copy()     # Assign to local variable for efficiency as current_user is a proxy
    if current_app.config.get("LOG_DEBUG"):
        current_app.logger.debug(f"{notification_id} {pid} proxy requested")
    purl = JPER.get_proxy_url(notification_id, pid)
    log_dict = {
        "acc_id": org_acc.id if org_acc.is_authenticated else None,
        "note_id": notification_id,
        "filename": pid
    }
    if purl:
        log_dict["source"] = "proxy"
        ContentLog(log_dict).insert()
        return redirect(purl)
    else:
        log_dict["source"] = "notfound"
        ContentLog(log_dict).insert()
        _abort_404_not_found("Not found")


def _outgoing_note_list_obj(api_vers, repo_id=None):
    """
    Process a list request, either against the full dataset or the specific repo_id supplied

    This function will pull the arguments it requires out of the Flask request object.  See the API documentation
    for the parameters of these kinds of requests.

    :param api_vers: String - API version.
    :param repo_id: the repo id to limit the request to
    :return: List of notifications that are appropriate to the parameters
    """
    since = request.values.get("since")
    since_id = request.values.get("since_id")
    page = request.values.get("page", 1)
    page_size = request.values.get("pageSize", current_app.config.get("DEFAULT_LIST_PAGE_SIZE", 25))

    if not since and not since_id:
        _abort_400_bad_request("Missing required parameter 'since' (date-time) or 'since_id'")

    if since:
        try:
            since = dates.reformat(since)
        except ValueError:
            _abort_400_bad_request(f"Unable to understand since date '{since}'")

    if since_id:
        try:
            since_id = int(since_id)
        except ValueError:
            _abort_400_bad_request("Parameter 'since_id' is not an integer")

    try:
        page = int(page)
    except ValueError:
        _abort_400_bad_request("Parameter 'page' is not an integer")

    try:
        page_size = int(page_size)
    except ValueError:
        _abort_400_bad_request("Parameter 'pageSize' is not an integer")

    try:
        return JPER.outgoing_notes_list_obj(
            api_vers, since=since, since_id=since_id, page=page, page_size=page_size, repository_id=repo_id)
    except ParameterException as e:
        _abort_400_bad_request(str(e))
    except Exception as e:
        _abort_500(f"Unexpected error: {repr(e)}")


@blueprint.route("/routed", methods=["GET"])
@blueprint.route("/routed/<repo_uuid>", methods=["GET"])
@authentication_required__api
def list_repository_routed(api_vers, repo_uuid=None):
    """
    List all the notifications that have been routed to the specified repository, limited by the parameters supplied
    in the URL.

    See the API documentation for more details.

    :param api_vers: API version - set automatically as defined in `url_defaults` when webapi blueprint is registered
    :param repo_uuid: the UUID of the reponsitory whose notifications are to be retrieved
    :return: a list of notifications appropriate to the parameters
    """
    org_acc = current_user.copy()     # Assign to local variable for efficiency as current_user is a proxy
    if org_acc.is_super:
        if not repo_uuid:
            _abort_400_bad_request("A repository account UUID must be provided.")
        acc = AccOrg.pull(repo_uuid, pull_name="uuid")
        if acc is None:
            _abort_404_not_found(f"No repository account with UUID: {repo_uuid}.")
    else:
        if repo_uuid and org_acc.uuid != repo_uuid:
            _abort_403_forbidden(f"You may only retrieve notifications for repository id: {org_acc.uuid}.")
        acc = org_acc
        
    note_list = _outgoing_note_list_obj(api_vers, acc.id)     # Aborts with 400 or 500 if error

    resp = make_response(note_list.json(), 200)
    resp.mimetype = "application/json"

    return resp


def post_patch_matching_params(acc):
    """
    Insert or Update matching parameters from JSON or file.
    :param acc: Object - account for which matching params being changed
    :return: Tuple - (Boolean-error-indicator, Message-string)
    """
    if request.method not in ('POST', 'PATCH'):
        return False, f"Requested HTTP method ({request.method}) is NOT supported."

    repo_id = acc.id
    params_loaded = None
    add_to_existing = request.method == "PATCH"
    try:
        # JSON upload
        if request.is_json:
            # JSON upload
            params_loaded, redundancies, matching_params = AccRepoMatchParams.update_match_params(
                repo_id, acc.org_name, acc.uuid, jsoncontent=request.json, add=add_to_existing)
        # CSV upload
        elif request.files:
            file = request.files['file']
            if file.filename.endswith('.csv'):
                params_loaded, redundancies, matching_params = AccRepoMatchParams.update_match_params(
                    repo_id, acc.org_name, acc.uuid, csvfile=file, add=add_to_existing)
    # valid file type, but some validation went wrong in the upload
    except Exception as e:
        current_app.logger.warning(
            f"Problem updating matching parameters for acc id {repo_id} ({acc.org_name}): {repr(e)}")
        return False, "Invalid content in matching parameters (no changes were made)."

    # no valid file or JSON submitted at all
    if not params_loaded:
        return False, "Problem setting matching parameters - ensure you submit valid data."
    else:
        msg = "Your matching parameters have been updated & the previous version archived."
        # if there is a list of length > 0 (there are actual removed redundancies to report to the user)
        if redundancies:
            msg += ("<br>A number of duplicate or redundant parameters were removed - see following:<ul><li>" +
                    "</li><li>".join(redundancies) + "</li></ul>")
        return True, msg


@blueprint.route("/config", methods=["GET", "POST", "PATCH"])
@blueprint.route("/config/<repo_uuid>", methods=["GET", "POST", "PATCH"])
@authentication_required__api
def config(api_vers, repo_uuid=None):
    """
    For GET (retrieving config), POST (submitting new/replacing existing config) & PATCH (adding to existing config)
    requests relating to a repository's matching parameters config.

    For repository/admin users only.

    Repository users may not use this endpoint to specify a repository id, the repository id they are using is
    implied by the user making the request. Admin users may (and must, to effectively use this endpoint as an admin
    account itself has no repository configuration) specify a repository UUID, this will be the repository's
    configuration which is retrieved or updated/created.

    A GET request will return a JSON object containing the contents of the target repository's configuration. If no
    configuration currently exists for that repository, it will be created and display the empty JSON object.

    A POST request must contain either JSON data, with mimetype of application/json. Or it may contain a csv file in
    the forms with enctype="multipart/form-data", the key value of this form submission must be "file". Successfully
    validated csv/JSON content will be uploaded, and return a 202 with a list of redundancies removed during upload.
    Failure will result in a 400.

    :param api_vers: API version - set automatically as defined in `url_defaults` when webapi blueprint is registered
    :param repo_uuid: Repository UUID (NB. NOT id)

    :return: 200 with JSON content on successful GET 204 on successful POST 400 with error message on unsuccessful
    POST 401 with error message on unauthenticated request.
    """
    org_acc = current_user.copy()     # Assign to local variable for efficiency as current_user is a proxy
    # if current_app.config.get("LOG_DEBUG"):
    #     current_app.logger.debug(f"API: config {request.method} for {user_acc.id}")

    if org_acc.is_super:
        if not repo_uuid:
            _abort_400_bad_request("A repository UUID must be provided.")
        acc = AccOrg.pull(repo_uuid, pull_name="uuid")
        if not acc or not acc.is_repository:
            _abort_404_not_found(f"No repository account with UUID: {repo_uuid}.")
    elif org_acc.is_repository:
        if repo_uuid is None or repo_uuid == org_acc.uuid:
            acc = org_acc
        else:
            _abort_403_forbidden(f"You are not authorised to access account: {repo_uuid}.")
    else:
        _abort_403_forbidden("Only an admin or repository user can access this endpoint.")

    ## If we get this far we have both repo_id and acc ##
    if request.method == 'GET':
        matching_params = AccRepoMatchParams.pull(acc.id)
        return jsonify(matching_params.matching_config), 200
    # user attempting to change/add config
    else:
        is_ok, msg = post_patch_matching_params(acc)
        if not is_ok:
            _abort_400_bad_request(msg)

        # Matching params successfully loaded
        return "", 204
