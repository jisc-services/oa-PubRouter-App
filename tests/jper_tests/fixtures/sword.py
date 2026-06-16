from werkzeug.datastructures import Authorization


def basic_auth(username, password):
    """
    Create a werkzeug Authorization object for testing

    This is used in JPERSwordAuth

    :param username: Username to put in the auth object
    :param password: Password to put in the auth object

    :return: Authorization object for basic auth with the given username and password
    """
    return Authorization("basic", {"username": username, "password": password})
