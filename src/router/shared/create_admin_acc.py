"""
Create an admin user account if one doesn't already exist
"""
from werkzeug.security import generate_password_hash
from router.shared.models.account import AccOrg, AccUser


def create_admin_user(api_key=None):
    """
    Initialise the application at startup.

    Ths function will be executed for you whenever you start the app.

    It will do the following:
        0. Check if 'admin' user account already exists
    If it doesn't:
        1. Create the initial admin Org account
        2. Create Org-Admin user account, with username 'admin'.

    :param api_key: String - OPTIONAL API key
    :return: Tuple: (Boolean: True - New Admin account created; False - Admin account already existed, User Account object)
    """
    # If admin user account doesn't exist
    username = "admin"

    user_acc = AccUser.pull_user_n_org_ac(username, "username")
    if user_acc is None:
        if api_key is None:
            api_key = username
        org_acc = AccOrg({
            "api_key": api_key,
            "role": "A",
            "org_name": "Jisc Admin"
        })
        org_acc.insert()

        print(f"\nSuperOrganisation account with Id [{org_acc.id}] created for user '{username}' with api_key '{api_key}'.")

        ## Create Org Admin user account

        user_acc = AccUser({
            "acc_id": org_acc.id,
            "username": username,
            "surname": "Administrator",
            "forename": "Default",
            "role_code": "A",
            "password": generate_password_hash(username),
            "failed_login_count": 0,
            "direct_login": True    # Login doesn't require an access link sent by email
        })
        user_acc.insert()  # This generates the UUID
        user_acc.acc_org = org_acc  # Assign it's parent account
        print(f"\nSuperuser Admin User account with Id [{user_acc.id}] created for user '{username}' with password '{username}'.")

        print("\nTHIS SUPERUSER ACCOUNT IS INSECURE - CHANGE PASSWORD IMMEDIATELY...\n")
        is_new_acc = True
    else:
        org_acc = user_acc.acc_org
        print(f"\nAdmin user account Id [{user_acc.id}] with username '{username}' for Organisation Id [{org_acc.id}] ({org_acc.org_name}) already exists.")
        is_new_acc = False
    return is_new_acc, user_acc
