import click
from router.jper_sword_out.app import app
from router.jper_sword_out.deposit import Deposit
from router.shared.models.note import RoutedNotification
from router.shared.models.account import AccOrg


def load_cli():
    """
    Function to create the click group for sword-out.

    The name of the command group is defined in the entry_points section of setup.py.

    """
    @click.group()
    def sword_out_cli():
        pass

    @sword_out_cli.command("resend-note")
    @click.argument('note_id')
    @click.argument('account_id')
    # This needs to be decorated with the app otherwise it won't be in scope for the RoutedNotification use.
    def resend_notification(note_id, account_id):
        """
        Resend a notification to a specific repository using the command line.

        example:
        flask sword-out resend-note (note_id) (account_id)

        :param note_id: ID of notification to resend
        :param account_id: ID of account to resend the notification to
        """
        with app.app_context():
            note = RoutedNotification.pull(note_id)
            # If notification exists and has been matched (routed) to the specified repository
            if note is not None and account_id in note.repositories:
                account = AccOrg.pull(account_id)
                Deposit.init_cls().process_notification(account, note.make_outgoing())
            else:
                print(
                    f"ERROR: Either the notification with id '{note_id}' did not exist, or the account with id '{account_id}' did not match the notification."
                )

    return sword_out_cli


with app.app_context():
    cli = load_cli()
