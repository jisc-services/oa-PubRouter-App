import os
import json
import shutil
from logging import WARNING

from flask import request, send_file, make_response, jsonify

from octopus.modules.logger.logger import init_logger
from octopus.core import create_app

# Load base configuration (used by all environments) and environment specific config
app = create_app(__name__,
                 ["router.shared.global_config.base",
                  "router.shared.global_config.{env}",
                  "router.store.config.base",
                  "router.store.config.{env}"])

logger = init_logger(name="store",
                     log_level=app.config.get("LOGLEVEL", "INFO"),
                     log_file=app.config.get("LOGFILE"),
                     flexi_cutover=WARNING  # Warning
                     )

def _http_json_error(status_code, error_message='Problem with request'):
    """
    JSONified version of Flask's abort function.

    Will abort the request and return a JSON response with a set error message.

    @param status_code: Status code to return in the response
    @param error_message: Error message to add to the JSON response
    """
    # return make_response(jsonify(error=error_message), status_code)
    return jsonify(error=error_message), status_code

@app.route('/')
@app.route('/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE'])
def storage(path=''):

    if '..' in path or path.startswith('/'):
        msg = f"Invalid path '{path}'"
        logger.error(msg)
        return _http_json_error(400, msg)

    dir = app.config['STORE_MAIN_DIR'] + '/' + path
    logger.info(f"{request.method} path: {path}")

    # No path specified, so return directory listing
    if path == '':
        try:
            listing = os.listdir(dir)
        except Exception as e:
            msg = f"Cannot list directory {dir}. Error: {str(e)}."
            logger.error(msg)
            return _http_json_error(404, msg)
        resp = make_response(json.dumps(listing))
        resp.mimetype = "application/json"
        return resp

    # Retrieve file or get directory listing of path
    if request.method == 'GET':
        try:
            # If required path is a file, then return the file
            if os.path.isfile(dir):
                return send_file(dir)

            # Path is not recognized as a file, assume it is a directory and attempt to return listing
            listing = os.listdir(dir)
            resp = make_response(json.dumps(listing))
            resp.mimetype = "application/json"
            return resp
        except Exception as e:
            msg = f"Path '{dir}' doesn't exist. Error: {str(e)}"
            logger.error("(GET) " + msg)
            return _http_json_error(404, msg)

    if request.method == 'DELETE' or (request.method == 'POST' and request.form.get('submit', '').lower() == 'delete'):
        try:
            if os.path.isfile(dir):
                os.remove(dir)
            else:
                shutil.rmtree(dir)
            return ''
        except Exception as e:
            msg = f"Cannot delete '{dir}'. Error: {str(e)}"
            logger.error("(DELETE) " + msg)
            return _http_json_error(404, msg)

    if request.method == 'POST':
        # Split the directory into 2 parts, assume the last segment is the filename
        sdir = dir.rstrip('/').rsplit('/', 1)[0]
        try:
            # Create target directory if it doesn't already exist
            if not os.path.exists(sdir):
                os.makedirs(sdir)

            file = request.files.get('file')
            # If file was POSTed
            if file:
                file.save(dir)
            # Otherwise, assume raw file data or JSON object has been POSTed
            else:
                data = ''
                write_mode = 'w'
                if request.data:
                    data = request.data
                    # Convert a dict to a string representation
                    if isinstance(data, dict):
                        data = json.dumps(data)
                    # otherwise if data NOT a string, assume it is bytes sequence so set file write mode accordingly
                    elif not isinstance(data, str):
                        write_mode = 'wb'  # write as binary data
                elif request.is_json:
                    data = json.dumps(request.json)

                if len(data) == 0:
                    msg = f"No data to write to '{dir}'"
                    logger.error("(POST) " + msg)
                    return _http_json_error(400, msg)
                else:
                    out = open(dir, write_mode)
                    out.write(data)
                    out.close()
        except Exception as e:
            msg = f"Failed to save content to '{sdir}'. Error: {str(e)}"
            logger.critical(f"(POST) {msg}", extra={"subject": "Store save failed"})
            return _http_json_error(400, msg)

        return ''

    # PUT is used to create a directory
    if request.method == 'PUT':
        if os.path.exists(dir):
            msg = f"Path '{dir}' already exists"
            logger.error("(PUT) " + msg)
            return _http_json_error(400, msg)
        try:
            os.makedirs(dir)
        except Exception as e:
            msg = f"Failed to make directory '{dir}'. Error: {str(e)}"
            logger.critical(f"(PUT) {msg}", extra={"subject": "Store directory creation"})
            return _http_json_error(400, msg)
        return ''

    msg = f"Unexpected request method: {request.method}"
    logger.error(msg)
    return _http_json_error(400, msg)


if __name__ == "__main__":
    if not os.path.exists(app.config['STORE_MAIN_DIR']):
        print('Storage folder does not exist!')
        exit(1)
    else:
        app.run(
            host='0.0.0.0',
            port=app.config['PORT'],
            threaded=app.config['THREADED']
        )
